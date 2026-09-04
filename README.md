# Sequential Prompts for Forge Neo

![CI](https://github.com/umimi893/sd-webui-sequential-prompts-forge-neo/actions/workflows/ci.yml/badge.svg)

An always-on extension for **Stable Diffusion WebUI Forge Neo** that resolves inline prompt choices in a deterministic order instead of randomly.

Current release: **v0.6.0**.

## Syntax

Use double equals for normal sequential choices:

```text
==front | side | back==
```

Use triple equals when the selected choice should also determine the output folder:

```text
===front | side | back===
```

The old `$...$`, `$$...$$`, `=...=`, `[[...]]`, `&...&`, and `&&...&&` forms are **not syntax** and remain literal prompt text.

### Example

```text
1girl, ===front | side | back===, ==day | sunset | night==
```

With **Advance every image** and Batch size 3:

```text
image 1: 1girl, front, day     -> front/
image 2: 1girl, side, sunset   -> side/
image 3: 1girl, back, night    -> back/
```

Multiple folder markers combine with `__`:

```text
===A|B|C===, ===D|E|F===
```

produces folders such as:

```text
A__D/
B__E/
C__F/
```

## Why v0.6.0 changed the delimiters

v0.5.x used `$...$` / `$$...$$`. That was a poor coexistence choice for Dynamic Prompts because Dynamic Prompts itself uses dollar-prefixed grammar such as `${variable}` and `$$` inside multi-selection syntax.

v0.6.0 therefore moves Sequential Prompts to `==...==` / `===...===`. Dynamic Prompts' default grammar is kept separate:

```text
{red|blue}                 # Dynamic Prompts variant
__hair_color__             # Dynamic Prompts wildcard
${season=!{summer|winter}} # Dynamic Prompts variable
%{wrapper$$inner}          # Dynamic Prompts wrap command
==front|back==             # Sequential Prompts
===front|back===           # Sequential Prompts + folder routing
```

The CI suite installs the real `dynamicprompts` package and verifies that its default variant, multi-select-dollar, variable, and Sequential/Folder syntax coexist in the same prompt.

If a user manually changes Dynamic Prompts' configurable variant or wildcard delimiters so they overlap `==` or `===`, generation is stopped with a clear conflict instead of depending on callback order.

## Sequence modes

### One choice per batch (default / recommended)

Every image in a Forge batch uses the same choice, then the next batch advances to the next choice.

```text
==A|B|C==
```

```text
batch 1: A, A, A
batch 2: B, B, B
batch 3: C, C, C
```

If **Hold each choice for N images / batches = 3**, each choice is held for three batches before advancing.

### Advance every image

Use this if you explicitly want mixed choices inside the same batch.

```text
==A|B|C==
```

Batch size 1, Batch count 3:

```text
A -> B -> C
```

Batch size 3, Batch count 1:

```text
A, B, C
```

### Repeat, start, and end behavior

- **Hold each choice for N images / batches** — holds a choice for N sequence units.
- **Start index** — starts from a later choice.
- **Loop** — wraps after the final choice.
- **Clamp** — stays on the final choice.
- **Also process negative prompt** — resolves Sequential syntax in the negative prompt too.

## Escapes and prompt-language coexistence

Inside a Sequential block:

```text
\|   literal pipe
\=   literal equals
\\   literal backslash
```

Unrelated backslashes are preserved, including Windows-style paths.

The parser deliberately avoids stealing syntax owned by Forge or Dynamic Prompts:

- Forge Extra Network tags such as `<lora:name:1>` are treated atomically.
- Forge bracket syntax such as `[red|blue]` does not become a Sequential separator.
- Forge grouping/emphasis can contain a Sequential block, e.g. `(==A|B==)`.
- Dynamic Prompts brace blocks such as `{red|blue}`, `${...}`, and other balanced `{...}` constructs remain opaque until Dynamic Prompts expands them.
- Plain `$` / `$$` are never interpreted by Sequential Prompts.

Nested Sequential blocks are intentionally unsupported and fail closed as literal text rather than being partially transformed.

Empty choices are supported:

```text
==with hat||without hat==
```

A folder marker may contain a single value:

```text
===portrait===
```

## Dynamic Prompts

Dynamic Prompts and Sequential Prompts are intended to be enabled at the same time.

A normal combined prompt looks like this:

```text
1girl, {red|blue} hair, __background__, ==front view|side view|back view==
```

Dynamic Prompts expands its own syntax during `process()`. Sequential Prompts activates from the final prompt arrays after all `process()` callbacks, then resolves `==...==` / `===...===` in `before_process_batch()`.

This also allows a Dynamic Prompts wildcard or other expansion to introduce Sequential syntax into the final prompt, provided the resulting text contains a valid top-level Sequential block.

### Important limitation: Prompt Matrix

Forge's selectable **Prompt Matrix** script consumes the raw prompt's `|` separators before the normal processing lifecycle. That conflict is structural and is unrelated to the choice of `==` delimiters, so Prompt Matrix remains intentionally rejected when raw Sequential syntax is present.

## LoRA / Extra Networks

Choices may contain Forge Extra Network tags:

```text
==<lora:a:1> | <lora:b:1>==
```

Forge Neo applies Extra Network configuration per batch, not independently per image. Therefore the extension rejects a Sequential configuration that would create different active LoRA/Extra Network settings inside the same batch.

Safe examples include:

- Batch size 1.
- One choice per batch mode where every image in the current batch resolves to the same Extra Network setup.

Existing heterogeneous Extra Network prompts unrelated to Sequential Prompts are not newly policed by this extension.

## Hires.fix

When Hires.fix is enabled, the corresponding Hires prompt arrays use the same frozen image identity and sequence position as the normal prompt.

Folder routing is controlled only by the **main positive prompt**. `===...===` in negative or Hires-only prompt text does not create a folder.

If **Save images before highres fix** is enabled, those intermediate first-pass images stay in Forge's normal output location. Only final core samples and their directly-associated auxiliary saves are routed.

## Output folders

`===...===` folders are sanitized for portable filesystem use:

- Windows-invalid filename characters are replaced.
- Windows reserved device names are handled.
- Unicode is normalized.
- dangerous control/bidi characters are removed or replaced.
- long UTF-8 names are deterministically shortened.
- lossy sanitization receives a short deterministic hash so different raw choices do not silently collapse into the same directory across runs.
- path containment is checked before and after directory creation.

Forge's existing **save-to-dirs** behavior is preserved: the Sequential choice folder is nested under the subdirectory Forge already selected.

### Save numbering

Forge computes its numeric filename before `before_image_saved`. The extension recomputes the numeric prefix inside the actual destination folder while preserving Forge's final Override / Number Suffix collision policy.

## Post-processing identity

Forge allows `postprocess_batch_list` extensions to reorder, remove, or add images if they also update prompt/seed metadata. Folder routing follows that live metadata identity instead of trusting the original slot number.

If identity is genuinely ambiguous, routing is skipped rather than guessed.

## Forge scripts and special modes

Sequence state begins again for each independent `process_images()` invocation. This matters for scripts such as X/Y/Z Plot, Prompts from File, Loopback, and img2img Batch, which create sub-runs or reuse the processing object.

Two Forge selectable scripts are intentionally treated specially when Sequential syntax is relevant:

- **Prompt Matrix**: rejects raw Sequential syntax because it consumes `|` before the normal lifecycle.
- **SD Upscale**: rejects Sequential syntax because it recursively generates tiles and saves the final composite outside the normal core sample-save identity.

Multi-frame **Wan/video** jobs are also rejected when Sequential syntax is active because Forge's batch axis represents video frames rather than independent image identities. Single-frame Wan remains allowed.

## Installation

From the Forge Neo root directory:

```bash
git clone https://github.com/umimi893/sd-webui-sequential-prompts-forge-neo.git extensions/sd-webui-sequential-prompts-forge-neo
```

Then restart Forge Neo and expand the **Sequential Prompts** accordion in txt2img or img2img. The extension is enabled by default; prompts without `==...==` or `===...===` remain a behavioral no-op.

To update an existing clone:

```bash
cd extensions/sd-webui-sequential-prompts-forge-neo
git pull
```

Restart Forge Neo after updating.

## Compatibility and testing

GitHub Actions runs on **Ubuntu and Windows with Python 3.13**.

The suite covers sequencing, batching, Hires.fix, LoRA/Extra Networks, real Dynamic Prompts parser/generator coexistence, save routing, numbering, Unicode/path handling, and special-mode guards.
