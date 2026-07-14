"""
Review Queue — persistent storage for items awaiting human review.

This is the missing piece between "the orchestrator produced a result"
and "a human can actually see and act on it." Stored as a simple JSON
file — good enough for a single-firm demo; a real deployment would use
a real database, but the interface (add/list/update) would stay the same.
"""

import json
import os
import uuid
from datetime import datetime, timezone

QUEUE_PATH = os.path.join(os.path.dirname(__file__), "review_queue.json")


def _load() -> list:
    if not os.path.exists(QUEUE_PATH):
        return []
    with open(QUEUE_PATH) as f:
        return json.load(f)


def _save(items: list):
    with open(QUEUE_PATH, "w") as f:
        json.dump(items, f, indent=2, default=str)


def add_item(orchestrator_result: dict) -> str:
    """Adds a new orchestrator result to the queue. Returns the item's id."""
    items = _load()
    item_id = str(uuid.uuid4())[:8]
    items.append({
        "id": item_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",  # pending -> approved | rejected | edited
        "reviewed_at": None,
        "result": orchestrator_result,
    })
    _save(items)
    return item_id


def list_items(status: str = None) -> list:
    """status=None returns all items; otherwise filters (e.g. 'pending')."""
    items = _load()
    if status:
        return [i for i in items if i["status"] == status]
    return items


def update_status(item_id: str, new_status: str, note: str = ""):
    items = _load()
    for item in items:
        if item["id"] == item_id:
            item["status"] = new_status
            item["reviewed_at"] = datetime.now(timezone.utc).isoformat()
            item["review_note"] = note
            break
    _save(items)


def clear_queue():
    """Wipes the queue — useful for resetting between demo runs."""
    _save([])
