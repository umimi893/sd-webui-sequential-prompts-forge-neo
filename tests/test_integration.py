from __future__ import annotations

import unittest
from types import SimpleNamespace

from seqprompt.batch_integration import BatchIntegrationError, SequenceConfig
from seqprompt.integration import prepare_after_init, preparse_is_clean, resolve_current_batch

KNOWN = {"lora": "lora", "lyco": "lora"}


def make_p(*, total=3, batch_size=3, prompt="$A|B|C$", negative="neg", enable_hr=False, hr=None, hr_neg=None):
    all_prompts = [prompt] * total
    all_negatives = [negative] * total
    return SimpleNamespace(
        batch_size=batch_size,
        all_prompts=all_prompts,
        all_negative_prompts=all_negatives,
        all_seeds=list(range(10, 10 + total)),
        all_subseeds=list(range(20, 20 + total)),
        prompts=[],
        negative_prompts=[],
        seeds=[],
        subseeds=[],
        enable_hr=enable_hr,
        all_hr_prompts=list(hr if hr is not None else ([prompt] * total)) if enable_hr else None,
        all_hr_negative_prompts=list(hr_neg if hr_neg is not None else ([negative] * total)) if enable_hr else None,
        disable_extra_networks=False,
        main_prompt=all_prompts[0],
        main_negative_prompt=all_negatives[0],
    )


def slice_batch(p, n):
    s = n * p.batch_size
    e = (n + 1) * p.batch_size
    p.iteration = n
    p.prompts = p.all_prompts[s:e]
    p.negative_prompts = p.all_negative_prompts[s:e]
    p.seeds = p.all_seeds[s:e]
    p.subseeds = p.all_subseeds[s:e]


class ContractFlowTests(unittest.TestCase):
    def prepare(self, p, config=None):
        return prepare_after_init(p, config=config or SequenceConfig(), known_networks=KNOWN)

    def resolve(self, p, run, n, config=None):
        slice_batch(p, n)
        return resolve_current_batch(p, batch_number=n, run=run, known_networks=KNOWN)

    def clean(self, p, run, n, config=None):
        return preparse_is_clean(p, batch_number=n, run=run)

    def test_enabled_but_no_syntax_is_behavioral_noop_and_does_not_freeze(self):
        p = make_p(prompt="plain")
        run = self.prepare(p)
        self.assertIsNone(run)
        self.assertFalse(hasattr(p, "_seqprompt_frozen_layout"))

    def test_normal_three_image_batch_runs_end_to_end(self):
        p = make_p(total=3, batch_size=3)
        run = self.prepare(p)
        self.assertIsNotNone(run)
        result = self.resolve(p, run, 0)
        self.assertEqual(p.prompts, ["A", "B", "C"])
        self.assertEqual(p.all_prompts, ["A", "B", "C"])
        self.assertEqual(result.matched_blocks, 3)
        self.assertTrue(self.clean(p, run, 0))

    def test_partial_second_batch_stays_in_same_frozen_identity_domain(self):
        p = make_p(total=5, batch_size=3)
        run = self.prepare(p)
        self.resolve(p, run, 0)
        self.resolve(p, run, 1)
        self.assertEqual(p.prompts, ["A", "B"])
        self.assertTrue(self.clean(p, run, 1))

    def test_hr_only_sequence_can_use_readonly_plain_positive_identity_array(self):
        p = make_p(total=1, batch_size=1, prompt="plain", enable_hr=True, hr=["$H1|H2$"], hr_neg=["plain"])
        p.all_prompts = tuple(p.all_prompts)
        run = self.prepare(p)
        self.assertIsNotNone(run)
        self.resolve(p, run, 0)
        self.assertEqual(p.all_hr_prompts, ["H1"])
        self.assertEqual(p.all_prompts, ("plain",))
        self.assertTrue(self.clean(p, run, 0))

    def test_active_positive_readonly_source_is_rejected_by_activation_not_lifecycle(self):
        p = make_p(total=1, batch_size=1)
        p.all_prompts = tuple(p.all_prompts)
        with self.assertRaisesRegex(BatchIntegrationError, "read-only: all_prompts"):
            self.prepare(p)
        self.assertFalse(hasattr(p, "_seqprompt_frozen_layout"))

    def test_unsafe_per_image_lora_is_rejected_during_post_init_preflight(self):
        p = make_p(total=2, batch_size=2, prompt="$<lora:a:1>|<lora:b:1>$")
        with self.assertRaisesRegex(BatchIntegrationError, "prompt batch 1"):
            self.prepare(p)

    def test_per_batch_lora_is_allowed_and_resolved_consistently(self):
        config = SequenceConfig(advance_mode="batch")
        p = make_p(total=3, batch_size=3, prompt="$$<lora:a:1>|<lora:b:1>$$")
        run = self.prepare(p, config)
        result = self.resolve(p, run, 0, config)
        self.assertEqual(p.prompts, ["<lora:a:1>"] * 3)
        self.assertEqual(len(result.folder_choices), 3)
        self.assertTrue(self.clean(p, run, 0, config))

    def test_future_hr_sequence_does_not_trip_current_preparse_sentinel(self):
        p = make_p(total=2, batch_size=1, prompt="plain", enable_hr=True, hr=["$H1|H2$", "$H1|H2$"], hr_neg=["plain", "plain"])
        run = self.prepare(p)
        self.resolve(p, run, 0)
        self.assertEqual(p.all_hr_prompts[1], "$H1|H2$")
        self.assertTrue(self.clean(p, run, 0))

    def test_late_callback_reintroducing_sequence_is_fail_closed_by_sentinel(self):
        p = make_p(total=1, batch_size=1)
        run = self.prepare(p)
        self.resolve(p, run, 0)
        p.prompts[0] = "$late1|late2$"
        self.assertFalse(self.clean(p, run, 0))

    def test_negative_toggle_off_keeps_negative_literal_through_full_flow(self):
        config = SequenceConfig(apply_negative=False)
        p = make_p(total=1, batch_size=1, prompt="$A|B$", negative="$N1|N2$")
        run = self.prepare(p, config)
        self.resolve(p, run, 0, config)
        self.assertEqual(p.prompts, ["A"])
        self.assertEqual(p.negative_prompts, ["$N1|N2$"])
        self.assertTrue(self.clean(p, run, 0, config))


if __name__ == "__main__":
    unittest.main()
