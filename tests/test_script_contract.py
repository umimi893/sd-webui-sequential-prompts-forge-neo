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

        class FakeScript:
            pass

        fake_scripts.Script = FakeScript
        fake_scripts.AlwaysVisible = object()
        fake_modules.scripts = fake_scripts

        script_path = Path(__file__).parents[1] / "scripts" / "sequential_prompts.py"
        spec = importlib.util.spec_from_file_location("sequential_prompts_contract", script_path)
        module = importlib.util.module_from_spec(spec)

        with patch.dict(
            sys.modules,
            {
                "gradio": fake_gradio,
                "modules": fake_modules,
                "modules.scripts": fake_scripts,
            },
        ):
            assert spec.loader is not None
            spec.loader.exec_module(module)

        return module, fake_scripts

    def test_script_is_always_visible(self):
        module, fake_scripts = self.load_script_module()
        script = module.Script()
        self.assertIs(script.show(False), fake_scripts.AlwaysVisible)
        self.assertIs(script.show(True), fake_scripts.AlwaysVisible)

    def test_process_records_metadata_without_destroying_template(self):
        module, _ = self.load_script_module()
        script = module.Script()
        p = SimpleNamespace(
            all_prompts=["[[A|B|C]]"],
            extra_generation_params={},
        )

        script.process(p, True, "image", 1, 0, "loop", True)

        self.assertEqual(p.all_prompts, ["[[A|B|C]]"])
        self.assertEqual(p.extra_generation_params["Sequential advance"], "image")

    def test_before_process_batch_resolves_actual_batch(self):
        module, _ = self.load_script_module()
        script = module.Script()
        p = SimpleNamespace(
            batch_size=3,
            prompts=["[[A|B|C]]"] * 3,
            negative_prompts=[""] * 3,
            all_prompts=["[[A|B|C]]"] * 3,
            all_negative_prompts=[""] * 3,
            main_prompt="[[A|B|C]]",
            main_negative_prompt="",
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


if __name__ == "__main__":
    unittest.main()
