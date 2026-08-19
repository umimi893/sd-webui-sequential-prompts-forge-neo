from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .activation import (
    active_sources_are_mutable,
    scan_relevant_sources,
    unresolved_relevant_sequence_present,
)
from .batch_integration import (
    BatchIntegrationError,
    BatchResolutionResult,
    SequenceConfig,
    preflight_job_extra_networks,
    resolve_frozen_batch,
)
from .core import resolve_sequential_blocks, sequence_index_for_image
from .folders import remember_output_folder, remember_output_identity
from .lifecycle import (
    FrozenLayout,
    expected_batch_bounds,
    freeze_layout_after_init,
    install_one_shot_preparse_guard,
    validate_live_batch,
)


@dataclass(frozen=True)
class ActiveRunContract:
    layout: FrozenLayout
    active_sources: frozenset[str]
    config: SequenceConfig


def prepare_after_init(
    p: Any,
    *,
    config: SequenceConfig,
    known_networks: Mapping[str, str] | None = None,
) -> ActiveRunContract | None:
    """Activate only when final post-process arrays really contain $ syntax."""
    scan = scan_relevant_sources(
        p,
        apply_negative=config.apply_negative,
        resolve=lambda text, index: resolve_sequential_blocks(text, index, "loop"),
    )
    if not scan.active:
        return None
    if not active_sources_are_mutable(scan):
        names = ", ".join(source.name for source in scan.active_sources if not source.mutable)
        raise BatchIntegrationError(f"active Sequential sources are read-only: {names}")

    layout = freeze_layout_after_init(p)
    active_sources = frozenset(source.name for source in scan.active_sources)
    preflight_job_extra_networks(
        p,
        batch_size=layout.batch_size,
        config=config,
        resolve=resolve_sequential_blocks,
        sequence_index_for_image=sequence_index_for_image,
        known_networks=known_networks,
    )
    run = ActiveRunContract(layout=layout, active_sources=active_sources, config=config)
    p._seqprompt_active_run = run
    return run


def resolve_current_batch(
    p: Any,
    *,
    batch_number: int,
    run: ActiveRunContract,
    known_networks: Mapping[str, str] | None = None,
) -> BatchResolutionResult:
    start, expected_len = validate_live_batch(p, batch_number=batch_number)
    result = resolve_frozen_batch(
        p,
        batch_number=batch_number,
        start=start,
        expected_len=expected_len,
        batch_size=run.layout.batch_size,
        config=run.config,
        resolve=resolve_sequential_blocks,
        sequence_index_for_image=sequence_index_for_image,
        known_networks=known_networks,
        active_sources=run.active_sources,
    )

    folder_by_index = dict(result.folder_choices)
    for local_index in range(result.length):
        global_index = result.start + local_index
        remember_output_identity(
            p,
            global_index,
            prompt=p.prompts[local_index],
            negative_prompt=p.negative_prompts[local_index],
            seed=p.seeds[local_index],
            subseed=p.subseeds[local_index],
        )
        choices = folder_by_index.get(global_index)
        if choices:
            remember_output_folder(p, global_index, choices)

    return result


def preparse_is_clean(p: Any, *, batch_number: int, run: ActiveRunContract) -> bool:
    start, current_len = expected_batch_bounds(run.layout, batch_number)
    return not unresolved_relevant_sequence_present(
        p,
        apply_negative=run.config.apply_negative,
        resolve=lambda text, index: resolve_sequential_blocks(text, index, "loop"),
        current_start=start,
        current_len=current_len,
    )


def install_preparse_sentinel(p: Any, *, batch_number: int, run: ActiveRunContract) -> None:
    """Install core-level validation after every before_process_batch callback."""
    install_one_shot_preparse_guard(p)
    guarded = p.parse_extra_network_prompts

    def sentinel(*args: Any, **kwargs: Any) -> Any:
        # lifecycle guard is one-shot and restores the original before validation.
        # Let it run first; then verify no later callback reintroduced raw syntax.
        # We cannot call the lifecycle wrapper and then inspect because it invokes
        # Forge parse immediately. Instead perform the unresolved check before it.
        if not preparse_is_clean(p, batch_number=batch_number, run=run):
            p._seqprompt_blocked_reason = (
                "unresolved Sequential Prompts syntax remained after batch callbacks"
            )
        return guarded(*args, **kwargs)

    # Preserve the original marker installed by lifecycle; restore logic still owns it.
    p.parse_extra_network_prompts = sentinel
