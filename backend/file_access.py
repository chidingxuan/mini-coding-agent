"""文件访问范围、路径检查和只读操作。"""
import os
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
    # 输入：path为项目根目录相对路径str，目前仅允许'workspace/demo.py'。
    # 返回：检查通过的绝对路径Path；不读写正文，不代表用户已确认，越界/链接/缺失时抛AgentError。
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
    # 输入：path为项目根目录相对路径str，例如'backend/api.py'；须属于固定读取白名单。
    # 返回：UTF-8正文str；只读取，超过20000字节、编码错误或路径不允许时抛AgentError。
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
    # 输入：无；使用程序中的固定READABLE_FILES白名单。
    # 返回：实际存在的项目相对路径list[str]，按路径排序；只列名称，不读取正文。
    files = []

    for path in sorted(READABLE_FILES):
        if (PROJECT_DIR / path).is_file():
            files.append(path)

    return files

def search_code(query: str) -> list[dict[str, str | int]]: #查找文件里有没有该关键词
    # 输入：query为非空关键词str，区分大小写，按字面匹配，不是语义检索。
    # 返回：最多20条命中字典列表，每条含path、line（从1开始）、text（最多300字符）；只读白名单文件。
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
    # 输入：path为项目相对路径str，start_line/end_line为从1开始的整数，含结束行，最多80行。
    # 返回：带'行号: 正文'的str；只读取，权限沿用read_file，非法范围抛AgentError。
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

def list_workspace_files() -> list[str]:#找出工作区目录下所有的文件名
    # 输入：无；只遍历PROJECT_DIR/workspace，排除隐藏路径、指定目录、数据库/日志及符号链接。
    # 返回：排序后的工作区相对路径list[str]，例如['demo.py']，空目录返回[]；不读取正文。
    # 限制：符合规则的文件超过200个则抛AgentError；扫描失败明确报错，不静默返回不完整列表。
    workspace = PROJECT_DIR / "workspace"

    if workspace.is_symlink() or not workspace.is_dir():
        raise AgentError("tool_rejected", "工作区必须是现有的普通目录")

    excluded_dirs = {
        ".git", ".venv", "venv", "node_modules",
        "__pycache__", ".pytest_cache", "runtime",
    }
    files = []

    def on_walk_error(error: OSError) -> None:
        # 输入：error为os.walk扫描目录时传入的OSError，由遍历器自动调用。
        # 返回：无正常返回，始终抛出tool_failed类AgentError；不回显原始系统异常。
        raise AgentError(
            "tool_failed",
            "工作区扫描失败，请检查目录访问权限",
        ) from None
    for current, dirs, names in os.walk(
        workspace,
        followlinks=False,
        onerror=on_walk_error,
    ):
        current = Path(current)

        dirs[:] = sorted(
            name
            for name in dirs
            if name not in excluded_dirs
            and not name.startswith(".")
            and not (current / name).is_symlink()
        )

        for name in sorted(names):
            target = current / name

            if name.startswith("."):
                continue
            if target.is_symlink() or not target.is_file():
                continue
            if target.suffix.lower() in {".sqlite", ".sqlite3", ".db", ".log"}:
                continue

            files.append(target.relative_to(workspace).as_posix())

            if len(files) > 200:
                raise AgentError(
                    "tool_rejected",
                    "工作区文件超过200个，请缩小工作区范围",
                )

    return sorted(files)

def resolve_workspace_file(path: str) -> Path:#根据文件名返回出这个文件的地址
    # 输入：path为工作区相对路径str，例如'demo.py'，不是项目相对路径'workspace/demo.py'。
    # 返回：列表允许且通过链接/范围/文件类型检查的绝对路径Path；不读取正文，不授予写入权限。
    if not isinstance(path, str):
        raise AgentError("invalid_tool_arguments", "path必须是字符串")

    # 只接受列表工具实际展示的路径，复用现有排除规则。
    if path not in list_workspace_files():
        raise AgentError("tool_rejected", "目标不在允许访问的工作区文件列表中")

    workspace = PROJECT_DIR / "workspace"

    try:
        target = workspace

        for part in Path(path).parts:
            target = target / part
            if target.is_symlink():
                raise AgentError("tool_rejected", "不允许访问符号链接")

        root = workspace.resolve(strict=True)
        target = target.resolve(strict=True)

        if not target.is_relative_to(root) or not target.is_file():
            raise AgentError("tool_rejected", "目标必须是工作区内的普通文件")

    except (OSError, RuntimeError):
        raise AgentError("tool_failed", "无法访问工作区目标文件") from None

    return target
