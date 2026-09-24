from typing import Any, Dict


def determine_recovery_strategy(
    execution_review: Dict[str, Any],
    replanning: Dict[str, Any],
    autonomous_loop: Dict[str, Any],
    controlled_execution: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Phase 9: Intelligent Execution Recovery.

    Determines the safest recovery strategy after execution.
    This function does not execute anything. It only decides
    what the next recovery action should be.
    """

    execution_review = (
        execution_review
        if isinstance(execution_review, dict)
        else {}
    )

    replanning = (
        replanning
        if isinstance(replanning, dict)
        else {}
    )

    autonomous_loop = (
        autonomous_loop
        if isinstance(autonomous_loop, dict)
        else {}
    )

    controlled_execution = (
        controlled_execution
        if isinstance(controlled_execution, dict)
        else {}
    )


    execution_status = str(
        execution_review.get(
            "execution_status",
            ""
        )
    ).strip().lower()


    review_status = str(
        execution_review.get(
            "review_status",
            ""
        )
    ).strip().lower()


    replanning_required = bool(
        replanning.get(
            "replanning_required",
            False
        )
    )


    controlled_action = str(
        controlled_execution.get(
            "action",
            ""
        )
    ).strip().lower()


    # --------------------------------------------------
    # APPROVAL
    # --------------------------------------------------

    if execution_status == "approval_required":

        return {
            "recovery_required": False,
            "strategy": "wait_for_approval",
            "reason": (
                "Execution is waiting for explicit user approval."
            ),
            "safe_to_continue": False,
        }


    # --------------------------------------------------
    # SUCCESS
    # --------------------------------------------------

    if (
        execution_status == "completed"
        and not replanning_required
    ):

        return {
            "recovery_required": False,
            "strategy": "continue",
            "reason": (
                "Execution completed successfully."
            ),
            "safe_to_continue": True,
        }


    # --------------------------------------------------
    # CONTROLLED STOP
    # --------------------------------------------------

    if controlled_action in (
        "stop",
        "halt",
        "approval_required",
    ):

        return {
            "recovery_required": False,
            "strategy": "stop_safely",
            "reason": (
                "Controlled execution stopped further action."
            ),
            "safe_to_continue": False,
        }


    # --------------------------------------------------
    # REPLANNING
    # --------------------------------------------------

    if replanning_required:

        return {
            "recovery_required": True,
            "strategy": "prepare_recovery_plan",
            "reason": (
                "Execution requires replanning before continuing."
            ),
            "safe_to_continue": False,
        }


    # --------------------------------------------------
    # ATTENTION REQUIRED
    # --------------------------------------------------

    if review_status == "needs_attention":

        return {
            "recovery_required": True,
            "strategy": "analyze_failure",
            "reason": (
                "Execution requires additional analysis."
            ),
            "safe_to_continue": False,
        }


    # --------------------------------------------------
    # UNKNOWN STATE
    # --------------------------------------------------

    return {
        "recovery_required": False,
        "strategy": "stop_safely",
        "reason": (
            "Execution state is unknown."
        ),
        "safe_to_continue": False,
    }
