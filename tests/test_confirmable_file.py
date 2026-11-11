"""只验证确认目标的路径检查；不写入项目文件、不调用模型。"""

from pathlib import Path

import pytest

from backend import file_access
from backend.errors import AgentError


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(file_access, "PROJECT_DIR", tmp_path)
    (tmp_path / "workspace").mkdir()
    target = tmp_path / "workspace" / "demo.py"
    target.write_text('print("演练")\n', encoding="utf-8")
    return tmp_path, target


def test_returns_path_without_changing_file(project):
    _, target = project
    before = target.read_bytes()
    assert file_access.resolve_confirmable_file("workspace/demo.py") == target
    assert target.read_bytes() == before


def test_rejects_other_paths_even_if_readable(project):
    root, _ = project
    for path in ("main.py", "backend/api.py", "backend/llm.py", ".env",
                 "../workspace/demo.py", "workspace/../workspace/demo.py",
                 str(root / "workspace" / "demo.py")):
        with pytest.raises(AgentError) as caught:
            file_access.resolve_confirmable_file(path)
        assert caught.value.code == "tool_rejected"


def test_rejects_non_string():
    with pytest.raises(AgentError) as caught:
        file_access.resolve_confirmable_file(Path("workspace/demo.py"))
    assert caught.value.code == "invalid_tool_arguments"


def test_rejects_missing_file_and_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(file_access, "PROJECT_DIR", tmp_path)
    with pytest.raises(AgentError):
        file_access.resolve_confirmable_file("workspace/demo.py")
    (tmp_path / "workspace" / "demo.py").mkdir(parents=True)
    with pytest.raises(AgentError):
        file_access.resolve_confirmable_file("workspace/demo.py")


def test_rejects_file_symlink_even_within_project(tmp_path, monkeypatch):
    monkeypatch.setattr(file_access, "PROJECT_DIR", tmp_path)
    (tmp_path / "workspace").mkdir()
    real = tmp_path / "real.py"
    real.write_text("unchanged\n", encoding="utf-8")
    (tmp_path / "workspace" / "demo.py").symlink_to(real)
    with pytest.raises(AgentError):
        file_access.resolve_confirmable_file("workspace/demo.py")
    assert real.read_text(encoding="utf-8") == "unchanged\n"


def test_rejects_parent_and_broken_symlinks(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "demo.py").write_text("unchanged\n", encoding="utf-8")
    (root / "workspace").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(file_access, "PROJECT_DIR", root)
    with pytest.raises(AgentError):
        file_access.resolve_confirmable_file("workspace/demo.py")
    assert (outside / "demo.py").read_text(encoding="utf-8") == "unchanged\n"

    broken_root = tmp_path / "broken-project"
    (broken_root / "workspace").mkdir(parents=True)
    (broken_root / "workspace" / "demo.py").symlink_to(tmp_path / "missing.py")
    monkeypatch.setattr(file_access, "PROJECT_DIR", broken_root)
    with pytest.raises(AgentError):
        file_access.resolve_confirmable_file("workspace/demo.py")
