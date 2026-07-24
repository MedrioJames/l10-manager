"""Meeting configuration, repeating instances, and occurrence persistence.

Everything here lives in Data/ (never touched by app updates - see
CLAUDE.md). Two files:
  Data/config.json       - meeting info, repeating instances, the global
                            Segment library, and Schedules (see schedule.py)
  Data/occurrences.json  - per-occurrence customization (overrides, one-offs)

Repeating instances describe a recurring meeting (e.g. "Weekly Leadership
Sync"); the recurrence rule generates occurrence *dates* on the fly, so most
occurrences have no stored record at all. A record only exists once someone
customizes that occurrence's schedule, renames it, or creates a standalone
one-off meeting that isn't tied to any repeating instance.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import recurrence as rec
import schedule as sch

CONFIG_FILENAME = "config.json"
OCCURRENCES_FILENAME = "occurrences.json"


class DataLoadError(Exception):
    """Raised when a data file exists but neither it nor its .bak backup can
    be parsed - genuine corruption, not a missing-file first run. Callers
    must not silently fall back to a blank default here, since that blank
    default would then get written back on the next save, permanently
    wiping whatever was actually on disk (this is how a Google Drive sync
    hiccup or an interrupted write turned into full data loss before this
    was added - see CLAUDE.md)."""

    def __init__(self, path: Path):
        self.path = path
        super().__init__(f"{path} and its .bak backup could not be read")


def data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "Data"


def _config_path() -> Path:
    return data_dir() / CONFIG_FILENAME


def _occurrences_path() -> Path:
    return data_dir() / OCCURRENCES_FILENAME


def _backup_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".bak")


def load_json_with_fallback(path: Path) -> Optional[dict]:
    """Reads path, falling back to path.bak if path is missing/corrupt.
    Returns None only if path doesn't exist at all (a normal first run).
    Raises DataLoadError if path exists but neither it nor its backup will
    parse - never silently returns a blank result for that case, since the
    caller would otherwise happily save that blank data straight back over
    whatever's actually on disk."""
    if not path.exists():
        return None
    backup = _backup_path(path)
    for candidate in (path, backup):
        if not candidate.exists():
            continue
        try:
            return json.loads(candidate.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
    raise DataLoadError(path)


def atomic_write_json(path: Path, payload: dict) -> None:
    """Snapshots the current (if currently valid) file to path.bak, then
    writes the new content to a temp file and atomically replaces path with
    it - never a direct truncate-in-place write. This matters because Data/
    lives on a Google Drive-synced mount: a direct write_text() that gets
    interrupted mid-write (sync lock, crash, disk full) leaves a truncated
    file that the old code silently treated as "blank," and the next save
    would then overwrite the real data with nothing. os.replace() is atomic
    on the same filesystem, so there's no window where the file is
    half-written."""
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
        else:
            try:
                shutil.copyfile(path, _backup_path(path))
            except OSError:
                pass

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # os.replace() can transiently fail with "Access is denied" (WinError 5)
    # on Windows if Google Drive Desktop (or another cloud-sync client) has
    # the destination file momentarily locked while syncing it - not a real
    # permissions problem, just a race with the sync client. Retry a few
    # times with a short backoff before giving up; this is the standard
    # mitigation for atomic replace on a cloud-synced folder.
    attempts = 5
    for attempt in range(attempts):
        try:
            os.replace(tmp_path, path)
            return
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.1 * (attempt + 1))


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
    schedule_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "default_length_minutes": self.default_length_minutes,
            "recurrence": self.recurrence.to_dict(),
            "schedule_id": self.schedule_id,
        }

    @staticmethod
    def from_dict(d: dict) -> "RepeatingInstance":
        return RepeatingInstance(
            id=d.get("id", sch.new_id()),
            name=d.get("name", ""),
            description=d.get("description", ""),
            default_length_minutes=int(d.get("default_length_minutes", 90)),
            recurrence=rec.RecurrenceRule.from_dict(d.get("recurrence", {})) if d.get("recurrence") else rec.RecurrenceRule(),
            schedule_id=d.get("schedule_id"),
        )


@dataclass
class Person:
    id: str = field(default_factory=sch.new_id)
    name: str = ""
    email: str = ""
    jira_account_id: str = ""  # maps assignments to Jira on sync, if linked
    # Set via the "Review Jira People Matches" modal (see jira_people_sync.py)
    # when the user has looked and confirmed this person just isn't on Jira -
    # keeps them out of the "unmatched local people" list on future reviews.
    jira_unmatched: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "jira_account_id": self.jira_account_id,
            "jira_unmatched": self.jira_unmatched,
        }

    @staticmethod
    def from_dict(d: dict) -> "Person":
        return Person(
            id=d.get("id", sch.new_id()),
            name=d.get("name", ""),
            email=d.get("email", ""),
            jira_account_id=d.get("jira_account_id", ""),
            jira_unmatched=bool(d.get("jira_unmatched", False)),
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
    # Every raw Jira status name ever discovered during a sync, additive-only
    # (jira_sync.map_remote_status() appends to this, never removes) - kept
    # separate from status_mapping because status_mapping's keys can shrink
    # (removing a status's mapped pill in Settings deletes that key outright,
    # see ui/settings.py's unmap_jira_status) or simply never get re-added if
    # a raw status's issues fall outside pull_issues()'s un-paginated 100-
    # issue window on a later sync. Without this separate ledger, either case
    # permanently drops that status name from the "add a Jira status" picker
    # even though it's a completely valid, still-real Jira workflow status -
    # a real user hit this after unmapping one status and finding it
    # vanished from every other status's picker too, with no way to bring it
    # back short of Jira happening to resurface it in the next sync's top 100.
    known_status_names: List[str] = field(default_factory=list)
    # When True, jira_sync.sync_from_jira() skips creating a *new* local
    # issue whose mapped status is hidden from the board (MeetingConfig.
    # hidden_statuses()) - existing already-synced issues are left alone
    # even if their Jira status later maps to hidden, to avoid surprising
    # deletions.
    sync_only_visible_statuses: bool = False
    # "Don't ask again" ledgers for the people-matching review (see
    # jira_people_sync.py) - both additive/backward-compatible. A dismissed
    # remote member (ignored) or a rejected name-only match pair shouldn't
    # keep nagging the user on every re-open of the review modal.
    ignored_account_ids: List[str] = field(default_factory=list)
    rejected_match_pairs: List[List[str]] = field(default_factory=list)  # [[person_id, account_id], ...]

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "base_url": self.base_url,
            "email": self.email,
            "project_key": self.project_key,
            "project_name": self.project_name,
            "status_mapping": dict(self.status_mapping),
            "known_status_names": list(self.known_status_names),
            "sync_only_visible_statuses": self.sync_only_visible_statuses,
            "ignored_account_ids": list(self.ignored_account_ids),
            "rejected_match_pairs": [list(pair) for pair in self.rejected_match_pairs],
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
            # A config saved before known_status_names existed has no record
            # of any Jira status name ever unmapped or paginated out of a
            # later sync - the best available reconstruction is whatever's
            # currently in status_mapping, which is at least a strict subset
            # of the truth rather than an empty list.
            known_status_names=list(d.get("known_status_names") or d.get("status_mapping", {}).keys()),
            sync_only_visible_statuses=bool(d.get("sync_only_visible_statuses", False)),
            ignored_account_ids=list(d.get("ignored_account_ids", [])),
            rejected_match_pairs=[list(pair) for pair in d.get("rejected_match_pairs", [])],
        )


@dataclass
class Column:
    """A board column. Multiple Statuses can share a column - dragging a
    card onto a column with more than one Status requires the UI to ask
    which one was intended (see ui/issue_board.py).

    hidden_by_default is a DIFFERENT concept from a hidden Status
    (Status.column_id=None, "not shown on the board at all, just
    counted") - this column still exists, still has real statuses/cards,
    it's just collapsed out of the board's default view (e.g. a "Solved"
    column a user wants out of the way day-to-day, but still one click
    away, not buried in Settings). ui/issue_board.py's board-level "Show
    hidden columns" toggle is what actually reveals it, for the current
    viewing session only - this field only controls the STARTING state."""
    id: str = field(default_factory=sch.new_id)
    name: str = ""
    order: int = 0
    hidden_by_default: bool = False

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "order": self.order, "hidden_by_default": self.hidden_by_default}

    @staticmethod
    def from_dict(d: dict) -> "Column":
        return Column(
            id=d.get("id", sch.new_id()), name=d.get("name", ""), order=int(d.get("order", 0)),
            hidden_by_default=bool(d.get("hidden_by_default", False)),
        )


@dataclass
class Status:
    """column_id of None means this status is hidden from the board
    entirely (just counted) - this replaces the old hardcoded 'Dropped'
    special case with something any custom status can opt into. is_closed
    distinguishes "hidden but still an active backlog item" (e.g. a custom
    "Someday" status) from "hidden because terminal" (e.g. "Dropped") -
    used by the Backlog view (ui/issue_board.py::open_backlog_modal) to
    only surface issues that are actually still worth looking at.

    color is an explicit user-picked hex string ("#RRGGBB"), None until
    someone customizes it in Settings > Board - ui/issue_board.py falls
    back to its existing auto-cycled-by-column palette whenever it's None,
    so a config saved before this field existed (or a status nobody's
    bothered to customize) looks completely unchanged. A real user asked
    for this directly, rather than the board silently making the color
    choice up on its own."""
    id: str = field(default_factory=sch.new_id)
    name: str = ""
    column_id: Optional[str] = None
    is_closed: bool = False
    color: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "column_id": self.column_id, "is_closed": self.is_closed,
            "color": self.color,
        }

    @staticmethod
    def from_dict(d: dict) -> "Status":
        return Status(
            id=d.get("id", sch.new_id()), name=d.get("name", ""), column_id=d.get("column_id"),
            is_closed=bool(d.get("is_closed", False)), color=d.get("color"),
        )


# Fixed ids (not random) so existing Data/issues.json entries created before
# custom statuses existed keep resolving correctly - the default seed below
# uses the exact same ids the old hardcoded STATUS_OPEN/STATUS_IN_PROGRESS/
# STATUS_SOLVED/STATUS_DROPPED constants used.
DEFAULT_STATUS_OPEN_ID = "open"
DEFAULT_STATUS_IN_PROGRESS_ID = "in_progress"
DEFAULT_STATUS_SOLVED_ID = "solved"
DEFAULT_STATUS_DROPPED_ID = "dropped"
# A real, persistent status - not a special sentinel - for a Jira status
# that's been deliberately unmapped from a column (see jira_sync.py's
# map_remote_status()/reclassify_local_issues()). column_id=None reuses the
# same "hidden from the board, just counted" machinery Dropped already
# uses, and is_closed=False keeps unmapped issues showing up in the
# Backlog view - they need someone to pick a real status for them, unlike
# Dropped, which is genuinely done.
DEFAULT_STATUS_UNMAPPED_ID = "unmapped"


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
        Status(id=DEFAULT_STATUS_DROPPED_ID, name="Dropped", column_id=None, is_closed=True),
        Status(id=DEFAULT_STATUS_UNMAPPED_ID, name="Unmapped", column_id=None),
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
    segments: List[sch.Segment] = field(default_factory=sch.default_segments)
    schedules: List[sch.Schedule] = field(default_factory=lambda: [sch.default_schedule()])
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
            "segments": [s.to_dict() for s in self.segments],
            "schedules": [s.to_dict() for s in self.schedules],
            "people": [p.to_dict() for p in self.people],
            "jira": self.jira.to_dict(),
            "columns": [c.to_dict() for c in self.columns],
            "statuses": [s.to_dict() for s in self.statuses],
            "board_display": self.board_display.to_dict(),
            "onboarded": self.onboarded,
        }

    @staticmethod
    def from_dict(d: dict) -> "MeetingConfig":
        segments = [sch.Segment.from_dict(s) for s in d.get("segments", [])]
        schedules = [sch.Schedule.from_dict(s) for s in d.get("schedules", [])]
        columns = [Column.from_dict(c) for c in d.get("columns", [])]
        statuses = [Status.from_dict(s) for s in d.get("statuses", [])]
        # Backward-compat migration for a config saved before the
        # "Unmapped" status existed - a real, editable Status like any
        # other (not seeded fresh only for brand-new configs via
        # `statuses or default_statuses()` below, since THIS config
        # already has a non-empty statuses list). Without this, an
        # existing install's map_remote_status()/reclassify_local_issues()
        # would have nowhere real to put a deliberately-unmapped Jira
        # status.
        if statuses and not any(s.id == DEFAULT_STATUS_UNMAPPED_ID for s in statuses):
            statuses.append(Status(id=DEFAULT_STATUS_UNMAPPED_ID, name="Unmapped", column_id=None))
        return MeetingConfig(
            meeting=MeetingInfo.from_dict(d.get("meeting", {})),
            repeating_instances=[RepeatingInstance.from_dict(r) for r in d.get("repeating_instances", [])],
            segments=segments or sch.default_segments(),
            schedules=schedules or [sch.default_schedule()],
            people=[Person.from_dict(p) for p in d.get("people", [])],
            jira=JiraConfig.from_dict(d.get("jira", {})),
            columns=columns or default_columns(),
            statuses=statuses or default_statuses(),
            board_display=BoardDisplaySettings.from_dict(d.get("board_display", {})),
            onboarded=bool(d.get("onboarded", False)),
        )

    def find_segment(self, segment_id: Optional[str]) -> Optional[sch.Segment]:
        if not segment_id:
            return None
        return next((s for s in self.segments if s.id == segment_id), None)

    def find_schedule(self, schedule_id: Optional[str]) -> Optional[sch.Schedule]:
        if not schedule_id:
            return None
        return next((s for s in self.schedules if s.id == schedule_id), None)

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

    def backlog_statuses(self) -> List[Status]:
        """Hidden statuses that are still active (not is_closed) - the
        Backlog view (ui/issue_board.py::open_backlog_modal) shows issues
        in these statuses; a hidden-and-closed status like "Dropped" is
        terminal and never shows up as a backlog item."""
        return [s for s in self.hidden_statuses() if not s.is_closed]


def default_meeting_name(app_dir: Path) -> str:
    """The install folder is named '<Meeting Name> L10' - strip that suffix
    for a sensible default meeting name in the wizard."""
    folder_name = app_dir.parent.name or "My Team"
    if folder_name.lower().endswith("l10"):
        folder_name = folder_name[: -len("l10")].strip()
    return folder_name or "My Team"


def load_config() -> MeetingConfig:
    path = _config_path()
    data = load_json_with_fallback(path)
    if data is None:
        return MeetingConfig()
    return MeetingConfig.from_dict(data)


def save_config(config: MeetingConfig) -> None:
    atomic_write_json(_config_path(), config.to_dict())


# --- Occurrences ---------------------------------------------------------


@dataclass
class Occurrence:
    id: str
    date: date
    repeating_instance_id: Optional[str]  # None for a standalone/one-off meeting
    title: str
    schedule_id: Optional[str]
    overrides: List[sch.SegmentOverride] = field(default_factory=list)
    notes: str = ""
    # Captured live by the Conclude segment type (segment_types.py::ConcludeType)
    # during a run; read back later by ui/review.py. ratings maps person_id
    # -> a 1-10 meeting rating (the standard EOS "everyone rates the
    # meeting" close).
    ratings: Dict[str, int] = field(default_factory=dict)
    cascading_message: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.date.isoformat(),
            "repeating_instance_id": self.repeating_instance_id,
            "title": self.title,
            "schedule_id": self.schedule_id,
            "overrides": [o.to_dict() for o in self.overrides],
            "notes": self.notes,
            "ratings": dict(self.ratings),
            "cascading_message": self.cascading_message,
        }

    @staticmethod
    def from_dict(d: dict) -> "Occurrence":
        return Occurrence(
            id=d["id"],
            date=date.fromisoformat(d["date"]),
            repeating_instance_id=d.get("repeating_instance_id"),
            title=d.get("title", ""),
            schedule_id=d.get("schedule_id"),
            overrides=[sch.SegmentOverride.from_dict(o) for o in d.get("overrides", [])],
            notes=d.get("notes", ""),
            ratings=dict(d.get("ratings", {})),
            cascading_message=d.get("cascading_message", ""),
        )


def occurrence_key(repeating_instance_id: Optional[str], occurrence_date: date, standalone_id: Optional[str] = None) -> str:
    if repeating_instance_id:
        return f"{repeating_instance_id}::{occurrence_date.isoformat()}"
    return standalone_id or sch.new_id()


def load_occurrences() -> Dict[str, Occurrence]:
    data = load_json_with_fallback(_occurrences_path())
    if data is None:
        return {}
    try:
        return {key: Occurrence.from_dict(value) for key, value in data.items()}
    except (ValueError, KeyError) as exc:
        raise DataLoadError(_occurrences_path()) from exc


def save_occurrences(occurrences: Dict[str, Occurrence]) -> None:
    payload = {key: occ.to_dict() for key, occ in occurrences.items()}
    atomic_write_json(_occurrences_path(), payload)


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


def get_or_create_occurrence(config: MeetingConfig, occurrence_key: str, view: Optional[dict] = None) -> Optional[Occurrence]:
    """Returns the stored Occurrence for occurrence_key, or builds a new
    (unsaved) one from its resolved view if none exists yet - most
    occurrences have no stored record at all until something needs to
    persist per-occurrence data against them (notes, a schedule override,
    Conclude's ratings/cascading message, ...). Pass `view` if the caller
    already has it in hand (e.g. ui/prep.py) to skip re-resolving it.
    Returns None only if the occurrence truly can't be resolved at all."""
    occ = get_occurrence(occurrence_key)
    if occ is not None:
        return occ
    if view is None:
        view = resolve_occurrence_view(config, occurrence_key)
    if view is None:
        return None
    return Occurrence(
        id=occurrence_key, date=view["date"], repeating_instance_id=view["repeating_instance_id"],
        title=view["title"], schedule_id=view["schedule_id"], overrides=[],
    )


def upcoming_occurrence_views(config: MeetingConfig, range_start: date, range_end: date) -> List[dict]:
    """Combines recurrence-generated dates with any stored customization into
    a flat, date-sorted list of dicts the UI can render directly:
    {key, date, repeating_instance_id, title, schedule_id,
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
                "schedule_id": (occ.schedule_id if occ else ri.schedule_id),
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
                "schedule_id": occ.schedule_id,
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
            "schedule_id": (occ.schedule_id if occ else (ri.schedule_id if ri else None)),
            "length_minutes": ri.default_length_minutes if ri else None,
            "is_customized": occ is not None and bool(occ.overrides),
        }

    if occ:
        return {
            "key": occurrence_key,
            "date": occ.date,
            "repeating_instance_id": None,
            "title": occ.title,
            "schedule_id": occ.schedule_id,
            "length_minutes": None,
            "is_customized": bool(occ.overrides),
        }

    return None
