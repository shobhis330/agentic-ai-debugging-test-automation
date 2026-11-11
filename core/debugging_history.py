
import json
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HISTORY_FILE = PROJECT_ROOT / "data" / "debugging_history.json"


def _load_history():
    if not HISTORY_FILE.exists():
        return []

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def get_history():
    """Return debugging records, newest first."""
    return sorted(
        _load_history(),
        key=lambda item: item.get("timestamp", ""),
        reverse=True
    )


def add_history_entry(
    file_name,
    status,
    issue="",
    original_code="",
    corrected_code="",
    test_summary="",
    details=""
):
    """Save one debugging session locally."""
    history = _load_history()

    entry = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "file_name": str(file_name),
        "status": str(status),
        "issue": str(issue),
        "original_code": str(original_code),
        "corrected_code": str(corrected_code),
        "test_summary": str(test_summary),
        "details": str(details)
    }

    history.append(entry)
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(history, file, indent=4, ensure_ascii=False)

    return entry


def delete_history_entry(entry_id):
    history = _load_history()
    updated = [item for item in history if item.get("id") != entry_id]
    _save_history(updated)


def clear_history():
    _save_history([])


def _save_history(history):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(history, file, indent=4, ensure_ascii=False)


def get_history_summary():
    history = get_history()

    return {
        "total": len(history),
        "successful": sum(
            1 for item in history
            if item.get("status", "").lower() in ("success", "fixed", "passed")
        ),
        "failed": sum(
            1 for item in history
            if item.get("status", "").lower() in ("failed", "error")
        )
    }
