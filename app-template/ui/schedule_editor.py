"""Per-occurrence schedule editor: skip/restore entries, add extra ones,
adjust an entry's name/duration/config - all layered on top of the base
Schedule as overrides (see schedule.py), never modifying the Schedule
itself. Skipped entries stay listed (marked skipped) so they can be
restored.
"""

import tkinter as tk
from tkinter import ttk

import config as cfgmod
import schedule as sch
from ui import icon_button, segment_override_form, segment_picker, theme
from ui.notifications import show_error_banner
from ui.scrollable import ScrollableFrame


def build(ctx, occurrence_key, view=None, **kwargs) -> None:
    try:
        resolved = view or cfgmod.resolve_occurrence_view(ctx.config, occurrence_key)
    except cfgmod.DataLoadError:
        show_error_banner(
            ctx, "Data/occurrences.json couldn't be read - a backup may be available at occurrences.json.bak.",
        )
        resolved = None

    if not resolved:
        frame = ttk.Frame(ctx.content)
        frame.pack(fill="both", expand=True, padx=32, pady=28)
        ttk.Label(frame, text="Couldn't find that meeting.", style="Body.TLabel").pack(anchor="w")
        return

    schedule_obj = ctx.config.find_schedule(resolved["schedule_id"])
    if not schedule_obj:
        frame = ttk.Frame(ctx.content)
        frame.pack(fill="both", expand=True, padx=32, pady=28)
        ttk.Label(frame, text="This meeting has no schedule to edit.", style="Body.TLabel").pack(anchor="w")
        return

    try:
        occ = cfgmod.get_occurrence(occurrence_key)
    except cfgmod.DataLoadError:
        show_error_banner(
            ctx, "Data/occurrences.json couldn't be read - a backup may be available at occurrences.json.bak.",
        )
        occ = None
    state = {"overrides": list(occ.overrides) if occ else []}
    _render(ctx, state, resolved, schedule_obj, occurrence_key)


def _render(ctx, state, view, schedule_obj, occurrence_key) -> None:
    for child in ctx.content.winfo_children():
        child.destroy()

    scroll = ScrollableFrame(ctx.content)
    scroll.pack(fill="both", expand=True)
    frame = ttk.Frame(scroll.body)
    frame.pack(fill="both", expand=True, padx=32, pady=28)

    ttk.Label(frame, text=f"Edit Schedule - {view['title']}", style="Heading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Label(
        frame, text="Skipped segments stay listed so you can restore them. Adjustments and extras are marked.",
        style="Muted.TLabel", wraplength=520,
    ).pack(anchor="w", pady=(0, 16))

    list_frame = ttk.Frame(frame)
    list_frame.pack(fill="x", pady=(0, 8))

    total_label = ttk.Label(frame, text="", style="Body.TLabel")

    def render_list() -> None:
        for child in list_frame.winfo_children():
            child.destroy()
        current = sch.compute_effective_schedule(schedule_obj, ctx.config.segments, state["overrides"])
        for effective in current:
            row = tk.Frame(list_frame, background=theme.CARD_BG, highlightbackground=theme.LINE, highlightthickness=1)
            row.pack(fill="x", pady=2)

            left = tk.Frame(row, background=theme.CARD_BG)
            left.pack(side="left", fill="both", expand=True, padx=12, pady=8)
            label_color = theme.MUTED if effective.status == "skipped" else theme.INK
            weight = "normal" if effective.status == "skipped" else "bold"
            tk.Label(left, text=effective.name, background=theme.CARD_BG, foreground=label_color,
                     font=("Segoe UI", 10, weight)).pack(anchor="w")

            tag = ""
            if effective.status == "skipped":
                tag = "Skipped"
            elif effective.status == "extra":
                tag = "Extra"
            elif effective.status == "adjusted":
                tag = f"Adjusted (was {effective.original_duration_minutes} min)"
            if tag:
                tk.Label(left, text=tag, background=theme.CARD_BG, foreground=theme.PRIMARY,
                         font=("Segoe UI", 8)).pack(anchor="w")

            right = tk.Frame(row, background=theme.CARD_BG)
            right.pack(side="right", padx=10, pady=6)
            tk.Label(right, text=f"{effective.duration_minutes} min", background=theme.CARD_BG,
                     foreground=label_color, font=("Segoe UI", 9)).pack(side="left", padx=(0, 10))

            is_schedule_entry = any(e.id == effective.id for e in schedule_obj.entries)

            if effective.status == "skipped":
                icon_button.icon_button(
                    right, icon_button.GLYPH_RESTORE, lambda eid=effective.id: restore_entry(eid),
                ).pack(side="left", padx=2)
            elif is_schedule_entry:
                icon_button.icon_button(
                    right, icon_button.GLYPH_SKIP, lambda eid=effective.id: skip_entry(eid),
                ).pack(side="left", padx=2)
                icon_button.icon_button(
                    right, icon_button.GLYPH_EDIT, lambda eid=effective.id: adjust_entry(eid),
                ).pack(side="left", padx=2)
            else:
                icon_button.icon_button(
                    right, icon_button.GLYPH_DELETE, lambda eid=effective.id: remove_extra(eid), danger=True,
                ).pack(side="left", padx=2)

        total_label.configure(text=f"Total: {sch.effective_total_minutes(current)} minutes")

    def skip_entry(entry_id: str) -> None:
        state["overrides"] = [
            o for o in state["overrides"] if not (o.kind == sch.OVERRIDE_SKIP and o.entry_id == entry_id)
        ]
        state["overrides"].append(sch.SegmentOverride(kind=sch.OVERRIDE_SKIP, entry_id=entry_id))
        render_list()

    def restore_entry(entry_id: str) -> None:
        state["overrides"] = [
            o for o in state["overrides"]
            if not (o.kind in (sch.OVERRIDE_SKIP, sch.OVERRIDE_ADJUST) and o.entry_id == entry_id)
        ]
        render_list()

    def adjust_entry(entry_id: str) -> None:
        entry = next((e for e in schedule_obj.entries if e.id == entry_id), None)
        if entry is None:
            return
        segment = ctx.config.find_segment(entry.segment_id)
        if segment is None:
            return
        effective = sch.compute_effective_schedule(schedule_obj, ctx.config.segments, state["overrides"])
        current = next((e for e in effective if e.id == entry_id), None)
        resolved = {
            "name": current.name if current else segment.name,
            "duration_minutes": current.duration_minutes if current else segment.duration_minutes,
            "config": current.config if current else segment.resolved_config(),
        }

        def on_save(fields) -> None:
            state["overrides"] = [
                o for o in state["overrides"] if not (o.kind == sch.OVERRIDE_ADJUST and o.entry_id == entry_id)
            ]
            state["overrides"].append(sch.SegmentOverride(
                kind=sch.OVERRIDE_ADJUST, entry_id=entry_id,
                name_override=fields["name_override"], duration_override=fields["duration_override"],
                config_overrides=fields["config_overrides"],
            ))
            render_list()

        segment_override_form.open_override_modal(ctx, segment, resolved, on_save, title="Adjust for This Meeting")

    def remove_extra(override_id: str) -> None:
        state["overrides"] = [o for o in state["overrides"] if o.id != override_id]
        render_list()

    def add_segment() -> None:
        def on_picked(segment) -> None:
            resolved = {
                "name": segment.name, "duration_minutes": segment.duration_minutes,
                "config": segment.resolved_config(),
            }

            def on_save(fields) -> None:
                state["overrides"].append(sch.SegmentOverride(
                    kind=sch.OVERRIDE_ADD, segment_id=segment.id,
                    name_override=fields["name_override"], duration_override=fields["duration_override"],
                    config_overrides=fields["config_overrides"],
                ))
                render_list()

            segment_override_form.open_override_modal(ctx, segment, resolved, on_save, title="Add This Segment")

        segment_picker.open_segment_picker(ctx, on_picked, title="Add Segment to This Meeting")

    render_list()

    ttk.Button(frame, text="+ Add Segment", style="Secondary.TButton",
               command=add_segment).pack(anchor="w", pady=(8, 4))
    total_label.pack(anchor="w", pady=(4, 20))

    button_row = ttk.Frame(frame)
    button_row.pack(fill="x")

    def cancel() -> None:
        ctx.navigate("prep", occurrence_key=occurrence_key, view=view)

    def save() -> None:
        occ = cfgmod.get_occurrence(occurrence_key)
        if occ is None:
            occ = cfgmod.Occurrence(
                id=occurrence_key, date=view["date"], repeating_instance_id=view["repeating_instance_id"],
                title=view["title"], schedule_id=view["schedule_id"], overrides=[],
            )
        occ.overrides = state["overrides"]
        cfgmod.save_occurrence(occ, key=occurrence_key)
        ctx.navigate("prep", occurrence_key=occurrence_key)

    ttk.Button(button_row, text="Cancel", style="Secondary.TButton", command=cancel).pack(side="left")
    ttk.Button(button_row, text="Save Schedule", style="Primary.TButton", command=save).pack(side="right")
