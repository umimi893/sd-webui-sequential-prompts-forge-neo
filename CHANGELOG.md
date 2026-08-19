# Changelog

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
