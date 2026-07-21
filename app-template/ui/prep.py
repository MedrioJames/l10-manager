"""Prep screen for one specific meeting occurrence: shows its effective
schedule (a Schedule's segments + any per-occurrence overrides) and links
to the Schedule Editor. Also handles creating a standalone one-off meeting
that isn't tied to any repeating instance.
"""

from datetime import date

import tkinter as tk
from tkinter import ttk, messagebox

import config as cfgmod
import schedule as sch
from ui import issue_board, run_meeting, theme
from ui.notifications import show_error_banner
from ui.occurrence_list import render_occurrence_list
from ui.rounded_button import RoundedButton
from ui.rounded_card import RoundedCard
from ui.scrollable import ScrollableFrame


def build(ctx, occurrence_key=None, view=None, create_one_off=False, **kwargs) -> None:
    scroll = ScrollableFrame(ctx.content)
    scroll.pack(fill="both", expand=True)
    frame = ttk.Frame(scroll.body)
    frame.pack(fill="both", expand=True, padx=32, pady=28)

    if create_one_off:
        _render_create_one_off(ctx, frame)
        return

    if occurrence_key is None and view is None:
        _render_picker(ctx, frame)
        return

    try:
        resolved = view or cfgmod.resolve_occurrence_view(ctx.config, occurrence_key)
    except cfgmod.DataLoadError:
        show_error_banner(
            ctx, "Data/occurrences.json couldn't be read - a backup may be available at occurrences.json.bak.",
        )
        resolved = None

    if not resolved:
        ttk.Label(frame, text="Couldn't find that meeting.", style="Body.TLabel").pack(anchor="w")
        RoundedButton(frame, text="Back to Dashboard", variant="tonal",
                   command=lambda: ctx.navigate("dashboard")).pack(anchor="w", pady=(12, 0))
        return

    _render_prep(ctx, frame, resolved)


def _render_picker(ctx, frame) -> None:
    """Reached from the sidebar (no specific occurrence in hand yet) -
    reuses the same "list of upcoming meetings" component Dashboard/Run
    Meeting also use."""
    ttk.Label(frame, text="Prep", style="Heading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Label(frame, text="Pick a meeting to prep.", style="Muted.TLabel").pack(anchor="w", pady=(0, 16))

    def on_pick(picked_view) -> None:
        for child in frame.winfo_children():
            child.destroy()
        _render_prep(ctx, frame, picked_view)

    render_occurrence_list(frame, ctx, on_pick=on_pick)


def _render_create_one_off(ctx, frame) -> None:
    ttk.Label(frame, text="Create a One-Off Meeting", style="Heading.TLabel").pack(anchor="w", pady=(0, 16))

    title_var = tk.StringVar(value="Special L10")
    ttk.Label(frame, text="Title", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Entry(frame, textvariable=title_var, width=36).pack(anchor="w", pady=(0, 12))

    date_var = tk.StringVar(value=date.today().isoformat())
    ttk.Label(frame, text="Date (YYYY-MM-DD)", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Entry(frame, textvariable=date_var, width=16).pack(anchor="w", pady=(0, 12))

    schedules = ctx.config.schedules
    schedule_display = {f"{s.name} ({sch.schedule_total_minutes(s, ctx.config.segments)} min)": s for s in schedules}
    schedule_name_var = tk.StringVar(value=next(iter(schedule_display), ""))
    ttk.Label(frame, text="Schedule", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Combobox(
        frame, textvariable=schedule_name_var, state="readonly",
        values=list(schedule_display.keys()), width=34,
    ).pack(anchor="w", pady=(0, 16))

    button_row = ttk.Frame(frame)
    button_row.pack(fill="x")

    def cancel() -> None:
        ctx.navigate("dashboard")

    def create() -> None:
        try:
            occurrence_date = date.fromisoformat(date_var.get().strip())
        except ValueError:
            messagebox.showerror("Check the date", "Date must be in YYYY-MM-DD format")
            return
        schedule_obj = schedule_display.get(schedule_name_var.get())
        new_id = sch.new_id()
        occ = cfgmod.Occurrence(
            id=new_id, date=occurrence_date, repeating_instance_id=None,
            title=title_var.get().strip() or "Special L10",
            schedule_id=schedule_obj.id if schedule_obj else None,
            overrides=[],
        )
        cfgmod.save_occurrence(occ, key=new_id)
        ctx.navigate("prep", occurrence_key=new_id)

    RoundedButton(button_row, text="Cancel", variant="tonal", command=cancel).pack(side="left")
    RoundedButton(button_row, text="Create", variant="filled", command=create).pack(side="right")


def _render_no_schedule(ctx, frame, view) -> None:
    ttk.Label(frame, text="No schedule is set for this meeting.", style="Body.TLabel").pack(anchor="w", pady=(0, 8))

    if view["repeating_instance_id"] is not None:
        ttk.Label(
            frame, text="This is part of a repeating series - you can set a schedule for every "
                         "occurrence of it, or just for this one meeting.",
            style="Muted.TLabel", wraplength=520,
        ).pack(anchor="w", pady=(0, 8))
        RoundedButton(
            frame, text="Set Schedule for the Whole Series...", variant="tonal",
            command=lambda: ctx.navigate("settings", edit_instance_id=view["repeating_instance_id"]),
        ).pack(anchor="w", pady=(0, 12))

    ttk.Label(frame, text="Set a schedule for just this meeting:", style="Muted.TLabel").pack(anchor="w", pady=(0, 4))

    schedules = ctx.config.schedules
    schedule_display = {f"{s.name} ({sch.schedule_total_minutes(s, ctx.config.segments)} min)": s for s in schedules}
    schedule_name_var = tk.StringVar(value=next(iter(schedule_display), ""))

    picker_row = ttk.Frame(frame)
    picker_row.pack(fill="x", pady=(0, 16))
    ttk.Combobox(
        picker_row, textvariable=schedule_name_var, state="readonly", width=30,
        values=list(schedule_display.keys()),
    ).pack(side="left", padx=(0, 8))

    def set_this_meeting_schedule() -> None:
        chosen = schedule_display.get(schedule_name_var.get())
        if chosen is None:
            return
        try:
            occ = cfgmod.get_or_create_occurrence(ctx.config, view["key"], view=view)
        except cfgmod.DataLoadError:
            show_error_banner(
                ctx, "Data/occurrences.json couldn't be read - the schedule couldn't be saved.",
            )
            return
        if occ is None:
            return
        occ.schedule_id = chosen.id
        cfgmod.save_occurrence(occ, key=view["key"])
        ctx.navigate("prep", occurrence_key=view["key"])

    RoundedButton(
        picker_row, text="Set Schedule for This Meeting", variant="filled", command=set_this_meeting_schedule,
    ).pack(side="left")


def _render_prep(ctx, frame, view) -> None:
    date_str = f"{view['date'].strftime('%A, %B')} {view['date'].day}, {view['date'].year}"
    ttk.Label(frame, text=view["title"], style="Heading.TLabel").pack(anchor="w")
    ttk.Label(frame, text=date_str, style="Muted.TLabel").pack(anchor="w", pady=(0, 20))

    schedule_obj = ctx.config.find_schedule(view["schedule_id"])
    if not schedule_obj:
        _render_no_schedule(ctx, frame, view)
    else:
        try:
            occ = cfgmod.get_occurrence(view["key"])
        except cfgmod.DataLoadError:
            show_error_banner(
                ctx, "Data/occurrences.json couldn't be read - a backup may be available at occurrences.json.bak.",
            )
            occ = None
        overrides = occ.overrides if occ else []
        effective = sch.compute_effective_schedule(schedule_obj, ctx.config.segments, overrides)

        list_frame = ttk.Frame(frame)
        list_frame.pack(fill="x", pady=(0, 12))
        for segment in effective:
            card = RoundedCard(list_frame)
            card.pack(fill="x", pady=2)
            row = card.body
            label_color = theme.MUTED if segment.status == "skipped" else theme.INK
            name_text = segment.name
            if segment.status == "skipped":
                name_text += "  (skipped)"
            elif segment.status == "extra":
                name_text += "  (extra)"
            elif segment.status == "adjusted":
                name_text += f"  (was {segment.original_duration_minutes} min)"
            tk.Label(row, text=name_text, background=theme.CARD_BG, foreground=label_color,
                     font=("Segoe UI", 10)).pack(side="left", padx=12, pady=6)
            tk.Label(row, text=f"{segment.duration_minutes} min", background=theme.CARD_BG,
                     foreground=label_color, font=("Segoe UI", 9)).pack(side="right", padx=12, pady=6)

        total = sch.effective_total_minutes(effective)
        ttk.Label(frame, text=f"Total: {total} minutes", style="Body.TLabel").pack(anchor="w", pady=(0, 16))

    button_row = ttk.Frame(frame)
    button_row.pack(fill="x")
    RoundedButton(button_row, text="Back to Dashboard", variant="tonal",
               command=lambda: ctx.navigate("dashboard")).pack(side="left")
    RoundedButton(
        button_row, text="View Backlog", variant="tonal",
        command=lambda: issue_board.open_backlog_modal(ctx),
    ).pack(side="left", padx=(8, 0))
    if schedule_obj:
        RoundedButton(
            button_row, text="Edit Schedule for This Meeting", variant="tonal",
            command=lambda: ctx.navigate("schedule_editor", occurrence_key=view["key"], view=view),
        ).pack(side="right", padx=(8, 0))

        def do_start_meeting() -> None:
            run_meeting.start_meeting(ctx, view)

        RoundedButton(
            button_row, text="Start Meeting", variant="filled", command=do_start_meeting,
        ).pack(side="right")
