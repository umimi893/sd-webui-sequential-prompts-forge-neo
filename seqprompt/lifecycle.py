from __future__ import annotations

from dataclasses import dataclass
from operator import index as integer_index
from typing import Any, Callable


class LifecycleInvariantError(RuntimeError):
    pass


@dataclass(frozen=True)
class FrozenLayout:
    batch_size: int
    total: int


def _strict_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool):
        raise LifecycleInvariantError(f"{label} is not an integer")
    try:
        return integer_index(value)
    except TypeError as exc:
        raise LifecycleInvariantError(f"{label} is not an integer") from exc


def _positive_int(value: Any, *, label: str) -> int:
    result = _strict_int(value, label=label)
    if result < 1:
        raise LifecycleInvariantError(f"{label} must be >= 1")
    return result


def _require_indexable_total(values: Any, total: int, *, label: str) -> None:
    if not isinstance(values, (list, tuple)):
        raise LifecycleInvariantError(f"{label} is not an indexable sequence")
    if len(values) != total:
        raise LifecycleInvariantError(f"{label} length changed or is misaligned ({len(values)} != {total})")


def freeze_layout_after_init(p: Any) -> FrozenLayout:
    batch_size = _positive_int(getattr(p, "batch_size", None), label="batch_size")
    all_prompts = getattr(p, "all_prompts", None)
    if not isinstance(all_prompts, (list, tuple)):
        raise LifecycleInvariantError("all_prompts is not an indexable sequence")
    total = len(all_prompts)
    if total < 1:
        raise LifecycleInvariantError("all_prompts must not be empty at init freeze")
    _require_indexable_total(getattr(p, "all_negative_prompts", None), total, label="all_negative_prompts")
    _require_indexable_total(getattr(p, "all_seeds", None), total, label="all_seeds")
    _require_indexable_total(getattr(p, "all_subseeds", None), total, label="all_subseeds")
    if bool(getattr(p, "enable_hr", False)):
        _require_indexable_total(getattr(p, "all_hr_prompts", None), total, label="all_hr_prompts")
        _require_indexable_total(getattr(p, "all_hr_negative_prompts", None), total, label="all_hr_negative_prompts")
    frozen = FrozenLayout(batch_size=batch_size, total=total)
    p._seqprompt_frozen_layout = frozen
    return frozen


def expected_batch_bounds(layout: FrozenLayout, batch_number: int) -> tuple[int, int]:
    batch_number = _strict_int(batch_number, label="batch_number")
    if batch_number < 0:
        raise LifecycleInvariantError("batch_number must be >= 0")
    start = batch_number * layout.batch_size
    remaining = max(layout.total - start, 0)
    return start, min(layout.batch_size, remaining)


def validate_live_batch(p: Any, *, batch_number: int) -> tuple[int, int]:
    layout = getattr(p, "_seqprompt_frozen_layout", None)
    if not isinstance(layout, FrozenLayout):
        raise LifecycleInvariantError("layout was not frozen after p.init")
    current_batch_size = _positive_int(getattr(p, "batch_size", None), label="batch_size")
    if current_batch_size != layout.batch_size:
        raise LifecycleInvariantError(f"batch_size changed after init ({layout.batch_size} -> {current_batch_size})")
    all_prompts = getattr(p, "all_prompts", None)
    if not isinstance(all_prompts, (list, tuple)) or len(all_prompts) != layout.total:
        current = len(all_prompts) if isinstance(all_prompts, (list, tuple)) else None
        raise LifecycleInvariantError(f"all_prompts changed after init ({layout.total} -> {current})")
    _require_indexable_total(getattr(p, "all_negative_prompts", None), layout.total, label="all_negative_prompts")
    _require_indexable_total(getattr(p, "all_seeds", None), layout.total, label="all_seeds")
    _require_indexable_total(getattr(p, "all_subseeds", None), layout.total, label="all_subseeds")
    if bool(getattr(p, "enable_hr", False)):
        _require_indexable_total(getattr(p, "all_hr_prompts", None), layout.total, label="all_hr_prompts")
        _require_indexable_total(getattr(p, "all_hr_negative_prompts", None), layout.total, label="all_hr_negative_prompts")
    start, expected_len = expected_batch_bounds(layout, batch_number)
    for values, label in (
        (getattr(p, "prompts", None), "prompts"),
        (getattr(p, "negative_prompts", None), "negative_prompts"),
        (getattr(p, "seeds", None), "seeds"),
        (getattr(p, "subseeds", None), "subseeds"),
    ):
        if not isinstance(values, (list, tuple)):
            raise LifecycleInvariantError(f"{label} is not an indexable batch")
        if len(values) != expected_len:
            raise LifecycleInvariantError(f"{label} live batch length is {len(values)}; expected {expected_len}")
    return start, expected_len


def global_index(p: Any, *, batch_number: int, local_index: int) -> int:
    start, expected_len = validate_live_batch(p, batch_number=batch_number)
    local_index = _strict_int(local_index, label="local_index")
    if local_index < 0 or local_index >= expected_len:
        raise LifecycleInvariantError("local_index is outside the frozen Forge batch")
    return start + local_index


def install_init_gate(p: Any, *, abort_reason: str | None = None, after_init: Callable[[Any], Any] | None = None) -> Callable[..., Any]:
    original = getattr(p, "init", None)
    if not callable(original):
        raise LifecycleInvariantError("p.init is not callable")
    if callable(getattr(p, "_seqprompt_original_init", None)):
        return getattr(p, "init")
    p._seqprompt_original_init = original

    def wrapped_init(*args: Any, **kwargs: Any) -> Any:
        p.init = original
        p._seqprompt_original_init = None
        if abort_reason:
            raise LifecycleInvariantError(str(abort_reason))
        result = original(*args, **kwargs)
        if after_init is None:
            freeze_layout_after_init(p)
        else:
            after_init(p)
        return result

    p.init = wrapped_init
    return wrapped_init


def install_one_shot_preparse_guard(p: Any) -> Callable[..., Any]:
    original = getattr(p, "parse_extra_network_prompts", None)
    if not callable(original):
        raise LifecycleInvariantError("parse_extra_network_prompts is not callable")
    if callable(getattr(p, "_seqprompt_original_parse_extra_network_prompts", None)):
        return getattr(p, "parse_extra_network_prompts")
    p._seqprompt_original_parse_extra_network_prompts = original

    def guarded_parse(*args: Any, **kwargs: Any) -> Any:
        p.parse_extra_network_prompts = original
        p._seqprompt_original_parse_extra_network_prompts = None
        try:
            blocked = getattr(p, "_seqprompt_blocked_reason", None)
            if blocked:
                raise LifecycleInvariantError(str(blocked))
            validate_live_batch(p, batch_number=getattr(p, "iteration", 0))
            return original(*args, **kwargs)
        except Exception:
            p._seqprompt_frozen_layout = None
            raise

    p.parse_extra_network_prompts = guarded_parse
    return guarded_parse


def _rebind_if_copied_bound_method(callable_obj: Any, p: Any) -> Any:
    owner = getattr(callable_obj, "__self__", None)
    function = getattr(callable_obj, "__func__", None)
    if owner is not None and function is not None and owner is not p:
        try:
            return function.__get__(p, type(p))
        except (AttributeError, TypeError):
            return callable_obj
    return callable_obj


def restore_lifecycle_overrides(p: Any) -> None:
    original_init = getattr(p, "_seqprompt_original_init", None)
    if callable(original_init):
        p.init = _rebind_if_copied_bound_method(original_init, p)
    p._seqprompt_original_init = None
    original_parse = getattr(p, "_seqprompt_original_parse_extra_network_prompts", None)
    if callable(original_parse):
        p.parse_extra_network_prompts = _rebind_if_copied_bound_method(original_parse, p)
    p._seqprompt_original_parse_extra_network_prompts = None
    p._seqprompt_frozen_layout = None


def seed_setup_owner(p: Any) -> None:
    if getattr(p, "_seqprompt_owner_id", None) is None:
        p._seqprompt_owner_id = id(p)


def begin_run_state(p: Any) -> bool:
    owner = getattr(p, "_seqprompt_owner_id", None)
    inherited = owner is not None and owner != id(p)
    restore_lifecycle_overrides(p)
    if inherited and isinstance(getattr(p, "extra_generation_params", None), dict):
        p.extra_generation_params = dict(p.extra_generation_params)
    p._seqprompt_owner_id = id(p)
    p._seqprompt_frozen_layout = None
    p._seqprompt_blocked_reason = None
    return inherited


def block_current_batch(p: Any, reason: str) -> None:
    p._seqprompt_blocked_reason = str(reason)
    p.prompts = []


def save_global_index(p: Any) -> int:
    layout = getattr(p, "_seqprompt_frozen_layout", None)
    if not isinstance(layout, FrozenLayout):
        raise LifecycleInvariantError("save routing has no frozen layout")
    try:
        iteration = _strict_int(getattr(p, "iteration"), label="iteration")
        batch_index = _strict_int(getattr(p, "batch_index"), label="batch_index")
    except (LifecycleInvariantError, AttributeError) as exc:
        raise LifecycleInvariantError("save routing index is invalid") from exc
    if iteration < 0 or batch_index < 0 or batch_index >= layout.batch_size:
        raise LifecycleInvariantError("save routing index is outside frozen layout")
    result = iteration * layout.batch_size + batch_index
    if result >= layout.total:
        raise LifecycleInvariantError("save routing index exceeds frozen total")
    return result
