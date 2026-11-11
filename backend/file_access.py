"""文件访问范围、路径检查和只读操作。"""

from pathlib import Path

from backend.errors import AgentError

PROJECT_DIR = Path(__file__).resolve().parent.parent

READABLE_FILES = {
    "main.py",
    "backend/api.py",
    "backend/llm.py",
    "workspace/demo.py",
}

CONFIRMABLE_FILES = {"workspace/demo.py"}


def resolve_confirmable_file(path: str) -> Path:
    """只检查当前目标并返回路径；不写入，也不代表修改已获确认。"""
    if not isinstance(path, str):
        raise AgentError("invalid_tool_arguments", "path必须是字符串")
    if path not in CONFIRMABLE_FILES:
        raise AgentError("tool_rejected", "目标不在确认写入范围内")

    try:
        root = PROJECT_DIR.resolve(strict=True)
        target = root
        # 在resolve之前逐级检查，避免父目录或文件的符号链接被解析掉。
        for part in Path(path).parts:
            target = target / part
            if target.is_symlink():
                raise AgentError("tool_rejected", "确认目标及其父目录不能是符号链接")
        resolved = target.resolve(strict=True)
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise AgentError("tool_rejected", "确认目标必须是项目内现有的普通文件")
    except (OSError, RuntimeError):
        raise AgentError("tool_rejected", "无法安全访问确认目标，请检查文件及目录") from None

    return resolved


def read_file(path: str) -> str: #阅读某个文件
    if not isinstance(path, str):
        raise AgentError("invalid_tool_arguments", "path必须是字符串")
    if Path(path).is_absolute():
        raise AgentError("tool_rejected", "只接受项目相对路径")

    try:
        target = (PROJECT_DIR / path).resolve()
    except (OSError, ValueError):
        raise AgentError("tool_rejected", "无法安全解析目标路径") from None

    if not target.is_relative_to(PROJECT_DIR):
        raise AgentError("tool_rejected", "目标不在项目内")

    relative_path = target.relative_to(PROJECT_DIR).as_posix()
    if relative_path not in READABLE_FILES:
        raise AgentError("tool_rejected", "不允许读取这个文件")

    try:
        if not target.is_file():
            raise AgentError("tool_failed", "目标文件不存在或不是普通文件")
        if target.stat().st_size > 20_000:
            raise AgentError("tool_rejected", "文件超过20000字节，暂不支持读取")
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise AgentError("tool_failed", "文件读取失败，请检查文件权限和UTF-8编码") from None


def list_files() -> list[str]: #列出所有文件
    files = []

    for path in sorted(READABLE_FILES):
        if (PROJECT_DIR / path).is_file():
            files.append(path)

    return files


def search_code(query: str) -> list[dict[str, str | int]]: #查找文件里有没有该关键词
    if not isinstance(query, str) or not query.strip():
        raise AgentError("invalid_tool_arguments", "query必须是非空字符串")

    query = query.strip()
    hits = []

    for path in list_files():
        content = read_file(path)

        for line_number, line in enumerate(content.splitlines(), start=1):
            if query in line:
                hits.append({
                    "path": path,
                    "line": line_number,
                    "text": line[:300],
                })

                if len(hits) >= 20:
                    return hits

    return hits


def read_lines(path: str, start_line: int, end_line: int) -> str:#按行号阅读
    if type(start_line) is not int or type(end_line) is not int:
        raise AgentError("invalid_tool_arguments", "起止行号必须是整数")

    if not 1 <= start_line <= end_line:
        raise AgentError("invalid_tool_arguments", "行号必须从1开始，结束行不能小于开始行")

    if end_line - start_line + 1 > 80:
        raise AgentError("tool_rejected", "一次最多读取80行")

    lines = read_file(path).splitlines()

    if start_line > len(lines):
        raise AgentError("invalid_tool_arguments", "开始行超过文件总行数")

    selected = lines[start_line - 1:end_line]

    return "\n".join(
        f"{number}: {line}"
        for number, line in enumerate(selected, start=start_line)
    )
