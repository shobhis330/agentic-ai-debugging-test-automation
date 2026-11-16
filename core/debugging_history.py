"""Persistent debugging-session history for DebugEngage AI."""

import json
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HISTORY_FILE = PROJECT_ROOT / "data" / "debugging_history.json"

SUCCESS_STATUSES = {"success", "fixed", "passed"}
FAILED_STATUSES = {"failed", "error"}
PENDING_STATUSES = {
    "bug_found",
    "no_bug_found",
    "pending",
    "in_progress",
    "insufficient_information",
    "environment_issue",
    "review_required",
    "review_unavailable",
}

STATUS_LABELS = {
    "success": "Validated Successfully",
    "fixed": "Fixed",
    "passed": "Passed",
    "failed": "Failed",
    "error": "Error",
    "bug_found": "Bug Found — Fix Pending",
    "no_bug_found": "No Bug Found — Validation Pending",
    "pending": "Pending",
    "in_progress": "In Progress",
    "insufficient_information": "Needs More Information",
    "environment_issue": "Environment Issue",
    "review_required": "Review Required",
    "review_unavailable": "AI Review Unavailable",
}


def _load_history():
    if not HISTORY_FILE.exists():
        return []
    try:
        with HISTORY_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_history(history):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = HISTORY_FILE.with_suffix(HISTORY_FILE.suffix + ".tmp")
    with temporary_file.open("w", encoding="utf-8") as file:
        json.dump(history, file, indent=4, ensure_ascii=False)
    temporary_file.replace(HISTORY_FILE)


def get_history():
    """Return valid debugging records, newest first."""
    return sorted(
        _load_history(),
        key=lambda item: item.get("timestamp", ""),
        reverse=True,
    )


def add_history_entry(
    file_name,
    status,
    issue="",
    original_code="",
    corrected_code="",
    test_summary="",
    details="",
):
    """Save a new debugging session and return the stored record."""
    now = datetime.now()
    entry = {
        "id": now.strftime("%Y%m%d%H%M%S%f"),
        "timestamp": now.isoformat(timespec="seconds"),
        "file_name": str(file_name),
        "status": str(status).strip().lower(),
        "issue": str(issue),
        "original_code": str(original_code),
        "corrected_code": str(corrected_code),
        "test_summary": str(test_summary),
        "details": str(details),
    }
    history = _load_history()
    history.append(entry)
    _save_history(history)
    return entry


def update_history_entry(entry_id, **changes):
    """Update an existing record without creating a duplicate."""
    allowed = {
        "status", "issue", "test_summary", "details", "corrected_code"
    }
    history = _load_history()
    for item in history:
        if item.get("id") == entry_id:
            for key, value in changes.items():
                if key in allowed:
                    item[key] = str(value).strip().lower() if key == "status" else str(value)
            _save_history(history)
            return True
    return False


def delete_history_entry(entry_id):
    history = _load_history()
    updated = [item for item in history if item.get("id") != entry_id]
    if len(updated) != len(history):
        _save_history(updated)
        return True
    return False


def clear_history():
    _save_history([])


def get_status_label(status):
    """Return a readable label while preserving the stored status value."""
    normalized = str(status or "unknown").strip().lower()
    return STATUS_LABELS.get(normalized, normalized.replace("_", " ").title())


def get_history_summary():
    """Summarize sessions without treating bug detection as a completed fix."""
    history = get_history()
    statuses = [str(item.get("status", "unknown")).strip().lower() for item in history]
    return {
        "total": len(history),
        "successful": sum(status in SUCCESS_STATUSES for status in statuses),
        "failed": sum(status in FAILED_STATUSES for status in statuses),
        "pending": sum(status in PENDING_STATUSES for status in statuses),
        "unclassified": sum(
            status not in SUCCESS_STATUSES
            and status not in FAILED_STATUSES
            and status not in PENDING_STATUSES
            for status in statuses
        ),
    }
