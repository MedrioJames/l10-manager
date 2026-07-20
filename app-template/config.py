"""Meeting configuration, repeating instances, and occurrence persistence.

Everything here lives in Data/ (never touched by app updates - see
CLAUDE.md). Two files:
  Data/config.json       - meeting info, repeating instances, schedule templates
  Data/occurrences.json  - per-occurrence customization (overrides, one-offs)

Repeating instances describe a recurring meeting (e.g. "Weekly Leadership
Sync"); the recurrence rule generates occurrence *dates* on the fly, so most
occurrences have no stored record at all. A record only exists once someone
customizes that occurrence's schedule, renames it, or creates a standalone
one-off meeting that isn't tied to any repeating instance.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import recurrence as rec
import schedule as sch

CONFIG_FILENAME = "config.json"
OCCURRENCES_FILENAME = "occurrences.json"


def data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "Data"


def _config_path() -> Path:
    return data_dir() / CONFIG_FILENAME


def _occurrences_path() -> Path:
    return data_dir() / OCCURRENCES_FILENAME


@dataclass
class MeetingInfo:
    name: str = ""
    description: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "description": self.description}

    @staticmethod
    def from_dict(d: dict) -> "MeetingInfo":
        return MeetingInfo(name=d.get("name", ""), description=d.get("description", ""))


@dataclass
class RepeatingInstance:
    id: str = field(default_factory=sch.new_id)
    name: str = ""
    description: str = ""
    default_length_minutes: int = 90
    recurrence: rec.RecurrenceRule = field(default_factory=rec.RecurrenceRule)
    schedule_template_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "default_length_minutes": self.default_length_minutes,
            "recurrence": self.recurrence.to_dict(),
            "schedule_template_id": self.schedule_template_id,
        }

    @staticmethod
    def from_dict(d: dict) -> "RepeatingInstance":
        return RepeatingInstance(
            id=d.get("id", sch.new_id()),
            name=d.get("name", ""),
            description=d.get("description", ""),
            default_length_minutes=int(d.get("default_length_minutes", 90)),
            recurrence=rec.RecurrenceRule.from_dict(d.get("recurrence", {})) if d.get("recurrence") else rec.RecurrenceRule(),
            schedule_template_id=d.get("schedule_template_id"),
        )


@dataclass
class Person:
    id: str = field(default_factory=sch.new_id)
    name: str = ""
    email: str = ""
    jira_account_id: str = ""  # maps assignments to Jira on sync, if linked

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "jira_account_id": self.jira_account_id,
        }

    @staticmethod
    def from_dict(d: dict) -> "Person":
        return Person(
            id=d.get("id", sch.new_id()),
            name=d.get("name", ""),
            email=d.get("email", ""),
            jira_account_id=d.get("jira_account_id", ""),
        )


@dataclass
class JiraConfig:
    """Non-secret Jira connection settings. The API token is deliberately
    NOT stored here - see credential_store.py. This file lives in Data/,
    which is designed to be shared with teammates for coverage; a token
    would leak to anyone who opens that folder.

    status_mapping maps a raw Jira status name (e.g. "In Review") to one of
    our local Status ids - Jira workflows are custom per project, so this
    can't be hardcoded. New Jira statuses encountered during sync get a
    best-effort default mapping auto-added here for the user to correct in
    Settings, rather than sync silently guessing forever.
    """
    enabled: bool = False
    base_url: str = ""
    email: str = ""
    project_key: str = ""
    project_name: str = ""
    status_mapping: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "base_url": self.base_url,
            "email": self.email,
            "project_key": self.project_key,
            "project_name": self.project_name,
            "status_mapping": dict(self.status_mapping),
        }

    @staticmethod
    def from_dict(d: dict) -> "JiraConfig":
        return JiraConfig(
            enabled=bool(d.get("enabled", False)),
            base_url=d.get("base_url", ""),
            email=d.get("email", ""),
            project_key=d.get("project_key", ""),
            project_name=d.get("project_name", ""),
            status_mapping=dict(d.get("status_mapping", {})),
        )


@dataclass
class Column:
    """A board column. Multiple Statuses can share a column - dragging a
    card onto a column with more than one Status requires the UI to ask
    which one was intended (see ui/issue_board.py)."""
    id: str = field(default_factory=sch.new_id)
    name: str = ""
    order: int = 0

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "order": self.order}

    @staticmethod
    def from_dict(d: dict) -> "Column":
        return Column(id=d.get("id", sch.new_id()), name=d.get("name", ""), order=int(d.get("order", 0)))


@dataclass
class Status:
    """column_id of None means this status is hidden from the board
    entirely (just counted) - this replaces the old hardcoded 'Dropped'
    special case with something any custom status can opt into."""
    id: str = field(default_factory=sch.new_id)
    name: str = ""
    column_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "column_id": self.column_id}

    @staticmethod
    def from_dict(d: dict) -> "Status":
        return Status(id=d.get("id", sch.new_id()), name=d.get("name", ""), column_id=d.get("column_id"))


# Fixed ids (not random) so existing Data/issues.json entries created before
# custom statuses existed keep resolving correctly - the default seed below
# uses the exact same ids the old hardcoded STATUS_OPEN/STATUS_IN_PROGRESS/
# STATUS_SOLVED/STATUS_DROPPED constants used.
DEFAULT_STATUS_OPEN_ID = "open"
DEFAULT_STATUS_IN_PROGRESS_ID = "in_progress"
DEFAULT_STATUS_SOLVED_ID = "solved"
DEFAULT_STATUS_DROPPED_ID = "dropped"


def default_columns() -> List[Column]:
    return [
        Column(id="col_open", name="Open", order=0),
        Column(id="col_progress", name="In Progress", order=1),
        Column(id="col_solved", name="Solved", order=2),
    ]


def default_statuses() -> List[Status]:
    return [
        Status(id=DEFAULT_STATUS_OPEN_ID, name="Open", column_id="col_open"),
        Status(id=DEFAULT_STATUS_IN_PROGRESS_ID, name="In Progress", column_id="col_progress"),
        Status(id=DEFAULT_STATUS_SOLVED_ID, name="Solved", column_id="col_solved"),
        Status(id=DEFAULT_STATUS_DROPPED_ID, name="Dropped", column_id=None),
    ]


@dataclass
class BoardDisplaySettings:
    show_status: bool = True
    show_description: bool = False
    show_assignee: bool = True

    def to_dict(self) -> dict:
        return {
            "show_status": self.show_status,
            "show_description": self.show_description,
            "show_assignee": self.show_assignee,
        }

    @staticmethod
    def from_dict(d: dict) -> "BoardDisplaySettings":
        return BoardDisplaySettings(
            show_status=bool(d.get("show_status", True)),
            show_description=bool(d.get("show_description", False)),
            show_assignee=bool(d.get("show_assignee", True)),
        )


@dataclass
class MeetingConfig:
    meeting: MeetingInfo = field(default_factory=MeetingInfo)
    repeating_instances: List[RepeatingInstance] = field(default_factory=list)
    schedule_templates: List[sch.ScheduleTemplate] = field(default_factory=lambda: [sch.default_template()])
    people: List[Person] = field(default_factory=list)
    jira: JiraConfig = field(default_factory=JiraConfig)
    columns: List[Column] = field(default_factory=default_columns)
    statuses: List[Status] = field(default_factory=default_statuses)
    board_display: BoardDisplaySettings = field(default_factory=BoardDisplaySettings)
    onboarded: bool = False

    def to_dict(self) -> dict:
        return {
            "meeting": self.meeting.to_dict(),
            "repeating_instances": [r.to_dict() for r in self.repeating_instances],
            "schedule_templates": [t.to_dict() for t in self.schedule_templates],
            "people": [p.to_dict() for p in self.people],
            "jira": self.jira.to_dict(),
            "columns": [c.to_dict() for c in self.columns],
            "statuses": [s.to_dict() for s in self.statuses],
            "board_display": self.board_display.to_dict(),
            "onboarded": self.onboarded,
        }

    @staticmethod
    def from_dict(d: dict) -> "MeetingConfig":
        templates = [sch.ScheduleTemplate.from_dict(t) for t in d.get("schedule_templates", [])]
        columns = [Column.from_dict(c) for c in d.get("columns", [])]
        statuses = [Status.from_dict(s) for s in d.get("statuses", [])]
        return MeetingConfig(
            meeting=MeetingInfo.from_dict(d.get("meeting", {})),
            repeating_instances=[RepeatingInstance.from_dict(r) for r in d.get("repeating_instances", [])],
            schedule_templates=templates or [sch.default_template()],
            people=[Person.from_dict(p) for p in d.get("people", [])],
            jira=JiraConfig.from_dict(d.get("jira", {})),
            columns=columns or default_columns(),
            statuses=statuses or default_statuses(),
            board_display=BoardDisplaySettings.from_dict(d.get("board_display", {})),
            onboarded=bool(d.get("onboarded", False)),
        )

    def find_template(self, template_id: Optional[str]) -> Optional[sch.ScheduleTemplate]:
        if not template_id:
            return None
        return next((t for t in self.schedule_templates if t.id == template_id), None)

    def find_instance(self, instance_id: Optional[str]) -> Optional[RepeatingInstance]:
        if not instance_id:
            return None
        return next((r for r in self.repeating_instances if r.id == instance_id), None)

    def find_person(self, person_id: Optional[str]) -> Optional[Person]:
        if not person_id:
            return None
        return next((p for p in self.people if p.id == person_id), None)

    def find_status(self, status_id: Optional[str]) -> Optional[Status]:
        if not status_id:
            return None
        return next((s for s in self.statuses if s.id == status_id), None)

    def find_column(self, column_id: Optional[str]) -> Optional[Column]:
        if not column_id:
            return None
        return next((c for c in self.columns if c.id == column_id), None)

    def sorted_columns(self) -> List[Column]:
        return sorted(self.columns, key=lambda c: c.order)

    def statuses_in_column(self, column_id: str) -> List[Status]:
        return [s for s in self.statuses if s.column_id == column_id]

    def hidden_statuses(self) -> List[Status]:
        """Statuses with no column - not shown on the board, just counted."""
        valid_column_ids = {c.id for c in self.columns}
        return [s for s in self.statuses if not s.column_id or s.column_id not in valid_column_ids]


def default_meeting_name(app_dir: Path) -> str:
    """The install folder is named '<Meeting Name> L10' - strip that suffix
    for a sensible default meeting name in the wizard."""
    folder_name = app_dir.parent.name or "My Team"
    if folder_name.lower().endswith("l10"):
        folder_name = folder_name[: -len("l10")].strip()
    return folder_name or "My Team"


def load_config() -> MeetingConfig:
    path = _config_path()
    if not path.exists():
        return MeetingConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return MeetingConfig.from_dict(data)
    except (ValueError, OSError):
        return MeetingConfig()


def save_config(config: MeetingConfig) -> None:
    data_dir().mkdir(parents=True, exist_ok=True)
    _config_path().write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")


# --- Occurrences ---------------------------------------------------------


@dataclass
class Occurrence:
    id: str
    date: date
    repeating_instance_id: Optional[str]  # None for a standalone/one-off meeting
    title: str
    schedule_template_id: Optional[str]
    overrides: List[sch.SectionOverride] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.date.isoformat(),
            "repeating_instance_id": self.repeating_instance_id,
            "title": self.title,
            "schedule_template_id": self.schedule_template_id,
            "overrides": [o.to_dict() for o in self.overrides],
        }

    @staticmethod
    def from_dict(d: dict) -> "Occurrence":
        return Occurrence(
            id=d["id"],
            date=date.fromisoformat(d["date"]),
            repeating_instance_id=d.get("repeating_instance_id"),
            title=d.get("title", ""),
            schedule_template_id=d.get("schedule_template_id"),
            overrides=[sch.SectionOverride.from_dict(o) for o in d.get("overrides", [])],
        )


def occurrence_key(repeating_instance_id: Optional[str], occurrence_date: date, standalone_id: Optional[str] = None) -> str:
    if repeating_instance_id:
        return f"{repeating_instance_id}::{occurrence_date.isoformat()}"
    return standalone_id or sch.new_id()


def load_occurrences() -> Dict[str, Occurrence]:
    path = _occurrences_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {key: Occurrence.from_dict(value) for key, value in data.items()}
    except (ValueError, OSError, KeyError):
        return {}


def save_occurrences(occurrences: Dict[str, Occurrence]) -> None:
    data_dir().mkdir(parents=True, exist_ok=True)
    payload = {key: occ.to_dict() for key, occ in occurrences.items()}
    _occurrences_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")


def get_occurrence(key: str) -> Optional[Occurrence]:
    return load_occurrences().get(key)


def save_occurrence(occ: Occurrence, key: Optional[str] = None) -> None:
    occurrences = load_occurrences()
    occurrences[key or occurrence_key(occ.repeating_instance_id, occ.date, occ.id)] = occ
    save_occurrences(occurrences)


def delete_occurrence(key: str) -> None:
    occurrences = load_occurrences()
    if key in occurrences:
        del occurrences[key]
        save_occurrences(occurrences)


def upcoming_occurrence_views(config: MeetingConfig, range_start: date, range_end: date) -> List[dict]:
    """Combines recurrence-generated dates with any stored customization into
    a flat, date-sorted list of dicts the UI can render directly:
    {key, date, repeating_instance_id, title, schedule_template_id,
     length_minutes, is_customized}.

    Most occurrences have no stored record - they're purely computed from a
    repeating instance's recurrence rule. A record only exists once someone
    customizes that date's schedule/title, or for standalone one-offs.
    """
    stored = load_occurrences()
    views: List[dict] = []

    for ri in config.repeating_instances:
        for occurrence_date in rec.generate_occurrences(ri.recurrence, range_start, range_end):
            key = occurrence_key(ri.id, occurrence_date)
            occ = stored.get(key)
            views.append({
                "key": key,
                "date": occurrence_date,
                "repeating_instance_id": ri.id,
                "title": occ.title if occ else ri.name,
                "schedule_template_id": (occ.schedule_template_id if occ else ri.schedule_template_id),
                "length_minutes": ri.default_length_minutes,
                "is_customized": occ is not None and bool(occ.overrides),
            })

    for key, occ in stored.items():
        if occ.repeating_instance_id is None and range_start <= occ.date <= range_end:
            views.append({
                "key": key,
                "date": occ.date,
                "repeating_instance_id": None,
                "title": occ.title,
                "schedule_template_id": occ.schedule_template_id,
                "length_minutes": None,
                "is_customized": bool(occ.overrides),
            })

    views.sort(key=lambda v: v["date"])
    return views


def resolve_occurrence_view(config: MeetingConfig, occurrence_key: str) -> Optional[dict]:
    """Same shape as upcoming_occurrence_views()'s dicts, for a single known
    key - used when navigating straight to Prep/the schedule editor without
    the dashboard's list already in hand (e.g. after a save-and-return)."""
    stored = load_occurrences()
    occ = stored.get(occurrence_key)

    if "::" in occurrence_key:
        ri_id, date_iso = occurrence_key.split("::", 1)
        ri = config.find_instance(ri_id)
        occurrence_date = date.fromisoformat(date_iso)
        return {
            "key": occurrence_key,
            "date": occurrence_date,
            "repeating_instance_id": ri_id,
            "title": occ.title if occ else (ri.name if ri else "Meeting"),
            "schedule_template_id": (occ.schedule_template_id if occ else (ri.schedule_template_id if ri else None)),
            "length_minutes": ri.default_length_minutes if ri else None,
            "is_customized": occ is not None and bool(occ.overrides),
        }

    if occ:
        return {
            "key": occurrence_key,
            "date": occ.date,
            "repeating_instance_id": None,
            "title": occ.title,
            "schedule_template_id": occ.schedule_template_id,
            "length_minutes": None,
            "is_customized": bool(occ.overrides),
        }

    return None
