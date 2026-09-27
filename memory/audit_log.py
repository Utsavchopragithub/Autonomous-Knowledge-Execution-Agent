"""
memory/audit_log.py

SQLite-based audit trail (built into Python, no server needed).

Now tracks a plan_id per query, since one query can produce MULTIPLE steps
(multi-step planning). Every step of every plan gets its own row, so the
full chain of what the agent decided and did is fully traceable -- this is
what "maintain audit logs for every action performed" means in practice.
"""

import sqlite3
import os
import uuid
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "agent_memory.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            plan_id TEXT,
            query TEXT,
            step_id TEXT,
            step_description TEXT,
            action_name TEXT,
            reasoning TEXT,
            was_critical INTEGER,
            approved_by_human INTEGER,
            executed_in_parallel INTEGER,
            result TEXT
        )
        """
    )
    return conn


def new_plan_id() -> str:
    return uuid.uuid4().hex[:8]


def log_step(
    plan_id,
    query,
    step_id,
    step_description,
    action_name,
    reasoning,
    was_critical,
    approved_by_human,
    executed_in_parallel,
    result,
):
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO audit_log
        (timestamp, plan_id, query, step_id, step_description, action_name,
         reasoning, was_critical, approved_by_human, executed_in_parallel, result)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.utcnow().isoformat(),
            plan_id,
            query,
            step_id,
            step_description,
            action_name,
            reasoning,
            int(bool(was_critical)),
            int(bool(approved_by_human)),
            int(bool(executed_in_parallel)),
            str(result),
        ),
    )
    conn.commit()
    conn.close()


def get_recent_interactions(limit: int = 5):
    """Short-term / recency-based memory: last few individual steps, oldest first."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT query, action_name, result FROM audit_log ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return list(reversed(rows))


def get_all_interactions_for_memory():
    """Used by memory/long_term.py to build the semantic long-term memory index."""
    conn = _get_conn()
    rows = conn.execute("SELECT query, action_name, result FROM audit_log ORDER BY id ASC").fetchall()
    conn.close()
    return rows


def print_all_logs():
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM audit_log ORDER BY id ASC").fetchall()
    conn.close()
    for row in rows:
        print(row)