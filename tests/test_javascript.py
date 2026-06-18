"""Run frontend unit tests via Node's built-in test runner."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS_TEST_DIR = ROOT / "static" / "js"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_javascript_unit_tests():
    test_files = sorted(JS_TEST_DIR.glob("*.test.js"))
    assert test_files, f"no JS test files found in {JS_TEST_DIR}"

    result = subprocess.run(
        ["node", "--test", *[str(path) for path in test_files]],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (result.stdout + "\n" + result.stderr).strip()
