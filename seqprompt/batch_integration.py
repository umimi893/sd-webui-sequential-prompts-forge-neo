from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Callable, Mapping


class BatchIntegrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class SequenceConfig:
    advance_mode: str = "image"
    repeat_each: int = 1
    start_index: int = 0
    end_mode: str = "loop"
    apply_negative: bool = True


@dataclass(frozen=True)
class NetworkParamSignature:
    network: str
    params: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class BatchResolutionResult:
    start: int
    length: int
    folder_choices: tuple[tuple[int, tuple[str, ...]], ...]
    matched_blocks: int


_EXTRA_NETWORK_RE = re.compile(r"<(\w+):([^>]+)>")


def _normalized_network_name(name: str, known_networks: Mapping[str, str] | None) -> str | None:
    if known_networks is None:
        return name
    return known_networks.get(name)


def forge_extra_network_signature(prompt: Any, *, known_networks: Mapping[str, str] | None = None) -> tuple[NetworkParamSignature, ...]:
    if not isinstance(prompt, str):
        return ()
    grouped: dict[str, list[tuple[str, ...]]] = {}
    order: list[str] = []
    for match in _EXTRA_NETWORK_RE.finditer(prompt):
        raw_name = match.group(1)
        canonical = _normalized_network_name(raw_name, known_networks)
        if canonical is None:
            continue
        if canonical not in grouped:
            grouped[canonical] = []
            order.append(canonical)
        grouped[canonical].append(tuple(match.group(2).split(":")))
    return tuple(NetworkParamSignature(network=name, params=tuple(grouped[name])) for name in order)


def sequential_network_change_is_unsafe(
    raw_prompts: list[str] | tuple[str, ...],
    resolved_prompts: list[str] | tuple[str, ...],
    *,
    known_networks: Mapping[str, str] | None = None,
    extra_networks_enabled: bool = True,
) -> bool:
    if not extra_networks_enabled or len(resolved_prompts) <= 1:
        return False
    if len(raw_prompts) != len(resolved_prompts):
        raise BatchIntegrationError("raw/resolved prompt lengths differ")
    before = [forge_extra_network_signature(x, known_networks=known_networks) for x in raw_prompts]
    after = [forge_extra_network_signature(x, known_networks=known_networks) for x in resolved_prompts]
    if not any(a != b for a, b in zip(before, after)):
        return False
    return any(signature != after[0] for signature in after[1:])


def _sequence_index(*, global_index: int, batch_size: int, config: SequenceConfig, sequence_index_for_image: Callable[..., int]) -> int:
    return sequence_index_for_image(
        image_index=global_index,
        batch_size=batch_size,
        advance_mode=config.advance_mode,
        repeat_each=config.repeat_each,
        start_index=config.start_index,
    )


def _resolve_one(text: str, *, global_index: int, batch_size: int, config: SequenceConfig, resolve: Callable[..., Any], sequence_index_for_image: Callable[..., int]) -> Any:
    sequence_index = _sequence_index(global_index=global_index, batch_size=batch_size, config=config, sequence_index_for_image=sequence_index_for_image)
    return resolve(text, sequence_index=sequence_index, end_mode=config.end_mode)


def _resolved_copy(values: list[str] | tuple[str, ...], *, batch_size: int, config: SequenceConfig, resolve: Callable[..., Any], sequence_index_for_image: Callable[..., int]) -> list[str]:
    return [
        _resolve_one(str(value), global_index=index, batch_size=batch_size, config=config, resolve=resolve, sequence_index_for_image=sequence_index_for_image).text
        for index, value in enumerate(values)
    ]


def preflight_job_extra_networks(
    p: Any,
    *,
    batch_size: int,
    config: SequenceConfig,
    resolve: Callable[..., Any],
    sequence_index_for_image: Callable[..., int],
    known_networks: Mapping[str, str] | None = None,
) -> None:
    if bool(getattr(p, "disable_extra_networks", False)):
        return
    all_prompts = getattr(p, "all_prompts", None)
    if isinstance(all_prompts, (list, tuple)):
        resolved = _resolved_copy(all_prompts, batch_size=batch_size, config=config, resolve=resolve, sequence_index_for_image=sequence_index_for_image)
        for start in range(0, len(resolved), batch_size):
            raw_batch = list(all_prompts[start : start + batch_size])
            resolved_batch = resolved[start : start + batch_size]
            if sequential_network_change_is_unsafe(raw_batch, resolved_batch, known_networks=known_networks, extra_networks_enabled=True):
                raise BatchIntegrationError(f"prompt batch {start // batch_size + 1} resolves to different Extra Network/LoRA settings per image")
    if not bool(getattr(p, "enable_hr", False)):
        return
    all_hr_prompts = getattr(p, "all_hr_prompts", None)
    if isinstance(all_hr_prompts, (list, tuple)):
        resolved_hr = _resolved_copy(all_hr_prompts, batch_size=batch_size, config=config, resolve=resolve, sequence_index_for_image=sequence_index_for_image)
        for start in range(0, len(resolved_hr), batch_size):
            raw_batch = list(all_hr_prompts[start : start + batch_size])
            resolved_batch = resolved_hr[start : start + batch_size]
            if sequential_network_change_is_unsafe(raw_batch, resolved_batch, known_networks=known_networks, extra_networks_enabled=True):
                raise BatchIntegrationError(f"Hires.fix prompt batch {start // batch_size + 1} resolves to different Extra Network/LoRA settings per image")


def _source_has_sequence(values: Any, *, resolve: Callable[..., Any]) -> bool:
    if not isinstance(values, (list, tuple)):
        return False
    for value in values:
        if not isinstance(value, str):
            continue
        if int(getattr(resolve(value, sequence_index=0, end_mode="loop"), "matched_blocks", 0)) > 0:
            return True
    return False


def infer_active_source_names(p: Any, *, config: SequenceConfig, resolve: Callable[..., Any]) -> frozenset[str]:
    active: set[str] = set()
    if _source_has_sequence(getattr(p, "all_prompts", None), resolve=resolve):
        active.add("all_prompts")
    if config.apply_negative and _source_has_sequence(getattr(p, "all_negative_prompts", None), resolve=resolve):
        active.add("all_negative_prompts")
    if bool(getattr(p, "enable_hr", False)):
        if _source_has_sequence(getattr(p, "all_hr_prompts", None), resolve=resolve):
            active.add("all_hr_prompts")
        if config.apply_negative and _source_has_sequence(getattr(p, "all_hr_negative_prompts", None), resolve=resolve):
            active.add("all_hr_negative_prompts")
    return frozenset(active)


def resolve_frozen_batch(
    p: Any,
    *,
    batch_number: int,
    start: int,
    expected_len: int,
    batch_size: int,
    config: SequenceConfig,
    resolve: Callable[..., Any],
    sequence_index_for_image: Callable[..., int],
    known_networks: Mapping[str, str] | None = None,
    active_sources: frozenset[str] | set[str] | None = None,
) -> BatchResolutionResult:
    if active_sources is None:
        active_sources = infer_active_source_names(p, config=config, resolve=resolve)
    else:
        active_sources = frozenset(active_sources)

    prompts = getattr(p, "prompts", None)
    all_prompts = getattr(p, "all_prompts", None)
    if not isinstance(prompts, (list, tuple)) or len(prompts) != expected_len:
        raise BatchIntegrationError("live positive batch length changed")

    folder_records: list[tuple[int, tuple[str, ...]]] = []
    matched_blocks = 0
    if "all_prompts" in active_sources:
        if not isinstance(prompts, list) or not isinstance(all_prompts, list):
            raise BatchIntegrationError("active positive prompts must be mutable lists")
        raw_positive = list(prompts)
        for local_index, raw in enumerate(raw_positive):
            global_index = start + local_index
            resolution = _resolve_one(raw, global_index=global_index, batch_size=batch_size, config=config, resolve=resolve, sequence_index_for_image=sequence_index_for_image)
            prompts[local_index] = resolution.text
            all_prompts[global_index] = resolution.text
            matched_blocks += int(getattr(resolution, "matched_blocks", 0))
            folder_choices = tuple(getattr(resolution, "folder_choices", ()))
            if folder_choices:
                folder_records.append((global_index, folder_choices))
        if sequential_network_change_is_unsafe(raw_positive, prompts, known_networks=known_networks, extra_networks_enabled=not bool(getattr(p, "disable_extra_networks", False))):
            raise BatchIntegrationError("current positive batch resolves to different Extra Network/LoRA settings per image")

    if config.apply_negative and "all_negative_prompts" in active_sources:
        negatives = getattr(p, "negative_prompts", None)
        all_negatives = getattr(p, "all_negative_prompts", None)
        if not isinstance(negatives, list) or not isinstance(all_negatives, list):
            raise BatchIntegrationError("active negative prompts must be mutable lists")
        if len(negatives) != expected_len:
            raise BatchIntegrationError("live negative batch length changed")
        for local_index, raw in enumerate(list(negatives)):
            global_index = start + local_index
            resolution = _resolve_one(raw, global_index=global_index, batch_size=batch_size, config=config, resolve=resolve, sequence_index_for_image=sequence_index_for_image)
            negatives[local_index] = resolution.text
            all_negatives[global_index] = resolution.text
            matched_blocks += int(getattr(resolution, "matched_blocks", 0))

    if bool(getattr(p, "enable_hr", False)) and "all_hr_prompts" in active_sources:
        hr_prompts = getattr(p, "all_hr_prompts", None)
        if not isinstance(hr_prompts, list):
            raise BatchIntegrationError("active Hires prompts must be a mutable list")
        raw_hr = list(hr_prompts[start : start + expected_len])
        for local_index, raw in enumerate(raw_hr):
            global_index = start + local_index
            resolution = _resolve_one(raw, global_index=global_index, batch_size=batch_size, config=config, resolve=resolve, sequence_index_for_image=sequence_index_for_image)
            hr_prompts[global_index] = resolution.text
            matched_blocks += int(getattr(resolution, "matched_blocks", 0))
        resolved_hr = hr_prompts[start : start + expected_len]
        if sequential_network_change_is_unsafe(raw_hr, resolved_hr, known_networks=known_networks, extra_networks_enabled=not bool(getattr(p, "disable_extra_networks", False))):
            raise BatchIntegrationError("current Hires.fix batch resolves to different Extra Network/LoRA settings per image")

    if bool(getattr(p, "enable_hr", False)) and config.apply_negative and "all_hr_negative_prompts" in active_sources:
        hr_negatives = getattr(p, "all_hr_negative_prompts", None)
        if not isinstance(hr_negatives, list):
            raise BatchIntegrationError("active Hires negative prompts must be a mutable list")
        for local_index in range(expected_len):
            global_index = start + local_index
            resolution = _resolve_one(hr_negatives[global_index], global_index=global_index, batch_size=batch_size, config=config, resolve=resolve, sequence_index_for_image=sequence_index_for_image)
            hr_negatives[global_index] = resolution.text
            matched_blocks += int(getattr(resolution, "matched_blocks", 0))

    if all_prompts:
        p.main_prompt = all_prompts[0]
    all_negatives = getattr(p, "all_negative_prompts", None)
    if isinstance(all_negatives, list) and all_negatives:
        p.main_negative_prompt = all_negatives[0]

    return BatchResolutionResult(start=start, length=expected_len, folder_choices=tuple(folder_records), matched_blocks=matched_blocks)
