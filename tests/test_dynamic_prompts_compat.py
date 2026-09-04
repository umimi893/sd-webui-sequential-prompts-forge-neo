from __future__ import annotations

import unittest

from seqprompt.core import resolve_sequential_blocks

try:
    from dynamicprompts.generators import RandomPromptGenerator
except ImportError:  # Local unit-test runs may not have the optional test dependency.
    RandomPromptGenerator = None


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

    def test_folder_marker_survives_dynamic_prompts(self):
        generated = self.generator.generate("{red|blue}, ===front|back===", num_images=4)
        for prompt in generated:
            self.assertIn("===front|back===", prompt)
            resolved = resolve_sequential_blocks(prompt, 0)
            self.assertEqual(resolved.folder_choices, ("front",))
            self.assertTrue(resolved.text.endswith("front"), resolved.text)


if __name__ == "__main__":
    unittest.main()
