# Sequential Prompts for Stable Diffusion WebUI Forge Neo

Deterministic sequential prompt alternatives for Stable Diffusion WebUI Forge Neo, with optional automatic output-folder sorting.

Forge Neo target: [`Haoming02/sd-webui-forge-classic`](https://github.com/Haoming02/sd-webui-forge-classic), branch `neo`.

## Syntax

### Ordered choice

```text
=A | B | C=
```

The selected value advances in deterministic order.

Example:

```text
1girl, =front view | side view | back view=, white background
```

### Ordered choice + output folder

Use doubled equals when that block should also control the output folder:

```text
==A | B | C==
```

Example:

```text
1girl, ==front view | side view | back view==, white background
```

With Per image mode and Batch size = 3, the three generated images are routed to:

```text
front view/
side view/
back view/
```

A normal block can be used alongside a folder block:

```text
==A | B | C==, =D | E | F=
```

This generates:

```text
A, D   -> A/
B, E   -> B/
C, F   -> C/
```

If multiple doubled blocks are present, only those doubled blocks contribute to the folder name:

```text
==A | B | C==, ==D | E | F==
```

routes to:

```text
A__D/
B__E/
C__F/
```

Folder names are sanitized for Windows-invalid characters, reserved device names, path traversal, and excessive length.

### Legacy compatibility

The old syntax remains accepted but does not control folders:

```text
[[A|B|C]]
```

## Sequence modes

### Per image

With Batch size = 1 and Batch count = 3:

```text
=A | B | C=
```

resolves to:

```text
A
B
C
```

With Batch size = 3 and Batch count = 1, it resolves inside that one batch as:

```text
A
B
C
```

With `Repeat each choice = 3`:

```text
A A A B B B C C C
```

### Per batch

With Batch size = 3 and Batch count = 3:

```text
=A | B | C=
```

resolves to:

```text
A A A
B B B
C C C
```

## Multiple blocks

All sequential blocks share the same global sequence index:

```text
=red | blue | green= hair, =dress | shirt | coat=
```

becomes:

```text
red hair, dress
blue hair, shirt
green hair, coat
```

Blocks may have different choice counts; Loop and Clamp apply independently to each block.

## LoRA / Extra Networks

Resolution occurs before Forge Neo parses Extra Networks, so choices can contain LoRA tags:

```text
=<lora:a:1> | <lora:b:1> | <lora:c:1>=
```

Folder markers can also contain them; the selected text is sanitized before becoming a directory name.

## Escaping

Inside a sequential block:

- `\|` -> literal `|`
- `\=` -> literal `=`
- `\\` -> literal `\`

Example:

```text
=A\|B | C\=D | E\\F=
```

## Hires.fix and negative prompts

- Positive prompts are always processed.
- Negative prompt processing can be toggled in the extension panel.
- Hires.fix positive and negative prompt arrays use the same global sequence index as the first pass.
- Folder routing is derived from doubled blocks in the main positive prompt.
- Forge Neo's optional saved Hires.fix first-pass intermediate is intentionally not moved into a choice folder because it is saved before Forge exposes a reliable final-image batch index.
- Grids are intentionally left in the normal Forge Neo grid output location.

## Install

From the Forge Neo directory:

```bash
git clone https://github.com/umimi893/sd-webui-sequential-prompts-forge-neo extensions/sd-webui-sequential-prompts-forge-neo
```

Restart Forge Neo afterwards.

## Compatibility

- Designed for **Stable Diffusion WebUI Forge Neo**.
- Uses Forge Neo's `process()` and `before_process_batch()` lifecycle.
- Uses Forge Neo's `before_image_saved` callback for per-image output routing.
- Compatible by design with Dynamic Prompts: `{...}` expansion can finish first, then this extension resolves `=...=` / `==...==` blocks at batch time.
- No third-party Python packages are required.

## Development

```bash
python -m compileall -q seqprompt scripts tests
python -m unittest discover -s tests -v
```

## Current limitations

- Nested sequential blocks are intentionally unsupported.
- Sequential wildcard files are not implemented yet.
- Full GPU-backed UI + image-generation smoke testing still requires an actual Forge Neo installation.
