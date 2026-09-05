from __future__ import annotations

import os
import unittest
from pathlib import Path


FORGE_ROOT = os.environ.get("FORGE_NEO_CONTRACT_ROOT")
DYNAMIC_PROMPTS_ROOT = os.environ.get("DYNAMIC_PROMPTS_EXTENSION_ROOT")


def _read(root: str | None, relative: str) -> str:
    if not root:
        raise RuntimeError("contract source root is not configured")
    return (Path(root) / relative).read_text(encoding="utf-8")


def _assert_in_order(test: unittest.TestCase, text: str, markers: tuple[str, ...]) -> None:
    cursor = -1
    for marker in markers:
        position = text.find(marker, cursor + 1)
        test.assertGreaterEqual(position, 0, f"missing upstream contract marker: {marker!r}")
        test.assertGreater(position, cursor, f"upstream lifecycle order changed near: {marker!r}")
        cursor = position


@unittest.skipUnless(FORGE_ROOT, "FORGE_NEO_CONTRACT_ROOT is not configured")
class ForgeNeoUpstreamContractTests(unittest.TestCase):
    def test_process_images_lifecycle_order_matches_audited_contract(self):
        processing = _read(FORGE_ROOT, "modules/processing.py")
        start = processing.index("def process_images_inner(")
        end = processing.index("\ndef process_extra_images(", start)
        inner = processing[start:end]
        _assert_in_order(
            self,
            inner,
            (
                "p.setup_prompts()",
                "p.scripts.process(p)",
                "p.init(p.all_prompts, p.all_seeds, p.all_subseeds)",
                "p.scripts.before_process_batch(",
                "if len(p.prompts) == 0:",
                "p.parse_extra_network_prompts()",
                "extra_networks.activate(p, p.extra_network_data)",
                "p.scripts.process_batch(",
                "p.setup_conds()",
            ),
        )

    def test_before_process_batch_exceptions_are_caught_by_forge(self):
        scripts = _read(FORGE_ROOT, "modules/scripts.py")
        start = scripts.index("    def before_process_batch(self, p, **kwargs):")
        end = scripts.index("    def before_process_init_images", start)
        body = scripts[start:end]
        self.assertIn("try:", body)
        self.assertIn("script.before_process_batch", body)
        self.assertIn("except Exception:", body)
        self.assertIn("errors.report", body)

    def test_core_save_sets_batch_index_before_direct_save(self):
        processing = _read(FORGE_ROOT, "modules/processing.py")
        start = processing.index("for i, x_sample in enumerate(x_samples_ddim):")
        end = processing.index("            del x_samples_ddim", start)
        save_loop = processing[start:end]
        _assert_in_order(
            self,
            save_loop,
            (
                "p.batch_index = i",
                "images.save_image(image, p.outpath_samples",
            ),
        )

    def test_before_image_saved_still_precedes_atomic_write(self):
        images = _read(FORGE_ROOT, "modules/images.py")
        start = images.index("def save_image(")
        end = images.index("\ndef read_info_from_image", start)
        body = images[start:end]
        _assert_in_order(
            self,
            body,
            (
                "params = script_callbacks.ImageSaveParams",
                "script_callbacks.before_image_saved_callback(params)",
                "fullfn_without_extension, extension = os.path.splitext(params.filename)",
                "_atomically_save_image(image, fullfn_without_extension, extension)",
            ),
        )

    def test_hires_contract_uses_current_prompt_arrays_and_output_root(self):
        processing = _read(FORGE_ROOT, "modules/processing.py")
        self.assertIn(
            "self.outpath_samples = opts.outdir_hires_samples or self.outpath_samples",
            processing,
        )
        self.assertIn(
            "self.hr_prompts = self.all_hr_prompts[self.iteration * self.batch_size : (self.iteration + 1) * self.batch_size]",
            processing,
        )
        self.assertIn(
            "self.hr_negative_prompts = self.all_hr_negative_prompts[self.iteration * self.batch_size : (self.iteration + 1) * self.batch_size]",
            processing,
        )

    def test_prompt_matrix_still_consumes_raw_pipe_delimiters(self):
        matrix = _read(FORGE_ROOT, "scripts/prompt_matrix.py")
        self.assertIn('prompt_matrix_parts = original_prompt.split("|")', matrix)


@unittest.skipUnless(
    DYNAMIC_PROMPTS_ROOT,
    "DYNAMIC_PROMPTS_EXTENSION_ROOT is not configured",
)
class DynamicPromptsExtensionUpstreamContractTests(unittest.TestCase):
    def test_process_expands_arrays_before_restoring_template_prompt(self):
        source = _read(
            DYNAMIC_PROMPTS_ROOT,
            "sd_dynamic_prompts/dynamic_prompting.py",
        )
        start = source.index("    def process(")
        body = source[start:]
        _assert_in_order(
            self,
            body,
            (
                "all_prompts, all_negative_prompts = generate_prompts(",
                "p.all_prompts = all_prompts",
                "p.all_negative_prompts = all_negative_prompts",
                "p.prompt = original_prompt",
            ),
        )

    def test_default_configurable_delimiters_remain_separate(self):
        settings = _read(DYNAMIC_PROMPTS_ROOT, "sd_dynamic_prompts/settings.py")
        self.assertIn('key="dp_parser_variant_start"', settings)
        self.assertIn('"{",', settings)
        self.assertIn('key="dp_parser_variant_end"', settings)
        self.assertIn('"}",', settings)
        self.assertIn('key="dp_parser_wildcard_wrap"', settings)
        self.assertIn('"__",', settings)


if __name__ == "__main__":
    unittest.main()
