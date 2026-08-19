# Changelog

## v0.5.1

- Sequential Prompts is enabled by default. Plain prompts remain unaffected when no `$...$` or `$$...$$` syntax is present.
- The default grouping is now **one choice per batch** (`AAA → BBB → CCC`).
- The per-image `ABC` mode remains available for mixed choices inside a batch.
- Renamed the repeat control to **Hold each choice for N images / batches** and clarified what large values such as 150 mean.
- Moved Start index, Loop/Clamp, and negative-prompt processing into **Advanced settings**.
- Simplified the public documentation around validation and release history.

## v0.5.0 — initial public release

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

- Release contract tests run on Ubuntu and Windows with Python 3.13.

## v0.4.1

- Hardened equals-syntax parser, routing reset behavior, grid detection and documentation.

## v0.4.0

- Added choice-based output folders with `==...==`.
