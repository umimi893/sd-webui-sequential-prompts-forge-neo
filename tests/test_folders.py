import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from seqprompt.folders import (
    build_folder_name,
    remember_output_folder,
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

    def test_route_image_save_skips_grid_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            grid_root = root / 'grids'
            grid_root.mkdir()
            original = grid_root / '00000-grid.png'
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
