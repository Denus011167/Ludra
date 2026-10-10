# Ludra

**Your games. One place.**

Ludra is a visual game launcher for Linux, with Steam game discovery, cover artwork management, backgrounds, library sorting, launch overrides, hidden-item management, and support for manually added non-Steam games.

**Status:** Version 1.0.0 RC1 — private release-preparation draft. Tested by the project owner on Bazzite. **Not yet cleared for public distribution.**

## Project layout

- `io.github.Denus011167.Ludra/main.py` — Python/GTK launcher
- `io.github.Denus011167.Ludra/flatpak.yml` — local Flatpak build manifest (see release notes before submission)
- `io.github.Denus011167.Ludra/*.desktop`, `*.metainfo.xml` — application metadata
- `build.sh` — local Bazzite builder and installer (changes the installed user Flatpak)
- `migrate-from-steamgallery.sh` — optional data migration helper
- `LICENSE` — MIT license for original project source code only
- `ASSET-LICENSING.md` — asset licensing review and exclusions
- `RELEASE-READINESS.txt` — outstanding release checks

## Testing on Bazzite

On a machine where you intend to install or replace Ludra, run `./build.sh` from the repository root. **This script replaces the installed user Flatpak for the existing app ID.** Read it first. Do not run it merely to inspect the repository.

## License

Original Ludra source code: MIT, © 2026 Denus01. See `LICENSE`. The MIT statement does **not** assert rights over third-party fonts, externally sourced artwork, or embedded media; see `ASSET-LICENSING.md`.

## Publishing

This repository is being prepared privately. Before making it public, verify the provenance and publication rights of all images and lettering, prepare screenshots and review project metadata. Flatpak/Flathub submissions must follow the applicable current policies. This manifest is retained from the already tested local package; it is not presented as a Flathub-ready submission.
