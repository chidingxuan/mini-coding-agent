from pathlib import Path
from difflib import unified_diff
from uuid import uuid4
import json
from backend.errors import AgentError

PROJECT_DIR = Path(__file__).resolve().parent.parent

READABLE_FILES = {
    "main.py",
    "backend/api.py",
    "backend/llm.py",
}


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

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取当前项目中允许访问的Python代码文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于项目根目录的文件路径。",
                        "enum": sorted(READABLE_FILES),
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出当前项目白名单中实际存在的文件路径，不返回文件正文。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": (
                "在白名单代码文件中搜索区分大小写的字面关键词，"
                "返回文件路径、行号和命中行，最多20条。不是语义搜索。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要搜索的非空关键词，例如save_turn。",
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_lines",
            "description": (
                "读取白名单文件的指定行，包含结束行，一次最多80行。"
                "适合查看搜索命中附近的代码，返回带原始行号的正文。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "enum": sorted(READABLE_FILES),
                        "description": "项目相对文件路径。",
                    },
                    "start_line": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "开始行号，从1开始。",
                    },
                    "end_line": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "结束行号，不能小于开始行。",
                    },
                },
                "required": ["path", "start_line", "end_line"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preview_edit",
            "description": (
                "生成白名单代码文件的单处替换差异预览，不写入或执行文件。"
                "应先读取代码；old_text必须是精确且唯一的源码原文，不带读取结果的行号。"
                "保留缩进和换行，不能猜测原文。"
                "成功后在最终回答中用diff代码块完整展示返回的差异，明确说明仅预览、未写入文件。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "enum": sorted(READABLE_FILES),
                        "description": "项目相对文件路径，只允许现有白名单文件。",
                    },
                    "old_text": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 20000,
                        "description": "文件中精确且唯一的非空原文，包含原有缩进。",
                    },
                    "new_text": {
                        "type": "string",
                        "maxLength": 20000,
                        "description": "替换后的文本；空字符串表示预览删除该原文。",
                    },
                },
                "required": ["path", "old_text", "new_text"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_proposal",
            "description": (
                "生成白名单代码文件的单处替换提案，并收集到本次调用的内存列表。"
                "只生成提案，不保存数据库、不写入或执行文件，也不代表修改已获批准。"
                "应先读取代码；old_text必须是精确且唯一的源码原文，不带行号。"
                "保留缩进和换行，不能猜测原文；向用户明确说明提案尚未应用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "enum": sorted(READABLE_FILES),
                        "description": "项目相对文件路径，只允许现有白名单文件。",
                    },
                    "old_text": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 20000,
                        "description": "文件中精确且唯一的非空原文，包含原有缩进。",
                    },
                    "new_text": {
                        "type": "string",
                        "maxLength": 20000,
                        "description": "替换后的文本；空字符串表示提议删除该原文。",
                    },
                },
                "required": ["path", "old_text", "new_text"],
                "additionalProperties": False,
            },
        },
    },
]
    
def execute_tool(name: str,
                 arguments: str,
                 *,
                 edit_proposals: list[dict] | None = None,
                 ) -> str: #检查工具
    if not isinstance(name, str) or name not in {
        "read_file", "list_files", "search_code", "read_lines", "preview_edit", "create_proposal",
    }:
        raise AgentError("tool_rejected", "不支持这个工具")

    if not isinstance(arguments, str):
        raise AgentError("invalid_tool_arguments", "工具参数必须是JSON字符串")
    try:
        args = json.loads(arguments)
    except json.JSONDecodeError:
        raise AgentError("invalid_tool_arguments", "工具参数不是合法JSON") from None

    if not isinstance(args, dict):
        raise AgentError("invalid_tool_arguments", "工具参数必须是字典")

    # 列文件：不接受任何参数
    if name == "list_files":
        if args:
            raise AgentError("invalid_tool_arguments", "list_files不接受参数")

        return json.dumps(list_files(), ensure_ascii=False)
    if name == "search_code":
        if set(args) != {"query"} or not isinstance(args["query"], str):
            raise AgentError(
                "invalid_tool_arguments",
                "search_code必须且只能提供字符串query",
            )

        return json.dumps(search_code(args["query"]), ensure_ascii=False)

    if name == "read_lines":
        if set(args) != {"path", "start_line", "end_line"}:
            raise AgentError(
                "invalid_tool_arguments",
                "read_lines必须且只能提供path、start_line、end_line",
            )

        return read_lines(
            args["path"],
            args["start_line"],
            args["end_line"],
        )

    if name == "create_proposal":
        if edit_proposals is None:
            raise AgentError("tool_rejected", "当前调用没有提供提案收集列表")

        if set(args) != {"path", "old_text", "new_text"}:
            raise AgentError(
                "invalid_tool_arguments",
                "create_proposal必须且只能提供path、old_text、new_text",
            )

        proposal = create_proposal(
            args["path"],
            args["old_text"],
            args["new_text"],
        )

        edit_proposals.append(proposal)

        return json.dumps(proposal, ensure_ascii=False)

    if name == "preview_edit":
        if set(args) != {"path", "old_text", "new_text"}:
            raise AgentError(
                "invalid_tool_arguments",
                "preview_edit必须且只能提供path、old_text、new_text",
            )

        return preview_edit(args["path"], args["old_text"], args["new_text"])

    # 读文件：必须只有一个字符串参数path
    if set(args) != {"path"}:
        raise AgentError("invalid_tool_arguments", "read_file必须且只能提供path")

    if not isinstance(args["path"], str):
        raise AgentError("invalid_tool_arguments", "path必须是字符串")

    return read_file(args["path"])
    


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


def preview_edit(path: str, old_text: str, new_text: str) -> str:#预览更改的代码
    """基于当前文件生成单处替换的文本差异；不写入、不执行、不保存待应用补丁。"""
    if not isinstance(old_text, str) or not old_text:
        raise AgentError("invalid_tool_arguments", "old_text必须是非空字符串")
    if not isinstance(new_text, str):
        raise AgentError("invalid_tool_arguments", "new_text必须是字符串")
    if len(old_text) > 20_000 or len(new_text) > 20_000:
        raise AgentError("tool_rejected", "单次预览的替换文本不能超过20000字符")

    source = read_file(path)
    position = source.find(old_text)
    if position < 0 or source.find(old_text, position + 1) != -1:
        raise AgentError(
            "invalid_tool_arguments",
            "old_text必须在文件中恰好出现一次，请提供准确且唯一的原文",
        )

    proposed = source.replace(old_text, new_text, 1)
    if proposed == source:
        raise AgentError("invalid_tool_arguments", "没有实际修改")
    try:
        proposed_size = len(proposed.encode("utf-8"))
    except UnicodeEncodeError:
        raise AgentError("invalid_tool_arguments", "替换后的文本必须能编码为UTF-8") from None
    if proposed_size > 20_000:
        raise AgentError("tool_rejected", "预览修改后的文件不能超过20000字节")

    diff = unified_diff(
        source.splitlines(keepends=True),
        proposed.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )
    return "".join(
        line if line.endswith("\n")
        else line + "\n\\ No newline at end of file\n"
        for line in diff
    )


def create_proposal(path: str, old_text: str, new_text: str) -> dict:
    diff = preview_edit(path, old_text, new_text)

    return {
        "id": uuid4().hex,
        "path": path,
        "old_text": old_text,
        "new_text": new_text,
        "diff": diff,
    }
