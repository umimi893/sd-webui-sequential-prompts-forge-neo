import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from seqprompt.folders import route_image_save


class ForgeSaveContextContractTests(unittest.TestCase):
    @staticmethod
    def _make_fake_forge_save():
        namespace = {"route": route_image_save}
        exec(
            compile(
                "def save_image(params, *, grid=False, add_number=True, basename='', forced_filename=None):\n"
                "    route(params)\n"
                "    return params.filename\n",
                "C:/forge/modules/images.py",
                "exec",
            ),
            namespace,
        )
        return namespace["save_image"]

    @staticmethod
    def _processing(root: Path, mapping=None):
        return SimpleNamespace(
            _seqprompt_folder_routing_enabled=True,
            _seqprompt_output_folders=mapping or {0: "A"},
            batch_size=1,
            iteration=0,
            batch_index=0,
            is_hr_pass=False,
            outpath_samples=str(root),
            outpath_grids=str(root / "grids"),
        )

    def test_exact_live_forge_frame_routes_and_renumbers_destination(self):
        save_image = self._make_fake_forge_save()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = self._processing(root)

            first = SimpleNamespace(p=p, filename=str(root / "00000-same.png"))
            save_image(first, grid=False, add_number=True)
            first_path = Path(first.filename)
            self.assertEqual(first_path, root / "A" / "00000-same.png")
            first_path.write_bytes(b"first")

            second = SimpleNamespace(p=p, filename=str(root / "00000-same.png"))
            save_image(second, grid=False, add_number=True)
            second_path = Path(second.filename)
            self.assertEqual(second_path, root / "A" / "00001-same.png")
            self.assertEqual(first_path.read_bytes(), b"first")

    def test_exact_live_forge_grid_frame_is_not_routed(self):
        save_image = self._make_fake_forge_save()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = self._processing(root)
            original = root / "custom-grid-name.png"
            params = SimpleNamespace(p=p, filename=str(original))

            save_image(params, grid=True, add_number=True, basename="grid")

            self.assertEqual(Path(params.filename), original)

    def test_exact_live_forced_filename_frame_is_preserved(self):
        save_image = self._make_fake_forge_save()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = self._processing(root)
            params = SimpleNamespace(p=p, filename=str(root / "00000-forced.png"))

            save_image(
                params,
                grid=False,
                add_number=True,
                forced_filename="00000-forced",
            )

            self.assertEqual(Path(params.filename), root / "A" / "00000-forced.png")


if __name__ == "__main__":
    unittest.main()
