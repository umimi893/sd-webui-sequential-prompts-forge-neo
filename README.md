# Sequential Prompts for Forge Neo

An always-on extension for **Stable Diffusion WebUI Forge Neo** that resolves inline prompt choices in a deterministic order instead of randomly.

Current development version: **v0.5.0**.

## Syntax

Use a single dollar pair for normal sequential choices:

```text
$front | side | back$
```

Use a double dollar pair when the selected choice should also determine the output folder:

```text
$$front | side | back$$
```

The old `=...=`, `==...==`, `[[...]]`, `&...&`, and `&&...&&` forms are **not syntax** in v0.5.0 and remain literal prompt text.

### Example

```text
1girl, $$front | side | back$$, $day | sunset | night$
```

With **Per image** and Batch size 3:

```text
image 1: 1girl, front, day     -> front/
image 2: 1girl, side, sunset   -> side/
image 3: 1girl, back, night    -> back/
```

Multiple folder markers combine with `__`:

```text
$$A|B|C$$, $$D|E|F$$
```

produces folders such as:

```text
A__D/
B__E/
C__F/
```

## Sequence modes

### Per image

The sequence advances once for every image Forge is about to generate.

```text
$A|B|C$
```

Batch size 1, Batch count 3:

```text
A -> B -> C
```

Batch size 3, Batch count 1:

```text
A, B, C
```

Batch size 2:

```text
batch 1: A, B
batch 2: C, A
```

### Per batch

Every image in a Forge batch uses the same choice:

```text
batch 1: A, A, A
batch 2: B, B, B
batch 3: C, C, C
```

### Repeat, start, and end behavior

The UI also provides:

- **Repeat each choice** — e.g. Per image + repeat 3 gives `AAA BBB CCC`.
- **Start index** — start from a later choice.
- **Loop** — wrap after the final choice.
- **Clamp** — stay on the final choice after reaching it.
- **Also process negative prompt** — use the same sequence identity for negative prompts.

## Escapes and prompt-language coexistence

Inside a Sequential block:

```text
\|   literal pipe
\$   literal dollar
\\   literal backslash
```

Unrelated backslashes are preserved, including Windows-style paths.

The parser deliberately avoids stealing syntax owned by Forge or Dynamic Prompts:

- Forge Extra Network tags such as `<lora:name:1>` are treated atomically.
- Forge bracket syntax such as `[red|blue]` does not become a Sequential separator.
- Forge grouping/emphasis can still contain a Sequential block, e.g. `($A|B$)`.
- Dynamic Prompts' default `{...}` grammar is left opaque until Dynamic Prompts expands it.

Nested Sequential blocks are intentionally unsupported and fail closed as literal text rather than being partially transformed.

Empty choices are supported:

```text
$with hat||without hat$
```

## LoRA / Extra Networks

Choices may contain Forge Extra Network tags:

```text
$<lora:a:1> | <lora:b:1>$
```

However, current Forge Neo applies Extra Network configuration **per batch**, not independently per image. Therefore this extension rejects a Sequential configuration that would create different active LoRA/Extra Network settings inside the same batch.

Safe examples include:

- Batch size 1.
- Per batch mode where every image in the current batch resolves to the same Extra Network setup.

Existing heterogeneous Extra Network prompts that are unrelated to Sequential Prompts are not newly policed by this extension.

## Hires.fix

When Hires.fix is enabled, the corresponding Hires prompt arrays use the same frozen image identity and sequence position as the normal prompt.

Folder routing is controlled only by the **main positive prompt**. `$$...$$` in negative or Hires-only prompt text does not create a folder.

If **Save images before highres fix** is enabled, those intermediate first-pass images stay in Forge's normal output location. Only final core samples and their directly-associated auxiliary saves are routed.

## Dynamic Prompts

The extension resolves batches after all `process()` callbacks, so Dynamic Prompts can expand prompts first.

The default Dynamic Prompts delimiters coexist with `$...$`.

If Dynamic Prompts is explicitly configured to use `$` or `$$` as one of its own delimiters while a relevant raw Sequential template is present, generation is stopped with a clear conflict instead of letting callback order decide the result.

## Output folders

`$$...$$` folders are sanitized for portable filesystem use:

- Windows-invalid filename characters are replaced.
- Windows reserved device names are handled.
- Unicode is normalized.
- dangerous control/bidi characters are removed or replaced.
- long UTF-8 names are deterministically shortened.
- lossy sanitization receives a short deterministic hash so different raw choices do not silently collapse into the same directory across runs.
- path containment is checked before and after directory creation.

Forge's existing **save-to-dirs** behavior is preserved: the Sequential choice folder is nested under the subdirectory Forge already selected.

### Save numbering

Forge computes its numeric filename before `before_image_saved`. Moving that file into a new choice folder without recalculating the sequence can cause repeated `00000` names and possible overwrites.

v0.5.0 recomputes the numeric prefix inside the actual destination folder while preserving Forge's own final **Override / Number Suffix** collision policy.

## Post-processing identity

Forge allows `postprocess_batch_list` extensions to reorder, remove, or add images if they also update prompt/seed metadata. Folder routing follows that live metadata identity instead of trusting the original slot number.

If the identity is genuinely ambiguous — for example two original images have identical prompt/negative/seed/subseed metadata but different folder outcomes — routing is skipped rather than guessing.

An extension that secretly swaps only pixel data while leaving all Forge metadata unchanged cannot be detected by a save callback; this remains a documented limitation.

## Forge scripts and special modes

Sequence state begins again for each independent `process_images()` invocation. This matters for scripts such as X/Y/Z Plot, Prompts from File, Loopback, and img2img Batch, which create sub-runs or reuse the processing object.

Two Forge selectable scripts are intentionally treated specially when Sequential syntax is relevant:

- **Prompt Matrix**: its raw parser splits the selected prompt on `|` before the normal Forge processing lifecycle, which conflicts structurally with `$A|B$`.
- **SD Upscale**: it recursively generates tiles and saves the final composite outside the normal core sample-save identity.

These combinations fail closed instead of producing misleading sequences/folders.

Multi-frame **Wan/video** jobs are also rejected when Sequential syntax is active because Forge's batch axis represents video frames rather than independent image identities. Single-frame Wan remains allowed.

## Installation

Clone this repository into Forge Neo's extensions directory:

```bash
git clone https://github.com/umimi893/sd-webui-sequential-prompts-forge-neo.git
```

Then restart Forge Neo and expand the **Sequential Prompts** accordion in txt2img or img2img.

To update an existing clone:

```bash
git pull
```

## Validation status

The v0.5.0 development branch has been rebuilt from audited components covering:

- `$` / `$$` parser behavior and malformed input.
- Forge batch/index lifecycle and partial API prompt-list batches.
- LoRA / Extra Networks and Hires.fix.
- Dynamic Prompts ordering and delimiter conflicts.
- save routing, numbering, grids, auxiliary images, postprocess reorder, path safety, and Unicode.
- abort/reuse state and Wan/video policy.

The development audit exercised **304 detailed local unit/contract checks**, preserved in the Git-invisible audit snapshot. The committed release CI suite is intentionally smaller and contains **68 focused contract tests** covering the release-critical behavior without duplicating every audit edge case.

The remaining release gate is a real Forge Neo GPU/UI/disk smoke test on Windows. Unit tests deliberately do not claim to replace that runtime check.

See [`AUDIT.md`](AUDIT.md) for the detailed compatibility and risk record.
