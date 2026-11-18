"""工作区列表工具接线验证：只操作临时文件，不调用模型。"""

import json

import pytest

from backend import file_access, tool
from backend.errors import AgentError
from backend.tool_schemas import TOOLS


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(file_access, "PROJECT_DIR", tmp_path)
    root = tmp_path / "workspace"
    root.mkdir()
    return root


def test_dispatch_returns_workspace_relative_paths_without_reading(workspace):
    (workspace / "src").mkdir()
    (workspace / "src" / "海边.py").write_bytes(b"\xff\xfe")
    (workspace / ".env").touch()
    (workspace / "node_modules").mkdir()
    (workspace / "node_modules" / "hidden.py").touch()
    payload = tool.execute_tool("list_workspace_files", "{}")
    assert json.loads(payload) == ["src/海边.py"]
    assert "海边.py" in payload
    assert (workspace / "src" / "海边.py").read_bytes() == b"\xff\xfe"
    # 列出路径不等于获得旧读取工具的访问许可。
    with pytest.raises(AgentError):
        tool.execute_tool("read_file", '{"path":"workspace/src/海边.py"}')


@pytest.mark.parametrize("arguments", ['{"path":".."}', '[]', 'null', 'invalid'])
def test_rejects_parameters_and_invalid_arguments(workspace, arguments):
    with pytest.raises(AgentError) as caught:
        tool.execute_tool("list_workspace_files", arguments)
    assert caught.value.code == "invalid_tool_arguments"


def test_schema_and_empty_result(workspace):
    entries = [entry for entry in TOOLS if entry["function"]["name"] == "list_workspace_files"]
    assert len(entries) == 1
    assert entries[0]["function"]["parameters"] == {
        "type": "object", "properties": {}, "required": [], "additionalProperties": False,
    }
    assert json.loads(tool.execute_tool("list_workspace_files", "{}")) == []
    assert json.loads(tool.execute_tool("list_files", "{}")) == []


def test_dispatch_preserves_file_count_limit(workspace):
    for index in range(200):
        (workspace / f"file_{index:03}.py").touch()
    assert len(json.loads(tool.execute_tool("list_workspace_files", "{}"))) == 200
    (workspace / "overflow.py").touch()
    with pytest.raises(AgentError) as caught:
        tool.execute_tool("list_workspace_files", "{}")
    assert caught.value.code == "tool_rejected"
