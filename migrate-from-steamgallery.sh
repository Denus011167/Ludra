#!/usr/bin/env bash
set -euo pipefail
OLD="$HOME/.var/app/com.example.SteamGallery/data/SteamGallery"
NEW="$HOME/.var/app/io.github.Denus011167.Ludra/data/Ludra"

if [[ ! -d "$OLD" ]]; then
  echo "No old SteamGallery/Ludra data found. Nothing to migrate."
  exit 0
fi

mkdir -p "$NEW"
# Copy only when destination items do not already exist, so rerunning is safe.
cp -an "$OLD"/. "$NEW"/
echo "Migrated existing Ludra data to the new Flatpak identity."
