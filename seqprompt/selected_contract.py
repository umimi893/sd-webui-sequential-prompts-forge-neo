from __future__ import annotations

from typing import Any


def selected_script_conflict(
    title: str | None,
    *,
    raw_positive_had_sequence: bool,
    raw_negative_had_sequence: bool,
    current_has_sequence: bool,
    prompt_matrix_type: str | None = None,
) -> str | None:
    normalized = str(title or "").strip().casefold()

    if normalized == "prompt matrix":
        # Prompt Matrix consumes exactly one raw field before inner process_images().
        # Sequence introduced later by styles/other process callbacks is not consumed by it.
        target = str(prompt_matrix_type or "positive").strip().casefold()
        target_had_sequence = (
            raw_negative_had_sequence if target == "negative" else raw_positive_had_sequence
        )
        if target_had_sequence:
            return "Prompt Matrix consumes '|' from the selected raw prompt before core processing"
        return None

    if normalized == "sd upscale":
        if raw_positive_had_sequence or raw_negative_had_sequence or current_has_sequence:
            return "SD Upscale recursively processes tiles and saves a composite outside core"
        return None

    return None
