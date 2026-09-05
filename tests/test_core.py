import random
import unittest

from seqprompt.core import resolve_sequential_blocks, sequence_index_for_image, split_choices


class CoreTests(unittest.TestCase):
    def test_normal_sequence(self):
        self.assertEqual(
            [resolve_sequential_blocks("==A|B|C==", i).text for i in range(4)],
            ["A", "B", "C", "A"],
        )

    def test_folder_sequence(self):
        r = resolve_sequential_blocks("===A|B|C===", 1)
        self.assertEqual((r.text, r.folder_choices, r.matched_blocks), ("B", ("B",), 1))

    def test_single_folder_marker(self):
        r = resolve_sequential_blocks("===A===", 99)
        self.assertEqual((r.text, r.folder_choices, r.matched_blocks), ("A", ("A",), 1))

    def test_single_folder_marker_decodes_escapes(self):
        r = resolve_sequential_blocks(r"===A\|B===", 0)
        self.assertEqual((r.text, r.folder_choices), ("A|B", ("A|B",)))

    def test_double_equals_without_choice_is_literal(self):
        self.assertEqual(resolve_sequential_blocks("==A==", 0).text, "==A==")

    def test_multiple_blocks_share_index(self):
        self.assertEqual(resolve_sequential_blocks("==A|B==, ==C|D==", 1).text, "B, D")

    def test_multiple_folder_blocks(self):
        r = resolve_sequential_blocks("===A|B===, ===C|D===", 1)
        self.assertEqual(r.folder_choices, ("B", "D"))

    def test_old_dollar_syntax_is_literal(self):
        self.assertEqual(resolve_sequential_blocks("$A|B$", 1).text, "$A|B$")
        self.assertEqual(resolve_sequential_blocks("$$A|B$$", 1).text, "$$A|B$$")

    def test_old_single_equals_is_literal(self):
        self.assertEqual(resolve_sequential_blocks("=A|B=", 1).text, "=A|B=")

    def test_old_brackets_are_literal(self):
        self.assertEqual(resolve_sequential_blocks("[[A|B]]", 1).text, "[[A|B]]")

    def test_escaped_pipe_equals_backslash(self):
        self.assertEqual(split_choices(r"A\|B|C\=D|E\\F"), ["A|B", "C=D", r"E\F"])

    def test_unrelated_backslashes_preserved(self):
        self.assertEqual(
            split_choices(r"C:\models\x|D:\images\y"),
            [r"C:\models\x", r"D:\images\y"],
        )

    def test_escape_outside_block_is_preserved_exactly(self):
        for text in (r"\==A|B==", r"\===A|B===", r"prefix \==A|B== suffix"):
            with self.subTest(text=text):
                r = resolve_sequential_blocks(text, 1)
                self.assertEqual(r.text, text)
                self.assertEqual(r.matched_blocks, 0)

    def test_extra_network_is_atomic(self):
        self.assertEqual(
            resolve_sequential_blocks("==<lora:x:a|b=1>|plain==", 0).text,
            "<lora:x:a|b=1>",
        )

    def test_forge_alternation_pipe_is_not_choice_separator(self):
        self.assertEqual(
            resolve_sequential_blocks("==[red|blue] hair|green hair==", 0).text,
            "[red|blue] hair",
        )

    def test_sequence_inside_forge_group(self):
        self.assertEqual(resolve_sequential_blocks("(==A|B==)", 1).text, "(B)")

    def test_dynamic_prompt_braces_are_opaque(self):
        self.assertEqual(
            resolve_sequential_blocks("{==A|B==}", 1).text,
            "{==A|B==}",
        )

    def test_dynamic_prompts_variable_is_opaque(self):
        text = "${season=!{summer|winter}}"
        self.assertEqual(resolve_sequential_blocks(text, 1).text, text)

    def test_dynamic_prompts_and_sequential_can_share_prompt(self):
        self.assertEqual(
            resolve_sequential_blocks("{red|blue}, ==front|back==", 1).text,
            "{red|blue}, back",
        )

    def test_dynamic_prompts_multi_select_is_opaque(self):
        text = "{2$$red|green|blue}, ==front|back=="
        self.assertEqual(resolve_sequential_blocks(text, 1).text, "{2$$red|green|blue}, back")

    def test_dynamic_prompts_wrap_is_opaque(self):
        text = "%{cinematic $$ {red|blue} subject}, ==front|back=="
        self.assertEqual(
            resolve_sequential_blocks(text, 1).text,
            "%{cinematic $$ {red|blue} subject}, back",
        )

    def test_adjacent_normal_blocks(self):
        self.assertEqual(resolve_sequential_blocks("==A|B====C|D==", 1).text, "BD")

    def test_adjacent_folder_blocks(self):
        r = resolve_sequential_blocks("===A|B======C|D===", 1)
        self.assertEqual((r.text, r.folder_choices), ("BD", ("B", "D")))

    def test_mixed_adjacent_blocks(self):
        normal_then_folder = resolve_sequential_blocks("==A|B=====C|D===", 1)
        self.assertEqual(
            (normal_then_folder.text, normal_then_folder.folder_choices),
            ("BD", ("D",)),
        )
        folder_then_normal = resolve_sequential_blocks("===A|B=====C|D==", 1)
        self.assertEqual(
            (folder_then_normal.text, folder_then_normal.folder_choices),
            ("BD", ("B",)),
        )

    def test_malformed_nested_fails_literal(self):
        text = "==outer ==A|B==|tail=="
        self.assertEqual(resolve_sequential_blocks(text, 1).text, text)

    def test_malformed_nested_folder_fails_literal(self):
        text = "===outer ===A=== tail==="
        self.assertEqual(resolve_sequential_blocks(text, 0).text, text)

    def test_malformed_equals_runs_fail_closed(self):
        samples = (
            "====A|B====",
            "==A|B======C|D==",
            "===A|B=======C|D===",
            "========A|B========",
        )
        for text in samples:
            with self.subTest(text=text):
                r = resolve_sequential_blocks(text, 1)
                self.assertEqual(r.text, text)
                self.assertEqual(r.matched_blocks, 0)

    def test_attached_comparison_like_text_is_literal(self):
        for text in (
            "artist==foo|bar==weight",
            "x==left|right==y",
            "name_==left|right==suffix",
        ):
            with self.subTest(text=text):
                self.assertEqual(resolve_sequential_blocks(text, 1).text, text)

    def test_empty_choice(self):
        self.assertEqual(resolve_sequential_blocks("==A||C==", 1).text, "")

    def test_clamp(self):
        self.assertEqual(resolve_sequential_blocks("==A|B|C==", 99, "clamp").text, "C")

    def test_parser_is_total_and_deterministic_for_random_text(self):
        rng = random.Random(893)
        alphabet = "abcXYZ012 =|\\[]{}()<>:$%_,-"
        for _ in range(1000):
            text = "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 120)))
            sequence_index = rng.randrange(0, 20)
            first = resolve_sequential_blocks(text, sequence_index)
            second = resolve_sequential_blocks(text, sequence_index)
            self.assertEqual(first, second)
            self.assertIsInstance(first.text, str)
            self.assertGreaterEqual(first.matched_blocks, 0)

    def test_per_image_indices(self):
        self.assertEqual(
            [sequence_index_for_image(i, 3, "image", 1, 0) for i in range(5)],
            [0, 1, 2, 3, 4],
        )

    def test_per_batch_indices(self):
        self.assertEqual(
            [sequence_index_for_image(i, 3, "batch", 1, 0) for i in range(6)],
            [0, 0, 0, 1, 1, 1],
        )

    def test_repeat_and_start(self):
        self.assertEqual(
            [sequence_index_for_image(i, 1, "image", 2, 3) for i in range(4)],
            [3, 3, 4, 4],
        )


if __name__ == "__main__":
    unittest.main()
