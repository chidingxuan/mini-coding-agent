"""拆分后跨模块接线验证；只使用临时真实文件和数据库。"""

from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
from pathlib import Path

import pytest

from backend import edits, file_access, storage, tool
from backend.errors import AgentError
from backend.tool_schemas import TOOLS


@pytest.fixture
def pending(tmp_path, monkeypatch):
    monkeypatch.setattr(file_access, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    storage.init_db()
    target = tmp_path / "workspace" / "demo.py"
    target.parent.mkdir()
    target.write_bytes(b"value = 1\r\n")
    proposals = []
    tool.execute_tool("create_proposal", json.dumps({
        "path": "workspace/demo.py", "old_text": "value = 1", "new_text": "value = 2",
    }), edit_proposals=proposals)
    storage.save_turn("one", "q", "a", proposals)
    return target, proposals[0]["id"]


def test_dispatch_and_schema_keep_scope(pending):
    target, _ = pending
    assert json.loads(tool.execute_tool("list_files", "{}")) == ["workspace/demo.py"]
    assert tool.execute_tool("read_file", '{"path":"workspace/demo.py"}') == "value = 1\n"
    assert {entry["function"]["name"] for entry in TOOLS} == {
        "read_file", "list_files", "search_code", "read_lines", "preview_edit", "create_proposal",
    }
    assert file_access.CONFIRMABLE_FILES == {"workspace/demo.py"}
    assert file_access.READABLE_FILES == {
        "main.py", "backend/api.py", "backend/llm.py", "workspace/demo.py",
    }
    assert target.read_bytes() == b"value = 1\r\n"


def test_apply_cross_module_and_serialize_duplicate_requests(pending):
    target, identifier = pending
    with pytest.raises(AgentError) as caught:
        edits.apply_proposal("other", identifier)
    assert caught.value.code == "proposal_not_found"

    def apply():
        try:
            return edits.apply_proposal("one", identifier)
        except AgentError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: apply(), range(2)))
    assert {"proposal_id": identifier, "status": "applied"} in results
    assert "tool_rejected" in results
    saved = storage.load_proposal("one", identifier)
    assert saved["status"] == "applied"
    assert Path(saved["backup_path"]).read_bytes() == b"value = 1\r\n"
    assert target.read_bytes() == b"value = 2\r\n"
    assert not list(target.parent.glob(".mini-agent-*.tmp"))


def test_record_failure_keeps_backup_and_reports_changed_file(pending, monkeypatch):
    target, identifier = pending

    def fail_record(*args):
        raise sqlite3.OperationalError("test database failure")

    monkeypatch.setattr(edits, "mark_proposal_applied", fail_record)
    with pytest.raises(AgentError) as caught:
        edits.apply_proposal("one", identifier)
    assert caught.value.code == "proposal_record_failed"
    assert target.read_bytes() == b"value = 2\r\n"
    assert storage.load_proposal("one", identifier)["status"] == "pending"
    backups = list((file_access.PROJECT_DIR / "runtime" / "edit_backups").glob("*.before"))
    assert len(backups) == 1 and backups[0].read_bytes() == b"value = 1\r\n"
    assert not edits._apply_lock.locked()
