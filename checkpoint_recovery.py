from typing import Any, Dict


def determine_checkpoint_recovery(
    checkpoint: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """
    Phase 12: Checkpoint Recovery Decision.

    Determines the safest action when an execution checkpoint
    is found after interruption or restart.

    This function only decides what should happen.
    It does not execute or resume anything.
    """

    if not isinstance(checkpoint, dict):
        return {
            "recovery_required": False,
            "action": "none",
            "reason": "No active checkpoint found.",
            "safe_to_resume": False,
        }

    if not checkpoint.get("active"):
        return {
            "recovery_required": False,
            "action": "none",
            "reason": "Checkpoint is not active.",
            "safe_to_resume": False,
        }

    stage = str(
        checkpoint.get("stage", "")
    ).strip().lower()

    request = checkpoint.get("request")

    if not request:
        return {
            "recovery_required": False,
            "action": "stop_safely",
            "reason": "Active checkpoint has no request.",
            "safe_to_resume": False,
        }

    # Safe early stages.
    if stage in {
        "started",
        "reviewed",
        "planning",
    }:
        return {
            "recovery_required": True,
            "action": "resume_from_checkpoint",
            "reason": (
                "Execution was interrupted during a recoverable stage."
            ),
            "safe_to_resume": True,
        }

    # Execution was already in progress.
    if stage in {
        "executing",
        "replanning",
    }:
        return {
            "recovery_required": True,
            "action": "analyze_before_resume",
            "reason": (
                "Execution was interrupted during an active stage."
            ),
            "safe_to_resume": False,
        }

    # Safety-related stages.
    if stage in {
        "approval_required",
        "stopped",
    }:
        return {
            "recovery_required": False,
            "action": "stop_safely",
            "reason": (
                "Checkpoint requires no automatic continuation."
            ),
            "safe_to_resume": False,
        }

    return {
        "recovery_required": False,
        "action": "stop_safely",
        "reason": "Checkpoint stage is unknown.",
        "safe_to_resume": False,
    }
