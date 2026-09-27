"""
agent/graph.py

The upgraded agent flow (LangGraph state machine):

  retrieve_node   -> pulls from ALL 4 knowledge sources (hybrid search)
  recall_node     -> semantic long-term memory recall (not just "last 3")
  plan_node       -> LLM plans one or more steps, flags confidence/conflicts
  route_node      -> if confidence is low / a conflict was flagged, escalate
                      to a human instead of guessing; otherwise proceed
  escalate_node    -> auto-files an HR escalation with the reason attached
  execute_node    -> runs the plan (executor.py: parallel batches + human
                      approval gate for critical steps)
  explain_node    -> builds the final explanation, step by step

Nothing here hardcodes WHAT to do -- the LLM (Gemini) decides the plan;
Python only retrieves data, enforces the safety gate, executes whatever
was decided, and logs everything.
"""

from typing import TypedDict

from langgraph.graph import StateGraph, END

from knowledge.retriever import KnowledgeRetriever
from memory.long_term import LongTermMemory
from memory.audit_log import new_plan_id, log_step
from agent.planner import build_plan
from agent.executor import execute_plan
from actions.actions import escalate_to_hr

retriever = KnowledgeRetriever()
long_term_memory = LongTermMemory()


class AgentState(TypedDict):
    query: str
    employee_id: str
    retrieved: list
    memory_snippets: list
    plan: dict
    plan_id: str
    step_outcomes: list
    final_answer: str


def retrieve_node(state: AgentState) -> AgentState:
    state["retrieved"] = retriever.retrieve(state["query"], top_k=5)
    return state


def recall_node(state: AgentState) -> AgentState:
    state["memory_snippets"] = long_term_memory.recall(state["query"], top_k=3)
    return state


def plan_node(state: AgentState) -> AgentState:
    state["plan"] = build_plan(
        query=state["query"],
        employee_id=state.get("employee_id", "unknown"),
        retrieved=state["retrieved"],
        memory_snippets=state["memory_snippets"],
    )
    state["plan_id"] = new_plan_id()
    return state


def route_after_plan(state: AgentState) -> str:
    plan = state["plan"]
    if plan.get("confidence") == "low" or plan.get("conflicts_or_gaps"):
        return "escalate_node"
    if not plan.get("steps"):
        return "escalate_node"
    return "execute_node"


def escalate_node(state: AgentState) -> AgentState:
    reason = state["plan"].get("conflicts_or_gaps") or "Low confidence in available knowledge to safely act."
    result = escalate_to_hr(issue=f"Query: '{state['query']}'. Reason: {reason}")
    log_step(
        state["plan_id"], state["query"], "escalation", "Escalated due to low confidence / conflicting info",
        "escalate_to_hr", reason, False, True, False, result,
    )
    state["step_outcomes"] = [{
        "step": {"id": "escalation", "description": "Escalated to HR", "action": "escalate_to_hr", "reasoning": reason},
        "result": result,
        "approved": True,
        "parallel": False,
    }]
    return state


def _cli_approve(step: dict) -> bool:
    print("\n[HUMAN APPROVAL REQUIRED]")
    print(f"  Step            : {step.get('description')}")
    print(f"  Action proposed : {step['action']}")
    print(f"  Parameters      : {step['params']}")
    print(f"  Reasoning       : {step.get('reasoning', '')}")
    answer = input("  Approve this action? (y/n): ").strip().lower()
    return answer == "y"


def execute_node(state: AgentState) -> AgentState:
    state["step_outcomes"] = execute_plan(
        plan=state["plan"],
        plan_id=state["plan_id"],
        query=state["query"],
        approve_fn=_cli_approve,
    )
    return state


def explain_node(state: AgentState) -> AgentState:
    plan = state["plan"]
    lines = []

    if plan.get("confidence") in ("medium", "low") or plan.get("conflicts_or_gaps"):
        lines.append(f"Confidence: {plan.get('confidence', 'unknown')}")
    if plan.get("conflicts_or_gaps"):
        lines.append(f"Note: {plan['conflicts_or_gaps']}")

    for outcome in state["step_outcomes"]:
        step = outcome["step"]
        result = outcome["result"]
        tag = " [ran in parallel]" if outcome.get("parallel") else ""
        lines.append(
            f"\nStep {step.get('id', '?')}{tag}: {step.get('description', step.get('action'))}\n"
            f"  Reasoning: {step.get('reasoning', '')}\n"
            f"  Action: {step.get('action')}\n"
            f"  Result: {result.get('message', result)}"
        )

    state["final_answer"] = "\n".join(lines)
    return state


def build_agent():
    graph = StateGraph(AgentState)

    graph.add_node("retrieve_node", retrieve_node)
    graph.add_node("recall_node", recall_node)
    graph.add_node("plan_node", plan_node)
    graph.add_node("escalate_node", escalate_node)
    graph.add_node("execute_node", execute_node)
    graph.add_node("explain_node", explain_node)

    graph.set_entry_point("retrieve_node")
    graph.add_edge("retrieve_node", "recall_node")
    graph.add_edge("recall_node", "plan_node")
    graph.add_conditional_edges("plan_node", route_after_plan, {
        "escalate_node": "escalate_node",
        "execute_node": "execute_node",
    })
    graph.add_edge("escalate_node", "explain_node")
    graph.add_edge("execute_node", "explain_node")
    graph.add_edge("explain_node", END)

    return graph.compile()