from __future__ import annotations

import hashlib
import inspect
import ntpath
import os
import re
from dataclasses import dataclass
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
    windows_reserved = stem in _RESERVED_WINDOWS_NAMES
    if hasattr(ntpath, "isreserved"):
        windows_reserved = windows_reserved or bool(ntpath.isreserved(cleaned))
    if windows_reserved:
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


@dataclass(frozen=True)
class ForgeSaveContext:
    """Relevant locals from the active Forge Neo ``images.save_image`` call."""

    grid: bool | None = None
    add_number: bool | None = None
    basename: str = ""
    forced_filename: Any = None


def _forge_save_context() -> ForgeSaveContext | None:
    """Read the active Forge ``images.save_image`` call synchronously.

    ``before_image_saved`` is invoked from inside ``images.save_image``. Current
    Forge Neo therefore still has the exact ``grid`` and computed ``add_number``
    locals on the stack when this callback runs. Reading those values avoids
    guessing from filenames/paths and avoids global/thread-local grid markers
    that can be confused by live-preview grids or other extensions.

    The helper is deliberately defensive: if Forge changes this implementation
    detail later, callers fall back to conservative path/filename heuristics.
    """
    frame = inspect.currentframe()
    try:
        frame = frame.f_back if frame is not None else None
        for _ in range(12):
            if frame is None:
                break

            code = frame.f_code
            filename = code.co_filename.replace("\\", "/")
            if code.co_name == "save_image" and filename.endswith("/modules/images.py"):
                local_values = frame.f_locals
                grid = local_values.get("grid")
                add_number = local_values.get("add_number")
                return ForgeSaveContext(
                    grid=grid if isinstance(grid, bool) else None,
                    add_number=add_number if isinstance(add_number, bool) else None,
                    basename=str(local_values.get("basename", "") or ""),
                    forced_filename=local_values.get("forced_filename"),
                )

            frame = frame.f_back

        return None
    finally:
        # Break the reference cycle created by frame objects.
        del frame


def _looks_like_grid_filename(filename: Path) -> bool:
    """Filename-only fallback for callers that bypass image_grid_callback()."""
    stem = filename.stem.lower()
    return stem == "grid" or stem.startswith("grid-") or stem.startswith("grid_")


def _looks_like_grid_save(p: Any, filename: Path) -> bool:
    """Use output roots first, then the conservative grid filename fallback."""
    grid_root_value = getattr(p, "outpath_grids", None)
    sample_root_value = getattr(p, "outpath_samples", None)

    if grid_root_value:
        grid_root = Path(grid_root_value)
        sample_root = Path(sample_root_value) if sample_root_value else None
        under_grid = _path_is_under(filename.parent, grid_root)
        under_sample = bool(sample_root and _path_is_under(filename.parent, sample_root))

        if under_grid and not under_sample:
            return True
        if under_sample and not under_grid:
            return False

        if under_grid and under_sample and sample_root is not None:
            # When roots are nested, the more specific configured root tells us
            # which output family owns this path. When they are the same root,
            # an unknown/partial Forge save context is genuinely ambiguous; fail
            # closed and skip routing rather than risk moving a grid.
            try:
                grid_resolved = grid_root.resolve()
                sample_resolved = sample_root.resolve()
                if grid_resolved == sample_resolved:
                    return True
                try:
                    sample_resolved.relative_to(grid_resolved)
                    return False  # sample root is the deeper/more-specific root
                except ValueError:
                    pass
                try:
                    grid_resolved.relative_to(sample_resolved)
                    return True  # grid root is the deeper/more-specific root
                except ValueError:
                    pass
            except (OSError, RuntimeError, ValueError):
                return True

            return True

    return _looks_like_grid_filename(filename)


def _forge_add_number_enabled() -> bool:
    try:
        from modules import shared

        return bool(getattr(shared.opts, "save_images_add_number", False))
    except (AttributeError, ImportError):
        return False


def _forge_forced_empty_pattern_numbering(p: Any, source: Path) -> bool:
    """Detect Forge's ``file_decoration == ""`` forced-number case.

    ``save_image`` forces numbering when the *rendered* filename decoration is
    empty even if the global add-number option is off. For normal generated
    samples, an explicit empty ``samples_filename_pattern`` override is the
    practical way to reach that branch. Restrict this inference to a pure
    numeric filename so ordinary numeric seed-based patterns are not mistaken
    for sequence counters.
    """
    overrides = getattr(p, "override_settings", None)
    if not isinstance(overrides, dict) or overrides.get("samples_filename_pattern", object()) != "":
        return False

    return bool(re.fullmatch(r"\d{5,}", source.stem))


def _next_sequence_number(path: Path, basename: str = "") -> int:
    """Mirror Forge Neo's ``get_next_sequence_number`` for one destination."""
    result = -1
    prefix = f"{basename}-" if basename else ""
    prefix_length = len(prefix)

    try:
        entries = path.iterdir()
        for entry in entries:
            name = entry.name
            if not name.startswith(prefix):
                continue

            stem = os.path.splitext(name[prefix_length:])[0]
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
    p: Any = None,
    add_number: bool | None = None,
    basename: str = "",
) -> str:
    """Preserve Forge's ascending-number semantics after changing directories."""
    if add_number is None:
        add_number = _forge_add_number_enabled()
        if not add_number:
            add_number = _forge_forced_empty_pattern_numbering(p, source)

    # When Forge did not number this save (for example a forced/custom filename),
    # preserve its configured Override/Number-Suffix collision behavior exactly.
    if not add_number:
        return source.name

    if basename:
        match = re.match(
            rf"^{re.escape(basename)}-(\d{{4,}})(.*)$",
            source.name,
        )
        minimum_width = 4
    else:
        match = re.match(r"^(\d{5,})(.*)$", source.name)
        minimum_width = 5

    if match is None:
        return source.name

    next_number = _next_sequence_number(destination_dir, basename)
    width = max(len(match.group(1)), minimum_width)
    if basename:
        return f"{basename}-{next_number:0{width}d}{match.group(2)}"
    return f"{next_number:0{width}d}{match.group(2)}"


def _fit_folder_for_forge_post_callback(source: Path, folder: str) -> str | None:
    """Keep Forge's post-callback full-path truncation from cutting a directory.

    Current Forge Neo applies ``f_namemax`` to the entire post-callback path
    string on platforms exposing ``os.statvfs``. If adding our folder pushes the
    directory portion past that character boundary, Forge can slice through the
    directory name and then try to save into a path that was never created.

    Only shorten the extension-added folder enough to leave the complete parent
    directory, both separators, and a useful filename prefix intact (the whole
    stem when short, otherwise at least 32 characters). If the original Forge
    parent is already too long to leave that budget, skip routing rather than
    turn a successful original save into a failure or collision-prone name.
    """
    if not hasattr(os, "statvfs"):
        return folder

    try:
        max_name_len = int(os.statvfs(source.parent).f_namemax)
    except (AttributeError, OSError, TypeError, ValueError):
        return folder

    extension = source.suffix
    forge_limit = max_name_len - max(4, len(extension))
    parent_length = len(os.fspath(source.parent))

    # Preserve a useful prefix of Forge's filename as well as the complete
    # added directory. Without this budget, a very long existing parent path
    # could leave Forge only one filename character after its full-path slice,
    # increasing collision/overwrite risk. Preserve the whole stem when short,
    # otherwise at least the first 32 characters (typically including Forge's
    # numeric prefix and a useful part of the decoration).
    filename_budget = min(max(len(source.stem), 1), 32)
    # parent/folder/filename-prefix
    max_folder_length = forge_limit - parent_length - 2 - filename_budget
    if max_folder_length <= 0:
        return None
    if len(folder) <= max_folder_length:
        return folder

    digest = hashlib.sha1(folder.encode("utf-8")).hexdigest()[:8]
    if max_folder_length <= len(digest):
        return digest[:max_folder_length]

    suffix = f"__{digest}"
    if max_folder_length <= len(suffix):
        return digest[:max_folder_length]

    readable = folder[: max_folder_length - len(suffix)].rstrip(" ._")
    if not readable:
        return digest[:max_folder_length]
    return f"{readable}{suffix}"


def route_image_save(params: Any) -> None:
    """Forge Neo ``before_image_saved`` callback for ``==...==`` folders."""
    # Be idempotent if hot reload or an unusual caller invokes our callback more
    # than once for the same ImageSaveParams object.
    if bool(getattr(params, "_seqprompt_save_handled", False)):
        return

    save_context = _forge_save_context()
    if save_context is not None and save_context.grid is True:
        params._seqprompt_save_handled = True
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
    if not source.name:
        return
    if (save_context is None or save_context.grid is None) and _looks_like_grid_save(p, source):
        # A future Forge refactor may leave the synchronous save_image frame in
        # place while renaming/removing its local ``grid`` variable. Treat a
        # partial context as unknown and fall back conservatively instead of
        # assuming it is a sample.
        params._seqprompt_save_handled = True
        return

    fitted_folder = _fit_folder_for_forge_post_callback(source, folder)
    if not fitted_folder:
        return

    destination_dir = source.parent / fitted_folder
    if not _path_is_under(destination_dir, source.parent):
        return

    destination_dir.mkdir(parents=True, exist_ok=True)
    context_add_number = None
    context_basename = ""
    if save_context is not None:
        context_basename = save_context.basename
        if save_context.forced_filename is not None:
            # Forge bypasses its numbering branch entirely for forced filenames.
            context_add_number = False
        else:
            context_add_number = save_context.add_number

    destination_name = _renumber_for_destination(
        source,
        destination_dir,
        p=p,
        add_number=context_add_number,
        basename=context_basename,
    )
    params.filename = os.fspath(destination_dir / destination_name)
    params._seqprompt_save_handled = True
