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
    }
]
    
def execute_tool(name: str, arguments: str) -> str:
    # 1. 检查工具名称
    if name != "read_file":
        raise ValueError("不支持这个工具")
    
    # 2. 解析参数JSON
    args = json.loads(arguments)

    # 3. 检查参数结构
    if not isinstance(args, dict) or set(args) != {"path"}:
        raise ValueError("模型参数不对")

    if not isinstance(args["path"], str):
        raise ValueError("path必须是字符串")
    
    # 4. 调用read_file，返回文件正文
    return read_file(args["path"])
