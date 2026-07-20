"""The Run Meeting screen - live control for an active meeting run: current
segment + countdown, overall time remaining, start/pause, advance early,
jump to any segment, adjust the meeting clock, open the presentation
window, and a collapsible personal-notes panel. Reuses the same
effective-schedule row style already used by ui/prep.py/ui/schedule_editor.py
rather than inventing a new list widget.

start_meeting(ctx, view) is the entry point Prep calls to begin a run: it
computes the effective schedule once, builds a run_state.MeetingRunState,
mounts the persistent indicator bar, and navigates here.
"""

import tkinter as tk
from tkinter import messagebox, ttk

import config as cfgmod
import run_state as rs
import schedule as sch
import segment_types as st
from ui import presentation, run_indicator, theme
from ui.dialogs import ask_minutes
from ui.notifications import show_error_banner
from ui.scrollable import ScrollableFrame


def start_meeting(ctx, view) -> None:
    if ctx.run_state is not None and not ctx.run_state.ended and ctx.run_state.occurrence_key != view["key"]:
        if not messagebox.askyesno(
            "A meeting is already running", "End the current run and start this one instead?",
        ):
            return
        ctx.run_state.stop()

    schedule_obj = ctx.config.find_schedule(view["schedule_id"])
    if not schedule_obj:
        messagebox.showerror("No schedule", "This meeting has no schedule to run.")
        return

    try:
        occ = cfgmod.get_occurrence(view["key"])
    except cfgmod.DataLoadError:
        show_error_banner(
            ctx, "Data/occurrences.json couldn't be read - a backup may be available at occurrences.json.bak.",
        )
        occ = None

    overrides = occ.overrides if occ else []
    effective = sch.compute_effective_schedule(schedule_obj, ctx.config.segments, overrides)
    runnable = [s for s in effective if s.status != "skipped"]
    if not runnable:
        messagebox.showerror("Nothing to run", "This meeting's schedule has no segments to run.")
        return

    ctx.run_state = rs.MeetingRunState(ctx.root, view["key"], view["title"], runnable)
    ctx.run_state.resume()
    run_indicator.mount(ctx)
    ctx.navigate("run_meeting", occurrence_key=view["key"])


def build(ctx, occurrence_key=None, **kwargs) -> None:
    if ctx.run_state is None or ctx.run_state.ended:
        frame = ttk.Frame(ctx.content)
        frame.pack(fill="both", expand=True, padx=32, pady=28)
        ttk.Label(frame, text="No meeting is currently running.", style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(
            frame, text="Start a meeting from its Prep screen to begin a live run.", style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 16))
        ttk.Button(frame, text="Go to Dashboard", style="Primary.TButton",
                   command=lambda: ctx.navigate("dashboard")).pack(anchor="w")
        return

    _render_active(ctx)


def _render_active(ctx) -> None:
    scroll = ScrollableFrame(ctx.content)
    scroll.pack(fill="both", expand=True)
    frame = ttk.Frame(scroll.body)
    frame.pack(fill="both", expand=True, padx=32, pady=28)

    state = ctx.run_state

    segment_label = ttk.Label(frame, text="", style="Heading.TLabel")
    segment_label.pack(anchor="w")

    countdown_label = tk.Label(frame, text="", background=theme.BG, font=("Segoe UI", 48, "bold"))
    countdown_label.pack(anchor="w", pady=(4, 4))

    overall_label = ttk.Label(frame, text="", style="Body.TLabel")
    overall_label.pack(anchor="w", pady=(0, 16))

    controls = ttk.Frame(frame)
    controls.pack(fill="x", pady=(0, 20))

    toggle_btn = ttk.Button(controls, text="Pause", style="Primary.TButton", command=state.toggle_start_pause)
    toggle_btn.pack(side="left", padx=(0, 8))

    def handle_next() -> None:
        was_last = state.is_last_segment
        state.advance_to_next()
        if was_last:
            ctx.navigate("conclude")

    next_btn = ttk.Button(controls, text="Next Segment →", style="Secondary.TButton", command=handle_next)
    next_btn.pack(side="left", padx=(0, 16))

    ttk.Button(controls, text="-5 min", style="Secondary.TButton",
               command=lambda: state.adjust_overall_time(-300)).pack(side="left", padx=2)
    ttk.Button(controls, text="+5 min", style="Secondary.TButton",
               command=lambda: state.adjust_overall_time(300)).pack(side="left", padx=2)

    def custom_add() -> None:
        minutes = ask_minutes(ctx.root, "Add time", "Minutes to add to the meeting:", 5)
        if minutes:
            state.adjust_overall_time(minutes * 60)

    def custom_subtract() -> None:
        minutes = ask_minutes(ctx.root, "Subtract time", "Minutes to subtract from the meeting:", 5)
        if minutes:
            state.adjust_overall_time(-minutes * 60)

    ttk.Button(controls, text="Custom +", style="Secondary.TButton", command=custom_add).pack(side="left", padx=2)
    ttk.Button(controls, text="Custom -", style="Secondary.TButton", command=custom_subtract).pack(side="left", padx=2)
    ttk.Button(controls, text="Open Presentation Window", style="Secondary.TButton",
               command=lambda: presentation.open_presentation(ctx)).pack(side="right")

    extra_frame = ttk.Frame(frame)
    extra_frame.pack(fill="x", pady=(0, 12))

    ttk.Label(frame, text="Agenda", style="SectionHeading.TLabel").pack(anchor="w", pady=(4, 8))
    agenda_frame = ttk.Frame(frame)
    agenda_frame.pack(fill="x", pady=(0, 16))

    def render_agenda() -> None:
        for child in agenda_frame.winfo_children():
            child.destroy()
        for idx, segment in enumerate(state.segments):
            is_current = idx == state.current_index
            is_done = idx < state.current_index
            bg = theme.SUBTLE_BG if is_current else theme.CARD_BG
            fg = theme.MUTED if is_done else theme.INK
            row = tk.Frame(
                agenda_frame, background=bg, cursor="hand2",
                highlightbackground=theme.PRIMARY if is_current else theme.LINE,
                highlightthickness=2 if is_current else 1,
            )
            row.pack(fill="x", pady=2)
            name_label = tk.Label(
                row, text=segment.name, background=bg, foreground=fg,
                font=("Segoe UI", 10, "bold" if is_current else "normal"),
            )
            name_label.pack(side="left", padx=12, pady=8)
            dur_label = tk.Label(row, text=f"{segment.duration_minutes} min", background=bg, foreground=fg,
                                  font=("Segoe UI", 9))
            dur_label.pack(side="right", padx=12, pady=8)
            for widget in (row, name_label, dur_label):
                widget.bind("<Button-1>", lambda _e, i=idx: state.jump_to_segment(i))

    # --- Personal notes (collapsible) ---
    notes_toggle_btn = ttk.Button(frame, text="▸ Notes", style="Secondary.TButton")
    notes_toggle_btn.pack(anchor="w", pady=(0, 4))

    notes_body = ttk.Frame(frame)
    notes_text = tk.Text(notes_body, height=6, width=70, wrap="word", font=("Segoe UI", 9))
    notes_text.pack(fill="x", pady=(4, 0))

    try:
        occ = cfgmod.get_occurrence(state.occurrence_key)
    except cfgmod.DataLoadError:
        occ = None
    if occ and occ.notes:
        notes_text.insert("1.0", occ.notes)

    notes_visible = {"value": False}

    def toggle_notes() -> None:
        notes_visible["value"] = not notes_visible["value"]
        if notes_visible["value"]:
            notes_body.pack(fill="x")
            notes_toggle_btn.configure(text="▾ Notes")
        else:
            notes_body.pack_forget()
            notes_toggle_btn.configure(text="▸ Notes")

    notes_toggle_btn.configure(command=toggle_notes)

    def save_notes(_event=None) -> None:
        _save_notes(ctx, state.occurrence_key, notes_text.get("1.0", "end-1c"))

    notes_text.bind("<FocusOut>", save_notes)

    # --- Live refresh ---
    last_rendered_index = {"value": None}

    def refresh() -> None:
        if ctx.run_state is None:
            return
        current_state = ctx.run_state
        segment = current_state.current_segment
        segment_label.configure(text=segment.name if segment else "Meeting complete")

        segment_time = rs.format_mmss(current_state.segment_remaining_seconds)
        if current_state.segment_over_time:
            countdown_label.configure(text=f"+{segment_time}", foreground=theme.DANGER)
        else:
            countdown_label.configure(text=segment_time, foreground=theme.INK)

        overall_time = rs.format_mmss(current_state.overall_remaining_seconds)
        prefix = "+" if current_state.overall_over_time else ""
        overall_label.configure(text=f"{prefix}{overall_time} left in meeting")

        toggle_btn.configure(text="Pause" if current_state.running else "Resume")
        next_btn.configure(text="End Meeting" if current_state.is_last_segment else "Next Segment →")

        if last_rendered_index["value"] != current_state.current_index:
            render_agenda()
            for child in extra_frame.winfo_children():
                child.destroy()
            if segment is not None:
                st.get_segment_type(segment.type_id).render_run_view(extra_frame, segment)
            last_rendered_index["value"] = current_state.current_index

    refresh()
    ctx.run_state.add_listener(refresh)
    frame.bind("<Destroy>", lambda _e: ctx.run_state.remove_listener(refresh) if ctx.run_state else None)


def _save_notes(ctx, occurrence_key: str, text: str) -> None:
    try:
        occ = cfgmod.get_occurrence(occurrence_key)
    except cfgmod.DataLoadError:
        show_error_banner(
            ctx, "Data/occurrences.json couldn't be read - notes couldn't be saved.",
        )
        return

    if occ is None:
        try:
            view = cfgmod.resolve_occurrence_view(ctx.config, occurrence_key)
        except cfgmod.DataLoadError:
            view = None
        if view is None:
            return
        occ = cfgmod.Occurrence(
            id=occurrence_key, date=view["date"], repeating_instance_id=view["repeating_instance_id"],
            title=view["title"], schedule_id=view["schedule_id"], overrides=[],
        )

    occ.notes = text
    cfgmod.save_occurrence(occ, key=occurrence_key)
