"""両SDKで共有する算術課題・操作境界・固定テスト・成功判定。"""

import ast
import difflib
import subprocess
import sys
from pathlib import Path
from typing import Any

SYSTEM = (
    "Fix the addition bug in calculator.py using Read and Edit. "
    "Only calculator.py and test_calculator.py may be read. "
    "Never edit tests. The exercise permits only def add(a, b) with "
    "one return expression: a + b, a - b, or a * b. "
    "Use run_tests after editing and inspect its actual result. "
    "No shell or other tools are available. Do not claim success without "
    "a passing test result for your final edit."
)
TASK = "整数の加算関数を修正し、固定テストの成功を確認して。"

BROKEN = "def add(a, b):\n    return a - b\n"
TESTS = """import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from calculator import add

class AdditionTests(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(add(17, 25), 42)

    def test_mixed(self):
        self.assertEqual(add(-3, 5), 2)

    def test_zero(self):
        self.assertEqual(add(0, 0), 0)

    def test_negative(self):
        self.assertEqual(add(-5, -2), -7)

if __name__ == "__main__":
    unittest.main()
"""
TEST_TOOL = "run_tests"


def check_source(source: str) -> None:
    """実行可能な課題はadd(a,b)の単一算術式だけ。汎用Pythonではない。"""
    if len(source.encode("utf-8")) > 4096:
        raise ValueError("Denied: source too large.")
    try:
        # Match the parser used for importing the actual UTF-8 file, including
        # encoding cookies. Parsing a str alone could overlook a different codec.
        tree = ast.dump(ast.parse(source.encode("utf-8")))
    except SyntaxError:
        raise ValueError("Denied: invalid exercise source.") from None
    permitted = {
        ast.dump(ast.parse(f"def add(a, b):\n    return a {operator} b\n"))
        for operator in ("+", "-", "*")
    }
    if tree not in permitted:
        raise ValueError(
            "Denied: only the exercise's arithmetic expression is allowed."
        )


class Exercise:
    """アプリ所有の一時ファイル、操作境界と実テストの状態。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir()
        (root / "calculator.py").write_text(BROKEN, encoding="utf-8")
        (root / "test_calculator.py").write_text(TESTS, encoding="utf-8")
        self.test_runs = 0
        self.last_tested: str | None = None
        self.last_returncode: int | None = None

    def source(self) -> str:
        for name in ("calculator.py", "test_calculator.py"):
            path = self.root / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("Denied: exercise files must be regular files.")
        if (self.root / "test_calculator.py").read_text(encoding="utf-8") != TESTS:
            raise ValueError("Denied: fixed tests changed.")
        source = (self.root / "calculator.py").read_text(encoding="utf-8")
        check_source(source)
        return source

    def run_tests(self) -> dict[str, object]:
        source = self.source()
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(self.root / "test_calculator.py")],
            cwd=self.root,
            env={},
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.last_tested = source
        self.last_returncode = result.returncode
        return {"returncode": result.returncode, "output": result.stderr[-4096:]}

    def permits(self, name: str, arguments: dict[str, Any]) -> bool:
        if name == TEST_TOOL:
            return not arguments and self.test_runs < 4
        raw_path = arguments.get("file_path")
        if name not in {"Read", "Edit"} or not isinstance(raw_path, str):
            return False
        path = Path(raw_path)
        if not path.is_absolute():
            path = self.root / path
        # No normalization of '..' and no symlink traversal are needed or allowed.
        if path not in {self.root / "calculator.py", self.root / "test_calculator.py"}:
            return False
        if path.is_symlink() or not path.is_file():
            return False
        if name == "Read":
            return set(arguments) <= {"file_path", "offset", "limit"}
        if path.name != "calculator.py":
            return False
        if set(arguments) - {"file_path", "old_string", "new_string", "replace_all"}:
            return False
        old, new = arguments.get("old_string"), arguments.get("new_string")
        if not isinstance(old, str) or not old or not isinstance(new, str):
            return False
        if arguments.get("replace_all", False) is not False:
            return False
        source = self.source()
        if source.count(old) != 1:
            return False
        check_source(source.replace(old, new, 1))
        return True

    def checked_diff(self) -> str:
        source = self.source()
        if (
            source == BROKEN
            or self.test_runs == 0
            or self.last_tested != source
            or self.last_returncode != 0
        ):
            raise ValueError("Repair incomplete: no verified model test result.")
        if self.run_tests()["returncode"] != 0:
            raise ValueError("Repair incomplete: final tests failed.")
        return "".join(
            difflib.unified_diff(
                BROKEN.splitlines(keepends=True),
                source.splitlines(keepends=True),
                fromfile="before/calculator.py",
                tofile="after/calculator.py",
            )
        )
