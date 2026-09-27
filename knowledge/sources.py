"""
knowledge/sources.py

Loads FOUR genuinely different internal knowledge source types and
normalizes them into one common shape: {"text", "source", "meta"}.
This normalized list is what gets embedded into the vector index in
retriever.py — so from the agent's point of view, a policy sentence from
JSON, a CSV ticket record, a SQL employee row, and an unstructured
handbook chunk are all just "documents" it can search over the same way.

  1. JSON      -> data/knowledge_base.json      (structured policy entries)
  2. CSV       -> data/tickets_history.csv      (structured historical records)
  3. Database  -> employees.db (SQLite)         (structured relational data)
  4. Unstructured text -> data/handbook_unstructured.txt (chunked free text)
"""

import json
import os
import csv

from knowledge.chunker import chunk_text
from knowledge.db_setup import init_employee_db, all_employees_as_documents

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
JSON_PATH = os.path.join(BASE_DIR, "data", "knowledge_base.json")
CSV_PATH = os.path.join(BASE_DIR, "data", "tickets_history.csv")
HANDBOOK_PATH = os.path.join(BASE_DIR, "data", "handbook_unstructured.txt")


def load_json_source():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        entries = json.load(f)
    return [
        {
            "text": f"{e['topic']}: {e['content']}",
            "source": "policy_kb (JSON)",
            "meta": {"topic": e["topic"]},
        }
        for e in entries
    ]


def load_csv_source():
    docs = []
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = (
                f"Past ticket {row['ticket_id']} ({row['severity']} severity, {row['status']}): "
                f"issue was '{row['issue']}'. Resolution: {row['resolved_notes']}."
            )
            docs.append({"text": text, "source": "ticket_history (CSV)", "meta": row})
    return docs


def load_db_source():
    init_employee_db()  # create + seed once, safe to call repeatedly
    docs = all_employees_as_documents()
    for d in docs:
        d["source"] = "employee_db (SQL Database)"
    return docs


def load_unstructured_source():
    with open(HANDBOOK_PATH, "r", encoding="utf-8") as f:
        raw_text = f.read()
    chunks = chunk_text(raw_text, chunk_size_words=90, overlap_words=15)
    return [
        {"text": chunk, "source": "handbook (unstructured text)", "meta": {"chunk_index": i}}
        for i, chunk in enumerate(chunks)
    ]


def load_all_sources():
    """Combine all 4 source types into one list of normalized documents."""
    docs = []
    docs.extend(load_json_source())
    docs.extend(load_csv_source())
    docs.extend(load_db_source())
    docs.extend(load_unstructured_source())
    return docs