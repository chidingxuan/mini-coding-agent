"""用临时真实文件验证提案快照；不替换模型、不发送API请求。"""

from hashlib import sha256
import json

import pytest

from backend import file_access, proposal_files, tool
from backend.errors import AgentError


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setattr(file_access, "PROJECT_DIR", tmp_path)
    (tmp_path / "workspace").mkdir()
    target = tmp_path / "workspace" / "demo.py"
    target.write_bytes(b"value = 1\r\n")
    return target


def test_demo_hash_diff_and_dispatch_share_snapshot(demo):
    before = demo.read_bytes()
    proposals = []
    reply = tool.execute_tool("create_proposal", json.dumps({
        "path": "workspace/demo.py", "old_text": "value = 1", "new_text": "value = 2",
    }), edit_proposals=proposals)
    proposal = json.loads(reply)
    assert proposals == [proposal]
    assert proposal["before_sha256"] == sha256(before).hexdigest()
    assert "-value = 1\r\n+value = 2\r\n" in proposal["diff"]
    assert demo.read_bytes() == before


def test_no_second_read_after_snapshot(demo, monkeypatch):
    original_reader = proposal_files.read_confirmable_snapshot
    snapshots = []

    def read_then_change(path):
        snapshot = original_reader(path)
        snapshots.append(snapshot)
        # 模拟读取完成后文件发生变化；只能修改临时测试文件。
        demo.write_bytes(b"value = 999\n")
        return snapshot

    monkeypatch.setattr(proposal_files, "read_confirmable_snapshot", read_then_change)
    proposal = proposal_files.create_proposal("workspace/demo.py", "value = 1", "value = 2")
    assert len(snapshots) == 1
    assert proposal["before_sha256"] == snapshots[0]["before_sha256"]
    assert "-value = 1\r\n+value = 2\r\n" in proposal["diff"]
    assert "999" not in proposal["diff"]
    assert demo.read_bytes() == b"value = 999\n"


def test_source_code_proposals_still_have_five_fields(demo):
    source = demo.parents[1] / "main.py"
    source.write_bytes(b"value = 1\n")
    proposal = proposal_files.create_proposal("main.py", "value = 1", "value = 2")
    assert set(proposal) == {"id", "path", "old_text", "new_text", "diff"}
    assert source.read_bytes() == b"value = 1\n"


def test_invalid_demo_replacement_is_not_collected(demo):
    before = demo.read_bytes()
    proposals = []
    with pytest.raises(AgentError):
        tool.execute_tool("create_proposal", json.dumps({
            "path": "workspace/demo.py", "old_text": "missing", "new_text": "new",
        }), edit_proposals=proposals)
    assert proposals == []
    assert demo.read_bytes() == before
