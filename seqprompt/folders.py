from __future__ import annotations

import hashlib
import os
import re
import threading
from pathlib import Path
from typing import Any, Iterable

_INVALID_WINDOWS_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_WINDOWS_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
    "COM¹",
    "COM²",
    "COM³",
    "LPT¹",
    "LPT²",
    "LPT³",
}

# images.image_grid() and images.save_image() run synchronously on the same
# generation thread. A thread-local marker lets us identify the following grid
# save even when grids and samples share a directory and the filename pattern
# does not contain the word "grid".
_GRID_SAVE_STATE = threading.local()


def _truncate_with_hash(
    value: str,
    *,
    original: str,
    max_length: int,
    max_bytes: int,
) -> str:
    """Bound one filename component by characters and UTF-8 bytes."""
    max_length = max(int(max_length), 16)
    max_bytes = max(int(max_bytes), 32)

    encoded = value.encode("utf-8")
    if len(value) <= max_length and len(encoded) <= max_bytes:
        return value

    digest = hashlib.sha1(original.encode("utf-8")).hexdigest()[:8]
    suffix = f"__{digest}"
    char_budget = max(max_length - len(suffix), 1)
    byte_budget = max(max_bytes - len(suffix.encode("utf-8")), 1)

    prefix: list[str] = []
    used_bytes = 0
    for char in value:
        encoded_char = char.encode("utf-8")
        if len(prefix) >= char_budget or used_bytes + len(encoded_char) > byte_budget:
            break
        prefix.append(char)
        used_bytes += len(encoded_char)

    readable = "".join(prefix).rstrip(" ._")
    if not readable:
        readable = "choice"

    # The minimum budgets above make this fit for normal inputs, but keep the
    # fallback defensive in case callers provide unusually tiny custom limits.
    result = f"{readable}{suffix}"
    while len(result) > max_length or len(result.encode("utf-8")) > max_bytes:
        readable = readable[:-1].rstrip(" ._")
        if not readable:
            readable = "c"
            result = f"{readable}{suffix}"
            break
        result = f"{readable}{suffix}"

    return result


def sanitize_folder_component(
    value: str,
    *,
    max_length: int = 64,
    max_bytes: int = 180,
) -> str:
    """Convert a selected prompt choice into one safe directory component."""
    original = str(value).strip()
    cleaned = _INVALID_WINDOWS_CHARS_RE.sub("_", original)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = cleaned.strip(" ._")

    if not cleaned or cleaned in {".", ".."}:
        cleaned = "choice"

    # Windows treats reserved device names as special even with extensions.
    stem = cleaned.split(".", 1)[0].upper()
    if stem in _RESERVED_WINDOWS_NAMES:
        cleaned = f"_{cleaned}"

    cleaned = _truncate_with_hash(
        cleaned,
        original=original,
        max_length=max_length,
        max_bytes=max_bytes,
    )
    return cleaned or "choice"


def build_folder_name(
    choices: Iterable[str],
    *,
    component_max_length: int = 64,
    component_max_bytes: int = 180,
    total_max_length: int = 120,
    total_max_bytes: int = 220,
) -> str | None:
    """Combine all selected ``==...==`` values into a single safe folder name."""
    raw_choices = [str(choice) for choice in choices]
    if not raw_choices:
        return None

    components = [
        sanitize_folder_component(
            choice,
            max_length=component_max_length,
            max_bytes=component_max_bytes,
        )
        for choice in raw_choices
    ]
    combined = "__".join(components)
    raw = "\0".join(raw_choices)
    combined = _truncate_with_hash(
        combined,
        original=raw,
        max_length=total_max_length,
        max_bytes=total_max_bytes,
    )
    return combined


def remember_output_folder(p: Any, global_index: int, choices: Iterable[str]) -> str | None:
    """Store the folder selected for one generated image on the processing object."""
    folder = build_folder_name(choices)
    mapping = getattr(p, "_seqprompt_output_folders", None)
    if not isinstance(mapping, dict):
        mapping = {}
        p._seqprompt_output_folders = mapping

    if folder:
        mapping[int(global_index)] = folder
    else:
        mapping.pop(int(global_index), None)

    return folder


def _path_is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def reset_grid_save_marker() -> None:
    """Clear any pending grid-save marker for the current generation thread."""
    _GRID_SAVE_STATE.pending = False


def mark_next_grid_save(_params: Any = None, *, should_save: bool | None = None) -> None:
    """Mark the next image save on this thread as a Forge grid save."""
    if should_save is None:
        try:
            from modules import shared

            should_save = bool(getattr(shared.opts, "grid_save", False))
        except (AttributeError, ImportError):
            should_save = False

    _GRID_SAVE_STATE.pending = bool(should_save)


def _consume_grid_save_marker() -> bool:
    pending = bool(getattr(_GRID_SAVE_STATE, "pending", False))
    _GRID_SAVE_STATE.pending = False
    return pending


def _looks_like_grid_filename(filename: Path) -> bool:
    """Filename-only fallback for callers that bypass image_grid_callback()."""
    stem = filename.stem.lower()
    return stem == "grid" or stem.startswith("grid-") or stem.startswith("grid_")


def _forge_add_number_enabled() -> bool:
    try:
        from modules import shared

        return bool(getattr(shared.opts, "save_images_add_number", False))
    except (AttributeError, ImportError):
        return False


def _next_sequence_number(path: Path) -> int:
    """Mirror Forge's basename-empty sequence scan inside the routed folder."""
    result = -1
    try:
        entries = path.iterdir()
        for entry in entries:
            stem = entry.name.rsplit(".", 1)[0]
            first = stem.split("-", 1)[0]
            try:
                result = max(int(first), result)
            except ValueError:
                continue
    except OSError:
        return 0

    return result + 1


def _renumber_for_destination(
    source: Path,
    destination_dir: Path,
    *,
    add_number: bool | None = None,
) -> str:
    """Preserve Forge's ascending-number semantics after changing directories.

    Forge computes the numeric prefix in the original directory before the
    before_image_saved callback runs. Because routed images never land there,
    that original counter can otherwise remain at 00000 forever. Recompute the
    prefix against the actual destination folder when Forge numbering is on.
    """
    if add_number is None:
        add_number = _forge_add_number_enabled()
    if not add_number:
        return source.name

    match = re.match(r"^(\d{5,})(.*)$", source.name)
    if match is None:
        return source.name

    next_number = _next_sequence_number(destination_dir)
    width = max(len(match.group(1)), 5)
    return f"{next_number:0{width}d}{match.group(2)}"


def route_image_save(params: Any) -> None:
    """Forge Neo ``before_image_saved`` callback for ``==...==`` folders."""
    # image_grid_callback() runs immediately before Forge's grid save. Consume
    # this first so grid routing stays correct even with shared sample/grid dirs
    # and custom grid filename patterns.
    if _consume_grid_save_marker():
        return

    p = getattr(params, "p", None)
    if p is None or not getattr(p, "_seqprompt_folder_routing_enabled", False):
        return

    # Hires.fix can save first-pass intermediates before Forge sets batch_index
    # for final images. Skip those rather than risk putting them in a wrong folder.
    if getattr(p, "is_hr_pass", False):
        return

    try:
        batch_index = int(getattr(p, "batch_index"))
        iteration = int(getattr(p, "iteration", 0))
        batch_size = max(int(getattr(p, "batch_size", 1)), 1)
    except (TypeError, ValueError, AttributeError):
        return

    if batch_index < 0:
        return

    global_index = iteration * batch_size + batch_index
    mapping = getattr(p, "_seqprompt_output_folders", None)
    if not isinstance(mapping, dict):
        return

    folder = mapping.get(global_index)
    if not folder:
        return

    source = Path(getattr(params, "filename", ""))
    if not source.name or _looks_like_grid_filename(source):
        return

    destination_dir = source.parent / folder
    if not _path_is_under(destination_dir, source.parent):
        return

    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_name = _renumber_for_destination(source, destination_dir)
    params.filename = os.fspath(destination_dir / destination_name)
