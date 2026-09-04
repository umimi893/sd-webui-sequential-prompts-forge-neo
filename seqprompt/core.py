from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import re


_EXTRA_NETWORK_AT_START_RE = re.compile(r"<(\w+):([^>]+)>")
_NORMAL_DELIMITER = "=="
_FOLDER_DELIMITER = "==="


def _extra_network_end(text: str, index: int) -> int | None:
    if index < 0 or index >= len(text) or text[index] != "<":
        return None
    match = _EXTRA_NETWORK_AT_START_RE.match(text, index)
    return match.end() if match is not None else None


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _balanced_group_end(text: str, index: int, opener: str, closer: str) -> int | None:
    if index < 0 or index >= len(text) or text[index] != opener or _is_escaped(text, index):
        return None
    depth = 0
    cursor = index
    while cursor < len(text):
        if text[cursor] == "\\":
            cursor += 2 if cursor + 1 < len(text) else 1
            continue
        char = text[cursor]
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return cursor + 1
        cursor += 1
    return None


def _atomic_span_end(text: str, index: int) -> int | None:
    end = _extra_network_end(text, index)
    if end is not None:
        return end
    if index < len(text) and text[index] == "[":
        return _balanced_group_end(text, index, "[", "]")
    if index < len(text) and text[index] == "{":
        return _balanced_group_end(text, index, "{", "}")
    if index < len(text) and text[index] == "(":
        return _balanced_group_end(text, index, "(", ")")
    return None


@dataclass(frozen=True)
class PromptResolution:
    text: str
    folder_choices: tuple[str, ...] = ()
    matched_blocks: int = 0


def split_choices(body: str) -> list[str]:
    choices: list[str] = []
    buffer: list[str] = []
    index = 0
    while index < len(body):
        atomic_end = _atomic_span_end(body, index)
        if atomic_end is not None:
            buffer.append(body[index:atomic_end])
            index = atomic_end
            continue
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


def _can_start_block(text: str, index: int, *, adjacent: bool = False) -> bool:
    if _is_escaped(text, index):
        return False
    if adjacent:
        return True
    if index <= 0:
        return True
    previous = text[index - 1]
    return not (previous.isalnum() or previous in {"_", "="})


def _can_end_block(text: str, delimiter_end: int) -> bool:
    if delimiter_end >= len(text):
        return True
    following = text[delimiter_end]
    return not (following.isalnum() or following in {"_", "="})


def _body_has_choice_separator(body: str) -> bool:
    index = 0
    while index < len(body):
        atomic_end = _atomic_span_end(body, index)
        if atomic_end is not None:
            index = atomic_end
            continue
        if body[index] == "|" and not _is_escaped(body, index):
            return True
        index += 1
    return False


def _equals_run_length(text: str, index: int) -> int:
    end = index
    while end < len(text) and text[end] == "=":
        end += 1
    return end - index


def _delimiter_at(text: str, index: int) -> tuple[str, bool] | None:
    run = _equals_run_length(text, index)
    if run == 3:
        return _FOLDER_DELIMITER, True
    if run == 2:
        return _NORMAL_DELIMITER, False
    return None


def _find_closing_equals(text: str, start: int, delimiter: str) -> int:
    cursor = start
    while cursor < len(text):
        atomic_end = _atomic_span_end(text, cursor)
        if atomic_end is not None:
            cursor = atomic_end
            continue
        if _is_escaped(text, cursor):
            cursor += 1
            continue

        if text[cursor] == "=":
            run = _equals_run_length(text, cursor)
            end = cursor + len(delimiter)
            if run == len(delimiter) and _can_end_block(text, end):
                return cursor
            # Adjacent blocks share one uninterrupted equals run, e.g.
            # ==A|B====C|D== (close == followed immediately by open ==).
            if run >= len(delimiter) + len(_NORMAL_DELIMITER):
                return cursor

        nested = _delimiter_at(text, cursor)
        if nested is not None and _can_start_block(text, cursor):
            return -2

        cursor += 1
    return -1


def _select_choice(
    body: str,
    sequence_index: int,
    end_mode: str,
    *,
    allow_single: bool = False,
) -> str | None:
    if not allow_single and not _body_has_choice_separator(body):
        return None
    choices = split_choices(body)
    if not choices or (len(choices) < 2 and not allow_single):
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
    if not text or "==" not in text:
        return PromptResolution(text)

    output: list[str] = []
    folder_choices: list[str] = []
    matched_blocks = 0
    index = 0
    adjacent_after_resolved_block = False

    while index < len(text):
        extra_end = _extra_network_end(text, index)
        if extra_end is not None:
            output.append(text[index:extra_end])
            index = extra_end
            adjacent_after_resolved_block = False
            continue

        if text[index] in {"[", "("}:
            closer = "]" if text[index] == "[" else ")"
            group_end = _balanced_group_end(text, index, text[index], closer)
            if group_end is not None:
                inner = resolve_sequential_blocks(
                    text[index + 1 : group_end - 1],
                    sequence_index,
                    end_mode,
                )
                output.append(text[index] + inner.text + closer)
                folder_choices.extend(inner.folder_choices)
                matched_blocks += inner.matched_blocks
                index = group_end
                adjacent_after_resolved_block = False
                continue

        if text[index] == "{":
            group_end = _balanced_group_end(text, index, "{", "}")
            if group_end is not None:
                output.append(text[index:group_end])
                index = group_end
                adjacent_after_resolved_block = False
                continue

        candidate = _delimiter_at(text, index)
        if candidate is not None and _can_start_block(
            text,
            index,
            adjacent=adjacent_after_resolved_block,
        ):
            delimiter, is_folder = candidate
            end = _find_closing_equals(text, index + len(delimiter), delimiter)
            if end == -2:
                return PromptResolution(text)
            if end >= 0:
                body = text[index + len(delimiter) : end].strip()
                selected = (
                    _select_choice(
                        body,
                        sequence_index,
                        end_mode,
                        allow_single=is_folder,
                    )
                    if body
                    else None
                )
                if selected is not None:
                    output.append(selected)
                    if is_folder:
                        folder_choices.append(selected)
                    matched_blocks += 1
                    index = end + len(delimiter)
                    adjacent_after_resolved_block = True
                    continue
                output.append(text[index : end + len(delimiter)])
                index = end + len(delimiter)
                adjacent_after_resolved_block = False
                continue

        if text[index] == "\\" and index + 1 < len(text) and text[index + 1] == "=":
            output.append("=")
            index += 2
            adjacent_after_resolved_block = False
            continue

        output.append(text[index])
        index += 1
        adjacent_after_resolved_block = False

    return PromptResolution("".join(output), tuple(folder_choices), matched_blocks)


def replace_sequential_blocks(text: str, sequence_index: int, end_mode: str = "loop") -> str:
    return resolve_sequential_blocks(text, sequence_index, end_mode).text


def sequence_index_for_image(
    image_index: int,
    batch_size: int,
    advance_mode: str,
    repeat_each: int,
    start_index: int,
) -> int:
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
    output: list[str] = []
    for image_index, prompt in enumerate(prompts):
        sequence_index = sequence_index_for_image(
            image_index,
            batch_size,
            advance_mode,
            repeat_each,
            start_index,
        )
        output.append(replace_sequential_blocks(prompt, sequence_index, end_mode))
    return output
