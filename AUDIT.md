# Compatibility audit

Audit date: 2026-08-19

Extension version reviewed: **v0.4.2 candidate**

Target: Stable Diffusion WebUI Forge Neo, `Haoming02/sd-webui-forge-classic`, branch `neo`.

Upstream commit inspected: `e782dc3fe07deb4653a8a1a1ad8ffa52783f54c5` (re-verified as the current `neo` head on 2026-08-19).

## Scope

This second full review retraced the extension against Forge Neo's current prompt, batching, Hires.fix, image-save, grid-save, and UI-save paths. It includes:

- `StableDiffusionProcessing.setup_prompts()`;
- `ScriptRunner.process()` and `before_process_batch()` ordering;
- prompt/negative slicing for partial and full batches;
- Dynamic Prompts-style replacement of `all_prompts`, `n_iter`, seeds, and Hires arrays;
- Extra Networks / LoRA parsing;
- Hires.fix first-pass and second-pass prompt handling;
- `iteration`, `batch_index`, and global image indexing;
- final images and auxiliary saves (pre-restoration, pre-color-correction, masks/composites);
- `images.save_image()`, Forge filename numbering, collision behavior, and `before_image_saved`;
- grid creation/saving, including shared sample/grid directories and custom filename settings;
- UI manual-save behavior;
- Windows filename rules and reserved device names;
- UTF-8 filename-component length on Linux/ext4;
- reused processing-object state;
- Python 3.13 unit/contract coverage.

## Findings from the second audit

### High — choice-folder routing could reset Forge's numeric counter and overwrite a previous output

Forge creates the filename and ascending numeric prefix **before** calling `before_image_saved`. v0.4.1 then redirected that finished filename into `A/`, `B/`, etc. Because the image never landed in the original directory, Forge's next sequence scan could see the original directory as empty and propose the same numeric prefix again.

Forge's normal defaults use an ascending number and allow the `Override` collision behavior. Repeated choice folders combined with a repeated seed/prompt or a custom filename pattern could therefore overwrite a prior routed image.

**Fix in v0.4.2:** when Forge numbering is enabled, Sequential Prompts recomputes the numeric prefix against the **actual destination choice folder**. A regression test simulates two identical Forge-proposed `00000-same.png` paths routed to the same `A/` folder and verifies the second becomes `00001-same.png` without modifying the first.

### Medium — Japanese/emoji folder names were limited by characters, not UTF-8 bytes

v0.4.1 limited folder components by Python character count. A string can be well under the character limit while exceeding a filesystem's byte limit (for example, many Japanese characters or emoji on ext4).

**Fix in v0.4.2:** folder components and combined names are bounded by both character count and UTF-8 byte count, with a deterministic hash suffix when shortened.

### Medium — a grid could be routed into the last image's choice folder under unusual save settings

v0.4.1 inferred grids from paths/filenames. If sample and grid roots were shared and Forge generated a custom/extended grid filename that did not contain an obvious `grid` token, the stale final `batch_index` could make the grid look like a normal final image.

**Fix in v0.4.2:** the extension registers Forge Neo's `image_grid` callback and marks the immediately following grid save on the current generation thread. `before_image_saved` consumes that marker and never routes the grid. A narrow filename heuristic remains only as a fallback.

### Medium — equals syntax still had avoidable false-positive forms

v0.4.1 protected the opening `=` boundary, but a closing delimiter attached directly to a word was still accepted. Spaced assignment-like text such as `foo = bar|baz = qux` also resembled the lightweight syntax.

**Fix in v0.4.2:** both opening and closing equals delimiters must be at token boundaries, and padding whitespace immediately inside `=...=` / `==...==` is not accepted. The documented form remains `=A | B | C=`.

### Low/Medium — Windows reserved device-name coverage was incomplete

v0.4.1 covered `CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, and `LPT1`–`LPT9`, but not Microsoft's documented superscript forms such as `COM¹` and `LPT³`.

**Fix in v0.4.2:** the complete documented superscript COM/LPT variants are sanitized too.

### Low — stale generation metadata could survive a reused disabled run

Routing state was already reset, but `Sequential ...` infotext metadata could remain if an API/client reused the same processing object and disabled the extension on the next run.

**Fix in v0.4.2:** all extension-owned generation metadata is cleared before the enabled check while unrelated metadata is preserved.

### QA — Windows-specific behavior was only tested on Ubuntu CI

The extension contains Windows filename rules but v0.4.1 CI ran only on Ubuntu.

**Fix in v0.4.2:** the GitHub Actions matrix now runs Python 3.13 tests on both `ubuntu-latest` and `windows-latest`.

## Previous important fixes retained

### High — Hires.fix prompt arrays

Forge Neo maintains independent `all_hr_prompts` and `all_hr_negative_prompts`. They are resolved at the same global image index as the first pass.

### High — extension ordering / Dynamic Prompts

Actual sequential resolution remains in `before_process_batch()`, after all `process()` callbacks and before Forge Neo parses Extra Networks. Dynamic Prompts can therefore expand/replace prompt lists first, and LoRA tags selected by Sequential Prompts are available before Extra Networks parsing.

### Medium — backslash handling

Only `\|`, `\=`, and `\\` are interpreted as escapes. Other backslashes remain literal.

## Folder-marker properties re-verified

`==A|B|C==` adds save-time folder routing while `=A|B|C=` remains a normal sequence.

Verified properties include:

- doubled markers are parsed before single-equals markers;
- normal markers never contribute folder names;
- multiple doubled markers combine deterministically as `A__D`;
- global index is `iteration * batch_size + local image index`;
- partial final batches are bounded by the actual sliced prompt list;
- folder routing derives only from the main positive prompt;
- Hires positive/negative arrays use the same sequence index;
- Hires first-pass intermediates are skipped while `is_hr_pass` is true;
- final Hires outputs are routed after Forge resets `is_hr_pass`;
- auxiliary image saves exposed with the same `batch_index` follow the image's choice folder;
- grids are skipped by the grid-save marker;
- manual UI saves reconstruct a lightweight processing object without the private routing-enable state, so they are not unintentionally rerouted;
- Windows-invalid characters, control characters, `..`, slashes, reserved device names, long Unicode names, and path containment are handled defensively;
- Forge numbering is recomputed per destination choice folder when numbering is enabled.

## Automated verification

Run:

```bash
python -m compileall -q seqprompt scripts tests
python -m unittest discover -s tests -v
```

Local Python 3.13 result for the v0.4.2 candidate: **68 tests passed** and `git diff --check` passed.

The GitHub Actions workflow is configured to run the same compile/tests on both Ubuntu and Windows. A branch/PR CI run is required before this candidate should replace v0.4.1 on `main`.

Coverage includes:

- Per image / Per batch sequencing;
- Batch size/count, repeat, start index, Loop, Clamp;
- `=...=`, `==...==`, and legacy `[[...]]`;
- opening/closing token-boundary false-positive protection;
- multiple blocks and differing choice counts;
- escaping and unrelated backslashes;
- positive/negative/Hires array synchronization;
- Dynamic Prompts-style pre-expansion;
- LoRA / Extra Network choices;
- per-image folder mapping across batches;
- per-folder numeric sequence preservation / overwrite regression;
- Windows invalid/reserved names, including superscript device names;
- traversal/containment guards;
- UTF-8 byte-aware Unicode shortening;
- custom/shared-directory grid saves;
- Hires intermediates and auxiliary saves;
- disabled/reused processing state and metadata;
- Forge-style callback registration.

## Residual risks / not yet proven

1. **A real GPU-backed Forge Neo generation has still not been executed by this automated suite.** Actual txt2img/img2img/Hires output is the final release gate.
2. Windows CI can validate Python/filesystem behavior, but a real Forge Neo save on the user's Windows installation is still more valuable than a stubbed contract test.
3. Another third-party extension can intentionally rewrite prompts after this extension's `before_process_batch()` callback if callback priority is manually changed.
4. The lightweight `=...=` syntax can never be mathematically collision-proof with every possible natural prompt. The boundary rules substantially reduce false positives; use the documented standalone form.
5. Distinct raw choices can sanitize to the same folder component (including case-only differences on normal Windows filesystems); they will share a folder, though the per-folder numbering guard prevents routing-induced filename-counter reset from overwriting them.
6. Nested sequential blocks are intentionally unsupported.
7. Sequential wildcard files are not implemented.
8. Video/Wan-specific batching is not explicitly release-tested.
9. The repository still has no explicit license file.

## Release recommendation

Do **not** describe v0.4.1 as fully safe after this second audit because the save-numbering issue is material. The v0.4.2 candidate addresses every concrete issue found in this pass, but it should first pass the new Ubuntu + Windows CI matrix and then receive a clean Forge Neo smoke test, especially on Windows.
