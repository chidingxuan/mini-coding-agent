import sqlite3
from contextlib import closing
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_DIR / "runtime" / "agent.sqlite3"


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(DB_PATH)) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL
            )
        """)
        connection.commit()

def save_turn(
    conversation_id: str,
    question: str,
    answer: str,
) -> None:
    with closing(sqlite3.connect(DB_PATH)) as connection:
        with connection:
            connection.executemany(
                """
                INSERT INTO messages (conversation_id, role, content)
                VALUES (?, ?, ?)
                """,
                [
                    (conversation_id, "user", question),
                    (conversation_id, "assistant", answer),
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