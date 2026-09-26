"""
agent/graph.py

The actual "agent" — a LangGraph state machine with 5 nodes:

  retrieve_node   -> perceive: pull relevant facts from the knowledge base
  reason_node     -> reason: LLM decides intent + action + params + why
  approval_node   -> safety: pause for a human if the action is critical
  execute_node    -> act: actually run the chosen Python action function
  explain_node    -> explain: build the final answer + write the audit log

No step uses hardcoded if/else rules to answer the user's question — the
LLM (Gemini, free tier) does all the reasoning and decides which action to
call. Python code only executes what the LLM decided and enforces the
safety gate for critical actions.
"""

import json
import os
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI

from knowledge.retriever import KnowledgeRetriever
from actions.actions import ACTIONS, CRITICAL_ACTIONS
from memory.audit_log import log_interaction, get_recent_interactions

# ---------------------------------------------------------------------------
# LLM setup — Google Gemini free tier.
# Get a free key (no credit card) at https://aistudio.google.com/app/apikey
# Model: gemini-3.1-flash-lite is the current stable, cost-free-tier-friendly
# model as of late 2026. If Google renames/retires it, swap the string below
# for whatever shows as "stable" on https://ai.google.dev/gemini-api/docs/models
# ---------------------------------------------------------------------------
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

llm = ChatGoogleGenerativeAI(
    model=GEMINI_MODEL,
    temperature=0,
    google_api_key=os.getenv("GEMINI_API_KEY"),
)

retriever = KnowledgeRetriever()

AVAILABLE_ACTIONS_DESC = """
- create_ticket(issue, severity): file an IT/support ticket for a hardware/software problem
- check_leave_balance(employee_id): look up how many leave days an employee has left
- request_leave(employee_id, days): submit a leave request
- request_wfh_exception(employee_id, days): request extra work-from-home days
- reset_password(employee_id): CRITICAL — resets an employee's password
- deactivate_account(employee_id): CRITICAL — deactivates an employee account
- escalate_to_hr(issue): send an unresolved/sensitive issue to HR
- answer_only(): use this when the query is purely informational and needs no action
"""


class AgentState(TypedDict):
    query: str
    employee_id: str
    retrieved: list
    intent: str
    action_name: str
    params: dict
    reasoning: str
    is_critical: bool
    approved: bool
    result: dict
    final_answer: str


# --------------------------- Nodes ---------------------------------------

def retrieve_node(state: AgentState) -> AgentState:
    results = retriever.retrieve(state["query"], top_k=3)
    state["retrieved"] = results
    return state


def reason_node(state: AgentState) -> AgentState:
    context_block = "\n".join(f"- ({r['topic']}) {r['content']}" for r in state["retrieved"])
    history = get_recent_interactions(limit=3)
    history_block = "\n".join(f"- Q: {q} -> action: {a} -> result: {res}" for q, a, res in history) or "None"

    prompt = f"""You are an internal Helpdesk Agent. You must decide what to do about an
employee's request using ONLY the internal knowledge provided below. Do not
invent policies that are not in the knowledge base.

Internal knowledge relevant to this query:
{context_block}

Recent past interactions (for context/continuity):
{history_block}

Available actions you may choose from:
{AVAILABLE_ACTIONS_DESC}

Employee query: "{state['query']}"
Employee ID: {state.get('employee_id', 'unknown')}

Think about the employee's intent, then decide the single best action.
Respond with ONLY a valid JSON object, no markdown, no extra text, in this
exact shape:
{{
  "intent": "<one short phrase describing what the user wants>",
  "action": "<one of the action names above, exactly as written>",
  "params": {{"...": "..."}},
  "reasoning": "<2-3 sentences explaining why this action and not another>",
  "is_critical": true or false
}}
"""

    response = llm.invoke(prompt)
    content = response.content
    if isinstance(content, list):
        raw = "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        ).strip()
    else:
        raw = str(content).strip()

    # Be defensive: strip accidental markdown code fences if the model adds them
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.replace("json\n", "", 1)

    try:
        decision = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback so the graph never crashes on a malformed LLM response
        decision = {
            "intent": "unclear",
            "action": "answer_only",
            "params": {},
            "reasoning": f"Could not parse model output, defaulting to no action. Raw: {raw[:200]}",
            "is_critical": False,
        }

    state["intent"] = decision.get("intent", "")
    state["action_name"] = decision.get("action", "answer_only")
    state["params"] = decision.get("params", {}) or {}
    state["reasoning"] = decision.get("reasoning", "")
    state["is_critical"] = bool(decision.get("is_critical", False)) or (
        decision.get("action") in CRITICAL_ACTIONS
    )

    # Make sure the employee_id is available to the action even if the LLM omits it
    state["params"].setdefault("employee_id", state.get("employee_id", "unknown"))
    return state


def approval_node(state: AgentState) -> AgentState:
    print("\n[HUMAN APPROVAL REQUIRED]")
    print(f"  Action proposed : {state['action_name']}")
    print(f"  Parameters      : {state['params']}")
    print(f"  Agent reasoning : {state['reasoning']}")
    answer = input("  Approve this action? (y/n): ").strip().lower()
    state["approved"] = answer == "y"
    return state


def execute_node(state: AgentState) -> AgentState:
    if state["is_critical"] and not state.get("approved", False):
        state["result"] = {
            "status": "rejected",
            "message": "Action was NOT executed — critical action was not approved by a human.",
        }
        return state

    action_fn = ACTIONS.get(state["action_name"], ACTIONS["answer_only"])
    try:
        state["result"] = action_fn(**state["params"])
    except TypeError as e:
        state["result"] = {"status": "error", "message": f"Action failed due to bad parameters: {e}"}
    return state


def explain_node(state: AgentState) -> AgentState:
    final_answer = (
        f"Intent understood: {state['intent']}\n"
        f"Reasoning: {state['reasoning']}\n"
        f"Action taken: {state['action_name']}\n"
        f"Result: {state['result'].get('message', state['result'])}"
    )
    state["final_answer"] = final_answer

    log_interaction(
        query=state["query"],
        intent=state["intent"],
        action_name=state["action_name"],
        reasoning=state["reasoning"],
        was_critical=state["is_critical"],
        approved_by_human=state.get("approved", not state["is_critical"]),
        result=state["result"],
    )
    return state


# --------------------------- Graph wiring ---------------------------------

def route_after_reason(state: AgentState) -> str:
    return "approval_node" if state["is_critical"] else "execute_node"


def build_agent():
    graph = StateGraph(AgentState)

    graph.add_node("retrieve_node", retrieve_node)
    graph.add_node("reason_node", reason_node)
    graph.add_node("approval_node", approval_node)
    graph.add_node("execute_node", execute_node)
    graph.add_node("explain_node", explain_node)

    graph.set_entry_point("retrieve_node")
    graph.add_edge("retrieve_node", "reason_node")
    graph.add_conditional_edges("reason_node", route_after_reason, {
        "approval_node": "approval_node",
        "execute_node": "execute_node",
    })
    graph.add_edge("approval_node", "execute_node")
    graph.add_edge("execute_node", "explain_node")
    graph.add_edge("explain_node", END)

    return graph.compile()
