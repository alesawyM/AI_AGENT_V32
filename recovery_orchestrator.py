from typing import Any, Dict


def orchestrate_recovery(
    execution_resume: Dict[str, Any] | None,
    checkpoint_recovery: Dict[str, Any] | None,
    execution_recovery: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """
    Phase 13: Safe Recovery Orchestration.

    Combines recovery decisions from the execution resume,
    checkpoint recovery, and execution recovery systems.

    This function only determines the safest next action.
    It does not automatically execute or resume work.
    """

    execution_resume = (
        execution_resume
        if isinstance(execution_resume, dict)
        else {}
    )

    checkpoint_recovery = (
        checkpoint_recovery
        if isinstance(checkpoint_recovery, dict)
        else {}
    )

    execution_recovery = (
        execution_recovery
        if isinstance(execution_recovery, dict)
        else {}
    )


    # --------------------------------------------------
    # HARD SAFETY STOPS
    # --------------------------------------------------

    checkpoint_action = str(
        checkpoint_recovery.get(
            "action",
            ""
        )
    ).strip().lower()

    execution_action = str(
        execution_recovery.get(
            "strategy",
            ""
        )
    ).strip().lower()


    if checkpoint_action == "stop_safely":

        return {
            "action": "stop_safely",
            "recovery_required": False,
            "safe_to_resume": False,
            "reason": (
                checkpoint_recovery.get(
                    "reason",
                    "Checkpoint requires a safe stop."
                )
            ),
        }


    if execution_action in {
        "wait_for_approval",
        "stop_safely",
    }:

        return {
            "action": execution_action,
            "recovery_required": False,
            "safe_to_resume": False,
            "reason": (
                execution_recovery.get(
                    "reason",
                    "Execution recovery requires no continuation."
                )
            ),
        }


    # --------------------------------------------------
    # CHECKPOINT RECOVERY
    # --------------------------------------------------

    if (
        checkpoint_recovery.get(
            "recovery_required"
        )
        and checkpoint_recovery.get(
            "safe_to_resume"
        )
    ):

        return {
            "action": "resume_from_checkpoint",
            "recovery_required": True,
            "safe_to_resume": True,
            "reason": checkpoint_recovery.get(
                "reason",
                "Checkpoint can be resumed safely."
            ),
        }


    # --------------------------------------------------
    # EXECUTION RESUME
    # --------------------------------------------------

    if (
        execution_resume.get(
            "resume_required"
        )
        and execution_resume.get(
            "safe_to_resume"
        )
    ):

        return {
            "action": "resume_execution",
            "recovery_required": True,
            "safe_to_resume": True,
            "reason": execution_resume.get(
                "reason",
                "Previous execution can be resumed safely."
            ),
        }


    # --------------------------------------------------
    # ANALYSIS REQUIRED
    # --------------------------------------------------

    if (
        checkpoint_recovery.get(
            "recovery_required"
        )
        or execution_recovery.get(
            "recovery_required"
        )
    ):

        return {
            "action": "analyze_before_resume",
            "recovery_required": True,
            "safe_to_resume": False,
            "reason": (
                "Recovery requires additional analysis "
                "before continuation."
            ),
        }


    # --------------------------------------------------
    # NO RECOVERY REQUIRED
    # --------------------------------------------------

    return {
        "action": "none",
        "recovery_required": False,
        "safe_to_resume": False,
        "reason": (
            "No recovery action is required."
        ),
    }
