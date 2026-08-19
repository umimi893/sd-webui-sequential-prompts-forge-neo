import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from seqprompt.folders import (
    build_folder_name,
    mark_next_grid_save,
    remember_output_folder,
    reset_grid_save_marker,
    route_image_save,
    sanitize_folder_component,
)


class FolderTests(unittest.TestCase):
    def test_sanitize_windows_forbidden_characters(self):
        self.assertEqual(
            sanitize_folder_component('<lora:umi/face?1*>'),
            'lora_umi_face_1',
        )

    def test_sanitize_path_traversal(self):
        self.assertEqual(sanitize_folder_component('..'), 'choice')
        self.assertNotIn('/', sanitize_folder_component('../secret'))
        self.assertNotIn('\\', sanitize_folder_component(r'..\\secret'))

    def test_sanitize_windows_reserved_name(self):
        self.assertEqual(sanitize_folder_component('CON'), '_CON')
        self.assertEqual(sanitize_folder_component('com1.txt'), '_com1.txt')

    def test_sanitize_windows_superscript_reserved_names(self):
        self.assertEqual(sanitize_folder_component('COM¹'), '_COM¹')
        self.assertEqual(sanitize_folder_component('lpt³.txt'), '_lpt³.txt')

    def test_unicode_component_is_bounded_by_utf8_bytes(self):
        value = '猫' * 100
        result = sanitize_folder_component(value)
        self.assertLessEqual(len(result), 64)
        self.assertLessEqual(len(result.encode('utf-8')), 180)
        self.assertIn('__', result)

    def test_combined_unicode_folder_is_bounded_by_utf8_bytes(self):
        result = build_folder_name(['猫' * 60, '犬' * 60])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertLessEqual(len(result), 120)
        self.assertLessEqual(len(result.encode('utf-8')), 220)

    def test_long_names_are_deterministically_shortened(self):
        value = 'a' * 200
        first = sanitize_folder_component(value, max_length=40)
        second = sanitize_folder_component(value, max_length=40)
        self.assertEqual(first, second)
        self.assertLessEqual(len(first), 40)
        self.assertIn('__', first)

    def test_build_folder_name_combines_marked_blocks(self):
        self.assertEqual(build_folder_name(['A', 'D']), 'A__D')

    def test_build_folder_name_returns_none_without_markers(self):
        self.assertIsNone(build_folder_name([]))

    def test_remember_output_folder_stores_per_image_mapping(self):
        p = SimpleNamespace()
        remember_output_folder(p, 2, ['C', 'F'])
        self.assertEqual(p._seqprompt_output_folders[2], 'C__F')

    def test_route_image_save_does_nothing_when_routing_is_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / '00000.png'
            p = SimpleNamespace(
                _seqprompt_folder_routing_enabled=False,
                _seqprompt_output_folders={0: 'A'},
                batch_size=1,
                iteration=0,
                batch_index=0,
                is_hr_pass=False,
            )
            params = SimpleNamespace(p=p, filename=str(original))
            route_image_save(params)
            self.assertEqual(Path(params.filename), original)

    def test_grid_marker_false_does_not_skip_sample(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = SimpleNamespace(
                _seqprompt_folder_routing_enabled=True,
                _seqprompt_output_folders={0: 'A'},
                batch_size=1,
                iteration=0,
                batch_index=0,
                is_hr_pass=False,
            )
            reset_grid_save_marker()
            mark_next_grid_save(should_save=False)
            params = SimpleNamespace(p=p, filename=str(root / '00000.png'))
            route_image_save(params)
            self.assertEqual(Path(params.filename).parent.name, 'A')

    def test_route_image_save_creates_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = SimpleNamespace(
                _seqprompt_folder_routing_enabled=True,
                _seqprompt_output_folders={1: 'B'},
                batch_size=3,
                iteration=0,
                batch_index=1,
                is_hr_pass=False,
                outpath_samples=str(root),
                outpath_grids=str(root / 'grids'),
            )
            params = SimpleNamespace(p=p, filename=str(root / '00002.png'))

            route_image_save(params)

            self.assertEqual(Path(params.filename).parent.name, 'B')
            self.assertTrue(Path(params.filename).parent.is_dir())

    def test_routing_recomputes_number_inside_destination_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = SimpleNamespace(
                _seqprompt_folder_routing_enabled=True,
                _seqprompt_output_folders={0: 'A', 1: 'A'},
                batch_size=2,
                iteration=0,
                batch_index=0,
                is_hr_pass=False,
            )

            first = SimpleNamespace(p=p, filename=str(root / '00000-same.png'))
            with patch('seqprompt.folders._forge_add_number_enabled', return_value=True):
                route_image_save(first)
            first_path = Path(first.filename)
            self.assertEqual(first_path.name, '00000-same.png')
            first_path.write_bytes(b'first')

            # The original Forge directory is still empty, so Forge itself may
            # propose 00000 again. Routing must number against A/ instead.
            p.batch_index = 1
            second = SimpleNamespace(p=p, filename=str(root / '00000-same.png'))
            with patch('seqprompt.folders._forge_add_number_enabled', return_value=True):
                route_image_save(second)
            second_path = Path(second.filename)

            self.assertEqual(second_path.name, '00001-same.png')
            self.assertNotEqual(first_path, second_path)
            self.assertEqual(first_path.read_bytes(), b'first')

    def test_routing_keeps_filename_when_forge_numbering_is_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = SimpleNamespace(
                _seqprompt_folder_routing_enabled=True,
                _seqprompt_output_folders={0: 'A'},
                batch_size=1,
                iteration=0,
                batch_index=0,
                is_hr_pass=False,
            )
            params = SimpleNamespace(p=p, filename=str(root / '00000-custom.png'))
            with patch('seqprompt.folders._forge_add_number_enabled', return_value=False):
                route_image_save(params)
            self.assertEqual(Path(params.filename).name, '00000-custom.png')

    def test_grid_marker_skips_custom_named_grid_in_shared_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = SimpleNamespace(
                _seqprompt_folder_routing_enabled=True,
                _seqprompt_output_folders={0: 'A'},
                batch_size=1,
                iteration=0,
                batch_index=0,
                is_hr_pass=False,
            )
            original = root / 'custom-grid-name-without-grid-token.png'
            params = SimpleNamespace(p=p, filename=str(original))

            reset_grid_save_marker()
            mark_next_grid_save(should_save=True)
            route_image_save(params)

            self.assertEqual(Path(params.filename), original)

    def test_grid_marker_is_consumed_only_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = SimpleNamespace(
                _seqprompt_folder_routing_enabled=True,
                _seqprompt_output_folders={0: 'A'},
                batch_size=1,
                iteration=0,
                batch_index=0,
                is_hr_pass=False,
            )
            reset_grid_save_marker()
            mark_next_grid_save(should_save=True)
            grid = SimpleNamespace(p=p, filename=str(root / 'custom.png'))
            route_image_save(grid)

            sample = SimpleNamespace(p=p, filename=str(root / '00000-sample.png'))
            route_image_save(sample)
            self.assertEqual(Path(sample.filename).parent.name, 'A')

    def test_route_image_save_uses_global_index_across_batches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = SimpleNamespace(
                _seqprompt_folder_routing_enabled=True,
                _seqprompt_output_folders={4: 'E'},
                batch_size=3,
                iteration=1,
                batch_index=1,
                is_hr_pass=False,
                outpath_samples=str(root),
                outpath_grids=str(root / 'grids'),
            )
            params = SimpleNamespace(p=p, filename=str(root / '00005.png'))

            route_image_save(params)

            self.assertEqual(Path(params.filename).parent.name, 'E')

    def test_route_image_save_skips_hires_intermediate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / '00001-before-highres-fix.png'
            p = SimpleNamespace(
                _seqprompt_folder_routing_enabled=True,
                _seqprompt_output_folders={0: 'A'},
                batch_size=1,
                iteration=0,
                batch_index=0,
                is_hr_pass=True,
                outpath_samples=str(root),
                outpath_grids=str(root / 'grids'),
            )
            params = SimpleNamespace(p=p, filename=str(original))

            route_image_save(params)

            self.assertEqual(Path(params.filename), original)

    def test_sample_filename_containing_grid_word_is_still_routed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = SimpleNamespace(
                _seqprompt_folder_routing_enabled=True,
                _seqprompt_output_folders={0: 'A'},
                batch_size=1,
                iteration=0,
                batch_index=0,
                is_hr_pass=False,
                outpath_samples=str(root),
                outpath_grids=str(root),
            )
            params = SimpleNamespace(p=p, filename=str(root / '00001-my-grid-style.png'))

            route_image_save(params)

            self.assertEqual(Path(params.filename).parent.name, 'A')

    def test_route_image_save_skips_grid_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            grid_root = root / 'grids'
            grid_root.mkdir()
            original = grid_root / 'grid-0000.png'
            p = SimpleNamespace(
                _seqprompt_folder_routing_enabled=True,
                _seqprompt_output_folders={2: 'C'},
                batch_size=3,
                iteration=0,
                batch_index=2,
                is_hr_pass=False,
                outpath_samples=str(root / 'images'),
                outpath_grids=str(grid_root),
            )
            params = SimpleNamespace(p=p, filename=str(original))

            route_image_save(params)

            self.assertEqual(Path(params.filename), original)


if __name__ == '__main__':
    unittest.main()
