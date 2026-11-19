"""算術課題の操作境界と固定テストの実行条件を検証する。"""

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from coding_agent.repair_exercise import Exercise, check_source

FIXED = "def add(a, b):\n    return a + b\n"


@pytest.fixture
def exercise(tmp_path: Path) -> Exercise:
    return Exercise(tmp_path / "project")


@pytest.mark.parametrize(
    "source",
    [
        "import os\n" + FIXED,
        "def add(a, b):\n    return __import__('os').getenv('PRIVATE')\n",
        "def add(a, b):\n    return a ** b\n",
        "def add(a, b=open('private')):\n    return a + b\n",
        "@print('private')\n" + FIXED,
        FIXED + "print('private')\n",
        "# coding: unicode_escape\n# \\nraise RuntimeError('private')\n" + FIXED,
        "def add(a, b):\n    while True: pass\n",
        "syntax error",
        " " * 4097,
    ],
)
def test_executable_source_is_limited(source: str) -> None:
    with pytest.raises(ValueError, match="Denied"):
        check_source(source)


@pytest.mark.parametrize("change", ["tests", "link"])
def test_modified_or_symlinked_tests_are_not_executed(
    exercise: Exercise, change: str
) -> None:
    tests = exercise.root / "test_calculator.py"
    if change == "link":
        tests.unlink()
        tests.symlink_to(exercise.root / "calculator.py")
    else:
        tests.write_text("raise SystemExit(0)\n")
    with pytest.raises(ValueError, match="Denied"):
        exercise.run_tests()


def test_test_process_has_no_credentials_and_has_timeout(
    exercise: Exercise, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command == [
            sys.executable,
            "-I",
            "-B",
            str(exercise.root / "test_calculator.py"),
        ]
        assert kwargs["env"] == {}
        assert kwargs["timeout"] == 5
        assert "shell" not in kwargs
        raise subprocess.TimeoutExpired(command, 5)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(subprocess.TimeoutExpired):
        exercise.run_tests()
