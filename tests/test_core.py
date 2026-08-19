import unittest

from seqprompt.core import (
    expand_prompt_series,
    replace_sequential_blocks,
    sequence_index_for_image,
    split_choices,
)


class CoreTests(unittest.TestCase):
    def test_split_choices_supports_escaped_pipe(self):
        self.assertEqual(split_choices(r"A\|B|C"), ["A|B", "C"])

    def test_split_choices_supports_escaped_backslash(self):
        self.assertEqual(split_choices(r"A\\B|C"), [r"A\B", "C"])

    def test_split_choices_preserves_unrelated_backslashes(self):
        self.assertEqual(
            split_choices(r"C:\models\foo|D:\images\bar"),
            [r"C:\models\foo", r"D:\images\bar"],
        )

    def test_split_choices_preserves_trailing_backslash(self):
        self.assertEqual(split_choices("A\\|B\\"), ["A|B\\"])

    def test_basic_loop(self):
        prompt = "x [[A|B|C]] y"
        self.assertEqual(replace_sequential_blocks(prompt, 0), "x A y")
        self.assertEqual(replace_sequential_blocks(prompt, 1), "x B y")
        self.assertEqual(replace_sequential_blocks(prompt, 2), "x C y")
        self.assertEqual(replace_sequential_blocks(prompt, 3), "x A y")

    def test_clamp(self):
        self.assertEqual(
            replace_sequential_blocks("[[A|B|C]]", 99, "clamp"),
            "C",
        )

    def test_multiple_blocks_share_sequence_index(self):
        prompt = "[[red|blue|green]] hair, [[dress|shirt|coat]]"
        self.assertEqual(
            replace_sequential_blocks(prompt, 1),
            "blue hair, shirt",
        )

    def test_different_block_lengths_wrap_independently(self):
        prompt = "[[A|B]], [[1|2|3]]"
        self.assertEqual(replace_sequential_blocks(prompt, 4), "A, 2")

    def test_per_image_batch_count_sequence(self):
        prompts = ["[[A|B|C]]"] * 3
        self.assertEqual(
            expand_prompt_series(
                prompts,
                batch_size=1,
                advance_mode="image",
            ),
            ["A", "B", "C"],
        )

    def test_per_image_across_larger_batches(self):
        prompts = ["[[A|B|C]]"] * 6
        self.assertEqual(
            expand_prompt_series(
                prompts,
                batch_size=3,
                advance_mode="image",
            ),
            ["A", "B", "C", "A", "B", "C"],
        )

    def test_per_image_repeat_three(self):
        prompts = ["[[A|B|C]]"] * 9
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
        prompts = ["[[A|B|C]]"] * 9
        self.assertEqual(
            expand_prompt_series(
                prompts,
                batch_size=3,
                advance_mode="batch",
            ),
            ["A", "A", "A", "B", "B", "B", "C", "C", "C"],
        )

    def test_per_batch_repeat_two_batches(self):
        prompts = ["[[A|B|C]]"] * 12
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
