# Forge Neo Compatibility Audit — v0.4.2 candidate

Audit date: 2026-08-20 JST
Target: `Haoming02/sd-webui-forge-classic` branch `neo`
Verified upstream head: `e782dc3fe07deb4653a8a1a1ad8ffa52783f54c5`

This document records the current compatibility assessment for the **draft v0.4.2 candidate**. It intentionally does not claim full release validation: a real Forge Neo GPU/UI/save smoke test remains outstanding.

## Scope re-checked

The audit traced the current Forge Neo implementation for:

- `setup_prompts()` and prompt-list sizing;
- `process()` / `before_process_batch()` ordering;
- partial final batches;
- Extra Networks / LoRA parsing;
- Hires.fix prompt arrays and first-pass intermediate saves;
- `iteration` and `batch_index` assignment;
- final-image and auxiliary-image save calls;
- final grid construction/save;
- `images.save_image()` filename generation and `before_image_saved` timing;
- `save_images_add_number`, empty decorations, `basename`, `forced_filename`, and collision policy;
- img2img Batch processing-object reuse;
- global callback ordering and script source reload behavior;
- Forge's queued Gradio generation path;
- current Forge-compatible Dynamic Prompts fork behavior.

The Forge prompt parser was also re-checked: `=` is plain prompt text in the current schedule grammar, while the extension resolves its syntax before conditioning/Extra Networks parsing.

## Findings and fixes

### High — v0.4.1 could reset destination numbering and overwrite routed images

Forge computes a numbered filename in its original output directory **before** `before_image_saved`. v0.4.1 then moved that filename into `A/`, `B/`, etc. Because the original directory could remain empty, Forge could propose the same number again. With Forge's normal Override collision behavior, a later routed save could replace an earlier file.

**v0.4.2 fix:** when Forge actually enabled numbering, the extension mirrors Forge's sequence scan in the **real destination choice folder** and rewrites only the numeric prefix. Regression coverage simulates Forge proposing `00000-same.png` twice and verifies the routed results become `A/00000-same.png` and `A/00001-same.png`.

### High — the first v0.4.2 grid-marker approach also matched live-preview grids

An earlier candidate used the global `image_grid` callback as a “next save is a grid” marker. Forge also calls `images.image_grid()` to build live-preview progress grids. A live-preview callback could therefore cause the next real sample save to be skipped by choice-folder routing.

**Final fix:** no persistent grid marker is used. `before_image_saved` is called synchronously from Forge's `modules.images.save_image()`, so the extension inspects that active call frame and reads Forge's exact `grid` value. A core saved grid has `grid=True`; a normal sample has `grid=False`. Live-preview grid creation never leaves stale save state.

### High/Medium — save numbering must match Forge's exact branch, not the global option alone

Forge can force numbering when the rendered filename decoration is empty even if the global add-number setting is off. Conversely, `forced_filename` bypasses Forge's numbering branch entirely. Numeric seed-based filenames must not be mistaken for counters when numbering is disabled.

**Fix:** the synchronous Forge save context also records the already-computed `add_number`, `basename`, and `forced_filename` values. Exact values are authoritative. `forced_filename` is never renumbered. Conservative fallback logic is used only if a future Forge refactor prevents reading the current context.

### Medium — partial save context needed a conservative grid fallback

A future Forge version could retain the same `save_image()` call while renaming/removing only its local `grid` variable. Treating “frame found” as equivalent to `grid=False` would then be unsafe.

**Fix:** `grid=None` is treated as unknown and falls back to output-root / conservative filename checks. Nested roots use the more-specific configured root. If sample and grid roots are identical/ambiguous, fallback fails closed and does not route the save. Exact `grid=False` still allows legitimate sample filenames that happen to contain the word `grid`.

### Medium — Forge's current statvfs path slicing can cut a post-callback path

On platforms exposing `os.statvfs`, current Forge Neo applies `f_namemax` to the **whole post-callback path string**, even though `f_namemax` is a component limit. Adding a choice directory can therefore make Forge slice through the added directory or reduce the remaining filename to a collision-prone fragment on already-long paths.

**Fix:** the extension budgets only its added folder before returning from the callback. It preserves the entire added directory and a useful filename prefix (the complete stem when short, otherwise at least 32 characters). If the existing parent path leaves no safe budget, folder routing is skipped for that save rather than making the original Forge save less safe.

### Medium — long Unicode folder names need byte-aware limits

Character limits alone do not protect Japanese/emoji names on filesystems with byte-based component limits.

**Fix:** each component and the combined folder are bounded by both character count and UTF-8 byte length. Deterministic hash suffixes preserve stable naming after truncation.

### Medium — Windows reserved/device names were broader than the initial list

Classic names (`CON`, `NUL`, `COM1`, etc.) are not the complete Windows reservation set.

**Fix:** the sanitizer keeps the explicit classic/superscript COM/LPT list and also uses Python 3.13 `ntpath.isreserved()` when available, covering names such as `CONIN$` and `CONOUT$`.

### Medium — malformed equals blocks and assignment-like text needed stricter boundaries

An unclosed equals block could previously search too far, and lightweight `=...=` syntax could collide with ordinary `key=value`-style prompt text.

**Fix:** opening and closing boundaries are checked; malformed earlier blocks remain literal without swallowing a later valid standalone block. The single-equals form remains strict about padding immediately inside its delimiters. The more explicit doubled folder form intentionally accepts visual padding such as `== A | B | C ==`.

### Medium — repeated batch-hook invocation could delete an already-recorded folder mapping

The first `before_process_batch()` call resolves `==...==` into plain prompt text. If the same batch hook were invoked again, the marker is naturally gone. Treating “no marker found” as an instruction to delete the folder would lose the first mapping.

**Fix:** folder mappings are recorded only when a folder marker is actually resolved. Run-level state is reset in `Script.process()`, so a repeated hook becomes idempotent instead of destructive.

### Medium/Low — stale private state could affect later saves or reused processing objects

API/batch code can reuse processing objects, and global save callbacks outlive one generation.

**Fix:** `Script.process()` clears private routing state and extension-owned metadata before checking the enabled flag. `Script.postprocess()` clears the private folder map/routing flag again after Forge's final/auxiliary/grid saves have completed, while leaving generation metadata intact. Manual UI saves therefore do not inherit a stale generated-image index.

### QA — source/hot reload could duplicate the global save callback

**Fix:** the script removes callbacks previously registered from the same source file before registering the current `before_image_saved` callback. The callback itself is also idempotent for one `ImageSaveParams` object.

## Compatibility conclusions

### Batch size / count

Per-image sequencing uses Forge's global image position `batch_number * batch_size + local_index`. A partial final batch therefore continues at the correct global position. Per-batch mode intentionally advances using the full configured Forge batch unit.

### Hires.fix

`all_hr_prompts` and `all_hr_negative_prompts` are resolved before Forge slices/parses them. Hires first-pass intermediate saves are excluded while Forge reports `is_hr_pass=True`. Folder identity is intentionally taken only from the main positive prompt.

### LoRA / Extra Networks

Resolution occurs in `before_process_batch()`, which current Forge documents/calls before Extra Networks parsing. LoRA tags can therefore be selected normally. Folder-marker LoRA choices are independently sanitized only for filesystem naming.

### Dynamic Prompts

The current Forge-compatible Dynamic Prompts fork expands/replaces `p.all_prompts`, negative prompts, seeds/count, and Hires arrays in its `process()` callback. Sequential Prompts intentionally does not resolve templates in its own `process()`; it waits until `before_process_batch()`. This makes Dynamic Prompts expansion happen first regardless of the relative order of their `process()` callbacks.

### img2img Batch

Forge processes each input file as a separate `process_images()` invocation while reusing the processing object. Because Sequential Prompts resets run state at each invocation, the sequence **restarts from Start index for every input file**. This is deterministic but is not a directory-wide global counter.

## Automated verification

Current local Python 3.13 verification:

```bash
python -m compileall -q seqprompt scripts tests
python -m unittest discover -s tests -v
git diff --check
```

Result: **94 tests passed**; compile and whitespace checks passed.

Coverage includes:

- Per image / Per batch; Batch size/count; Repeat; Start; Loop/Clamp;
- full and partial batches;
- normal, doubled-folder, and legacy syntax;
- malformed-block recovery and assignment/key-value false-positive boundaries;
- escaping and unrelated-backslash preservation;
- repeated batch-hook idempotency;
- positive/negative/Hires synchronization;
- negative/Hires-only folder markers not controlling output directories;
- Dynamic Prompts-style pre-expansion;
- normal and folder-marker LoRA choices;
- multi-marker folder naming;
- Windows invalid/reserved/device names;
- Unicode character/byte limits;
- traversal/symlink-aware containment;
- exact Forge save-context extraction using real Python frames;
- exact/fallback grid detection, including shared and nested output roots;
- destination-folder numbering, basename handling, forced filenames, numeric-seed false positives;
- long Forge parent-path budgeting;
- duplicate save-callback invocation;
- reused/disabled run-state cleanup;
- Forge-style Script callback contract.

The GitHub Actions matrix is configured for Python 3.13 on both Ubuntu and Windows. The revised third-pass head must pass both jobs again after it is pushed.

## Residual risks / release gates

1. **Real Forge Neo GPU/UI E2E remains the final release gate.** Unit/contract tests cannot prove actual Windows txt2img/img2img/Hires generation and disk writes end to end.
2. **Late third-party image reordering is not fully trackable.** An extension may add/remove/reorder tensors in `postprocess_batch_list`. Forge requires it to update prompts/seeds, but Forge exposes no stable custom per-image identity that this extension can use to follow arbitrary reordering, especially when LoRA-only choices collapse to the same parsed prompt text.
3. **Callback priority remains user-configurable.** An extension intentionally rewriting prompts after this extension's `before_process_batch` can change the final result; a later `before_image_saved` callback can also move/rename the path after this extension.
4. **img2img Batch restarts per input file.** Directory-wide continuation is not implemented.
5. **Video/Wan batching is not release-tested.** Wan can change effective sampling batch behavior relative to configured `p.batch_size`.
6. **Concurrent direct callers outside Forge's normal queue can race destination numbering.** Normal Gradio GPU jobs are serialized by Forge's queue lock.
7. Distinct raw choices can sanitize/case-fold/join to the same directory and intentionally share its numbering sequence.
8. Extremely long **pre-existing** output paths can still fail in Forge/OS code even when this extension elects not to add a folder.
9. Nested sequential blocks and native sequential wildcard files remain unsupported.
10. The repository has no explicit license file.

## Release recommendation

Keep PR #2 **draft**. Push this third-pass implementation, require fresh Ubuntu + Windows CI success, then run a real Forge Neo smoke matrix before merging to `main`:

1. txt2img Per image, Batch size 1/count 3 → A/B/C;
2. txt2img Per image, Batch size 3 → A/B/C in one batch;
3. Per batch → AAA/BBB/CCC;
4. `==A|B|C==, =D|E|F=` → A/B/C folders with matching prompt pairs;
5. repeated cycle back into A verifies no overwrite and ascending destination numbering;
6. shared/custom grid output configuration verifies grid exclusion;
7. Hires.fix, including optional first-pass save;
8. Dynamic Prompts enabled;
9. LoRA choices and folder-marker LoRA choices;
10. img2img normal and img2img Batch behavior on Windows.
