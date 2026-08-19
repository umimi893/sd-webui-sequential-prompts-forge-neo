# Changelog

## v0.4.2 (candidate)

- Fixed a high-severity choice-folder overwrite risk by mirroring Forge numbering against the actual routed destination folder.
- Replaced the earlier global/final-grid marker design after a third audit found it could be polluted by Forge live-preview grids.
- Grid exclusion now reads Forge's exact synchronous `images.save_image()` context (`grid`) at `before_image_saved` time, with conservative fallback only when that context is unavailable or partial.
- Numbering now follows Forge's exact computed `add_number`, `basename`, and `forced_filename` state; forced/custom names and numeric seed filenames are no longer reinterpreted as counters.
- Added partial-context fallback coverage so a future Forge refactor that removes only the local `grid` variable fails conservatively.
- Added UTF-8 byte-aware folder limits and deterministic shortening for long Japanese/emoji names.
- Added a defensive budget for Forge Neo's current post-callback full-path `f_namemax` slicing; the extension preserves its whole added directory plus a useful filename prefix, or skips routing when no safe budget remains.
- Expanded Windows reserved-name coverage through Python 3.13 `ntpath.isreserved()` plus explicit classic/superscript device names.
- Hardened equals-block opening/closing boundaries and malformed-block recovery; the explicit doubled folder form accepts `== A | B | C ==` padding while the lighter single-equals form stays strict.
- Made repeated `before_process_batch()` invocation non-destructive to an already-recorded folder mapping.
- Clear stale Sequential Prompts state/metadata on reused processing objects and clear private routing state again after generation saves complete.
- Made the global save callback safe against source/hot reload duplication and repeated invocation of the same save params.
- Added direct coverage that LoRA folder markers route correctly while negative/Hires-only doubled markers never control the output folder.
- Documented deterministic img2img Batch behavior: the sequence restarts for each input file.
- Expanded CI to Python 3.13 on Ubuntu and Windows.
- Expanded automated coverage to **94 tests**.

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
