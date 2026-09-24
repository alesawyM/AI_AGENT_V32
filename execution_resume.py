from typing import Any, Dict, Optional

from execution_state import get_active_execution


def prepare_execution_resume() -> Dict[str, Any]:
    """
    Phase 11: Execution Resume / Crash Recovery.

    Detects whether a previous execution was left active.
    This layer does not automatically execute or repeat work.
    It only prepares a safe resume decision.
    """

    active_execution: Optional[
        Dict[str, Any]
    ] = get_active_execution()


    # --------------------------------------------------
    # NO ACTIVE EXECUTION
    # --------------------------------------------------

    if not active_execution:

        return {
            "resume_required": False,
            "action": "none",
            "reason": (
                "No active execution requires recovery."
            ),
            "safe_to_resume": False,
            "execution": None,
        }


    status = str(
        active_execution.get(
            "status",
            ""
        )
    ).strip().lower()


    request = active_execution.get(
        "request"
    )


    # --------------------------------------------------
    # APPROVAL STATE
    # --------------------------------------------------

    if status == "approval_required":

        return {
            "resume_required": False,
            "action": "wait_for_approval",
            "reason": (
                "Previous execution requires user approval."
            ),
            "safe_to_resume": False,
            "execution": active_execution,
        }


    # --------------------------------------------------
    # ACTIVE / RUNNING EXECUTION
    # --------------------------------------------------

    if status in {
        "running",
        "reviewed",
        "replanning",
    }:

        return {
            "resume_required": True,
            "action": "prepare_resume",
            "reason": (
                "An unfinished execution was detected."
            ),
            "safe_to_resume": False,
            "execution": active_execution,
            "request": request,
        }


    # --------------------------------------------------
    # UNKNOWN ACTIVE STATE
    # --------------------------------------------------

    return {
        "resume_required": False,
        "action": "stop_safely",
        "reason": (
            "Active execution state is not recognized."
        ),
        "safe_to_resume": False,
        "execution": active_execution,
    }
