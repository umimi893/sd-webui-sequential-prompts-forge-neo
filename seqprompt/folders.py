from __future__ import annotations

import hashlib
import os
import re
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
}


def sanitize_folder_component(value: str, *, max_length: int = 64) -> str:
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

    max_length = max(int(max_length), 16)
    if len(cleaned) > max_length:
        digest = hashlib.sha1(original.encode("utf-8")).hexdigest()[:8]
        keep = max_length - len(digest) - 2
        cleaned = f"{cleaned[:keep].rstrip(' ._')}__{digest}"

    return cleaned or "choice"


def build_folder_name(
    choices: Iterable[str],
    *,
    component_max_length: int = 64,
    total_max_length: int = 120,
) -> str | None:
    """Combine all selected ``==...==`` values into a single safe folder name."""
    raw_choices = [str(choice) for choice in choices]
    if not raw_choices:
        return None

    components = [
        sanitize_folder_component(choice, max_length=component_max_length)
        for choice in raw_choices
    ]
    combined = "__".join(components)

    total_max_length = max(int(total_max_length), 24)
    if len(combined) > total_max_length:
        raw = "\0".join(raw_choices)
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
        keep = total_max_length - len(digest) - 2
        combined = f"{combined[:keep].rstrip(' ._')}__{digest}"

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
    except (OSError, ValueError):
        return False


def _looks_like_grid_save(p: Any, filename: Path) -> bool:
    grid_root_value = getattr(p, "outpath_grids", None)
    sample_root_value = getattr(p, "outpath_samples", None)
    if not grid_root_value:
        return False

    grid_root = Path(grid_root_value)
    sample_root = Path(sample_root_value) if sample_root_value else None

    # When the roots are distinct, a filename under the grid root is definitely
    # a grid and must not be routed into one image's choice folder.
    if sample_root is None or grid_root.resolve() != sample_root.resolve():
        return _path_is_under(filename.parent, grid_root)

    # If samples and grids intentionally share a directory, Forge normally uses
    # the ``grid`` basename. Keep this heuristic deliberately narrow so a normal
    # sample filename containing a word such as ``my-grid-style`` is not skipped.
    stem = filename.stem.lower()
    return stem == "grid" or stem.startswith("grid-") or stem.startswith("grid_")


def route_image_save(params: Any) -> None:
    """Forge Neo ``before_image_saved`` callback for ``==...==`` folders."""
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
    if not source.name or _looks_like_grid_save(p, source):
        return

    destination_dir = source.parent / folder
    if not _path_is_under(destination_dir, source.parent):
        return

    destination_dir.mkdir(parents=True, exist_ok=True)
    params.filename = os.fspath(destination_dir / source.name)
