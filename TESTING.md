# Ludra v1.0.0 — development build (NOT PUBLISHED)

Derived from the RC5 source archive. The installed RC5 application and its settings are not touched by `./build.sh`.

Changes:
- First-start default width/height changed from 1440×900 to 900×650. Already saved dimensions still take precedence.
- AppStream metadata replaced with the user-validated version, with four real screenshot URLs, OARS, website, issue tracker and Ludra Project developer.
- VERSION updated to 1.0.0; release date in metadata is PROVISIONAL and must be checked when publishing.
- Build script stops after creating `Ludra-v1.0.0-TEST.flatpak`, instead of uninstalling/reinstalling the currently installed app or launching it.

## Build
Extract this ZIP into a working directory and run `./build.sh` from its root. It needs Flatpak, internet for the builder runtime (if not installed) and org.flatpak.Builder.

## Safe testing
This build uses the SAME Flatpak app ID as RC5. DO NOT install it to the ordinary user installation if preserving RC5 is important. To test side-by-side, first create a named Flatpak installation (`flatpak --installations` to review existing installations; `flatpak --help` / `man flatpak-installation` for named installations), and install only into that named installation after verifying it is available. Alternatively use another test machine or VM.

A clean settings profile is required to observe the new first-launch defaults. Existing settings intentionally retain previously saved dimensions.

## Still to verify
- 900×650 displays roughly 3–4 covers on different display scales; adjust after real screenshots/testing.
- AppStream validation on target system and Flathub-specific lint.
- Bazaar missing icon may depend on store metadata/origin rather than icon packaging.
- Stable release date and all release documentation before publishing.
