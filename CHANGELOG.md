# Changelog

## v0.4.2

- Fixed a **high-severity save-routing issue** where Forge could compute the same numeric prefix repeatedly in the original output directory after files were redirected into choice folders. Sequential Prompts now recomputes the ascending prefix against the actual destination folder before saving.
- Added UTF-8 byte-aware folder-name limits so long Japanese/emoji choices stay below common filesystem component limits.
- Added the complete documented Windows reserved device-name set, including superscript COM/LPT names.
- Replaced grid-path guessing with a Forge `image_grid` callback marker, preventing grids from being routed into the last choice folder under shared/custom save settings.
- Clear stale Sequential Prompts generation metadata when a reused processing object later runs with the extension disabled.
- Hardened both opening and closing `=...=` / `==...==` token boundaries and stopped accepting padding spaces immediately inside equals delimiters.
- Expanded CI to Python 3.13 on both Ubuntu and Windows.
- Expanded automated coverage to 68 tests.

## v0.4.1

- Hardened `=...=` / `==...==` parsing so ordinary attached `key=value` text with pipes is not accidentally consumed as a sequential block.
- Clear stale folder-routing state even when the extension is disabled on a reused processing object.
- Record the negative-prompt processing toggle in generation metadata.
- Narrowed the grid filename heuristic so normal sample filenames containing the word `grid` are still routed.
- Added an extra path-containment guard before creating a choice folder.
- Expanded automated coverage to 54 tests.
- Reworked README documentation around the current syntax, folder routing, batching, compatibility, installation, and audit status.

## v0.4.0

- Added `==A|B|C==` folder-marker syntax.
- Added per-image output-folder routing through Forge Neo's `before_image_saved` callback.
- Multiple folder markers combine as `A__D`.
- Added Windows/path-traversal-safe folder-name sanitization and deterministic length limits.
- Added grid and Hires.fix-intermediate exclusions.

## v0.3.0

- Introduced `=A|B|C=` as the primary sequential syntax.
- Kept legacy `[[A|B|C]]` support.
- Added escaping for literal `=`, `|`, and `\` inside choices.

## v0.2.0

- Moved actual prompt resolution to `before_process_batch()` to improve coexistence with other prompt-expanding extensions.
- Added Hires.fix positive/negative prompt synchronization.
- Fixed unrelated backslashes being treated as generic escapes.
- Added LoRA / Extra Networks compatibility tests.

## v0.1.0

- Initial Forge Neo implementation using legacy `[[A|B|C]]` syntax.
- Added Per image / Per batch sequencing, repeat, start index, Loop/Clamp, and optional negative-prompt processing.
