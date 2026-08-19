from __future__ import annotations

import hashlib
import inspect
import json
import ntpath
import os
import re
import unicodedata
from dataclasses import dataclass
from operator import index as integer_index
from pathlib import Path
from typing import Any, Iterable

_INVALID_WINDOWS_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_WINDOWS_NAMES = {
    "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
    "COM¹", "COM²", "COM³", "LPT¹", "LPT²", "LPT³",
}
_BIDI_CONTROL_CHARS = {
    "\u061c", "\u200e", "\u200f", "\u202a", "\u202b", "\u202c",
    "\u202d", "\u202e", "\u2066", "\u2067", "\u2068", "\u2069",
}


class SaveRoutingInvariantError(RuntimeError):
    pass


@dataclass(frozen=True)
class SaveLayout:
    batch_size: int
    total: int


@dataclass(frozen=True)
class ForgeSaveContext:
    grid: bool | None
    add_number: bool | None
    basename: str
    forced_filename: Any
    core_processing_save: bool
    core_video: bool


def _strict_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool):
        raise SaveRoutingInvariantError(f"{label} is not an integer")
    try:
        return integer_index(value)
    except TypeError as exc:
        raise SaveRoutingInvariantError(f"{label} is not an integer") from exc


def _choice_source_text(choices: Iterable[str]) -> str:
    return json.dumps([str(x) for x in choices], ensure_ascii=True, separators=(",", ":"))


def _truncate_with_hash(value: str, *, original: str, max_length: int, max_bytes: int) -> str:
    max_length = max(int(max_length), 1)
    max_bytes = max(int(max_bytes), 1)
    encoded = value.encode("utf-8", errors="replace")
    if len(value) <= max_length and len(encoded) <= max_bytes:
        return value
    digest = hashlib.sha256(original.encode("utf-8", errors="replace")).hexdigest()[:12]
    suffix = f"__{digest}"
    suffix_bytes = len(suffix.encode("utf-8"))
    if len(suffix) >= max_length or suffix_bytes >= max_bytes:
        return digest[: max(1, min(max_length, max_bytes, len(digest)))]
    char_budget = max_length - len(suffix)
    byte_budget = max_bytes - suffix_bytes
    chars: list[str] = []
    used = 0
    for char in value:
        part = char.encode("utf-8", errors="replace")
        if len(chars) >= char_budget or used + len(part) > byte_budget:
            break
        chars.append(char)
        used += len(part)
    readable = "".join(chars).rstrip(" ._")
    if not readable:
        return digest[: max(1, min(max_length, max_bytes, len(digest)))]
    return f"{readable}{suffix}"


def sanitize_folder_component(value: str, *, max_length: int = 64, max_bytes: int = 180) -> str:
    raw = unicodedata.normalize("NFC", str(value).strip())
    cleaned_chars: list[str] = []
    for ch in raw:
        if unicodedata.category(ch) in {"Cc", "Cs"} or ch in _BIDI_CONTROL_CHARS:
            cleaned_chars.append("_")
        else:
            cleaned_chars.append(ch)
    cleaned = _INVALID_WINDOWS_CHARS_RE.sub("_", "".join(cleaned_chars))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"_+", "_", cleaned).strip(" ._")
    if not cleaned or cleaned in {".", ".."}:
        cleaned = "empty" if raw == "" else "choice"
    stem = cleaned.split(".", 1)[0].upper()
    reserved = stem in _RESERVED_WINDOWS_NAMES
    if hasattr(ntpath, "isreserved"):
        try:
            reserved = reserved or bool(ntpath.isreserved(cleaned))
        except (TypeError, ValueError):
            pass
    if reserved:
        cleaned = f"_{cleaned}"
    return _truncate_with_hash(cleaned, original=raw, max_length=max_length, max_bytes=max_bytes) or "choice"


def build_folder_name(
    choices: Iterable[str],
    *,
    component_max_length: int = 64,
    component_max_bytes: int = 180,
    total_max_length: int = 120,
    total_max_bytes: int = 220,
) -> str | None:
    raw_choices = [unicodedata.normalize("NFC", str(x)) for x in choices]
    if not raw_choices:
        return None
    parts = [sanitize_folder_component(x, max_length=component_max_length, max_bytes=component_max_bytes) for x in raw_choices]
    combined = "__".join(parts)
    source = _choice_source_text(raw_choices)
    lossy = any(part != raw.strip() for raw, part in zip(raw_choices, parts))
    if lossy:
        digest = hashlib.sha256(source.encode("utf-8", errors="replace")).hexdigest()[:8]
        combined = f"{combined}__{digest}"
    return _truncate_with_hash(combined, original=source, max_length=total_max_length, max_bytes=total_max_bytes)


def remember_output_folder(p: Any, global_index: int, choices: Iterable[str]) -> str | None:
    raw_choices = tuple(unicodedata.normalize("NFC", str(x)) for x in choices)
    folder = build_folder_name(raw_choices)
    mapping = getattr(p, "_seqprompt_output_folders", None)
    if not isinstance(mapping, dict):
        mapping = {}
        p._seqprompt_output_folders = mapping
    if not folder:
        mapping.pop(int(global_index), None)
        return None
    registry = getattr(p, "_seqprompt_folder_sources", None)
    if not isinstance(registry, dict):
        registry = {}
        p._seqprompt_folder_sources = registry
    key = folder.casefold()
    existing = registry.get(key)
    if existing is not None and existing != raw_choices:
        source = _choice_source_text(raw_choices)
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
        folder = _truncate_with_hash(f"{folder}__{digest}", original=source, max_length=120, max_bytes=220)
        key = folder.casefold()
    registry[key] = raw_choices
    mapping[_strict_int(global_index, label="global_index")] = folder
    p._seqprompt_folder_routing_enabled = True
    return folder


def _canonical_prompt(value: Any) -> str:
    return str(value)


def remember_output_identity(p: Any, global_index: int, *, prompt: Any, negative_prompt: Any, seed: Any, subseed: Any) -> None:
    identities = getattr(p, "_seqprompt_output_identities", None)
    if not isinstance(identities, dict):
        identities = {}
        p._seqprompt_output_identities = identities
    identities[_strict_int(global_index, label="global_index")] = (_canonical_prompt(prompt), str(negative_prompt), seed, subseed)


def _current_identity(p: Any, batch_index: int) -> tuple[Any, ...] | None:
    arrays = []
    for name in ("prompts", "negative_prompts", "seeds", "subseeds"):
        values = getattr(p, name, None)
        if not isinstance(values, (list, tuple)) or not (0 <= batch_index < len(values)):
            return None
        arrays.append(values)
    return (_canonical_prompt(arrays[0][batch_index]), str(arrays[1][batch_index]), arrays[2][batch_index], arrays[3][batch_index])


def _frozen_layout(p: Any) -> SaveLayout | None:
    layout = getattr(p, "_seqprompt_frozen_layout", None)
    if layout is None:
        return None
    try:
        batch_size = _strict_int(getattr(layout, "batch_size"), label="frozen batch_size")
        total = _strict_int(getattr(layout, "total"), label="frozen total")
    except (AttributeError, SaveRoutingInvariantError):
        return None
    if batch_size < 1 or total < 1:
        return None
    return SaveLayout(batch_size, total)


def _folder_for_live_slot(p: Any, *, iteration: int, batch_index: int) -> str | None:
    layout = _frozen_layout(p)
    if layout is None or iteration < 0 or batch_index < 0 or batch_index >= layout.batch_size:
        return None
    batch_start = iteration * layout.batch_size
    global_index = batch_start + batch_index
    if global_index >= layout.total:
        return None
    mapping = getattr(p, "_seqprompt_output_folders", None)
    identities = getattr(p, "_seqprompt_output_identities", None)
    if not isinstance(mapping, dict) or not isinstance(identities, dict):
        return None
    current = _current_identity(p, batch_index)
    if current is None:
        return None
    expected_len = min(layout.batch_size, max(layout.total - batch_start, 0))
    outcomes = {mapping.get(index) for index in range(batch_start, batch_start + expected_len) if identities.get(index) == current}
    if len(outcomes) != 1:
        return None
    return next(iter(outcomes))


def _path_is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def _code_filename_matches(filename: str, module_path: str) -> bool:
    value = str(filename).replace("\\", "/").casefold().lstrip("./")
    target = module_path.replace("\\", "/").casefold().lstrip("./")
    return value == target or value.endswith(f"/{target}")


def forge_save_context() -> ForgeSaveContext | None:
    frame = inspect.currentframe()
    try:
        frame = frame.f_back if frame is not None else None
        for _ in range(14):
            if frame is None:
                return None
            code = frame.f_code
            if code.co_name == "save_image" and _code_filename_matches(code.co_filename, "modules/images.py"):
                local_values = frame.f_locals
                caller = frame.f_back
                direct_core = bool(caller is not None and caller.f_code.co_name == "process_images_inner" and _code_filename_matches(caller.f_code.co_filename, "modules/processing.py"))
                return ForgeSaveContext(
                    grid=local_values.get("grid") if isinstance(local_values.get("grid"), bool) else None,
                    add_number=local_values.get("add_number") if isinstance(local_values.get("add_number"), bool) else None,
                    basename=str(local_values.get("basename", "") or ""),
                    forced_filename=local_values.get("forced_filename"),
                    core_processing_save=direct_core,
                    core_video=bool(caller and caller.f_locals.get("_is_video", False)) if direct_core else False,
                )
            frame = frame.f_back
        return None
    finally:
        del frame


def _next_sequence_number(path: Path, basename: str = "") -> int | None:
    result = -1
    prefix = f"{basename}-" if basename else ""
    try:
        for entry in path.iterdir():
            if not entry.name.startswith(prefix):
                continue
            stem = os.path.splitext(entry.name[len(prefix):])[0]
            first = stem.split("-", 1)[0]
            try:
                result = max(result, int(first))
            except ValueError:
                pass
    except OSError:
        return None
    return result + 1


def _renumber_for_destination(source: Path, destination: Path, *, context: ForgeSaveContext) -> str | None:
    if context.forced_filename is not None:
        return source.name
    if context.add_number is False:
        return source.name
    if context.add_number is not True:
        return None
    if context.basename:
        match = re.match(rf"^{re.escape(context.basename)}-(\d{{4,}})(.*)$", source.name)
        minimum_width = 4
    else:
        match = re.match(r"^(\d{5,})(.*)$", source.name)
        minimum_width = 5
    if match is None:
        return None
    number = _next_sequence_number(destination, context.basename)
    if number is None:
        return None
    width = max(minimum_width, len(match.group(1)))
    if context.basename:
        return f"{context.basename}-{number:0{width}d}{match.group(2)}"
    return f"{number:0{width}d}{match.group(2)}"


def _fit_for_forge_posix_slice(source: Path, folder: str, *, preserve_full_filename: bool) -> str | None:
    if not hasattr(os, "statvfs"):
        return folder
    try:
        max_name_len = int(os.statvfs(source.parent).f_namemax)
    except (AttributeError, OSError, TypeError, ValueError):
        return folder
    forge_limit = max_name_len - max(4, len(source.suffix))
    parent_length = len(os.fspath(source.parent))
    filename_budget = max(len(source.stem), 1) if preserve_full_filename else min(max(len(source.stem), 1), 32)
    folder_budget = forge_limit - parent_length - filename_budget - 2
    if folder_budget <= 0:
        return None
    if len(folder) <= folder_budget:
        return folder
    return _truncate_with_hash(folder, original=folder, max_length=folder_budget, max_bytes=220)


def _windows_units(value: os.PathLike[str] | str) -> int:
    return len(os.fspath(value).encode("utf-16-le", errors="surrogatepass")) // 2


def _fit_for_windows_path(source: Path, folder: str, *, limit: int = 248) -> str | None:
    absolute = source if source.is_absolute() else Path.cwd() / source
    if _windows_units(absolute) > limit:
        return None
    budget = limit - _windows_units(absolute.parent) - _windows_units(absolute.name) - 2
    if budget <= 0:
        return None
    if _windows_units(folder) <= budget:
        return folder
    digest = hashlib.sha256(folder.encode("utf-8", errors="replace")).hexdigest()[:12]
    suffix = f"__{digest}"
    if budget <= len(digest):
        return digest[:budget]
    chars: list[str] = []
    used = 0
    for ch in folder:
        units = _windows_units(ch)
        if used + units > budget - len(suffix):
            break
        chars.append(ch)
        used += units
    readable = "".join(chars).rstrip(" ._")
    return f"{readable}{suffix}" if readable else digest[:budget]


def _fit_folder_for_platform(source: Path, folder: str, *, preserve_full_filename: bool) -> str | None:
    fitted = _fit_for_forge_posix_slice(source, folder, preserve_full_filename=preserve_full_filename)
    if not fitted:
        return None
    if os.name == "nt":
        return _fit_for_windows_path(source, fitted)
    return fitted


def route_with_context(params: Any, context: ForgeSaveContext | None) -> bool:
    if bool(getattr(params, "_seqprompt_save_handled", False)):
        return False
    p = getattr(params, "p", None)
    if p is None or not bool(getattr(p, "_seqprompt_folder_routing_enabled", False)):
        return False
    if getattr(p, "_seqprompt_owner_id", id(p)) != id(p):
        return False
    if context is None or not context.core_processing_save or context.core_video:
        return False
    if context.grid is not False:
        params._seqprompt_save_handled = True
        return False
    if context.forced_filename is None and context.add_number is None:
        return False
    if bool(getattr(p, "is_hr_pass", False)):
        return False
    try:
        iteration = _strict_int(getattr(p, "iteration"), label="iteration")
        batch_index = _strict_int(getattr(p, "batch_index"), label="batch_index")
    except (AttributeError, SaveRoutingInvariantError):
        return False
    folder = _folder_for_live_slot(p, iteration=iteration, batch_index=batch_index)
    if not folder:
        return False
    try:
        source = Path(getattr(params, "filename"))
    except (AttributeError, TypeError, ValueError, OSError):
        return False
    if not source.name:
        return False
    sample_root_value = getattr(p, "outpath_samples", None)
    if not sample_root_value:
        return False
    try:
        sample_root = Path(sample_root_value)
    except (TypeError, ValueError, OSError):
        return False
    if not _path_is_under(source.parent, sample_root):
        return False
    preserve_full = context.forced_filename is not None or context.add_number is not True
    folder = _fit_folder_for_platform(source, folder, preserve_full_filename=preserve_full)
    if not folder:
        return False
    destination = source.parent / folder
    if not _path_is_under(destination, source.parent):
        return False
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    if not _path_is_under(destination, source.parent):
        return False
    destination_name = _renumber_for_destination(source, destination, context=context)
    if destination_name is None:
        return False
    params.filename = os.fspath(destination / destination_name)
    params._seqprompt_save_handled = True
    return True


def route_image_save(params: Any) -> None:
    route_with_context(params, forge_save_context())
