from typing import Any, Dict


def review_recovery(
    recovery_analysis: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """
    Phase 17: Recovery Review.

    Reviews the recovery analysis result and determines
    whether recovery may proceed, requires approval,
    or must stop safely.

    This function does not execute the original task.
    """


    if not isinstance(recovery_analysis, dict):

        return {
            "review_status": "blocked",
            "decision": "stop_safely",
            "safe_to_resume": False,
            "reason": (
                "Recovery analysis result is invalid."
            ),
        }


    analysis_required = bool(
        recovery_analysis.get(
            "analysis_required",
            False,
        )
    )


    analysis_status = str(
        recovery_analysis.get(
            "analysis_status",
            "",
        )
    ).strip().lower()


    next_action = str(
        recovery_analysis.get(
            "next_action",
            "",
        )
    ).strip().lower()


    safe_for_resume_review = bool(
        recovery_analysis.get(
            "safe_for_resume_review",
            False,
        )
    )


    # --------------------------------------------------
    # NO RECOVERY REQUIRED
    # --------------------------------------------------

    if (
        not analysis_required
        and analysis_status == "not_required"
        and next_action == "none"
    ):

        return {
            "review_status": "not_required",
            "decision": "none",
            "safe_to_resume": False,
            "reason": (
                "No recovery review is required."
            ),
        }


    # --------------------------------------------------
    # BLOCKED OR UNSAFE ANALYSIS
    # --------------------------------------------------

    if analysis_status == "blocked":

        return {
            "review_status": "blocked",
            "decision": "stop_safely",
            "safe_to_resume": False,
            "reason": (
                "Recovery analysis identified an unsafe state."
            ),
        }


    # --------------------------------------------------
    # WAITING FOR ANALYSIS
    # --------------------------------------------------

    if analysis_status in {
        "waiting",
        "pending",
    }:

        return {
            "review_status": "waiting",
            "decision": "analyze_before_resume",
            "safe_to_resume": False,
            "reason": (
                "Recovery analysis is not complete."
            ),
        }


    # --------------------------------------------------
    # SAFE REVIEW REQUIRED
    # --------------------------------------------------

    if (
        analysis_required
        and analysis_status == "ready"
        and safe_for_resume_review
    ):

        if next_action in {
            "review_execution_resume",
            "review_checkpoint_resume",
        }:

            return {
                "review_status": "approved_for_review",
                "decision": next_action,
                "safe_to_resume": True,
                "reason": (
                    "Recovery is ready for controlled "
                    "resume review."
                ),
            }


    # --------------------------------------------------
    # UNKNOWN OR UNSAFE STATE
    # --------------------------------------------------

    return {
        "review_status": "blocked",
        "decision": "stop_safely",
        "safe_to_resume": False,
        "reason": (
            "Recovery analysis state is unknown or unsafe."
        ),
    }
