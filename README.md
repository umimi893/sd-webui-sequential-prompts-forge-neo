# Sequential Prompts for Stable Diffusion WebUI Forge Neo

![tests](https://github.com/umimi893/sd-webui-sequential-prompts-forge-neo/actions/workflows/tests.yml/badge.svg)

Deterministic prompt sequencing for **Stable Diffusion WebUI Forge Neo**, with optional per-choice output-folder sorting.

Current development version: **v0.4.1**

Audited against Forge Neo `neo` commit `e782dc3fe07deb4653a8a1a1ad8ffa52783f54c5` (current upstream head when this README was updated).

## What it does

Instead of choosing prompt alternatives randomly, this extension walks through them in a predictable order.

```text
=A | B | C=
```

With **Per image** mode:

```text
A → B → C → A → ...
```

With Batch size = 3, one batch can therefore generate A, B, and C in one pass.

It can also sort saved images into folders based on the selected choice:

```text
==front | side | back==
```

which can produce:

```text
front/
side/
back/
```

## Syntax reference

| Syntax | Meaning |
|---|---|
| `=A | B | C=` | Ordered sequential choice |
| `==A | B | C==` | Ordered choice + use the selected value for output-folder routing |
| `[[A|B|C]]` | Legacy compatibility syntax; ordered choice only |

The `=...=` and `==...==` forms are intended to be standalone prompt tokens, for example after a comma or whitespace. This avoids accidentally interpreting ordinary text such as `artist=foo|bar, weight=1` as a sequence.

### Basic example

```text
1girl, =front view | side view | back view=, white background
```

Batch size = 3, Batch count = 1, **Per image**:

```text
image 1 → front view
image 2 → side view
image 3 → back view
```

### Folder-routing example

```text
1girl, ==front view | side view | back view==, white background
```

The same three images are saved under:

```text
front view/
side view/
back view/
```

### Folder marker + normal marker

```text
==A | B | C==, =D | E | F=
```

Per image:

```text
A, D → A/
B, E → B/
C, F → C/
```

Only the doubled `==...==` block contributes to the folder name.

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

All doubled blocks use the same global sequence index and their selected values are joined with `__`.

## Sequence controls

### Per image

The sequence advances once per generated image, including images inside the same batch.

`=A|B|C=` with Batch size = 3:

```text
batch 1 → A, B, C
batch 2 → A, B, C
```

With `Repeat each choice = 3`:

```text
A, A, A, B, B, B, C, C, C, ...
```

### Per batch

The sequence advances once per batch.

`=A|B|C=` with Batch size = 3 and Batch count = 3:

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

Different blocks may contain different numbers of choices; each block applies Loop/Clamp independently while sharing the same global sequence index.

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

represents the three choices:

```text
A|B
C=D
E\F
```

## LoRA / Extra Networks

Sequential resolution runs before Forge Neo parses Extra Networks, so LoRA tags can be choices:

```text
=<lora:character_a:1> | <lora:character_b:1>=
```

Folder markers may also contain Extra Network syntax:

```text
==<lora:character_a:1> | <lora:character_b:1>==
```

When used as a folder name, invalid filesystem characters are sanitized automatically.

## Output-folder behavior

Folder routing is based only on doubled blocks in the **main positive prompt**.

The extension:

- routes each final image using its global image index;
- supports Batch size greater than 1;
- creates the destination folder before Forge saves the image;
- sanitizes Windows-invalid characters and control characters;
- blocks path traversal such as `..`, `/`, and `\` from creating parent/nested paths;
- protects Windows reserved names such as `CON`, `NUL`, `COM1`, and `LPT1`;
- shortens excessively long folder names deterministically;
- leaves grids in Forge Neo's normal grid location;
- leaves Hires.fix first-pass intermediate saves in Forge Neo's normal location.

If Forge Neo's own **save images to subdirectory** option is enabled, the choice folder is created inside the directory Forge already selected.

Auxiliary saves for an image, such as masks or pre-color-correction copies, follow the same choice folder when Forge exposes the same image index.

## Negative prompts and Hires.fix

- Positive prompts are always processed when the extension is enabled.
- Negative prompt processing can be enabled/disabled in the extension panel.
- Hires.fix positive and negative prompt arrays use the same sequence index as the corresponding image.
- A custom Hires.fix prompt can contain sequential syntax as well.
- Folder names are intentionally derived from the main positive prompt, not from negative or Hires-only prompt blocks.

## Dynamic Prompts compatibility

This extension deliberately uses `=...=` / `==...==`, not Dynamic Prompts' `{...}` syntax.

Actual sequential resolution happens in Forge Neo's `before_process_batch()` stage, after other extensions have had their `process()` callbacks. This allows Dynamic Prompts-style expansion to happen first and then lets Sequential Prompts resolve the final batch templates.

As with any A1111/Forge extension, users can manually alter callback priority; an extension that intentionally rewrites prompts after this extension can still change the final result.

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

The extension has been checked against Forge Neo's current prompt lifecycle, including:

- prompt setup and batch slicing;
- `process()` / `before_process_batch()` ordering;
- Extra Networks parsing;
- Hires.fix prompt arrays;
- per-image `batch_index` / `iteration` handling;
- `before_image_saved` save-path callback behavior.

Automated coverage currently includes **54 tests** for sequencing, folder markers, escaping, false-positive `key=value` protection, Hires.fix arrays, Dynamic Prompts-style pre-expansion, LoRA choices, negative prompts, output routing, path safety, grids, and the Forge-style script callback contract.

Run locally:

```bash
python -m compileall -q seqprompt scripts tests
python -m unittest discover -s tests -v
```

See [`AUDIT.md`](AUDIT.md) for the compatibility review and residual risks.

## Known limitations

- A full GPU-backed Forge Neo UI/image-generation smoke test is still recommended before treating the extension as fully release-validated.
- Nested sequential blocks are intentionally unsupported.
- Sequential wildcard files are not implemented.
- The legacy `[[...]]` syntax is supported for compatibility but does not route folders.
- Sanitization can cause two unusual raw choice strings to map to the same folder name; avoid relying on filesystem-invalid characters to distinguish categories.
- The repository does not yet include an explicit license file.

## Version history

See [`CHANGELOG.md`](CHANGELOG.md).
