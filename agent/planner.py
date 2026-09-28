"""
agent/planner.py

This replaces the old "one query -> one action" reasoning with real
PLANNING: the LLM looks at the query + everything retrieved from all 4
knowledge sources + relevant long-term memory, and returns:

  - confidence: how sure it is, given what it found
  - conflicts_or_gaps: plain-English note if sources disagree or info is
    missing (this is what makes "handle incomplete/conflicting information
    gracefully" a real behavior instead of just a README bullet point)
  - steps: an ORDERED list of one or more actions to take, each with its
    own reasoning and a `depends_on` list -- steps with no shared
    dependencies can be run in PARALLEL (see agent/executor.py)

The LLM does 100% of the deciding here; Python only validates the JSON
shape and enforces safety rules afterward.
"""

import json
from agent.llm_client import llm, extract_text

AVAILABLE_ACTIONS_DESC = """
- create_ticket(issue, severity): file an IT/support ticket
- check_leave_balance(employee_id): look up an employee's leave balance from the employee database
- request_leave(employee_id, days): submit a leave request
- request_wfh_exception(employee_id, days): request extra work-from-home days
- reset_password(employee_id): CRITICAL - resets a password. Choose this when the employee asks for a reset; the system itself pauses and asks a human to approve before it runs.
- deactivate_account(employee_id): CRITICAL - deactivates an account. Choose this when asked to deactivate; the system itself pauses and asks a human to approve before it runs.
- escalate_to_hr(issue): send an issue to HR for manual review
- lookup_similar_tickets(issue): search past ticket history (CSV records) for similar resolved issues
- answer_only(): use when the query is purely informational and needs no action
"""

PLANNER_PROMPT = """You are the planning brain of an internal Helpdesk Agent.
You have access to FOUR internal knowledge sources (a policy JSON file, a
CSV of past support tickets, a SQL employee database, and an unstructured
company handbook) -- results from all of them are shown below, each
labeled with its source. Sources can occasionally disagree or be
incomplete; you must notice this rather than silently pick one.

Retrieved knowledge (each item shows which source it came from):
{context_block}

Relevant long-term memory (past interactions that might matter here, if any):
{memory_block}

Available actions:
{actions_block}

Employee query: "{query}"
Employee ID: {employee_id}

Do the following:
1. Judge your confidence given the retrieved knowledge: "high", "medium", or "low".
   Use "low" if sources conflict on a material fact (e.g. different leave-day
   numbers) or if there simply isn't enough information to safely act.
2. If there IS a conflict or gap, describe it in one sentence in
   "conflicts_or_gaps" (empty string if none).
3. Break the request into one or more ORDERED steps. Most queries need only
   one step. Use multiple steps only when the request genuinely requires a
   sequence (e.g. "check my balance and then request 2 days off").
4. For each step give it a step id ("s1", "s2", ...), a short description,
   the action name (from the list above), its params, reasoning, whether it
   is critical, and a "depends_on" list of step ids it must wait for (empty
   list if it can run immediately / in parallel with other independent steps).
5. Do NOT swap a critical action for a safer one (for example a ticket) just 
   because it is critical. Human approval is enforced by the system after you
   plan, so choose the action that actually fulfils the request and set is_critical to true.

Respond with ONLY valid JSON, no markdown, in this exact shape:
{{
  "confidence": "high" | "medium" | "low",
  "conflicts_or_gaps": "<one sentence, or empty string>",
  "steps": [
    {{
      "id": "s1",
      "description": "<short description>",
      "action": "<action name>",
      "params": {{"...": "..."}},
      "reasoning": "<2-3 sentences>",
      "is_critical": true or false,
      "depends_on": []
    }}
  ]
}}
"""


def build_plan(query: str, employee_id: str, retrieved: list, memory_snippets: list) -> dict:
    context_block = "\n".join(f"- [{r['source']}] {r['text']}" for r in retrieved) or "None found."
    memory_block = "\n".join(f"- {m}" for m in memory_snippets) or "None relevant."

    prompt = PLANNER_PROMPT.format(
        context_block=context_block,
        memory_block=memory_block,
        actions_block=AVAILABLE_ACTIONS_DESC,
        query=query,
        employee_id=employee_id,
    )

    response = llm.invoke(prompt)
    raw = extract_text(response)

    try:
        plan = json.loads(raw)
    except json.JSONDecodeError:
        # Never crash the agent on a malformed LLM response -- fail safe
        # by escalating instead of guessing.
        plan = {
            "confidence": "low",
            "conflicts_or_gaps": f"Could not parse planning output reliably. Raw: {raw[:200]}",
            "steps": [],
        }

    # Defensive defaults so downstream code never KeyErrors on a slightly off response
    plan.setdefault("confidence", "medium")
    plan.setdefault("conflicts_or_gaps", "")
    plan.setdefault("steps", [])
    for step in plan["steps"]:
        step.setdefault("params", {})
        step.setdefault("depends_on", [])
        step.setdefault("is_critical", False)
        step["params"].setdefault("employee_id", employee_id)

    return plan