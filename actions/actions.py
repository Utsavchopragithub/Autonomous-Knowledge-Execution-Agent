"""
actions/actions.py

These are the real, independent actions the agent can take. In a production
system these would call real APIs (ticketing system, HRMS, IT admin panel).
Here they are simulated (they return a structured result and print a log
line) so the assignment can be run and evaluated without any paid backend —
the AGENT REASONING is what's being graded, not a real ticketing integration.

Every action is registered in ACTIONS so the agent's decision node can look
up and call the right function by name. CRITICAL_ACTIONS lists the ones that
must never run without a human explicitly approving them first.
"""

import random
import string


def _fake_id(prefix: str) -> str:
    return f"{prefix}-{''.join(random.choices(string.digits, k=4))}"


def create_ticket(issue: str, severity: str = "medium", **kwargs) -> dict:
    ticket_id = _fake_id("TCK")
    return {
        "status": "created",
        "ticket_id": ticket_id,
        "issue": issue,
        "severity": severity,
        "message": f"Support ticket {ticket_id} created for: {issue} (severity: {severity}).",
    }


def check_leave_balance(employee_id: str = "unknown", **kwargs) -> dict:
    # Simulated balance — in a real system this would query an HRMS.
    balance = random.randint(2, 18)
    return {
        "status": "success",
        "employee_id": employee_id,
        "balance_days": balance,
        "message": f"Employee {employee_id} has {balance} leave days remaining.",
    }


def request_leave(employee_id: str = "unknown", days: int = 1, **kwargs) -> dict:
    request_id = _fake_id("LV")
    return {
        "status": "submitted",
        "request_id": request_id,
        "days": days,
        "message": f"Leave request {request_id} submitted for {days} day(s).",
    }


def request_wfh_exception(employee_id: str = "unknown", days: int = 1, **kwargs) -> dict:
    request_id = _fake_id("WFH")
    return {
        "status": "submitted",
        "request_id": request_id,
        "message": f"WFH exception request {request_id} submitted for manager approval.",
    }


def reset_password(employee_id: str = "unknown", **kwargs) -> dict:
    # CRITICAL — should only reach here after human approval.
    return {
        "status": "completed",
        "employee_id": employee_id,
        "message": f"Password for {employee_id} has been reset and a temporary password sent.",
    }


def deactivate_account(employee_id: str = "unknown", **kwargs) -> dict:
    # CRITICAL — irreversible action.
    return {
        "status": "completed",
        "employee_id": employee_id,
        "message": f"Account for {employee_id} has been deactivated.",
    }


def escalate_to_hr(issue: str, **kwargs) -> dict:
    case_id = _fake_id("HR")
    return {
        "status": "escalated",
        "case_id": case_id,
        "message": f"Issue escalated to HR as case {case_id}: {issue}",
    }


def answer_only(**kwargs) -> dict:
    """Used when the query is purely informational and no action is needed."""
    return {"status": "no_action_needed", "message": "This was an informational query; no action was taken."}


# Registry the agent's decision node looks up by name.
ACTIONS = {
    "create_ticket": create_ticket,
    "check_leave_balance": check_leave_balance,
    "request_leave": request_leave,
    "request_wfh_exception": request_wfh_exception,
    "reset_password": reset_password,
    "deactivate_account": deactivate_account,
    "escalate_to_hr": escalate_to_hr,
    "answer_only": answer_only,
}

# Actions that must be approved by a human before execute_node runs them.
CRITICAL_ACTIONS = {"reset_password", "deactivate_account"}
