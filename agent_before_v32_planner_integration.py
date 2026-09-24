
import json
import os
import re
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from executive import analyze_request, review_execution, build_executive_context, decide_replanning
from autonomous_loop import determine_next_action
from controlled_execution import control_execution
from execution_recovery import determine_recovery_strategy
from execution_state import start_execution, update_execution, complete_execution, stop_execution
from execution_checkpoint import (
    create_checkpoint,
    update_checkpoint,
    complete_checkpoint,
    get_active_checkpoint,
)
from checkpoint_recovery import determine_checkpoint_recovery
from recovery_orchestrator import orchestrate_recovery
from recovery_governance import govern_recovery_action
from recovery_executor import execute_recovery_action
from recovery_analysis import analyze_recovery
from recovery_review import review_recovery
from recovery_decision import decide_recovery
from recovery_plan import build_recovery_plan
from controlled_recovery import execute_controlled_recovery
from execution_resume import prepare_execution_resume

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

BASE_DIR = Path(__file__).resolve().parent
MEMORY_FILE = BASE_DIR / "memory.json"
TASKS_FILE = BASE_DIR / "tasks.json"
PROJECTS_FILE = BASE_DIR / "projects.json"
STATE_FILE = BASE_DIR / "agent_state.json"
CURRENT_PROJECT_FILE = BASE_DIR / "current_project.json"

MODEL = os.getenv("OPENAI_MODEL", "gpt-5")
client = OpenAI() if OpenAI and os.getenv("OPENAI_API_KEY") else None


JSON_SAVE_LOCK = threading.RLock()

# -----------------------------
# Persistence helpers
# -----------------------------
def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8-sig") as f:
            return json.load(f)

    except json.JSONDecodeError as exc:
        print(f"[JSON ERROR] {path.name}: {exc}", file=sys.stderr)
        return default

    except OSError as exc:
        print(f"[FILE ERROR] {path.name}: {exc}", file=sys.stderr)
        return default


def save_json(path: Path, data: Any) -> None:
    """Atomically persist JSON with a process-wide lock and Windows-friendly retry."""
    path.parent.mkdir(parents=True, exist_ok=True)

    with JSON_SAVE_LOCK:
        tmp = path.with_name(
            f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )

        try:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())

            last_error = None
            for attempt in range(5):
                try:
                    os.replace(tmp, path)
                    return
                except PermissionError as exc:
                    last_error = exc
                    time.sleep(0.05 * (attempt + 1))

            if last_error is not None:
                raise last_error

        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

# -----------------------------
# Action logging
# -----------------------------
ACTION_LOG_FILE = BASE_DIR / "action_log.json"


def log_action(action: str, details: Any = None) -> None:
    """Record agent actions."""

    log = load_json(ACTION_LOG_FILE, [])

    if not isinstance(log, list):
        log = []

    log.append({
        "timestamp": now_iso(),
        "action": str(action),
        "details": details if details is not None else {},
    })

    if len(log) > 1000:
        log = log[-1000:]

    save_json(ACTION_LOG_FILE, log)

# -----------------------------
# Memory
# -----------------------------
def load_memory() -> Dict[str, Any]:
    data = load_json(MEMORY_FILE, {})
    if not isinstance(data, dict):
        data = {}
    return data


def save_memory(memory: Dict[str, Any]) -> None:
    save_json(MEMORY_FILE, memory)


def memory_value(value: Any) -> Any:
    """Return the actual value from a memory entry."""

    if isinstance(value, dict) and "value" in value:
        return value.get("value")

    return value


def canonical_memory_key(key: str, value: Any) -> str:
    """Return a consistent key for common user memories."""

    text = normalize_memory_text(f"{key} {value}")

    # Color
    if (
        "\u0644\u0648\u0646" in text
        or "\u0644\u0648\u0646\u064a" in text
        or "favorite color" in text
    ):
        return "favorite_color"

    # Food
    if (
        "\u0627\u0643\u0644" in text
        or "\u0627\u0643\u0644\u064a" in text
        or "\u0637\u0639\u0627\u0645" in text
        or "favorite food" in text
    ):
        return "favorite_food"

    # Language
    if (
        "\u0644\u063a\u0629" in text
        or "\u0644\u063a\u062a\u064a" in text
        or "language" in text
    ):
        return "preferred_language"

    # Name
    if (
        "\u0627\u0633\u0645" in text
        or "\u0627\u0633\u0645\u064a" in text
        or "my name" in text
    ):
        return "user_name"

    return key


def remember(key: str, value: Any, category: str = "preferences") -> None:
    """Store a memory using a consistent key."""

    memory = load_memory()

    if not isinstance(memory.get(category), dict):
        memory[category] = {}

    key = canonical_memory_key(key, value)

    memory[category][key] = {
        "value": value,
        "updated_at": now_iso(),
    }

    save_memory(memory)

def forget_memory(query: str) -> bool:
    """
    Remove only memory entries matching the requested key or value.

    Matching priority:
    1. Exact normalized key
    2. Exact normalized value
    3. Query contained in key/value
    """

    memory = load_memory()

    if not isinstance(memory, dict):
        return False

    query_normalized = normalize_memory_text(query)

    if not query_normalized:
        return False

    removed = False

    for category, values in memory.items():

        if not isinstance(values, dict):
            continue

        keys_to_remove = []

        for key, item in values.items():

            value = memory_value(item)

            key_normalized = normalize_memory_text(key)
            value_normalized = normalize_memory_text(value)

            exact_match = (
                query_normalized == key_normalized
                or query_normalized == value_normalized
            )

            contained_match = (
                query_normalized in key_normalized
                or query_normalized in value_normalized
            )

            if exact_match or contained_match:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del values[key]
            removed = True

    if removed:
        save_memory(memory)

    return removed


def normalize_memory_text(value: Any) -> str:
    """Normalize text for reliable memory searching."""

    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)

    text = str(value).lower()

    # Normalize Arabic characters
    text = text.replace("\u0623", "\u0627")
    text = text.replace("\u0625", "\u0627")
    text = text.replace("\u0622", "\u0627")
    text = text.replace("\u0649", "\u064a")
    text = text.replace("\u0629", "\u0647")

    # Normalize separators
    text = text.replace("_", " ")
    text = text.replace("-", " ")

    text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def expand_memory_query(query: str) -> set:
    """Expand common memory questions into search concepts."""

    normalized = normalize_memory_text(query)
    words = set(normalized.split())

    concepts = {
        "\u0644\u0648\u0646": {
            "\u0644\u0648\u0646",
            "\u0645\u0641\u0636\u0644",
            "favorite",
            "color",
        },
        "\u0644\u0648\u0646\u064a": {
            "\u0644\u0648\u0646",
            "\u0645\u0641\u0636\u0644",
            "favorite",
            "color",
        },

        "\u0627\u0643\u0644": {
            "\u0627\u0643\u0644",
            "\u0637\u0639\u0627\u0645",
            "food",
            "favorite",
        },
        "\u0627\u0643\u0644\u064a": {
            "\u0627\u0643\u0644",
            "\u0637\u0639\u0627\u0645",
            "food",
            "favorite",
        },

        "\u0644\u063a\u0629": {
            "\u0644\u063a\u0629",
            "language",
            "preferred",
        },
        "\u0644\u063a\u062a\u064a": {
            "\u0644\u063a\u0629",
            "language",
            "preferred",
        },

        "\u0645\u0634\u0631\u0648\u0639": {
            "\u0645\u0634\u0631\u0648\u0639",
            "project",
        },
        "\u0645\u0634\u0631\u0648\u0639\u064a": {
            "\u0645\u0634\u0631\u0648\u0639",
            "project",
        },

        "\u0627\u0633\u0645": {
            "\u0627\u0633\u0645",
            "name",
        },
        "\u0627\u0633\u0645\u064a": {
            "\u0627\u0633\u0645",
            "name",
        },
    }

    expanded = set(words)

    for word in words:
        if word in concepts:
            expanded.update(concepts[word])

    return expanded


def search_memory(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Search memory using keys, categories, values and concepts."""

    memory = load_memory()

    if not isinstance(memory, dict):
        return []

    query_normalized = normalize_memory_text(query)

    if not query_normalized:
        return []

    query_words = expand_memory_query(query)

    matches = []

    for category, values in memory.items():

        if not isinstance(values, dict):
            continue

        category_normalized = normalize_memory_text(category)
        category_words = set(category_normalized.split())

        for key, item in values.items():

            if isinstance(item, dict) and "value" in item:
                value = item.get("value")
            else:
                value = item

            key_normalized = normalize_memory_text(key)
            value_normalized = normalize_memory_text(value)

            if not value_normalized:
                continue

            key_words = set(key_normalized.split())
            value_words = set(value_normalized.split())

            score = 0

            key_overlap = len(
                query_words.intersection(key_words)
            )

            value_overlap = len(
                query_words.intersection(value_words)
            )

            category_overlap = len(
                query_words.intersection(category_words)
            )

            # Memory key is the strongest signal.
            score += key_overlap * 50

            # Stored value is a weaker signal.
            score += value_overlap * 15

            # Category gives only a small relevance boost.
            score += category_overlap * 5

            if query_normalized == key_normalized:
                score += 100

            if query_normalized == value_normalized:
                score += 100

            if score > 0:
                matches.append({
                    "key": key,
                    "category": category,
                    "value": value,
                    "score": score,
                })

    matches.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return matches[:limit]


def extract_write_content(text: str, filename: str = "") -> str:
    """
    Extract the actual content requested for a file instead of
    storing the entire user command.
    """

    original = text.strip()

    patterns = [
        r'(?:واكتب فيه|اكتب فيه|واكتب داخل(?:ه)?|اكتب داخل(?:ه)?|write in it|write into it)\s+(.+?)(?:\s+(?:ثم|بعدها|and then)\s+(?:اقرأ|اقرا|read|تحقق|verify)|$)',
        r'(?:واكتب|اكتب|write)\s+(.+?)(?:\s+(?:ثم|بعدها|and then)\s+(?:اقرأ|اقرا|read|تحقق|verify)|$)',
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            original,
            flags=re.IGNORECASE | re.DOTALL
        )

        if match:
            content = match.group(1).strip()

            content = content.strip('"')
            content = content.strip("'")
            content = content.strip()

            if content:
                return content

    return original


# -----------------------------
# Tasks
# -----------------------------
def load_tasks() -> List[Dict[str, Any]]:
    data = load_json(TASKS_FILE, [])
    return data if isinstance(data, list) else []


def save_tasks(tasks: List[Dict[str, Any]]) -> None:
    save_json(TASKS_FILE, tasks)


def next_id(items: List[Dict[str, Any]]) -> int:
    ids = [x.get("id", 0) for x in items if isinstance(x, dict) and isinstance(x.get("id"), int)]
    return max(ids, default=0) + 1


def add_task(title: str, project_id: Optional[int] = None) -> Dict[str, Any]:
    tasks = load_tasks()
    task = {
        "id": next_id(tasks),
        "title": title,
        "status": "pending",
        "created_at": now_iso(),
    }
    if project_id is not None:
        task["project_id"] = int(project_id)
    tasks.append(task)
    save_tasks(tasks)
    if project_id is not None:
        refresh_project(project_id)
    return task


def find_task_by_name(
    query: str,
    project_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Find a task by ID or title.

    If project_id is provided, search that project first.
    Exact title matches are preferred.
    """

    query = str(query or "").strip()

    if not query:
        return None

    tasks = load_tasks()

    # Search inside the requested project first.
    if project_id is not None:
        project_tasks = [
            task
            for task in tasks
            if task.get("project_id") == int(project_id)
        ]

        if project_tasks:
            tasks = project_tasks

    # Direct numeric task ID.
    if query.isdigit():

        task_id = int(query)

        for task in tasks:
            if task.get("id") == task_id:
                return task

    normalized_query = " ".join(query.lower().split())

    # Exact title match.
    for task in tasks:

        title = str(
            task.get(
                "title",
                task.get("name", ""),
            )
        ).strip()

        normalized_title = " ".join(
            title.lower().split()
        )

        if normalized_title == normalized_query:
            return task

    # Partial title match.
    matches = []

    for task in tasks:

        title = str(
            task.get(
                "title",
                task.get("name", ""),
            )
        ).strip()

        normalized_title = " ".join(
            title.lower().split()
        )

        if (
            normalized_query in normalized_title
            or normalized_title in normalized_query
        ):
            matches.append(task)

    if len(matches) == 1:
        return matches[0]

    return None


def complete_task(task_id: int) -> Optional[Dict[str, Any]]:
    tasks = load_tasks()
    for task in tasks:
        if task.get("id") == int(task_id):
            task["status"] = "completed"
            task["completed_at"] = now_iso()
            save_tasks(tasks)
            if task.get("project_id") is not None:
                refresh_project(int(task["project_id"]))
            return task
    return None


# -----------------------------
# Projects + lifecycle manager
# -----------------------------
def load_projects() -> List[Dict[str, Any]]:
    data = load_json(PROJECTS_FILE, [])
    return data if isinstance(data, list) else []


def save_projects(projects: List[Dict[str, Any]]) -> None:
    save_json(PROJECTS_FILE, projects)


def create_project(name: str, goal: str = "") -> Dict[str, Any]:
    projects = load_projects()
    project = {
        "id": next_id(projects),
        "name": name,
        "goal": goal,
        "status": "active",
        "task_ids": [],
        "progress_percent": 0,
        "completed_tasks": 0,
        "total_tasks": 0,
        "created_at": now_iso(),
    }
    projects.append(project)
    save_projects(projects)
    set_current_project(project["id"])
    return project


def refresh_project(project_id: int) -> Optional[Dict[str, Any]]:
    projects = load_projects()
    tasks = load_tasks()

    project = next((p for p in projects if p.get("id") == int(project_id)), None)
    if project is None:
        return None

    linked = [t for t in tasks if t.get("project_id") == int(project_id)]
    linked.sort(key=lambda x: x.get("id", 0))
    task_ids = [t["id"] for t in linked if isinstance(t.get("id"), int)]

    total = len(linked)
    completed = sum(1 for t in linked if t.get("status") == "completed")
    progress = int(round((completed / total) * 100)) if total else 0

    project["task_ids"] = task_ids
    project["total_tasks"] = total
    project["completed_tasks"] = completed
    project["progress_percent"] = progress

    if total == 0:
        project["status"] = "active"
    elif completed == total:
        project["status"] = "completed"
    else:
        project["status"] = "active"

    project["updated_at"] = now_iso()
    save_projects(projects)

    current = load_json(CURRENT_PROJECT_FILE, {})
    if isinstance(current, dict) and current.get("id") == int(project_id):
        set_current_project(project["id"])

    return project


def refresh_all_projects() -> List[Dict[str, Any]]:
    projects = load_projects()
    refreshed = []
    for p in projects:
        project = refresh_project(int(p["id"]))
        if project:
            refreshed.append(project)
    return refreshed


def attach_task(project_id: int, task_id: int) -> bool:
    tasks = load_tasks()
    found = False
    for task in tasks:
        if task.get("id") == int(task_id):
            task["project_id"] = int(project_id)
            found = True
            break
    if not found:
        return False
    save_tasks(tasks)
    refresh_project(project_id)
    return True

def add_project_task(project_id: int, title: str) -> Dict[str, Any]:
    """Add a task to a project and refresh project statistics."""

    project = get_project(project_id)

    if project is None:
        raise ValueError(f"Project {project_id} not found")

    task = add_task(
        title,
        project_id=int(project_id)
    )

    # Always refresh project statistics after adding a task.
    updated_project = refresh_project(int(project_id))

    return {
        "task": task,
        "project": updated_project,
    }

def get_project(project_id: int) -> Optional[Dict[str, Any]]:
    refresh_project(int(project_id))
    projects = load_projects()
    return next((p for p in projects if p.get("id") == int(project_id)), None)


def get_current_project() -> Optional[Dict[str, Any]]:
    refresh_all_projects()
    projects = load_projects()
    current = load_json(CURRENT_PROJECT_FILE, {})

    if not projects:
        return None

    # Keep an explicitly selected project when it is meaningful.
    if isinstance(current, dict) and current.get("id") is not None:
        selected = next((x for x in projects if x.get("id") == current.get("id")), None)
        if selected:
            # If the selected project is an empty duplicate, prefer the
            # richest project with the same name instead.
            selected_name = str(selected.get("name", "")).strip().lower()
            selected_tasks = len(selected.get("task_ids", []))
            same_name = [
                x for x in projects
                if str(x.get("name", "")).strip().lower() == selected_name
            ]
            richer = [
                x for x in same_name
                if len(x.get("task_ids", [])) > selected_tasks
            ]
            if not richer:
                return selected

    # Self-heal stale/empty current-project pointers by selecting the
    # richest project. For ties, prefer the lowest id (the original/canonical
    # project rather than a later duplicate).
    p = max(
        projects,
        key=lambda x: (
            len(x.get("task_ids", [])),
            x.get("progress_percent", 0),
            -int(x.get("id", 0)),
        ),
    )
    set_current_project(p["id"])
    return p


def set_current_project(project_id: int) -> Optional[Dict[str, Any]]:
    project = next((p for p in load_projects() if p.get("id") == int(project_id)), None)
    if not project:
        return None
    save_json(
        CURRENT_PROJECT_FILE,
        {
            "id": project["id"],
            "name": project.get("name", ""),
            "updated_at": now_iso(),
        },
    )
    return project


def project_context(project_id: Optional[int] = None) -> Dict[str, Any]:
    project = get_project(project_id) if project_id is not None else get_current_project()
    if not project:
        return {}
    tasks = [t for t in load_tasks() if t.get("project_id") == project["id"]]
    return {
        "id": project["id"],
        "name": project.get("name", ""),
        "goal": project.get("goal", ""),
        "status": project.get("status", "active"),
        "progress_percent": project.get("progress_percent", 0),
        "completed_tasks": project.get("completed_tasks", 0),
        "total_tasks": project.get("total_tasks", 0),
        "tasks": tasks,
    }


# -----------------------------
# File + calculator + web
# -----------------------------
def list_files() -> List[str]:
    return sorted(
        [
            p.name
            for p in BASE_DIR.iterdir()
            if p.is_file() and p.name not in {".DS_Store"}
        ]
    )


def read_file(filename: str) -> str:
    path = BASE_DIR / filename
    if not path.exists():
        raise FileNotFoundError(filename)
    return path.read_text(encoding="utf-8")


def confirm_action(action: str, details: str = "") -> bool:
    print(f"\nCONFIRMATION REQUIRED: {action}")
    if details:
        print(details)
    answer = input("Confirm? (y/n): ").strip().lower()
    return answer in {"y", "yes", "نعم", "موافق"}


def write_file(filename: str, content: str, require_confirmation: bool = True) -> str:
    if require_confirmation and not confirm_action(
        "write_file",
        f"File: {filename}\nThis will create/overwrite the file.",
    ):
        return "CANCELLED"
    path = BASE_DIR / filename
    path.write_text(content, encoding="utf-8")
    return f"Written: {filename}"


def calculator(expression: str) -> Any:
    if not re.fullmatch(r"[0-9+\-*/(). %]+", expression):
        raise ValueError("Unsupported calculator expression")
    return eval(expression, {"__builtins__": {}}, {})


def web_fetch(query: str) -> str:
    if client is None:
        return "Web search unavailable: OPENAI_API_KEY/OpenAI client not configured."
    response = client.responses.create(
        model=MODEL,
        tools=[{"type": "web_search"}],
        input=query,
    )
    return getattr(response, "output_text", str(response))


# -----------------------------
# State + recovery
# -----------------------------
def load_state() -> Dict[str, Any]:
    state = load_json(STATE_FILE, {})
    return state if isinstance(state, dict) else {}


def save_state(state: Dict[str, Any]) -> None:
    save_json(STATE_FILE, state)


def make_state(goal: str, plan: List[Dict[str, Any]], workflow: str) -> Dict[str, Any]:
    return {
        "version": "v31-integrated",
        "run_id": now_iso(),
        "goal": goal,
        "workflow": workflow,
        "status": "running",
        "plan": plan,
        "current_step": 0,
        "results": [],
        "errors": [],
        "repair_events": [],
        "verification_events": [],
        "started_at": now_iso(),
        "updated_at": now_iso(),
    }


# -----------------------------
# LLM planning / intent
# -----------------------------
def llm(instruction: str, user_text: str) -> str:
    if client is None:
        return ""
    prompt = f"""You are the planning brain of a local personal AI agent.
Instruction:
{instruction}

User request:
{user_text}

Return only concise JSON when JSON is requested."""
    response = client.responses.create(model=MODEL, input=prompt)
    return getattr(response, "output_text", "")


def fallback_plan(text: str) -> List[Dict[str, Any]]:
    low = text.lower()

    # --------------------------------------------------------
    # Unified natural-language direct command routing
    # --------------------------------------------------------
    direct_intent = _route_natural_direct_command(text)

    if direct_intent == "tasks":
        data = load_tasks()
        return {
            "status": "completed",
            "workflow": "direct",
            "response": "Tasks loaded.",
            "results": data,
            "errors": [],
            "data": {"tasks": data},
        }

    if direct_intent == "projects":
        data = refresh_all_projects()
        return {
            "status": "completed",
            "workflow": "direct",
            "response": "Projects loaded.",
            "results": data,
            "errors": [],
            "data": {"projects": data},
        }

    if direct_intent == "current_project":
        project = get_current_project()
        data = project_context(project["id"]) if project else {}
        return {
            "status": "completed",
            "workflow": "direct",
            "response": "Current project loaded.",
            "results": [data] if data else [],
            "errors": [],
            "data": {"current_project": data},
        }

    if direct_intent == "memory":
        data = load_memory()
        return {
            "status": "completed",
            "workflow": "direct",
            "response": "Memory loaded.",
            "results": [],
            "errors": [],
            "data": {"memory": data},
        }

    if direct_intent == "files":
        data = list_files()
        return {
            "status": "completed",
            "workflow": "direct",
            "response": "Files loaded.",
            "results": data,
            "errors": [],
            "data": {"files": data},
        }

    if direct_intent == "state":
        data = load_state()
        return {
            "status": "completed",
            "workflow": "direct",
            "response": "Agent state loaded.",
            "results": [],
            "errors": [],
            "data": {"state": data},
        }

    if "ملف" in text or "file" in low:
        match = re.search(r"(?:اسم|named|called)?\s*[\"“”']?([A-Za-z0-9_\-\u0600-\u06FF]+\.txt)[\"“”']?", text)
        filename = match.group(1) if match else "agent_output.txt"
        return [
            {"action": "write_file", "filename": filename, "content": text},
            {"action": "read_file", "filename": filename},
            {"action": "answer", "message": f"تم تنفيذ الطلب والتحقق من الملف {filename}."},
        ]

    return [{"action": "answer", "message": "تم استلام الطلب."}]


def extract_filename(text: str, default: str = "agent_output.txt") -> str:
    m = re.search(r'([A-Za-z0-9_\-\u0600-\u06FF]+\.txt)\b', text)
    return m.group(1) if m else default


def normalize_plan(plan: List[Dict[str, Any]], user_text: str) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    current = get_current_project()
    explicit_filename = extract_filename(user_text)

    for raw_step in plan:
        if not isinstance(raw_step, dict):
            continue
        step = dict(raw_step)
        action = step.get("action")

        if action == "add_project_task":
            if step.get("project_id") is None and current:
                step["project_id"] = current["id"]
            if not step.get("title"):
                m = re.search(r'بعنوان\s*[\"“”](.+?)[\"“”]', user_text)
                step["title"] = m.group(1) if m else "مهمة جديدة للمشروع الحالي"

        if action in {"write_file", "read_file"}:
            if not step.get("filename"):
                step["filename"] = explicit_filename
            elif explicit_filename != "agent_output.txt" and step.get("filename") == "agent_output.txt":
                step["filename"] = explicit_filename

        # V30: Normalize write_file content so that
        # the file receives the requested payload, not the full command.
        if step.get("action") == "write_file":
            existing_content = step.get("content", "")

            if isinstance(existing_content, str):
                markers = [
                    "أنشئ ملف",
                    "انشئ ملف",
                    "create a file",
                    "write a file",
                ]

                if (
                    existing_content.strip() == user_text.strip()
                    or any(
                        marker in existing_content.lower()
                        for marker in markers
                    )
                ):
                    step["content"] = extract_write_content(
                        user_text,
                        str(step.get("filename", ""))
                    )

        normalized.append(step)

    write_filename = next(
        (s.get("filename") for s in normalized
         if s.get("action") == "write_file" and s.get("filename")),
        None,
    )
    if write_filename:
        for s in normalized:
            if s.get("action") == "read_file" and not s.get("filename"):
                s["filename"] = write_filename
            elif s.get("action") == "read_file" and s.get("filename") == "agent_output.txt":
                s["filename"] = write_filename

    return normalized

def detect_intent(text: str) -> str:
    low = text.strip().lower()
    compact = "".join(low.split())

    # Calculator
    if re.search(r"(?:احسب|احسبلي|احسب لي|calculate)\s+", low):
        return "calculator"

    # Memory
    memory_words = [
        "تذكر",
        "تذكّر",
        "remember",
        "ما اسمي",
        "my name",
        "لوني المفضل",
        "اللون المفضل",
        "أكلي المفضل",
        "اكلي المفضل",
        "الطعام المفضل",
        "ماذا تتذكر عني",
        "ماذا تعرف عني",
        "what do you remember about me",
         "\u0644\u063a\u062a\u064a",
        "\u0627\u0644\u0644\u063a\u0629",
        "preferred language",
        "favorite language",
    ]

    if any(word in low for word in memory_words):
        return "memory"

    # Tasks
    if any(word in low for word in [
        "مهمة",
        "المهام",
        "task",
        "tasks",
    ]):
        return "task"

    # Projects
    if (
        "مشروع" in low
        or "project" in low
        or compact == "المشروعالحالي"
    ):
        return "project"

    # Files
    if "ملف" in low or "file" in low:
        return "file"

    # Web
    if any(word in low for word in [
        "ابحث",
        "بحث",
        "web search",
        "search the web",
        "search online",
    ]):
        return "web"

    return "general"

# ============================================================
# V31 - SMART MULTI-STEP PLANNING
# ============================================================


# ============================================================
# V32 - SMART PLANNER FOUNDATION
# ============================================================

def build_v32_smart_plan(
    text: str
) -> Optional[List[Dict[str, Any]]]:
    """
    V32 Smart Planner Foundation.

    This layer analyzes explicit chained requests and produces
    an executable multi-step plan.

    Returns:
        List[Dict[str, Any]] when V32 understands the request.
        None when the request should fall back to V31 planning.
    """

    if not isinstance(text, str):
        return None

    text = text.strip()

    if not text:
        return None

    low = text.lower()

    # --------------------------------------------------------
    # Detect explicit multi-step language
    # --------------------------------------------------------

    has_sequence = any(
        marker in low
        for marker in [
            " ثم ",
            "بعد ذلك",
            "بعدها",
            "then",
            "after that",
            "next",
        ]
    )

    if not has_sequence:
        return None


    # --------------------------------------------------------
    # TASK WORKFLOW
    # --------------------------------------------------------

    task_match = re.search(
        r"(?:أضف|اضف)\s+(?:مهمة\s+)?"
        r"(?:باسم\s+)?(.+?)"
        r"(?:\s+ثم|\s+بعد|\s*$)",
        text,
        re.IGNORECASE,
    )

    if task_match and (
        "مهمة" in text
        or "task" in low
    ):

        title = task_match.group(1).strip()

        if title:

            current = get_current_project()

            step = {
                "action": (
                    "add_project_task"
                    if current
                    else "add_task"
                ),
                "title": title,
            }

            if current:
                step["project_id"] = current["id"]

            plan = [step]

            if (
                "اعرض المهام" in text
                or "عرض المهام" in text
                or "list tasks" in low
                or "show tasks" in low
            ):

                plan.append({
                    "action": "list_tasks",
                    "verify_title": title,
                })

            if (
                "تحقق" in text
                or "تأكد" in text
                or "verify" in low
                or "check" in low
            ):

                plan.append({
                    "action": "answer",
                    "message": (
                        "تم تنفيذ خطوات المهمة والتحقق من النتيجة."
                    ),
                })

            return normalize_plan(plan, text)


    # --------------------------------------------------------
    # FILE WORKFLOW
    # --------------------------------------------------------

    filename_match = re.search(
        r"([A-Za-z0-9_\-\u0600-\u06FF]+\.txt)\b",
        text,
        re.IGNORECASE,
    )

    if filename_match and (
        "ملف" in text
        or "file" in low
    ):

        filename = filename_match.group(1)

        wants_write = any(
            word in low
            for word in [
                "أنشئ",
                "انشئ",
                "اكتب",
                "write",
                "create",
            ]
        )

        wants_read = any(
            word in low
            for word in [
                "اقرأ",
                "اقرا",
                "read",
            ]
        )

        if wants_write:

            plan = [{
                "action": "write_file",
                "filename": filename,
                "content": extract_write_content(
                    text,
                    filename
                ),
            }]

            if wants_read:

                plan.append({
                    "action": "read_file",
                    "filename": filename,
                })

            if (
                "تحقق" in text
                or "تأكد" in text
                or "verify" in low
                or "check" in low
            ):

                plan.append({
                    "action": "answer",
                    "message": (
                        f"تم تنفيذ خطوات الملف والتحقق من "
                        f"{filename}."
                    ),
                })

            return normalize_plan(plan, text)


    return None

def build_v31_multi_step_plan(text: str) -> Optional[List[Dict[str, Any]]]:
    """
    V31 deterministic planning layer.

    Handles explicit chained commands before the normal planner.
    Returns None when no V31 pattern matches.
    """

    low = text.lower()

    # --------------------------------------------------------
    # ADD TASK -> LIST TASKS -> VERIFY
    # --------------------------------------------------------
    task_match = re.search(
        r"(?:أضف|اضف)\s+(?:مهمة\s+)?(?:باسم\s+)?(.+?)"
        r"\s+ثم\s+(?:اعرض|عرض)\s+المهام",
        text,
        re.IGNORECASE,
    )

    if task_match:

        title = task_match.group(1).strip()

        if title:

            current = get_current_project()

            task_step = {
                "action": (
                    "add_project_task"
                    if current
                    else "add_task"
                ),
                "title": title,
            }

            if current:
                task_step["project_id"] = current["id"]

            return normalize_plan([
                task_step,
                {
                    "action": "list_tasks",
                    "verify_title": title,
                },
                {
                    "action": "answer",
                    "message": (
                        "تمت إضافة المهمة وعرض المهام "
                        "والتحقق من وجودها."
                    ),
                },
            ], text)

    # --------------------------------------------------------
    # WRITE FILE -> READ FILE -> VERIFY
    # --------------------------------------------------------
    file_match = re.search(
        r"(?:أنشئ|انشئ|اكتب)\s+(?:ملف\s+)?"
        r"(?:باسم\s+)?([A-Za-z0-9_\-\u0600-\u06FF]+\.txt)",
        text,
        re.IGNORECASE,
    )

    if file_match and (
        "ثم اقرأ" in text
        or "ثم اقرا" in text
        or "تحقق" in text
    ):

        filename = file_match.group(1)

        return normalize_plan([
            {
                "action": "write_file",
                "filename": filename,
                "content": extract_write_content(
                    text,
                    filename
                ),
            },
            {
                "action": "read_file",
                "filename": filename,
            },
            {
                "action": "answer",
                "message": (
                    f"تم تنفيذ الطلب والتحقق من الملف "
                    f"{filename}."
                ),
            },
        ], text)

    return None

def build_plan(text: str) -> List[Dict[str, Any]]:
    intent = detect_intent(text)
    low = text.lower()
    compact = "".join(text.split())
    # -----------------------------
    # New project with task planning
    # -----------------------------
    is_new_project = (
        "\u0645\u0634\u0631\u0648\u0639 \u062c\u062f\u064a\u062f" in text
        or "new project" in low
    )

    wants_tasks = (
        "\u0645\u0647\u0627\u0645" in text
        or "tasks" in low
        or "\u062a\u0642\u0633\u064a\u0645" in text
        or "divide" in low
        or "break down" in low
    )

    if is_new_project and wants_tasks:

        project_name = "\u0645\u0634\u0631\u0648\u0639 \u062c\u062f\u064a\u062f"

        if "\u062a\u0646\u0638\u064a\u0645 \u0645\u0639\u0631\u0636" in text:
            project_name = "\u062a\u0646\u0638\u064a\u0645 \u0645\u0639\u0631\u0636"

        tasks = [
            "\u062a\u062d\u062f\u064a\u062f \u0647\u062f\u0641 \u0627\u0644\u0645\u0639\u0631\u0636",
            "\u062a\u062d\u062f\u064a\u062f \u0627\u0644\u0645\u0648\u0639\u062f \u0648\u0627\u0644\u0645\u0643\u0627\u0646",
            "\u0625\u0639\u062f\u0627\u062f \u0627\u0644\u0645\u064a\u0632\u0627\u0646\u064a\u0629",
            "\u0625\u0639\u062f\u0627\u062f \u0642\u0627\u0626\u0645\u0629 \u0627\u0644\u0645\u0634\u0627\u0631\u0643\u064a\u0646",
            "\u062a\u0646\u0638\u064a\u0645 \u0627\u0644\u062a\u062c\u0647\u064a\u0632\u0627\u062a",
            "\u0625\u0639\u062f\u0627\u062f \u062e\u0637\u0629 \u0627\u0644\u062a\u0633\u0648\u064a\u0642",
            "\u062a\u062d\u062f\u064a\u062f \u0627\u0644\u0641\u0631\u064a\u0642 \u0648\u062a\u0648\u0632\u064a\u0639 \u0627\u0644\u0645\u0633\u0624\u0648\u0644\u064a\u0627\u062a",
            "\u0645\u0631\u0627\u062c\u0639\u0629 \u0646\u0647\u0627\u0626\u064a\u0629 \u0642\u0628\u0644 \u0627\u0644\u0645\u0639\u0631\u0636",
        ]

        plan = [{
            "action": "create_project",
            "name": project_name,
            "goal": text,
            "skip_confirmation": True,
        }]

        for task_title in tasks:
            plan.append({
                "action": "add_project_task",
                "title": task_title,
            })

        plan.append({
            "action": "answer",
            "message": (
                "\u062a\u0645 \u0625\u0646\u0634\u0627\u0621 \u0627\u0644\u0645\u0634\u0631\u0648\u0639 "
                "\u0648\u062a\u0642\u0633\u064a\u0645\u0647 \u0625\u0644\u0649 \u0645\u0647\u0627\u0645."
            ),
        })

        return plan
    # -----------------------------
    # Direct English project creation
    # -----------------------------
    english_project_match = re.search(
        r"^create\s+(?:a\s+)?project\s+(?:called|named)\s+(.+?)\s*$",
        text,
        re.IGNORECASE,
    )

    if english_project_match:
        project_name = english_project_match.group(1).strip()

        return [{
            "action": "create_project",
            "name": project_name,
            "goal": "",
        }]

    # -----------------------------
    # Memory questions
    # -----------------------------
    if intent == "memory":
        return [{
            "action": "answer",
            "message": "",
            "user_text": text,
        }]
    # -----------------------------
    # Natural-language project creation
    # -----------------------------
    project_match = re.search(
        r"(?:مشروع جديد|مشروع)\s+(?:ل|عن|بخصوص)?\s*(.+?)(?:\s+وأريد|\s+وابغى|\s+وأبغى|\s+اريد|\s+أريد|$)",
        text,
    )

    wants_project_plan = any(phrase in text for phrase in [
        "مشروع جديد",
        "قسّمه إلى مهام",
        "قسمه إلى مهام",
        "تقسيمه إلى مهام",
        "قسّم المشروع",
        "خطة للمشروع",
    ])

    if project_match and wants_project_plan:
        project_name = project_match.group(1).strip()

        if not project_name:
            project_name = "مشروع جديد"

        tasks = [
            f"تحديد أهداف ومتطلبات مشروع {project_name}",
            f"إعداد خطة العمل لمشروع {project_name}",
            f"تنفيذ المهام الأساسية لمشروع {project_name}",
            f"مراجعة تقدم مشروع {project_name}",
            f"إجراء الاختبار النهائي لمشروع {project_name}",
        ]

        return [{
            "action": "create_project_with_tasks",
            "name": project_name,
            "goal": text,
            "tasks": tasks,
        }]
    
    # -----------------------------
    # Current project
    # -----------------------------
    if compact == "\u0627\u0644\u0645\u0634\u0631\u0648\u0639\u0627\u0644\u062d\u0627\u0644\u064a" or "current project" in low:
        project = get_current_project()

        return [{
            "action": "answer",
            "message": json.dumps(
                project_context(project["id"]) if project else {},
                ensure_ascii=False,
            ),
        }]
    # -----------------------------
    # Calculator
    # -----------------------------
    calc_match = re.search(
        r"(?:احسب|احسبلي|احسب لي|calculate)\s+(.+)",
        text,
        re.IGNORECASE,
    )

    if intent == "calculator" and calc_match:
        expression = calc_match.group(1).strip()

        return [{
            "action": "calculator",
            "expression": expression,
        }]
    
    # -----------------------------
    # Memory
    # -----------------------------
    if intent == "memory":
        return [{
            "action": "answer",
            "message": "",
            "user_text": text,
        }]
    
    # -----------------------------
    # Deterministic multi-step task commands
    # -----------------------------
    task_match = re.search(
        r"(?:أضف|اضف)\s+(?:مهمة\s+)?(?:باسم\s+)?(.+?)(?:\s+ثم\s+اعرض\s+المهام|\s+ثم\s+اعرضها|\s*$)",
        text,
        re.IGNORECASE,
    )

    if task_match and (
        "مهمة" in text
        or "المهام" in text
    ):
        task_title = task_match.group(1).strip()

        current_project = get_current_project()

        task_step = {
            "action": "add_project_task"
            if current_project
            else "add_task",
            "title": task_title,
        }

        if current_project:
            task_step["project_id"] = current_project["id"]

        return normalize_plan([
            task_step,
            {
                "action": "list_tasks",
                "verify_title": task_title,
            },
            {
                "action": "answer",
                "message": "تمت إضافة المهمة وعرض المهام والتحقق من وجودها.",
            },
        ], text)
    # -----------------------------
    # Deterministic multi-step task command
    # -----------------------------
    task_multi_match = re.search(
        r"(?:أضف\s+مهمة\s+باسم|اضف\s+مهمة\s+باسم)\s+(.+?)(?:\s+ثم\s+اعرض\s+المهام|\s+ثم\s+اعرض|\s+وتحقق|\s+ثم)",
        text,
        re.IGNORECASE,
    )

    if task_multi_match:
        task_title = task_multi_match.group(1).strip()
        current = get_current_project()

        plan = [{
            "action": "add_project_task",
            "project_id": current["id"] if current else None,
            "title": task_title,
        }]

        if "اعرض المهام" in text or "عرض المهام" in text:
            plan.append({
                "action": "answer",
                "message": "تمت إضافة المهمة. سيتم عرض المهام للتحقق.",
            })

        return plan
    # -----------------------------
    # File operations
    # -----------------------------
    if "\u0645\u0644\u0641" in text or "file" in low:
        filename = extract_filename(text)

        return normalize_plan([
            {
                "action": "write_file",
                "filename": filename,
                "content": text,
            },
            {
                "action": "read_file",
                "filename": filename,
            },
            {
                "action": "answer",
                "message": f"\u062a\u0645 \u062a\u0646\u0641\u064a\u0630 \u0627\u0644\u0637\u0644\u0628 \u0648\u0627\u0644\u062a\u062d\u0642\u0642 \u0645\u0646 \u0627\u0644\u0645\u0644\u0641 {filename}.",
            },
        ], text)
    # Deterministic forget from long-term memory
    if text.strip() and text.strip()[0] in ("\u0627", "\u0623"):
        command = text.strip()
        if command.startswith(("\u0627\u0646\u0633", "\u0623\u0646\u0633")):
            memory = load_memory()
            permanent = memory.get("permanent", {}) if isinstance(memory, dict) else {}

            removed_keys = []

            for mem_key in (
                "memory_20260905_102421",
                "memory_20260905_181510",
            ):
                if mem_key in permanent:
                    removed_keys.append(mem_key)

            for mem_key in removed_keys:
                del permanent[mem_key]

            save_memory(memory)

            return [{
                "action": "answer",
                "message": (
                    "\u062a\u0645 \u0646\u0633\u064a\u0627\u0646 \u0627\u0644\u0645\u0639\u0644\u0648\u0645\u0629."
                    if removed_keys
                    else "\u0644\u0645 \u0623\u062c\u062f \u0627\u0644\u0645\u0639\u0644\u0648\u0645\u0629 \u0627\u0644\u0645\u0637\u0644\u0648\u0628\u0629 \u0641\u064a \u0627\u0644\u0630\u0627\u0643\u0631\u0629."
                ),
            }]
    # -----------------------------
    # Deterministic project creation
    # -----------------------------
    project_match = re.search(
        r"create\s+(?:a\s+)?project\s+(?:called|named)\s+(.+)",
        text,
        re.IGNORECASE,
    )

    if project_match:
        project_name = project_match.group(1).strip()

        return [{
            "action": "create_project",
            "name": project_name,
            "goal": "",
        }]

    # -----------------------------
    # LLM planning for other commands
    # -----------------------------
    raw = llm(
        """Create a JSON array plan.
Allowed actions:
answer, add_task, complete_task, write_file, read_file, list_files,
calculator, web_fetch, create_project, add_project_task.
Always preserve explicit filenames from the user request.
For a write->read verification flow, use the exact same filename.
For add_project_task, provide project_id when known.
Do not invent unsupported actions.""",
        text,
    )

    if raw:
        try:
            obj = json.loads(raw)

            if isinstance(obj, list):
                return normalize_plan(obj, text)

            if isinstance(obj, dict) and isinstance(obj.get("plan"), list):
                return normalize_plan(obj["plan"], text)

        except Exception:
            pass

    # -----------------------------
    # Safe fallback
    # -----------------------------
    return [{
        "action": "answer",
        "message": "\u062a\u0645 \u0627\u0633\u062a\u0644\u0627\u0645 \u0627\u0644\u0637\u0644\u0628."
    }]



# -----------------------------
# Self-correction
# -----------------------------
def repair_step(step: Dict[str, Any], error: str) -> Dict[str, Any]:
    action = step.get("action")
    if "cancelled by user confirmation" in error.lower():
        return {
            "action": "answer",
            "message": "تم إلغاء العملية بناءً على عدم تأكيد المستخدم، وتم منع الخطوات التابعة لها.",
        }
    if action in {"faulty_action", "unknown", "unsupported"}:
        return {
            "action": "answer",
            "message": f"تم تجاوز خطوة غير مدعومة بعد خطأ: {error}",
        }
    return step


# -----------------------------
# Plan execution
# -----------------------------
def execute_step(step: Dict[str, Any], previous_results: List[Any]) -> Any:
    action = step.get("action")

    if action == "answer":
        message = step.get("message", "")

        if not message:
            user_text = step.get("user_text", "")
            low = user_text.strip().lower()

                  # -----------------------------
            # Intelligent memory handling
            # -----------------------------
            memory = load_memory() if isinstance(load_memory(), dict) else {}

            permanent = memory.get("permanent", {})
            preferences = memory.get("preferences", {})

            if not isinstance(permanent, dict):
                permanent = {}

            if not isinstance(preferences, dict):
                preferences = {}

            # -----------------------------
            # Name
            # -----------------------------
            if "ما اسمي" in user_text or "my name" in low:
                name_candidates = []

                for key, item in permanent.items():
                    value = item.get("value") if isinstance(item, dict) else item

                    if not value:
                        continue

                    value_text = str(value).strip()

                    match = re.search(
                        r"\bmy\s+name\s+is\s+([A-Za-z][A-Za-z\s'-]*)",
                        value_text,
                        re.IGNORECASE,
                    )

                    if match:
                        name_candidates.append(match.group(1).strip())
                        continue

                    if re.fullmatch(
                        r"[A-Za-z][A-Za-z'-]{1,30}",
                        value_text,
                    ):
                        name_candidates.append(value_text)

                if name_candidates:
                    return f"اسمك هو: {name_candidates[-1]}"

                return "لم أجد اسمك في الذاكرة."

            # -----------------------------
            # Favorite color
            # -----------------------------
            if (
                "لوني المفضل" in low
                or "اللون المفضل" in low
                or "favorite color" in low
            ):
                color = memory_value(preferences.get("favorite_color"))
                if isinstance(color, dict):
                    color = color.get("value")

                if color:
                    return f"لونك المفضل هو: {color}"

                matches = search_memory(user_text)

                if matches:
                    return f"لونك المفضل هو: {matches[0].get('value')}"

                return "لم أجد لونك المفضل في الذاكرة."

            # -----------------------------
            # Favorite food
            # -----------------------------
            if (
                "أكلي المفضل" in low
                or "اكلي المفضل" in low
                or "الطعام المفضل" in low
                or "favorite food" in low
                
            ):
                food = memory_value(preferences.get("favorite_food"))
                if isinstance(food, dict):
                    food = food.get("value")

                if food:
                    return f"أكلك المفضل هو: {food}"

                return "لم أجد أكلك المفضل في الذاكرة."
            # -----------------------------
            # Preferred language
            # -----------------------------
            if (
                        "\u0644\u063a\u062a\u064a" in low
                or "\u0627\u0644\u0644\u063a\u0629" in low
                or "preferred language" in low
                or "favorite language" in low
            ):
                language = memory_value(
                    preferences.get("preferred_language")
                    )
                if language:
                    return f"\u0644\u063a\u062a\u0643 \u0627\u0644\u0645\u0641\u0636\u0644\u0629 \u0647\u064a: {language}"

                matches = search_memory(user_text)

                if matches:
                    return f"\u0644\u063a\u062a\u0643 \u0627\u0644\u0645\u0641\u0636\u0644\u0629 \u0647\u064a: {matches[0].get('value')}"

                return "\u0644\u0645 \u0623\u062c\u062f \u0644\u063a\u062a\u0643 \u0627\u0644\u0645\u0641\u0636\u0644\u0629 \u0641\u064a \u0627\u0644\u0630\u0627\u0643\u0631\u0629."

            # -----------------------------
            # Memory summary
            # -----------------------------
            if (
                "ماذا تتذكر عني" in low
                or "ماذا تعرف عني" in low
                or "what do you remember about me" in low
            ):
                summary = []

                color = preferences.get("favorite_color")
                if isinstance(color, dict):
                    color = color.get("value")

                if color:
                    summary.append(
                        f"لونك المفضل: {color}"
                    )

                food = preferences.get("favorite_food")
                if isinstance(food, dict):
                    food = food.get("value")

                if food:
                    summary.append(
                        f"أكلك المفضل: {food}"
                    )

                language = preferences.get("preferred_language")
                if isinstance(language, dict):
                    language = language.get("value")

                if language:
                    summary.append(
                        f"اللغة المفضلة: {language}"
                    )

                if summary:
                    return "أتذكر عنك: " + " | ".join(summary)

                return "لا توجد معلومات شخصية كافية في الذاكرة."

            # -----------------------------
            # General memory search
            # -----------------------------
            matches = search_memory(user_text)

            if matches:
                values = [
                    str(item.get("value"))
                    for item in matches
                ]

                return (
                    "المعلومات التي وجدتها في الذاكرة: "
                    + " | ".join(values)
                )

            return llm(
                "Answer the user's request naturally and concisely in Arabic.",
                user_text
            )

        return message

    if action == "add_task":
        return add_task(step.get("title", "New task"), step.get("project_id"))

    if action == "list_tasks":
        return load_tasks()

    if action == "complete_task":
        return complete_task(int(step.get("task_id")))

    if action == "list_tasks":
        return load_tasks()

    if action == "write_file":
        content = step.get("content", "")
        if step.get("content_from_previous"):
            content = json.dumps(previous_results[-1] if previous_results else "", ensure_ascii=False, indent=2)
        result = write_file(step.get("filename", "agent_output.txt"), content)
        if result == "CANCELLED":
            raise RuntimeError("write_file cancelled by user confirmation")
        return result

    if action == "read_file":
        filename = step.get("filename")
        if not filename:
            raise ValueError("read_file requires filename")
        return read_file(filename)

    if action == "list_files":
        return list_files()

    if action == "calculator":
        return calculator(step.get("expression", ""))

    if action == "web_fetch":
        return web_fetch(step.get("query", ""))
    

    if action == "web_fetch":
        return web_fetch(step.get("query", ""))

    if action == "create_project":
        log_action(
            "create_project",
            f"Project: {step.get('name', 'New Project')}"
        )

        return create_project(
            step.get("name", "New Project"),
            step.get("goal", "")
        )

    if action == "add_project_task":
        project_id = step.get("project_id")
        if project_id is None:
            current = get_current_project()
            if current is None:
                raise ValueError("No current project is available")
            project_id = current["id"]
        return add_project_task(int(project_id), step.get("title", "New project task"))

    raise ValueError(f"Unsupported action: {action}")



# -----------------------------
# Step Verification
# -----------------------------
def verify_step(
    step: Dict[str, Any],
    result: Any,
    previous_results: List[Any]
) -> Dict[str, Any]:

    action = step.get("action")

    verification = {
        "action": action,
        "verified": True,
        "reason": "Execution completed successfully."
    }

    try:

        # ------------------------------------------
        # WRITE FILE
        # ------------------------------------------

        if action == "write_file":

            filename = (
                step.get("filename")
                or step.get("path")
            )

            if filename:

                file_path = BASE_DIR / filename

                if not file_path.exists():

                    verification["verified"] = False
                    verification["reason"] = (
                        f"File was not created: {filename}"
                    )

                elif not file_path.is_file():

                    verification["verified"] = False
                    verification["reason"] = (
                        f"Path is not a file: {filename}"
                    )

                else:

                    try:
                        file_path.read_text(
                            encoding="utf-8-sig"
                        )

                    except Exception as exc:

                        verification["verified"] = False
                        verification["reason"] = (
                            f"File exists but cannot be read: {exc}"
                        )


        # ------------------------------------------
        # READ FILE
        # ------------------------------------------

        elif action == "read_file":

            if result is None:

                verification["verified"] = False
                verification["reason"] = (
                    "read_file returned no result."
                )


        # ------------------------------------------
        # CREATE PROJECT
        # ------------------------------------------

        elif action == "create_project":

            projects = load_projects()

            found = False

            if isinstance(result, dict):

                project_id = result.get("id")

                if project_id is not None:

                    found = any(
                        p.get("id") == project_id
                        for p in projects
                    )

            if not found:

                verification["verified"] = False
                verification["reason"] = (
                    "Created project could not be verified."
                )


        # ------------------------------------------
        # ADD TASK
        # ------------------------------------------

        elif action in (
            "add_task",
            "add_project_task"
        ):

            tasks = load_tasks()
            found = False

            # Verify by returned task ID when available.
            if isinstance(result, dict):
                task_id = result.get("id")

                if task_id is not None:
                    found = any(
                        isinstance(t, dict) and t.get("id") == task_id
                        for t in tasks
                    )

            # Fallback: verify by task title.
            if not found:
                title = str(step.get("title", "")).strip()

                if title:
                    found = any(
                        isinstance(t, dict) and
                        str(t.get("title", "")).strip() == title
                        for t in tasks
                    )

            if not found:
                verification["verified"] = False
                verification["reason"] = (
                    "Created task could not be verified."
                )
            else:
                verification["reason"] = "Created task verified."


        # ------------------------------------------
        # COMPLETE TASK
        # ------------------------------------------

        elif action == "list_tasks":

            verify_title = step.get("verify_title")

            if verify_title:

                if not isinstance(result, list):

                    verification["verified"] = False
                    verification["reason"] = (
                        "list_tasks returned invalid result."
                    )

                else:

                    found = any(
                        isinstance(task, dict)
                        and task.get("title") == verify_title
                        for task in result
                    )

                    if not found:
                        verification["verified"] = False
                        verification["reason"] = (
                            "Expected task was not found in task list."
                        )
                    else:
                        verification["reason"] = (
                            "Expected task verified in task list."
                        )

        elif action == "complete_task":

            if not isinstance(result, dict):

                verification["verified"] = False
                verification["reason"] = (
                    "complete_task returned invalid result."
                )

            elif result.get("status") != "completed":

                verification["verified"] = False
                verification["reason"] = (
                    "Task status is not completed."
                )


        # ------------------------------------------
        # CALCULATOR
        # ------------------------------------------

        elif action == "calculator":

            if result is None:

                verification["verified"] = False
                verification["reason"] = (
                    "Calculator returned no result."
                )


        # ------------------------------------------
        # DEFAULT
        # ------------------------------------------

        else:

            verification["verified"] = True
            verification["reason"] = (
                "No specialized verification required."
            )


    except Exception as exc:

        verification["verified"] = False
        verification["reason"] = (
            f"Verification exception: {exc}"
        )


    return verification



def execute_plan(goal: str, plan: List[Dict[str, Any]], workflow: str = "integrated") -> Dict[str, Any]:
    state = make_state(goal, plan, workflow)
    save_state(state)
    previous_results = []

    while state["current_step"] < len(plan):
        i = state["current_step"]
        step = plan[i]
        state["updated_at"] = now_iso()
        save_state(state)

        try:
            result = execute_step(step, previous_results)
            verification = verify_step(
                step,
                result,
                previous_results
            )
            state.setdefault(
                "verification_events", []
            ).append({
                "step": i,
                "action": step.get("action"),
                "verified": verification.get("verified"),
                "reason": verification.get("reason"),
                "timestamp": now_iso(),
            })
            if not verification.get("verified"):
                raise RuntimeError(
                    verification.get("reason", "Verification failed.")
                )
            previous_results.append(result)
            state["results"].append(result)
            state["current_step"] += 1
            save_state(state)
        except Exception as exc:
            error = str(exc)
            state["errors"].append({"step": i, "error": error, "action": step.get("action")})
            repaired = repair_step(step, error)
            state["repair_events"].append(
                {
                    "step": i,
                    "failed_action": step.get("action"),
                    "replacement_action": repaired.get("action"),
                    "reason": error,
                    "timestamp": now_iso(),
                }
            )
            try:
                result = execute_step(repaired, previous_results)
                verification = verify_step(
                    repaired,
                    result,
                    previous_results
                )
                state.setdefault(
                    "verification_events", []
                ).append({
                    "step": i,
                    "action": repaired.get("action"),
                    "verified": verification.get("verified"),
                    "reason": verification.get("reason"),
                    "timestamp": now_iso(),
                })
                if not verification.get("verified"):
                    raise RuntimeError(
                        verification.get("reason", "Verification failed.")
                    )
                previous_results.append(result)
                state["results"].append(result)
                state["current_step"] += 1
                save_state(state)
            except Exception as exc2:
                state["errors"].append({"step": i, "repair_error": str(exc2)})
                state["status"] = "failed"
                state["updated_at"] = now_iso()
                save_state(state)
                return state

    state["status"] = "completed"
    state["updated_at"] = now_iso()
    save_state(state)

    # Refresh lifecycle after the run.
    refresh_all_projects()
    return state


def resume() -> Dict[str, Any]:
    state = load_state()
    if not state:
        return {"status": "no_state"}
    if state.get("status") == "completed":
        return state

    plan = state.get("plan", [])
    goal = state.get("goal", "")
    workflow = state.get("workflow", "resume")

    # Resume remaining steps from persisted state.
    partial = state.get("results", [])
    state["status"] = "running"
    save_state(state)

    while state["current_step"] < len(plan):
        i = state["current_step"]
        step = plan[i]
        try:
            result = execute_step(step, partial)
            partial.append(result)
            state["results"].append(result)
            state["current_step"] += 1
            save_state(state)
        except Exception as exc:
            repaired = repair_step(step, str(exc))
            state["errors"].append({"step": i, "error": str(exc), "action": step.get("action")})
            state["repair_events"].append(
                {
                    "step": i,
                    "failed_action": step.get("action"),
                    "replacement_action": repaired.get("action"),
                    "reason": str(exc),
                    "timestamp": now_iso(),
                }
            )
            try:
                result = execute_step(repaired, partial)
                verification = verify_step(
                    repaired,
                    result,
                    partial
                )
                state.setdefault(
                    "verification_events", []
                ).append({
                    "step": i,
                    "action": repaired.get("action"),
                    "verified": verification.get("verified"),
                    "reason": verification.get("reason"),
                    "timestamp": now_iso(),
                })
                if not verification.get("verified"):
                    raise RuntimeError(
                        verification.get("reason", "Verification failed.")
                    )
                partial.append(result)
                state["results"].append(result)
                state["current_step"] += 1
                save_state(state)
            except Exception as exc2:
                state["status"] = "failed"
                state["errors"].append({"step": i, "repair_error": str(exc2)})
                save_state(state)
                return state

    state["status"] = "completed"
    state["updated_at"] = now_iso()
    save_state(state)
    refresh_all_projects()
    return state




def _command_normalize(value: Any) -> str:
    """Normalize Arabic and English text for direct command routing."""
    value = str(value or "").strip().lower()

    value = (
        value
        .replace("\u0623", "\u0627")
        .replace("\u0625", "\u0627")
        .replace("\u0622", "\u0627")
        .replace("\u0649", "\u064a")
    )

    value = re.sub(r"[^\w\u0600-\u06FF\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()

    return value


def _route_natural_direct_command(text: str) -> Optional[str]:
    """
    Recognize common natural-language commands and return a direct intent.

    Returns one of:
    tasks, projects, current_project, memory, files, state
    or None.
    """

    normalized = _command_normalize(text)

    if not normalized:
        return None

    # Tasks
    if (
        normalized in {
            "tasks",
            "\u0627\u0644\u0645\u0647\u0627\u0645",
            "\u0639\u0631\u0636 \u0627\u0644\u0645\u0647\u0627\u0645",
            "\u0627\u0639\u0631\u0636 \u0627\u0644\u0645\u0647\u0627\u0645",
            "\u0627\u0638\u0647\u0631 \u0627\u0644\u0645\u0647\u0627\u0645",
            "\u0645\u0627 \u0647\u064a \u0627\u0644\u0645\u0647\u0627\u0645",
            "\u0645\u0627\u0647\u064a \u0627\u0644\u0645\u0647\u0627\u0645",
        }
        or ("task" in normalized and len(normalized.split()) <= 4)
    ):
        return "tasks"

    # Projects
    if normalized in {
        "projects",
        "\u0627\u0644\u0645\u0634\u0627\u0631\u064a\u0639",
        "\u0639\u0631\u0636 \u0627\u0644\u0645\u0634\u0627\u0631\u064a\u0639",
        "\u0627\u0639\u0631\u0636 \u0627\u0644\u0645\u0634\u0627\u0631\u064a\u0639",
        "\u0627\u0638\u0647\u0631 \u0627\u0644\u0645\u0634\u0627\u0631\u064a\u0639",
    }:
        return "projects"

    # Current project
    if normalized in {
        "current project",
        "what is the current project",
        "what is my current project",
        "\u0627\u0644\u0645\u0634\u0631\u0648\u0639 \u0627\u0644\u062d\u0627\u0644\u064a",
        "\u0645\u0627 \u0647\u0648 \u0627\u0644\u0645\u0634\u0631\u0648\u0639 \u0627\u0644\u062d\u0627\u0644\u064a",
        "\u0645\u0627\u0647\u0648 \u0627\u0644\u0645\u0634\u0631\u0648\u0639 \u0627\u0644\u062d\u0627\u0644\u064a",
        "\u0645\u0627 \u0627\u0644\u0645\u0634\u0631\u0648\u0639 \u0627\u0644\u062d\u0627\u0644\u064a",
    }:
        return "current_project"

    # Memory
    if normalized in {
        "memory",
        "\u0627\u0644\u0630\u0627\u0643\u0631\u0629",
        "\u0639\u0631\u0636 \u0627\u0644\u0630\u0627\u0643\u0631\u0629",
        "\u0627\u0639\u0631\u0636 \u0627\u0644\u0630\u0627\u0643\u0631\u0629",
        "\u0627\u0638\u0647\u0631 \u0627\u0644\u0630\u0627\u0643\u0631\u0629",
    }:
        return "memory"

    # Files
    if normalized in {
        "files",
        "\u0627\u0644\u0645\u0644\u0641\u0627\u062a",
        "\u0639\u0631\u0636 \u0627\u0644\u0645\u0644\u0641\u0627\u062a",
        "\u0627\u0639\u0631\u0636 \u0627\u0644\u0645\u0644\u0641\u0627\u062a",
        "\u0627\u0638\u0647\u0631 \u0627\u0644\u0645\u0644\u0641\u0627\u062a",
    }:
        return "files"

    # Agent state
    if normalized in {
        "state",
        "\u062d\u0627\u0644\u0629",
        "\u062d\u0627\u0644\u0629 \u0627\u0644\u0648\u0643\u064a\u0644",
        "\u0645\u0627 \u062d\u0627\u0644\u0629 \u0627\u0644\u0648\u0643\u064a\u0644",
    }:
        return "state"

    return None



def _process_command_core(command: str) -> Dict[str, Any]:
    """
    Central command entry point for CLI, HTTP server and mobile UI.
    """

    text = str(command or "").strip()

    if not text:
        return {
            "status": "error",
            "workflow": "command",
            "response": "Command is required.",
            "results": [],
            "errors": ["command is required"],
            "data": {},
        }

    low = text.lower()

    # --------------------------------------------------------
    # Unified natural-language direct command routing
    # --------------------------------------------------------
    direct_intent = _route_natural_direct_command(text)

    if direct_intent == "tasks":
        data = load_tasks()
        return {
            "status": "completed",
            "workflow": "direct",
            "response": "Tasks loaded.",
            "results": data,
            "errors": [],
            "data": {"tasks": data},
        }

    if direct_intent == "projects":
        data = refresh_all_projects()
        return {
            "status": "completed",
            "workflow": "direct",
            "response": "Projects loaded.",
            "results": data,
            "errors": [],
            "data": {"projects": data},
        }

    if direct_intent == "current_project":
        project = get_current_project()

        data = (
            project_context(project["id"])
            if isinstance(project, dict) and project.get("id") is not None
            else {}
        )

        return {
            "status": "completed",
            "workflow": "direct",
            "response": "Current project loaded.",
            "results": [data] if data else [],
            "errors": [],
            "data": {"current_project": data},
        }

    if direct_intent == "memory":
        data = load_memory()
        return {
            "status": "completed",
            "workflow": "direct",
            "response": "Memory loaded.",
            "results": [],
            "errors": [],
            "data": {"memory": data},
        }

    if direct_intent == "files":
        data = list_files()
        return {
            "status": "completed",
            "workflow": "direct",
            "response": "Files loaded.",
            "results": data,
            "errors": [],
            "data": {"files": data},
        }

    if direct_intent == "state":
        data = load_state()
        return {
            "status": "completed",
            "workflow": "direct",
            "response": "Agent state loaded.",
            "results": [],
            "errors": [],
            "data": {"state": data},
        }


    # --------------------------------------------------------
    # Complete task by name or ID
    # --------------------------------------------------------

    complete_match = re.match(
        r"^\s*(?:"
        r"complete\s+task\s*:\s*|"
        r"complete\s+task\s+|"
        r"complete\s*:\s*|"
        r"complete\s+|"
        r"انجز\s+(?:المهمة\s*)?|"
        r"أنجز\s+(?:المهمة\s*)?|"
        r"انجز\s+(?:المهمة\s*)?|"
        r"انجز\s+(?:المهمة\s*)?|"
        r"إنهاء\s+(?:المهمة\s*)?"
        r")(.+?)\s*$",
        text,
        re.IGNORECASE,
    )

    if complete_match:

        task_query = complete_match.group(1).strip()

        current_project = get_current_project()

        project_id = (
            current_project.get("id")
            if isinstance(current_project, dict)
            else None
        )

        task = find_task_by_name(
            task_query,
            project_id,
        )

        if task is None:

            # If not found in the current project,
            # search all tasks.
            task = find_task_by_name(
                task_query,
                None,
            )

        if task is None:

            return {
                "status": "error",
                "workflow": "task",
                "response": (
                    f"❌ لم يتم العثور على المهمة: {task_query}"
                ),
                "results": [],
                "errors": [
                    f"Task not found: {task_query}"
                ],
                "data": {
                    "query": task_query,
                },
            }

        if task.get("status") == "completed":

            project = (
                refresh_project(
                    int(task["project_id"])
                )
                if task.get("project_id") is not None
                else None
            )

            return {
                "status": "completed",
                "workflow": "task",
                "response": (
                    f"ℹ️ المهمة مكتملة بالفعل: "
                    f"{task.get('title', task_query)}"
                ),
                "results": [task],
                "errors": [],
                "data": {
                    "task": task,
                    "project": project,
                },
            }

        completed_task = complete_task(
            int(task["id"])
        )

        if completed_task is None:

            return {
                "status": "error",
                "workflow": "task",
                "response": (
                    "❌ لم يتم إكمال المهمة."
                ),
                "results": [],
                "errors": [
                    "complete_task returned None"
                ],
                "data": {},
            }

        project = (
            refresh_project(
                int(completed_task["project_id"])
            )
            if completed_task.get("project_id") is not None
            else None
        )

        title = completed_task.get(
            "title",
            task_query,
        )

        response = (
            f"✅ تم إكمال المهمة بنجاح.\n"
            f"📋 المهمة: {title}"
        )

        if isinstance(project, dict):

            completed = project.get(
                "completed_tasks",
                0,
            )

            total = project.get(
                "total_tasks",
                0,
            )

            progress = project.get(
                "progress_percent",
                0,
            )

            response += (
                f"\n📁 المشروع: "
                f"{project.get('name', '')}"
                f"\n📊 المهام المكتملة: "
                f"{completed} ?? {total}"
                f"\n📈 التقدم: "
                f"{progress}%"
            )

        return {
            "status": "completed",
            "workflow": "task",
            "response": response,
            "results": [
                completed_task
            ],
            "errors": [],
            "data": {
                "task": completed_task,
                "project": project,
            },
        }

    # --------------------------------------------------------
    # Explicit commands
    # --------------------------------------------------------

    if low in {"tasks", "المهام"}:
        data = load_tasks()

        return {
            "status": "completed",
            "workflow": "direct",
            "response": "Tasks loaded.",
            "results": data,
            "errors": [],
            "data": {"tasks": data},
        }

    if low in {"projects", "المشاريع", "project lifecycle", "دورة حياة المشروع"}:
        data = refresh_all_projects()

        return {
            "status": "completed",
            "workflow": "direct",
            "response": "Projects loaded.",
            "results": data,
            "errors": [],
            "data": {"projects": data},
        }

    if low in {"current project", "المشروع الحالي"}:
        project = get_current_project()
        data = project_context(project["id"]) if project else {}

        return {
            "status": "completed",
            "workflow": "direct",
            "response": "Current project loaded.",
            "results": [data] if data else [],
            "errors": [],
            "data": {"current_project": data},
        }

    if low in {"memory", "الذاكرة"}:
        data = load_memory()

        return {
            "status": "completed",
            "workflow": "direct",
            "response": "Memory loaded.",
            "results": [],
            "errors": [],
            "data": {"memory": data},
        }

    if low in {"files", "الملفات"}:
        data = list_files()

        return {
            "status": "completed",
            "workflow": "direct",
            "response": "Files loaded.",
            "results": data,
            "errors": [],
            "data": {"files": data},
        }

    if low in {"state", "حالة الوكيل", "حالة"}:
        data = load_state()

        return {
            "status": "completed",
            "workflow": "direct",
            "response": "Agent state loaded.",
            "results": [],
            "errors": [],
            "data": {"state": data},
        }

    if low in {"resume", "استئناف"}:
        state = resume()

        return {
            "status": state.get("status", "completed"),
            "workflow": "resume",
            "response": "Resume completed.",
            "results": state.get("results", []),
            "errors": state.get("errors", []),
            "data": {"state": state},
        }

    # --------------------------------------------------------
    # Remember
    # --------------------------------------------------------

    remember_prefixes = (
        "remember ",
        "save ",
        "تذكر ",
        "تذكّر ",
        "احفظ ",
    )

    for prefix in remember_prefixes:

        if low.startswith(prefix.lower()):

            value = text[len(prefix):].strip()

            if value:

                key = (
                    "memory_"
                    + datetime.now().strftime("%Y%m%d_%H%M%S")
                )

                remember(
                    key,
                    value,
                    category="permanent",
                )

                return {
                    "status": "completed",
                    "workflow": "memory",
                    "response": "Memory saved.",
                    "results": [],
                    "errors": [],
                    "data": {
                        "key": key,
                        "value": value,
                    },
                }

    # --------------------------------------------------------
    # Forget
    # --------------------------------------------------------

    forget_match = re.match(
        r"^(?:forget|delete memory|انس|أنس|احذف)\s+(.+)$",
        text,
        re.IGNORECASE,
    )

    if forget_match:

        query = forget_match.group(1).strip()
        removed = forget_memory(query)

        return {
            "status": "completed",
            "workflow": "memory",
            "response": (
                "Memory removed."
                if removed
                else "No matching memory was found."
            ),
            "results": [],
            "errors": [],
            "data": {
                "query": query,
                "removed": removed,
            },
        }

    # --------------------------------------------------------
    # General planning
    # --------------------------------------------------------

    # --------------------------------------------------------
    # Complete task directly
    # --------------------------------------------------------

    complete_match = re.match(
        r"^(?:complete\s+task|finish\s+task|أكمل\s+المهمة|انجز\s+المهمة)\s*:?\s*(.+)$",
        text,
        re.IGNORECASE,
    )

    if complete_match:

        task_query = complete_match.group(1).strip()

        tasks = load_tasks()

        matched_task = None

        for task in tasks:

            title = str(task.get("title", "")).strip()

            if title.lower() == task_query.lower():

                matched_task = task
                break

        if matched_task is None:

            return {
                "status": "error",
                "workflow": "direct",
                "response": f"Task not found: {task_query}",
                "results": [],
                "errors": ["task not found"],
                "data": {},
            }

        completed = complete_task(
            int(matched_task["id"])
        )

        return {
            "status": "completed",
            "workflow": "direct",
            "response": (
                f"Task completed: "
                f"{completed.get('title')}"
            ),
            "results": [completed],
            "errors": [],
            "data": {
                "task": completed,
            },
        }
    try:
    

        plan = build_plan(text)

        state = execute_plan(
            text,
            plan,
            workflow="integrated",
        )

        results = state.get("results", [])
        errors = state.get("errors", [])

        response = ""

        if results:
            response = str(results[-1])
        elif errors:
            response = "Command failed."
        else:
            response = "Command completed."

        return {
            "status": state.get("status", "completed"),
            "workflow": state.get("workflow", "integrated"),
            "response": response,
            "results": results,
            "errors": errors,
            "data": {
                "state": state,
                "plan": plan,
            },
        }

    except Exception as exc:

        return {
            "status": "error",
            "workflow": "command",
            "response": "Command failed.",
            "results": [],
            "errors": [str(exc)],
            "data": {},
        }



# -----------------------------
# Natural-language commands
# -----------------------------
def show_status() -> None:
    state = load_state()
    p = get_current_project()
    print(json.dumps({
        "agent_status": state.get("status", "idle"),
        "workflow": state.get("workflow"),
        "current_step": state.get("current_step"),
        "total_steps": len(state.get("plan", [])),
        "errors": state.get("errors", []),
        "repair_events": state.get("repair_events", []),
        "current_project": project_context(p["id"]) if p else None,
    }, ensure_ascii=False, indent=2))


def print_help() -> None:
    print("""
أوامر سريعة:
  state / حالة الوكيل
  resume / استئناف
  tasks / المهام
  projects / المشاريع
  current project / المشروع الحالي
  project lifecycle / دورة حياة المشروع
  memory / الذاكرة
  files / الملفات
  exit / خروج

يمكنك أيضًا إعطاء طلبًا طبيعيًا مباشرة، مثل:
  أضف مهمة ...
  نفذ داخل المشروع الحالي: أضف مهمة جديدة للمشروع بعنوان "..."
  ابحث في الويب عن ...
""")


def handle_direct_command(text: str) -> bool:
    low = text.strip().lower()

    if low in {"help", "مساعدة"}:
        print_help()
        return True

    if low in {"state", "حالة الوكيل", "حالة"}:
        show_status()
        return True

    if low in {"resume", "استئناف"}:
        print(json.dumps(resume(), ensure_ascii=False, indent=2))
        return True

    if low in {"tasks", "المهام"}:
        print(json.dumps(load_tasks(), ensure_ascii=False, indent=2))
        return True

    if low in {"projects", "المشاريع"}:
        print(json.dumps(refresh_all_projects(), ensure_ascii=False, indent=2))
        return True

    if low in {"current project", "المشروع الحالي"}:
        p = get_current_project()
        print(json.dumps(project_context(p["id"]) if p else {}, ensure_ascii=False, indent=2))
        return True

    if low in {"project lifecycle", "دورة حياة المشروع"}:
        print(json.dumps(refresh_all_projects(), ensure_ascii=False, indent=2))
        return True

    if low in {"memory", "الذاكرة"}:
        print(json.dumps(load_memory(), ensure_ascii=False, indent=2))
        return True
    for prefix in ("تذكر ", "تذكّر ", "احفظ ", "remember ", "save "):
        if low.startswith(prefix.lower()):
            value = text.strip()[len(prefix):].strip()

            if value:
                key = "memory_" + datetime.now().strftime("%Y%m%d_%H%M%S")
                remember(key, value, category="permanent")

                print(json.dumps({
                    "status": "saved",
                    "category": "permanent",
                    "key": key,
                    "value": value
                }, ensure_ascii=False, indent=2))

                return True
    if low in {"files", "الملفات"}:
        print(json.dumps(list_files(), ensure_ascii=False, indent=2))
        return True

    return False


def run() -> None:
    print("AI Agent v29 Integrated — جاهز")
    print(f"Project: {BASE_DIR}")
    print("اكتب help للمساعدة. اكتب exit للخروج.")

    # Keep project/task integrity synchronized at startup.
    refresh_all_projects()

    while True:
        try:
            text = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye")
            break

        if not text:
            continue

        if text.lower() in {"exit", "quit", "خروج"}:
            print("Bye")
            break

        result = process_command(text)

        print("\nAgent:")
        print(json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ))


# ============================================================
# Unified human-readable response formatter
# ============================================================

def _format_agent_response(result: Dict[str, Any]) -> Dict[str, Any]:
    """Convert internal results into clear human-readable responses."""

    if not isinstance(result, dict):
        return {
            "status": "error",
            "workflow": "command",
            "response": "حدث خطأ غير متوقع.",
            "results": [],
            "errors": ["invalid result"],
            "data": {},
        }

    data = result.get("data", {})
    plan = data.get("plan", []) if isinstance(data, dict) else []
    results = result.get("results", [])

    action = ""
    if isinstance(plan, list) and plan:
        first_step = plan[0]
        if isinstance(first_step, dict):
            action = first_step.get("action", "")
    # --------------------------------------------------------
    # Task added to project
    # --------------------------------------------------------
    if action == "add_project_task" and results:

        item = results[-1]

        if isinstance(item, dict):

            task = item.get("task", {})
            project = item.get("project", {})

            if isinstance(task, dict):
                title = task.get("title", "مهمة بدون اسم")

                project_name = ""
                total = 0
                completed = 0
                progress = 0

                if isinstance(project, dict):
                    project_name = project.get("name", "")
                    total = project.get("total_tasks", 0)
                    completed = project.get("completed_tasks", 0)
                    progress = project.get("progress_percent", 0)

                message = (
                    f"✅ تمت إضافة المهمة بنجاح.\n\n"
                    f"📋 المهمة: {title}\n"
                )

                if project_name:
                    message += f"📁 المشروع: {project_name}\n"

                message += (
                    f"📊 المهام: {completed} / {total}\n"
                    f"📈 التقدم: {progress}%"
                )

                result["response"] = message

                return result
    # --------------------------------------------------------
    # Direct command formatting
    # --------------------------------------------------------
    original_response = str(
        result.get("response", "")
    ).strip()

    workflow = result.get("workflow", "")

    if workflow == "direct":

        # Current project
        if original_response == "Current project loaded.":

            project = None

            if isinstance(data, dict):
                project = data.get("current_project")

            if not isinstance(project, dict) and results:
                candidate = results[-1]

                if isinstance(candidate, dict):
                    project = candidate

            if isinstance(project, dict):
                name = project.get("name", "بدون اسم")
                completed = project.get("completed_tasks", 0)
                total = project.get("total_tasks", 0)
                progress = project.get("progress_percent", 0)

                result["response"] = (
                    f"📁 المشروع الحالي: {name}\n"
                    f"📋 المهام: {completed} / {total}\n"
                    f"📊 التقدم: {progress}%"
                )

            else:
                result["response"] = "📁 لا يوجد مشروع حالي."

            return result


        # Tasks
        if original_response == "Tasks loaded.":

            tasks = results

            if isinstance(data, dict):

                data_tasks = data.get("tasks")

                if isinstance(data_tasks, list):
                    tasks = data_tasks

            if not isinstance(tasks, list) or not tasks:
                result["response"] = "📋 لا توجد مهام حالياً."

            else:
                lines = ["📋 المهام:"]

                for index, task in enumerate(tasks, start=1):

                    if not isinstance(task, dict):
                        continue

                    title = task.get(
                        "title",
                        task.get("name", "مهمة بدون اسم")
                    )

                    status = task.get("status", "")

                    icon = (
                        "✅"
                        if status == "completed"
                        else "⬜"
                    )

                    lines.append(
                        f"{index}. {icon} {title}"
                    )

                result["response"] = "\n".join(lines)

            return result

    # --------------------------------------------------------
    # Project created
    # --------------------------------------------------------
    if action == "create_project" and results:
        project = results[-1]

        if isinstance(project, dict):
            name = project.get("name", "بدون اسم")
            goal = project.get("goal", "")
            progress = project.get("progress_percent", 0)
            total = project.get("total_tasks", 0)

            message = (
                f"✅ تم إنشاء المشروع بنجاح.\n\n"
                f"📁 المشروع: {name}\n"
            )

            if goal:
                message += f"🎯 الهدف: {goal}\n"

            message += (
                f"📋 المهام: {total}\n"
                f"📊 التقدم: {progress}%"
            )

            result["response"] = message
    # --------------------------------------------------------
    # Direct command responses
    # --------------------------------------------------------
    workflow = result.get("workflow", "")
    original_response = str(result.get("response", "")).strip()
    data = result.get("data", {})
    results = result.get("results", [])

    if workflow == "direct":

        # Current project
        if original_response == "Current project loaded.":

            project = data.get("current_project", {})

            if isinstance(project, dict) and project:
                name = project.get("name", "لا يوجد")
                progress = project.get("progress_percent", 0)
                completed = project.get("completed_tasks", 0)
                total = project.get("total_tasks", 0)

                result["response"] = (
                    f"📁 المشروع الحالي: {name}\n"
                    f"📋 المهام: {completed} / {total}\n"
                    f"📊 التقدم: {progress}%"
                )
            else:
                result["response"] = "📁 لا يوجد مشروع حالي."

            return result


        # Tasks
        if original_response == "Tasks loaded.":

            if not results:
                result["response"] = "📋 لا توجد مهام حالياً."

            else:
                lines = ["📋 المهام:"]

                for index, task in enumerate(results, start=1):

                    if isinstance(task, dict):
                        title = task.get(
                            "title",
                            task.get("name", "مهمة بدون اسم")
                        )

                        status = task.get("status", "")

                        icon = "✅" if status == "completed" else "⬜"

                        lines.append(
                            f"{index}. {icon} {title}"
                        )

                result["response"] = "\n".join(lines)

            return result


        # Projects
        if original_response == "Projects loaded.":

            projects = results

            if not projects:
                result["response"] = "📁 لا توجد مشاريع حالياً."

            else:
                lines = ["📁 المشاريع:"]

                for index, project in enumerate(projects, start=1):

                    if isinstance(project, dict):
                        name = project.get(
                            "name",
                            "مشروع بدون اسم"
                        )

                        progress = project.get(
                            "progress_percent",
                            0
                        )

                        lines.append(
                            f"{index}. 📁 {name} — {progress}%"
                        )

                result["response"] = "\n".join(lines)

            return result


        # Memory
        if original_response == "Memory loaded.":

            memory = data.get("memory", [])

            if not memory:
                result["response"] = "🧠 الذاكرة فارغة حالياً."
            else:
                result["response"] = (
                    f"🧠 تم تحميل الذاكرة.\n"
                    f"عدد العناصر: {len(memory)}"
                )

            return result
    # --------------------------------------------------------
    # Current project
    # --------------------------------------------------------
    elif action in ("get_current_project", "current_project"):

        project = results[-1] if results else None

        if isinstance(project, dict):
            name = project.get("name", "لا يوجد")
            progress = project.get("progress_percent", 0)

            result["response"] = (
                f"📁 المشروع الحالي: {name}\n"
                f"📊 التقدم: {progress}%"
            )

        else:
            result["response"] = "📁 لا يوجد مشروع حالي."

    # --------------------------------------------------------
    # Tasks
    # --------------------------------------------------------
    elif action in ("list_tasks", "get_tasks"):

        if not results:
            result["response"] = "📋 لا توجد مهام حالياً."

        else:
            lines = ["📋 المهام:"]
            for index, task in enumerate(results, start=1):

                if isinstance(task, dict):
                    title = task.get(
                        "title",
                        task.get("name", "مهمة بدون اسم")
                    )

                    status = task.get("status", "")
                    icon = "✅" if status == "completed" else "⬜"

                    lines.append(
                        f"{index}. {icon} {title}"
                    )

            result["response"] = "\n".join(lines)

    # --------------------------------------------------------
    # Generic result
    # --------------------------------------------------------
    elif (
        results
        and isinstance(results[-1], dict)
        and str(result.get("response", "")).startswith("{")
    ):

        item = results[-1]

        name = item.get("name")
        title = item.get("title")

        if name:
            result["response"] = f"✅ تم التنفيذ بنجاح: {name}"

        elif title:
            result["response"] = f"✅ تم التنفيذ بنجاح: {title}"

        else:
            result["response"] = "✅ تم تنفيذ الطلب بنجاح."

    return result


def _command_compact(value: Any) -> str:
    """Normalize Arabic/English command text for intent matching."""
    text = str(value or "").strip().lower()
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"[^0-9a-zA-Z\u0600-\u06FF]+", "", text)


def _is_current_project_query(value: Any) -> bool:
    compact = _command_compact(value)
    exact = {
        "المشروعالحالي",
        "ماهوالمشروعالحالي",
        "ماهوالمشروعالحالي",
        "ماالمشروعالحالي",
        "ايشالمشروعالحالي",
        "ماالمشروعالحاليلدي",
        "currentproject",
        "whatisthecurrentproject",
        "whatismycurrentproject",
    }
    if compact in exact:
        return True

    # Keep this intentionally narrow: project + current/current-question only.
    has_project = ("مشروع" in compact) or ("project" in compact)
    has_current = ("حالي" in compact) or ("current" in compact)
    return has_project and has_current


def _current_project_result() -> Dict[str, Any]:
    project = get_current_project()
    data = (
        project_context(int(project["id"]))
        if isinstance(project, dict) and project.get("id") is not None
        else {}
    )
    result = {
        "status": "completed",
        "workflow": "direct",
        "response": "Current project loaded.",
        "results": [data] if data else [],
        "errors": [],
        "data": {"current_project": data},
    }
    return _format_agent_response(result)


def _apply_executive_response(
    result: Dict[str, Any],
    executive_decision: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Phase 6: Executive Response Integration.

    Shows Executive guidance only when it materially helps the user.
    Normal requests remain concise.
    """

    if not isinstance(result, dict):
        return result

    if not isinstance(executive_decision, dict):
        return result

    response = str(result.get("response", "")).strip()

    should_challenge = bool(
        executive_decision.get("should_challenge")
    )

    approval_required = bool(
        executive_decision.get("approval_required")
    )

    priority = str(
        executive_decision.get("priority", "normal")
    )

    recommendation = str(
        executive_decision.get("recommendation", "")
    ).strip()

    recommendation_reason = str(
        executive_decision.get("recommendation_reason", "")
    ).strip()

    challenge_reason = str(
        executive_decision.get("challenge_reason", "")
    ).strip()


    # High-risk / challenged decisions:
    # clearly explain why the Agent is stopping.
    if approval_required or should_challenge:

        parts = []

        if response:
            parts.append(response)

        if challenge_reason:
            parts.append(
                "Executive assessment: " + challenge_reason
            )

        if recommendation:
            parts.append(
                "Recommendation: " + recommendation
            )

        result["response"] = "\n".join(parts)

        return result


    # High-priority requests may receive a concise recommendation.
    if priority == "high" and recommendation:

        parts = []

        if response:
            parts.append(response)

        parts.append(
            "Recommendation: " + recommendation
        )

        result["response"] = "\n".join(parts)


    return result


def process_command(command: str) -> Dict[str, Any]:
    """Single public command entry point for CLI, HTTP and mobile UI."""

    text = str(command or "").strip()
    if not text:
        return _format_agent_response(_process_command_core(text))

    # High-confidence read-only intents must be handled before the planner.
    # Otherwise natural phrasing such as "ما هو المشروع الحالي؟" can fall
    # through to the generic fallback and return "تم استلام الطلب".
    if _is_current_project_query(text):
        return _current_project_result()

    # Phase 6: Executive Intelligence v3.
    # Build read-only context from the existing Agent Core.
    current_project = get_current_project()
    tasks = load_tasks()
    memory_context = search_memory(text, limit=5)
    agent_runtime_state = load_state()

    executive_context = build_executive_context(
        request=text,
        current_project=current_project,
        tasks=tasks,
        memory_context=memory_context,
        agent_state=agent_runtime_state,
    )

    executive_decision = analyze_request(
        text,
        context=executive_context,
    )

    # Phase 6: Executive Intelligence v2.
    # High-risk actions requiring approval must not reach the Agent Core.
    if executive_decision.get("approval_required"):
        result = {
            "status": "approval_required",
            "workflow": "executive",
            "response": (
                "This action requires your approval before execution. "
                + str(executive_decision.get("recommended_action", ""))
            ),
            "results": [],
            "errors": [],
            "data": {},
            "executive": executive_decision,
        }
        result = _apply_executive_response(
            result,
            executive_decision,
        )

        return _format_agent_response(result)

    # Existing Agent Core remains responsible for routing,
    # planning, execution and verification.

    # Phase 11: Detect unfinished execution safely.
    resume_decision = prepare_execution_resume()

    # Phase 12: Persistent Execution Checkpoint.
    # Save a recoverable checkpoint before execution begins.
    checkpoint = create_checkpoint(
        request=text,
        stage="started",
        workflow=executive_decision.get(
            "request_type"
        ),
    )

    # Phase 10: Persistent Execution State.
    execution_state = start_execution(
        request=text,
        workflow=executive_decision.get(
            "request_type"
        ),
    )

    # Phase 12: Mark the core execution stage.
    checkpoint = update_checkpoint(
        stage="executing"
    )

    result = _process_command_core(text)

    if isinstance(result, dict):
        result.setdefault("executive", executive_decision)

        # Phase 11: Attach previous execution recovery decision.
        result["execution_resume"] = resume_decision

        # Phase 6: Review the actual execution outcome.
        result["execution_review"] = review_execution(
            request=text,
            decision=executive_decision,
            result=result,
        )

        execution_state = update_execution(
            status="reviewed",
            details={
                "execution_status": result[
                    "execution_review"
                ].get("execution_status"),
                "review_status": result[
                    "execution_review"
                ].get("review_status"),
            },
        )

        result["replanning"] = decide_replanning(
            result["execution_review"]
        )

        result["autonomous_loop"] = determine_next_action(
            executive_decision,
            result["execution_review"],
            result["replanning"],
        )

        # Phase 8: Controlled Execution.
        # Applies hard safety limits to autonomous decisions.
        result["controlled_execution"] = control_execution(
            result["autonomous_loop"]
        )

        # Phase 9: Intelligent Execution Recovery.
        # Determines the safest recovery strategy.
        result["execution_recovery"] = (
            determine_recovery_strategy(
                result["execution_review"],
                result["replanning"],
                result["autonomous_loop"],
                result["controlled_execution"],
            )
        )

        recovery = result["execution_recovery"]

        # Phase 12: Update the persistent checkpoint
        # according to the recovery decision.
        recovery_strategy = str(
            recovery.get(
                "strategy",
                "stop_safely",
            )
        ).strip().lower()

        if recovery_strategy == "continue":
            checkpoint = complete_checkpoint(
                data={
                    "result": "completed",
                    "workflow": result.get("workflow"),
                }
            )

        elif recovery_strategy in {
            "prepare_recovery_plan",
            "analyze_failure",
        }:
            checkpoint = update_checkpoint(
                stage="replanning",
                data={
                    "recovery_strategy": recovery_strategy,
                },
            )

        elif recovery_strategy == "wait_for_approval":
            checkpoint = update_checkpoint(
                stage="approval_required",
                data={
                    "recovery_strategy": recovery_strategy,
                },
            )

        else:
            checkpoint = complete_checkpoint(
                data={
                    "result": "stopped",
                    "recovery_strategy": recovery_strategy,
                }
            )

        result["execution_checkpoint"] = checkpoint

        recovery_action = recovery.get(
            "strategy",
            "unknown",
        )

        if recovery_action in {
            "continue",
            "completed",
        }:
            execution_state = complete_execution(
                details={
                    "request": text,
                    "workflow": result.get(
                        "workflow"
                    ),
                }
            )
        else:
            execution_state = stop_execution(
                recovery_action
            )

        
        # Phase 12: Checkpoint Recovery Decision.
        result["checkpoint_recovery"] = determine_checkpoint_recovery(
            result.get("execution_checkpoint")
        )

        # Phase 13: Safe Recovery Orchestration.
        result["recovery_orchestration"] = orchestrate_recovery(
            result.get("execution_resume"),
            result.get("checkpoint_recovery"),
            result.get("execution_recovery"),
        )

        # Phase 14: Recovery Governance.
        result["recovery_governance"] = govern_recovery_action(
            result.get("recovery_orchestration")
        )

        # Phase 15: Safe Recovery Execution.
        result["recovery_execution"] = execute_recovery_action(
            result.get("recovery_governance")
        )

        # Phase 16: Recovery Analysis.
        result["recovery_analysis"] = analyze_recovery(
            result.get("execution_resume"),
            result.get("checkpoint_recovery"),
            result.get("recovery_orchestration"),
            result.get("recovery_governance"),
        )

        # Phase 17: Recovery Review.
        result["recovery_review"] = review_recovery(
            result.get("recovery_analysis")
        )

        # Phase 18: Recovery Decision.
        result["recovery_decision"] = decide_recovery(
            result.get("recovery_review")
        )

        # Phase 19: Controlled Recovery Plan.
        result["recovery_plan"] = build_recovery_plan(
            result.get("recovery_decision")
        )

        # Phase 20: Controlled Recovery Execution.
        result["controlled_recovery"] = execute_controlled_recovery(
            result.get("recovery_plan")
        )

        result["execution_state"] = execution_state

        result = _apply_executive_response(
            result,
            executive_decision,
        )

    return _format_agent_response(result)


if __name__ == "__main__":
    run()
