from pathlib import Path
import shutil
import subprocess

import pytest


def test_library_report_inline_frontend_behavior():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, str(root / "tests/library_report_inline_runner.cjs")],
        cwd=root, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
