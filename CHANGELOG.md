# Changelog

All notable public changes are recorded here. The current compatibility audit is in [`AUDIT.md`](AUDIT.md).

## v0.6.1 — lifecycle and compatibility hardening

### Fail-closed behavior

- Fixed a Forge Neo lifecycle bug where a failed Sequential batch set `p.prompts = []`, causing Forge to silently break the generation loop before the explicit core safety guard could run.
- Batch-resolution failures now preserve the live batch and are raised from the guarded core `parse_extra_network_prompts()` call, outside Forge's always-on callback exception catcher.
- Added a last-resort safe stop if the core preparse guard itself cannot be installed.
- Added explicit validation for grouping, repeat count, start index, end behavior, and negative-prompt settings. Invalid settings fail before sampling when Sequential syntax is actually active while remaining a no-op for plain prompts.
- The late-callback sentinel now snapshots Sequential's own resolved output so a legitimate selected value that resembles `==...==` is not mistaken for syntax injected later by another extension.

### Parser hardening

- Fixed malformed long `=` runs being reinterpreted from a later character position as valid close/open delimiter combinations.
- Only exact normal/folder delimiters and exact adjacent close+open runs are accepted.
- Malformed four-, six-, seven-, and longer equals runs fail closed rather than being partially transformed.
- Backslash decoding is now confined to matched Sequential choice bodies; text outside blocks is preserved exactly.
- Added deterministic randomized prompt fuzz coverage plus expanded malformed-input, comparison-text, Dynamic Prompts wrap, and mixed-adjacent-block tests.

### Dynamic Prompts

- Expanded real `dynamicprompts==0.31.0` tests to include actual wildcard files through `WildcardManager` and `%{...$$...}` wrap commands.
- Added a reverse-order parser test proving Sequential resolution does not damage Dynamic Prompts variants, variables, or `$$` multi-selection grammar.
- Kept custom Dynamic Prompts delimiter conflict detection fail-closed when a relevant raw Sequential prompt overlaps a user-configured delimiter.

### Forge Neo upstream contracts

- Re-audited against Forge Neo `neo` commit `d2c29a6bc6cf834c83cdefed394062c2c3e58760`.
- Added CI contract tests for process/init/batch/Extra Network order, Forge's callback exception catcher, Hires prompt arrays and Hires output root, save callback order, batch-index save identity, and Prompt Matrix raw-pipe behavior.
- Added a pinned sd-dynamic-prompts extension contract at `de056ff8d80e4ad120e13a90cf200f3383f427c6`.

### CI and documentation

- Expanded CI from two Python 3.13 jobs to Ubuntu/Windows across Python 3.10, 3.11, and 3.13.
- Pinned `dynamicprompts==0.31.0` for reproducible compatibility testing.
- Updated GitHub Actions to the current Node 24-based checkout/setup-python v7 releases, pinned by commit SHA; restricted workflow permissions to read-only contents and added a per-job timeout.
- Rewrote README around the v0.6.1 syntax, lifecycle guarantees, Dynamic Prompts coexistence, LoRA/Hires behavior, folder routing, migration, and troubleshooting boundaries.
- Added a full [`AUDIT.md`](AUDIT.md) describing verified upstream assumptions, fixes, automated coverage, and the remaining real-GPU/UI smoke-test boundary.

## v0.6.0 — Dynamic Prompts-compatible syntax

- Replaced `$A|B|C$` with `==A|B|C==` for normal deterministic sequencing.
- Replaced `$$A|B|C$$` with `===A|B|C===` for sequence-driven output-folder routing.
- Made `$...$` / `$$...$$` literal so Sequential Prompts no longer claims syntax used by Dynamic Prompts variables and multi-selection grammar.
- Preserved Dynamic Prompts `{...}`, `__wildcard__`, `${...}`, `%{...}`, and `$$` constructs as independent syntax.
- Added conflict detection for manually configured Dynamic Prompts delimiters that overlap `==` / `===`.
- Added real `dynamicprompts~=0.31.0` generator tests on Ubuntu and Windows.
- Added comparison-like false-positive protection and initial malformed-equals handling.
- Updated UI help, metadata, documentation, and versioning.

## v0.5.1 — batch-friendly defaults

- Enabled Sequential Prompts by default while keeping prompts with no Sequential syntax as a behavioral no-op.
- Changed the default grouping to one choice per batch (`AAA -> BBB -> CCC`).
- Kept per-image `ABC` mode available.
- Renamed and clarified the repeat control.
- Moved start index, Loop/Clamp, and negative-prompt processing into Advanced settings.

## v0.5.0 — `$` syntax and Forge lifecycle hardening

- Introduced `$A|B|C$` and `$$A|B|C$$` syntax. These delimiters were later retired in v0.6.0 because they overlap Dynamic Prompts grammar.
- Added parser escaping and protected Forge Extra Network/bracket constructs.
- Moved final activation behind all `process()` callbacks using a one-shot `p.init` gate.
- Added frozen batch identity, Hires-array synchronization, shallow-copy/reuse hardening, and a core preparse backstop.
- Added LoRA consistency protection and initial Dynamic Prompts conflict detection.
- Added identity-based output routing, path sanitization, destination numbering, and exclusions for grids/Hires intermediates/video frames.
- Added explicit Prompt Matrix, SD Upscale, and multi-frame Wan guards.

## v0.4.1 — equals-syntax audit

- Hardened the original `=...=` / `==...==` parser against attached `key=value` false positives.
- Improved routing-state reset, grid detection, path containment, and documentation.

## v0.4.0 — output folders

- Added choice-based output folders using the then-current `==...==` marker.

## Earlier releases

The earliest versions used `[[...]]` and later single-equals syntax while the Forge Neo lifecycle and routing model were being established. Those historical syntaxes are no longer accepted by current releases.
