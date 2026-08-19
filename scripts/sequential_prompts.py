from __future__ import annotations

import gradio as gr
import modules.scripts as scripts

from seqprompt import __version__
from seqprompt.core import expand_prompt_series


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
                    "Use `[[A|B|C]]`. Choices are selected in order instead of randomly. "
                    "This separate syntax avoids conflicts with Dynamic Prompts `{A|B|C}`."
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
        if not enabled:
            return

        batch_size = max(int(getattr(p, "batch_size", 1)), 1)
        repeat_each = max(int(repeat_each), 1)
        start_index = max(int(start_index), 0)

        all_prompts = list(getattr(p, "all_prompts", []) or [])
        all_negative_prompts = list(
            getattr(p, "all_negative_prompts", []) or []
        )

        p.all_prompts = expand_prompt_series(
            all_prompts,
            batch_size=batch_size,
            advance_mode=advance_mode,
            repeat_each=repeat_each,
            start_index=start_index,
            end_mode=end_mode,
        )

        if apply_negative:
            p.all_negative_prompts = expand_prompt_series(
                all_negative_prompts,
                batch_size=batch_size,
                advance_mode=advance_mode,
                repeat_each=repeat_each,
                start_index=start_index,
                end_mode=end_mode,
            )

        # Forge Neo sets these from all_prompts before scripts.process().
        # Keep them synchronized after our transformation.
        if p.all_prompts:
            p.main_prompt = p.all_prompts[0]
        if p.all_negative_prompts:
            p.main_negative_prompt = p.all_negative_prompts[0]

        p.extra_generation_params["Sequential Prompts"] = f"v{__version__}"
        p.extra_generation_params["Sequential advance"] = advance_mode
        p.extra_generation_params["Sequential repeat"] = repeat_each
        p.extra_generation_params["Sequential start"] = start_index
        p.extra_generation_params["Sequential end"] = end_mode
