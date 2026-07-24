"""The Run Meeting screen - live control for an active meeting run: current
segment + countdown, overall time remaining, start/pause, advance early,
jump to any segment, adjust the meeting clock, open the presentation
window, and a collapsible personal-notes panel. Reuses the same
effective-schedule row style already used by ui/prep.py/ui/schedule_editor.py
rather than inventing a new list widget.

start_meeting(ctx, view) is the entry point Prep calls to begin a run: it
computes the effective schedule once, builds a run_state.MeetingRunState,
mounts the persistent indicator bar, and navigates here.

Time-adjustment controls are split into two scopes, both inline on this
screen (no popups - a real user asked for this directly, since the old
"Custom +/-" buttons opened a modal Toplevel dialog just to type a number):
"This Segment" adjusts only the currently active segment (and, if that
changes the agenda's total length, offers an inline invite - not a popup -
to apply the same change to the meeting's remaining time); "Meeting Time"
adjusts the overall countdown directly, independent of any one segment.
The Agenda list's own per-row +/- buttons let ANY segment be rebalanced
(e.g. take 5 min from IDS, give it to Scorecard) without touching the
overall meeting length at all unless the same inline invite is accepted.
"""

import datetime as dt

import tkinter as tk
from tkinter import messagebox, ttk

import config as cfgmod
import run_state as rs
import schedule as sch
import segment_types as st
from ui import meeting_complete, presentation, run_indicator, theme
from ui.notifications import show_error_banner
from ui.occurrence_list import render_occurrence_list
from ui.rounded_button import RoundedButton
from ui.rounded_card import RoundedCard
from ui.scrollable import ScrollableFrame

QUICK_STEP_MINUTES = 5


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
    if ctx.run_state is None:
        frame = ttk.Frame(ctx.content)
        frame.pack(fill="both", expand=True, padx=32, pady=28)
        ttk.Label(frame, text="Run Meeting", style="Heading.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Label(
            frame, text="No meeting is currently running - pick one below to start.", style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 16))
        render_occurrence_list(frame, ctx, on_pick=lambda v: start_meeting(ctx, v), button_label="Start Meeting")
        return

    if ctx.run_state.ended:
        meeting_complete.build(ctx)
        return

    _render_active(ctx)


def _projected_end_time_text(overall_remaining_seconds: float) -> str:
    end = dt.datetime.now() + dt.timedelta(seconds=max(0.0, overall_remaining_seconds))
    return end.strftime("%I:%M %p").lstrip("0") or "12:00 AM"


def _parse_spinbox_minutes(raw: str, fallback: int = QUICK_STEP_MINUTES) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return fallback
    return max(1, value)


def _render_active(ctx) -> None:
    scroll = ScrollableFrame(ctx.content)
    scroll.pack(fill="both", expand=True)
    frame = ttk.Frame(scroll.body)
    frame.pack(fill="both", expand=True, padx=32, pady=28)

    state = ctx.run_state

    # --- Segment title / countdown - each individually toggleable via the
    # segment's own display config (universal show_segment_title/
    # show_time_remaining fields - see segment_types.py::DisplayConfig).
    # Rebuilt (not just hidden) on a segment/config change so hiding one
    # never leaves a gap where the other used to be, and so there's no
    # widget reordering to get wrong when a hidden one is turned back on.
    header_frame = ttk.Frame(frame)
    header_frame.pack(fill="x", anchor="w")
    header_widgets = {"segment_label": None, "countdown_label": None}

    def rebuild_header(seg_config: dict) -> None:
        for child in header_frame.winfo_children():
            child.destroy()
        header_widgets["segment_label"] = None
        header_widgets["countdown_label"] = None
        if seg_config.get(st.FIELD_SHOW_SEGMENT_TITLE, True):
            lbl = ttk.Label(header_frame, text="", style="Heading.TLabel")
            lbl.pack(anchor="w")
            header_widgets["segment_label"] = lbl
        if seg_config.get(st.FIELD_SHOW_TIME_REMAINING, True):
            lbl = tk.Label(header_frame, text="", background=theme.BG, font=("Segoe UI", 44, "bold"))
            lbl.pack(anchor="w", pady=(4, 4))
            header_widgets["countdown_label"] = lbl

    # --- Display (per-segment, live, no popup) --------------------------
    # Lets the two universal toggles above be flipped mid-meeting for the
    # CURRENT segment - a real user asked for this to be adjustable live,
    # with a preview; this screen IS the preview, since toggling a
    # checkbox here immediately rebuilds the header above via the same
    # mechanism a real config change would trigger.
    ttk.Label(frame, text="Display", style="Label.TLabel").pack(anchor="w", pady=(0, 2))
    display_controls = ttk.Frame(frame)
    display_controls.pack(fill="x", pady=(0, 8))
    show_title_var = tk.BooleanVar(value=True)
    show_time_var = tk.BooleanVar(value=True)

    def apply_display_toggle(key: str, var: tk.BooleanVar) -> None:
        segment = state.current_segment
        if segment is None:
            return
        segment.config[key] = var.get()
        rebuild_header(segment.config)
        state.notify_display_config_changed()

    ttk.Checkbutton(
        display_controls, text="Show segment title", variable=show_title_var,
        command=lambda: apply_display_toggle(st.FIELD_SHOW_SEGMENT_TITLE, show_title_var),
    ).pack(side="left", padx=(0, 16))
    ttk.Checkbutton(
        display_controls, text="Show time remaining", variable=show_time_var,
        command=lambda: apply_display_toggle(st.FIELD_SHOW_TIME_REMAINING, show_time_var),
    ).pack(side="left")

    # --- Inline "apply the same change to the meeting" invite -----------
    # Appears right here (never a popup) whenever a segment adjustment
    # (current or from the Agenda list below) changes the agenda's total
    # length - a real user asked to be "invited" to also extend/shrink the
    # meeting's remaining time by the same amount, as a choice, not an
    # automatic side effect.
    invite_frame = ttk.Frame(frame)

    def dismiss_invite() -> None:
        for child in invite_frame.winfo_children():
            child.destroy()
        invite_frame.pack_forget()

    def offer_length_invite(segment_name: str, applied_delta_minutes: int) -> None:
        if applied_delta_minutes == 0:
            return
        dismiss_invite()

        def accept() -> None:
            state.adjust_overall_time(applied_delta_minutes * 60)
            dismiss_invite()

        sign = "+" if applied_delta_minutes > 0 else ""
        card = RoundedCard(invite_frame, background=theme.SUBTLE_BG, border_color=theme.PRIMARY, border_width=1)
        card.pack(fill="x")
        row = card.body
        tk.Label(
            row, text=(
                f"{segment_name} changed by {sign}{applied_delta_minutes} min. "
                f"Apply the same change to the meeting's remaining time?"
            ),
            background=theme.SUBTLE_BG, foreground=theme.INK, font=("Segoe UI", 9),
            wraplength=520, justify="left",
        ).pack(side="left", padx=(12, 8), pady=10, fill="x", expand=True)
        btns = tk.Frame(row, background=theme.SUBTLE_BG)
        btns.pack(side="right", padx=8)
        RoundedButton(btns, text="Yes", variant="filled", command=accept).pack(side="left", padx=2)
        RoundedButton(btns, text="No thanks", variant="tonal", command=dismiss_invite).pack(side="left", padx=2)
        invite_frame.pack(fill="x", pady=(0, 12))

    def apply_segment_delta(index: int, delta_minutes: int) -> None:
        if not (0 <= index < len(state.segments)):
            return
        segment_name = state.segments[index].name
        applied = state.adjust_segment_duration(index, delta_minutes)
        offer_length_invite(segment_name, applied)

    # --- This Segment (adjusts only the currently active segment) ------
    ttk.Label(frame, text="This Segment", style="Label.TLabel").pack(anchor="w", pady=(0, 2))
    this_segment_controls = ttk.Frame(frame)
    this_segment_controls.pack(fill="x", pady=(0, 4))

    RoundedButton(
        this_segment_controls, text=f"-{QUICK_STEP_MINUTES} min", variant="tonal",
        command=lambda: apply_segment_delta(state.current_index, -QUICK_STEP_MINUTES),
    ).pack(side="left", padx=2)
    RoundedButton(
        this_segment_controls, text=f"+{QUICK_STEP_MINUTES} min", variant="tonal",
        command=lambda: apply_segment_delta(state.current_index, QUICK_STEP_MINUTES),
    ).pack(side="left", padx=2)

    segment_custom_var = tk.StringVar(value=str(QUICK_STEP_MINUTES))
    ttk.Spinbox(
        this_segment_controls, from_=1, to=120, textvariable=segment_custom_var, width=4,
    ).pack(side="left", padx=(12, 4))
    RoundedButton(
        this_segment_controls, text="Add", variant="tonal",
        command=lambda: apply_segment_delta(state.current_index, _parse_spinbox_minutes(segment_custom_var.get())),
    ).pack(side="left", padx=2)
    RoundedButton(
        this_segment_controls, text="Subtract", variant="tonal",
        command=lambda: apply_segment_delta(state.current_index, -_parse_spinbox_minutes(segment_custom_var.get())),
    ).pack(side="left", padx=2)

    invite_frame.pack(fill="x", pady=(0, 12))
    dismiss_invite()  # starts collapsed; only shown when there's something to invite

    overall_label = ttk.Label(frame, text="", style="Body.TLabel")
    overall_label.pack(anchor="w", pady=(0, 16))

    controls = ttk.Frame(frame)
    controls.pack(fill="x", pady=(0, 8))

    toggle_btn = RoundedButton(controls, text="Pause", variant="filled", command=state.toggle_start_pause)
    toggle_btn.pack(side="left", padx=(0, 8))

    def handle_next() -> None:
        was_last = state.is_last_segment
        dismiss_invite()
        state.advance_to_next()
        if was_last:
            ctx.navigate("run_meeting")

    next_btn = RoundedButton(controls, text="Next Segment →", variant="tonal", command=handle_next)
    next_btn.pack(side="left", padx=(0, 8))

    def end_meeting_now() -> None:
        if messagebox.askyesno("End meeting", "End this meeting now? This can't be undone."):
            state.stop()
            ctx.navigate("run_meeting")

    RoundedButton(controls, text="End Meeting...", variant="tonal", command=end_meeting_now).pack(side="left", padx=(0, 16))
    RoundedButton(controls, text="Open Presentation Window", variant="tonal",
               command=lambda: presentation.open_presentation(ctx)).pack(side="right")

    # --- Meeting Time (adjusts the overall countdown directly) ---------
    ttk.Label(frame, text="Meeting Time", style="Label.TLabel").pack(anchor="w", pady=(4, 2))
    meeting_time_controls = ttk.Frame(frame)
    meeting_time_controls.pack(fill="x", pady=(0, 20))

    RoundedButton(
        meeting_time_controls, text=f"-{QUICK_STEP_MINUTES} min", variant="tonal",
        command=lambda: state.adjust_overall_time(-QUICK_STEP_MINUTES * 60),
    ).pack(side="left", padx=2)
    RoundedButton(
        meeting_time_controls, text=f"+{QUICK_STEP_MINUTES} min", variant="tonal",
        command=lambda: state.adjust_overall_time(QUICK_STEP_MINUTES * 60),
    ).pack(side="left", padx=2)

    meeting_custom_var = tk.StringVar(value=str(QUICK_STEP_MINUTES))
    ttk.Spinbox(
        meeting_time_controls, from_=1, to=240, textvariable=meeting_custom_var, width=4,
    ).pack(side="left", padx=(12, 4))
    RoundedButton(
        meeting_time_controls, text="Add", variant="tonal",
        command=lambda: state.adjust_overall_time(_parse_spinbox_minutes(meeting_custom_var.get()) * 60),
    ).pack(side="left", padx=2)
    RoundedButton(
        meeting_time_controls, text="Subtract", variant="tonal",
        command=lambda: state.adjust_overall_time(-_parse_spinbox_minutes(meeting_custom_var.get()) * 60),
    ).pack(side="left", padx=2)

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
            card = RoundedCard(
                agenda_frame, background=bg,
                border_color=theme.PRIMARY if is_current else theme.LINE,
                border_width=2 if is_current else 1,
            )
            card.pack(fill="x", pady=2)
            row = card.body
            row.configure(cursor="hand2")
            name_label = tk.Label(
                row, text=segment.name, background=bg, foreground=fg,
                font=("Segoe UI", 10, "bold" if is_current else "normal"), cursor="hand2",
            )
            name_label.pack(side="left", padx=12, pady=8)
            for widget in (row, name_label):
                widget.bind("<Button-1>", lambda _e, i=idx: (dismiss_invite(), state.jump_to_segment(i)))

            # Per-row rebalancing - lets ANY segment's length change (not
            # just the current one), e.g. take 5 min from IDS and give it
            # to Scorecard rather than extending the whole meeting. These
            # are separate widgets from the row's own jump-to-segment
            # binding above, so clicking them never also jumps.
            adjust_box = tk.Frame(row, background=bg)
            adjust_box.pack(side="right", padx=(4, 12), pady=4)
            RoundedButton(
                adjust_box, text="−", variant="tonal",
                command=lambda i=idx: apply_segment_delta(i, -QUICK_STEP_MINUTES),
            ).pack(side="left", padx=1)
            dur_label = tk.Label(
                adjust_box, text=f"{segment.duration_minutes} min", background=bg, foreground=fg,
                font=("Segoe UI", 9), width=7, anchor="center",
            )
            dur_label.pack(side="left", padx=4)
            RoundedButton(
                adjust_box, text="+", variant="tonal",
                command=lambda i=idx: apply_segment_delta(i, QUICK_STEP_MINUTES),
            ).pack(side="left", padx=1)

    # --- Personal notes (collapsible) ---
    notes_toggle_btn = RoundedButton(frame, text="▸ Notes", variant="tonal")
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
    last_agenda_signature = {"value": None}

    def refresh() -> None:
        if ctx.run_state is None:
            return
        current_state = ctx.run_state
        segment = current_state.current_segment
        seg_config = segment.config if segment is not None else {}

        if last_rendered_index["value"] != current_state.current_index:
            rebuild_header(seg_config)
            show_title_var.set(seg_config.get(st.FIELD_SHOW_SEGMENT_TITLE, True))
            show_time_var.set(seg_config.get(st.FIELD_SHOW_TIME_REMAINING, True))

        if header_widgets["segment_label"] is not None:
            header_widgets["segment_label"].configure(text=segment.name if segment else "Meeting complete")

        segment_time = rs.format_mmss(current_state.segment_remaining_seconds)
        if header_widgets["countdown_label"] is not None:
            if current_state.segment_over_time:
                header_widgets["countdown_label"].configure(text=f"+{segment_time}", foreground=theme.DANGER)
            else:
                header_widgets["countdown_label"].configure(text=segment_time, foreground=theme.INK)

        overall_time = rs.format_mmss(current_state.overall_remaining_seconds)
        prefix = "+" if current_state.overall_over_time else ""
        end_time_text = _projected_end_time_text(current_state.overall_remaining_seconds)
        overall_label.configure(
            text=(
                f"{prefix}{overall_time} left in meeting (ends ~{end_time_text})  ·  "
                f"Total meeting length: {current_state.total_length_minutes} min"
            ),
        )

        toggle_btn.configure(text="Pause" if current_state.running else "Resume")
        next_btn.configure(text="Finish Meeting" if current_state.is_last_segment else "Next Segment →")

        agenda_signature = (
            current_state.current_index, tuple(s.duration_minutes for s in current_state.segments),
        )
        if last_agenda_signature["value"] != agenda_signature:
            render_agenda()
            last_agenda_signature["value"] = agenda_signature

        if last_rendered_index["value"] != current_state.current_index:
            dismiss_invite()
            for child in extra_frame.winfo_children():
                child.destroy()
            if segment is not None:
                st.get_segment_type(segment.type_id).render_run_view(extra_frame, segment, ctx)
            last_rendered_index["value"] = current_state.current_index

    refresh()
    ctx.run_state.add_listener(refresh)
    frame.bind("<Destroy>", lambda _e: ctx.run_state.remove_listener(refresh) if ctx.run_state else None)


def _save_notes(ctx, occurrence_key: str, text: str) -> None:
    try:
        occ = cfgmod.get_or_create_occurrence(ctx.config, occurrence_key)
    except cfgmod.DataLoadError:
        show_error_banner(
            ctx, "Data/occurrences.json couldn't be read - notes couldn't be saved.",
        )
        return
    if occ is None:
        return

    occ.notes = text
    cfgmod.save_occurrence(occ, key=occurrence_key)
