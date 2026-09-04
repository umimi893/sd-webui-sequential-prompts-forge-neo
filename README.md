# Sequential Prompts for Forge Neo

![CI](https://github.com/umimi893/sd-webui-sequential-prompts-forge-neo/actions/workflows/ci.yml/badge.svg)

Deterministic prompt sequencing for **Stable Diffusion WebUI Forge Neo**, with optional per-choice output folders and first-class coexistence with **Dynamic Prompts**.

Current release: **v0.6.1**

Audited against:

- **Forge Neo** `Haoming02/sd-webui-forge-classic` branch `neo`, commit `d2c29a6bc6cf834c83cdefed394062c2c3e58760`
- **sd-dynamic-prompts** extension commit `de056ff8d80e4ad120e13a90cf200f3383f427c6`
- **dynamicprompts** parser/generator package `0.31.0`

The audit details, lifecycle assumptions, fixes, and remaining validation boundary are documented in [`AUDIT.md`](AUDIT.md).

## What this extension does

Dynamic Prompts is excellent when you want a random or combinatorial choice. Sequential Prompts is for the opposite case: **walk through choices in a predictable order**.

```text
==front view | side view | back view==
```

can produce:

```text
front view -> side view -> back view -> front view -> ...
```

Use triple equals when the selected value should also become an output-folder identity:

```text
===front view | side view | back view===
```

which can route final images to:

```text
front view/
side view/
back view/
```

## Quick start

### Normal sequencing

```text
1girl, ==front view | side view | back view==, white background
```

### Sequencing + output folders

```text
1girl, ===front view | side view | back view===, white background
```

### Dynamic Prompts + Sequential Prompts together

```text
1girl, {red|blue} hair, __background__, ==front view|side view|back view==
```

Dynamic Prompts expands `{...}` and `__...__`; Sequential Prompts then advances `==...==` deterministically.

## Syntax reference

| Syntax | Meaning |
|---|---|
| `==A | B | C==` | Ordered Sequential choice |
| `===A | B | C===` | Ordered choice + selected value contributes to output folder |
| `===A===` | Single fixed folder marker |
| `\|` | Literal `|` inside a Sequential block |
| `\=` | Literal `=` inside a Sequential block |
| `\\` | Literal backslash inside a Sequential block |

Old forms are intentionally **not parsed**:

```text
$A|B$
$$A|B$$
=A|B=
[[A|B]]
&A|B&
&&A|B&&
```

They remain literal prompt text. This is deliberate: compatibility aliases would reintroduce collisions and false positives that v0.6.x is designed to remove.

## Why `==` / `===`

v0.5.x used `$...$` and `$$...$$`. That collided conceptually and practically with Dynamic Prompts, which uses dollar syntax in its own grammar:

```text
${season=!{summer|winter}}
{2$$red|green|blue}
%{wrapper ...$$inner}
```

v0.6.x therefore reserves only:

```text
==...==
===...===
```

Dynamic Prompts keeps its default grammar:

```text
{A|B}          variants
__name__       wildcards
${name=...}    variables
%{...$$...}    wrap command
```

Forge keeps its own grammar, including:

```text
(prompt:1.2)
[before:after:0.5]
[red|blue]
<lora:name:1>
```

The Sequential parser treats Dynamic Prompts brace blocks, Forge Extra Network tags, and Forge bracket/group constructs as protected structures rather than stealing their internal `|` characters.

## Sequence grouping

### One choice per batch — default and recommended

With Batch size 3:

```text
==A|B|C==
```

produces:

```text
batch 1 -> A A A
batch 2 -> B B B
batch 3 -> C C C
```

This mode is especially important when choices alter LoRA / Extra Network configuration because Forge activates those networks per batch.

### Advance every image

With Batch size 3:

```text
==A|B|C==
```

produces:

```text
batch 1 -> A B C
batch 2 -> A B C
```

Use this only when you actually want different choices within one batch.

## Repeat, start, and end behavior

The extension exposes four sequence controls:

- **Sequence grouping** — advance per batch or per image.
- **Hold each choice for N images / batches** — repeat a value for N sequence units.
- **Start index** — start from a later choice; `0` is the first value.
- **After the last choice** — **Loop** wraps to the first choice; **Clamp** stays on the final choice.

All Sequential blocks in one image use the same global sequence index, even if the blocks have different numbers of choices.

## Multiple blocks and folders

```text
===A|B|C===, ==D|E|F==
```

resolves together:

```text
A, D -> A/
B, E -> B/
C, F -> C/
```

Multiple folder blocks are joined with `__`:

```text
===A|B|C===, ===D|E|F===
```

becomes:

```text
A__D/
B__E/
C__F/
```

Adjacent blocks are also supported, but ordinary comma/space-separated prompt tokens are easier to read and are recommended.

## Escaping

Escapes are defined **inside a matched Sequential block**:

```text
==A\|B | C\=D | E\\F==
```

contains these three choices:

```text
A|B
C=D
E\F
```

Backslashes outside Sequential blocks are preserved. Windows-style paths therefore remain untouched when no Sequential block consumes them.

## Parser safety rules

The parser intentionally fails closed on ambiguous input.

- A normal `==...==` block requires at least one unescaped top-level `|`.
- A folder `===...===` block may contain one value.
- Nested Sequential blocks are unsupported.
- Malformed or overlong delimiter runs such as `====...====` are not partially interpreted.
- Attached comparison-like text such as `artist==foo|bar==weight` is left literal.
- Extra Network tags such as `<lora:name:1>` are atomic.
- Pipes inside Forge `[...]`, Dynamic Prompts `{...}`, and protected groups do not split Sequential choices.
- Randomized fuzz/regression tests verify that arbitrary prompt text is parsed deterministically and without crashes.

## Dynamic Prompts compatibility

Dynamic Prompts and Sequential Prompts are intended to run **at the same time**.

The normal Forge lifecycle is:

1. Dynamic Prompts expands its templates during its `process()` callback.
2. Forge calls `p.init(...)` after all always-on `process()` callbacks.
3. Sequential Prompts inspects the resulting final prompt arrays after `p.init(...)`.
4. Sequential Prompts resolves the current batch in `before_process_batch()`.
5. A one-shot core guard validates the final state immediately before Forge parses Extra Networks.

This means a Dynamic Prompts wildcard may itself produce a valid `==...==` block and Sequential Prompts can consume that final result.

Automated compatibility tests use the real `dynamicprompts==0.31.0` package and cover:

- `{A|B}` variants
- `{2$$A|B|C}` multi-selection
- `${variable}` assignments/access
- `%{...$$...}` wrap commands
- actual wildcard files through `WildcardManager`
- normal Sequential blocks
- folder-routing Sequential blocks
- both processing orders at the parser level

If Dynamic Prompts is manually configured to use a variant/wildcard delimiter that overlaps `==` / `===`, relevant raw Sequential jobs are rejected instead of relying on callback order.

## Negative prompts

**Also process negative prompt** is enabled by default.

When enabled, positive and negative prompt arrays share the same image identity and sequence index. When disabled, Sequential-looking text in the negative prompt remains untouched.

Folder names are derived only from folder markers in the **main positive prompt**.

## LoRA / Extra Networks

LoRA choices are supported:

```text
==<lora:character_a:1> | <lora:character_b:1>==
```

However, Forge activates Extra Networks for a batch. If Sequential Prompts would create different LoRA / Extra Network configurations inside the same batch, the job is rejected before sampling.

Safe patterns include:

```text
Batch size = 1
```

or the default **one choice per batch** mode.

The guard only rejects unsafe differences created by Sequential resolution; it does not invent new policy for unrelated prompts supplied by other extensions.

## Hires.fix

Hires.fix positive and negative prompt arrays are included in the same frozen image-layout contract.

- The same sequence index is used for the base and corresponding Hires prompt.
- Custom Hires prompts may contain `==...==` / `===...===`.
- Hires-only folder markers do **not** determine the folder; folder identity comes from the main positive prompt.
- Forge Neo's current Hires output-root behavior is respected, including `outdir_hires_samples` when configured.
- First-pass Hires intermediate saves are not routed as final Sequential samples.

## Output-folder routing

Folder routing is intentionally conservative.

A destination component is:

- Unicode-normalized;
- stripped of control and dangerous bidi characters;
- sanitized for Windows-invalid filename characters;
- protected against `.` / `..` and Windows device names such as `CON`, `NUL`, `COM1`, and `LPT1`;
- byte/character bounded;
- deterministically hashed when sanitization is lossy so distinct unsafe names do not silently collapse together.

The destination path is containment-checked before use.

If Forge's own **save to dirs** option is enabled, the Sequential folder is nested under the directory Forge already selected.

## Save numbering and post-processing identity

Forge creates a candidate filename before the `before_image_saved` callback. Sequential Prompts redirects that filename into the selected folder and recomputes the numeric prefix against the destination directory, while preserving Forge's final collision policy.

Folder routing follows the live prompt/negative/seed/subseed identity. If another extension legitimately reorders images and metadata together, routing follows that identity rather than blindly trusting the original slot. If the identity becomes ambiguous, routing is skipped rather than guessed.

Grids, video output, manual/non-core saves, and Hires first-pass intermediates are deliberately excluded from normal choice-folder routing.

## Fail-closed lifecycle behavior

Forge catches exceptions thrown by always-on script callbacks. That means throwing from `before_process_batch()` alone is **not enough** to guarantee a broken batch stops.

v0.6.1 therefore uses a two-stage safety design:

1. batch-resolution failures are recorded without emptying the live prompt list;
2. a one-shot wrapper around Forge's core `parse_extra_network_prompts()` raises the recorded error outside the always-on callback catcher.

This avoids the older failure mode where setting `p.prompts = []` caused Forge to silently break out of its generation loop before the explicit safety exception could run.

The guard also snapshots the resolved prompt state. Unchanged output produced by Sequential Prompts is trusted, while a later extension that changes the protected prompt state and reintroduces `==...==` / `===...===` is stopped before Extra Network parsing.

Invalid API/script settings are normalized only for inspection; if a real Sequential block is active, invalid grouping/repeat/start/end/negative settings cause an explicit pre-sampling failure instead of falling through with raw syntax.

## Special Forge modes

### Prompt Matrix — intentionally incompatible for raw Sequential syntax

Forge's selectable **Prompt Matrix** script splits its selected raw prompt on `|` before the normal processing lifecycle. Because `|` is also the choice separator inside Sequential blocks, this is a structural conflict. Relevant raw Sequential jobs are rejected.

### SD Upscale — intentionally rejected when Sequential is relevant

SD Upscale recursively processes tiles and produces its composite outside the normal core sample identity used by folder routing. Sequential jobs are rejected rather than pretending that identity is reliable.

### Wan / video

Multi-frame Wan/video jobs are rejected when Sequential syntax is active because the batch axis represents frames rather than independent image identities. Single-frame Wan remains allowed.

## Installation

From the Forge Neo root directory:

```bash
git clone https://github.com/umimi893/sd-webui-sequential-prompts-forge-neo.git extensions/sd-webui-sequential-prompts-forge-neo
```

Restart Forge Neo, then open the **Sequential Prompts** accordion in txt2img or img2img.

The extension is enabled by default, but a prompt with no valid `==...==` / `===...===` syntax is a behavioral no-op.

### Update

```bash
cd extensions/sd-webui-sequential-prompts-forge-neo
git pull
```

Restart Forge Neo after updating Python extension code.

## Migrating from v0.5.x

Replace:

```text
$A|B|C$
```

with:

```text
==A|B|C==
```

and replace:

```text
$$A|B|C$$
```

with:

```text
===A|B|C===
```

There is no automatic compatibility parser for the old dollar syntax because that would recreate the Dynamic Prompts conflict.

## Automated verification

CI runs the full suite on:

- Ubuntu latest / Windows latest
- Python 3.10 / 3.11 / 3.13
- pinned `dynamicprompts==0.31.0`

CI also checks out the audited upstream Forge Neo and sd-dynamic-prompts commits and verifies the lifecycle contracts this extension depends on: callback exception handling, process/init/batch order, Extra Network parsing order, Hires prompt arrays/output root, save callback order, save identity, and Prompt Matrix behavior.

The suite covers parser edge cases and randomized input, Dynamic Prompts integration, batch/partial-batch identity, Hires.fix, negative prompts, LoRA safety, shallow-copy/reuse behavior, output routing, Unicode/Windows/path safety, numbering, special-mode rejection, and explicit fail-closed errors.

See [`AUDIT.md`](AUDIT.md) for what is proven automatically and what still requires a real Forge UI/GPU smoke run.

## Development

Local core tests:

```bash
python -m compileall -q seqprompt scripts tests
python -m unittest discover -s tests -v
```

Upstream contract tests are skipped locally unless `FORGE_NEO_CONTRACT_ROOT` and `DYNAMIC_PROMPTS_EXTENSION_ROOT` point at the audited source trees. GitHub Actions configures both automatically.

## Release history

See [`CHANGELOG.md`](CHANGELOG.md).
