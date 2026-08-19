import unittest
from types import SimpleNamespace

from seqprompt.integration import apply_processing_batch


class IntegrationTests(unittest.TestCase):
    def make_processing(self, batch_size=3):
        return SimpleNamespace(
            batch_size=batch_size,
            prompts=["=A|B|C="] * batch_size,
            negative_prompts=["=nA|nB|nC="] * batch_size,
            all_prompts=["=A|B|C="] * 9,
            all_negative_prompts=["=nA|nB|nC="] * 9,
            all_hr_prompts=["=hA|hB|hC="] * 9,
            all_hr_negative_prompts=["=hnA|hnB|hnC="] * 9,
            main_prompt="=A|B|C=",
            main_negative_prompt="=nA|nB|nC=",
            _seqprompt_output_folders={},
        )

    def apply(self, p, batch_number, *, mode="batch", apply_negative=True):
        p.prompts = p.all_prompts[
            batch_number * p.batch_size : (batch_number + 1) * p.batch_size
        ]
        p.negative_prompts = p.all_negative_prompts[
            batch_number * p.batch_size : (batch_number + 1) * p.batch_size
        ]
        apply_processing_batch(
            p,
            batch_number=batch_number,
            advance_mode=mode,
            repeat_each=1,
            start_index=0,
            end_mode="loop",
            apply_negative=apply_negative,
        )

    def test_per_batch_updates_current_and_global_prompt_lists(self):
        p = self.make_processing()
        self.apply(p, 0)
        self.apply(p, 1)
        self.apply(p, 2)

        self.assertEqual(p.all_prompts, ["A"] * 3 + ["B"] * 3 + ["C"] * 3)
        self.assertEqual(
            p.all_negative_prompts,
            ["nA"] * 3 + ["nB"] * 3 + ["nC"] * 3,
        )
        self.assertEqual(p.main_prompt, "A")
        self.assertEqual(p.main_negative_prompt, "nA")

    def test_hires_prompts_follow_same_sequence(self):
        p = self.make_processing()
        self.apply(p, 0)
        self.apply(p, 1)
        self.apply(p, 2)

        self.assertEqual(
            p.all_hr_prompts,
            ["hA"] * 3 + ["hB"] * 3 + ["hC"] * 3,
        )
        self.assertEqual(
            p.all_hr_negative_prompts,
            ["hnA"] * 3 + ["hnB"] * 3 + ["hnC"] * 3,
        )

    def test_negative_toggle_leaves_both_negative_arrays_untouched(self):
        p = self.make_processing()
        self.apply(p, 0, apply_negative=False)

        self.assertEqual(p.all_negative_prompts[:3], ["=nA|nB|nC="] * 3)
        self.assertEqual(
            p.all_hr_negative_prompts[:3],
            ["=hnA|hnB|hnC="] * 3,
        )

    def test_per_image_uses_global_image_index(self):
        p = self.make_processing()
        self.apply(p, 0, mode="image")
        self.assertEqual(p.all_prompts[:3], ["A", "B", "C"])

    def test_folder_marker_maps_each_image_in_batch(self):
        p = self.make_processing()
        p.all_prompts = ["==A|B|C==, =D|E|F="] * 3
        p.all_negative_prompts = [""] * 3
        p.all_hr_prompts = list(p.all_prompts)
        p.all_hr_negative_prompts = [""] * 3
        p.prompts = list(p.all_prompts)
        p.negative_prompts = [""] * 3

        apply_processing_batch(
            p,
            batch_number=0,
            advance_mode="image",
            repeat_each=1,
            start_index=0,
            end_mode="loop",
            apply_negative=True,
        )

        self.assertEqual(p.all_prompts, ["A, D", "B, E", "C, F"])
        self.assertEqual(p._seqprompt_output_folders, {0: "A", 1: "B", 2: "C"})

    def test_repeated_batch_hook_preserves_existing_folder_mapping(self):
        p = self.make_processing(batch_size=1)
        p.all_prompts = ["==A|B=="]
        p.all_negative_prompts = [""]
        p.all_hr_prompts = list(p.all_prompts)
        p.all_hr_negative_prompts = [""]
        p.prompts = list(p.all_prompts)
        p.negative_prompts = [""]

        apply_processing_batch(
            p,
            batch_number=0,
            advance_mode="image",
            repeat_each=1,
            start_index=0,
            end_mode="loop",
            apply_negative=True,
        )
        self.assertEqual(p._seqprompt_output_folders, {0: "A"})

        apply_processing_batch(
            p,
            batch_number=0,
            advance_mode="image",
            repeat_each=1,
            start_index=0,
            end_mode="loop",
            apply_negative=True,
        )
        self.assertEqual(p._seqprompt_output_folders, {0: "A"})

    def test_multiple_folder_markers_combine_names(self):
        p = self.make_processing()
        p.all_prompts = ["==A|B|C==, ==D|E|F=="] * 3
        p.all_negative_prompts = [""] * 3
        p.all_hr_prompts = list(p.all_prompts)
        p.all_hr_negative_prompts = [""] * 3
        p.prompts = list(p.all_prompts)
        p.negative_prompts = [""] * 3

        apply_processing_batch(
            p,
            batch_number=0,
            advance_mode="image",
            repeat_each=1,
            start_index=0,
            end_mode="loop",
            apply_negative=True,
        )

        self.assertEqual(
            p._seqprompt_output_folders,
            {0: "A__D", 1: "B__E", 2: "C__F"},
        )

    def test_normal_marker_never_creates_folder_mapping(self):
        p = self.make_processing()
        self.apply(p, 0, mode="image")
        self.assertEqual(p._seqprompt_output_folders, {})

    def test_partial_final_batch_uses_correct_global_indices_and_folders(self):
        p = self.make_processing(batch_size=3)
        p.all_prompts = ["==A|B|C=="] * 5
        p.all_negative_prompts = [""] * 5
        p.all_hr_prompts = list(p.all_prompts)
        p.all_hr_negative_prompts = [""] * 5

        p.prompts = p.all_prompts[0:3]
        p.negative_prompts = p.all_negative_prompts[0:3]
        apply_processing_batch(
            p,
            batch_number=0,
            advance_mode="image",
            repeat_each=1,
            start_index=0,
            end_mode="loop",
            apply_negative=True,
        )

        p.prompts = p.all_prompts[3:6]
        p.negative_prompts = p.all_negative_prompts[3:6]
        apply_processing_batch(
            p,
            batch_number=1,
            advance_mode="image",
            repeat_each=1,
            start_index=0,
            end_mode="loop",
            apply_negative=True,
        )

        self.assertEqual(p.all_prompts, ["A", "B", "C", "A", "B"])
        self.assertEqual(
            p._seqprompt_output_folders,
            {0: "A", 1: "B", 2: "C", 3: "A", 4: "B"},
        )

    def test_dynamic_prompt_style_expansion_can_happen_before_batch_hook(self):
        p = self.make_processing()
        p.all_prompts = [
            "photo, =red|blue|green= dress, sunny",
            "photo, =red|blue|green= dress, rainy",
            "photo, =red|blue|green= dress, snow",
        ]
        p.all_negative_prompts = [""] * 3
        p.all_hr_prompts = list(p.all_prompts)
        p.all_hr_negative_prompts = [""] * 3
        p.prompts = list(p.all_prompts)
        p.negative_prompts = [""] * 3

        apply_processing_batch(
            p,
            batch_number=0,
            advance_mode="image",
            repeat_each=1,
            start_index=0,
            end_mode="loop",
            apply_negative=True,
        )

        self.assertEqual(
            p.all_prompts,
            [
                "photo, red dress, sunny",
                "photo, blue dress, rainy",
                "photo, green dress, snow",
            ],
        )

    def test_lora_choice_is_resolved_before_forge_extra_network_parser(self):
        p = self.make_processing(batch_size=1)
        p.all_prompts = ["1girl, =<lora:a:1>|<lora:b:1>="]
        p.all_negative_prompts = [""]
        p.all_hr_prompts = list(p.all_prompts)
        p.all_hr_negative_prompts = [""]
        p.prompts = list(p.all_prompts)
        p.negative_prompts = [""]

        apply_processing_batch(
            p,
            batch_number=0,
            advance_mode="image",
            repeat_each=1,
            start_index=1,
            end_mode="loop",
            apply_negative=True,
        )

        self.assertEqual(p.prompts[0], "1girl, <lora:b:1>")
        self.assertEqual(p.all_hr_prompts[0], "1girl, <lora:b:1>")

    def test_folder_marker_with_lora_records_sanitized_folder_and_resolves_prompt(self):
        p = self.make_processing(batch_size=1)
        p.all_prompts = ["==<lora:a:1>|<lora:b:1>=="]
        p.all_negative_prompts = [""]
        p.all_hr_prompts = list(p.all_prompts)
        p.all_hr_negative_prompts = [""]
        p.prompts = list(p.all_prompts)
        p.negative_prompts = [""]

        apply_processing_batch(
            p,
            batch_number=0,
            advance_mode="image",
            repeat_each=1,
            start_index=1,
            end_mode="loop",
            apply_negative=True,
        )

        self.assertEqual(p.prompts[0], "<lora:b:1>")
        self.assertEqual(p._seqprompt_output_folders, {0: "lora_b_1"})

    def test_negative_folder_marker_never_controls_output_folder(self):
        p = self.make_processing(batch_size=1)
        p.all_prompts = ["=A|B="]
        p.all_negative_prompts = ["==nA|nB=="]
        p.all_hr_prompts = list(p.all_prompts)
        p.all_hr_negative_prompts = list(p.all_negative_prompts)
        p.prompts = list(p.all_prompts)
        p.negative_prompts = list(p.all_negative_prompts)
        p._seqprompt_output_folders = {}

        apply_processing_batch(
            p,
            batch_number=0,
            advance_mode="image",
            repeat_each=1,
            start_index=1,
            end_mode="loop",
            apply_negative=True,
        )

        self.assertEqual(p.negative_prompts[0], "nB")
        self.assertEqual(p._seqprompt_output_folders, {})

    def test_hires_only_folder_marker_never_controls_output_folder(self):
        p = self.make_processing(batch_size=1)
        p.all_prompts = ["=A|B="]
        p.all_negative_prompts = [""]
        p.all_hr_prompts = ["==hA|hB=="]
        p.all_hr_negative_prompts = [""]
        p.prompts = list(p.all_prompts)
        p.negative_prompts = [""]
        p._seqprompt_output_folders = {}

        apply_processing_batch(
            p,
            batch_number=0,
            advance_mode="image",
            repeat_each=1,
            start_index=1,
            end_mode="loop",
            apply_negative=True,
        )

        self.assertEqual(p.all_hr_prompts[0], "hB")
        self.assertEqual(p._seqprompt_output_folders, {})

    def test_legacy_bracket_syntax_still_works_integration(self):
        p = self.make_processing(batch_size=1)
        p.all_prompts = ["1girl, [[red|blue]] hair"]
        p.all_negative_prompts = [""]
        p.all_hr_prompts = list(p.all_prompts)
        p.all_hr_negative_prompts = [""]
        p.prompts = list(p.all_prompts)
        p.negative_prompts = [""]

        apply_processing_batch(
            p,
            batch_number=0,
            advance_mode="image",
            repeat_each=1,
            start_index=1,
            end_mode="loop",
            apply_negative=True,
        )

        self.assertEqual(p.prompts[0], "1girl, blue hair")


if __name__ == "__main__":
    unittest.main()
