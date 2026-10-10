# Ludra

**Your games. One place.**

Ludra is a visual game launcher for Linux, built with Python and GTK. It brings Steam games and manually added games into a customizable gallery.

**Current release:** 1.0.0 RC1 (pre-release). Tested on two Bazzite computers using Bazzite's preinstalled Steam. Other Linux distributions and Steam installations have not yet been comprehensively tested.

## Features

- Discover and launch games from a local Steam library.
- Add non-Steam games manually with launch commands.
- Choose cover artwork, including custom images and optional SteamGridDB integration.
- Customize wallpapers, gallery layout, sorting and appearance.
- Hide and restore entries in the game library.
- Use keyboard shortcuts and configurable launcher preferences.

## Install

Download the `.flatpak` bundle from the project's **Releases** page when the release is published. Follow the instructions in [INSTALL.md](INSTALL.md), including requirements, installation, update limitations, and removal.

This standalone Flatpak bundle does **not** automatically receive updates. The GitHub release remains a draft during final publication checks.

## Source layout

- `io.github.Denus011167.Ludra/main.py` — Python/GTK application.
- `io.github.Denus011167.Ludra/flatpak.yml` — local Flatpak build manifest, **not an approved Flathub submission**.
- `io.github.Denus011167.Ludra/*.desktop` and `*.metainfo.xml` — desktop and AppStream metadata.
- `build.sh` — local Bazzite build/install script; review it before running, as it can replace the installed user Flatpak.
- `migrate-from-steamgallery.sh` — optional migration helper.
- `LICENSE` — MIT license covering original Ludra source code.
- `ASSET-LICENSING.md` — provenance and licensing notes for bundled artwork and typefaces.
- `screenshots/` — application screenshots.

## Licensing and acknowledgements

Original Ludra source code: **MIT**, © 2026 Denus01. See [LICENSE](LICENSE).

The MIT license does not automatically apply to third-party fonts, game-cover artwork, trademarks or media. See [ASSET-LICENSING.md](ASSET-LICENSING.md) for details. Ludra uses a Moonhouse-based rendered wordmark; the Moonhouse font file is not included in the reviewed source package.

Ludra's development involved substantial assistance from ChatGPT, and several bundled illustrations and wallpapers were generated with ChatGPT. This involvement is disclosed for transparency.

## Feedback

You can use this repository's Issues tab for feedback when the repository becomes public. Please avoid sharing API keys, personal account details or sensitive logs in issue reports.

## Publication status

The source repository and standalone Flatpak release are in **pre-publication review**. Availability on GitHub does not imply availability on Flathub or Bazaar. Flathub distribution, if pursued, requires a separate review and compliance with its submission policies.
