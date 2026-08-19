# Changelog

## v0.5.0 — development

### Breaking syntax change

- New primary syntax: `$A|B|C$`.
- New folder-routing syntax: `$$A|B|C$$`.
- Removed compatibility parsing for `=...=`, `==...==`, `[[...]]`, and abandoned ampersand prototypes. They now remain literal prompt text.

### Parser

- Added `$`, `|`, and backslash escaping.
- Kept Forge Extra Network tags atomic.
- Protected Forge bracket/alternation syntax and Dynamic Prompts default brace syntax.
- Added adjacent-block handling, empty choices, malformed-input recovery, and fail-closed unsupported nesting.

### Forge lifecycle

- Freeze image layout after all `process()` callbacks via a one-shot `p.init` gate.
- Use frozen batch/total identity for sequencing and save routing.
- Validate prompt/negative/seed/subseed alignment and legitimate final partial batches.
- Added one-shot core preparse backstop because Forge catches always-on callback exceptions.
- Hardened shallow-copy/reuse state for X/Y/Z Plot and similar scripts.

### Integration

- Activation is a no-op when no final relevant Sequential syntax exists.
- Hires arrays are processed only when Hires is enabled.
- Added Dynamic Prompts `$`/`$$` delimiter conflict detection.
- Added late unresolved-syntax sentinel.
- Added batch-wide LoRA/Extra Network consistency protection only when Sequential itself creates the unsafe difference.

### Output folders

- Follow postprocess metadata identity instead of mutable slot indices.
- Recompute Forge numeric prefixes in the destination folder to prevent overwrite-prone repeated numbering.
- Route only positively identified core sample saves; grids, Hires intermediates, manual saves and video frames are excluded.
- Expanded Windows/Unicode/path sanitization and deterministic lossy-name disambiguation.
- Preserved Forge save-to-dirs and final Override/Number-Suffix policy.

### Special modes

- Explicitly reject relevant Prompt Matrix and SD Upscale combinations that cannot preserve the sequence contract.
- Reject active multi-frame Wan/video jobs; single-frame Wan remains supported.
- Sequence state restarts for each independent `process_images()` sub-run.

### Testing

- Rebuilt the production test suite from audited parser/lifecycle/integration/save prototypes.
- 304 detailed local audit checks were completed and preserved in the Git-invisible audit snapshot.
- The committed release CI suite contains 68 focused contract tests to keep routine CI maintainable.
- Ubuntu + Windows / Python 3.13 CI required before merge.

## v0.4.1

- Hardened equals-syntax parser, routing reset behavior, grid detection and documentation.

## v0.4.0

- Added choice-based output folders with `==...==`.
