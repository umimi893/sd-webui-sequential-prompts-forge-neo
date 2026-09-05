# Sequential Prompts for Forge Neo v0.6.1

v0.6.1 is the hardened compatibility baseline for deterministic Sequential Prompts on Forge Neo.

## Main changes

- Uses `==A|B|C==` for deterministic sequencing and `===A|B|C===` for sequencing plus output-folder routing.
- Retires `$...$` / `$$...$$` as Sequential syntax so Dynamic Prompts can keep its own dollar grammar without collision.
- Fixes a Forge lifecycle failure mode that could silently terminate a broken Sequential batch before the intended explicit error surfaced.
- Fixes malformed long `=` runs being partially reinterpreted as valid Sequential delimiters.
- Adds explicit fail-closed validation for script/API settings when Sequential syntax is active.
- Strengthens the late-callback safety sentinel while avoiding false positives from Sequential's own resolved output.
- Expands real Dynamic Prompts compatibility coverage to variants, `$$` multi-selection, variables, wrap commands, real wildcard files, and parser-order checks.
- Re-audits current Forge Neo lifecycle, Hires.fix prompt arrays/output roots, save callbacks, Extra Network ordering, and Prompt Matrix behavior against a pinned upstream commit.
- Hardens output-folder routing, Windows filename/path handling, Unicode normalization, collision handling, and save numbering.
- Adds real-machine smoke-test and privacy-conscious diagnostics tooling for issues that cannot be proven inside GitHub Actions.

## Audited baseline

```text
Forge Neo
Haoming02/sd-webui-forge-classic
neo @ d2c29a6bc6cf834c83cdefed394062c2c3e58760

sd-dynamic-prompts
adieyal/sd-dynamic-prompts @ de056ff8d80e4ad120e13a90cf200f3383f427c6

dynamicprompts==0.31.0
```

## Syntax

Normal deterministic sequence:

```text
1girl, ==front view|side view|back view==
```

Sequence plus output-folder routing:

```text
1girl, ===front view|side view|back view===
```

Dynamic Prompts can coexist in the same prompt:

```text
1girl, {red|blue} hair, __background__, ==front view|side view|back view==
```

## Important migration note

v0.5.x syntax:

```text
$A|B|C$
$$A|B|C$$
```

must be migrated to:

```text
==A|B|C==
===A|B|C===
```

The old dollar syntax is intentionally not accepted as a compatibility alias.

## Safety behavior

When the extension cannot preserve an audited prompt/batch identity, it is designed to fail closed rather than silently guess.

In particular:

- unsafe per-image LoRA / Extra Network switching inside one Forge batch is rejected;
- raw Sequential syntax with Prompt Matrix is intentionally incompatible;
- relevant SD Upscale jobs are intentionally rejected;
- multi-frame Wan/video jobs are rejected when Sequential syntax is active;
- ambiguous save-routing identity is skipped rather than guessed.

## Verification

CI runs on Ubuntu and Windows across Python 3.10, 3.11, and 3.13. Each job installs the real pinned Dynamic Prompts parser/generator dependency and checks pinned Forge Neo / sd-dynamic-prompts source contracts.

For the real GPU/UI boundary, follow [`SMOKE_TEST.md`](SMOKE_TEST.md). If a real-machine case fails, collect diagnostics with:

```bash
python tools/collect_diagnostics.py --output sequential-prompts-diagnostics.json
```

See [`AUDIT.md`](AUDIT.md) for the compatibility audit and [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md) for the final release gate.
