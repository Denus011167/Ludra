# Ludra — asset origins and licensing notes

This document describes the assets included with Ludra. **The MIT license at the repository root applies to Ludra's original source code; it does not by itself grant rights to third-party fonts, game artwork or trademarks.**

## ChatGPT-generated artwork

The project owner reports that the following assets were generated with ChatGPT during Ludra's development:

- Six bundled abstract wallpapers (`background-*.jpg`) and their preview thumbnails (`background-thumb-*.jpg`).
- The Behind the Scenes collage (`ludra-behind-the-scenes.png`), including the fictional Ludra band imagery.
- The project's other generated illustration and controller components, insofar as used in the bundled logo and icon graphics. **Exact component provenance should be confirmed before treating each such graphic as independently cleared.**

The collage includes partly blurred fictional band artwork. Blurring is a precaution, not proof that all depicted material is free of third-party rights.

These images are identified as AI-generated. Their inclusion is subject to applicable OpenAI terms and any third-party rights that might be implicated by specific content. This notice is not a legal warranty of originality or exclusive copyright ownership.

## Moonhouse typeface

The Ludra wordmark uses lettering based on **Moonhouse**, attributed in font listings to **NimaType / NimaVisual**.

- Reference: https://www.fontspace.com/moonhouse-font-f18420
- The rendered wordmark/logo images are distributed as graphics.
- **No Moonhouse `.ttf` or `.otf` font file is included** in the inspected Ludra 1.0.0 RC1 source archive.
- The typeface is separate third-party material, **not MIT-licensed by Ludra**. The exact license accompanying the font/version used should be retained and checked, especially for logo use and any future redistribution of font binaries.

## Game covers and external services

Ludra can display artwork supplied by Steam, SteamGridDB, and/or the user. Such artwork remains subject to its respective owner or provider's terms. The Ludra MIT source-code license does not cover third-party game covers. Public screenshots should use appropriately cleared artwork and should not expose personal API credentials.

## Review before public publication

- Visually inspect the released logo, icons and collage for recognisable third-party protected material or marks.
- Verify the exact Moonhouse font license used to create the wordmark; do not bundle font binaries without redistribution rights.
- Review screenshots for private data, game cover rights and accuracy (distinguish actual app screenshots from generated promotional mockups).
- Disclose AI involvement accurately in any distribution venue that requires it, and comply with that venue's submission rules.

This notice documents provenance and known limitations; it is **not legal advice or a blanket declaration that all assets are cleared**.
# Asset rights review — pending

This file documents open questions; it is **not** a grant of permission or a claim that these assets are MIT-licensed.

- `ludra-final-logo-header.png`, `ludra-about-medium.png`: Moonhouse-based lettering and controller composition. Verify the font license and any source artwork rights, including whether rendering in a logo is permitted.
- `ludra-icon*.png`: Verify artwork ownership and any source materials.
- `background-*.jpg` and `background-thumb-*.jpg`: Verify origin, license, and permission for redistribution.
- `ludra-behind-the-scenes.png`: Review the historical collage for third-party logos, fonts, and other embedded material.

These assets are included in this **private working source snapshot** because the application references them. Their inclusion does not establish permission to publish or redistribute them. Remove or replace anything that cannot be cleared before making the repository public.

No Moonhouse font binary is intentionally bundled in this source snapshot.
