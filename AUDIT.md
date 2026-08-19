# Compatibility audit

Audit date: 2026-08-19

Extension version reviewed: **v0.4.1**

Target: Stable Diffusion WebUI Forge Neo, `Haoming02/sd-webui-forge-classic`, branch `neo`.

Upstream commit inspected: `e782dc3fe07deb4653a8a1a1ad8ffa52783f54c5` (verified as the current `neo` head on 2026-08-19).

## Scope

The review traced the extension against Forge Neo's script, prompt, Hires.fix, and image-save lifecycle, including:

- `StableDiffusionProcessing.setup_prompts()`
- `ScriptRunner.process()`
- `ScriptRunner.before_process_batch()`
- per-batch positive/negative prompt slicing
- Extra Networks parsing and activation
- Hires.fix positive/negative prompt arrays
- `iteration`, `batch_index`, and global image indexing
- `images.save_image()` and `before_image_saved`
- infotext/main-prompt synchronization
- interaction with Dynamic Prompts-style prompt-list expansion
- Python 3.13 compatibility

## Important issues fixed during the audit

### High — Hires.fix used unresolved sequential syntax

Early versions transformed only `all_prompts` and `all_negative_prompts`. Forge Neo maintains independent `all_hr_prompts` and `all_hr_negative_prompts`, so Hires.fix could receive the raw sequential template.

**Fix:** Hires.fix arrays are resolved with the same global image index immediately before each batch is parsed.

### High — prompt expansion was order-sensitive with other extensions

Resolving the full prompt list inside `process()` could collapse a sequential template before another always-on extension expanded or replaced prompts.

**Fix:** actual resolution happens in `before_process_batch()`, after all `process()` callbacks and before Forge Neo parses Extra Networks.

### Medium — unrelated backslashes could be removed

The first parser treated backslash as a generic escape even though only specific delimiters were intended.

**Fix:** only `\|`, `\=`, and `\\` are escapes; unrelated backslashes remain literal.

### Medium — `=...=` could false-positive on ordinary `key=value` text

Because `=` is intentionally lightweight syntax, text containing two ordinary equals signs with a pipe between them could previously resemble a sequence, for example `artist=foo|bar, weight=1`.

**Fix in v0.4.1:** an equals-based sequential block may start at the beginning of a prompt or after a non-word boundary, but not when the opening equals is attached directly to a letter, digit, or underscore.

### Medium — stale save-routing state on reused processing objects

Folder-routing state was reset only after confirming the extension was enabled. An API/client that reused a processing object could theoretically carry routing state into a later disabled run.

**Fix in v0.4.1:** routing state is always cleared before the enabled check.

### Low — grid heuristic could skip normal files containing `grid`

When grid and sample roots are the same, a broad filename heuristic could mistake a normal filename such as `my-grid-style.png` for a Forge grid.

**Fix in v0.4.1:** same-root fallback detection now only recognizes the normal Forge `grid`, `grid-...`, or `grid_...` basename forms.

## Folder-marker audit

`==A|B|C==` adds save-time folder routing while `=A|B|C=` remains a normal sequence.

Verified properties:

- doubled markers are parsed before single-equals markers;
- single-equals blocks never contribute folder names;
- multiple doubled markers combine deterministically as `A__D`;
- folder routing uses the global image index (`iteration * batch_size + batch_index`);
- Batch size > 1 routes each image independently;
- Windows-invalid characters and reserved device names are sanitized;
- `/`, `\\`, `..`, control characters, and path traversal cannot create parent/nested paths;
- long folder names are deterministically shortened;
- a containment guard is checked again before directory creation;
- grids are excluded from normal choice-folder routing;
- Hires.fix first-pass intermediates are excluded because Forge saves them while `is_hr_pass` is true;
- the callback creates the destination directory itself because Forge creates only the original path before `before_image_saved` runs.

## Automated verification

Run:

```bash
python -m compileall -q seqprompt scripts tests
python -m unittest discover -s tests -v
```

Current result: **54 tests passed**.

Coverage includes:

- Per image / Per batch sequencing
- Batch size and Batch count behavior
- repeat counts, start index, Loop, Clamp
- normal `=...=`, folder `==...==`, and legacy `[[...]]`
- multiple blocks and different choice counts
- escaped pipes, equals signs, and backslashes
- ordinary `key=value` false-positive protection
- positive/negative batch synchronization
- Hires.fix positive/negative arrays
- negative-processing toggle
- Dynamic Prompts-style pre-expansion
- LoRA / Extra Network choices
- per-image folder mapping across batches
- Windows-invalid/reserved/path-traversal folder inputs
- long folder names
- grid and Hires intermediate exclusions
- stale routing state reset
- Forge-style script callback registration/contract

## Residual risks / not yet proven

1. A real GPU-backed Forge Neo launch has not been executed by this test suite, so end-to-end Gradio rendering and actual image generation/saving remain the final integration check.
2. Windows and Linux save routing are covered by filesystem-level unit tests, not by a real Forge Neo process on both operating systems.
3. Nested sequential blocks are intentionally unsupported.
4. Sequential wildcard files are not implemented.
5. Another third-party extension can theoretically rewrite prompts after this extension's `before_process_batch()` callback if callback priority is manually changed.
6. Unusual distinct raw choices can sanitize to the same folder component, causing those outputs to share a folder.
7. The repository currently has no explicit license file.

## Release recommendation

v0.4.1 is suitable for normal Forge Neo user testing and substantially safer than the initial implementation. Before calling it fully release-validated, run a clean-install smoke test covering:

- txt2img with Batch size 1 and 3;
- img2img;
- Hires.fix;
- `=A|B|C=` and `==A|B|C==`;
- `==A|B|C==, =D|E|F=` folder routing;
- multiple `==...==` markers;
- Dynamic Prompts coexistence;
- a LoRA choice;
- actual image saving on Windows.
