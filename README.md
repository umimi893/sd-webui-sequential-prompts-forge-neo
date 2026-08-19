# Sequential Prompts for Stable Diffusion WebUI Forge Neo

A small Forge Neo extension that resolves inline prompt alternatives **in deterministic order** instead of randomly.

Forge Neo target: [`Haoming02/sd-webui-forge-classic`](https://github.com/Haoming02/sd-webui-forge-classic), branch `neo`.

## Syntax

```text
1girl, [[front view|side view|back view]], white background
```

The extension uses `[[...]]` rather than Dynamic Prompts' `{...}` syntax, so both extensions can be installed without fighting over the same block.

## Modes

### Per image

With Batch size = 1 and Batch count = 3:

```text
[[A|B|C]]
```

resolves to:

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
[[A|B|C]]
```

resolves to:

```text
A A A
B B B
C C C
```

This maps directly to Forge Neo's `batch_size` / `n_iter` processing model.

## Multiple sequential blocks

All blocks use the same sequence index:

```text
[[red|blue|green]] hair, [[dress|shirt|coat]]
```

becomes:

```text
red hair, dress
blue hair, shirt
green hair, coat
```

## Escaping

Use `\|` for a literal pipe:

```text
[[A\|B|C]]
```

means the two choices `A|B` and `C`.

## End behavior

- **Loop**: `A → B → C → A → ...`
- **Clamp**: `A → B → C → C → ...`

## Positive / negative prompts

Positive prompts are always processed while negative-prompt processing can be toggled from the extension panel.

## Install on Forge Neo

Install it from your Forge Neo directory with:

```bash
git clone https://github.com/umimi893/sd-webui-sequential-prompts-forge-neo extensions/sd-webui-sequential-prompts-forge-neo
```

Then restart Forge Neo.

You can also place this project folder manually under:

```text
sd-webui-forge-neo/extensions/sd-webui-sequential-prompts-forge-neo/
```

## Compatibility

- Designed for **Stable Diffusion WebUI Forge Neo**.
- Tested with Python 3.13 at the pure-Python core level.
- Uses Forge Neo/A1111-compatible `scripts.Script` and `process()` APIs.
- No third-party Python packages are required.

## Development

Run tests:

```bash
python -m unittest discover -s tests -v
```

## Current limitations

- Nested `[[...]]` blocks are intentionally unsupported.
- Sequential wildcard files are not implemented yet.
- Full UI + image-generation integration tests require an actual Forge Neo installation.
