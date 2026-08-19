from __future__ import annotations

from typing import Any


def clear_save_state(p: Any) -> None:
    """Disable and clear run-private save routing state after a run or before reuse."""
    p._seqprompt_folder_routing_enabled = False
    p._seqprompt_output_folders = {}
    p._seqprompt_output_identities = {}
    p._seqprompt_folder_sources = {}


def finish_run_state(p: Any) -> None:
    """Called from Script.postprocess after Forge has completed all core/grid saves."""
    clear_save_state(p)
    p._seqprompt_blocked_reason = None
    p._seqprompt_frozen_layout = None


def begin_save_state(p: Any) -> None:
    """Always clear stale state before deciding whether the new job is active."""
    clear_save_state(p)


def is_multiframe_wan(p: Any, *, wan_mode: bool, model_is_wan: bool) -> bool:
    """Mirror the already-normalized Forge condition visible to Script.process()."""
    if not wan_mode or not model_is_wan:
        return False
    try:
        batch_size = p.batch_size.__index__()
    except (AttributeError, TypeError):
        return True  # malformed Wan state: do not pretend frame identity is known
    return batch_size > 1


def sequential_wan_conflict(
    p: Any,
    *,
    sequential_active: bool,
    wan_mode: bool,
    model_is_wan: bool,
) -> str | None:
    if not sequential_active:
        return None
    if is_multiframe_wan(p, wan_mode=wan_mode, model_is_wan=model_is_wan):
        return (
            "Sequential Prompts does not support multi-frame Wan/video jobs: "
            "Forge's batch axis represents video frames rather than independent image identities."
        )
    return None
