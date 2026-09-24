from typing import Any, Dict


def analyze_recovery(
    execution_resume: Dict[str, Any] | None,
    checkpoint_recovery: Dict[str, Any] | None,
    recovery_orchestration: Dict[str, Any] | None,
    recovery_governance: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """
    Phase 16: Recovery Analysis.

    Analyzes a recovery situation before any execution
    continuation is considered.

    This layer does not execute or resume the original task.
    It only determines whether the recovery state can be
    safely analyzed and what the next controlled action is.
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

    recovery_orchestration = (
        recovery_orchestration
        if isinstance(recovery_orchestration, dict)
        else {}
    )

    recovery_governance = (
        recovery_governance
        if isinstance(recovery_governance, dict)
        else {}
    )

    action = str(
        recovery_orchestration.get(
            "action",
            ""
        )
    ).strip().lower()

    governance_decision = str(
        recovery_governance.get(
            "decision",
            ""
        )
    ).strip().lower()

    # --------------------------------------------------
    # NO RECOVERY REQUIRED
    # --------------------------------------------------

    if action in {
        "",
        "none",
    }:

        return {
            "analysis_required": False,
            "analysis_status": "not_required",
            "next_action": "none",
            "safe_for_resume_review": False,
            "reason": (
                "No recovery analysis is required."
            ),
        }

    # --------------------------------------------------
    # APPROVAL IS A HARD STOP
    # --------------------------------------------------

    if action == "wait_for_approval":

        return {
            "analysis_required": False,
            "analysis_status": "blocked",
            "next_action": "wait_for_approval",
            "safe_for_resume_review": False,
            "reason": (
                "Recovery cannot continue without "
                "explicit user approval."
            ),
        }

    # --------------------------------------------------
    # SAFETY STOP
    # --------------------------------------------------

    if (
        action == "stop_safely"
        or governance_decision == "block"
    ):

        return {
            "analysis_required": False,
            "analysis_status": "blocked",
            "next_action": "stop_safely",
            "safe_for_resume_review": False,
            "reason": (
                "Recovery analysis was blocked by "
                "the safety controls."
            ),
        }

    # --------------------------------------------------
    # ANALYSIS REQUIRED
    # --------------------------------------------------

    if (
        action == "analyze_before_resume"
        or governance_decision == "analyze"
    ):

        execution = execution_resume.get(
            "execution"
        )

        request = execution_resume.get(
            "request"
        )

        if not isinstance(execution, dict):

            return {
                "analysis_required": False,
                "analysis_status": "blocked",
                "next_action": "stop_safely",
                "safe_for_resume_review": False,
                "reason": (
                    "Recovery analysis requires a "
                    "valid previous execution."
                ),
            }

        if not request:

            request = execution.get("request")

        if not request:

            return {
                "analysis_required": False,
                "analysis_status": "blocked",
                "next_action": "stop_safely",
                "safe_for_resume_review": False,
                "reason": (
                    "Previous execution has no request "
                    "to analyze."
                ),
            }

        return {
            "analysis_required": True,
            "analysis_status": "ready",
            "next_action": "analyze_previous_execution",
            "safe_for_resume_review": True,
            "reason": (
                "Previous execution is available for "
                "controlled recovery analysis."
            ),
            "request": request,
            "execution": execution,
        }

    # --------------------------------------------------
    # SAFE EXECUTION RESUME CANDIDATE
    # --------------------------------------------------

    if (
        action == "resume_execution"
        and governance_decision == "allow"
    ):

        return {
            "analysis_required": True,
            "analysis_status": "ready",
            "next_action": "review_execution_resume",
            "safe_for_resume_review": True,
            "reason": (
                "Execution recovery requires controlled "
                "resume review before continuation."
            ),
        }


    # --------------------------------------------------
    # SAFE CHECKPOINT RESUME CANDIDATE
    # --------------------------------------------------

    if (
        action == "resume_from_checkpoint"
        and governance_decision == "allow"
    ):

        return {
            "analysis_required": True,
            "analysis_status": "ready",
            "next_action": "review_checkpoint_resume",
            "safe_for_resume_review": True,
            "reason": (
                "Checkpoint recovery requires controlled "
                "resume review before continuation."
            ),
        }

    # --------------------------------------------------
    # UNKNOWN STATE
    # --------------------------------------------------

    return {
        "analysis_required": False,
        "analysis_status": "blocked",
        "next_action": "stop_safely",
        "safe_for_resume_review": False,
        "reason": (
            "Recovery state is unknown or unsafe."
        ),
    }
