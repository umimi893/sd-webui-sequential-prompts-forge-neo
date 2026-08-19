# Compatibility audit

Audit date: 2026-08-19

Target: Stable Diffusion WebUI Forge Neo, `Haoming02/sd-webui-forge-classic`, branch `neo`.
Upstream commit inspected: `e782dc3fe07deb4653a8a1a1ad8ffa52783f54c5`.

## Scope

The review traced the extension against Forge Neo's actual script and generation lifecycle, including:

- `StableDiffusionProcessing.setup_prompts()`
- `ScriptRunner.process()`
- `ScriptRunner.before_process_batch()`
- per-batch slicing of positive and negative prompts
- Extra Networks parsing
- Hires.fix prompt arrays and second-pass conditioning
- infotext/main-prompt synchronization
- interaction with Dynamic Prompts-style prompt-list expansion
- Python 3.13 compatibility

## Findings fixed in v0.2.0

### High: Hires.fix used unresolved sequential syntax

Forge Neo maintains separate `all_hr_prompts` and `all_hr_negative_prompts` arrays. v0.1.0 only transformed `all_prompts` and `all_negative_prompts`, so a first pass could use `A` while the Hires.fix pass still received raw `[[A|B|C]]` text.

Fix: resolve Hires.fix arrays at the same global image index immediately before each batch is parsed.

### High: prompt expansion was order-sensitive with other extensions

v0.1.0 resolved the entire prompt list in `process()`. If another always-on extension replaced or expanded `p.all_prompts` after that callback, sequential selection could be lost. In particular, an extension that generated prompt variants after Sequential Prompts could receive an already-collapsed `A` template and replicate only that choice.

Fix: defer actual `[[...]]` resolution to `before_process_batch()`. Forge Neo invokes this after all `process()` callbacks and before Extra Networks parsing. The selected choice can therefore contain LoRA/extra-network tags and can safely operate on prompt lists produced by Dynamic Prompts.

### Medium: unrelated backslashes were silently removed

The parser documented support for `\|` and `\\`, but v0.1.0 treated backslash as a generic escape character. Text such as `C:\models\foo` could lose backslashes.

Fix: backslash now escapes only `|` or another backslash; otherwise it remains literal.

## Verification

Automated tests cover:

- per-image sequencing
- per-batch sequencing
- repeat counts
- loop and clamp behavior
- multiple blocks and differing block lengths
- escaped pipes and backslashes
- preservation of unrelated/trailing backslashes
- positive and negative batch-list synchronization
- Hires.fix positive and negative arrays
- disabled negative processing
- prompt lists already expanded by another extension
- LoRA tags inside choices before Extra Networks parsing
- script callback contract with a minimal Forge-style stub

Run:

```bash
python -m compileall -q seqprompt scripts tests
python -m unittest discover -s tests -v
```

## Residual risks / not yet proven

1. A real GPU-backed Forge Neo launch has not yet been executed in CI, so Gradio rendering and end-to-end image generation remain the final integration check.
2. Nested `[[...]]` blocks are intentionally unsupported.
3. There is no whole-block escape syntax for literal `[[...]]` text yet.
4. Another third-party extension could theoretically modify prompts *after* this extension's `before_process_batch()` callback. Forge Neo allows user callback prioritization, so no extension can make ordering completely impossible to override.
5. The repository currently has no license file. Before broad public distribution, choose and add an explicit license.

## Release recommendation

v0.2.0 is suitable for Forge Neo user testing. The remaining release gate is a clean-install smoke test in Forge Neo covering txt2img, img2img, Hires.fix, Batch size/count, Dynamic Prompts coexistence, and a LoRA choice.

## v0.4.0 folder-marker audit

The `==A|B|C==` syntax adds save-time folder routing while keeping `=A|B|C=` as a normal sequential block.

Safety and compatibility checks added:

- doubled markers are parsed before single-equals markers, preventing `==...==` from being partially consumed as `=...=`
- multiple doubled markers combine deterministically as `A__D`
- ordinary single-equals blocks never contribute to output folder names
- output names are sanitized for Windows-invalid characters and reserved device names
- `/`, `\\`, `..`, control characters, and other path-traversal inputs cannot create nested or parent paths
- long generated directory names are deterministically shortened with a hash suffix
- save routing uses the global image index (`iteration * batch_size + batch_index`), so Batch size > 1 is routed per image
- Forge grids are excluded from choice-folder routing
- Hires.fix first-pass intermediate saves are excluded because Forge saves them before exposing a reliable final image batch index
- the callback creates the destination directory itself because Forge Neo creates its original output directory before `before_image_saved` runs

The remaining release gate is still a real Forge Neo smoke test with final image saving enabled on Windows and Linux.
