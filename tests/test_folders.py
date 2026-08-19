import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import seqprompt.folders as folders_module
from seqprompt.folders import (
    ForgeSaveContext,
    build_folder_name,
    remember_output_folder,
    route_image_save,
    sanitize_folder_component,
)


class FolderTests(unittest.TestCase):
    @staticmethod
    def _fake_frame(name, filename, back=None, locals_dict=None):
        return SimpleNamespace(
            f_code=SimpleNamespace(co_name=name, co_filename=filename),
            f_back=back,
            f_locals=locals_dict or {},
        )

    def test_forge_save_context_reads_grid_and_numbering_locals(self):
        save_frame = self._fake_frame(
            'save_image',
            'C:/forge/modules/images.py',
            locals_dict={
                'grid': True,
                'add_number': True,
                'basename': 'grid',
                'forced_filename': None,
            },
        )
        dispatch = self._fake_frame(
            'before_image_saved_callback',
            'C:/forge/modules/script_callbacks.py',
            save_frame,
        )
        helper = self._fake_frame('_forge_save_context', __file__, dispatch)

        with patch.object(folders_module.inspect, 'currentframe', return_value=helper):
            context = folders_module._forge_save_context()

        self.assertEqual(
            context,
            ForgeSaveContext(
                grid=True,
                add_number=True,
                basename='grid',
                forced_filename=None,
            ),
        )

    def test_forge_save_context_reads_real_python_frame_locals(self):
        namespace = {}
        code = compile(
            "def save_image(callback):\n"
            "    grid = False\n"
            "    add_number = True\n"
            "    basename = ''\n"
            "    forced_filename = None\n"
            "    return callback()\n",
            'C:/forge/modules/images.py',
            'exec',
        )
        exec(code, namespace)
        context = namespace['save_image'](folders_module._forge_save_context)
        self.assertEqual(
            context,
            ForgeSaveContext(
                grid=False, add_number=True, basename='', forced_filename=None
            ),
        )

    def test_forge_save_context_reads_real_compiled_save_image_frame(self):
        namespace = {"callback": folders_module._forge_save_context}
        exec(
            compile(
                "def save_image():\n"
                "    grid = False\n"
                "    add_number = True\n"
                "    basename = 'sample'\n"
                "    forced_filename = None\n"
                "    return callback()\n",
                "C:/forge/modules/images.py",
                "exec",
            ),
            namespace,
        )

        context = namespace["save_image"]()
        self.assertEqual(
            context,
            ForgeSaveContext(
                grid=False,
                add_number=True,
                basename="sample",
                forced_filename=None,
            ),
        )

    def test_forge_save_context_returns_none_outside_forge_save(self):
        caller = self._fake_frame('something_else', 'C:/other.py')
        helper = self._fake_frame('_forge_save_context', __file__, caller)
        with patch.object(folders_module.inspect, 'currentframe', return_value=helper):
            self.assertIsNone(folders_module._forge_save_context())

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

    def test_sanitize_additional_windows_device_names(self):
        self.assertEqual(sanitize_folder_component('CONIN$'), '_CONIN$')
        self.assertEqual(sanitize_folder_component('CONOUT$'), '_CONOUT$')

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

    def test_exact_forge_grid_flag_skips_shared_custom_grid_name(self):
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
            original = root / 'totally-custom-name.png'
            params = SimpleNamespace(p=p, filename=str(original))
            context = ForgeSaveContext(grid=True, add_number=False, basename='grid')
            with patch('seqprompt.folders._forge_save_context', return_value=context):
                route_image_save(params)
            self.assertEqual(Path(params.filename), original)

    def test_partial_save_context_falls_back_to_grid_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            grid_root = root / 'grids'
            grid_root.mkdir()
            p = SimpleNamespace(
                _seqprompt_folder_routing_enabled=True,
                _seqprompt_output_folders={0: 'A'},
                batch_size=1,
                iteration=0,
                batch_index=0,
                is_hr_pass=False,
                outpath_samples=str(root / 'images'),
                outpath_grids=str(grid_root),
            )
            original = grid_root / 'custom-name.png'
            params = SimpleNamespace(p=p, filename=str(original))
            context = ForgeSaveContext(grid=None, add_number=True, basename='grid')
            with patch('seqprompt.folders._forge_save_context', return_value=context):
                route_image_save(params)
            self.assertEqual(Path(params.filename), original)

    def test_exact_non_grid_context_ignores_grid_like_sample_filename(self):
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
            params = SimpleNamespace(p=p, filename=str(root / 'grid-custom.png'))
            context = ForgeSaveContext(grid=False, add_number=False, basename='')
            with patch('seqprompt.folders._forge_save_context', return_value=context):
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
            context = ForgeSaveContext(grid=False, add_number=True, basename='')

            first = SimpleNamespace(p=p, filename=str(root / '00000-same.png'))
            with patch('seqprompt.folders._forge_save_context', return_value=context):
                route_image_save(first)
            first_path = Path(first.filename)
            self.assertEqual(first_path.name, '00000-same.png')
            first_path.write_bytes(b'first')

            p.batch_index = 1
            second = SimpleNamespace(p=p, filename=str(root / '00000-same.png'))
            with patch('seqprompt.folders._forge_save_context', return_value=context):
                route_image_save(second)
            second_path = Path(second.filename)

            self.assertEqual(second_path.name, '00001-same.png')
            self.assertNotEqual(first_path, second_path)
            self.assertEqual(first_path.read_bytes(), b'first')

    def test_numbering_with_nonempty_basename_matches_forge_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            choice = root / 'A'
            choice.mkdir()
            (choice / 'mask-0000-extra.png').write_bytes(b'first')
            p = SimpleNamespace(
                _seqprompt_folder_routing_enabled=True,
                _seqprompt_output_folders={0: 'A'},
                batch_size=1,
                iteration=0,
                batch_index=0,
                is_hr_pass=False,
                outpath_samples=str(root),
                outpath_grids=str(root / 'grids'),
            )
            params = SimpleNamespace(p=p, filename=str(root / 'mask-0000-extra.png'))
            context = ForgeSaveContext(
                grid=False, add_number=True, basename='mask', forced_filename=None
            )
            with patch('seqprompt.folders._forge_save_context', return_value=context):
                route_image_save(params)
            self.assertEqual(Path(params.filename).name, 'mask-0001-extra.png')

    def test_forced_filename_is_never_reinterpreted_as_numbered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            choice = root / 'A'
            choice.mkdir()
            (choice / '00000-forced.png').write_bytes(b'first')
            p = SimpleNamespace(
                _seqprompt_folder_routing_enabled=True,
                _seqprompt_output_folders={0: 'A'},
                batch_size=1,
                iteration=0,
                batch_index=0,
                is_hr_pass=False,
                outpath_samples=str(root),
                outpath_grids=str(root / 'grids'),
            )
            params = SimpleNamespace(p=p, filename=str(root / '00000-forced.png'))
            context = ForgeSaveContext(
                grid=False,
                add_number=None,
                basename='',
                forced_filename='00000-forced',
            )
            with patch('seqprompt.folders._forge_save_context', return_value=context), patch(
                'seqprompt.folders._forge_add_number_enabled', return_value=True
            ):
                route_image_save(params)
            self.assertEqual(Path(params.filename).name, '00000-forced.png')

    def test_exact_context_preserves_filename_when_forge_numbering_is_disabled(self):
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
            params = SimpleNamespace(p=p, filename=str(root / '1234567890-custom.png'))
            context = ForgeSaveContext(grid=False, add_number=False, basename='')
            with patch('seqprompt.folders._forge_save_context', return_value=context):
                route_image_save(params)
            self.assertEqual(Path(params.filename).name, '1234567890-custom.png')

    def test_fallback_numbering_off_does_not_reinterpret_numeric_seed_as_counter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            choice = root / 'A'
            choice.mkdir()
            (choice / '1234567890-same.png').write_bytes(b'first')
            p = SimpleNamespace(
                _seqprompt_folder_routing_enabled=True,
                _seqprompt_output_folders={0: 'A'},
                batch_size=1,
                iteration=0,
                batch_index=0,
                is_hr_pass=False,
                override_settings={},
                outpath_samples=str(root),
                outpath_grids=str(root / 'grids'),
            )
            params = SimpleNamespace(p=p, filename=str(root / '1234567890-same.png'))
            with patch('seqprompt.folders._forge_save_context', return_value=None), patch(
                'seqprompt.folders._forge_add_number_enabled', return_value=False
            ):
                route_image_save(params)
            self.assertEqual(Path(params.filename).name, '1234567890-same.png')

    def test_fallback_explicit_empty_filename_pattern_keeps_forced_numbering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            choice = root / 'A'
            choice.mkdir()
            (choice / '00000.png').write_bytes(b'first')
            p = SimpleNamespace(
                _seqprompt_folder_routing_enabled=True,
                _seqprompt_output_folders={0: 'A'},
                batch_size=1,
                iteration=0,
                batch_index=0,
                is_hr_pass=False,
                override_settings={'samples_filename_pattern': ''},
                outpath_samples=str(root),
                outpath_grids=str(root / 'grids'),
            )
            params = SimpleNamespace(p=p, filename=str(root / '00000.png'))
            with patch('seqprompt.folders._forge_save_context', return_value=None), patch(
                'seqprompt.folders._forge_add_number_enabled', return_value=False
            ):
                route_image_save(params)
            self.assertEqual(Path(params.filename).name, '00001.png')

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

    def test_exact_sample_context_routes_grid_like_filename_in_shared_root(self):
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
            context = ForgeSaveContext(grid=False, add_number=False, basename='')
            with patch('seqprompt.folders._forge_save_context', return_value=context):
                route_image_save(params)

            self.assertEqual(Path(params.filename).parent.name, 'A')

    def test_shared_root_fallback_fails_closed_when_context_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / 'totally-custom-sample-name.png'
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
            params = SimpleNamespace(p=p, filename=str(original))
            with patch('seqprompt.folders._forge_save_context', return_value=None):
                route_image_save(params)
            self.assertEqual(Path(params.filename), original)

    def test_distinct_grid_root_is_skipped_when_save_context_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            grid_root = root / 'grids'
            grid_root.mkdir()
            original = grid_root / 'totally-custom-name.png'
            p = SimpleNamespace(
                _seqprompt_folder_routing_enabled=True,
                _seqprompt_output_folders={0: 'A'},
                batch_size=1,
                iteration=0,
                batch_index=0,
                is_hr_pass=False,
                outpath_samples=str(root / 'images'),
                outpath_grids=str(grid_root),
            )
            params = SimpleNamespace(p=p, filename=str(original))
            with patch('seqprompt.folders._forge_save_context', return_value=None):
                route_image_save(params)
            self.assertEqual(Path(params.filename), original)

    def test_sample_root_nested_under_grid_root_is_not_misclassified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample_root = root / 'outputs' / 'images'
            sample_root.mkdir(parents=True)
            p = SimpleNamespace(
                _seqprompt_folder_routing_enabled=True,
                _seqprompt_output_folders={0: 'A'},
                batch_size=1,
                iteration=0,
                batch_index=0,
                is_hr_pass=False,
                outpath_samples=str(sample_root),
                outpath_grids=str(root / 'outputs'),
            )
            params = SimpleNamespace(p=p, filename=str(sample_root / '00000.png'))
            with patch('seqprompt.folders._forge_save_context', return_value=None):
                route_image_save(params)
            self.assertEqual(Path(params.filename).parent.name, 'A')

    def test_grid_root_nested_under_sample_root_is_classified_as_grid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample_root = root / 'outputs'
            grid_root = sample_root / 'grids'
            grid_root.mkdir(parents=True)
            original = grid_root / 'custom.png'
            p = SimpleNamespace(
                _seqprompt_folder_routing_enabled=True,
                _seqprompt_output_folders={0: 'A'},
                batch_size=1,
                iteration=0,
                batch_index=0,
                is_hr_pass=False,
                outpath_samples=str(sample_root),
                outpath_grids=str(grid_root),
            )
            params = SimpleNamespace(p=p, filename=str(original))
            with patch('seqprompt.folders._forge_save_context', return_value=None):
                route_image_save(params)
            self.assertEqual(Path(params.filename), original)

    def test_route_callback_is_idempotent_for_same_params_object(self):
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
                outpath_grids=str(root / 'grids'),
            )
            params = SimpleNamespace(p=p, filename=str(root / '00000.png'))
            context = ForgeSaveContext(grid=False, add_number=False, basename='')
            with patch('seqprompt.folders._forge_save_context', return_value=context):
                route_image_save(params)
                route_image_save(params)

            routed = Path(params.filename)
            self.assertEqual(routed.parent, root / 'A')
            self.assertNotEqual(routed.parent, root / 'A' / 'A')

    def test_grid_skip_is_idempotent_for_same_params_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / 'custom-grid-output.png'
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
            params = SimpleNamespace(p=p, filename=str(original))
            context = ForgeSaveContext(grid=True, add_number=False, basename='grid')
            with patch('seqprompt.folders._forge_save_context', return_value=context):
                route_image_save(params)
                route_image_save(params)

            self.assertEqual(Path(params.filename), original)

    def test_long_parent_path_shortens_choice_folder_before_forge_full_path_slice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = SimpleNamespace(
                _seqprompt_folder_routing_enabled=True,
                _seqprompt_output_folders={0: 'very-long-choice-folder-name'},
                batch_size=1,
                iteration=0,
                batch_index=0,
                is_hr_pass=False,
                outpath_samples=str(root),
                outpath_grids=str(root / 'grids'),
            )
            source = root / '00000.png'
            params = SimpleNamespace(p=p, filename=str(source))

            fake_limit = len(str(root)) + len(source.stem) + 20
            context = ForgeSaveContext(grid=False, add_number=False, basename='')
            with patch(
                'seqprompt.folders.os.statvfs',
                return_value=SimpleNamespace(f_namemax=fake_limit),
                create=True,
            ), patch('seqprompt.folders._forge_save_context', return_value=context):
                route_image_save(params)

            routed = Path(params.filename)
            self.assertNotEqual(routed.parent.name, 'very-long-choice-folder-name')
            forge_slice_limit = fake_limit - 4
            self.assertLessEqual(
                len(str(routed.parent)) + 1 + len(routed.stem),
                forge_slice_limit,
            )
            self.assertTrue(routed.parent.is_dir())

    def test_routing_is_skipped_if_forge_parent_leaves_no_safe_folder_budget(self):
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
                outpath_grids=str(root / 'grids'),
            )
            source = root / '00000.png'
            params = SimpleNamespace(p=p, filename=str(source))

            fake_limit = len(str(root)) + len(source.stem) + 6
            context = ForgeSaveContext(grid=False, add_number=False, basename='')
            with patch(
                'seqprompt.folders.os.statvfs',
                return_value=SimpleNamespace(f_namemax=fake_limit),
                create=True,
            ), patch('seqprompt.folders._forge_save_context', return_value=context):
                route_image_save(params)

            self.assertEqual(Path(params.filename), source)

    def test_route_image_save_skips_grid_filename_in_fallback_mode(self):
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
            with patch('seqprompt.folders._forge_save_context', return_value=None):
                route_image_save(params)

            self.assertEqual(Path(params.filename), original)


if __name__ == '__main__':
    unittest.main()
