"""文件差异、提案、快照、备份与替换，不负责用户确认。"""

from difflib import unified_diff
from hashlib import sha256
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from backend import file_access
from backend.errors import AgentError
from backend.file_access import CONFIRMABLE_FILES, read_file, resolve_confirmable_file


def preview_edit(path: str, old_text: str, new_text: str) -> str:#预览更改的代码
    """基于当前文件生成单处替换的文本差异；不写入、不执行、不保存待应用补丁。"""
    return _build_edit_diff(path, read_file(path), old_text, new_text)


def _build_edit_diff(path: str, source: str, old_text: str, new_text: str) -> str:
    """仅根据已读取的正文构造差异，不再次读取文件。"""
    if not isinstance(old_text, str) or not old_text:
        raise AgentError("invalid_tool_arguments", "old_text必须是非空字符串")
    if not isinstance(new_text, str):
        raise AgentError("invalid_tool_arguments", "new_text必须是字符串")
    if len(old_text) > 20_000 or len(new_text) > 20_000:
        raise AgentError("tool_rejected", "单次预览的替换文本不能超过20000字符")

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
    snapshot = None
    if isinstance(path, str) and path in CONFIRMABLE_FILES:
        snapshot = read_confirmable_snapshot(path)
        diff = _build_edit_diff(path, snapshot["content"], old_text, new_text)
    else:
        diff = preview_edit(path, old_text, new_text)

    proposal = {
        "id": uuid4().hex,
        "path": path,
        "old_text": old_text,
        "new_text": new_text,
        "diff": diff,
    }
    if snapshot is not None:
        proposal["before_sha256"] = snapshot["before_sha256"]
    return proposal


def read_confirmable_snapshot(path: str) -> dict[str, str]: #检查文件并生成文件指纹
    target = resolve_confirmable_file(path)

    try:
        raw = target.read_bytes()

        if len(raw) > 20_000:
            raise AgentError("tool_rejected", "文件超过20000字节")

        content = raw.decode("utf-8")
    except (OSError, UnicodeError):
        raise AgentError(
            "tool_failed",
            "读取文件快照失败，请检查文件权限和UTF-8编码",
        ) from None

    return {
        "content": content,
        "before_sha256": sha256(raw).hexdigest(),
    }


def check_proposal_version(proposal: dict) -> dict[str, str]:#检查指纹是否正确
    if proposal.get("status") != "pending":
        raise AgentError(
            "tool_rejected",
            "提案不是待应用状态，不能继续",
        )

    # 检查允许的路径，并读取当前文件正文和指纹
    snapshot = read_confirmable_snapshot(proposal["path"])

    # 取出生成提案时保存的旧指纹
    expected_hash = proposal.get("before_sha256")

    if not expected_hash:
        raise AgentError(
            "tool_rejected",
            "提案缺少原文件指纹，请重新生成提案",
        )

    if snapshot["before_sha256"] != expected_hash:
        raise AgentError(
            "tool_rejected",
            "文件已变化，请重新生成提案",
        )

    return snapshot


def prepare_proposal_change(proposal: dict) -> dict[str, str]:#生成修改后的文件
    snapshot = check_proposal_version(proposal)
    source = snapshot["content"]

    diff = _build_edit_diff(
        proposal["path"],
        source,
        proposal["old_text"],
        proposal["new_text"],
    )

    if diff != proposal["diff"]:
        raise AgentError(
            "tool_rejected",
            "提案差异与替换内容不一致，请重新生成提案",
        )

    updated = source.replace(
        proposal["old_text"],
        proposal["new_text"],
        1,
    )

    return {
        "before_content": source,
        "after_content": updated,
    }


def backup_proposal_source(proposal: dict) -> Path:#生成备份的文件
    prepared = prepare_proposal_change(proposal)
    original_bytes = prepared["before_content"].encode("utf-8")

    backup_dir = file_access.PROJECT_DIR / "runtime" / "edit_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    backup_path = backup_dir / f"{uuid4().hex}.before"

    with backup_path.open("xb") as file:
        file.write(original_bytes)

    return backup_path


def write_proposal_change(proposal: dict) -> Path:
    prepared = prepare_proposal_change(proposal)
    target = resolve_confirmable_file(proposal["path"])

    backup_path = backup_proposal_source(proposal)
    temporary_path = None

    try:
        with NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=".mini-agent-",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            file.write(prepared["after_content"].encode("utf-8"))
            file.flush()
            os.fsync(file.fileno())

        # 保留原文件的普通权限位，避免替换后意外改变权限。
        os.chmod(temporary_path, target.stat().st_mode & 0o777)

        # 准备和备份期间，用户可能又修改了目标文件。
        check_proposal_version(proposal)
        target = resolve_confirmable_file(proposal["path"])

        os.replace(temporary_path, target)
        return backup_path

    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
