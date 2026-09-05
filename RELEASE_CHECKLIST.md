# v0.6.1 release checklist

This is the final release gate for Sequential Prompts for Forge Neo v0.6.1.

## Automated gate

The release candidate must satisfy all of the following on the exact commit intended for release:

- [ ] `metadata.ini` reports `Version = 0.6.1`.
- [ ] README reports v0.6.1 and the current audited upstream versions.
- [ ] Ubuntu / Python 3.10 CI passes.
- [ ] Ubuntu / Python 3.11 CI passes.
- [ ] Ubuntu / Python 3.13 CI passes.
- [ ] Windows / Python 3.10 CI passes.
- [ ] Windows / Python 3.11 CI passes.
- [ ] Windows / Python 3.13 CI passes.
- [ ] The diagnostics collector self-test passes in every CI matrix job.
- [ ] The real `dynamicprompts==0.31.0` integration suite passes.
- [ ] The pinned Forge Neo upstream contract tests pass.
- [ ] The pinned sd-dynamic-prompts extension contract tests pass.

The audited upstream baseline is:

```text
Forge Neo: d2c29a6bc6cf834c83cdefed394062c2c3e58760
sd-dynamic-prompts: de056ff8d80e4ad120e13a90cf200f3383f427c6
dynamicprompts: 0.31.0
```

## Real-machine gate

Run [`SMOKE_TEST.md`](SMOKE_TEST.md) on the intended Forge Neo installation.

At minimum, do not publish a stronger compatibility claim until these have been exercised on a real machine:

- [ ] Forge Neo starts and the Sequential Prompts UI renders in txt2img and img2img.
- [ ] Plain prompts remain a behavioral no-op.
- [ ] Per-batch sequencing works.
- [ ] Per-image sequencing works.
- [ ] Dynamic Prompts and Sequential Prompts coexist in the real Forge UI.
- [ ] A real wildcard can coexist with Sequential syntax.
- [ ] Hires.fix works.
- [ ] `===...===` folder routing writes real files to the expected root.
- [ ] Windows path sanitization works on a real Windows filesystem when Windows is a supported target.
- [ ] The save formats actually used by the tester work.
- [ ] img2img works.
- [ ] A safe LoRA sequence works.
- [ ] An unsafe per-image LoRA sequence is explicitly rejected before sampling.
- [ ] Unsupported special modes fail explicitly rather than silently producing uncertain output.

## Failure capture

Before changing settings after a failure, run from the extension directory:

```bash
python tools/collect_diagnostics.py --output sequential-prompts-diagnostics.json
```

Review the JSON before posting it. The collector does not read prompts, images, API keys, environment variables, or Forge configuration values.

Then report the smallest reproduction using the repository's structured Bug report form.

## Documentation gate

Before publishing a release/tag:

- [ ] README syntax examples match the current parser.
- [ ] README does not present retired `$...$` / `$$...$$` syntax as supported Sequential syntax.
- [ ] [`AUDIT.md`](AUDIT.md) identifies the exact Forge Neo / Dynamic Prompts versions audited.
- [ ] [`CHANGELOG.md`](CHANGELOG.md) contains all user-visible v0.6.1 changes.
- [ ] [`SMOKE_TEST.md`](SMOKE_TEST.md) matches the current supported/unsupported behavior.
- [ ] Bug-report instructions match the diagnostics collector.

## GitHub release gate

The repository should have an immutable point users can install when v0.6.1 is declared released:

- [ ] Create tag `v0.6.1` on the exact accepted commit.
- [ ] Create a GitHub Release for `v0.6.1` from that tag.
- [ ] Use [`RELEASE_NOTES_v0.6.1.md`](RELEASE_NOTES_v0.6.1.md) as the release-note baseline.
- [ ] Verify the source archive contains `metadata.ini`, README, AUDIT, SMOKE_TEST, diagnostics tool, and the extension code.
- [ ] Do not move or recreate the published tag after release.

## Acceptance rule

A green automated matrix proves the audited source-level contracts. It does not substitute for the real Forge Neo GPU/UI smoke run.

If the real-machine gate has not been completed, v0.6.1 may still be described as **CI-audited**, but it should not be described as universally proven bug-free on every Forge/extension combination.
