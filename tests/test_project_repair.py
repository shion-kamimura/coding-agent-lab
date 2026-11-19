"""指定プロジェクトの操作境界と、実SDKを使うオフライン検証。"""

import json
import sys
from pathlib import Path

import httpx2
import pytest

from coding_agent.file_tools import FileTools
from coding_agent.project_repair import _Project, repair_project
from tests.test_client_repair import call
from tests.test_tool_use import MockSDK, body

READABLE = ("src/price.py", "tests/check.py", "requirements.txt")
EDITABLE = "src/price.py"
TEST_FILES = ("tests/check.py",)
COMMAND = (sys.executable, "-I", "-B", TEST_FILES[0])
BROKEN = "def total(price, fee):\n    return price - fee\n"


@pytest.fixture
def practice(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / EDITABLE).write_text(BROKEN, encoding="utf-8")
    (tmp_path / "requirements.txt").write_text(
        "The service fee is added to the price.\n", encoding="utf-8"
    )
    (tmp_path / "private.txt").write_text("outside the allowlist", encoding="utf-8")
    (tmp_path / TEST_FILES[0]).write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path.cwd() / 'src'))\n"
        "from price import total\n"
        "assert total(12, 3) == 15, 'incorrect total'\n"
        "print('price check passed')\n",
        encoding="utf-8",
    )
    return tmp_path


def replacement(old: str, new: str) -> dict[str, str]:
    return {"file_path": EDITABLE, "old_string": old, "new_string": new}


def test_project_repair(mock_sdk: MockSDK, practice: Path) -> None:
    contents: list[list[dict[str, object]]] = [
        [call("Read", {"file_path": path}, index)]
        for index, path in enumerate(READABLE)
    ]
    contents += [
        [call("Edit", replacement("price - fee", "price * fee"), 3)],
        [call("run_tests", {}, 4)],
        [call("Edit", replacement("price * fee", "price + fee"), 5)],
        [call("run_tests", {}, 6)],
        [{"type": "text", "text": "Fixed and tested."}],
    ]
    results = [
        {"text": (practice / path).read_text(encoding="utf-8")} for path in READABLE
    ]
    index = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal index
        payload = json.loads(request.content)
        assert all(path in payload["messages"][0]["content"] for path in READABLE)
        if index:
            messages = payload["messages"]
            assert messages[-2]["content"] == contents[index - 1]
            result = messages[-1]["content"][0]
            assert result["tool_use_id"] == f"tool_{index - 1}"
            output = json.loads(result["content"])
            if index <= len(results):
                assert output == results[index - 1]
            if index == 5:
                assert output["returncode"] != 0
                assert "incorrect total" in output["stderr"]
            if index == 7:
                assert output["returncode"] == 0
                assert "price check passed" in output["stdout"]
        content = contents[index]
        index += 1
        return httpx2.Response(
            200,
            json=body(content, "end_turn" if index == len(contents) else "tool_use"),
        )

    mock_sdk(handler)
    summary = repair_project(
        practice,
        task="Fix the service fee calculation based on the project files.",
        readable_files=READABLE,
        editable_file=EDITABLE,
        test_files=TEST_FILES,
        test_command=COMMAND,
        test_timeout=5,
    )
    assert index == len(contents)
    assert '"returncode": 0' in summary
    assert "--- before/src/price.py" in summary
    assert "-    return price - fee\n+    return price + fee" in summary
    assert (practice / EDITABLE).read_text(encoding="utf-8") == BROKEN.replace("-", "+")
    assert (practice / TEST_FILES[0]).read_text(encoding="utf-8") == results[1]["text"]


def test_permissions_are_independent(practice: Path) -> None:
    with FileTools(practice, READABLE[1:]) as reader:
        project = _Project(practice, reader, EDITABLE, TEST_FILES, COMMAND, 5)
        for name, arguments in [
            ("Read", {"file_path": "private.txt"}),
            ("Read", {"file_path": EDITABLE}),
            ("Read", {"file_path": "../requirements.txt"}),
            ("Read", {"file_path": str(practice / TEST_FILES[0])}),
            ("Edit", {**replacement("assert", "#"), "file_path": TEST_FILES[0]}),
            ("Edit", {**replacement("outside", "inside"), "file_path": "private.txt"}),
            ("run_tests", {"command": "something else"}),
        ]:
            assert project.execute(name, arguments) == {"error": "Operation denied."}
        assert project.execute("Edit", replacement("-", "+")) == {"edited": EDITABLE}
        with pytest.raises(ValueError, match="readable test files"):
            _Project(practice, reader, TEST_FILES[0], TEST_FILES, COMMAND, 5)


@pytest.mark.parametrize("link", ["symlink", "hardlink", "directory"])
def test_rejects_linked_edit_targets(practice: Path, link: str) -> None:
    target = practice / EDITABLE
    source = practice / "private.txt"
    if link == "directory":
        (practice / "alias").symlink_to(target.parent, target_is_directory=True)
        edit_path = "alias/price.py"
    else:
        edit_path = EDITABLE
        target.unlink()
        if link == "symlink":
            target.symlink_to(source)
        else:
            target.hardlink_to(source)
    with (
        FileTools(practice, READABLE[1:]) as reader,
        pytest.raises(ValueError, match="regular files without links"),
    ):
        _Project(practice, reader, edit_path, TEST_FILES, COMMAND, 5)


@pytest.mark.parametrize("scenario", ["untested", "stale", "failed", "outside", "new"])
def test_finish_checks_latest_result_and_whole_tree(
    practice: Path, scenario: str
) -> None:
    with FileTools(practice, READABLE) as reader:
        project = _Project(practice, reader, EDITABLE, TEST_FILES, COMMAND, 5)
        op = "*" if scenario == "failed" else "+"
        project.execute("Edit", replacement("-", op))
        if scenario != "untested":
            result = project.execute("run_tests", {})
            assert (result["returncode"] == 0) == (scenario != "failed")
        if scenario == "stale":
            project.execute("Edit", replacement("+", "*"))
            project.execute("Edit", replacement("*", "+"))
        if scenario == "outside":
            (practice / "private.txt").write_text("changed", encoding="utf-8")
        if scenario == "new":
            (practice / "untracked.txt").touch()
        with pytest.raises(ValueError, match="Repair incomplete"):
            project.finish()


def test_test_process_timeout(practice: Path) -> None:
    (practice / TEST_FILES[0]).write_text(
        "import time\ntime.sleep(30)", encoding="utf-8"
    )
    with FileTools(practice, READABLE) as reader:
        project = _Project(practice, reader, EDITABLE, TEST_FILES, COMMAND, 0.2)
        project.execute("Edit", replacement("-", "+"))
        assert project.execute("run_tests", {}) == {"error": "Tests timed out."}
        with pytest.raises(ValueError, match="current passing test"):
            project.finish()


def test_test_process_cannot_leave_changes_and_complete(practice: Path) -> None:
    (practice / TEST_FILES[0]).write_text(
        "from pathlib import Path\nPath('private.txt').unlink()\n", encoding="utf-8"
    )
    with FileTools(practice, READABLE) as reader:
        project = _Project(practice, reader, EDITABLE, TEST_FILES, COMMAND, 5)
        project.execute("Edit", replacement("-", "+"))
        with pytest.raises(ValueError, match="unexpected project changes"):
            project.execute("run_tests", {})
        with pytest.raises(ValueError, match="unexpected project changes"):
            project.finish()
