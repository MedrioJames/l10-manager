"""To-Do tracking - the data layer behind the To-Do List segment type (see
segment_types.py's TodoType). Deliberately simple, matching EOS's own
practice: no due dates, no priority - just a title, an optional assignee,
and done/not-done. To-dos carry forward automatically every week until
marked done (rather than being scoped to "only last week's"), since that
matches real EOS practice better and avoids needing to resolve "the
previous occurrence" of a repeating instance.

Todos live in Data/todos.json, mirroring issues.py's exact shape/pattern -
same atomic_write_json/load_json_with_fallback persistence, same
load/save/delete/list function shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import config as cfgmod
import schedule as sch

TODOS_FILENAME = "todos.json"


def _todos_path() -> Path:
    return cfgmod.data_dir() / TODOS_FILENAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Todo:
    id: str = field(default_factory=sch.new_id)
    title: str = ""
    assignee_id: Optional[str] = None
    repeating_instance_id: Optional[str] = None  # which recurring meeting this belongs to
    done: bool = False
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "assignee_id": self.assignee_id,
            "repeating_instance_id": self.repeating_instance_id,
            "done": self.done,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(d: dict) -> "Todo":
        return Todo(
            id=d.get("id", sch.new_id()),
            title=d.get("title", ""),
            assignee_id=d.get("assignee_id"),
            repeating_instance_id=d.get("repeating_instance_id"),
            done=bool(d.get("done", False)),
            created_at=d.get("created_at") or _now_iso(),
            updated_at=d.get("updated_at") or _now_iso(),
        )


def load_todos() -> Dict[str, Todo]:
    data = cfgmod.load_json_with_fallback(_todos_path())
    if data is None:
        return {}
    try:
        return {key: Todo.from_dict(value) for key, value in data.items()}
    except (ValueError, KeyError) as exc:
        raise cfgmod.DataLoadError(_todos_path()) from exc


def save_todos(todos: Dict[str, Todo]) -> None:
    payload = {key: todo.to_dict() for key, todo in todos.items()}
    cfgmod.atomic_write_json(_todos_path(), payload)


def save_todo(todo: Todo) -> None:
    todos = load_todos()
    todo.updated_at = _now_iso()
    todos[todo.id] = todo
    save_todos(todos)


def delete_todo(todo_id: str) -> None:
    todos = load_todos()
    if todo_id in todos:
        del todos[todo_id]
        save_todos(todos)


def get_todo(todo_id: str) -> Optional[Todo]:
    return load_todos().get(todo_id)


def list_todos(repeating_instance_id: Optional[str] = None, include_done: bool = False) -> List[Todo]:
    todos = list(load_todos().values())
    if repeating_instance_id is not None:
        todos = [t for t in todos if t.repeating_instance_id == repeating_instance_id]
    if not include_done:
        todos = [t for t in todos if not t.done]
    todos.sort(key=lambda t: t.created_at)
    return todos
