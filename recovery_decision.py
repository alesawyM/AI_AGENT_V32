from typing import Any, Dict


def decide_recovery(
    recovery_review: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """
    Phase 18: Recovery Decision.

    Converts the recovery review result into the final
    controlled recovery decision.

    This layer does not execute the original task.
    It only determines whether recovery may proceed,
    requires further work, or must stop safely.
    """

    if not isinstance(recovery_review, dict):

        return {
            "decision_status": "blocked",
            "action": "stop_safely",
            "resume_allowed": False,
            "reason": (
                "Recovery review result is invalid."
            ),
        }


    review_status = str(
        recovery_review.get(
            "review_status",
            "",
        )
    ).strip().lower()


    decision = str(
        recovery_review.get(
            "decision",
            "",
        )
    ).strip().lower()


    safe_to_resume = bool(
        recovery_review.get(
            "safe_to_resume",
            False,
        )
    )


    # --------------------------------------------------
    # NO RECOVERY REQUIRED
    # --------------------------------------------------

    if (
        review_status == "not_required"
        and decision == "none"
    ):

        return {
            "decision_status": "not_required",
            "action": "none",
            "resume_allowed": False,
            "reason": (
                "No recovery decision is required."
            ),
        }


    # --------------------------------------------------
    # SAFE EXECUTION RESUME
    # --------------------------------------------------

    if (
        review_status == "approved_for_review"
        and decision == "review_execution_resume"
        and safe_to_resume
    ):

        return {
            "decision_status": "approved",
            "action": "resume_execution",
            "resume_allowed": True,
            "reason": (
                "Execution recovery passed controlled review."
            ),
        }


    # --------------------------------------------------
    # SAFE CHECKPOINT RESUME
    # --------------------------------------------------

    if (
        review_status == "approved_for_review"
        and decision == "review_checkpoint_resume"
        and safe_to_resume
    ):

        return {
            "decision_status": "approved",
            "action": "resume_from_checkpoint",
            "resume_allowed": True,
            "reason": (
                "Checkpoint recovery passed controlled review."
            ),
        }


    # --------------------------------------------------
    # ANALYSIS STILL REQUIRED
    # --------------------------------------------------

    if decision == "analyze_before_resume":

        return {
            "decision_status": "waiting",
            "action": "analyze_before_resume",
            "resume_allowed": False,
            "reason": (
                "Recovery analysis must complete before "
                "a resume decision can be made."
            ),
        }


    # --------------------------------------------------
    # SAFETY STOP
    # --------------------------------------------------

    if decision == "stop_safely":

        return {
            "decision_status": "blocked",
            "action": "stop_safely",
            "resume_allowed": False,
            "reason": (
                "Recovery was blocked by the recovery review."
            ),
        }


    # --------------------------------------------------
    # UNKNOWN OR UNSAFE STATE
    # --------------------------------------------------

    return {
        "decision_status": "blocked",
        "action": "stop_safely",
        "resume_allowed": False,
        "reason": (
            "Recovery review state is unknown or unsafe."
        ),
    }
