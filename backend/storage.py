import sqlite3
from contextlib import closing
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_DIR / "runtime" / "agent.sqlite3"


def init_db() -> None:
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
