"""发送给模型的工具说明，不提供执行或写入能力。"""

from backend.file_access import READABLE_FILES

TOOLS = [#把所有工具的介绍都放在这个list里
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
