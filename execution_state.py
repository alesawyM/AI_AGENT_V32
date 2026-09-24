import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional


BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "execution_state.json"


def _now() -> str:
    return datetime.now().isoformat()


def _default_state() -> Dict[str, Any]:
    return {
        "active": False,
        "request": None,
        "status": "idle",
        "workflow": None,
        "cycle": 0,
        "replans": 0,
        "updated_at": _now(),
        "history": [],
    }


def load_execution_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return _default_state()

    try:
        data = json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(data, dict):
            return _default_state()

        return data

    except Exception:
        return _default_state()


def save_execution_state(
    state: Dict[str, Any]
) -> Dict[str, Any]:

    state = dict(state)

    state["updated_at"] = _now()

    STATE_FILE.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return state


def start_execution(
    request: str,
    workflow: Optional[str] = None,
) -> Dict[str, Any]:

    state = load_execution_state()

    state.update({
        "active": True,
        "request": request,
        "status": "running",
        "workflow": workflow,
        "cycle": 0,
        "replans": 0,
    })

    state.setdefault(
        "history",
        []
    ).append({
        "event": "started",
        "timestamp": _now(),
        "request": request,
    })

    return save_execution_state(state)


def update_execution(
    status: str,
    cycle: Optional[int] = None,
    replans: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    state = load_execution_state()

    state["status"] = status

    if cycle is not None:
        state["cycle"] = cycle

    if replans is not None:
        state["replans"] = replans

    event = {
        "event": status,
        "timestamp": _now(),
    }

    if details:
        event["details"] = details

    state.setdefault(
        "history",
        []
    ).append(event)

    return save_execution_state(state)


def complete_execution(
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    state = load_execution_state()

    state["active"] = False
    state["status"] = "completed"

    state.setdefault(
        "history",
        []
    ).append({
        "event": "completed",
        "timestamp": _now(),
        "details": details or {},
    })

    return save_execution_state(state)


def stop_execution(
    reason: str,
) -> Dict[str, Any]:

    state = load_execution_state()

    state["active"] = False
    state["status"] = "stopped"

    state.setdefault(
        "history",
        []
    ).append({
        "event": "stopped",
        "timestamp": _now(),
        "reason": reason,
    })

    return save_execution_state(state)


def get_active_execution() -> Optional[Dict[str, Any]]:

    state = load_execution_state()

    if state.get("active"):
        return state

    return None


def reset_execution_state() -> Dict[str, Any]:

    state = _default_state()

    return save_execution_state(state)
