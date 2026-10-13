# Installing Ludra on Linux

**Release:** Ludra 1.0.0 RC5 (pre-release)  
**Architecture:** x86_64  
**Status:** Pre-release software, tested on Bazzite. The RC5 standalone bundle has also been installed successfully as a User Flatpak; other distribution and Steam-installation combinations are not yet verified.

Ludra is a visual Steam and manually added game launcher for Linux.

## Requirements

- A Linux distribution with Flatpak installed (tested on Bazzite).
- The GNOME 49 Flatpak runtime (`org.gnome.Platform//49`). Flatpak can obtain a missing runtime from a configured remote when available.
- Steam installed and configured for Steam game discovery and launching (tested with Bazzite's preinstalled Steam).
- A graphical Wayland or X11 desktop session.

## Install the downloadable Flatpak bundle

1. Visit [GitHub Releases](https://github.com/Denus011167/Ludra/releases), open the latest **published** release, and download its `.flatpak` bundle from **Assets**. Use the filename actually provided there.
2. On Bazzite, open the downloaded file in the graphical Flatpak installer and choose a **User** installation. If the installer reports an existing installation, first check whether Ludra is installed for the User, System, or both.
3. Alternatively, from the folder containing the downloaded bundle, run:

   ```bash
   flatpak install --user ./NAME-OF-DOWNLOADED-BUNDLE.flatpak
   ```

   Read Flatpak's confirmation and runtime dependency prompts before accepting. If a required runtime cannot be found, configure a trusted Flatpak remote providing it; do not download runtime files from unknown sites.
4. Launch **Ludra** from your application menu, or run:

   ```bash
   flatpak run io.github.Denus011167.Ludra
   ```

The installer has been tested by the project owner on two Bazzite computers. Other distributions and Steam installations have not been comprehensively tested.

## Existing installations

Installing the bundle with the same application ID can replace an existing user installation. Back up settings and manually added game entries before changing installations. This RC uses the application ID `io.github.Denus011167.Ludra`.

## User vs. System installations

Flatpak supports separate **User** and **System** installations. If Ludra appears to remain installed after an uninstall, a copy may exist in the other installation scope. Before removing anything, check:

```bash
flatpak list --app --columns=application,installation | grep -i ludra
```

To remove a User installation only:

```bash
flatpak uninstall --user io.github.Denus011167.Ludra
```

To remove a System installation only (only if you intend to):

```bash
flatpak uninstall --system io.github.Denus011167.Ludra
```

Neither command should be used blindly, and **do not use `--delete-data`** if you want to preserve your settings and manually added entries. The recommended installation method for the GitHub bundle is **User**.

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

Before publishing a new release, the maintainer should review asset rights, verify the source archive and Flatpak bundle contents, and test the exact uploaded bundle. Being available on GitHub does not mean Ludra has been accepted by Flathub or Bazaar.
