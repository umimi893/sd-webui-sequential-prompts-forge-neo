from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "sequential_prompts.py"


class FakeScriptBase:
    def elem_id(self, value):
        return value


class ScriptContractTests(unittest.TestCase):
    def load_script_module(self, *, wan=False, model_is_wan=False, dp_opts=None):
        registrations = []
        removed = []

        scripts_mod = types.ModuleType("modules.scripts")
        scripts_mod.Script = FakeScriptBase
        scripts_mod.AlwaysVisible = object()

        callbacks_mod = types.ModuleType("modules.script_callbacks")
        callbacks_mod.remove_current_script_callbacks = lambda: removed.append(True)
        callbacks_mod.on_before_image_saved = lambda fn, **kw: registrations.append((fn, kw))

        extra_mod = types.ModuleType("modules.extra_networks")
        extra_mod.extra_network_registry = {}
        extra_mod.extra_network_aliases = {}

        opts = SimpleNamespace(
            dp_parser_variant_start="{",
            dp_parser_variant_end="}",
            dp_parser_wildcard_wrap="__",
        )
        for key, value in (dp_opts or {}).items():
            setattr(opts, key, value)
        shared_mod = types.ModuleType("modules.shared")
        shared_mod.opts = opts
        shared_mod.sd_model = SimpleNamespace(is_wan=model_is_wan)

        modules_mod = types.ModuleType("modules")
        modules_mod.scripts = scripts_mod
        modules_mod.script_callbacks = callbacks_mod
        modules_mod.extra_networks = extra_mod
        modules_mod.shared = shared_mod

        args_mod = types.ModuleType("backend.args")
        args_mod.dynamic_args = SimpleNamespace(wan=wan)
        backend_mod = types.ModuleType("backend")
        backend_mod.args = args_mod

        gradio_mod = types.ModuleType("gradio")

        fake = {
            "gradio": gradio_mod,
            "modules": modules_mod,
            "modules.scripts": scripts_mod,
            "modules.script_callbacks": callbacks_mod,
            "modules.extra_networks": extra_mod,
            "modules.shared": shared_mod,
            "backend": backend_mod,
            "backend.args": args_mod,
        }
        with mock.patch.dict(sys.modules, fake):
            spec = importlib.util.spec_from_file_location("seqprompt_script_contract", SCRIPT_PATH)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module, scripts_mod, registrations, removed

    def make_p(self, prompt="===A|B|C===, ==D|E|F==", total=3, batch_size=3):
        def init(*args, **kwargs):
            return None

        def parse_extra_network_prompts(*args, **kwargs):
            return "parsed"

        return SimpleNamespace(
            prompt=prompt,
            negative_prompt="neg",
            batch_size=batch_size,
            n_iter=1,
            all_prompts=[prompt] * total,
            all_negative_prompts=["neg"] * total,
            all_seeds=list(range(10, 10 + total)),
            all_subseeds=list(range(20, 20 + total)),
            prompts=[],
            negative_prompts=[],
            seeds=[],
            subseeds=[],
            enable_hr=False,
            disable_extra_networks=False,
            extra_generation_params={},
            scripts=SimpleNamespace(alwayson_scripts=[], selectable_scripts=[]),
            script_args=[0],
            init=init,
            parse_extra_network_prompts=parse_extra_network_prompts,
            main_prompt=prompt,
            main_negative_prompt="neg",
        )

    def activate(self, module, p, *, enabled=True):
        script = module.Script()
        script.setup(p)
        script.process(p, enabled, "image", 1, 0, "loop", True)
        p.init(p.all_prompts, p.all_seeds, p.all_subseeds)
        return script

    def slice_batch(self, p, n=0):
        s = n * p.batch_size
        e = (n + 1) * p.batch_size
        p.iteration = n
        p.prompts = p.all_prompts[s:e]
        p.negative_prompts = p.all_negative_prompts[s:e]
        p.seeds = p.all_seeds[s:e]
        p.subseeds = p.all_subseeds[s:e]

    def test_title_is_stable_and_script_is_always_visible(self):
        module, scripts_mod, _, _ = self.load_script_module()
        script = module.Script()
        self.assertEqual(script.title(), "Sequential Prompts for Forge Neo")
        self.assertIs(script.show(False), scripts_mod.AlwaysVisible)

    def test_ui_defaults_are_enabled_and_batch_first(self):
        module, _, _, _ = self.load_script_module()
        created = []

        class Context:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def component(kind):
            def make(*args, **kwargs):
                created.append((kind, args, kwargs))
                return SimpleNamespace(kind=kind, args=args, kwargs=kwargs)

            return make

        module.gr.Group = Context
        module.gr.Accordion = Context
        module.gr.Markdown = component("Markdown")
        module.gr.Checkbox = component("Checkbox")
        module.gr.Radio = component("Radio")
        module.gr.Slider = component("Slider")

        values = module.Script().ui(False)
        self.assertEqual(len(values), 6)

        enabled = next(
            item
            for item in created
            if item[0] == "Checkbox" and item[2].get("label") == "Enable Sequential Prompts"
        )
        grouping = next(
            item
            for item in created
            if item[0] == "Radio" and item[2].get("label") == "Sequence grouping"
        )
        hold = next(
            item
            for item in created
            if item[0] == "Slider"
            and item[2].get("label") == "Hold each choice for N images / batches"
        )

        self.assertTrue(enabled[2]["value"])
        self.assertEqual(grouping[2]["value"], "batch")
        self.assertEqual(grouping[2]["choices"][0][1], "batch")
        self.assertEqual(hold[2]["value"], 1)

    def test_save_callback_is_reload_safe_and_registered(self):
        _, _, registrations, removed = self.load_script_module()
        self.assertEqual(removed, [True])
        self.assertEqual(len(registrations), 1)
        self.assertEqual(registrations[0][1]["name"], "sequential-prompts-choice-folders")

    def test_full_batch_contract_resolves_and_records_folder_identity(self):
        module, _, _, _ = self.load_script_module()
        p = self.make_p()
        script = self.activate(module, p)
        self.assertIn("Sequential Prompts", p.extra_generation_params)

        self.slice_batch(p)
        script.before_process_batch(p, True, "image", 1, 0, "loop", True, batch_number=0)
        self.assertEqual(p.prompts, ["A, D", "B, E", "C, F"])
        self.assertEqual(p._seqprompt_output_folders, {0: "A", 1: "B", 2: "C"})
        self.assertEqual(len(p._seqprompt_output_identities), 3)
        self.assertEqual(p.parse_extra_network_prompts(), "parsed")

    def test_enabled_without_syntax_is_behavioral_noop(self):
        module, _, _, _ = self.load_script_module()
        p = self.make_p(prompt="plain", total=1, batch_size=1)
        self.activate(module, p)
        self.assertIsNone(p._seqprompt_active_run)
        self.assertNotIn("Sequential Prompts", p.extra_generation_params)
        self.assertFalse(p._seqprompt_folder_routing_enabled)

    def test_late_unresolved_syntax_is_hard_stopped_at_core_preparse(self):
        module, _, _, _ = self.load_script_module()
        p = self.make_p(prompt="==A|B==", total=1, batch_size=1)
        script = self.activate(module, p)
        self.slice_batch(p)
        script.before_process_batch(p, True, "image", 1, 0, "loop", True, batch_number=0)
        p.prompts[0] = "==late1|late2=="
        with self.assertRaisesRegex(Exception, "unresolved Sequential"):
            p.parse_extra_network_prompts()

    def test_multiframe_wan_is_rejected_after_final_init_state(self):
        module, _, _, _ = self.load_script_module(wan=True, model_is_wan=True)
        p = self.make_p(prompt="==A|B==", total=5, batch_size=5)
        script = module.Script()
        script.setup(p)
        script.process(p, True, "image", 1, 0, "loop", True)
        with self.assertRaisesRegex(Exception, "multi-frame Wan"):
            p.init(p.all_prompts, p.all_seeds, p.all_subseeds)

    def test_default_dynamic_prompts_delimiters_are_allowed(self):
        module, _, _, _ = self.load_script_module()
        p = self.make_p(prompt="==A|B==", total=1, batch_size=1)
        dp = SimpleNamespace(args_from=1, title=lambda: "Dynamic Prompts")
        p.scripts.alwayson_scripts = [dp]
        p.script_args = [0, True]
        script = module.Script()
        script.setup(p)
        script.process(p, True, "image", 1, 0, "loop", True)
        p.init(p.all_prompts, p.all_seeds, p.all_subseeds)
        self.assertIsNotNone(p._seqprompt_active_run)

    def test_hr_raw_witness_participates_in_dynamic_prompts_custom_delimiter_conflict(self):
        module, _, _, _ = self.load_script_module(
            dp_opts={"dp_parser_variant_start": "==", "dp_parser_variant_end": "=="}
        )
        p = self.make_p(prompt="plain", total=1, batch_size=1)
        p.enable_hr = True
        p.hr_prompt = "==H1|H2=="
        p.hr_negative_prompt = ""
        p.all_hr_prompts = [p.hr_prompt]
        p.all_hr_negative_prompts = ["neg"]
        dp = SimpleNamespace(args_from=1, title=lambda: "Dynamic Prompts")
        p.scripts.alwayson_scripts = [dp]
        p.script_args = [0, True]
        script = module.Script()
        script.setup(p)
        script.process(p, True, "image", 1, 0, "loop", True)
        with self.assertRaisesRegex(Exception, "Dynamic Prompts"):
            p.init(p.all_prompts, p.all_seeds, p.all_subseeds)

    def test_postprocess_clears_routing_state(self):
        module, _, _, _ = self.load_script_module()
        p = self.make_p(total=1, batch_size=1, prompt="===A|B===")
        script = self.activate(module, p)
        self.slice_batch(p)
        script.before_process_batch(p, True, "image", 1, 0, "loop", True, batch_number=0)
        self.assertTrue(p._seqprompt_folder_routing_enabled)
        script.postprocess(p, None, True, "image", 1, 0, "loop", True)
        self.assertFalse(p._seqprompt_folder_routing_enabled)
        self.assertEqual(p._seqprompt_output_folders, {})
        self.assertIsNone(p._seqprompt_frozen_layout)


if __name__ == "__main__":
    unittest.main()
