# Sequential Prompts for Stable Diffusion WebUI Forge Neo

![tests](https://github.com/umimi893/sd-webui-sequential-prompts-forge-neo/actions/workflows/tests.yml/badge.svg)

Deterministic prompt sequencing for **Stable Diffusion WebUI Forge Neo**, with optional per-choice output-folder sorting.

Current candidate version: **v0.4.2**

Target: [`Haoming02/sd-webui-forge-classic`](https://github.com/Haoming02/sd-webui-forge-classic), branch `neo`.

Audited against Forge Neo commit `e782dc3fe07deb4653a8a1a1ad8ffa52783f54c5`, re-verified as the current `neo` head during the third audit on 2026-08-20 JST.

## Syntax

| Syntax | Meaning |
|---|---|
| `=A | B | C=` | Ordered sequential choice |
| `==A | B | C==` | Ordered choice + use the selected value for output-folder routing |
| `[[A|B|C]]` | Legacy compatibility syntax; ordered choice only |

The normal form is intentionally lightweight and boundary-sensitive. Use it as a standalone prompt token:

```text
1girl, =front view | side view | back view=, white background
```

The explicit doubled folder form also accepts visual padding:

```text
== A | B | C ==
```

For the single-equals form, keep the delimiters tight:

```text
=A | B | C=     # supported
= A | B | C =   # deliberately left literal
```

This helps avoid consuming ordinary assignment-like prompt text such as:

```text
artist=foo|bar, weight=1
foo = bar|baz = qux
=A|B=tail
```

Malformed/unclosed equals blocks are left literal rather than being allowed to swallow a later valid block.

## Sequence modes

### Per image

The sequence advances once for every generated image, including individual image slots inside one batch.

`=A | B | C=` with Batch size = 1, Batch count = 3:

```text
A
B
C
```

With Batch size = 3, Batch count = 1:

```text
one batch → A, B, C
```

With Batch size = 3, Batch count = 2:

```text
batch 1 → A, B, C
batch 2 → A, B, C
```

With `Repeat each choice = 3`:

```text
A, A, A, B, B, B, C, C, C, ...
```

### Per batch

The sequence advances once per full Forge batch.

`=A | B | C=` with Batch size = 3, Batch count = 3:

```text
batch 1 → A, A, A
batch 2 → B, B, B
batch 3 → C, C, C
```

With `Repeat each choice = 2`, each value is held for two batches before advancing.

### Start index and end behavior

- `Start index = 0` starts from the first choice; `1` starts from the second, and so on.
- **Loop**: `A → B → C → A → ...`
- **Clamp**: `A → B → C → C → ...`

Different blocks may have different choice counts. They share the same global sequence index but Loop/Clamp is applied independently to each block.

## Multiple blocks

All blocks in one prompt are synchronized by the same image sequence index:

```text
=red | blue | green= hair, =dress | shirt | coat=
```

produces:

```text
red hair, dress
blue hair, shirt
green hair, coat
```

## Choice folders

Use doubled equals when a block should also control the save folder.

```text
==front | side | back==
```

can route the three results into:

```text
front/
side/
back/
```

### Folder block + normal block

```text
==A | B | C==, =D | E | F=
```

Per image produces:

```text
A, D → A/
B, E → B/
C, F → C/
```

Only doubled `==...==` blocks contribute to folder names.

### Multiple folder blocks

```text
==A | B | C==, ==D | E | F==
```

produces:

```text
A, D → A__D/
B, E → B__E/
C, F → C__F/
```

## Save safety

Folder routing happens in Forge Neo's synchronous `before_image_saved` callback.

The extension reads the active Forge `images.save_image()` call context at save time, including Forge's already-computed:

- `grid` flag;
- `add_number` decision;
- `basename`;
- `forced_filename` state.

This is important for correctness:

- live-preview grids do **not** set any persistent “next save is a grid” marker;
- actual saved grids are excluded using Forge's exact `grid=True` value;
- `forced_filename` saves are never incorrectly reinterpreted as numbered files;
- normal sample filenames containing the word `grid` are still routed when Forge explicitly says `grid=False`.

If that exact Forge call context cannot be found (for example after an upstream refactor), the extension falls back conservatively to output-root checks. Nested roots use the more-specific configured root; a shared/ambiguous sample+grid root fails closed and leaves the save at Forge's original location rather than risking a grid move.

### Per-folder numbering / overwrite protection

Forge chooses its initial numeric prefix before `before_image_saved` runs. Because the extension then changes the directory, Forge's original directory can remain empty and otherwise keep proposing the same number.

When Forge has actually enabled numbering, the extension recomputes the numeric prefix against the **destination choice folder**.

For example, if Forge proposes `00000-same.png` twice for category `A`, the routed names become:

```text
A/00000-same.png
A/00001-same.png
```

When Forge did not number a save, the extension preserves Forge's filename and leaves Forge's configured Override / Number Suffix collision behavior authoritative.

### Folder-name safety

Selected values are sanitized before becoming one directory component. The extension:

- replaces Windows-invalid characters and control characters;
- prevents `/`, `\`, `.`/`..`, and similar input from creating nested/parent paths;
- protects Windows device names such as `CON`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`, superscript COM/LPT forms, `CONIN$`, and `CONOUT$`;
- removes problematic trailing spaces/periods;
- limits both character count and UTF-8 byte length;
- deterministically adds a short hash when shortening is required;
- performs a resolved path-containment check before directory creation.

### Long Linux output paths

Current Forge Neo applies `f_namemax` after save callbacks to the whole post-callback path string on `statvfs` platforms. Adding another directory can expose that behavior when the existing output path is already long.

The extension therefore budgets its added folder against Forge's audited post-callback limit. It preserves the complete added directory **and a useful prefix of Forge's filename** (the whole stem when short, otherwise at least 32 characters), shortening only the extension-added folder when possible. If no safe folder budget remains, it leaves that image at Forge's original save location instead of turning an otherwise valid save into a broken or collision-prone path.

### Forge's own “Save Images to Subdirectory” option

If Forge already selected a subdirectory, the choice folder is created **inside that selected directory**.

## Grids, auxiliary saves, and lifecycle cleanup

- Final generated images are routed per image.
- Forge's saved grids are not routed.
- Hires.fix first-pass intermediate saves are not routed while Forge reports `is_hr_pass=True`.
- Auxiliary saves tied to the current generated image (pre-face-restoration, pre-color-correction, masks/composites) follow the same choice-folder mapping when Forge exposes the same `batch_index`.
- The save callback is idempotent for the same `ImageSaveParams`, protecting against duplicate callback invocation/hot reload.
- At the end of `Script.postprocess()`, private folder-routing state is cleared so later/manual/third-party saves cannot reuse a stale image index.
- Source/hot reload removes older save callbacks from this same extension file before registering the current callback.

## Hires.fix

Forge Neo maintains separate Hires prompt arrays. The extension resolves:

- `all_hr_prompts`;
- `all_hr_negative_prompts` when negative processing is enabled;

using the same global image index as the corresponding first-pass image.

A custom Hires prompt may contain sequential syntax. Folder names are intentionally derived only from doubled blocks in the **main positive prompt**, not from a negative or Hires-only block.

### img2img Batch behavior

Forge Neo processes each input file in img2img Batch as a separate `process_images()` run while reusing the processing object. Sequential Prompts intentionally resets its private run state at the start of each run, so the sequence currently **restarts from the configured Start index for each input file**.

This is deterministic and safe, but it is not a single A → B → C counter spanning the entire input directory. A future option could add directory-wide continuation if that workflow is needed.

## Negative prompts

Positive prompts are processed whenever Sequential Prompts is enabled.

Negative-prompt processing can be toggled from the extension panel. The toggle is recorded in generation metadata together with sequence mode, repeat count, start index, and end behavior.

## LoRA / Extra Networks

Actual sequence resolution happens in `before_process_batch()`, before Forge Neo parses Extra Networks. Choices may therefore contain LoRA tags:

```text
=<lora:character_a:1> | <lora:character_b:1>=
```

Folder markers can contain them too:

```text
==<lora:character_a:1> | <lora:character_b:1>==
```

Filesystem-invalid characters are sanitized only for the folder name; the resolved prompt still contains the selected LoRA tag for Forge to parse.

## Dynamic Prompts compatibility

This extension deliberately uses `=...=` / `==...==`, not Dynamic Prompts' `{...}` syntax.

Forge Neo runs all extensions' `process()` callbacks before batching. Sequential Prompts does **not** collapse templates in `process()`; it waits for `before_process_batch()`. This allows Dynamic Prompts-style extensions to update `all_prompts`, seeds, `n_iter`, and Hires arrays first.

As with other Forge/A1111 scripts, user-modified callback ordering or a third-party script that deliberately rewrites prompts after Sequential Prompts can still change the final result.

## Escaping

Inside a sequential block:

```text
\|  → literal |
\=  → literal =
\\  → literal \
```

For example:

```text
=A\|B | C\=D | E\\F=
```

represents three choices: `A|B`, `C=D`, and `E\F`.

## Install

From the Forge Neo directory:

```bash
git clone https://github.com/umimi893/sd-webui-sequential-prompts-forge-neo extensions/sd-webui-sequential-prompts-forge-neo
```

Restart Forge Neo after installation.

### Update

```bash
cd extensions/sd-webui-sequential-prompts-forge-neo
git pull
```

Restart Forge Neo after updating.

## Audit / development status

The v0.4.2 candidate has been traced against the current Forge Neo prompt and save lifecycle, including:

- prompt setup and batch slicing;
- full and partial batches;
- `process()` / `before_process_batch()` ordering;
- Dynamic Prompts-style list replacement;
- Extra Networks / LoRA parsing;
- Hires.fix prompt arrays and first-pass intermediate saves;
- `iteration` / `batch_index` indexing;
- Forge filename generation, `grid`, `add_number`, `basename`, and `forced_filename` handling;
- final and auxiliary saves;
- UI manual saves;
- callback reload/idempotency;
- Windows filename rules;
- Linux/`statvfs` path behavior;
- reused processing-state cleanup.

Current local automated coverage: **94 tests** on Python 3.13.

The GitHub Actions matrix runs the same compile/tests on:

- `ubuntu-latest` / Python 3.13;
- `windows-latest` / Python 3.13.

Run locally:

```bash
python -m compileall -q seqprompt scripts tests
python -m unittest discover -s tests -v
```

See [`AUDIT.md`](AUDIT.md) for the detailed audit and remaining release gates.

## Known limitations / release gate

- A real GPU-backed Forge Neo txt2img/img2img/Hires generation and Windows disk-save smoke test is still required before calling v0.4.2 fully release-validated.
- Save-context detection intentionally depends on the audited synchronous `modules/images.py:save_image()` → `before_image_saved` lifecycle. The implementation has conservative fallbacks, but a future Forge refactor should trigger re-audit.
- A third-party extension that adds/removes/reorders generated images late in `postprocess_batch_list` can desynchronize index-based choice-folder mapping. Forge requires such an extension to update prompt/seed arrays, but there is no stable per-image folder identity channel for this extension to follow through arbitrary reordering.
- Concurrent direct callers that bypass Forge's normal queued generation path can race a destination-folder numeric scan. Normal Gradio GPU jobs are serialized by Forge.
- Distinct raw values may sanitize/case-fold to the same folder and therefore share its numbering sequence.
- img2img Batch restarts the sequence for each input file rather than continuing one global counter across the directory.
- Video/Wan-specific batching is not explicitly release-tested; Wan can alter effective sampling batch behavior.
- Nested sequential blocks are intentionally unsupported.
- Sequential wildcard files are not implemented.
- The repository does not yet include an explicit license file.

## Version history

See [`CHANGELOG.md`](CHANGELOG.md).
