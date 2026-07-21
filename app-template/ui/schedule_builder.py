"""Schedule Builder - the global Segment library (Segments tab) and
reusable named Schedules built from it (Schedules tab), replacing the old
schedule_templates.py now that segments have types with their own config
(see segment_types.py) and are reused across schedules rather than each
schedule owning its own inline section data. Same single-file TabBar
pattern as ui/settings.py.
"""

import tkinter as tk
from tkinter import messagebox, ttk

import schedule as sch
import segment_types as st
from ui import icon_button, theme
from ui.schedule_entry_editor import build_entry_list_editor
from ui.scrollable import ScrollableFrame
from ui.segment_editor import open_segment_editor_modal
from ui.tabs import TabBar

TAB_SEGMENTS = 0
TAB_SCHEDULES = 1


def build(ctx, **kwargs) -> None:
    state = {
        "active_tab": TAB_SEGMENTS,
        "schedule_mode": "overview", "editing_schedule_id": None,
        "working_entries": None, "working_name": None, "working_description": None,
    }
    _render(ctx, state)


def _render(ctx, state) -> None:
    for child in ctx.content.winfo_children():
        child.destroy()

    outer = ttk.Frame(ctx.content)
    outer.pack(fill="both", expand=True, padx=32, pady=28)
    ttk.Label(outer, text="Schedules", style="Heading.TLabel").pack(anchor="w", pady=(0, 16))

    def on_tab_change(index: int) -> None:
        state["active_tab"] = index

    tabs = TabBar(outer, ["Segments", "Schedules"], on_change=on_tab_change)
    tabs.pack(fill="both", expand=True)

    segments_tab = ScrollableFrame(tabs.page(TAB_SEGMENTS))
    segments_tab.pack(fill="both", expand=True)
    schedules_tab = ScrollableFrame(tabs.page(TAB_SCHEDULES))
    schedules_tab.pack(fill="both", expand=True)

    _render_segments_tab(ctx, state, _padded(segments_tab.body))
    _render_schedules_tab(ctx, state, _padded(schedules_tab.body))

    tabs.select(state.get("active_tab", TAB_SEGMENTS))


def _padded(parent) -> ttk.Frame:
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=True, padx=16, pady=16)
    return frame


# --- Segments tab ---------------------------------------------------------

def _render_segments_tab(ctx, state, frame) -> None:
    ttk.Label(
        frame, text="Globally-defined, reusable segments you can add to any schedule.",
        style="Muted.TLabel", wraplength=520,
    ).pack(anchor="w", pady=(0, 16))

    by_type = {}
    for segment in ctx.config.segments:
        by_type.setdefault(segment.type_id, []).append(segment)

    for seg_type in st.all_segment_types():
        segments_here = by_type.get(seg_type.type_id, [])
        if not segments_here:
            continue
        ttk.Label(frame, text=seg_type.display_name, style="SectionHeading.TLabel").pack(anchor="w", pady=(8, 4))
        for segment in segments_here:
            row = tk.Frame(frame, background=theme.CARD_BG, highlightbackground=theme.LINE, highlightthickness=1)
            row.pack(fill="x", pady=3)
            info = tk.Frame(row, background=theme.CARD_BG)
            info.pack(side="left", fill="both", expand=True, padx=14, pady=10)
            tk.Label(info, text=segment.name, background=theme.CARD_BG, foreground=theme.INK,
                     font=("Segoe UI", 10, "bold")).pack(anchor="w")
            tk.Label(info, text=f"{segment.duration_minutes} min", background=theme.CARD_BG,
                     foreground=theme.MUTED, font=("Segoe UI", 8)).pack(anchor="w")

            button_box = tk.Frame(row, background=theme.CARD_BG)
            button_box.pack(side="right", padx=10)
            icon_button.icon_button(
                button_box, icon_button.GLYPH_EDIT, lambda s=segment: _edit_segment(ctx, state, s),
            ).pack(side="left", padx=2)
            icon_button.icon_button(
                button_box, icon_button.GLYPH_DUPLICATE, lambda s=segment: _duplicate_segment(ctx, state, s),
            ).pack(side="left", padx=2)
            icon_button.icon_button(
                button_box, icon_button.GLYPH_DELETE, lambda s=segment: _delete_segment(ctx, state, s), danger=True,
            ).pack(side="left", padx=2)

    ttk.Button(
        frame, text="+ New Segment", style="Secondary.TButton",
        command=lambda: _new_segment(ctx, state),
    ).pack(anchor="w", pady=(12, 0))


def _new_segment(ctx, state) -> None:
    def on_saved(_segment) -> None:
        state["active_tab"] = TAB_SEGMENTS
        _render(ctx, state)

    open_segment_editor_modal(ctx, segment=None, locked_type=None, on_saved=on_saved)


def _edit_segment(ctx, state, segment) -> None:
    def on_saved(_segment) -> None:
        state["active_tab"] = TAB_SEGMENTS
        _render(ctx, state)

    open_segment_editor_modal(ctx, segment=segment, locked_type=segment.type_id, on_saved=on_saved)


def _duplicate_segment(ctx, state, segment) -> None:
    ctx.config.segments.append(sch.Segment(
        type_id=segment.type_id, name=f"{segment.name} (Copy)",
        duration_minutes=segment.duration_minutes, config=dict(segment.config),
    ))
    ctx.save_config()
    state["active_tab"] = TAB_SEGMENTS
    _render(ctx, state)


def _delete_segment(ctx, state, segment) -> None:
    in_use = any(e.segment_id == segment.id for s in ctx.config.schedules for e in s.entries)
    if in_use and not messagebox.askyesno(
        "Segment in use", "One or more schedules use this segment. Delete it anyway?",
    ):
        return
    ctx.config.segments = [s for s in ctx.config.segments if s.id != segment.id]
    ctx.save_config()
    state["active_tab"] = TAB_SEGMENTS
    _render(ctx, state)


# --- Schedules tab ----------------------------------------------------------

def _render_schedules_tab(ctx, state, frame) -> None:
    if state["schedule_mode"] == "edit":
        _render_edit_schedule(ctx, state, frame)
        return

    ttk.Label(
        frame, text="Reusable agenda blueprints, built from segments, that you can attach to any repeating meeting.",
        style="Muted.TLabel", wraplength=520,
    ).pack(anchor="w", pady=(0, 16))

    for schedule in ctx.config.schedules:
        row = tk.Frame(frame, background=theme.CARD_BG, highlightbackground=theme.LINE, highlightthickness=1)
        row.pack(fill="x", pady=4)
        info = tk.Frame(row, background=theme.CARD_BG)
        info.pack(side="left", fill="both", expand=True, padx=14, pady=10)
        tk.Label(info, text=schedule.name, background=theme.CARD_BG, foreground=theme.INK,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        total = sch.schedule_total_minutes(schedule, ctx.config.segments)
        tk.Label(
            info, text=f"{len(schedule.entries)} segments - {total} min",
            background=theme.CARD_BG, foreground=theme.MUTED, font=("Segoe UI", 8),
        ).pack(anchor="w")

        button_box = tk.Frame(row, background=theme.CARD_BG)
        button_box.pack(side="right", padx=10)
        icon_button.icon_button(
            button_box, icon_button.GLYPH_EDIT, lambda s=schedule.id: _goto_edit_schedule(ctx, state, s),
        ).pack(side="left", padx=2)
        icon_button.icon_button(
            button_box, icon_button.GLYPH_DUPLICATE, lambda s=schedule.id: _duplicate_schedule(ctx, state, s),
        ).pack(side="left", padx=2)
        icon_button.icon_button(
            button_box, icon_button.GLYPH_DELETE, lambda s=schedule.id: _delete_schedule(ctx, state, s), danger=True,
        ).pack(side="left", padx=2)

    ttk.Button(
        frame, text="+ New Schedule", style="Secondary.TButton",
        command=lambda: _goto_edit_schedule(ctx, state, None),
    ).pack(anchor="w", pady=(12, 0))


def _goto_edit_schedule(ctx, state, schedule_id) -> None:
    schedule = ctx.config.find_schedule(schedule_id) if schedule_id else None
    state["schedule_mode"] = "edit"
    state["editing_schedule_id"] = schedule_id
    state["active_tab"] = TAB_SCHEDULES
    state["working_entries"] = [
        sch.ScheduleSegmentEntry(
            segment_id=e.segment_id, name_override=e.name_override,
            duration_override=e.duration_override, config_overrides=dict(e.config_overrides),
        )
        for e in (schedule.entries if schedule else [])
    ]
    state["working_name"] = schedule.name if schedule else ""
    state["working_description"] = schedule.description if schedule else ""
    _render(ctx, state)


def _duplicate_schedule(ctx, state, schedule_id) -> None:
    schedule = ctx.config.find_schedule(schedule_id)
    if not schedule:
        return
    ctx.config.schedules.append(sch.Schedule(
        name=f"{schedule.name} (Copy)",
        description=schedule.description,
        entries=[
            sch.ScheduleSegmentEntry(
                segment_id=e.segment_id, name_override=e.name_override,
                duration_override=e.duration_override, config_overrides=dict(e.config_overrides),
            )
            for e in schedule.entries
        ],
    ))
    ctx.save_config()
    state["active_tab"] = TAB_SCHEDULES
    _render(ctx, state)


def _delete_schedule(ctx, state, schedule_id) -> None:
    if len(ctx.config.schedules) <= 1:
        messagebox.showwarning("Can't delete", "You need at least one schedule.")
        return
    in_use = any(r.schedule_id == schedule_id for r in ctx.config.repeating_instances)
    if in_use and not messagebox.askyesno(
        "Schedule in use", "One or more repeating meetings use this schedule. Delete it anyway?",
    ):
        return
    ctx.config.schedules = [s for s in ctx.config.schedules if s.id != schedule_id]
    ctx.save_config()
    state["active_tab"] = TAB_SCHEDULES
    _render(ctx, state)


def _render_edit_schedule(ctx, state, frame) -> None:
    is_new = state["editing_schedule_id"] is None
    ttk.Label(frame, text="New Schedule" if is_new else "Edit Schedule", style="Heading.TLabel").pack(anchor="w", pady=(0, 16))

    name_var = tk.StringVar(value=state["working_name"])
    ttk.Label(frame, text="Name", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Entry(frame, textvariable=name_var, width=40).pack(anchor="w", pady=(0, 12))

    description_var = tk.StringVar(value=state["working_description"])
    ttk.Label(frame, text="Description (optional)", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Entry(frame, textvariable=description_var, width=40).pack(anchor="w", pady=(0, 16))

    ttk.Label(frame, text="Segments", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))

    total_label = ttk.Label(frame, text="", style="Body.TLabel")

    def update_total() -> None:
        temp_schedule = sch.Schedule(entries=state["working_entries"])
        total = sch.schedule_total_minutes(temp_schedule, ctx.config.segments)
        total_label.configure(text=f"Total: {total} minutes")

    build_entry_list_editor(frame, ctx, state["working_entries"], on_change=update_total)
    total_label.pack(anchor="w", pady=(4, 20))

    button_row = ttk.Frame(frame)
    button_row.pack(fill="x")

    def cancel() -> None:
        state["schedule_mode"] = "overview"
        state["active_tab"] = TAB_SCHEDULES
        _render(ctx, state)

    def save() -> None:
        name = name_var.get().strip() or "Untitled Schedule"
        description = description_var.get().strip()
        if not state["working_entries"]:
            messagebox.showerror("Add a segment", "A schedule needs at least one segment.")
            return
        if is_new:
            ctx.config.schedules.append(sch.Schedule(
                name=name, description=description, entries=state["working_entries"],
            ))
        else:
            schedule = ctx.config.find_schedule(state["editing_schedule_id"])
            schedule.name = name
            schedule.description = description
            schedule.entries = state["working_entries"]
        ctx.save_config()
        state["schedule_mode"] = "overview"
        state["active_tab"] = TAB_SCHEDULES
        _render(ctx, state)

    ttk.Button(button_row, text="Cancel", style="Secondary.TButton", command=cancel).pack(side="left")
    ttk.Button(button_row, text="Save", style="Primary.TButton", command=save).pack(side="right")
