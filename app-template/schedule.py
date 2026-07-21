"""Segments (globally-defined, reusable building blocks - see
segment_types.py for their types) and Schedules (named, ordered lists of
segment references) for L10 agendas.

A Segment is defined once, globally (name, type, default duration, and
whatever config its type needs) and can be reused across any number of
Schedules. A Schedule's entries reference a Segment by id and may override
its name/duration/config for that schedule. A specific meeting occurrence
can layer its own overrides on top of that - skip an entry, adjust it, or
add an extra one-off segment - without touching the Schedule or the global
Segment. "Restore" isn't a distinct override; it's removing that entry's
skip/adjust override, which is why skipped entries stay in the effective
schedule (marked skipped) rather than disappearing.

Resolution is a two-step cascade, both steps using the same fallthrough
shape: global Segment -> Schedule entry override -> occurrence override.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import segment_types as st


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Segment:
    """A globally-defined, reusable, named segment - the library entry.
    `config` holds only the fields the user has explicitly set; unset
    fields fall back to the type's own Config defaults (see
    resolved_config())."""
    id: str = field(default_factory=new_id)
    type_id: str = "generic"
    name: str = ""
    duration_minutes: int = 5
    config: dict = field(default_factory=dict)

    def resolved_config(self) -> dict:
        seg_type = st.get_segment_type(self.type_id)
        return {**seg_type.default_config(), **self.config}

    def to_dict(self) -> dict:
        return {
            "id": self.id, "type_id": self.type_id, "name": self.name,
            "duration_minutes": self.duration_minutes, "config": dict(self.config),
        }

    @staticmethod
    def from_dict(d: dict) -> "Segment":
        return Segment(
            id=d.get("id", new_id()), type_id=d.get("type_id", "generic"),
            name=d.get("name", ""), duration_minutes=int(d.get("duration_minutes", 5)),
            config=dict(d.get("config", {})),
        )


@dataclass
class ScheduleSegmentEntry:
    """One position within a Schedule - references a Segment by id and may
    override any of its name/duration/config for this particular
    schedule."""
    id: str = field(default_factory=new_id)
    segment_id: str = ""
    name_override: Optional[str] = None
    duration_override: Optional[int] = None
    config_overrides: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "segment_id": self.segment_id,
            "name_override": self.name_override, "duration_override": self.duration_override,
            "config_overrides": dict(self.config_overrides),
        }

    @staticmethod
    def from_dict(d: dict) -> "ScheduleSegmentEntry":
        return ScheduleSegmentEntry(
            id=d.get("id", new_id()), segment_id=d.get("segment_id", ""),
            name_override=d.get("name_override"), duration_override=d.get("duration_override"),
            config_overrides=dict(d.get("config_overrides", {})),
        )


@dataclass
class Schedule:
    """A reusable, named, ordered list of segment references - renamed
    from the old ScheduleTemplate. There's no bare .total_minutes property
    here anymore, since resolving a duration now needs the segment
    library - use schedule_total_minutes() instead."""
    id: str = field(default_factory=new_id)
    name: str = ""
    description: str = ""
    entries: List[ScheduleSegmentEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "entries": [e.to_dict() for e in self.entries],
        }

    @staticmethod
    def from_dict(d: dict) -> "Schedule":
        return Schedule(
            id=d.get("id", new_id()), name=d.get("name", ""), description=d.get("description", ""),
            entries=[ScheduleSegmentEntry.from_dict(e) for e in d.get("entries", [])],
        )


# Fixed (non-random) ids, matching config.py's DEFAULT_STATUS_*_ID convention,
# so a Schedule's entries keep resolving even if this list is regenerated.
SEGUE_ID = "seg_segue"
SCORECARD_ID = "seg_scorecard"
ROCKS_ID = "seg_rocks"
HEADLINES_ID = "seg_headlines"
TODO_ID = "seg_todo"
IDS_ID = "seg_ids"
CONCLUDE_ID = "seg_conclude"


def default_segments() -> List[Segment]:
    """The standard EOS Level 10 agenda's segments - see docs/L10-CONCEPT.md."""
    return [
        Segment(id=SEGUE_ID, type_id="generic", name="Segue", duration_minutes=5),
        Segment(id=SCORECARD_ID, type_id="scorecard", name="Scorecard", duration_minutes=5),
        Segment(id=ROCKS_ID, type_id="rocks", name="Rock Review", duration_minutes=5),
        Segment(id=HEADLINES_ID, type_id="headlines", name="Customer/Employee Headlines", duration_minutes=5),
        Segment(id=TODO_ID, type_id="todo", name="To-Do List", duration_minutes=5),
        Segment(id=IDS_ID, type_id="ids", name="IDS", duration_minutes=60),
        Segment(id=CONCLUDE_ID, type_id="conclude", name="Conclude", duration_minutes=5),
    ]


def default_schedule() -> Schedule:
    return Schedule(
        name="Standard L10", description="The classic EOS Level 10 Meeting agenda.",
        entries=[ScheduleSegmentEntry(segment_id=s.id) for s in default_segments()],
    )


# --- Per-occurrence overrides --------------------------------------------

OVERRIDE_SKIP = "skip"
OVERRIDE_ADD = "add"
OVERRIDE_ADJUST = "adjust"


@dataclass
class SegmentOverride:
    id: str = field(default_factory=new_id)
    kind: str = OVERRIDE_ADJUST  # OVERRIDE_SKIP | OVERRIDE_ADD | OVERRIDE_ADJUST
    entry_id: Optional[str] = None  # target for skip/adjust - a ScheduleSegmentEntry id
    name_override: Optional[str] = None
    duration_override: Optional[int] = None
    config_overrides: dict = field(default_factory=dict)
    segment_id: Optional[str] = None  # for "add" - references the global library
    insert_after_entry_id: Optional[str] = None  # for "add" - None means append at the end

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "entry_id": self.entry_id,
            "name_override": self.name_override, "duration_override": self.duration_override,
            "config_overrides": dict(self.config_overrides),
            "segment_id": self.segment_id, "insert_after_entry_id": self.insert_after_entry_id,
        }

    @staticmethod
    def from_dict(d: dict) -> "SegmentOverride":
        return SegmentOverride(
            id=d.get("id", new_id()), kind=d.get("kind", OVERRIDE_ADJUST), entry_id=d.get("entry_id"),
            name_override=d.get("name_override"), duration_override=d.get("duration_override"),
            config_overrides=dict(d.get("config_overrides", {})),
            segment_id=d.get("segment_id"), insert_after_entry_id=d.get("insert_after_entry_id"),
        )


@dataclass
class EffectiveSegment:
    """A segment as it should appear for one specific occurrence, after
    resolving the global Segment -> Schedule entry -> occurrence override
    cascade."""
    id: str
    name: str
    duration_minutes: int
    status: str  # "normal" | "skipped" | "extra" | "adjusted"
    type_id: str = "generic"
    config: dict = field(default_factory=dict)
    original_duration_minutes: Optional[int] = None  # set when status == "adjusted"


def _resolve(segment: Optional[Segment], name_override, duration_override, config_overrides):
    if segment is not None:
        seg_type = st.get_segment_type(segment.type_id)
        base_name = segment.name
        base_duration = segment.duration_minutes
        base_config = segment.resolved_config()
        type_id = segment.type_id
    else:
        # The referenced Segment was deleted out from under a live reference.
        base_name, base_duration, base_config, type_id = "(missing segment)", 5, {}, "generic"
    name = name_override if name_override is not None else base_name
    duration = duration_override if duration_override is not None else base_duration
    config = {**base_config, **(config_overrides or {})}
    return name, duration, type_id, config


def compute_effective_schedule(
    schedule: Schedule, segments: List[Segment], overrides: List[SegmentOverride],
) -> List[EffectiveSegment]:
    segments_by_id = {s.id: s for s in segments}

    skipped_ids = {o.entry_id for o in overrides if o.kind == OVERRIDE_SKIP}
    adjustments: Dict[str, SegmentOverride] = {
        o.entry_id: o for o in overrides if o.kind == OVERRIDE_ADJUST and o.entry_id
    }
    additions_after: Dict[Optional[str], List[SegmentOverride]] = {}
    for o in overrides:
        if o.kind == OVERRIDE_ADD and o.segment_id:
            additions_after.setdefault(o.insert_after_entry_id, []).append(o)

    def effective_for_add(o: SegmentOverride) -> EffectiveSegment:
        name, duration, type_id, config = _resolve(
            segments_by_id.get(o.segment_id), o.name_override, o.duration_override, o.config_overrides,
        )
        return EffectiveSegment(id=o.id, name=name, duration_minutes=duration, status="extra",
                                 type_id=type_id, config=config)

    effective: List[EffectiveSegment] = []
    for entry in schedule.entries:
        segment = segments_by_id.get(entry.segment_id)
        name1, dur1, type_id, config1 = _resolve(
            segment, entry.name_override, entry.duration_override, entry.config_overrides,
        )

        if entry.id in skipped_ids:
            effective.append(EffectiveSegment(
                id=entry.id, name=name1, duration_minutes=dur1, status="skipped",
                type_id=type_id, config=config1,
            ))
        elif entry.id in adjustments:
            o = adjustments[entry.id]
            name2 = o.name_override if o.name_override is not None else name1
            dur2 = o.duration_override if o.duration_override is not None else dur1
            config2 = {**config1, **(o.config_overrides or {})}
            effective.append(EffectiveSegment(
                id=entry.id, name=name2, duration_minutes=dur2, status="adjusted",
                type_id=type_id, config=config2, original_duration_minutes=dur1,
            ))
        else:
            effective.append(EffectiveSegment(
                id=entry.id, name=name1, duration_minutes=dur1, status="normal",
                type_id=type_id, config=config1,
            ))

        for o in additions_after.get(entry.id, []):
            effective.append(effective_for_add(o))

    for o in additions_after.get(None, []):
        effective.append(effective_for_add(o))

    return effective


def effective_total_minutes(effective_segments: List[EffectiveSegment]) -> int:
    return sum(s.duration_minutes for s in effective_segments if s.status != "skipped")


def schedule_total_minutes(schedule: Schedule, segments: List[Segment]) -> int:
    return effective_total_minutes(compute_effective_schedule(schedule, segments, []))


def schedule_display_items(schedules: List[Schedule], segments: List[Segment]) -> list:
    """Lightweight duck-typed wrappers (id/name/total_minutes) for
    ui/instance_form.py's RepeatingInstanceForm, which deliberately doesn't
    import schedule.py/config.py directly - a Schedule no longer has a bare
    .total_minutes property, since resolving one needs the segment
    library."""
    from types import SimpleNamespace
    return [
        SimpleNamespace(id=s.id, name=s.name, total_minutes=schedule_total_minutes(s, segments))
        for s in schedules
    ]
