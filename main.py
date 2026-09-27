"""
main.py

Entry point. Run with:  python3 main.py

Loads GEMINI_API_KEY from .env, builds the LangGraph agent (retrieve ->
recall memory -> plan -> escalate-or-execute -> explain), and runs a CLI
loop so you can talk to the Helpdesk Agent.
"""

import os
from dotenv import load_dotenv

load_dotenv()

if not os.getenv("GEMINI_API_KEY"):
    raise SystemExit(
        "GEMINI_API_KEY not found. Copy .env.example to .env and paste your "
        "free key from https://aistudio.google.com/app/apikey"
    )

from agent.graph import build_agent

print("Setting up knowledge sources and agent (first run downloads a small local model)...")
agent = build_agent()

print("=" * 70)
print(" Autonomous Knowledge Execution Agent — Internal Helpdesk")
print(" Type your request (or 'exit' to quit)")
print("=" * 70)

employee_id = input("Enter your employee ID (or press Enter for 'EMP001'): ").strip() or "EMP001"

while True:
    query = input("\nYou: ").strip()
    if query.lower() in ("exit", "quit"):
        print("Goodbye!")
        break
    if not query:
        continue

    initial_state = {
        "query": query,
        "employee_id": employee_id,
        "retrieved": [],
        "memory_snippets": [],
        "plan": {},
        "plan_id": "",
        "step_outcomes": [],
        "final_answer": "",
    }

    final_state = agent.invoke(initial_state)

    print("\n--- Agent ---")
    print(final_state["final_answer"])