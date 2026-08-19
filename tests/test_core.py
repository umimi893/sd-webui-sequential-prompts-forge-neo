import unittest

from seqprompt.core import (
    expand_prompt_series,
    replace_sequential_blocks,
    resolve_sequential_blocks,
    sequence_index_for_image,
    split_choices,
)


class CoreTests(unittest.TestCase):
    def test_split_choices_supports_escaped_pipe(self):
        self.assertEqual(split_choices(r"A\|B|C"), ["A|B", "C"])

    def test_split_choices_supports_escaped_backslash(self):
        self.assertEqual(split_choices(r"A\\B|C"), [r"A\B", "C"])

    def test_split_choices_supports_escaped_equals(self):
        self.assertEqual(split_choices(r"A\=1|B\=2"), ["A=1", "B=2"])

    def test_split_choices_preserves_unrelated_backslashes(self):
        self.assertEqual(
            split_choices(r"C:\models\foo|D:\images\bar"),
            [r"C:\models\foo", r"D:\images\bar"],
        )

    def test_split_choices_preserves_trailing_backslash(self):
        self.assertEqual(split_choices("A\\|B\\"), ["A|B\\"])

    def test_basic_loop_equals_syntax(self):
        prompt = "x =A|B|C= y"
        self.assertEqual(replace_sequential_blocks(prompt, 0), "x A y")
        self.assertEqual(replace_sequential_blocks(prompt, 1), "x B y")
        self.assertEqual(replace_sequential_blocks(prompt, 2), "x C y")
        self.assertEqual(replace_sequential_blocks(prompt, 3), "x A y")

    def test_folder_marker_resolves_and_records_choice(self):
        resolution = resolve_sequential_blocks("==A|B|C==", 1)
        self.assertEqual(resolution.text, "B")
        self.assertEqual(resolution.folder_choices, ("B",))

    def test_folder_marker_and_normal_block_are_independent(self):
        resolution = resolve_sequential_blocks("==A|B|C==, =D|E|F=", 2)
        self.assertEqual(resolution.text, "C, F")
        self.assertEqual(resolution.folder_choices, ("C",))

    def test_multiple_folder_markers_are_all_recorded(self):
        resolution = resolve_sequential_blocks("==A|B|C==, ==D|E|F==", 1)
        self.assertEqual(resolution.text, "B, E")
        self.assertEqual(resolution.folder_choices, ("B", "E"))

    def test_normal_block_does_not_create_folder_choice(self):
        resolution = resolve_sequential_blocks("=A|B|C=", 1)
        self.assertEqual(resolution.text, "B")
        self.assertEqual(resolution.folder_choices, ())

    def test_equals_inside_folder_choice_can_be_escaped(self):
        resolution = resolve_sequential_blocks(r"==x\=1|x\=2==", 1)
        self.assertEqual(resolution.text, "x=2")
        self.assertEqual(resolution.folder_choices, ("x=2",))

    def test_single_equals_inside_double_marker_is_literal(self):
        resolution = resolve_sequential_blocks("==x=1|x=2==", 0)
        self.assertEqual(resolution.text, "x=1")
        self.assertEqual(resolution.folder_choices, ("x=1",))

    def test_legacy_syntax_still_works(self):
        prompt = "x [[A|B|C]] y"
        self.assertEqual(replace_sequential_blocks(prompt, 1), "x B y")

    def test_clamp(self):
        self.assertEqual(
            replace_sequential_blocks("=A|B|C=", 99, "clamp"),
            "C",
        )

    def test_multiple_blocks_share_sequence_index(self):
        prompt = "=red|blue|green= hair, =dress|shirt|coat="
        self.assertEqual(
            replace_sequential_blocks(prompt, 1),
            "blue hair, shirt",
        )

    def test_different_block_lengths_wrap_independently(self):
        prompt = "=A|B=, =1|2|3="
        self.assertEqual(replace_sequential_blocks(prompt, 4), "A, 2")

    def test_non_sequential_equals_text_is_untouched(self):
        prompt = "cfg=5, sampler=euler"
        self.assertEqual(replace_sequential_blocks(prompt, 0), prompt)

    def test_key_value_text_with_pipe_is_not_misparsed(self):
        prompt = "artist=foo|bar, weight=1"
        self.assertEqual(replace_sequential_blocks(prompt, 0), prompt)

    def test_spaced_assignment_with_pipe_is_not_misparsed(self):
        prompt = "foo = bar|baz = qux"
        self.assertEqual(replace_sequential_blocks(prompt, 0), prompt)

    def test_padding_spaces_inside_equals_delimiters_are_not_syntax(self):
        prompt = "= A | B ="
        self.assertEqual(replace_sequential_blocks(prompt, 0), prompt)

    def test_equals_block_can_follow_comma_without_space(self):
        prompt = "tag,=A|B=,tail"
        self.assertEqual(replace_sequential_blocks(prompt, 1), "tag,B,tail")

    def test_folder_marker_attached_to_word_is_not_misparsed(self):
        prompt = "name==A|B=="
        resolution = resolve_sequential_blocks(prompt, 0)
        self.assertEqual(resolution.text, prompt)
        self.assertEqual(resolution.folder_choices, ())

    def test_equals_block_closing_delimiter_attached_to_word_is_not_misparsed(self):
        prompt = "=A|B=tail"
        self.assertEqual(replace_sequential_blocks(prompt, 0), prompt)

    def test_folder_block_closing_delimiter_attached_to_word_is_not_misparsed(self):
        prompt = "==A|B==tail"
        resolution = resolve_sequential_blocks(prompt, 0)
        self.assertEqual(resolution.text, prompt)
        self.assertEqual(resolution.folder_choices, ())

    def test_per_image_batch_count_sequence(self):
        prompts = ["=A|B|C="] * 3
        self.assertEqual(
            expand_prompt_series(
                prompts,
                batch_size=1,
                advance_mode="image",
            ),
            ["A", "B", "C"],
        )

    def test_per_image_across_larger_batches(self):
        prompts = ["=A|B|C="] * 6
        self.assertEqual(
            expand_prompt_series(
                prompts,
                batch_size=3,
                advance_mode="image",
            ),
            ["A", "B", "C", "A", "B", "C"],
        )

    def test_per_image_repeat_three(self):
        prompts = ["=A|B|C="] * 9
        self.assertEqual(
            expand_prompt_series(
                prompts,
                batch_size=1,
                advance_mode="image",
                repeat_each=3,
            ),
            ["A", "A", "A", "B", "B", "B", "C", "C", "C"],
        )

    def test_per_batch_three_images_each(self):
        prompts = ["=A|B|C="] * 9
        self.assertEqual(
            expand_prompt_series(
                prompts,
                batch_size=3,
                advance_mode="batch",
            ),
            ["A", "A", "A", "B", "B", "B", "C", "C", "C"],
        )

    def test_per_batch_repeat_two_batches(self):
        prompts = ["=A|B|C="] * 12
        self.assertEqual(
            expand_prompt_series(
                prompts,
                batch_size=3,
                advance_mode="batch",
                repeat_each=2,
            ),
            ["A"] * 6 + ["B"] * 6,
        )

    def test_start_index(self):
        self.assertEqual(
            sequence_index_for_image(0, 1, "image", 1, 2),
            2,
        )


if __name__ == "__main__":
    unittest.main()
