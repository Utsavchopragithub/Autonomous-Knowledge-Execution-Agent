"""
knowledge/db_setup.py

Why this file exists: the assignment explicitly asks for multiple internal
knowledge source TYPES (Database, JSON, CSV, Vector DB). Everything else in
this project is file-based (JSON/CSV/TXT). This file gives us a genuine
SQL database source — a local SQLite file (employees.db) — so the agent
can also query/act on real relational data, not just text chunks.
"""

import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "employees.db")
SEED_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "employees_seed.json")


def init_employee_db():
    """Create the employees table and seed it once. Safe to call every run."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS employees (
            employee_id TEXT PRIMARY KEY,
            name TEXT,
            department TEXT,
            leave_balance INTEGER
        )
        """
    )
    existing = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    if existing == 0:
        with open(SEED_PATH, "r", encoding="utf-8") as f:
            seed = json.load(f)
        conn.executemany(
            "INSERT INTO employees (employee_id, name, department, leave_balance) VALUES (?, ?, ?, ?)",
            [(e["employee_id"], e["name"], e["department"], e["leave_balance"]) for e in seed],
        )
        conn.commit()
    conn.close()


def get_employee(employee_id: str):
    """Direct structured lookup — used by actions, not by the fuzzy retriever."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT employee_id, name, department, leave_balance FROM employees WHERE employee_id = ?",
        (employee_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return {"employee_id": row[0], "name": row[1], "department": row[2], "leave_balance": row[3]}


def update_leave_balance(employee_id: str, new_balance: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE employees SET leave_balance = ? WHERE employee_id = ?", (new_balance, employee_id))
    conn.commit()
    conn.close()


def all_employees_as_documents():
    """Used by the retriever to make DB rows searchable alongside other sources."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT employee_id, name, department, leave_balance FROM employees").fetchall()
    conn.close()
    docs = []
    for employee_id, name, department, leave_balance in rows:
        text = (
            f"Employee {employee_id} ({name}) works in {department} and currently has "
            f"{leave_balance} leave days remaining."
        )
        docs.append({"text": text, "source": "employee_db", "meta": {"employee_id": employee_id}})
    return docs