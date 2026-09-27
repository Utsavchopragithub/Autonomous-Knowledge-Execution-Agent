"""
agent/executor.py

Takes the ordered list of steps from planner.py and actually runs them:

  1. TOPOLOGICAL BATCHING: steps are grouped into "batches" -- a step goes
     into the next batch once everything it depends_on has already run.
     Steps in the SAME batch have no dependency on each other.
  2. PARALLEL EXECUTION: all non-critical steps in a batch run at the same
     time using a thread pool (ThreadPoolExecutor), instead of one-by-one.
  3. CRITICAL STEPS are pulled out and run one at a time, each pausing for
     human approval first -- they never run silently inside a parallel
     batch, since a person needs to actually read and approve each one.

Every step (critical or not, parallel or not) is logged to the audit trail
with the same plan_id, so the full plan is traceable as one unit.
"""

from concurrent.futures import ThreadPoolExecutor

from actions.actions import ACTIONS, CRITICAL_ACTIONS
from memory.audit_log import log_step


def _is_critical(step: dict) -> bool:
    return bool(step.get("is_critical")) or step.get("action") in CRITICAL_ACTIONS


def _run_single_action(step: dict) -> dict:
    action_fn = ACTIONS.get(step["action"], ACTIONS["answer_only"])
    try:
        return action_fn(**step["params"])
    except TypeError as e:
        return {"status": "error", "message": f"Action failed due to bad parameters: {e}"}


def _batch_steps(steps: list):
    """Group steps into dependency-respecting batches for parallel execution."""
    remaining = {s["id"]: s for s in steps}
    done = set()
    batches = []

    while remaining:
        ready = [
            s for s in remaining.values()
            if all(dep in done for dep in s.get("depends_on", []))
        ]
        if not ready:
            # Circular or unresolved dependency -- bail out safely rather than hang
            ready = list(remaining.values())
        batches.append(ready)
        for s in ready:
            done.add(s["id"])
            del remaining[s["id"]]
    return batches


def execute_plan(plan: dict, plan_id: str, query: str, approve_fn) -> list:
    """
    approve_fn: a function(step) -> bool, called for every critical step so
    the CLI (or any future UI) controls how approval is actually collected.
    Returns a list of {step, result, approved} for the explain step.
    """
    steps = plan.get("steps", [])
    step_outcomes = {}

    batches = _batch_steps(steps)

    for batch in batches:
        critical_steps = [s for s in batch if _is_critical(s)]
        parallel_steps = [s for s in batch if not _is_critical(s)]

        # Critical steps: one at a time, each needs explicit human approval.
        for step in critical_steps:
            approved = approve_fn(step)
            if approved:
                result = _run_single_action(step)
            else:
                result = {"status": "rejected", "message": "Critical action was not approved by a human."}
            step_outcomes[step["id"]] = {"step": step, "result": result, "approved": approved, "parallel": False}
            log_step(
                plan_id, query, step["id"], step.get("description", ""), step["action"],
                step.get("reasoning", ""), True, approved, False, result,
            )

        # Non-critical steps in this batch: run together in parallel threads.
        if parallel_steps:
            with ThreadPoolExecutor(max_workers=max(1, len(parallel_steps))) as pool:
                futures = {pool.submit(_run_single_action, step): step for step in parallel_steps}
                for future in futures:
                    step = futures[future]
                    result = future.result()
                    step_outcomes[step["id"]] = {
                        "step": step, "result": result, "approved": True, "parallel": len(parallel_steps) > 1,
                    }
                    log_step(
                        plan_id, query, step["id"], step.get("description", ""), step["action"],
                        step.get("reasoning", ""), False, True, len(parallel_steps) > 1, result,
                    )

    return [step_outcomes[s["id"]] for s in steps]