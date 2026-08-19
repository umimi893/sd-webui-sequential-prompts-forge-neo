from __future__ import annotations

import re
from collections.abc import Iterable

_BLOCK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")


def split_choices(body: str) -> list[str]:
    r"""Split ``A|B|C`` while supporting ``\|`` and ``\\`` escapes.

    A backslash only escapes ``|`` or another backslash. Before any other
    character it is preserved literally so prompt text such as Windows paths
    is not silently modified.
    """
    choices: list[str] = []
    buffer: list[str] = []
    index = 0

    while index < len(body):
        char = body[index]

        if char == "\\":
            if index + 1 < len(body) and body[index + 1] in {"|", "\\"}:
                buffer.append(body[index + 1])
                index += 2
                continue

            buffer.append("\\")
            index += 1
            continue

        if char == "|":
            choices.append("".join(buffer).strip())
            buffer = []
        else:
            buffer.append(char)

        index += 1

    choices.append("".join(buffer).strip())
    return choices


def replace_sequential_blocks(
    text: str,
    sequence_index: int,
    end_mode: str = "loop",
) -> str:
    """Resolve every ``[[A|B|C]]`` block at one deterministic sequence index."""
    if not text or "[[" not in text:
        return text

    def replace(match: re.Match[str]) -> str:
        choices = split_choices(match.group(1))
        if not choices:
            return match.group(0)

        if end_mode == "clamp":
            choice_index = min(max(sequence_index, 0), len(choices) - 1)
        else:
            choice_index = sequence_index % len(choices)

        return choices[choice_index]

    return _BLOCK_RE.sub(replace, text)


def sequence_index_for_image(
    image_index: int,
    batch_size: int,
    advance_mode: str,
    repeat_each: int,
    start_index: int,
) -> int:
    """Return the sequence position for a global image index."""
    batch_size = max(int(batch_size), 1)
    repeat_each = max(int(repeat_each), 1)
    start_index = max(int(start_index), 0)

    if advance_mode == "batch":
        unit_index = image_index // batch_size
    else:
        unit_index = image_index

    return start_index + unit_index // repeat_each


def expand_prompt_series(
    prompts: Iterable[str],
    *,
    batch_size: int,
    advance_mode: str,
    repeat_each: int = 1,
    start_index: int = 0,
    end_mode: str = "loop",
) -> list[str]:
    """Resolve a complete Forge Neo ``all_prompts``-style prompt sequence."""
    output: list[str] = []
    for image_index, prompt in enumerate(prompts):
        sequence_index = sequence_index_for_image(
            image_index=image_index,
            batch_size=batch_size,
            advance_mode=advance_mode,
            repeat_each=repeat_each,
            start_index=start_index,
        )
        output.append(
            replace_sequential_blocks(
                prompt,
                sequence_index=sequence_index,
                end_mode=end_mode,
            )
        )
    return output
