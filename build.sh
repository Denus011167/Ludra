#!/usr/bin/env bash
set -euo pipefail

APP_ID="io.github.Denus011167.Ludra"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$PROJECT_DIR/io.github.Denus011167.Ludra"
# One source of truth for About, Flatpak metadata and installed-version checks.
VERSION_FILE="$APP_DIR/VERSION"
EXPECTED_VERSION="$(tr -d '\r\n' < "$VERSION_FILE")"
[[ "$EXPECTED_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-rc[0-9]+)?$ ]] || {
  echo "ERROR: Invalid release version in $VERSION_FILE: $EXPECTED_VERSION"; exit 1;
}
# Synchronize AppStream release metadata before invoking Flatpak Builder.
python3 - "$APP_DIR/io.github.Denus011167.Ludra.metainfo.xml" "$EXPECTED_VERSION" <<'PYXML'
import sys, datetime, xml.etree.ElementTree as ET
path, version = sys.argv[1:]
tree = ET.parse(path)
root = tree.getroot()
releases = root.find('releases')
if releases is None:
    releases = ET.SubElement(root, 'releases')
entry = releases.find('release')
if entry is None:
    entry = ET.SubElement(releases, 'release')
if entry.get('version') != version:
    entry.set('date', datetime.date.today().isoformat())
entry.set('version', version)
tree.write(path, encoding='utf-8', xml_declaration=True)
PYXML
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

echo "==> Safe build-only mode: installed Ludra was NOT changed."
cp -f Ludra.flatpak "$PROJECT_DIR/Ludra-v1.0.0-TEST.flatpak"
echo "==> Bundle created: $PROJECT_DIR/Ludra-v1.0.0-TEST.flatpak"
echo "==> To test without replacing RC5, use a separate Flatpak installation (instructions in TESTING.md)."
