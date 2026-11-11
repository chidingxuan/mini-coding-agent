"""模型工具请求的参数检查与分发，不提供确认写入入口。"""

import json

from backend.errors import AgentError
from backend.file_access import read_file, list_files, search_code, read_lines
from backend.proposal_files import preview_edit, create_proposal
from backend.tool_schemas import TOOLS


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
