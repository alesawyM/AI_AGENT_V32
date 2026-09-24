from typing import Any, Dict


def execute_recovery_action(
    governance: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """
    Phase 15: Safe Recovery Execution.

    Converts a recovery governance decision into a safe,
    non-destructive execution result.

    This layer does not directly re-run the original user task.
    It only authorizes and prepares safe recovery actions.
    """

    if not isinstance(governance, dict):
        return {
            "executed": False,
            "action": "none",
            "status": "stopped",
            "reason": "Invalid recovery governance decision.",
        }


    decision = str(
        governance.get("decision", "")
    ).strip().lower()


    action = str(
        governance.get("action", "")
    ).strip().lower()


    automatic_execution = bool(
        governance.get(
            "automatic_execution",
            False
        )
    )


    # --------------------------------------------------
    # BLOCKED RECOVERY
    # --------------------------------------------------

    if decision == "block":

        return {
            "executed": False,
            "action": action or "unknown",
            "status": "blocked",
            "reason": (
                "Recovery execution was blocked by governance."
            ),
        }


    # --------------------------------------------------
    # NO ACTION REQUIRED
    # --------------------------------------------------

    if action == "none":

        return {
            "executed": False,
            "action": "none",
            "status": "no_action",
            "reason": (
                "No recovery action is required."
            ),
        }


    # --------------------------------------------------
    # ANALYSIS REQUIRED
    # --------------------------------------------------

    if action == "analyze_before_resume":

        return {
            "executed": False,
            "action": action,
            "status": "waiting_for_analysis",
            "reason": (
                "Recovery requires analysis before execution."
            ),
        }


    # --------------------------------------------------
    # APPROVAL / SAFETY STOP
    # --------------------------------------------------

    if action in {
        "approval_required",
        "stop_safely",
    }:

        return {
            "executed": False,
            "action": action,
            "status": "stopped",
            "reason": (
                "Recovery action requires a safety stop."
            ),
        }


    # --------------------------------------------------
    # SAFE RESUME EXECUTION
    # --------------------------------------------------

    if (
        decision == "allow"
        and automatic_execution
        and action == "resume_execution"
    ):

        return {
            "executed": True,
            "action": action,
            "status": "prepared",
            "reason": (
                "Execution recovery was safely prepared."
            ),
        }


    # --------------------------------------------------
    # SAFE CHECKPOINT RESUME
    # --------------------------------------------------

    if (
        decision == "allow"
        and automatic_execution
        and action == "resume_from_checkpoint"
    ):

        return {
            "executed": True,
            "action": action,
            "status": "prepared",
            "reason": (
                "Checkpoint recovery was safely prepared."
            ),
        }


    # --------------------------------------------------
    # UNKNOWN OR UNSAFE ACTION
    # --------------------------------------------------

    return {
        "executed": False,
        "action": action or "unknown",
        "status": "stopped",
        "reason": (
            "Recovery action is unknown or unsafe."
        ),
    }
