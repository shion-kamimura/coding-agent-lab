"""起動側が許可したUTF-8ファイルだけを調べるPOSIX用ツール。"""

import errno
import os
import stat
from pathlib import Path
from types import TracebackType

MAX_FILES = 256
MAX_ENTRIES = 50
MAX_LINES = 100
MAX_BYTES = 16_384
MAX_FILE_BYTES = 262_144
SUFFIXES = {".md", ".txt", ".rst", ".py", ".toml", ".yaml", ".yml", ".json"}


class Rejected(ValueError):
    """モデルへ返してよい、固定文言の操作エラー。"""


def parts(path: str, *, directory: bool = False) -> tuple[str, ...]:
    if directory and path == ".":
        return ()
    items = tuple(path.split("/"))
    if (
        not path
        or len(path.encode("utf-8")) > 240
        or "\\" in path
        or any(not p or p.startswith(".") or ":" in p for p in items)
        or any(ord(c) < 32 or ord(c) == 127 for c in path)
    ):
        raise Rejected("Denied: use a relative path without dot components.")
    return items


class FileTools:
    """ルートFDを固定し、各要素をO_NOFOLLOWで開く。使用後はcloseする。"""

    def __init__(self, root: Path, allowed_files: tuple[str, ...]) -> None:
        if not 1 <= len(allowed_files) <= MAX_FILES:
            raise ValueError("Configure between 1 and 256 allowed files.")
        for path in allowed_files:
            parts(path)
            if Path(path).suffix not in SUFFIXES:
                raise ValueError("Unsupported allowed file suffix.")
        self.allowed = frozenset(allowed_files)
        self.evidence: dict[tuple[str, int], str] = {}
        self._root = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

    def __enter__(self) -> FileTools:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        os.close(self._root)

    def _open(self, path: str, *, directory: bool = False) -> int:
        items = parts(path, directory=directory)
        fd = os.dup(self._root)
        try:
            for index, item in enumerate(items):
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                if directory or index < len(items) - 1:
                    flags |= os.O_DIRECTORY
                child = os.open(item, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            return fd
        except BaseException:
            os.close(fd)
            raise

    def list_files(self, path: str) -> dict[str, object]:
        prefix = parts(path, directory=True)
        candidates: dict[str, str] = {}
        for allowed in sorted(self.allowed):
            items = tuple(allowed.split("/"))
            if items[: len(prefix)] == prefix and len(items) > len(prefix):
                name = items[len(prefix)]
                candidates[name] = (
                    "directory" if len(items) > len(prefix) + 1 else "file"
                )
        if not candidates:
            raise Rejected("Denied: directory is outside the configured scope.")
        fd = self._open(path, directory=True)
        try:
            entries = []
            for name, kind in sorted(candidates.items()):
                try:
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                if (kind == "directory" and stat.S_ISDIR(info.st_mode)) or (
                    kind == "file" and stat.S_ISREG(info.st_mode)
                ):
                    entries.append({"name": name, "type": kind})
            return {
                "path": path,
                "entries": entries[:MAX_ENTRIES],
                "omitted": len(entries) > MAX_ENTRIES,
                "scope": "configured files only; not a complete directory listing",
            }
        finally:
            os.close(fd)

    def read_file(
        self, path: str, start_line: int, line_count: int
    ) -> dict[str, object]:
        parts(path)
        if path not in self.allowed:
            raise Rejected("Denied: file is outside the configured scope.")
        if not 1 <= start_line <= MAX_FILE_BYTES or not 1 <= line_count <= MAX_LINES:
            raise Rejected("Use start_line=1..262144 and line_count=1..100.")
        fd = self._open(path)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise Rejected("Denied: only regular files are supported.")
        except BaseException:
            os.close(fd)
            raise
        with os.fdopen(fd, "rb") as file:
            data = file.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise Rejected("File exceeds the 262144-byte input limit.")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise Rejected("Only UTF-8 text is supported.") from None
        if any(ord(c) < 32 and c not in "\n\r\t" for c in text):
            raise Rejected("Binary/control characters are not supported.")
        lines = text.splitlines()
        selected: list[dict[str, object]] = []
        size = 0
        for number in range(start_line, min(len(lines) + 1, start_line + line_count)):
            line = lines[number - 1]
            size += len(line.encode("utf-8")) + 1
            if size > MAX_BYTES:
                break
            selected.append({"line": number, "text": line})
            self.evidence[path, number] = line
        if not selected and start_line <= len(lines):
            raise Rejected("A complete line exceeds the 16384-byte result limit.")
        end = start_line + len(selected) - 1
        return {
            "path": path,
            "start_line": start_line,
            "end_line": end if selected else None,
            "lines": selected,
            "has_more": end < len(lines),
            "omitted": start_line > 1 or end < len(lines),
        }

    def execute(self, name: str, arguments: object) -> dict[str, object]:
        try:
            if not isinstance(arguments, dict):
                raise Rejected("Arguments must be an object.")
            if name == "list_files" and set(arguments) == {"path"}:
                if isinstance(arguments["path"], str):
                    return self.list_files(arguments["path"])
            if name == "read_file" and set(arguments) == {
                "path",
                "start_line",
                "line_count",
            }:
                if (
                    isinstance(arguments["path"], str)
                    and type(arguments["start_line"]) is int
                    and type(arguments["line_count"]) is int
                ):
                    return self.read_file(
                        arguments["path"],
                        arguments["start_line"],
                        arguments["line_count"],
                    )
            raise Rejected(
                "Use list_files(path) or read_file(path, start_line, line_count)."
            )
        except Rejected as error:
            return {"error": str(error)}
        except OSError as error:
            if error.errno in {errno.ENOENT, errno.ENOTDIR}:
                return {"error": "Path not found or not an accessible directory."}
            if error.errno in {errno.ELOOP, errno.EACCES, errno.EPERM}:
                return {"error": "Denied: inaccessible path or symbolic link."}
            raise
