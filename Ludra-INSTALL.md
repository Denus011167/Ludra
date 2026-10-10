# Installing Ludra on Linux

**Release:** Ludra 1.0.0 RC1  
**Architecture:** x86_64  
**Status:** Release candidate, tested on two Bazzite computers. Not yet published as a stable release.

Ludra is a visual Steam and manually added game launcher for Linux.

## Requirements

- A Linux distribution with Flatpak installed (tested on Bazzite).
- The GNOME 49 Flatpak runtime (`org.gnome.Platform//49`). Flatpak can obtain a missing runtime from a configured remote when available.
- Steam installed and configured for Steam game discovery and launching (tested with Bazzite's preinstalled Steam).
- A graphical Wayland or X11 desktop session.

## Install the downloadable Flatpak bundle

1. Download `Ludra-1.0.0-RC1-x86_64.flatpak` from the Ludra release **Assets** section when the release is published.
2. On Bazzite, open the downloaded file in the graphical Flatpak installer and choose a **User** installation.
3. Alternatively, from the folder containing the downloaded bundle, run:

   ```bash
   flatpak install --user ./Ludra-1.0.0-RC1-x86_64.flatpak
   ```

   Read Flatpak's confirmation and runtime dependency prompts before accepting. If a required runtime cannot be found, configure a trusted Flatpak remote providing it; do not download runtime files from unknown sites.
4. Launch **Ludra** from your application menu, or run:

   ```bash
   flatpak run io.github.Denus011167.Ludra
   ```

The installer has been tested by the project owner on two Bazzite computers. Other distributions and Steam installations have not been comprehensively tested.

## Existing installations

Installing the bundle with the same application ID can replace an existing user installation. Back up settings and manually added game entries before changing installations. This RC uses the application ID `io.github.Denus011167.Ludra`.

## Updating

A standalone GitHub `.flatpak` bundle **does not provide automatic updates**. To update, download and install a newer bundle. If Ludra is later released through a Flatpak remote such as Flathub, updates can be delivered through that remote instead.

## Uninstall

```bash
flatpak uninstall --user io.github.Denus011167.Ludra
```

Flatpak may ask whether application data should also be removed. If you want to preserve settings, do not request deletion of application data.

## Artwork and licenses

The original Ludra source code is licensed under MIT. Fonts, images, and other assets have separate provenance and licensing considerations; see `ASSET-LICENSING.md` in the source repository. Some artwork and parts of the application were created with ChatGPT assistance.

## Issues and feedback

Repository: https://github.com/Denus011167/Ludra

Before public publication, the maintainer must finish the asset-rights review, verify release file contents, and make the repository/release public intentionally.
