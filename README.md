# Sequential Prompts for Stable Diffusion WebUI Forge Neo

![tests](https://github.com/umimi893/sd-webui-sequential-prompts-forge-neo/actions/workflows/tests.yml/badge.svg)

Deterministic prompt sequencing for **Stable Diffusion WebUI Forge Neo**, with optional per-choice output-folder sorting.

Current candidate version: **v0.4.2**

Audited against Forge Neo `neo` commit `e782dc3fe07deb4653a8a1a1ad8ffa52783f54c5` (re-verified as the current upstream head on 2026-08-19).

## What it does

Use a normal sequential block when you only want ordered prompt choices:

```text
=A | B | C=
```

With **Per image** mode the sequence is deterministic:

```text
A → B → C → A → ...
```

Use a doubled block when the selected choice should also name the output folder:

```text
==front | side | back==
```

which can route generated images into:

```text
front/
side/
back/
```

## Syntax reference

| Syntax | Meaning |
|---|---|
| `=A | B | C=` | Ordered sequential choice |
| `==A | B | C==` | Ordered choice + route the saved image by the selected value |
| `[[A|B|C]]` | Legacy compatibility syntax; ordered choice only |

### Equals blocks are standalone tokens

The equals forms are intentionally strict enough to avoid common `key=value` false positives.

Use:

```text
=A | B | C=
```

Do not add padding spaces immediately inside the delimiters:

```text
= A | B | C =
```

The second form is intentionally left untouched. Spaces around the `|` separators are fine.

The opening and closing equals delimiters also must not be attached directly to a letter, digit, or underscore. This keeps ordinary text such as these from being consumed:

```text
artist=foo|bar, weight=1
foo = bar|baz = qux
=A|B=tail
```

## Basic batching examples

### Per image

```text
=A | B | C=
```

Batch size = 1, Batch count = 3:

```text
image 1 → A
image 2 → B
image 3 → C
```

Batch size = 3, Batch count = 1:

```text
one batch → A, B, C
```

Batch size = 3, Batch count = 2:

```text
batch 1 → A, B, C
batch 2 → A, B, C
```

With `Repeat each choice = 3`:

```text
A, A, A, B, B, B, C, C, C, ...
```

### Per batch

With Batch size = 3 and Batch count = 3:

```text
batch 1 → A, A, A
batch 2 → B, B, B
batch 3 → C, C, C
```

With `Repeat each choice = 2`, each value is held for two full batches.

### Start index

`Start index = 0` starts from the first choice. `1` starts from the second, and so on.

### End behavior

- **Loop**: `A → B → C → A → ...`
- **Clamp**: `A → B → C → C → ...`

Different blocks may contain different choice counts. They share one global sequence index, but each block applies Loop/Clamp to its own choices.

## Folder routing

### One folder marker + one normal marker

```text
==A | B | C==, =D | E | F=
```

Per image:

```text
A, D → A/
B, E → B/
C, F → C/
```

Only doubled `==...==` blocks contribute to folder names.

### Multiple folder markers

```text
==A | B | C==, ==D | E | F==
```

becomes:

```text
A, D → A__D/
B, E → B__E/
C, F → C__F/
```

### Save-number safety

Forge Neo decides its initial filename before calling extension save callbacks. Because this extension changes the destination directory afterwards, v0.4.2 recomputes Forge's ascending numeric prefix against the **actual choice folder** when Forge numbering is enabled.

That matters for repeated categories. If Forge proposes the same source name twice because the original directory remains empty, routing behaves like this:

```text
A/00000-same.png
A/00001-same.png
```

instead of sending both saves to `A/00000-same.png`.

When Forge's own ascending-number option is disabled, the extension leaves the filename decoration unchanged and Forge's configured collision behavior remains authoritative.

### Folder-name safety

Choice-folder names are sanitized before directory creation. The extension:

- replaces Windows-invalid filename characters and control characters;
- prevents `/`, `\`, `.`/`..`, and similar input from creating nested/parent paths;
- protects Windows device names including `CON`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`, and the documented superscript COM/LPT forms;
- removes problematic trailing spaces/periods;
- bounds names by both character count and UTF-8 byte length;
- deterministically adds a short hash when a name must be shortened;
- performs a path-containment check again before creating the destination directory.

If Forge Neo's own **Save Images to Subdirectory** option is enabled, the choice folder is created inside the directory Forge already selected.

## Grids and auxiliary saves

Final generated images are routed per image. Forge grids are intentionally **not** routed into a choice folder.

v0.4.2 listens to Forge Neo's `image_grid` callback and marks the immediately following grid save, so this remains correct even when:

- sample and grid output directories are the same;
- extended/custom grid filenames are enabled;
- the grid filename itself does not make grid detection obvious.

A narrow `grid...` filename check is retained only as a fallback.

Auxiliary saves associated with an image, such as pre-face-restoration, pre-color-correction, mask, or mask-composite files, follow that image's choice folder when Forge exposes the same `batch_index`.

## Hires.fix

- Positive Hires.fix prompt arrays use the same global sequence index as the first pass.
- Negative Hires.fix prompt arrays do the same when negative processing is enabled.
- A custom Hires.fix prompt may contain sequential syntax.
- Folder names are derived only from doubled blocks in the **main positive prompt**.
- Forge's optional saved first-pass Hires intermediate is intentionally left in Forge's normal output location while `is_hr_pass` is true.
- The final Hires result is routed normally after Forge returns to the final-image save stage.

## Negative prompts

Positive prompts are processed whenever the extension is enabled. Negative-prompt processing can be toggled in the extension panel.

The toggle is recorded in generation metadata together with the sequence mode, repeat count, start index, and end behavior.

## LoRA / Extra Networks

Sequential resolution runs in `before_process_batch()`, before Forge Neo parses Extra Networks, so choices can contain LoRA tags:

```text
=<lora:character_a:1> | <lora:character_b:1>=
```

Folder markers can contain them too:

```text
==<lora:character_a:1> | <lora:character_b:1>==
```

Invalid filesystem characters in the selected text are sanitized before it becomes a directory name.

## Dynamic Prompts compatibility

This extension deliberately uses `=...=` / `==...==`, not Dynamic Prompts' `{...}` syntax.

Forge Neo calls all extensions' `process()` methods before it starts batching. Sequential Prompts does not collapse templates there; it waits until `before_process_batch()`. This lets Dynamic Prompts-style expansion replace `all_prompts`, `n_iter`, seeds, and Hires arrays first, then Sequential Prompts resolves the actual current batch.

As with any A1111/Forge extension, callback priority can be changed by the user. A third-party extension intentionally rewriting prompts after this extension's batch callback can still change the final result.

## Escaping

Inside a sequential block:

```text
\|  → literal |
\=  → literal =
\\  → literal \
```

Example:

```text
=A\|B | C\=D | E\\F=
```

represents:

```text
A|B
C=D
E\F
```

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

## Compatibility and audit status

Target: [`Haoming02/sd-webui-forge-classic`](https://github.com/Haoming02/sd-webui-forge-classic), branch `neo`.

The current audit traces:

- prompt setup and batch slicing;
- `process()` / `before_process_batch()` order;
- Dynamic Prompts-style prompt-list replacement;
- Extra Networks parsing and LoRA activation;
- Hires.fix prompt arrays and intermediate saves;
- `iteration` / `batch_index` global indexing;
- Forge filename generation and per-folder numbering;
- final and auxiliary image saves;
- grid creation/save callbacks;
- UI manual saves;
- Windows filename rules and Linux/ext4 byte-length constraints;
- reused processing-state cleanup.

Automated coverage for the v0.4.2 candidate currently contains **68 tests**. The GitHub Actions workflow runs Python 3.13 compile/tests on both Ubuntu and Windows.

Run locally:

```bash
python -m compileall -q seqprompt scripts tests
python -m unittest discover -s tests -v
```

See [`AUDIT.md`](AUDIT.md) for the detailed findings and residual risks.

## Known limitations

- A real GPU-backed Forge Neo UI/image-generation smoke test is still required before calling the extension fully release-validated.
- Video/Wan-specific batching is not explicitly release-tested.
- Nested sequential blocks are intentionally unsupported.
- Sequential wildcard files are not implemented.
- The legacy `[[...]]` syntax remains for compatibility but never routes folders.
- The lightweight equals syntax is intentionally boundary-sensitive; use the documented standalone form.
- Distinct raw choices can sanitize to the same folder name. Case-only differences also share a folder on normal Windows filesystems; such categories will be combined even though the per-folder numeric guard prevents the routing counter from resetting onto an existing numbered file.
- Another extension can still change prompts after Sequential Prompts if the user explicitly changes callback priority/order.
- The repository does not yet include an explicit license file.

## Version history

See [`CHANGELOG.md`](CHANGELOG.md).
