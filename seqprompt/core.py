from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class PromptResolution:
    text: str
    folder_choices: tuple[str, ...] = ()


def split_choices(body: str) -> list[str]:
    r"""Split ``A|B|C`` while supporting ``\|``, ``\\`` and ``\=`` escapes.

    A backslash only escapes ``|``, ``=`` or another backslash. Before any other
    character it is preserved literally so prompt text such as Windows paths
    is not silently modified.
    """
    choices: list[str] = []
    buffer: list[str] = []
    index = 0

    while index < len(body):
        char = body[index]

        if char == "\\":
            if index + 1 < len(body) and body[index + 1] in {"|", "=", "\\"}:
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


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _find_closing_double_equals(text: str, start: int) -> int:
    cursor = start
    while cursor < len(text) - 1:
        if text.startswith("==", cursor) and not _is_escaped(text, cursor):
            return cursor
        cursor += 1
    return -1


def _find_closing_single_equals(text: str, start: int) -> int:
    cursor = start
    while cursor < len(text):
        if text[cursor] != "=" or _is_escaped(text, cursor):
            cursor += 1
            continue

        # A doubled equals belongs to the explicit folder-marker syntax and is
        # never used as the closing delimiter for a normal =A|B= block.
        if (cursor + 1 < len(text) and text[cursor + 1] == "=") or (
            cursor > 0 and text[cursor - 1] == "="
        ):
            cursor += 1
            continue

        return cursor
    return -1


def _select_choice(body: str, sequence_index: int, end_mode: str) -> str | None:
    choices = split_choices(body)
    if len(choices) < 2:
        return None

    if end_mode == "clamp":
        choice_index = min(max(sequence_index, 0), len(choices) - 1)
    else:
        choice_index = sequence_index % len(choices)

    return choices[choice_index]


def resolve_sequential_blocks(
    text: str,
    sequence_index: int,
    end_mode: str = "loop",
) -> PromptResolution:
    """Resolve sequential prompt blocks and return folder-marker selections.

    Primary syntax:
        ``=A | B | C=`` resolves in sequence.

    Folder-marker syntax:
        ``==A | B | C==`` resolves in sequence and records the selected value
        for output-folder routing.

    Legacy compatibility syntax:
        ``[[A|B|C]]`` resolves in sequence but never controls folders.
    """
    if not text or "|" not in text:
        return PromptResolution(text)

    output: list[str] = []
    folder_choices: list[str] = []
    index = 0

    while index < len(text):
        if text.startswith("==", index) and not _is_escaped(text, index):
            end = _find_closing_double_equals(text, index + 2)
            if end >= 0:
                body = text[index + 2 : end]
                selected = _select_choice(body, sequence_index, end_mode)
                if selected is not None:
                    output.append(selected)
                    folder_choices.append(selected)
                    index = end + 2
                    continue

        if text.startswith("[[", index):
            end = text.find("]]", index + 2)
            if end >= 0:
                body = text[index + 2 : end]
                selected = _select_choice(body, sequence_index, end_mode)
                if selected is not None:
                    output.append(selected)
                    index = end + 2
                    continue

        if text[index] == "=" and not _is_escaped(text, index):
            is_double = index + 1 < len(text) and text[index + 1] == "="
            follows_double = index > 0 and text[index - 1] == "="
            if not is_double and not follows_double:
                end = _find_closing_single_equals(text, index + 1)
                if end >= 0:
                    body = text[index + 1 : end]
                    selected = _select_choice(body, sequence_index, end_mode)
                    if selected is not None:
                        output.append(selected)
                        index = end + 1
                        continue

        output.append(text[index])
        index += 1

    return PromptResolution("".join(output), tuple(folder_choices))


def replace_sequential_blocks(
    text: str,
    sequence_index: int,
    end_mode: str = "loop",
) -> str:
    """Resolve sequential blocks and return only the resulting prompt text."""
    return resolve_sequential_blocks(text, sequence_index, end_mode).text


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
