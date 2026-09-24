from typing import Any, Dict


def execute_controlled_recovery(
    recovery_plan: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """
    Phase 20: Controlled Recovery Execution.

    Executes only the recovery preparation authorized
    by the recovery plan.

    This layer does not automatically re-run the original
    user request. It only prepares a controlled recovery
    continuation.
    """

    if not isinstance(recovery_plan, dict):

        return {
            "execution_status": "blocked",
            "action": "stop_safely",
            "executed": False,
            "reason": (
                "Recovery plan is invalid."
            ),
        }


    plan_status = str(
        recovery_plan.get(
            "plan_status",
            "",
        )
    ).strip().lower()


    action = str(
        recovery_plan.get(
            "action",
            "",
        )
    ).strip().lower()


    resume_type = recovery_plan.get(
        "resume_type"
    )


    execution_allowed = bool(
        recovery_plan.get(
            "execution_allowed",
            False,
        )
    )


    next_step = str(
        recovery_plan.get(
            "next_step",
            "",
        )
    ).strip().lower()


    # --------------------------------------------------
    # NO RECOVERY REQUIRED
    # --------------------------------------------------

    if (
        plan_status == "not_required"
        and action == "none"
    ):

        return {
            "execution_status": "not_required",
            "action": "none",
            "executed": False,
            "reason": (
                "No controlled recovery execution is required."
            ),
        }


    # --------------------------------------------------
    # WAITING FOR ANALYSIS
    # --------------------------------------------------

    if (
        plan_status == "waiting"
        or next_step == "analysis"
    ):

        return {
            "execution_status": "waiting",
            "action": "analyze_before_resume",
            "executed": False,
            "reason": (
                "Recovery analysis must complete before "
                "controlled execution."
            ),
        }


    # --------------------------------------------------
    # BLOCKED PLAN
    # --------------------------------------------------

    if (
        plan_status == "blocked"
        or next_step == "stop"
    ):

        return {
            "execution_status": "blocked",
            "action": "stop_safely",
            "executed": False,
            "reason": (
                "Controlled recovery execution was blocked "
                "by the recovery plan."
            ),
        }


    # --------------------------------------------------
    # SAFE EXECUTION RESUME
    # --------------------------------------------------

    if (
        plan_status == "ready"
        and action == "resume_execution"
        and resume_type == "execution"
        and execution_allowed
        and next_step == "controlled_resume"
    ):

        return {
            "execution_status": "prepared",
            "action": "resume_execution",
            "resume_type": "execution",
            "executed": True,
            "reason": (
                "Controlled execution recovery was prepared."
            ),
        }


    # --------------------------------------------------
    # SAFE CHECKPOINT RESUME
    # --------------------------------------------------

    if (
        plan_status == "ready"
        and action == "resume_from_checkpoint"
        and resume_type == "checkpoint"
        and execution_allowed
        and next_step == "controlled_resume"
    ):

        return {
            "execution_status": "prepared",
            "action": "resume_from_checkpoint",
            "resume_type": "checkpoint",
            "executed": True,
            "reason": (
                "Controlled checkpoint recovery was prepared."
            ),
        }


    # --------------------------------------------------
    # UNKNOWN OR UNSAFE PLAN
    # --------------------------------------------------

    return {
        "execution_status": "blocked",
        "action": "stop_safely",
        "executed": False,
        "reason": (
            "Recovery plan is unknown or unsafe."
        ),
    }
