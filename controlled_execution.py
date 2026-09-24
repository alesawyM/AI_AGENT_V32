"""
Phase 8: Controlled Autonomous Execution.

This module controls the next execution step safely.

It does not execute tools directly.
It does not modify Agent state.
It determines whether execution may continue,
whether replanning is allowed, or whether the
Agent must stop safely.
"""

from typing import Any, Dict


MAX_EXECUTION_CYCLES = 3
MAX_REPLANNING_ATTEMPTS = 2


def control_execution(
    autonomous_loop: Dict[str, Any],
    execution_history: list | None = None,
) -> Dict[str, Any]:

    autonomous_loop = (
        autonomous_loop
        if isinstance(autonomous_loop, dict)
        else {}
    )

    execution_history = (
        execution_history
        if isinstance(execution_history, list)
        else []
    )

    next_action = str(
        autonomous_loop.get(
            "next_action",
            "stop_and_review",
        )
    ).strip().lower()

    execution_cycles = len(execution_history)

    replanning_attempts = sum(
        1
        for item in execution_history
        if isinstance(item, dict)
        and item.get("action")
        == "prepare_alternative_plan"
    )


    # -------------------------------------------------
    # 1. Approval is always a hard stop.
    # -------------------------------------------------

    if next_action == "wait_for_approval":

        return {
            "action": "wait_for_approval",
            "continue_execution": False,
            "safe_stop": True,
            "reason": (
                "Execution requires explicit user approval."
            ),
            "execution_cycles": execution_cycles,
            "replanning_attempts": replanning_attempts,
        }


    # -------------------------------------------------
    # 2. Maximum execution cycles.
    # -------------------------------------------------

    if execution_cycles >= MAX_EXECUTION_CYCLES:

        return {
            "action": "stop_and_review",
            "continue_execution": False,
            "safe_stop": True,
            "reason": (
                "Maximum execution cycle limit reached."
            ),
            "execution_cycles": execution_cycles,
            "replanning_attempts": replanning_attempts,
        }


    # -------------------------------------------------
    # 3. Controlled replanning.
    # -------------------------------------------------

    if next_action == "prepare_alternative_plan":

        if (
            replanning_attempts
            >= MAX_REPLANNING_ATTEMPTS
        ):

            return {
                "action": "stop_and_review",
                "continue_execution": False,
                "safe_stop": True,
                "reason": (
                    "Maximum replanning attempt limit reached."
                ),
                "execution_cycles": execution_cycles,
                "replanning_attempts": replanning_attempts,
            }

        return {
            "action": "prepare_alternative_plan",
            "continue_execution": True,
            "safe_stop": False,
            "reason": (
                "Execution may continue with a controlled "
                "alternative plan."
            ),
            "execution_cycles": execution_cycles,
            "replanning_attempts": replanning_attempts,
        }


    # -------------------------------------------------
    # 4. Normal continuation.
    # -------------------------------------------------

    if next_action == "continue":

        return {
            "action": "continue",
            "continue_execution": True,
            "safe_stop": False,
            "reason": (
                "Execution may continue normally."
            ),
            "execution_cycles": execution_cycles,
            "replanning_attempts": replanning_attempts,
        }


    # -------------------------------------------------
    # 5. Unknown state.
    # -------------------------------------------------

    return {
        "action": "stop_and_review",
        "continue_execution": False,
        "safe_stop": True,
        "reason": (
            "Unknown execution state. Stopping safely."
        ),
        "execution_cycles": execution_cycles,
        "replanning_attempts": replanning_attempts,
    }
