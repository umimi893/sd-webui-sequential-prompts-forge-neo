from __future__ import annotations

import gradio as gr
import modules.scripts as scripts
from backend import args as forge_args
from modules import extra_networks, script_callbacks, shared

from seqprompt import __version__
from seqprompt.activation import (
    dynamic_prompts_status_conflicts_with_sequential,
    dynamic_prompts_status_from_runner,
)
from seqprompt.batch_integration import SequenceConfig
from seqprompt.core import resolve_sequential_blocks
from seqprompt.folders import route_image_save
from seqprompt.integration import (
    ActiveRunContract,
    install_preparse_sentinel,
    prepare_after_init,
    resolve_current_batch,
)
from seqprompt.lifecycle import (
    LifecycleInvariantError,
    begin_run_state,
    block_current_batch,
    install_init_gate,
    restore_lifecycle_overrides,
    seed_setup_owner,
)
from seqprompt.selected_contract import selected_script_conflict
from seqprompt.state import begin_save_state, finish_run_state, sequential_wan_conflict


def _has_sequence_text(value) -> bool:
    if isinstance(value, (list, tuple)):
        return any(_has_sequence_text(item) for item in value)
    if not isinstance(value, str):
        return False
    return resolve_sequential_blocks(value, 0).matched_blocks > 0


def _selected_script_info(p):
    runner = getattr(p, "scripts", None)
    args_values = getattr(p, "script_args", None)
    selectable = getattr(runner, "selectable_scripts", None)
    if not isinstance(args_values, (list, tuple)) or not args_values:
        return None, None
    if not isinstance(selectable, (list, tuple)):
        return None, None
    try:
        index = int(args_values[0])
    except (TypeError, ValueError):
        return None, None
    if index <= 0 or index > len(selectable):
        return None, None
    script = selectable[index - 1]
    try:
        title = str(script.title())
    except Exception:
        title = None

    matrix_type = None
    if str(title or "").strip().casefold() == "prompt matrix":
        start = getattr(script, "args_from", None)
        if isinstance(start, int) and not isinstance(start, bool) and start + 2 < len(args_values):
            matrix_type = str(args_values[start + 2])
    return title, matrix_type


def _known_extra_networks() -> dict[str, str]:
    known: dict[str, str] = {}
    for name, network in getattr(extra_networks, "extra_network_registry", {}).items():
        known[str(name)] = str(getattr(network, "name", name))
    for alias, network in getattr(extra_networks, "extra_network_aliases", {}).items():
        known[str(alias)] = str(getattr(network, "name", alias))
    return known


def _dynamic_prompts_conflict(p, *, raw_witness: bool) -> bool:
    status = dynamic_prompts_status_from_runner(p)
    opts = shared.opts
    return dynamic_prompts_status_conflicts_with_sequential(
        status,
        raw_relevant_had_sequence=raw_witness,
        variant_start=str(getattr(opts, "dp_parser_variant_start", "{")),
        variant_end=str(getattr(opts, "dp_parser_variant_end", "}")),
        wildcard_wrap=str(getattr(opts, "dp_parser_wildcard_wrap", "__")),
    )


def _integer_setting(value, *, label: str, minimum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{label} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be an integer") from exc
    if result < minimum:
        raise ValueError(f"{label} must be >= {minimum}")
    return result


def _boolean_setting(value, *, label: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool) and value in {0, 1}:
        return bool(value)
    raise ValueError(f"{label} must be true or false")


def _validated_config(
    advance_mode,
    repeat_each,
    start_index,
    end_mode,
    apply_negative,
) -> tuple[SequenceConfig, str | None]:
    errors: list[str] = []

    advance = str(advance_mode).strip().casefold()
    if advance not in {"batch", "image"}:
        errors.append("Sequence grouping must be 'batch' or 'image'")
        advance = "batch"

    ending = str(end_mode).strip().casefold()
    if ending not in {"loop", "clamp"}:
        errors.append("After the last choice must be 'loop' or 'clamp'")
        ending = "loop"

    try:
        repeat = _integer_setting(repeat_each, label="Hold each choice", minimum=1)
    except ValueError as exc:
        errors.append(str(exc))
        repeat = 1

    try:
        start = _integer_setting(start_index, label="Start index", minimum=0)
    except ValueError as exc:
        errors.append(str(exc))
        start = 0

    try:
        negative = _boolean_setting(apply_negative, label="Negative prompt processing")
    except ValueError as exc:
        errors.append(str(exc))
        negative = True

    config = SequenceConfig(
        advance_mode=advance,
        repeat_each=repeat,
        start_index=start,
        end_mode=ending,
        apply_negative=negative,
    )
    reason = "; ".join(errors) if errors else None
    return config, reason


class Script(scripts.Script):
    """Forge Neo always-on script for deterministic sequential prompt variants."""

    def title(self):
        # Forge derives API/script IDs from title(), so keep this stable across releases.
        return "Sequential Prompts for Forge Neo"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def setup(self, p, *args):
        seed_setup_owner(p)
        p._seqprompt_setup_positive = _has_sequence_text(getattr(p, "prompt", ""))
        p._seqprompt_setup_negative = _has_sequence_text(getattr(p, "negative_prompt", ""))
        p._seqprompt_setup_hr_positive = _has_sequence_text(getattr(p, "hr_prompt", ""))
        p._seqprompt_setup_hr_negative = _has_sequence_text(getattr(p, "hr_negative_prompt", ""))
        title, matrix_type = _selected_script_info(p)
        p._seqprompt_selected_script_title = title
        p._seqprompt_prompt_matrix_type = matrix_type

    def ui(self, is_img2img):
        with gr.Group(elem_id=self.elem_id("sequential-prompts-group")):
            with gr.Accordion("Sequential Prompts", open=False):
                enabled = gr.Checkbox(
                    value=True,
                    label="Enable Sequential Prompts",
                    elem_id=self.elem_id("enabled"),
                )
                gr.Markdown(
                    "`==A | B | C==` walks choices in order. "
                    "`===A | B | C===` does the same and routes final saved images into "
                    "folders named after the selected choice. Multiple folder blocks combine "
                    "as `A__D`. The syntax is intentionally separate from Dynamic Prompts' "
                    "default `{...}`, `__wildcard__`, `${...}`, `%{...}`, and `$$` grammar. "
                    "The default grouping is one choice per batch (`AAA → BBB → CCC`)."
                )
                advance_mode = gr.Radio(
                    choices=[
                        ("One choice per batch (recommended): AAA → BBB → CCC", "batch"),
                        ("Advance every image: ABC → ABC → ABC", "image"),
                    ],
                    value="batch",
                    label="Sequence grouping",
                    elem_id=self.elem_id("advance-mode"),
                )
                repeat_each = gr.Slider(
                    minimum=1,
                    maximum=100,
                    step=1,
                    value=1,
                    label="Hold each choice for N images / batches",
                    info=(
                        "Batch mode: keep a choice for N whole batches. "
                        "Image mode: keep a choice for N images."
                    ),
                    elem_id=self.elem_id("repeat-each"),
                )
                with gr.Accordion("Advanced settings", open=False):
                    start_index = gr.Slider(
                        minimum=0,
                        maximum=1000,
                        step=1,
                        value=0,
                        label="Start from choice index (0 = first choice)",
                        elem_id=self.elem_id("start-index"),
                    )
                    end_mode = gr.Radio(
                        choices=[
                            ("Loop: A → B → C → A", "loop"),
                            ("Clamp: A → B → C → C", "clamp"),
                        ],
                        value="loop",
                        label="After the last choice",
                        elem_id=self.elem_id("end-mode"),
                    )
                    apply_negative = gr.Checkbox(
                        value=True,
                        label="Also process negative prompt",
                        elem_id=self.elem_id("apply-negative"),
                    )
        return [enabled, advance_mode, repeat_each, start_index, end_mode, apply_negative]

    def process(self, p, enabled, advance_mode, repeat_each, start_index, end_mode, apply_negative):
        begin_run_state(p)
        begin_save_state(p)
        p._seqprompt_active_run = None
        if not enabled:
            return

        config, config_error = _validated_config(
            advance_mode,
            repeat_each,
            start_index,
            end_mode,
            apply_negative,
        )
        p._seqprompt_config = config

        raw_positive = bool(getattr(p, "_seqprompt_setup_positive", False))
        raw_negative = bool(getattr(p, "_seqprompt_setup_negative", False))
        raw_hr_positive = bool(getattr(p, "_seqprompt_setup_hr_positive", False))
        raw_hr_negative = bool(getattr(p, "_seqprompt_setup_hr_negative", False))
        hr_enabled = bool(getattr(p, "enable_hr", False))
        raw_relevant = (
            raw_positive
            or (config.apply_negative and raw_negative)
            or (hr_enabled and raw_hr_positive)
            or (hr_enabled and config.apply_negative and raw_hr_negative)
        )
        selected_title = getattr(p, "_seqprompt_selected_script_title", None)
        matrix_type = getattr(p, "_seqprompt_prompt_matrix_type", None)
        abort_reasons: list[str] = []
        selected_reason = selected_script_conflict(
            selected_title,
            raw_positive_had_sequence=raw_positive,
            raw_negative_had_sequence=raw_negative,
            current_has_sequence=False,
            prompt_matrix_type=matrix_type,
        )
        if selected_reason:
            abort_reasons.append(selected_reason)
        if _dynamic_prompts_conflict(p, raw_witness=raw_relevant):
            abort_reasons.append(
                "Dynamic Prompts is configured with a custom delimiter that overlaps "
                "Sequential Prompts ==/=== syntax"
            )

        known_networks = _known_extra_networks()

        def after_init(processing):
            run = prepare_after_init(processing, config=config, known_networks=known_networks)
            if run is None:
                return
            if config_error:
                raise LifecycleInvariantError(f"Invalid Sequential Prompts settings: {config_error}")

            # SD Upscale can become relevant only after styles/another process callback
            # introduced Sequential syntax. Prompt Matrix's structural conflict is raw-only.
            late_reason = selected_script_conflict(
                selected_title,
                raw_positive_had_sequence=raw_positive,
                raw_negative_had_sequence=raw_negative,
                current_has_sequence=True,
                prompt_matrix_type=matrix_type,
            )
            if late_reason and str(selected_title or "").strip().casefold() == "sd upscale":
                raise LifecycleInvariantError(late_reason)

            model = getattr(shared, "sd_model", None)
            wan_reason = sequential_wan_conflict(
                processing,
                sequential_active=True,
                wan_mode=bool(getattr(forge_args.dynamic_args, "wan", False)),
                model_is_wan=bool(getattr(model, "is_wan", False)),
            )
            if wan_reason:
                raise LifecycleInvariantError(wan_reason)

            processing._seqprompt_active_run = run
            params = getattr(processing, "extra_generation_params", None)
            if isinstance(params, dict):
                params["Sequential Prompts"] = f"v{__version__}"
                params["Sequential advance"] = config.advance_mode
                params["Sequential repeat"] = config.repeat_each
                params["Sequential start"] = config.start_index
                params["Sequential end"] = config.end_mode
                params["Sequential negative"] = config.apply_negative

        install_init_gate(
            p,
            abort_reason="; ".join(abort_reasons) if abort_reasons else None,
            after_init=after_init,
        )

    def before_process_batch(self, p, enabled, advance_mode, repeat_each, start_index, end_mode, apply_negative, **kwargs):
        if not enabled:
            return
        run = getattr(p, "_seqprompt_active_run", None)
        if not isinstance(run, ActiveRunContract):
            return
        batch_number = kwargs.get("batch_number", 0)
        try:
            resolve_current_batch(
                p,
                batch_number=batch_number,
                run=run,
                known_networks=_known_extra_networks(),
            )
        except Exception as exc:
            # Forge catches exceptions from always-on before_process_batch callbacks.
            # Record the failure and let the out-of-callback parser guard raise it.
            block_current_batch(p, f"Sequential Prompts batch resolution failed: {exc}")

        try:
            install_preparse_sentinel(p, batch_number=batch_number, run=run)
        except Exception as exc:
            # If the core guard itself cannot be installed, there is no safe way to
            # continue with an active sequence. Emptying the live batch is a last-resort
            # stop here, and re-raising also makes Forge log the contract failure.
            block_current_batch(p, f"Sequential Prompts could not install its core safety guard: {exc}")
            try:
                p.prompts = []
            except Exception:
                pass
            raise

    def postprocess(self, p, processed, enabled, advance_mode, repeat_each, start_index, end_mode, apply_negative):
        restore_lifecycle_overrides(p)
        finish_run_state(p)
        p._seqprompt_active_run = None


# Reload-safe callback registration. Forge catches callback exceptions and continues
# the original save, so routing failures do not destroy generated samples.
try:
    script_callbacks.remove_current_script_callbacks()
except Exception:
    pass
script_callbacks.on_before_image_saved(
    route_image_save,
    name="sequential-prompts-choice-folders",
)
