# Forge Neo compatibility audit

This document records the release-relevant audit for the v0.5.0 `$...$` / `$$...$$` implementation.

## Audited upstreams

- Forge Neo: `Haoming02/sd-webui-forge-classic`, branch `neo`, audited head `e782dc3fe07deb4653a8a1a1ad8ffa52783f54c5`.
- Forge-compatible Dynamic Prompts: `abzaloff/sd-dynamic-prompts`, audited head `3e62452776f52e2c641c2c52d3cd908140c3743e`.

If either upstream changes the relevant lifecycle or save code, the assumptions below should be rechecked.

## 1. Parser audit

Final syntax:

```text
$A|B|C$       sequential only
$$A|B|C$$     sequential + output folder
```

Retired forms are deliberately literal: `=...=`, `==...==`, `[[...]]`, `&...&`, `&&...&&`.

Confirmed parser behavior:

- `\|`, `\$`, and `\\` escapes are supported.
- unrelated backslashes are preserved.
- Forge `<name:args>` Extra Network tags are atomic.
- Forge `[...]` / `(...)` grammar does not leak its internal `|` into Sequential choice splitting.
- top-level scanner can still resolve Sequential syntax inside Forge grouping.
- Dynamic Prompts default `{...}` blocks remain opaque to this parser.
- adjacent Sequential blocks work.
- malformed and unsupported nested blocks fail closed instead of partially transforming the prompt.
- empty choices are supported.
- ordinary dollar text that does not form a complete multi-choice block is left literal.

Parser audit suite: **68 tests** plus fuzz/stress checks during development.

## 2. Forge lifecycle and image identity

Current Forge order relevant to this extension is:

1. `setup_prompts()`
2. build `all_seeds` / `all_subseeds`
3. all always-on `process()` callbacks
4. `p.init(...)`
5. per iteration, slice prompt/seed arrays
6. all `before_process_batch()` callbacks
7. `len(p.prompts) == 0` break
8. `p.parse_extra_network_prompts()`
9. Extra Network activation
10. `process_batch()` / conditioning / sampling / post-processing / save

Important consequence: Forge catches exceptions raised directly by ScriptRunner callbacks and merely logs them. Therefore a callback exception alone is not a hard stop.

v0.5.0 consequently uses:

- a one-shot `p.init` gate after all `process()` callbacks to freeze the final batch size and total prompt count;
- the frozen layout for every global image index;
- an empty-current-prompt soft stop plus a one-shot core `parse_extra_network_prompts` backstop for unsafe batch states;
- strict integer identity rather than silently coercing floats/strings/bools;
- run ownership and rebinding safeguards for shallow-copied processing objects.

Final partial batches from explicit/API prompt lists are valid when they are the true frozen tail. Unexpected short batches are rejected.

Lifecycle audit suite: **76 tests**.

## 3. Activation / Dynamic Prompts / Hires / Extra Networks

The extension is a behavioral no-op when enabled but no final relevant prompt array contains Sequential syntax.

Only arrays that actually contain active Sequential syntax are required to be mutable. This avoids rejecting unrelated read-only prompt containers.

Hires arrays are examined only when `enable_hr=True`; stale `all_hr_*` data from a reused processing object is ignored when Hires is disabled.

Dynamic Prompts:

- current Forge-compatible Dynamic Prompts rewrites prompt/count/seed/Hires arrays in `process()`;
- activation after the real `p.init` therefore sees its final arrays;
- default `{...}` / `__...__` delimiters coexist;
- exact `$` / `$$` delimiter ownership conflicts fail closed;
- a core preparse sentinel rejects unresolved Sequential syntax reintroduced by a later batch callback.

### Extra Network / LoRA constraint

Forge's current batch parser effectively activates one positive-prompt Extra Network configuration for the batch. Hires positive follows the same batch-wide mechanism.

Therefore the extension rejects only cases where **Sequential resolution itself** changes the effective registered Extra Network signature and the resulting same-batch signatures differ.

It does not police pre-existing heterogeneous network text when Sequential changed only ordinary prompt text. Unknown network names and disabled Extra Networks do not trigger this guard.

A previous audit hypothesis that LoRA tags remained stripped until final save was disproved: Forge restores `p.prompts` from `p.all_prompts` before the save/postprocess path. No workaround for that false positive is included.

Integration audit suite: **86 tests**.

## 4. Save routing audit

Current Forge computes the original filename and numeric prefix, creates the original directory, then calls `before_image_saved`, and finally saves using the callback-mutated `params.filename`.

v0.5.0 routes only when the callback can positively identify the synchronous path:

```text
modules.processing.process_images_inner
    -> modules.images.save_image
```

and `grid is False` and the job is not a multi-frame video save.

This intentionally routes:

- final samples;
- before-face-restoration saves;
- before-color-correction saves;
- masks;
- mask composites.

It intentionally does **not** route:

- final grids;
- Hires first-pass intermediate saves;
- manual/third-party save calls;
- selectable-script composite saves outside Forge's core path;
- multi-frame video frame output.

No filename-only guess is used when the Forge save context cannot be proven.

### Numbering / overwrite finding

A high-impact issue in the earlier implementation was confirmed: Forge chose `00000...` in the original directory before the callback, while the extension moved the file into another directory. The original directory could remain empty, causing later saves to propose the same sequence again and potentially overwrite under Forge's `Override` policy.

v0.5.0 recomputes Forge-style numbering inside the actual destination folder. Forced and non-numbered filenames are preserved and Forge remains authoritative for final collision behavior.

### Postprocess reorder finding

A mutable `p.batch_size` or current slot number is not enough to identify the image after `postprocess_batch_list`. v0.5.0 stores every original slot's `(positive, negative, seed, subseed)` identity and reverse-maps the live save slot after compliant reordering/removal.

If identical metadata has more than one possible folder outcome, routing is skipped as ambiguous. Added images beyond the frozen original batch are not assigned fabricated identities.

Residual limitation: pixel-only reordering that leaves all Forge metadata unchanged cannot be detected from the save callback.

### Filesystem hardening

- output component sanitization covers portable Windows restrictions and reserved device names;
- Unicode NFC normalization;
- C0/lone-surrogate/bidi control hardening while preserving benign ZWJ emoji sequences;
- UTF-8 byte and character limits;
- deterministic disambiguation after lossy sanitization;
- destination containment checked before and after mkdir;
- save-to-dirs subdirectories preserved;
- POSIX Forge full-path post-callback truncation is budgeted explicitly;
- Windows path fitting uses UTF-16 code-unit budgeting.

Save-routing audit suite: **56 tests**. We intentionally did not chase 100% line coverage for OS API failure fallbacks once all release-relevant branches were exercised.

Forge catches exceptions from `before_image_saved` callbacks and continues the original save, so an unexpected routing callback failure should not destroy the generated image.

## 5. Abort/reuse and Wan/video

Run-private folder maps and identities are cleared before every new run and after normal postprocess. If an exception skips postprocess, the next run's begin step still clears stale routing state.

Forge's Wan mode can use the batch dimension as a video-frame axis. Multi-frame Wan is therefore not a valid independent-image sequence domain and is rejected only when Sequential syntax is actually active. Single-frame Wan and no-syntax jobs remain allowed.

Abort/Wan audit suite: **10 tests**.

## 6. Forge selectable scripts

- **Prompt Matrix** splits its selected raw prompt directly on `|`, structurally consuming `$A|B$` before the standard lifecycle. A relevant raw Prompt Matrix target is blocked.
- **SD Upscale** recursively runs tiled `process_images()` calls and saves a final composite outside the core save identity. Relevant Sequential use is blocked.
- **X/Y/Z Plot**, **Prompts from File**, **Loopback**, and img2img Batch create sub-runs or reuse/copy the processing object. Run-private state is reset for each `process_images()` invocation; the sequence therefore restarts per sub-run.

## Automated release checks

The detailed development audit exercised **304 unit/contract checks** across the parser, lifecycle, activation, batch integration, save routing, cleanup/Wan behavior, and Script orchestration. Those detailed tests are preserved in the Git-invisible local audit snapshot.

The committed release CI suite contains **68 focused contract tests**. It intentionally avoids duplicating every audit-only edge case while retaining coverage of the release-critical parser, frozen layout, LoRA/Hires integration, save routing, Wan policy, and Script orchestration contracts.

Release CI commands:

```text
python -m compileall -q seqprompt scripts tests
python -m unittest discover -s tests -v
git diff --check
```

CI must run on Python 3.13 on both Ubuntu and Windows.

## Runtime validation still recommended

Automated tests do not replace a real Forge Neo runtime smoke test. The following real-runtime checks are still recommended and should be recorded when available:

1. txt2img, Batch size 3, Per image: `$$A|B|C$$, $D|E|F$` -> A/B/C folders and correct prompts.
2. Repeat/start/loop/clamp.
3. Per batch mode.
4. Hires.fix final routing plus Save-before-Hires intermediate staying normal.
5. LoRA same-batch safe and rejected-unsafe cases.
6. Dynamic Prompts with default delimiters.
7. Grid enabled.
8. save-to-dirs enabled.
9. img2img.
10. Unicode/Japanese folder choices.
11. repeated saves returning to A without overwriting earlier A images.
12. Windows filesystem behavior with the user's actual Forge settings.

The absence of this recorded smoke run is documented explicitly; it does not change the passing automated audit/CI result above.
