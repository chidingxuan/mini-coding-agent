from pathlib import Path
import json

PROJECT_DIR = Path(__file__).resolve().parent.parent

READABLE_FILES = {
    "main.py",
    "backend/api.py",
    "backend/llm.py",
}


def read_file(path: str) -> str:
    # 在这里实现
    if Path(path).is_absolute():
        raise ValueError("只接受项目相对路径")

    target = (PROJECT_DIR / path).resolve()

    if not target.is_relative_to(PROJECT_DIR):
        raise ValueError("目标不在项目内")

    relative_path = target.relative_to(PROJECT_DIR).as_posix()
    if relative_path not in READABLE_FILES:
        raise ValueError("不允许读取这个文件")
    
    if not target.is_file():
        raise ValueError("目标文件不存在或不是普通文件")

    if target.stat().st_size > 20_000:
        raise ValueError("文件超过20000字节，暂不支持读取")

    return target.read_text(encoding="utf-8")

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
]
    
def execute_tool(name: str, arguments: str) -> str:
    if name not in {"read_file", "list_files"}:
        raise ValueError("不支持这个工具")

    args = json.loads(arguments)

    if not isinstance(args, dict):
        raise ValueError("工具参数必须是字典")

    # 列文件：不接受任何参数
    if name == "list_files":
        if args:
            raise ValueError("list_files不接受参数")

        return json.dumps(list_files(), ensure_ascii=False)

    # 读文件：必须只有一个字符串参数path
    if set(args) != {"path"}:
        raise ValueError("read_file必须且只能提供path")

    if not isinstance(args["path"], str):
        raise ValueError("path必须是字符串")

    return read_file(args["path"])
    


def list_files() -> list[str]:
    files = []

    for path in sorted(READABLE_FILES):
        if (PROJECT_DIR / path).is_file():
            files.append(path)

    return files
