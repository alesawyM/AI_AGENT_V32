"""
Phase 7: Autonomous Execution Loop.

This module converts Executive decisions, execution reviews and
replanning decisions into one explicit next-step decision.

It does not execute tools.
It does not modify Agent state.
It only determines what the Agent should do next.
"""

from typing import Any, Dict


def determine_next_action(
    executive_decision: Dict[str, Any],
    execution_review: Dict[str, Any],
    replanning: Dict[str, Any],
) -> Dict[str, Any]:

    executive_decision = (
        executive_decision
        if isinstance(executive_decision, dict)
        else {}
    )

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


    # -------------------------------------------------
    # 1. Approval always stops autonomous continuation.
    # -------------------------------------------------

    approval_required = bool(
        executive_decision.get("approval_required")
    )

    execution_status = str(
        execution_review.get(
            "execution_status",
            "",
        )
    ).strip().lower()

    if (
        approval_required
        or execution_status == "approval_required"
    ):

        return {
            "next_action": "wait_for_approval",
            "continue_execution": False,
            "replanning_required": False,
            "autonomous_execution": False,
            "reason": (
                "The Agent must wait for explicit user approval."
            ),
        }


    # -------------------------------------------------
    # 2. Failed execution may require replanning.
    # -------------------------------------------------

    replanning_required = bool(
        replanning.get("replanning_required")
    )

    if replanning_required:

        return {
            "next_action": "prepare_alternative_plan",
            "continue_execution": False,
            "replanning_required": True,
            "autonomous_execution": False,
            "reason": str(
                replanning.get(
                    "reason",
                    "Execution requires replanning.",
                )
            ),
        }


    # -------------------------------------------------
    # 3. Successful execution.
    # -------------------------------------------------

    completed = bool(
        execution_review.get("completed")
    )

    has_errors = bool(
        execution_review.get("has_errors")
    )

    if completed and not has_errors:

        return {
            "next_action": "continue",
            "continue_execution": True,
            "replanning_required": False,
            "autonomous_execution": True,
            "reason": (
                "Execution completed successfully."
            ),
        }


    # -------------------------------------------------
    # 4. Unknown / incomplete state.
    # -------------------------------------------------

    return {
        "next_action": "stop_and_review",
        "continue_execution": False,
        "replanning_required": False,
        "autonomous_execution": False,
        "reason": (
            "Execution state is incomplete and requires review."
        ),
    }
