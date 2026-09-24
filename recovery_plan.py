from typing import Any, Dict


def build_recovery_plan(
    recovery_decision: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """
    Phase 19: Controlled Recovery Plan.

    Converts the final recovery decision into a controlled,
    non-destructive recovery plan.

    This layer does not execute the original task.
    It only defines the next safe recovery step.
    """

    if not isinstance(recovery_decision, dict):

        return {
            "plan_status": "blocked",
            "action": "stop_safely",
            "resume_type": None,
            "execution_allowed": False,
            "next_step": "stop",
            "reason": (
                "Recovery decision is invalid."
            ),
        }


    decision_status = str(
        recovery_decision.get(
            "decision_status",
            "",
        )
    ).strip().lower()


    action = str(
        recovery_decision.get(
            "action",
            "",
        )
    ).strip().lower()


    resume_allowed = bool(
        recovery_decision.get(
            "resume_allowed",
            False,
        )
    )


    # --------------------------------------------------
    # NO RECOVERY REQUIRED
    # --------------------------------------------------

    if (
        decision_status == "not_required"
        and action == "none"
        and not resume_allowed
    ):

        return {
            "plan_status": "not_required",
            "action": "none",
            "resume_type": None,
            "execution_allowed": False,
            "next_step": "none",
            "reason": (
                "No recovery plan is required."
            ),
        }


    # --------------------------------------------------
    # APPROVED EXECUTION RESUME
    # --------------------------------------------------

    if (
        decision_status == "approved"
        and action == "resume_execution"
        and resume_allowed
    ):

        return {
            "plan_status": "ready",
            "action": "resume_execution",
            "resume_type": "execution",
            "execution_allowed": True,
            "next_step": "controlled_resume",
            "reason": (
                "Execution recovery is approved "
                "for controlled continuation."
            ),
        }


    # --------------------------------------------------
    # APPROVED CHECKPOINT RESUME
    # --------------------------------------------------

    if (
        decision_status == "approved"
        and action == "resume_from_checkpoint"
        and resume_allowed
    ):

        return {
            "plan_status": "ready",
            "action": "resume_from_checkpoint",
            "resume_type": "checkpoint",
            "execution_allowed": True,
            "next_step": "controlled_resume",
            "reason": (
                "Checkpoint recovery is approved "
                "for controlled continuation."
            ),
        }


    # --------------------------------------------------
    # ANALYSIS STILL REQUIRED
    # --------------------------------------------------

    if (
        decision_status == "waiting"
        and action == "analyze_before_resume"
        and not resume_allowed
    ):

        return {
            "plan_status": "waiting",
            "action": "analyze_before_resume",
            "resume_type": None,
            "execution_allowed": False,
            "next_step": "analysis",
            "reason": (
                "Recovery analysis must complete "
                "before continuation."
            ),
        }


    # --------------------------------------------------
    # SAFETY STOP
    # --------------------------------------------------

    if (
        decision_status == "blocked"
        or action == "stop_safely"
    ):

        return {
            "plan_status": "blocked",
            "action": "stop_safely",
            "resume_type": None,
            "execution_allowed": False,
            "next_step": "stop",
            "reason": (
                "Recovery is blocked by the final "
                "recovery decision."
            ),
        }


    # --------------------------------------------------
    # UNKNOWN OR UNSAFE STATE
    # --------------------------------------------------

    return {
        "plan_status": "blocked",
        "action": "stop_safely",
        "resume_type": None,
        "execution_allowed": False,
        "next_step": "stop",
        "reason": (
            "Recovery decision state is unknown or unsafe."
        ),
    }
