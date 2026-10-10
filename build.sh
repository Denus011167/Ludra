#!/usr/bin/env bash
set -euo pipefail

APP_ID="io.github.Denus011167.Ludra"
EXPECTED_VERSION="1.0.0-rc2"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$PROJECT_DIR/io.github.Denus011167.Ludra"
MANIFEST="flatpak.yml"

command -v flatpak >/dev/null || { echo "ERROR: Flatpak is not installed."; exit 1; }

echo "==> Preparing Flathub and the official Flatpak Builder..."
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user --noninteractive -y flathub org.flatpak.Builder

echo "==> Building Ludra with org.flatpak.Builder..."
cd "$APP_DIR"
rm -rf .flatpak-builder build repo Ludra.flatpak
flatpak run --command=flathub-build org.flatpak.Builder "$MANIFEST"

echo "==> Creating standalone Ludra.flatpak bundle..."
flatpak build-bundle repo Ludra.flatpak "$APP_ID" master \
  --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo

echo "==> Replacing the installed Ludra app (user data is preserved)..."
if flatpak --user info "$APP_ID" >/dev/null 2>&1; then
  flatpak --user uninstall --noninteractive -y "$APP_ID"
fi
flatpak --user install --noninteractive -y Ludra.flatpak

echo "==> Migrating data from the old com.example.SteamGallery build, if present..."
bash "$PROJECT_DIR/migrate-from-steamgallery.sh"

cp -f Ludra.flatpak "$PROJECT_DIR/Ludra.flatpak"

# KDE normally notices Flatpak exports automatically. Refresh its application
# cache when available so Ludra appears under Games immediately after a build.
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f "$HOME/.local/share/flatpak/exports/share/icons/hicolor" >/dev/null 2>&1 || true
fi
if command -v kbuildsycoca6 >/dev/null 2>&1; then
  echo "==> Refreshing KDE application/icon cache..."
  kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
fi

echo "==> Verifying installed Ludra version..."
INSTALLED_VERSION="$(flatpak --user info "$APP_ID" 2>/dev/null | sed -n 's/^[[:space:]]*Version:[[:space:]]*//p' | head -n1)"
if [[ "$INSTALLED_VERSION" != "$EXPECTED_VERSION" ]]; then
  echo "ERROR: Expected Ludra $EXPECTED_VERSION, but Flatpak reports '${INSTALLED_VERSION:-unknown}'."
  exit 1
fi

echo "==> Ludra $INSTALLED_VERSION installed successfully."
echo "==> Flatpak created: $PROJECT_DIR/Ludra.flatpak"
echo "==> Starting Ludra..."
flatpak run "$APP_ID"
