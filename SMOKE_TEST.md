# v0.6.1 real Forge Neo smoke-test protocol

This document is the manual release-validation boundary that remains after the automated compatibility audit in [`AUDIT.md`](AUDIT.md).

The goal is not to test image quality. The goal is to prove that the extension survives a real Forge Neo launch, real Gradio controls, real sampling, real Hires.fix, real Dynamic Prompts, and real filesystem saves on the user's machine.

## Rules for the smoke run

- Use the current `main` branch of this extension unless validating a specific release tag.
- Restart Forge Neo after updating Python extension code.
- Keep Prompt Matrix, SD Upscale, and multi-frame Wan/video disabled except for the explicit rejection checks below.
- Use a small resolution and a fast model/sampler so the smoke run is cheap.
- Do not judge the generated composition. Validate prompt metadata, sequence order, absence/presence of explicit errors, and output paths.
- If a case fails, stop and capture diagnostics before changing settings.

## Record the environment first

From the extension directory, run:

```bash
python tools/collect_diagnostics.py --output sequential-prompts-diagnostics.json
```

Attach that JSON to a bug report. The collector intentionally does **not** read prompts, images, API keys, environment variables, or Forge configuration values.

Record separately:

- Forge Neo launch command/arguments;
- GPU model;
- model/checkpoint family used for the smoke run;
- whether Dynamic Prompts is enabled;
- whether Hires.fix is enabled;
- whether Forge `save to dirs` is enabled.

## 1. Startup and UI

1. Start Forge Neo with the extension installed.
2. Open txt2img.
3. Confirm the **Sequential Prompts** accordion appears.
4. Confirm the extension is enabled by default.
5. Confirm the default grouping is **one choice per batch**.
6. Open img2img and confirm the same accordion is available.
7. Check the terminal for import tracebacks mentioning `sequential_prompts`, `seqprompt`, or this repository name.

**Pass:** both UIs render and no extension import error appears.

## 2. Behavioral no-op

Prompt:

```text
1girl, white background
```

Generate one image with Sequential Prompts enabled.

**Pass:** generation behaves like ordinary Forge generation and no Sequential-specific error is raised.

## 3. Basic txt2img sequence — per batch

Settings:

```text
Batch size = 3
Batch count = 3
Sequence grouping = one choice per batch
```

Prompt:

```text
1girl, ==front view|side view|back view==, white background
```

Expected resolved order in saved metadata / infotext:

```text
batch 1 -> front view, front view, front view
batch 2 -> side view,  side view,  side view
batch 3 -> back view,  back view,  back view
```

**Pass:** raw `==...==` syntax is absent from final sample metadata and the batch order matches exactly.

## 4. Basic txt2img sequence — per image

Settings:

```text
Batch size = 3
Batch count = 2
Sequence grouping = advance every image
```

Prompt:

```text
1girl, ==front view|side view|back view==, white background
```

Expected:

```text
batch 1 -> front view, side view, back view
batch 2 -> front view, side view, back view
```

**Pass:** each image advances independently and the second batch restarts at the expected global index.

## 5. Repeat / start / loop / clamp

Use:

```text
==A|B|C==
```

Run these small checks:

| Setting | Expected sequence |
|---|---|
| repeat 2, start 0, Loop | A, A, B, B, C, C, A, A |
| repeat 1, start 1, Loop | B, C, A, B |
| repeat 1, start 1, Clamp | B, C, C, C |

**Pass:** observed prompt metadata follows the table exactly.

## 6. Negative prompt synchronization

Positive:

```text
1girl, ==front view|side view|back view==
```

Negative:

```text
==bad front|bad side|bad back==
```

With **Also process negative prompt** enabled, generate three sequence units.

Expected pairs:

```text
front view / bad front
side view  / bad side
back view  / bad back
```

Disable negative-prompt processing and repeat.

**Pass:** the positive prompt still sequences, while the negative prompt keeps literal `==bad front|bad side|bad back==` text when the option is disabled.

## 7. Dynamic Prompts coexistence

Enable Dynamic Prompts.

Use a known real wildcard from the local installation in place of `__your_wildcard__`:

```text
1girl, {red|blue} hair, __your_wildcard__, ==front view|side view|back view==
```

Also test a Dynamic Prompts dollar construct and a Sequential block in the same prompt:

```text
{2$$red|green|blue}, ==front view|side view|back view==
```

**Pass:** Dynamic Prompts expands its syntax, Sequential advances only its `==...==` block, and neither parser leaves a parse exception.

## 8. Dynamic Prompts produces Sequential syntax

Create or use a wildcard whose selected line is:

```text
==front view|side view|back view==
```

Prompt:

```text
1girl, __that_wildcard__
```

**Pass:** Dynamic Prompts expands the wildcard first and Sequential then consumes the resulting Sequential block.

## 9. Hires.fix

Run with Hires.fix enabled.

Main prompt:

```text
1girl, ==front view|side view|back view==
```

Test both:

1. no separate Hires prompt;
2. a separate Hires prompt containing its own `==high detail|very high detail==` block.

If Forge is configured with a separate Hires output directory, test once with that configuration too.

**Pass:** base/Hires processing keeps the same image identity, no raw Sequential syntax leaks into a stage that should have been resolved, and final images are saved under Forge's current Hires output-root rules.

## 10. Folder routing

Prompt:

```text
1girl, ===front view|side view|back view===, white background
```

Generate three sequence units.

Expected final sample directories:

```text
front view/
side view/
back view/
```

Then enable Forge's own **save to dirs** option and repeat.

**Pass:** the Sequential directory is nested under Forge's selected directory rather than escaping or replacing the intended sample root.

## 11. Folder sanitization on Windows

Use safe-to-test folder labels containing characters that cannot be used directly as Windows directory components:

```text
===CON|a:b|dot..name===
```

**Pass:** generation does not fail due to an invalid Windows path, no path escapes the sample root, and distinct lossy names do not silently collapse to the same routed directory.

## 12. Save formats

Run the folder-routing check with every format actually used on the machine:

- PNG;
- JPEG/JPG if used;
- WebP if used.

**Pass:** routed final files exist, retain their expected extension, and numbering/collision handling does not overwrite an existing file.

## 13. img2img

Repeat the basic sequence and folder-routing cases in img2img using any harmless input image.

**Pass:** sequence order and routing match txt2img semantics.

## 14. Safe LoRA sequencing

Use two LoRAs known to load on the machine.

Safe configuration:

```text
Sequence grouping = one choice per batch
Batch size = 2
```

Prompt pattern:

```text
==<lora:first:1>|<lora:second:1>==
```

**Pass:** each batch uses one consistent Extra Network configuration and generation succeeds.

## 15. Unsafe per-image LoRA rejection

Configuration:

```text
Sequence grouping = advance every image
Batch size = 2
```

Prompt pattern:

```text
==<lora:first:1>|<lora:second:1>==
```

**Pass:** the job is explicitly rejected before sampling. It must not silently generate with the wrong LoRA and must not silently end the generation loop.

## 16. Explicit unsupported-mode rejection

With raw Sequential syntax present, verify:

- Prompt Matrix is rejected;
- SD Upscale is rejected when Sequential is relevant;
- multi-frame Wan/video is rejected;
- single-frame Wan remains allowed if available in the local Forge build.

**Pass:** unsupported modes fail explicitly rather than producing guessed sequence identity.

## 17. Late failure visibility

This is primarily covered by automated tests. During the real smoke run, any invariant failure that occurs must satisfy one release rule:

> A broken Sequential job may fail, but it must not silently continue with unresolved syntax and must not silently terminate without a reason.

If a terminal traceback/error appears, keep the complete error text for the bug report.

## Release acceptance

A local environment can be marked **smoke-tested for v0.6.1** when all applicable checks above pass.

A failure in an optional mode does not justify hiding it. Record the exact failed case, attach diagnostics, and keep that mode outside the supported release claim until it is understood.
