# v0.6.1 compatibility and safety audit

Audit date: **2026-09-05**

Extension release reviewed: **v0.6.1**

## Audited upstreams

### Stable Diffusion WebUI Forge Neo

Repository: `Haoming02/sd-webui-forge-classic`

Branch: `neo`

Audited commit:

```text
d2c29a6bc6cf834c83cdefed394062c2c3e58760
```

This replaces the older August 2026 audit baseline. CI checks out this exact commit and verifies the lifecycle assumptions used by Sequential Prompts.

### Dynamic Prompts extension

Repository: `adieyal/sd-dynamic-prompts`

Audited commit:

```text
de056ff8d80e4ad120e13a90cf200f3383f427c6
```

### Dynamic Prompts parser/generator

Package:

```text
dynamicprompts==0.31.0
```

CI installs the real package and executes integration tests against its grammar and generators.

## Audit objective

The goal of this audit was not merely to verify that `==A|B==` works in isolation. The review traced every contract needed for safe real-world coexistence with Forge Neo and Dynamic Prompts:

- prompt-array creation and mutation;
- always-on script callback ordering;
- Forge's callback exception handling;
- `p.init(...)` timing;
- current-batch slicing;
- Extra Network / LoRA parsing and activation;
- Hires.fix prompt arrays and current Hires output-root behavior;
- image identity across batch and post-processing operations;
- `before_image_saved` routing;
- save numbering and collision behavior;
- grids, auxiliary saves, Hires intermediates, manual saves, and video;
- X/Y/Z-style shallow copies and reused processing objects;
- Prompt Matrix, SD Upscale, and Wan/video special cases;
- Dynamic Prompts variants, multi-selection, variables, wrap commands, and wildcard files;
- malformed input, false positives, path safety, and invalid script/API settings.

## Upstream lifecycle verified

The audited Forge Neo `process_images_inner()` contract is:

1. `p.setup_prompts()` builds the prompt arrays.
2. Always-on `process()` callbacks run.
3. Forge calls `p.init(...)`.
4. Forge slices `p.prompts`, `p.negative_prompts`, seeds, and subseeds for the current batch.
5. Always-on `before_process_batch()` callbacks run.
6. Forge checks whether the live prompt list is empty.
7. Forge calls `p.parse_extra_network_prompts()`.
8. Extra Networks are activated.
9. `process_batch()` and conditioning setup follow.

Sequential Prompts deliberately resolves after step 3 and during step 5, with a one-shot safety check at step 7.

CI contains an upstream contract test that fails if this audited order changes.

## Important findings and fixes

### High — batch failures could silently end generation

**Previous behavior:** when Sequential batch validation/resolution failed, the extension set:

```python
p.prompts = []
```

The intent was to stop unsafe generation. However, current Forge Neo checks `len(p.prompts) == 0` immediately after `before_process_batch()` and breaks the generation loop **before** calling `parse_extra_network_prompts()`.

That meant the extension's later explicit core guard could be skipped, producing a silent stop instead of the intended reasoned failure.

**v0.6.1 fix:** batch failures now set only a blocked reason. The live prompt batch remains intact so Forge reaches the one-shot guarded `parse_extra_network_prompts()` call, which raises the real error outside the always-on callback exception catcher.

If the guard itself cannot be installed because an upstream contract changed, the extension uses an explicit last-resort empty-batch stop and re-raises so Forge logs the guard installation failure.

### High — malformed long equals runs could be partially interpreted

The v0.6.0 parser correctly rejected four-equals blocks, but a longer malformed run could be revisited from a later character position.

For example, a six-character equals run could expose a five-character suffix that looked like a valid `==` close immediately followed by a `===` opener. That allowed malformed input to be partially transformed.

**v0.6.1 fix:** an uninterrupted physical run of `=` is now evaluated as one token. Only these exact forms are accepted:

- exact `==` close;
- exact `===` close;
- close + immediately adjacent valid `==` opener;
- close + immediately adjacent valid `===` opener.

Malformed overlong runs are skipped as one unit and cannot be reinterpreted from the middle.

Regression tests cover four-, six-, seven-, and longer malformed delimiter runs.

### High — invalid script/API settings could fail inside a Forge-caught callback

The old configuration construction used direct conversions such as:

```python
int(repeat_each)
```

If an API client or stale UI state supplied an invalid value, `process()` could raise. Forge catches exceptions from always-on `process()` callbacks and continues, which is not a safe place to fail when raw Sequential syntax is present.

**v0.6.1 fix:** grouping, repeat count, start index, end mode, and negative-prompt toggle are validated explicitly. Invalid values remain a no-op for jobs with no Sequential syntax. If a final Sequential source is active, the invalid configuration is rejected from the `p.init(...)` gate, outside the always-on callback catcher and before sampling.

### Medium — a resolved choice could resemble fresh Sequential syntax

A legitimate selected choice can contain escaped text that decodes to something resembling `==A|B==`. A naive second scan could mistake the extension's own resolved output for syntax introduced later by another extension.

**v0.6.1 fix:** the core-preparse sentinel snapshots the protected resolved prompt state immediately after Sequential resolution. Unchanged output is trusted. If a later callback changes the protected prompt state, the changed state is rescanned and newly introduced Sequential syntax is rejected before Extra Network parsing.

### Medium — escape behavior outside blocks was inconsistent

Backslash decoding is now limited to matched Sequential choice bodies. Text outside Sequential blocks is preserved exactly instead of having `\=` consumed merely because another Sequential block exists elsewhere in the prompt.

### Medium — compatibility validation was too dependent on local mocks

v0.6.0 already introduced real `dynamicprompts` tests. v0.6.1 expands this further and pins upstream source contracts.

CI now verifies:

- real Dynamic Prompts variants;
- real `$$` multi-selection;
- real variables;
- real wrap commands;
- actual wildcard files via `WildcardManager`;
- parser behavior when Sequential resolution occurs before Dynamic Prompts parsing;
- the audited sd-dynamic-prompts extension process contract;
- the audited Forge Neo process/init/batch/parse order;
- Forge's callback exception catcher;
- current Hires prompt arrays and Hires output-root behavior;
- save callback ordering and save identity;
- Prompt Matrix's raw `|` consumption.

## Dynamic Prompts coexistence result

The v0.6.1 syntax does not claim Dynamic Prompts' default delimiters.

Verified combinations include:

```text
{red|blue}, ==front|back==
```

```text
{2$$red|green|blue}, ==front|back==
```

```text
${season=!{summer|winter}} ${season}, ==front|back==
```

```text
%{portrait of ..., cinematic$${red|blue} subject}, ==front|back==
```

```text
__background__, ==front|back==
```

and folder routing:

```text
{red|blue}, ===front|back===
```

The Sequential parser keeps balanced Dynamic Prompts `{...}` constructs opaque. The real Dynamic Prompts generator leaves `==...==` / `===...===` intact for Sequential resolution.

If a user manually reconfigures Dynamic Prompts' configurable variant/wildcard delimiters to overlap the Sequential delimiters, a relevant raw Sequential job is rejected.

## LoRA / Extra Network audit

Forge parses and activates Extra Networks per live batch. Sequential Prompts therefore preflights the final arrays and rejects only cases where **Sequential resolution itself** would create different Extra Network signatures inside one batch.

Verified behavior:

- Batch size 1 is safe for per-image LoRA switching.
- Default one-choice-per-batch mode is safe when all images in a batch resolve to the same network configuration.
- Unsafe per-image LoRA differences inside one batch are rejected before sampling.
- Extra Network tags are treated atomically by the Sequential choice splitter.
- Existing heterogeneous prompt behavior unrelated to Sequential resolution is not newly policed.

## Hires.fix audit

Current Forge Neo creates independent Hires prompt arrays and slices them for the current iteration. Sequential Prompts freezes and validates those arrays when Hires.fix is enabled, then resolves them using the same global image sequence identity.

A relevant upstream change since the old audit is:

```python
self.outpath_samples = opts.outdir_hires_samples or self.outpath_samples
```

The output router uses Forge's current `p.outpath_samples` at save time, so a configured Hires sample root remains the controlling root. The selected Sequential folder is placed below the root Forge currently exposes.

Hires first-pass intermediate saves do not originate from the final core sample-save call site and remain excluded from normal folder routing.

## Save-routing audit

The audited Forge save contract still calls `before_image_saved` after constructing a candidate filename and before the atomic write.

Sequential routing verifies:

- a frozen run layout exists;
- the save belongs to the current processing object;
- the save is a positively identified core sample/associated auxiliary save;
- the destination is under Forge's active sample root;
- the final choice identity can be mapped unambiguously;
- the destination component is filesystem-safe;
- destination numbering is recomputed before save.

Routing is skipped rather than guessed when identity or save provenance is ambiguous.

Grids, video, manual/non-core saves, and Hires first-pass intermediates are intentionally excluded.

## Filesystem safety audit

Folder components are protected against:

- `/` and `\` path separators;
- `.` and `..` traversal components;
- Windows-invalid characters;
- Windows reserved device names;
- control characters;
- dangerous bidirectional text controls;
- excessive character and UTF-8 byte length;
- deterministic collisions caused by lossy sanitization.

A final containment check is performed before the routed path is used.

## Special modes

### Prompt Matrix

Still intentionally incompatible when raw Sequential syntax is present in the selected matrix prompt. Forge Prompt Matrix splits the raw prompt on `|` before the normal lifecycle. This is structural and cannot be solved by changing the outer delimiter alone.

### SD Upscale

Still intentionally rejected when Sequential is relevant because tile sub-runs and final composite saving do not provide the same identity contract as normal core samples.

### Wan/video

Active multi-frame Wan/video jobs are rejected because Forge's batch dimension represents frames rather than independent image identities. Single-frame Wan remains allowed.

## Automated verification matrix

GitHub Actions runs on:

```text
ubuntu-latest  / Python 3.10
ubuntu-latest  / Python 3.11
ubuntu-latest  / Python 3.13
windows-latest / Python 3.10
windows-latest / Python 3.11
windows-latest / Python 3.13
```

Every job:

1. checks out this repository;
2. checks out the pinned audited Forge Neo commit;
3. checks out the pinned audited sd-dynamic-prompts extension commit;
4. installs `dynamicprompts==0.31.0`;
5. compiles extension and test code;
6. runs unit, integration, real Dynamic Prompts, filesystem, script-contract, randomized-parser, and upstream-contract tests.

The upstream contract tests are intentionally strict. If Forge Neo or Dynamic Prompts changes a lifecycle assumption in a future re-audit, the pinned baseline can be advanced only together with a review of the affected contract.

## What automated testing does not prove

No automated test suite can prove that a third-party extension ecosystem is bug-free under every possible combination.

This audit also does **not** claim a GPU-backed end-to-end Forge Neo launch was executed inside GitHub Actions. The remaining release boundary is a real local smoke run covering:

- Forge Neo startup and Gradio rendering;
- txt2img Batch size 1 and >1;
- img2img;
- Hires.fix with and without a separate Hires output directory;
- Dynamic Prompts enabled in the real Forge UI;
- real wildcard files from the user's extension installation;
- `==...==` and `===...===`;
- actual PNG/JPEG/WebP save behavior on the user's Windows installation;
- one safe LoRA sequence and one intentionally rejected unsafe LoRA sequence.

The code is designed to **fail closed** when an audited lifecycle invariant cannot be preserved. That is stronger than silently attempting an uncertain operation, but it is not a claim that unknown future third-party behavior is impossible.

## Release assessment

Subject to a green CI run on the final v0.6.1 commit, the implementation is suitable as the hardened release baseline for normal Forge Neo image-generation use.

Future updates to the audited Forge Neo commit, Dynamic Prompts extension commit, or Dynamic Prompts parser version should be treated as a compatibility re-audit rather than a blind version bump.
