import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional


BASE_DIR = Path(__file__).resolve().parent
CHECKPOINT_FILE = BASE_DIR / "execution_checkpoint.json"


def _now() -> str:
    return datetime.now().isoformat()


def _default_checkpoint() -> Dict[str, Any]:
    return {
        "active": False,
        "request": None,
        "stage": None,
        "workflow": None,
        "data": {},
        "created_at": None,
        "updated_at": _now(),
    }


def load_checkpoint() -> Dict[str, Any]:

    if not CHECKPOINT_FILE.exists():
        return _default_checkpoint()

    try:
        data = json.loads(
            CHECKPOINT_FILE.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(data, dict):
            return _default_checkpoint()

        return data

    except Exception:
        return _default_checkpoint()


def save_checkpoint(
    checkpoint: Dict[str, Any]
) -> Dict[str, Any]:

    checkpoint = dict(checkpoint)

    checkpoint["updated_at"] = _now()

    CHECKPOINT_FILE.write_text(
        json.dumps(
            checkpoint,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return checkpoint


def create_checkpoint(
    request: str,
    stage: str,
    workflow: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    checkpoint = {
        "active": True,
        "request": request,
        "stage": stage,
        "workflow": workflow,
        "data": data or {},
        "created_at": _now(),
    }

    return save_checkpoint(checkpoint)


def update_checkpoint(
    stage: str,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    checkpoint = load_checkpoint()

    checkpoint["active"] = True
    checkpoint["stage"] = stage

    if data is not None:
        checkpoint["data"] = data

    return save_checkpoint(checkpoint)


def complete_checkpoint(
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    checkpoint = load_checkpoint()

    checkpoint["active"] = False
    checkpoint["stage"] = "completed"

    if data is not None:
        checkpoint["data"] = data

    return save_checkpoint(checkpoint)


def clear_checkpoint() -> Dict[str, Any]:

    checkpoint = _default_checkpoint()

    return save_checkpoint(checkpoint)


def get_active_checkpoint() -> Optional[Dict[str, Any]]:

    checkpoint = load_checkpoint()

    if checkpoint.get("active"):
        return checkpoint

    return None
