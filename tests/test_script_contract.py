import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


class ScriptContractTests(unittest.TestCase):
    @staticmethod
    def load_script_module():
        fake_gradio = ModuleType("gradio")
        fake_modules = ModuleType("modules")
        fake_scripts = ModuleType("modules.scripts")
        fake_callbacks = ModuleType("modules.script_callbacks")
        registrations = []

        class FakeScript:
            pass

        def on_before_image_saved(callback, *, name=None):
            registrations.append(("before_image_saved", callback, name))

        def on_image_grid(callback, *, name=None):
            registrations.append(("image_grid", callback, name))

        fake_scripts.Script = FakeScript
        fake_scripts.AlwaysVisible = object()
        fake_callbacks.on_before_image_saved = on_before_image_saved
        fake_callbacks.on_image_grid = on_image_grid
        fake_modules.scripts = fake_scripts
        fake_modules.script_callbacks = fake_callbacks

        script_path = Path(__file__).parents[1] / "scripts" / "sequential_prompts.py"
        spec = importlib.util.spec_from_file_location("sequential_prompts_contract", script_path)
        module = importlib.util.module_from_spec(spec)

        with patch.dict(
            sys.modules,
            {
                "gradio": fake_gradio,
                "modules": fake_modules,
                "modules.scripts": fake_scripts,
                "modules.script_callbacks": fake_callbacks,
            },
        ):
            assert spec.loader is not None
            spec.loader.exec_module(module)

        return module, fake_scripts, registrations

    def test_script_is_always_visible(self):
        module, fake_scripts, _ = self.load_script_module()
        script = module.Script()
        self.assertIs(script.show(False), fake_scripts.AlwaysVisible)
        self.assertIs(script.show(True), fake_scripts.AlwaysVisible)

    def test_save_callbacks_are_registered(self):
        _, _, registrations = self.load_script_module()
        self.assertEqual(len(registrations), 2)
        self.assertEqual(
            [(kind, name) for kind, _, name in registrations],
            [
                ("image_grid", "sequential-prompts-grid-marker"),
                ("before_image_saved", "sequential-prompts-choice-folders"),
            ],
        )

    def test_process_records_metadata_without_destroying_template(self):
        module, _, _ = self.load_script_module()
        script = module.Script()
        p = SimpleNamespace(
            all_prompts=["==A|B|C=="],
            extra_generation_params={},
        )

        script.process(p, True, "image", 1, 0, "loop", True)

        self.assertEqual(p.all_prompts, ["==A|B|C=="])
        self.assertEqual(p.extra_generation_params["Sequential advance"], "image")
        self.assertTrue(p._seqprompt_folder_routing_enabled)
        self.assertEqual(p._seqprompt_output_folders, {})

    def test_disabled_process_clears_stale_folder_routing_state(self):
        module, _, _ = self.load_script_module()
        script = module.Script()
        p = SimpleNamespace(
            _seqprompt_folder_routing_enabled=True,
            _seqprompt_output_folders={0: "stale"},
            extra_generation_params={},
        )

        script.process(p, False, "image", 1, 0, "loop", True)

        self.assertFalse(p._seqprompt_folder_routing_enabled)
        self.assertEqual(p._seqprompt_output_folders, {})

    def test_disabled_process_clears_stale_generation_metadata(self):
        module, _, _ = self.load_script_module()
        script = module.Script()
        p = SimpleNamespace(
            extra_generation_params={
                "Sequential Prompts": "v0.4.1",
                "Sequential advance": "batch",
                "Sequential repeat": 9,
                "Sequential start": 3,
                "Sequential end": "clamp",
                "Sequential negative": True,
                "Other": "keep",
            },
        )

        script.process(p, False, "image", 1, 0, "loop", True)

        self.assertEqual(p.extra_generation_params, {"Other": "keep"})

    def test_process_records_negative_toggle_in_metadata(self):
        module, _, _ = self.load_script_module()
        script = module.Script()
        p = SimpleNamespace(extra_generation_params={})

        script.process(p, True, "image", 1, 0, "loop", False)

        self.assertFalse(p.extra_generation_params["Sequential negative"])

    def test_before_process_batch_resolves_actual_batch_and_folders(self):
        module, _, _ = self.load_script_module()
        script = module.Script()
        p = SimpleNamespace(
            batch_size=3,
            prompts=["==A|B|C=="] * 3,
            negative_prompts=[""] * 3,
            all_prompts=["==A|B|C=="] * 3,
            all_negative_prompts=[""] * 3,
            main_prompt="==A|B|C==",
            main_negative_prompt="",
            _seqprompt_output_folders={},
        )

        script.before_process_batch(
            p,
            True,
            "image",
            1,
            0,
            "loop",
            True,
            batch_number=0,
            prompts=p.prompts,
            seeds=[1, 2, 3],
            subseeds=[1, 2, 3],
        )

        self.assertEqual(p.prompts, ["A", "B", "C"])
        self.assertEqual(p.all_prompts, ["A", "B", "C"])
        self.assertEqual(p._seqprompt_output_folders, {0: "A", 1: "B", 2: "C"})


if __name__ == "__main__":
    unittest.main()
