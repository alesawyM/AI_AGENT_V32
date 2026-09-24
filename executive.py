from typing import Any, Dict, List


DIRECT_PATTERNS = (
    "اعرض",
    "المهام",
    "المشروع الحالي",
    "ما هو المشروع الحالي",
    "ماهو المشروع الحالي",
    "current project",
    "tasks",
)


def build_executive_context(
    request: str,
    current_project: Any = None,
    tasks: Any = None,
    memory_context: Any = None,
    agent_state: Any = None,
) -> Dict[str, Any]:
    """Build a read-only context for Executive Intelligence."""

    task_list = tasks if isinstance(tasks, list) else []

    open_tasks = [
        task for task in task_list
        if isinstance(task, dict)
        and str(task.get("status", "")).lower()
        not in ("completed", "complete", "done")
    ]

    return {
        "request": str(request or "").strip(),
        "current_project": (
            current_project if isinstance(current_project, dict) else None
        ),
        "tasks": {
            "total": len(task_list),
            "open": len(open_tasks),
        },
        "memory_context": (
            memory_context if isinstance(memory_context, list) else []
        ),
        "agent_state": (
            agent_state if isinstance(agent_state, dict) else {}
        ),
    }


def build_decision_intelligence(
    request: str,
    context: Dict[str, Any],
    *,
    is_goal_oriented: bool,
    priority: str,
    risk_level: str,
    approval_required: bool,
) -> Dict[str, Any]:
    """
    Decision Intelligence v1.

    Produces a clear recommendation, reasons, alternatives,
    and determines whether the Agent should challenge the request.
    This function is read-only and does not execute actions.
    """

    text = str(request or "").strip()
    current_project = context.get("current_project")
    task_info = context.get("tasks", {})

    open_tasks = (
        task_info.get("open", 0)
        if isinstance(task_info, dict)
        else 0
    )

    recommendation = ""
    recommendation_reason = ""
    alternatives: List[str] = []
    should_challenge = False
    challenge_reason = ""

    # Highest priority: safety and approval.
    if approval_required:
        recommendation = "Do not execute until explicit approval is received."
        recommendation_reason = (
            "The requested action is classified as high risk."
        )
        alternatives = [
            "Ask for explicit approval.",
            "Review the exact scope before execution.",
            "Prefer a reversible or non-destructive alternative.",
        ]

        should_challenge = True
        challenge_reason = (
            "The requested action may cause destructive or irreversible changes."
        )

    # Goal with active work context.
    elif is_goal_oriented and current_project:
        recommendation = (
            "Proceed with planning using the active project context."
        )
        recommendation_reason = (
            "An active project exists and can provide relevant execution context."
        )

        alternatives = [
            "Continue with the active project.",
            "Create a separate project if the new goal is unrelated.",
        ]

    # Goal while unfinished work exists.
    elif is_goal_oriented and open_tasks > 0:
        recommendation = (
            "Proceed with the goal, but review existing open tasks first."
        )
        recommendation_reason = (
            "There are unfinished tasks that may affect priority or execution."
        )

        alternatives = [
            "Continue with the new goal.",
            "Review and prioritize open tasks first.",
        ]

    # High priority request.
    elif priority == "high":
        recommendation = "Prioritize this request for immediate handling."
        recommendation_reason = (
            "The request contains high-priority indicators."
        )

        alternatives = [
            "Handle immediately.",
            "Confirm urgency if it conflicts with a higher-priority task.",
        ]

    # Normal goal.
    elif is_goal_oriented:
        recommendation = (
            "Create and execute a plan using the existing Agent workflow."
        )
        recommendation_reason = (
            "The request is goal-oriented and benefits from multi-step planning."
        )

        alternatives = [
            "Execute the generated plan.",
            "Ask for clarification if the goal is ambiguous.",
        ]

    # Direct request.
    else:
        recommendation = (
            "Handle the request directly through the existing command system."
        )
        recommendation_reason = (
            "The request does not require multi-step planning."
        )

        alternatives = [
            "Execute directly.",
        ]

    return {
        "recommendation": recommendation,
        "recommendation_reason": recommendation_reason,
        "alternatives": alternatives,
        "should_challenge": should_challenge,
        "challenge_reason": challenge_reason,
    }


def analyze_request(
    request: str,
    context: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Executive Intelligence v3.

    Analyzes the request together with read-only Agent context.
    This layer does not execute tools or modify data.
    """

    text = str(request or "").strip()
    normalized = text.lower()

    context = context if isinstance(context, dict) else {}

    is_goal_oriented = (
        len(text.split()) >= 4
        and not any(pattern in normalized for pattern in DIRECT_PATTERNS)
    )

    request_type = "goal" if is_goal_oriented else "direct"
    should_plan = is_goal_oriented

    risk_level = "low"
    approval_required = False
    autonomy_level = "direct"

    destructive_patterns = (
        "delete",
        "remove",
        "erase",
        "حذف",
        "امسح",
        "أمسح",
    )

    if any(pattern in normalized for pattern in destructive_patterns):
        risk_level = "high"
        approval_required = True
        autonomy_level = "approval_required"

    elif is_goal_oriented:
        autonomy_level = "autonomous"

    priority = "normal"

    priority_patterns = (
        "urgent",
        "critical",
        "عاجل",
        "ضروري",
        "مهم جدًا",
    )

    if any(pattern in normalized for pattern in priority_patterns):
        priority = "high"

    current_project = context.get("current_project")
    task_info = context.get("tasks", {})

    decision_factors: List[str] = []

    if current_project:
        decision_factors.append("active_project")

    if isinstance(task_info, dict) and task_info.get("open", 0) > 0:
        decision_factors.append("open_tasks")

    if is_goal_oriented:
        decision_factors.append("goal_oriented")

    if risk_level == "high":
        decision_factors.append("high_risk")

    if priority == "high":
        decision_factors.append("high_priority")

    if approval_required:
        recommended_action = (
            "Do not execute yet. Request explicit user approval first."
        )

    elif is_goal_oriented and current_project:
        recommended_action = (
            "Use the existing planning system and consider the active project context."
        )

    elif is_goal_oriented:
        recommended_action = (
            "Use the existing planning and execution system."
        )

    else:
        recommended_action = (
            "Route the request to the existing direct command system."
        )

    decision_intelligence = build_decision_intelligence(
        request=text,
        context=context,
        is_goal_oriented=is_goal_oriented,
        priority=priority,
        risk_level=risk_level,
        approval_required=approval_required,
    )

    return {
        "goal": text,
        "request_type": request_type,
        "is_goal_oriented": is_goal_oriented,
        "priority": priority,
        "risk_level": risk_level,
        "autonomy_level": autonomy_level,
        "approval_required": approval_required,
        "recommended_action": recommended_action,
        "decision_intelligence": decision_intelligence,
        "recommendation": decision_intelligence["recommendation"],
        "recommendation_reason": decision_intelligence[
            "recommendation_reason"
        ],
        "alternatives": decision_intelligence["alternatives"],
        "should_challenge": decision_intelligence["should_challenge"],
        "challenge_reason": decision_intelligence["challenge_reason"],
        "decision_factors": decision_factors,
        "context_summary": {
            "has_current_project": bool(current_project),
            "open_tasks": (
                task_info.get("open", 0)
                if isinstance(task_info, dict)
                else 0
            ),
            "memory_items": len(context.get("memory_context", [])),
        },
        "should_plan": should_plan,
        "should_execute": not approval_required,
    }

def review_execution(
    request: str,
    decision: Dict[str, Any],
    result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Phase 6: Executive Execution Review v1.

    Reviews the outcome after the existing Agent Core finishes.
    This function does not execute tools or modify state.
    It only produces an Executive assessment.
    """

    result = result if isinstance(result, dict) else {}

    status = str(result.get("status", "")).strip().lower()

    errors = result.get("errors", [])
    if not isinstance(errors, list):
        errors = [errors] if errors else []

    workflow = str(result.get("workflow", "")).strip()

    completed = status == "completed"
    has_errors = len(errors) > 0

    needs_replanning = False
    review_status = "completed"

    if not completed:
        review_status = "needs_attention"

    if has_errors:
        review_status = "needs_attention"
        needs_replanning = True

    if status in (
        "failed",
        "error",
        "interrupted",
        "partial",
    ):
        needs_replanning = True

    if status == "approval_required":
        review_status = "waiting_for_approval"

    if completed and not has_errors:
        assessment = (
            "Execution completed successfully."
        )
        recommendation = (
            "Continue with the next objective."
        )
    elif status == "approval_required":
        assessment = (
            "Execution is waiting for user approval."
        )
        recommendation = (
            "Wait for explicit approval before proceeding."
        )
    elif has_errors:
        assessment = (
            "Execution completed with errors or unresolved issues."
        )
        recommendation = (
            "Analyze the failure and prepare an alternative plan."
        )
    else:
        assessment = (
            "Execution did not complete successfully."
        )
        recommendation = (
            "Review the result and determine whether replanning is required."
        )

    return {
        "request": str(request or "").strip(),
        "workflow": workflow,
        "execution_status": status,
        "review_status": review_status,
        "completed": completed,
        "has_errors": has_errors,
        "error_count": len(errors),
        "needs_replanning": needs_replanning,
        "assessment": assessment,
        "recommendation": recommendation,
        "decision_type": (
            decision.get("request_type")
            if isinstance(decision, dict)
            else None
        ),
    }


def build_replanning_policy(
    decision: Dict[str, Any],
    execution_review: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Phase 6: Replanning Policy v1.

    Converts the execution review into a safe replanning decision.
    This version does not automatically re-execute the Agent Core.
    """

    review = (
        execution_review
        if isinstance(execution_review, dict)
        else {}
    )

    needs_replanning = bool(
        review.get("needs_replanning")
    )

    approval_required = bool(
        decision.get("approval_required")
        if isinstance(decision, dict)
        else False
    )

    if approval_required:
        return {
            "replanning_required": False,
            "action": "wait_for_approval",
            "reason": (
                "Execution cannot continue until user approval is provided."
            ),
            "automatic_replanning": False,
        }

    if needs_replanning:
        return {
            "replanning_required": True,
            "action": "prepare_alternative_plan",
            "reason": (
                "Execution did not complete successfully and requires "
                "an alternative plan."
            ),
            "automatic_replanning": False,
        }

    return {
        "replanning_required": False,
        "action": "continue",
        "reason": (
            "Execution completed without requiring replanning."
        ),
        "automatic_replanning": False,
    }

def decide_replanning(
    execution_review: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Phase 6: Executive Replanning Decision.

    Determines whether the Agent should replan after execution.
    This function does not automatically execute a new plan.
    """

    review = (
        execution_review
        if isinstance(execution_review, dict)
        else {}
    )

    review_status = str(
        review.get("review_status", "")
    ).strip().lower()

    needs_replanning = bool(
        review.get("needs_replanning")
    )

    execution_status = str(
        review.get("execution_status", "")
    ).strip().lower()

    if execution_status == "approval_required":
        return {
            "replanning_required": False,
            "action": "wait_for_approval",
            "reason": (
                "Execution is waiting for user approval."
            ),
            "automatic_replanning": False,
        }

    if needs_replanning:
        return {
            "replanning_required": True,
            "action": "prepare_alternative_plan",
            "reason": (
                "Execution did not complete successfully and requires "
                "an alternative plan."
            ),
            "automatic_replanning": False,
        }

    if review_status == "needs_attention":
        return {
            "replanning_required": True,
            "action": "review_and_replan",
            "reason": (
                "Execution requires additional review before continuing."
            ),
            "automatic_replanning": False,
        }

    return {
        "replanning_required": False,
        "action": "continue",
        "reason": (
            "Execution completed without requiring replanning."
        ),
        "automatic_replanning": False,
    }

