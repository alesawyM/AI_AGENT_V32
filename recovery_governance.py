from typing import Any, Dict


def govern_recovery_action(
    recovery_orchestration: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """
    Phase 14: Recovery Action Governance.

    Determines whether a recovery action is allowed,
    requires analysis, requires approval, or must be blocked.

    This function does not execute recovery actions.
    """

    recovery_orchestration = (
        recovery_orchestration
        if isinstance(recovery_orchestration, dict)
        else {}
    )


    action = str(
        recovery_orchestration.get(
            "action",
            ""
        )
    ).strip().lower()


    recovery_required = bool(
        recovery_orchestration.get(
            "recovery_required",
            False
        )
    )


    safe_to_resume = bool(
        recovery_orchestration.get(
            "safe_to_resume",
            False
        )
    )


    # --------------------------------------------------
    # NO ACTION
    # --------------------------------------------------

    if action in {
        "",
        "none",
    }:

        return {
            "decision": "allow",
            "action": "none",
            "automatic_execution": False,
            "reason": (
                "No recovery action is required."
            ),
        }


    # --------------------------------------------------
    # APPROVAL
    # --------------------------------------------------

    if action == "wait_for_approval":

        return {
            "decision": "wait_for_approval",
            "action": action,
            "automatic_execution": False,
            "reason": (
                "Recovery cannot continue without "
                "explicit user approval."
            ),
        }


    # --------------------------------------------------
    # HARD STOP
    # --------------------------------------------------

    if action == "stop_safely":

        return {
            "decision": "block",
            "action": action,
            "automatic_execution": False,
            "reason": (
                "Recovery action is blocked by a "
                "safety stop."
            ),
        }


    # --------------------------------------------------
    # ANALYSIS REQUIRED
    # --------------------------------------------------

    if action == "analyze_before_resume":

        return {
            "decision": "analyze",
            "action": action,
            "automatic_execution": False,
            "reason": (
                "Recovery requires additional analysis "
                "before continuation."
            ),
        }


    # --------------------------------------------------
    # SAFE RESUME
    # --------------------------------------------------

    if (
        action in {
            "resume_execution",
            "resume_from_checkpoint",
        }
        and recovery_required
        and safe_to_resume
    ):

        return {
            "decision": "allow",
            "action": action,
            "automatic_execution": False,
            "reason": (
                "Recovery action is eligible for "
                "safe continuation."
            ),
        }


    # --------------------------------------------------
    # UNKNOWN OR UNSAFE ACTION
    # --------------------------------------------------

    return {
        "decision": "block",
        "action": action or "unknown",
        "automatic_execution": False,
        "reason": (
            "Recovery action is unknown or unsafe."
        ),
    }
