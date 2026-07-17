"""Schedule templates and per-occurrence customization for L10 agendas.

A ScheduleTemplate is a reusable, named blueprint (e.g. "Standard L10 (90
min)") made of ordered Sections. A specific meeting occurrence can layer
overrides on top of a template - skip a section, add an extra one, or
adjust a section's length - without altering the template itself. "Restore"
isn't a distinct override; it's just removing that section's skip/adjust
override, which is why skipped sections stay in the effective schedule
(marked skipped) rather than disappearing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Section:
    id: str = field(default_factory=new_id)
    name: str = ""
    duration_minutes: int = 5

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "duration_minutes": self.duration_minutes}

    @staticmethod
    def from_dict(d: dict) -> "Section":
        return Section(
            id=d.get("id", new_id()),
            name=d.get("name", ""),
            duration_minutes=int(d.get("duration_minutes", 5)),
        )


@dataclass
class ScheduleTemplate:
    id: str = field(default_factory=new_id)
    name: str = ""
    description: str = ""
    sections: List[Section] = field(default_factory=list)

    @property
    def total_minutes(self) -> int:
        return sum(s.duration_minutes for s in self.sections)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "sections": [s.to_dict() for s in self.sections],
        }

    @staticmethod
    def from_dict(d: dict) -> "ScheduleTemplate":
        return ScheduleTemplate(
            id=d.get("id", new_id()),
            name=d.get("name", ""),
            description=d.get("description", ""),
            sections=[Section.from_dict(s) for s in d.get("sections", [])],
        )


def default_template() -> ScheduleTemplate:
    """The standard EOS Level 10 agenda - see docs/L10-CONCEPT.md."""
    return ScheduleTemplate(
        name="Standard L10 (90 min)",
        description="The classic EOS Level 10 Meeting agenda.",
        sections=[
            Section(name="Segue", duration_minutes=5),
            Section(name="Scorecard", duration_minutes=5),
            Section(name="Rock Review", duration_minutes=5),
            Section(name="Customer/Employee Headlines", duration_minutes=5),
            Section(name="To-Do List", duration_minutes=5),
            Section(name="IDS", duration_minutes=60),
            Section(name="Conclude", duration_minutes=5),
        ],
    )


# --- Per-occurrence overrides -------------------------------------------

OVERRIDE_SKIP = "skip"
OVERRIDE_ADD = "add"
OVERRIDE_ADJUST = "adjust"


@dataclass
class SectionOverride:
    kind: str  # OVERRIDE_SKIP | OVERRIDE_ADD | OVERRIDE_ADJUST
    section_id: Optional[str] = None  # target for skip/adjust - a template section id
    new_duration_minutes: Optional[int] = None  # for adjust
    added_section: Optional[Section] = None  # for add
    insert_after_section_id: Optional[str] = None  # for add - None means append at the end

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "section_id": self.section_id,
            "new_duration_minutes": self.new_duration_minutes,
            "added_section": self.added_section.to_dict() if self.added_section else None,
            "insert_after_section_id": self.insert_after_section_id,
        }

    @staticmethod
    def from_dict(d: dict) -> "SectionOverride":
        return SectionOverride(
            kind=d.get("kind"),
            section_id=d.get("section_id"),
            new_duration_minutes=d.get("new_duration_minutes"),
            added_section=Section.from_dict(d["added_section"]) if d.get("added_section") else None,
            insert_after_section_id=d.get("insert_after_section_id"),
        )


@dataclass
class EffectiveSection:
    """A section as it should appear for one specific occurrence, after
    applying overrides on top of the base template."""
    id: str
    name: str
    duration_minutes: int
    status: str  # "normal" | "skipped" | "extra" | "adjusted"
    original_duration_minutes: Optional[int] = None  # set when status == "adjusted"


def compute_effective_schedule(template: ScheduleTemplate, overrides: List[SectionOverride]) -> List[EffectiveSection]:
    skipped_ids = {o.section_id for o in overrides if o.kind == OVERRIDE_SKIP}
    adjustments: Dict[str, int] = {
        o.section_id: o.new_duration_minutes for o in overrides if o.kind == OVERRIDE_ADJUST and o.new_duration_minutes is not None
    }
    additions_after: Dict[str, List[Section]] = {}
    trailing_additions: List[Section] = []
    for o in overrides:
        if o.kind != OVERRIDE_ADD or not o.added_section:
            continue
        if o.insert_after_section_id:
            additions_after.setdefault(o.insert_after_section_id, []).append(o.added_section)
        else:
            trailing_additions.append(o.added_section)

    effective: List[EffectiveSection] = []
    for section in template.sections:
        if section.id in skipped_ids:
            effective.append(EffectiveSection(
                id=section.id, name=section.name, duration_minutes=section.duration_minutes,
                status="skipped",
            ))
        elif section.id in adjustments:
            effective.append(EffectiveSection(
                id=section.id, name=section.name, duration_minutes=adjustments[section.id],
                status="adjusted", original_duration_minutes=section.duration_minutes,
            ))
        else:
            effective.append(EffectiveSection(
                id=section.id, name=section.name, duration_minutes=section.duration_minutes,
                status="normal",
            ))

        for added in additions_after.get(section.id, []):
            effective.append(EffectiveSection(
                id=added.id, name=added.name, duration_minutes=added.duration_minutes, status="extra",
            ))

    for added in trailing_additions:
        effective.append(EffectiveSection(
            id=added.id, name=added.name, duration_minutes=added.duration_minutes, status="extra",
        ))

    return effective


def effective_total_minutes(effective_sections: List[EffectiveSection]) -> int:
    return sum(s.duration_minutes for s in effective_sections if s.status != "skipped")
