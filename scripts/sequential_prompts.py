from __future__ import annotations

import gradio as gr
import modules.scripts as scripts
from modules import script_callbacks

from seqprompt import __version__
from seqprompt.folders import (
    mark_next_grid_save,
    reset_grid_save_marker,
    route_image_save,
)
from seqprompt.integration import apply_processing_batch


class Script(scripts.Script):
    """Forge Neo always-on script for deterministic sequential prompt variants."""

    def title(self):
        return f"Sequential Prompts for Forge Neo v{__version__}"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        with gr.Group(elem_id=self.elem_id("sequential-prompts-group")):
            with gr.Accordion("Sequential Prompts", open=False):
                enabled = gr.Checkbox(
                    value=False,
                    label="Enable Sequential Prompts",
                    elem_id=self.elem_id("enabled"),
                )

                gr.Markdown(
                    "Use `=A | B | C=` for ordered choices. "
                    "Use `==A | B | C==` to also sort saved images into folders "
                    "named after the selected choice. Multiple `==...==` blocks combine "
                    "as `A__D`. Legacy `[[A|B|C]]` remains supported."
                )

                advance_mode = gr.Radio(
                    choices=[
                        ("Per image: A → B → C", "image"),
                        ("Per batch: AAA → BBB → CCC", "batch"),
                    ],
                    value="image",
                    label="Advance sequence",
                    elem_id=self.elem_id("advance-mode"),
                )

                repeat_each = gr.Slider(
                    minimum=1,
                    maximum=100,
                    step=1,
                    value=1,
                    label="Repeat each choice",
                    info=(
                        "Per image: 3 gives AAA BBB CCC. "
                        "Per batch: 3 keeps A for 3 batches, then B for 3 batches."
                    ),
                    elem_id=self.elem_id("repeat-each"),
                )

                start_index = gr.Slider(
                    minimum=0,
                    maximum=1000,
                    step=1,
                    value=0,
                    label="Start index (0 = first choice)",
                    elem_id=self.elem_id("start-index"),
                )

                end_mode = gr.Radio(
                    choices=[
                        ("Loop: A → B → C → A", "loop"),
                        ("Clamp: A → B → C → C", "clamp"),
                    ],
                    value="loop",
                    label="After the final choice",
                    elem_id=self.elem_id("end-mode"),
                )

                apply_negative = gr.Checkbox(
                    value=True,
                    label="Also process negative prompt",
                    elem_id=self.elem_id("apply-negative"),
                )

        return [
            enabled,
            advance_mode,
            repeat_each,
            start_index,
            end_mode,
            apply_negative,
        ]

    def process(
        self,
        p,
        enabled,
        advance_mode,
        repeat_each,
        start_index,
        end_mode,
        apply_negative,
    ):
        # Always reset per-run state first. This matters if an API/client reuses
        # a processing object and disables this extension on a later run.
        p._seqprompt_folder_routing_enabled = False
        p._seqprompt_output_folders = {}
        reset_grid_save_marker()

        params = getattr(p, "extra_generation_params", None)
        if not isinstance(params, dict):
            params = {}
            p.extra_generation_params = params

        for key in (
            "Sequential Prompts",
            "Sequential advance",
            "Sequential repeat",
            "Sequential start",
            "Sequential end",
            "Sequential negative",
        ):
            params.pop(key, None)

        if not enabled:
            return

        p._seqprompt_folder_routing_enabled = True

        # Do not resolve prompts here. Other always-on extensions may still
        # expand/replace p.all_prompts in their own process() callback. Actual
        # resolution happens in before_process_batch(), after those callbacks.
        params["Sequential Prompts"] = f"v{__version__}"
        params["Sequential advance"] = advance_mode
        params["Sequential repeat"] = max(int(repeat_each), 1)
        params["Sequential start"] = max(int(start_index), 0)
        params["Sequential end"] = end_mode
        params["Sequential negative"] = bool(apply_negative)

    def before_process_batch(
        self,
        p,
        enabled,
        advance_mode,
        repeat_each,
        start_index,
        end_mode,
        apply_negative,
        **kwargs,
    ):
        if not enabled:
            return

        apply_processing_batch(
            p,
            batch_number=kwargs.get("batch_number", 0),
            advance_mode=advance_mode,
            repeat_each=repeat_each,
            start_index=start_index,
            end_mode=end_mode,
            apply_negative=bool(apply_negative),
        )


script_callbacks.on_image_grid(
    mark_next_grid_save,
    name="sequential-prompts-grid-marker",
)

script_callbacks.on_before_image_saved(
    route_image_save,
    name="sequential-prompts-choice-folders",
)
