"""
export_audit_log.py

Exports the agent's SQLite audit trail (agent_memory.db) to a readable text
file, grouped by plan_id. Every row was written by the agent itself while it
ran (see memory/audit_log.py); nothing here is edited or generated.

Usage:
    python3 export_audit_log.py                 # writes audit_log_export.txt
    python3 export_audit_log.py my_logs.txt      # custom output name
"""

import os
import sqlite3
import sys
from collections import OrderedDict

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_memory.db")
out_path = sys.argv[1] if len(sys.argv) > 1 else "audit_log_export.txt"

if not os.path.exists(DB_PATH):
    raise SystemExit("agent_memory.db not found. Run python3 main.py and try a few queries first.")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM audit_log ORDER BY id ASC").fetchall()
conn.close()

plans = OrderedDict()
for r in rows:
    plans.setdefault(r["plan_id"], []).append(r)

lines = []
lines.append("AUDIT LOG EXPORT - Autonomous Knowledge Execution Agent")
lines.append(f"Total plans: {len(plans)}   Total logged steps: {len(rows)}")
lines.append("=" * 78)

for plan_id, steps in plans.items():
    lines.append("")
    lines.append(f"PLAN {plan_id}   |   query: {steps[0]['query']}")
    lines.append("-" * 78)
    for s in steps:
        lines.append(f"  [{s['timestamp']}] step {s['step_id']}: {s['step_description']}")
        lines.append(f"      action            : {s['action_name']}")
        lines.append(f"      reasoning         : {s['reasoning']}")
        lines.append(f"      critical          : {'yes' if s['was_critical'] else 'no'}")
        lines.append(f"      human approved    : {'yes' if s['approved_by_human'] else 'no'}")
        lines.append(f"      ran in parallel   : {'yes' if s['executed_in_parallel'] else 'no'}")
        lines.append(f"      result            : {s['result']}")
        lines.append("")

text = "\n".join(lines)
with open(out_path, "w", encoding="utf-8") as f:
    f.write(text)

print(text)
print(f"\nSaved to {out_path}")
