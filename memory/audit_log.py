"""
memory/audit_log.py

Free, zero-setup persistence using Python's built-in sqlite3 module (no
external DB server needed). Two things live here:

1. audit_log table — every query -> decision -> action -> result, so every
   run is fully traceable (this satisfies the "maintain audit logs" bonus
   requirement).
2. get_recent_interactions() — used to give the agent simple long-term
   memory: the last few interactions are pulled back in as extra context
   before reasoning, so the agent "remembers" recent conversation.
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "agent_memory.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            query TEXT,
            intent TEXT,
            action_name TEXT,
            reasoning TEXT,
            was_critical INTEGER,
            approved_by_human INTEGER,
            result TEXT
        )
        """
    )
    return conn


def log_interaction(query, intent, action_name, reasoning, was_critical, approved_by_human, result):
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO audit_log
        (timestamp, query, intent, action_name, reasoning, was_critical, approved_by_human, result)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.utcnow().isoformat(),
            query,
            intent,
            action_name,
            reasoning,
            int(bool(was_critical)),
            int(bool(approved_by_human)),
            str(result),
        ),
    )
    conn.commit()
    conn.close()


def get_recent_interactions(limit: int = 5):
    conn = _get_conn()
    rows = conn.execute(
        "SELECT query, action_name, result FROM audit_log ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    # Return oldest-first so it reads naturally as history
    return list(reversed(rows))


def print_all_logs():
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM audit_log ORDER BY id ASC").fetchall()
    conn.close()
    for row in rows:
        print(row)
