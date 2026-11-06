from pathlib import Path
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
                        "enum": [
                            "main.py",
                            "backend/api.py",
                            "backend/llm.py",
                        ],
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
]
    
def execute_tool(name: str, arguments: str) -> str: #检查工具
    if not isinstance(name, str) or name not in {"read_file", "list_files", "search_code"}:
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