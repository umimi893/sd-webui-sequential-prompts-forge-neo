from __future__ import annotations

from typing import Any

from .core import replace_sequential_blocks, sequence_index_for_image


def _replace_at(
    values: list[str],
    index: int,
    *,
    sequence_index: int,
    end_mode: str,
) -> str | None:
    if index < 0 or index >= len(values):
        return None

    resolved = replace_sequential_blocks(
        values[index],
        sequence_index=sequence_index,
        end_mode=end_mode,
    )
    values[index] = resolved
    return resolved


def apply_processing_batch(
    p: Any,
    *,
    batch_number: int,
    advance_mode: str,
    repeat_each: int,
    start_index: int,
    end_mode: str,
    apply_negative: bool,
) -> None:
    """Resolve sequential blocks for the actual Forge Neo batch about to run.

    This intentionally runs at batch time rather than process time so extensions
    that expand or replace prompt lists (for example Dynamic Prompts) get to run
    first. Forge Neo calls this hook before parsing Extra Networks, so selected
    choices may also contain LoRA / extra-network tags.
    """
    batch_size = max(int(getattr(p, "batch_size", 1)), 1)
    batch_number = max(int(batch_number), 0)
    repeat_each = max(int(repeat_each), 1)
    start_index = max(int(start_index), 0)

    batch_prompts = getattr(p, "prompts", None)
    all_prompts = getattr(p, "all_prompts", None)

    if isinstance(batch_prompts, list) and isinstance(all_prompts, list):
        for local_index in range(len(batch_prompts)):
            global_index = batch_number * batch_size + local_index
            sequence_index = sequence_index_for_image(
                image_index=global_index,
                batch_size=batch_size,
                advance_mode=advance_mode,
                repeat_each=repeat_each,
                start_index=start_index,
            )
            resolved = _replace_at(
                all_prompts,
                global_index,
                sequence_index=sequence_index,
                end_mode=end_mode,
            )
            if resolved is not None:
                batch_prompts[local_index] = resolved

    if apply_negative:
        batch_negative_prompts = getattr(p, "negative_prompts", None)
        all_negative_prompts = getattr(p, "all_negative_prompts", None)
        if isinstance(batch_negative_prompts, list) and isinstance(all_negative_prompts, list):
            for local_index in range(len(batch_negative_prompts)):
                global_index = batch_number * batch_size + local_index
                sequence_index = sequence_index_for_image(
                    image_index=global_index,
                    batch_size=batch_size,
                    advance_mode=advance_mode,
                    repeat_each=repeat_each,
                    start_index=start_index,
                )
                resolved = _replace_at(
                    all_negative_prompts,
                    global_index,
                    sequence_index=sequence_index,
                    end_mode=end_mode,
                )
                if resolved is not None:
                    batch_negative_prompts[local_index] = resolved

    # Forge Neo keeps Hires.fix prompts in separate arrays and slices them later
    # in parse_extra_network_prompts(). Resolve those arrays before that happens.
    all_hr_prompts = getattr(p, "all_hr_prompts", None)
    if isinstance(all_hr_prompts, list):
        batch_len = len(batch_prompts) if isinstance(batch_prompts, list) else batch_size
        for local_index in range(batch_len):
            global_index = batch_number * batch_size + local_index
            sequence_index = sequence_index_for_image(
                image_index=global_index,
                batch_size=batch_size,
                advance_mode=advance_mode,
                repeat_each=repeat_each,
                start_index=start_index,
            )
            _replace_at(
                all_hr_prompts,
                global_index,
                sequence_index=sequence_index,
                end_mode=end_mode,
            )

    if apply_negative:
        all_hr_negative_prompts = getattr(p, "all_hr_negative_prompts", None)
        if isinstance(all_hr_negative_prompts, list):
            batch_len = len(batch_prompts) if isinstance(batch_prompts, list) else batch_size
            for local_index in range(batch_len):
                global_index = batch_number * batch_size + local_index
                sequence_index = sequence_index_for_image(
                    image_index=global_index,
                    batch_size=batch_size,
                    advance_mode=advance_mode,
                    repeat_each=repeat_each,
                    start_index=start_index,
                )
                _replace_at(
                    all_hr_negative_prompts,
                    global_index,
                    sequence_index=sequence_index,
                    end_mode=end_mode,
                )

    if isinstance(all_prompts, list) and all_prompts:
        p.main_prompt = all_prompts[0]

    all_negative_prompts = getattr(p, "all_negative_prompts", None)
    if isinstance(all_negative_prompts, list) and all_negative_prompts:
        p.main_negative_prompt = all_negative_prompts[0]
