# Ludra

**Your games. One place.**

Ludra is a visual game launcher for Linux, built with Python and GTK4. It brings Steam games and manually added games together in a customizable gallery.

**Current published release:** [1.0.0 RC5 (pre-release)](https://github.com/Denus011167/Ludra/releases/tag/v1.0.0-rc5).

Tested on two Bazzite computers using Bazzite's preinstalled Steam. Other Linux distributions and Steam installations have not yet been comprehensively tested.

## Features

- Discover and launch games from a local Steam library.
- Add non-Steam games manually with launch commands.
- Choose cover artwork, including custom images and optional SteamGridDB integration.
- Customize wallpapers, gallery layout, sorting and appearance.
- Hide and restore entries in the game library.
- Use keyboard shortcuts and configurable launcher preferences.


## What's new in RC5

- Unified the window close buttons in Preferences and About with Ludra's visual styling.
- Added subtle hover feedback to slider handles.
- Corrected Refresh button hover artifacts while retaining its visual feedback.
- Added a central `VERSION` file to synchronize version information during local builds.
- Validated local RC5 installation from a standalone `.flatpak` bundle using a user installation on Bazzite.

## What's new in RC4

- Added brightness and contrast sliders for built-in and custom wallpapers.
- Added a Reset button to restore default wallpaper adjustments.
- Wallpaper adjustments are saved and restored between sessions.
- Refined the right-click game-cover menus with softer slate-gray styling.
- Improved the Behind the Scenes picture viewer with a fixed-size window.


## What's improved in RC3

- Improved GTK window styling for consistent rounded corners across User and System Flatpak installations on the tested Bazzite setup.
- Refined game-cover corners and artwork edge handling.
- Further visual polish and interface refinements.
- Additional stability and compatibility testing.

## Install

Download [Ludra 1.0.0 RC5](https://github.com/Denus011167/Ludra/releases/tag/v1.0.0-rc5) from GitHub Releases.

The release provides:
- A `.flatpak` bundle for installing the application.
- A source ZIP with the application files and local build script.

Exact asset names are shown on each release page; use the names actually listed for that version.

Follow [INSTALL.md](INSTALL.md) for requirements, installation, update limitations and removal.

The standalone Flatpak bundle does **not** automatically receive updates. If both User and System installations exist, check which one you're running; see [INSTALL.md](INSTALL.md).

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

The MIT license does not automatically apply to third-party fonts, game-cover artwork, trademarks or media. See [ASSET-LICENSING.md](ASSET-LICENSING.md) for details.

Ludra uses a Moonhouse-based rendered wordmark; the Moonhouse font file is not included in the reviewed source package.

Ludra's development involved substantial assistance from ChatGPT, and several bundled illustrations and wallpapers were generated with ChatGPT. This involvement is disclosed for transparency.

## Feedback

Bug reports, suggestions and testing feedback are welcome through the repository's [Issues](https://github.com/Denus011167/Ludra/issues) page.

Please avoid sharing API keys, personal account details or sensitive logs in issue reports.

## Publication status

Ludra 1.0.0 RC5 is available as a **pre-release** on [GitHub Releases](https://github.com/Denus011167/Ludra/releases/tag/v1.0.0-rc5).

Availability on GitHub does not imply availability on Flathub or Bazaar. Flathub distribution, if pursued, requires a separate review and compliance with its submission policies.
