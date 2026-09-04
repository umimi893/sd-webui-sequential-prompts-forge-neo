from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from seqprompt.core import resolve_sequential_blocks

try:
    from dynamicprompts.generators import RandomPromptGenerator
    from dynamicprompts.wildcards import WildcardManager
except ImportError:  # Local unit-test runs may not have the optional test dependency.
    RandomPromptGenerator = None
    WildcardManager = None


@unittest.skipIf(RandomPromptGenerator is None, "dynamicprompts test dependency is not installed")
class DynamicPromptsCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.generator = RandomPromptGenerator()

    def assert_dp_then_sequential(self, template: str) -> None:
        generated = self.generator.generate(template, num_images=6)
        self.assertGreater(len(generated), 0)
        for prompt in generated:
            self.assertIn("==front|back==", prompt)
            resolved = resolve_sequential_blocks(prompt, 1)
            self.assertEqual(resolved.matched_blocks, 1)
            self.assertNotIn("==front|back==", resolved.text)
            self.assertTrue(resolved.text.endswith("back"), resolved.text)

    def test_default_variant_and_sequential_coexist(self):
        self.assert_dp_then_sequential("{red|blue}, ==front|back==")

    def test_multi_select_dollar_syntax_and_sequential_coexist(self):
        self.assert_dp_then_sequential("{2$$red|green|blue}, ==front|back==")

    def test_variable_syntax_and_sequential_coexist(self):
        self.assert_dp_then_sequential(
            "${season=!{summer|winter}} ${season}, ==front|back=="
        )

    def test_wrap_command_and_sequential_coexist(self):
        self.assert_dp_then_sequential(
            "%{portrait of ..., cinematic$${red|blue} subject}, ==front|back=="
        )

    def test_real_wildcard_and_sequential_coexist(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "background.txt").write_text("forest\ncity\nstudio\n", encoding="utf-8")
            generator = RandomPromptGenerator(WildcardManager(Path(td)))
            generated = generator.generate("__background__, ==front|back==", num_images=6)
            for prompt in generated:
                self.assertNotIn("__background__", prompt)
                self.assertIn("==front|back==", prompt)
                resolved = resolve_sequential_blocks(prompt, 1)
                self.assertEqual(resolved.matched_blocks, 1)
                self.assertTrue(resolved.text.endswith("back"), resolved.text)

    def test_folder_marker_survives_dynamic_prompts(self):
        generated = self.generator.generate("{red|blue}, ===front|back===", num_images=4)
        for prompt in generated:
            self.assertIn("===front|back===", prompt)
            resolved = resolve_sequential_blocks(prompt, 0)
            self.assertEqual(resolved.folder_choices, ("front",))
            self.assertTrue(resolved.text.endswith("front"), resolved.text)

    def test_sequential_first_does_not_damage_dynamic_prompts_grammar(self):
        template = (
            "${season=!{summer|winter}} ${season}, "
            "{2$$red|green|blue}, ==front|back=="
        )
        sequential_first = resolve_sequential_blocks(template, 1)
        self.assertEqual(sequential_first.matched_blocks, 1)
        self.assertIn("${season=!{summer|winter}}", sequential_first.text)
        self.assertIn("{2$$red|green|blue}", sequential_first.text)
        generated = self.generator.generate(sequential_first.text, num_images=4)
        self.assertEqual(len(generated), 4)
        for prompt in generated:
            self.assertTrue(prompt.endswith("back"), prompt)
            self.assertNotIn("${season", prompt)


if __name__ == "__main__":
    unittest.main()
