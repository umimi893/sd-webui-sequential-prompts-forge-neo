from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from seqprompt import folders as sr


class Layout:
    def __init__(self, batch_size: int, total: int):
        self.batch_size = batch_size
        self.total = total


class Params(SimpleNamespace):
    pass


def make_p(root: Path, *, batch_size=3, total=3):
    p = SimpleNamespace(
        _seqprompt_owner_id=None,
        _seqprompt_folder_routing_enabled=True,
        _seqprompt_frozen_layout=Layout(batch_size, total),
        _seqprompt_output_folders={},
        _seqprompt_output_identities={},
        outpath_samples=str(root),
        iteration=0,
        batch_index=0,
        prompts=[], negative_prompts=[], seeds=[], subseeds=[],
        is_hr_pass=False,
    )
    p._seqprompt_owner_id = id(p)
    return p


def set_batch(p, prompts, negatives=None, seeds=None, subseeds=None):
    n = len(prompts)
    p.prompts = list(prompts)
    p.negative_prompts = list(negatives if negatives is not None else [""] * n)
    p.seeds = list(seeds if seeds is not None else range(100, 100 + n))
    p.subseeds = list(subseeds if subseeds is not None else range(200, 200 + n))


def remember_batch(p, folders):
    start = p.iteration * p._seqprompt_frozen_layout.batch_size
    for i in range(len(p.prompts)):
        gi = start + i
        sr.remember_output_identity(
            p, gi,
            prompt=p.prompts[i], negative_prompt=p.negative_prompts[i],
            seed=p.seeds[i], subseed=p.subseeds[i],
        )
        if folders[i] is not None:
            sr.remember_output_folder(p, gi, (folders[i],))


def sample_context(**kwargs):
    data = dict(
        grid=False, add_number=True, basename="", forced_filename=None,
        core_processing_save=True, core_video=False,
    )
    data.update(kwargs)
    return sr.ForgeSaveContext(**data)


class FolderTests(unittest.TestCase):
    def prepare(self, root: Path, *, filename="00000-x.png", folder="A"):
        p = make_p(root, batch_size=1, total=1)
        set_batch(p, ["prompt"], seeds=[1], subseeds=[2])
        remember_batch(p, [folder])
        return p, Params(p=p, filename=str(root / filename))

    def test_plain_unicode_and_empty_are_readable(self):
        self.assertEqual(sr.sanitize_folder_component("正面✨"), "正面✨")
        self.assertEqual(sr.sanitize_folder_component(""), "empty")

    def test_windows_reserved_and_invalid_chars_are_safe(self):
        self.assertEqual(sr.sanitize_folder_component("CON"), "_CON")
        out = sr.sanitize_folder_component('<lora:a/b?c*:1>')
        self.assertNotRegex(out, r'[<>:"/\\|?*]')

    def test_long_unicode_is_byte_bounded(self):
        out = sr.build_folder_name(["正" * 100, "側" * 100])
        self.assertIsNotNone(out)
        self.assertLessEqual(len(out), 120)
        self.assertLessEqual(len(out.encode("utf-8")), 220)

    def test_lossy_names_are_stably_distinct(self):
        a = sr.build_folder_name(("A/B",))
        b = sr.build_folder_name(("A\\B",))
        self.assertNotEqual(a.casefold(), b.casefold())
        self.assertEqual(sr.build_folder_name(("front",)), "front")

    def test_multiple_folder_choices_join(self):
        self.assertEqual(sr.build_folder_name(["A", "D"]), "A__D")

    def test_reorder_follows_metadata_identity(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_p(Path(td), batch_size=3, total=3)
            set_batch(p, ["A", "B", "C"], seeds=[1,2,3], subseeds=[11,12,13])
            remember_batch(p, ["A", "B", "C"])
            set_batch(p, ["C", "A", "B"], seeds=[3,1,2], subseeds=[13,11,12])
            self.assertEqual(sr._folder_for_live_slot(p, iteration=0, batch_index=0), "C")
            self.assertEqual(sr._folder_for_live_slot(p, iteration=0, batch_index=1), "A")

    def test_ambiguous_identical_identity_skips_routing(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_p(Path(td), batch_size=2, total=2)
            set_batch(p, ["same", "same"], seeds=[1,1], subseeds=[2,2])
            for i in (0,1):
                sr.remember_output_identity(p, i, prompt="same", negative_prompt="", seed=1, subseed=2)
            sr.remember_output_folder(p, 0, ("A",))
            self.assertIsNone(sr._folder_for_live_slot(p, iteration=0, batch_index=0))

    def test_second_iteration_uses_frozen_global_domain(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_p(Path(td), batch_size=2, total=4)
            p.iteration = 1
            set_batch(p, ["C", "D"], seeds=[3,4], subseeds=[13,14])
            remember_batch(p, ["C", "D"])
            self.assertEqual(sr._folder_for_live_slot(p, iteration=1, batch_index=1), "D")

    def test_destination_numbering_uses_destination_contents(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dest = root / "A"; dest.mkdir()
            (dest / "00000-x.png").touch(); (dest / "00002-x.png").touch()
            self.assertEqual(sr._renumber_for_destination(root / "00000-x.png", dest, context=sample_context()), "00003-x.png")

    def test_nonnumbered_and_forced_names_are_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dest = root / "A"; dest.mkdir()
            self.assertEqual(sr._renumber_for_destination(root / "custom.png", dest, context=sample_context(add_number=False)), "custom.png")
            self.assertEqual(sr._renumber_for_destination(root / "forced.png", dest, context=sample_context(add_number=None, forced_filename="forced")), "forced.png")

    def test_normal_core_sample_routes(self):
        with tempfile.TemporaryDirectory() as td:
            _, params = self.prepare(Path(td))
            self.assertTrue(sr.route_with_context(params, sample_context()))
            self.assertEqual(Path(params.filename).parent.name, "A")

    def test_auxiliary_core_saves_route(self):
        for suffix in ("-before-face-restoration", "-before-color-correction", "-mask", "-mask-composite"):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as td:
                _, params = self.prepare(Path(td), filename=f"00000-x{suffix}.png")
                self.assertTrue(sr.route_with_context(params, sample_context()))
                self.assertEqual(Path(params.filename).parent.name, "A")

    def test_save_to_dirs_nests_choice(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); forge_dir = root / "prompt_words"; forge_dir.mkdir()
            _, params = self.prepare(root)
            params.filename = str(forge_dir / "00000-x.png")
            self.assertTrue(sr.route_with_context(params, sample_context()))
            self.assertEqual(Path(params.filename).parent, forge_dir / "A")

    def test_grid_video_manual_and_hires_intermediate_do_not_route(self):
        with tempfile.TemporaryDirectory() as td:
            p, params = self.prepare(Path(td))
            self.assertFalse(sr.route_with_context(params, sample_context(grid=True, basename="grid")))
        with tempfile.TemporaryDirectory() as td:
            _, params = self.prepare(Path(td))
            self.assertFalse(sr.route_with_context(params, sample_context(core_video=True)))
        with tempfile.TemporaryDirectory() as td:
            _, params = self.prepare(Path(td))
            self.assertFalse(sr.route_with_context(params, sample_context(core_processing_save=False)))
        with tempfile.TemporaryDirectory() as td:
            p, params = self.prepare(Path(td)); p.is_hr_pass = True
            self.assertFalse(sr.route_with_context(params, sample_context()))

    def test_path_outside_sample_root_does_not_route(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as other:
            _, params = self.prepare(Path(td))
            params.filename = str(Path(other) / "00000-x.png")
            self.assertFalse(sr.route_with_context(params, sample_context()))

    def test_duplicate_callback_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            _, params = self.prepare(Path(td))
            self.assertTrue(sr.route_with_context(params, sample_context()))
            first = params.filename
            self.assertFalse(sr.route_with_context(params, sample_context()))
            self.assertEqual(params.filename, first)

    def test_missing_frozen_layout_does_not_route(self):
        with tempfile.TemporaryDirectory() as td:
            p, params = self.prepare(Path(td)); p._seqprompt_frozen_layout = None
            self.assertFalse(sr.route_with_context(params, sample_context()))

    def test_unknown_numbering_context_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dest = root / "A"; dest.mkdir()
            self.assertIsNone(sr._renumber_for_destination(root / "00000-x.png", dest, context=sample_context(add_number=None)))


if __name__ == "__main__":
    unittest.main()
