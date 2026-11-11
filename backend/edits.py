import sqlite3
from threading import Lock

from backend.errors import AgentError
from backend.storage import load_proposal, mark_proposal_applied
from backend.proposal_files import write_proposal_change

_apply_lock = Lock()


def apply_proposal(
    conversation_id: str,
    proposal_id: str,
) -> dict:
    with _apply_lock:
        proposal = load_proposal(conversation_id, proposal_id)

        if proposal is None:
            raise AgentError(
                "proposal_not_found",
                "没有找到属于该会话的提案",
                status_code=404,
            )

        if proposal["status"] != "pending":
            raise AgentError(
                "tool_rejected",
                "提案不是待应用状态，不能继续",
            )

        try:
            backup_path = write_proposal_change(proposal)
        except OSError:
            raise AgentError(
                "proposal_write_uncertain",
                "文件操作未正常完成，不能确认目标是否已修改；"
                "请检查文件和备份，不要直接重试",
                status_code=500,
            ) from None

        try:
            recorded = mark_proposal_applied(
                conversation_id,
                proposal_id,
                str(backup_path),
            )
        except sqlite3.Error:
            recorded = False

        if not recorded:
            raise AgentError(
                "proposal_record_failed",
                "文件已修改，但提案状态未能确认保存；"
                "请检查文件、数据库和备份，不要直接重试",
                status_code=500,
            ) from None

        return {
            "proposal_id": proposal_id,
            "status": "applied",
        }
