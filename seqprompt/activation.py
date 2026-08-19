from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class SourcePresence:
    name: str
    matched_indices: tuple[int, ...]
    mutable: bool

    @property
    def active(self) -> bool:
        return bool(self.matched_indices)


@dataclass(frozen=True)
class ActivationScan:
    sources: tuple[SourcePresence, ...]

    @property
    def active(self) -> bool:
        return any(source.active for source in self.sources)

    @property
    def active_sources(self) -> tuple[SourcePresence, ...]:
        return tuple(source for source in self.sources if source.active)


def _scan_values(
    name: str,
    values: Any,
    *,
    resolve: Callable[[str, int], Any],
) -> SourcePresence:
    if not isinstance(values, (list, tuple)):
        return SourcePresence(name=name, matched_indices=(), mutable=False)

    matched: list[int] = []
    for index, value in enumerate(values):
        if not isinstance(value, str):
            continue
        resolution = resolve(value, 0)
        if int(getattr(resolution, "matched_blocks", 0)) > 0:
            matched.append(index)

    return SourcePresence(
        name=name,
        matched_indices=tuple(matched),
        mutable=isinstance(values, list),
    )


def scan_relevant_sources(
    p: Any,
    *,
    apply_negative: bool,
    resolve: Callable[[str, int], Any],
) -> ActivationScan:
    sources = [
        _scan_values("all_prompts", getattr(p, "all_prompts", None), resolve=resolve)
    ]

    if apply_negative:
        sources.append(
            _scan_values(
                "all_negative_prompts",
                getattr(p, "all_negative_prompts", None),
                resolve=resolve,
            )
        )

    if bool(getattr(p, "enable_hr", False)):
        sources.append(
            _scan_values(
                "all_hr_prompts",
                getattr(p, "all_hr_prompts", None),
                resolve=resolve,
            )
        )
        if apply_negative:
            sources.append(
                _scan_values(
                    "all_hr_negative_prompts",
                    getattr(p, "all_hr_negative_prompts", None),
                    resolve=resolve,
                )
            )

    return ActivationScan(tuple(sources))


def active_sources_are_mutable(scan: ActivationScan) -> bool:
    """Only arrays that actually contain Sequential syntax must be mutable."""
    return all(source.mutable for source in scan.active_sources)


def dynamic_prompts_dollar_conflict(
    *,
    dp_enabled: bool,
    raw_relevant_had_sequence: bool,
    variant_start: str,
    variant_end: str,
    wildcard_wrap: str,
) -> bool:
    """Return True when enabled Dynamic Prompts claims our exact $/$$ delimiters."""
    if not dp_enabled or not raw_relevant_had_sequence:
        return False
    claimed = {str(variant_start), str(variant_end), str(wildcard_wrap)}
    return bool(claimed.intersection({"$", "$$"}))


def relevant_raw_sequence_witness(
    *,
    positive: bool,
    negative: bool,
    hr_positive: bool,
    hr_negative: bool,
    apply_negative: bool,
    enable_hr: bool,
) -> bool:
    if positive:
        return True
    if apply_negative and negative:
        return True
    if enable_hr and hr_positive:
        return True
    if enable_hr and apply_negative and hr_negative:
        return True
    return False


def dynamic_prompts_enabled_from_runner(p: Any) -> bool | None:
    """Read current DP always-on arg without importing DP. None means not found/unknown."""
    runner = getattr(p, "scripts", None)
    scripts = getattr(runner, "alwayson_scripts", None)
    args = getattr(p, "script_args", None)
    if not isinstance(scripts, (list, tuple)) or not isinstance(args, (list, tuple)):
        return None

    for script in scripts:
        try:
            title = str(script.title()).strip().casefold()
        except Exception:
            continue
        if not title.startswith("dynamic prompts"):
            continue

        start = getattr(script, "args_from", None)
        if not isinstance(start, int) or start < 0 or start >= len(args):
            return None
        return bool(args[start])

    return None


@dataclass(frozen=True)
class DynamicPromptsStatus:
    present: bool
    enabled: bool | None


def dynamic_prompts_status_from_runner(p: Any) -> DynamicPromptsStatus:
    """Locate current Dynamic Prompts script without importing the extension.

    ``enabled=None`` means DP was identified but its current enabled argument
    could not be read. That is distinct from the extension being absent and is
    intentionally treated conservatively by the delimiter-conflict policy.
    """
    runner = getattr(p, "scripts", None)
    scripts = getattr(runner, "alwayson_scripts", None)
    args = getattr(p, "script_args", None)
    if not isinstance(scripts, (list, tuple)):
        return DynamicPromptsStatus(present=False, enabled=None)

    for script in scripts:
        module_name = str(getattr(script.__class__, "__module__", "")).casefold()
        module_match = "sd_dynamic_prompts" in module_name
        title_match = False
        try:
            title_match = str(script.title()).strip().casefold().startswith("dynamic prompts")
        except Exception:
            pass
        if not (module_match or title_match):
            continue

        start = getattr(script, "args_from", None)
        if (
            isinstance(args, (list, tuple))
            and isinstance(start, int)
            and not isinstance(start, bool)
            and 0 <= start < len(args)
        ):
            return DynamicPromptsStatus(present=True, enabled=bool(args[start]))
        return DynamicPromptsStatus(present=True, enabled=None)

    return DynamicPromptsStatus(present=False, enabled=None)


def dynamic_prompts_status_conflicts_with_dollar(
    status: DynamicPromptsStatus,
    *,
    raw_relevant_had_sequence: bool,
    variant_start: str,
    variant_end: str,
    wildcard_wrap: str,
) -> bool:
    """Fail conservatively if present DP may own our exact delimiters."""
    if not status.present or status.enabled is False or not raw_relevant_had_sequence:
        return False
    claimed = {str(variant_start), str(variant_end), str(wildcard_wrap)}
    return bool(claimed.intersection({"$", "$$"}))


def unresolved_relevant_sequence_present(
    p: Any,
    *,
    apply_negative: bool,
    resolve: Callable[[str, int], Any],
    current_start: int = 0,
    current_len: int | None = None,
) -> bool:
    """Detect Sequential syntax that survived until Forge's core pre-parse point."""
    containers: list[Any] = [getattr(p, "prompts", None)]
    if apply_negative:
        containers.append(getattr(p, "negative_prompts", None))

    if bool(getattr(p, "enable_hr", False)):
        if current_len is None or current_start < 0 or current_len < 0:
            return True
        hr_prompts = getattr(p, "all_hr_prompts", None)
        if isinstance(hr_prompts, (list, tuple)):
            containers.append(hr_prompts[current_start : current_start + current_len])
        if apply_negative:
            hr_negatives = getattr(p, "all_hr_negative_prompts", None)
            if isinstance(hr_negatives, (list, tuple)):
                containers.append(hr_negatives[current_start : current_start + current_len])

    for values in containers:
        if not isinstance(values, (list, tuple)):
            continue
        for value in values:
            if not isinstance(value, str):
                continue
            if int(getattr(resolve(value, 0), "matched_blocks", 0)) > 0:
                return True
    return False
