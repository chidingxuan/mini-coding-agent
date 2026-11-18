import sqlite3
from contextlib import closing
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_DIR / "runtime" / "agent.sqlite3"


def init_db() -> None:
    # 输入：无；使用本模块DB_PATH指定的SQLite文件。
    # 返回：None；创建数据库目录和缺失表/列，保留旧记录，重复初始化不会清空数据。
    # 副作用：写入数据库结构；旧提案指纹和备份路径保持NULL，默认状态为pending。
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(DB_PATH)) as connection:
        # 串行化初始化，避免同时启动时重复执行同一列的迁移。
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS proposal_drafts (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                assistant_message_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                old_text TEXT NOT NULL,
                new_text TEXT NOT NULL,
                diff TEXT NOT NULL,
                before_sha256 TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'applied')),
                backup_path TEXT
            )
        """)
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(proposal_drafts)")
        }
        if "before_sha256" not in columns:
            # 旧记录保持NULL，不根据当前文件补算历史指纹。
            connection.execute("ALTER TABLE proposal_drafts ADD COLUMN before_sha256 TEXT")
        if "status" not in columns:
            connection.execute("""
                ALTER TABLE proposal_drafts
                ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'applied'))
            """)
        if "backup_path" not in columns:
            connection.execute(
                "ALTER TABLE proposal_drafts ADD COLUMN backup_path TEXT"
            )
        connection.commit()

def save_turn(
    conversation_id: str,
    question: str,
    answer: str,
    proposals: list[dict[str, str | None]] | None = None,
) -> None:
    # 输入：conversation_id、question、answer均为str；proposals为提案字典列表，可为None或[]。
    # 返回：None；把一轮问答及提案放在同一事务中保存，提案关联本次助手消息编号，失败整体回滚。
    # 提案字段：id/path/old_text/new_text/diff，before_sha256可缺失；不应用修改、不写目标代码文件。
    with closing(sqlite3.connect(DB_PATH)) as connection:
        with connection:
            connection.execute(
                """
                INSERT INTO messages (conversation_id, role, content)
                VALUES (?, ?, ?)
                """,
                (conversation_id, "user", question),
            )
            assistant_cursor = connection.execute(
                """
                INSERT INTO messages (conversation_id, role, content)
                VALUES (?, ?, ?)
                """,
                (conversation_id, "assistant", answer),
            )
            # 使用本次插入返回的编号，保证提案关联到这一轮的助手消息。
            assistant_message_id = assistant_cursor.lastrowid
            connection.executemany(
                """
                INSERT INTO proposal_drafts (
                    id, conversation_id, assistant_message_id,
                    path, old_text, new_text, diff, before_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        proposal["id"], conversation_id, assistant_message_id,
                        proposal["path"], proposal["old_text"],
                        proposal["new_text"], proposal["diff"],
                        proposal.get("before_sha256"),
                    )
                    for proposal in (proposals or [])
                ],
            )

def load_history(conversation_id: str) -> list[dict[str, str]]:
    # 输入：conversation_id为会话编号str。
    # 返回：按消息编号升序的list[dict]，每条仅含role和content，供模型上下文使用；无记录返回[]。
    # 副作用：只查询数据库，不调用模型、不修改历史。
    with closing(sqlite3.connect(DB_PATH)) as connection:
        rows = connection.execute(
            """
            SELECT role, content
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,),
        ).fetchall()

    return [
        {"role": role, "content": content}
        for role, content in rows
    ]

def load_messages(conversation_id: str) -> list[dict[str, str | int]]:
    """供历史展示使用；保留消息编号，不用于构造模型消息。"""
    # 输入：conversation_id为会话编号str。
    # 返回：按编号升序的消息字典列表，每条含id、role、content，供网页匹配提案；无记录返回[]。
    # 副作用：只查询数据库，不用于直接构造模型消息。
    with closing(sqlite3.connect(DB_PATH)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, role, content
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,),
        ).fetchall()

    return [dict(row) for row in rows]

def load_proposals(conversation_id: str) -> list[dict[str, str | int | None]]:
    # 输入：conversation_id为会话编号str，查询该会话的全部提案。
    # 返回：提案字典列表，含id/path/old_text/new_text/diff/assistant_message_id/before_sha256/status/backup_path；无记录为[]。
    # 说明：指纹和备份路径可为None；按助手消息编号及插入顺序排序，只查数据库，不应用修改。
    with closing(sqlite3.connect(DB_PATH)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, path, old_text, new_text, diff, assistant_message_id, before_sha256, status, backup_path
            FROM proposal_drafts
            WHERE conversation_id = ?
            ORDER BY assistant_message_id ASC, rowid ASC
            """,
            (conversation_id,),
        ).fetchall()

    return [dict(row) for row in rows]

def list_conversations() -> list[str]:
    # 输入：无。
    # 返回：会话编号list[str]，按各会话最新消息编号降序排列；无会话时返回[]，只查询数据库。
    with closing(sqlite3.connect(DB_PATH)) as connection:
        rows = connection.execute(
            """
            SELECT conversation_id
            FROM messages
            GROUP BY conversation_id
            ORDER BY MAX(id) DESC
            """
        ).fetchall()

    return [row[0] for row in rows]

def load_proposal(
    conversation_id: str,
    proposal_id: str,
) -> dict | None:
    # 输入：conversation_id为会话编号str，proposal_id为指定提案编号str，两个条件必须同时匹配。
    # 返回：一条提案dict（含替换文本、diff、指纹、状态、备份路径和助手消息编号），找不到返回None。
    # 说明：只查询数据库；会话范围检查不等同于完整用户鉴权。
    with closing(sqlite3.connect(DB_PATH)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT id, path, old_text, new_text, diff,
                   assistant_message_id, before_sha256, status, backup_path
            FROM proposal_drafts
            WHERE conversation_id = ? AND id = ?
            """,
            (conversation_id, proposal_id),
        ).fetchone()

    return dict(row) if row is not None else None

def mark_proposal_applied( #标记已经使用的提案
    conversation_id: str,
    proposal_id: str,
    backup_path: str,
) -> bool:
    # 输入：conversation_id、proposal_id为str；backup_path为程序实际生成的备份路径字符串。
    # 返回：成功将一条pending记录改为applied并保存备份路径时为True，无匹配待应用记录时为False。
    # 副作用：提交数据库更新；不创建备份或修改目标文件，只应在文件修改成功后调用。
    with closing(sqlite3.connect(DB_PATH)) as connection:
        with connection:
            cursor = connection.execute(
                """
                UPDATE proposal_drafts
                SET status = 'applied',
                    backup_path = ?
                WHERE conversation_id = ?
                  AND id = ?
                  AND status = 'pending'
                """,
                (backup_path, conversation_id, proposal_id),
            )

        return cursor.rowcount == 1
