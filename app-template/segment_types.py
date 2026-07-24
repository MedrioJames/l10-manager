"""Segment types - the extensible catalog of "kinds" a Segment (see
schedule.py) can be. Each type is one class: its Config dataclass defines
what's configurable, and the type owns how that config is edited (falls
back to an auto-generated form reflecting Config's fields if the type
doesn't need anything custom), how the live Run screen renders it, and how
the presentation window renders it. Adding a new type is "write the class,
you have what you need" - no other file needs to change.

Deliberately no `from __future__ import annotations` in this module -
render_settings_form's auto-generated form reflects on
dataclasses.fields(self.Config)[i].type, which needs real type objects
(bool/str/int/List[str]), not string annotations.

Rocks/Scorecard Configs are deliberately display-setting-only (show_owner,
show_trend_arrows) - real rock/scorecard data doesn't exist as a feature
yet (ui/placeholders.py stubs), so there's nothing else to store here.
"""

import dataclasses
import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Optional, Type

from ui import icon_button, theme
from ui.rounded_button import RoundedButton

# config/issues/todos are deliberately imported inside the functions that
# need them (below), not at module level: schedule.py already imports this
# module (for get_segment_type()), and config.py/issues.py/todos.py all
# import schedule.py (for schedule.new_id()) - a module-level import here
# would complete the cycle (schedule -> segment_types -> config -> schedule)
# and fail with "partially initialized module" on startup.


@dataclasses.dataclass
class DisplayConfig:
    """Universal on-screen display toggles - every built-in type's Config
    inherits from this (rather than each type separately redeclaring the
    same two fields), so dataclasses.fields(self.Config) always surfaces
    them first in the auto-generated settings form regardless of type,
    satisfying "universal + per-type mix": these two apply to every
    segment, and a type's own extra fields (show_people, show_owner, etc.)
    just come after them. A real user asked for this directly - "controls
    for what I'm showing on the screen (section title, time left, etc)...
    configured first in the segments config globally." ui/run_meeting.py
    and ui/presentation.py are the two renderers that actually respect
    these - both fall back to True via .get(key, True) for a segment
    saved before these fields existed, so nothing already configured
    changes appearance until someone unchecks something."""
    show_segment_title: bool = True
    show_time_remaining: bool = True
    show_meeting_time_remaining: bool = True


FIELD_SHOW_SEGMENT_TITLE = "show_segment_title"
FIELD_SHOW_TIME_REMAINING = "show_time_remaining"
FIELD_SHOW_MEETING_TIME_REMAINING = "show_meeting_time_remaining"


def render_preview(parent, name: str, duration_minutes: int, config: dict) -> None:
    """A small static mock of what ui/run_meeting.py's own header (segment
    title + countdown) and ui/presentation.py's header would look like for
    a segment, given `config`'s current values - used by
    ui/segment_editor.py and ui/segment_override_form.py so a real user can
    see the effect of the display toggles before saving, not only during a
    live meeting (where the real screen doubles as its own preview - see
    ui/run_meeting.py's inline "Display" controls, which rebuild the exact
    same header this mocks)."""
    card = tk.Frame(parent, background=theme.SUBTLE_BG, highlightbackground=theme.LINE, highlightthickness=1)
    card.pack(fill="x", pady=(0, 4))
    inner = tk.Frame(card, background=theme.SUBTLE_BG)
    inner.pack(padx=16, pady=14, anchor="w")

    show_title = config.get(FIELD_SHOW_SEGMENT_TITLE, True)
    show_time = config.get(FIELD_SHOW_TIME_REMAINING, True)
    show_meeting_time = config.get(FIELD_SHOW_MEETING_TIME_REMAINING, True)
    if show_title:
        tk.Label(
            inner, text=name or "(untitled segment)", background=theme.SUBTLE_BG,
            foreground=theme.INK, font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")
    if show_time:
        tk.Label(
            inner, text=f"{max(1, duration_minutes)}:00", background=theme.SUBTLE_BG,
            foreground=theme.INK, font=("Segoe UI", 28, "bold"),
        ).pack(anchor="w", pady=(4, 0))
    if show_meeting_time:
        tk.Label(
            inner, text="12:34 left in meeting", background=theme.SUBTLE_BG,
            foreground=theme.MUTED, font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(4, 0))
    if not show_title and not show_time and not show_meeting_time:
        tk.Label(
            inner, text="(nothing shown on screen)", background=theme.SUBTLE_BG,
            foreground=theme.MUTED, font=("Segoe UI", 9, "italic"),
        ).pack(anchor="w")


@dataclasses.dataclass
class DisplayOnlyConfig(DisplayConfig):
    """Shared by every built-in type that has no configurable behavior of
    its own beyond the two universal display toggles above (Generic,
    To-Do, IDS, Conclude) - reused instead of four near-identical empty
    subclasses, since splitting one out to add a real field later is
    trivial."""


class SegmentType:
    type_id: str = "generic"
    display_name: str = "Generic"
    Config: Optional[Type] = None
    default_duration_minutes: int = 5

    def default_config(self) -> dict:
        return dataclasses.asdict(self.Config()) if self.Config else {}

    def render_settings_form(self, parent, values: dict, on_change) -> None:
        """Default: reflects over Config's fields. `values` is mutated in
        place; on_change() fires after every edit. Override only if a type
        wants a custom-looking form."""
        if not self.Config:
            return
        for f in dataclasses.fields(self.Config):
            if f.name not in values:
                values[f.name] = f.default if f.default is not dataclasses.MISSING else None
            if f.type is bool:
                self._render_bool_field(parent, values, f.name, on_change)
            elif f.type is int:
                self._render_int_field(parent, values, f.name, on_change)
            elif f.type == List[str]:
                self._render_list_field(parent, values, f.name, on_change)
            else:
                self._render_str_field(parent, values, f.name, on_change)

    def render_run_view(self, parent, effective_segment, ctx) -> None:
        """Extra content shown on the Run Meeting screen below the
        countdown, for this specific segment. Default: nothing extra.
        `ctx` is the AppContext - reach ctx.config/ctx.run_state for
        anything beyond the segment itself (added when To-Do/IDS/Conclude
        needed real live behavior; the 5 original built-in types below
        never override this, so it's a safe, mechanical signature widen)."""
        return None

    def render_presentation_view(self, parent, effective_segment, ctx) -> None:
        """Extra content shown on the presentation window below the
        countdown. Default: nothing extra."""
        return None

    # --- default form field renderers -------------------------------

    @staticmethod
    def _label_for(field_name: str) -> str:
        return field_name.replace("_", " ").capitalize()

    def _render_bool_field(self, parent, values, key, on_change) -> None:
        var = tk.BooleanVar(value=bool(values.get(key)))

        def on_toggle() -> None:
            values[key] = var.get()
            on_change()

        ttk.Checkbutton(parent, text=self._label_for(key), variable=var, command=on_toggle).pack(anchor="w", pady=(0, 6))

    def _render_str_field(self, parent, values, key, on_change) -> None:
        ttk.Label(parent, text=self._label_for(key), style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 2))
        var = tk.StringVar(value=str(values.get(key) or ""))

        def on_edit(*_args) -> None:
            values[key] = var.get()
            on_change()

        var.trace_add("write", on_edit)
        ttk.Entry(parent, textvariable=var, width=36).pack(anchor="w", pady=(0, 8))

    def _render_int_field(self, parent, values, key, on_change) -> None:
        ttk.Label(parent, text=self._label_for(key), style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 2))
        var = tk.StringVar(value=str(values.get(key) or 0))

        def on_edit(*_args) -> None:
            try:
                values[key] = int(var.get())
            except ValueError:
                return
            on_change()

        var.trace_add("write", on_edit)
        ttk.Spinbox(parent, from_=0, to=999, width=8, textvariable=var).pack(anchor="w", pady=(0, 8))

    def _render_list_field(self, parent, values, key, on_change) -> None:
        ttk.Label(parent, text=self._label_for(key), style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
        values.setdefault(key, [])
        rows_frame = ttk.Frame(parent)
        rows_frame.pack(fill="x", pady=(0, 4))

        def render_rows() -> None:
            for child in rows_frame.winfo_children():
                child.destroy()
            for idx, item in enumerate(values[key]):
                row = ttk.Frame(rows_frame)
                row.pack(fill="x", pady=1)
                var = tk.StringVar(value=item)

                def on_edit(*_args, i=idx, v=var) -> None:
                    values[key][i] = v.get()
                    on_change()

                var.trace_add("write", on_edit)
                ttk.Entry(row, textvariable=var, width=30).pack(side="left", padx=(0, 4))
                icon_button.icon_button(
                    row, icon_button.GLYPH_DELETE, lambda i=idx: remove_item(i), danger=True,
                ).pack(side="left")

        def remove_item(idx: int) -> None:
            del values[key][idx]
            render_rows()
            on_change()

        def add_item() -> None:
            values[key].append("")
            render_rows()
            on_change()

        render_rows()
        RoundedButton(parent, text="+ Add", variant="tonal", command=add_item).pack(anchor="w", pady=(0, 10))


# --- Built-in types ---------------------------------------------------


@dataclasses.dataclass
class HeadlinesConfig(DisplayConfig):
    show_people: bool = True


class HeadlinesType(SegmentType):
    type_id = "headlines"
    display_name = "Headlines"
    Config = HeadlinesConfig


@dataclasses.dataclass
class CoreValuesConfig(DisplayConfig):
    values: List[str] = dataclasses.field(default_factory=list)


class CoreValuesType(SegmentType):
    type_id = "core_values"
    display_name = "Core Values"
    Config = CoreValuesConfig


@dataclasses.dataclass
class RocksConfig(DisplayConfig):
    show_owner: bool = True


class RocksType(SegmentType):
    type_id = "rocks"
    display_name = "Rock Review"
    Config = RocksConfig


@dataclasses.dataclass
class ScorecardConfig(DisplayConfig):
    show_trend_arrows: bool = True


class ScorecardType(SegmentType):
    type_id = "scorecard"
    display_name = "Scorecard"
    Config = ScorecardConfig


@dataclasses.dataclass
class GenericConfig(DisplayConfig):
    display_text: str = ""


class GenericType(SegmentType):
    type_id = "generic"
    display_name = "Generic"
    Config = GenericConfig

    def render_run_view(self, parent, effective_segment, ctx) -> None:
        _render_display_text(parent, effective_segment.config)

    def render_presentation_view(self, parent, effective_segment, ctx) -> None:
        _render_display_text(parent, effective_segment.config, presentation=True)


def _render_display_text(parent, config: dict, presentation: bool = False) -> None:
    text = (config.get("display_text") or "").strip()
    if not text:
        return
    if presentation:
        ttk.Label(parent, text=text, style="Heading.TLabel", wraplength=800, justify="center").pack(pady=20)
    else:
        ttk.Label(parent, text=text, style="Body.TLabel", wraplength=600, justify="left").pack(anchor="w")


# --- To-Do / IDS / Conclude: real live behavior, not just a Config -------
# To-Do, IDS, and Conclude have no PERSISTED configurable settings beyond
# the universal display fields (behavior below is standard EOS practice,
# not something worth making user-tunable yet). IDS's "focused issue"
# spotlight is deliberately NOT a Config field - it's live, in-memory,
# per-run state on run_state.py (like current_index), reset on the next
# meeting run, not something that would make sense to persist or override
# in Prep.

def _current_repeating_instance_id(ctx) -> Optional[str]:
    import config as cfgmod

    try:
        view = cfgmod.resolve_occurrence_view(ctx.config, ctx.run_state.occurrence_key)
    except cfgmod.DataLoadError:
        return None
    return view.get("repeating_instance_id") if view else None


FIELD_TODO_SHOW_OPEN = "show_open"
FIELD_TODO_SHOW_DONE = "show_done"


def _render_todo_list(parent, ctx, editable: bool, config: dict) -> None:
    import config as cfgmod
    import todos as td

    ri_id = _current_repeating_instance_id(ctx)
    show_open = config.get(FIELD_TODO_SHOW_OPEN, True)
    show_done = config.get(FIELD_TODO_SHOW_DONE, False)
    list_frame = ttk.Frame(parent)
    list_frame.pack(fill="x", anchor="w")

    def refresh() -> None:
        for child in list_frame.winfo_children():
            child.destroy()
        try:
            all_todos = td.list_todos(repeating_instance_id=ri_id, include_done=True)
        except cfgmod.DataLoadError:
            ttk.Label(list_frame, text="Data/todos.json couldn't be read.", style="Muted.TLabel").pack(anchor="w")
            return
        visible = [t for t in all_todos if (t.done and show_done) or (not t.done and show_open)]
        if not visible:
            ttk.Label(list_frame, text="No to-dos to show.", style="Muted.TLabel").pack(anchor="w")
        for todo in visible:
            row = ttk.Frame(list_frame)
            row.pack(fill="x", pady=2, anchor="w")
            assignee = ctx.config.find_person(todo.assignee_id)
            label = todo.title + (f"  ({assignee.name})" if assignee else "")
            if editable:
                var = tk.BooleanVar(value=todo.done)

                def on_toggle(t=todo, v=var) -> None:
                    t.done = v.get()
                    td.save_todo(t)
                    refresh()
                ttk.Checkbutton(row, text=label, variable=var, command=on_toggle).pack(anchor="w")
            else:
                mark = "☑" if todo.done else "☐"
                ttk.Label(row, text=f"{mark}  {label}", style="Body.TLabel").pack(anchor="w")

    refresh()

    if not editable:
        return

    add_row = ttk.Frame(parent)
    add_row.pack(fill="x", pady=(8, 0), anchor="w")
    title_var = tk.StringVar()
    ttk.Entry(add_row, textvariable=title_var, width=28).pack(side="left", padx=(0, 6))

    person_names = [p.name for p in ctx.config.people]
    assignee_var = tk.StringVar()
    if person_names:
        ttk.Combobox(
            add_row, textvariable=assignee_var, state="readonly", width=16, values=person_names,
        ).pack(side="left", padx=(0, 6))

    def add_todo() -> None:
        title = title_var.get().strip()
        if not title:
            return
        match = next((p for p in ctx.config.people if p.name == assignee_var.get()), None)
        td.save_todo(td.Todo(title=title, assignee_id=match.id if match else None, repeating_instance_id=ri_id))
        title_var.set("")
        assignee_var.set("")
        refresh()

    RoundedButton(add_row, text="+ Add To-Do", variant="tonal", command=add_todo).pack(side="left")


@dataclasses.dataclass
class TodoConfig(DisplayConfig):
    show_open: bool = True
    show_done: bool = False


class TodoType(SegmentType):
    type_id = "todo"
    display_name = "To-Do List"
    Config = TodoConfig

    def render_run_view(self, parent, effective_segment, ctx) -> None:
        _render_todo_list(parent, ctx, editable=True, config=effective_segment.config)

    def render_presentation_view(self, parent, effective_segment, ctx) -> None:
        _render_todo_list(parent, ctx, editable=False, config=effective_segment.config)


def _render_ids_list(parent, ctx, editable: bool) -> None:
    import config as cfgmod
    import issues as iss
    from ui import issue_board  # deferred: avoids importing ui.issue_board at module load for types that never need it

    list_frame = ttk.Frame(parent)
    list_frame.pack(fill="x", anchor="w")

    def refresh() -> None:
        for child in list_frame.winfo_children():
            child.destroy()
        try:
            all_issues = iss.list_issues()
        except cfgmod.DataLoadError:
            ttk.Label(list_frame, text="Data/issues.json couldn't be read.", style="Muted.TLabel").pack(anchor="w")
            return
        active_ids = (cfgmod.DEFAULT_STATUS_OPEN_ID, cfgmod.DEFAULT_STATUS_IN_PROGRESS_ID)
        active = [i for i in all_issues if i.status in active_ids]
        active.sort(key=lambda i: (i.status != cfgmod.DEFAULT_STATUS_IN_PROGRESS_ID, i.created_at))
        if not active:
            ttk.Label(list_frame, text="No open issues.", style="Muted.TLabel").pack(anchor="w")
        for issue in active:
            row = ttk.Frame(list_frame)
            row.pack(fill="x", pady=2, anchor="w")
            assignee = ctx.config.find_person(issue.assignee_id)
            label = issue.title + (f"  ({assignee.name})" if assignee else "")
            ttk.Label(row, text=label, style="Body.TLabel").pack(side="left")
            if editable:
                def solve(i=issue.id) -> None:
                    issue_board.set_issue_status(i, cfgmod.DEFAULT_STATUS_SOLVED_ID, refresh)
                def drop(i=issue.id) -> None:
                    issue_board.set_issue_status(i, cfgmod.DEFAULT_STATUS_DROPPED_ID, refresh)
                icon_button.icon_button(row, icon_button.GLYPH_SKIP, drop, danger=True).pack(side="right", padx=2)
                icon_button.icon_button(row, icon_button.GLYPH_SAVE, solve).pack(side="right", padx=2)

    refresh()

    if editable:
        RoundedButton(
            parent, text="+ New Issue", variant="tonal",
            command=lambda: issue_board.open_issue_dialog(ctx, iss.DEFAULT_SCOPE, None, refresh),
        ).pack(anchor="w", pady=(8, 0))


def _render_ids_board(parent, ctx) -> None:
    from ui import issue_board  # deferred: see _render_ids_list's own comment on why
    import issues as iss

    board_frame = ttk.Frame(parent)
    board_frame.pack(fill="both", expand=True)
    # The REAL board - drag-and-drop, columns, everything - not the old
    # compact list, per a real user's direct ask: "the ability to look at
    # the board just like it displays in issues." show_header=False since
    # the segment's own name is already shown above by ui/run_meeting.py's
    # own header. on_focus_issue/focused_issue_id thread through to each
    # card's Focus/Unfocus button - "select a particular item to focus on
    # (controlled by the run meeting window... presentation should just be
    # output)": this run view is the control surface, ui/presentation.py's
    # render_presentation_view (below) is the read-only reflection.
    issue_board.build_issue_board(
        board_frame, ctx, scope=iss.DEFAULT_SCOPE, show_header=False,
        on_focus_issue=ctx.run_state.set_focused_issue, focused_issue_id=ctx.run_state.focused_issue_id,
    )


def _render_ids_presentation(parent, ctx) -> None:
    import issues as iss

    focused_id = ctx.run_state.focused_issue_id if ctx.run_state else None
    focused_issue = iss.get_issue(focused_id) if focused_id else None
    if focused_issue is None:
        # Nothing spotlit - same compact open/in-progress list as before,
        # unchanged behavior for anyone not using the new Focus button.
        _render_ids_list(parent, ctx, editable=False)
        return

    assignee = ctx.config.find_person(focused_issue.assignee_id)
    status = ctx.config.find_status(focused_issue.status)
    ttk.Label(
        parent, text=focused_issue.title, style="Heading.TLabel", wraplength=800, justify="center",
    ).pack(pady=(10, 4))
    meta_bits = [b for b in (status.name if status else None, assignee.name if assignee else None) if b]
    if meta_bits:
        ttk.Label(parent, text="  ·  ".join(meta_bits), style="Muted.TLabel").pack()
    if focused_issue.description:
        ttk.Label(
            parent, text=focused_issue.description, style="Body.TLabel", wraplength=700, justify="center",
        ).pack(pady=(14, 0))


class IdsType(SegmentType):
    type_id = "ids"
    display_name = "IDS"
    Config = DisplayOnlyConfig

    def render_run_view(self, parent, effective_segment, ctx) -> None:
        _render_ids_board(parent, ctx)

    def render_presentation_view(self, parent, effective_segment, ctx) -> None:
        _render_ids_presentation(parent, ctx)


class ConcludeType(SegmentType):
    type_id = "conclude"
    display_name = "Conclude"
    Config = DisplayOnlyConfig

    def render_run_view(self, parent, effective_segment, ctx) -> None:
        import config as cfgmod

        ttk.Label(parent, text="Rate the meeting (1-10)", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 6))

        rating_vars = {}
        for person in ctx.config.people:
            row = ttk.Frame(parent)
            row.pack(fill="x", pady=2, anchor="w")
            ttk.Label(row, text=person.name, style="Body.TLabel", width=20).pack(side="left")
            var = tk.StringVar(value="8")
            ttk.Spinbox(row, from_=1, to=10, width=5, textvariable=var).pack(side="left")
            rating_vars[person.id] = var

        ttk.Label(parent, text="Cascading message", style="SectionHeading.TLabel").pack(anchor="w", pady=(12, 4))
        message_text = tk.Text(parent, height=3, width=60, font=("Segoe UI", 9), wrap="word")
        message_text.pack(anchor="w")

        status_label = ttk.Label(parent, text="", style="Muted.TLabel")

        def save() -> None:
            try:
                occ = cfgmod.get_or_create_occurrence(ctx.config, ctx.run_state.occurrence_key)
            except cfgmod.DataLoadError:
                occ = None
            if occ is None:
                status_label.configure(text="Couldn't save - occurrence data unavailable.")
                return
            occ.ratings = {}
            for person_id, var in rating_vars.items():
                try:
                    occ.ratings[person_id] = int(var.get())
                except ValueError:
                    continue
            occ.cascading_message = message_text.get("1.0", "end-1c")
            cfgmod.save_occurrence(occ, key=ctx.run_state.occurrence_key)
            status_label.configure(text="Saved.")

        RoundedButton(parent, text="Save", variant="filled", command=save).pack(anchor="w", pady=(10, 4))
        status_label.pack(anchor="w")

    def render_presentation_view(self, parent, effective_segment, ctx) -> None:
        ttk.Label(parent, text="Rate the meeting 1-10!", style="Heading.TLabel").pack(pady=20)


SEGMENT_TYPES: Dict[str, SegmentType] = {
    t.type_id: t for t in [
        GenericType(), HeadlinesType(), CoreValuesType(), RocksType(), ScorecardType(),
        TodoType(), IdsType(), ConcludeType(),
    ]
}


def get_segment_type(type_id: str) -> SegmentType:
    return SEGMENT_TYPES.get(type_id, SEGMENT_TYPES["generic"])


def all_segment_types() -> List[SegmentType]:
    return list(SEGMENT_TYPES.values())
