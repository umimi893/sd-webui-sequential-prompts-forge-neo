from __future__ import annotations

import argparse
import configparser
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXTENSION_DIR = Path(__file__).resolve().parents[1]


def _run_git(root: Path, *args: str) -> str | None:
    if not (root / ".git").exists():
        return None
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None


def _git_snapshot(root: Path | None) -> dict[str, Any] | None:
    if root is None or not root.exists():
        return None
    sha = _run_git(root, "rev-parse", "HEAD")
    branch = _run_git(root, "branch", "--show-current")
    dirty_text = _run_git(root, "status", "--porcelain")
    return {
        "commit": sha,
        "branch": branch,
        "dirty": bool(dirty_text) if dirty_text is not None else None,
    }


def _extension_version() -> str | None:
    metadata = EXTENSION_DIR / "metadata.ini"
    if not metadata.exists():
        return None
    parser = configparser.ConfigParser()
    try:
        parser.read(metadata, encoding="utf-8")
        return parser.get("Extension", "Version", fallback=None)
    except (configparser.Error, OSError):
        return None


def _infer_forge_root(explicit: str | None) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        return path if path.exists() else None

    parent = EXTENSION_DIR.parent
    if parent.name.lower() == "extensions":
        candidate = parent.parent
        if candidate.exists():
            return candidate

    return None


def _find_dynamic_prompts(forge_root: Path | None) -> Path | None:
    if forge_root is None:
        return None
    extensions = forge_root / "extensions"
    if not extensions.exists():
        return None

    preferred = [
        "sd-dynamic-prompts",
        "stable-diffusion-webui-wildcards",
    ]
    for name in preferred:
        candidate = extensions / name
        if candidate.exists():
            return candidate

    for candidate in sorted(extensions.iterdir()):
        lowered = candidate.name.lower()
        if candidate.is_dir() and "dynamic" in lowered and "prompt" in lowered:
            return candidate
    return None


def collect(forge_root_arg: str | None = None) -> dict[str, Any]:
    forge_root = _infer_forge_root(forge_root_arg)
    dynamic_prompts = _find_dynamic_prompts(forge_root)

    return {
        "schema_version": 1,
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "privacy_note": (
            "This collector does not read prompts, images, API keys, environment variables, "
            "or Forge configuration values."
        ),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
        },
        "sequential_prompts": {
            "version": _extension_version(),
            "git": _git_snapshot(EXTENSION_DIR),
        },
        "forge_neo": {
            "detected": forge_root is not None,
            "git": _git_snapshot(forge_root),
        },
        "dynamic_prompts": {
            "detected": dynamic_prompts is not None,
            "git": _git_snapshot(dynamic_prompts),
        },
    }


def _self_test() -> int:
    data = collect()
    required = {
        "schema_version",
        "collected_at_utc",
        "privacy_note",
        "platform",
        "sequential_prompts",
        "forge_neo",
        "dynamic_prompts",
    }
    if set(data) != required:
        return 1
    if data["schema_version"] != 1:
        return 1
    if not isinstance(data["platform"].get("python"), str):
        return 1
    if data["sequential_prompts"].get("version") is None:
        return 1
    json.dumps(data, ensure_ascii=False)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect privacy-conscious Sequential Prompts / Forge version diagnostics."
    )
    parser.add_argument(
        "--forge-root",
        help="Optional explicit Forge Neo root. If omitted, infer it from extensions/<this-extension>.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write JSON to this file instead of stdout.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Validate the collector itself and exit without writing diagnostics.",
    )
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    payload = collect(args.forge_root)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
