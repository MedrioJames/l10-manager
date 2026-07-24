"""The Run Meeting screen - live control for an active meeting run: current
segment + countdown, a progress bar across the whole agenda, start/pause,
advance early, jump to any segment, open the presentation window, and a
collapsible personal-notes panel. Reuses the same effective-schedule row
style already used by ui/prep.py/ui/schedule_editor.py rather than
inventing a new list widget.

start_meeting(ctx, view) is the entry point Prep calls to begin a run: it
computes the effective schedule once, builds a run_state.MeetingRunState,
mounts the persistent indicator bar, and navigates here.

There is no independent "meeting time" adjustment - a real user pointed out
the meeting's remaining time is simply a product of the segments, so
run_state.py derives it from segment durations rather than tracking it
separately (see MeetingRunState.overall_remaining_seconds). Adjusting a
segment's duration is the ONLY way to change how much time is left, and it
happens in exactly one place: the "Segment Settings" panel to the right of
the Agenda list, which shows Duration/Remaining/Display controls for
whichever segment was selected (via a row's small edit icon) - or, by
default, whichever segment is currently active ("follow" mode). This is
also where "adjust another segment's display before presenting it" happens,
since the panel isn't limited to the current segment.
"""

import datetime as dt

import tkinter as tk
from tkinter import messagebox, ttk

import config as cfgmod
import run_state as rs
import schedule as sch
import segment_types as st
from ui import icon_button, meeting_complete, presentation, run_indicator, theme
from ui.notifications import show_error_banner
from ui.occurrence_list import render_occurrence_list
from ui.progress_bar import ProgressBar
from ui.rounded_button import RoundedButton
from ui.rounded_card import RoundedCard
from ui.scrollable import ScrollableFrame

DURATION_MIN = 1
DURATION_MAX = 180


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
    # never leaves a gap where the other used to be, and there's no
    # widget-reordering to get wrong when a hidden one is turned back on.
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

    # --- "Time left in meeting" - also individually toggleable (same
    # rebuild-not-hide reasoning as the header above).
    meeting_time_frame = ttk.Frame(frame)
    meeting_time_frame.pack(fill="x", pady=(0, 12))
    meeting_time_widgets = {"label": None}

    def rebuild_meeting_time(seg_config: dict) -> None:
        for child in meeting_time_frame.winfo_children():
            child.destroy()
        meeting_time_widgets["label"] = None
        if seg_config.get(st.FIELD_SHOW_MEETING_TIME_REMAINING, True):
            lbl = ttk.Label(meeting_time_frame, text="", style="Body.TLabel")
            lbl.pack(anchor="w")
            meeting_time_widgets["label"] = lbl

    progress_bar = ProgressBar(frame)
    progress_bar.pack(fill="x", pady=(0, 20))

    controls = ttk.Frame(frame)
    controls.pack(fill="x", pady=(0, 20))

    toggle_btn = RoundedButton(controls, text="Pause", variant="filled", command=state.toggle_start_pause)
    toggle_btn.pack(side="left", padx=(0, 8))

    def handle_next() -> None:
        was_last = state.is_last_segment
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

    show_progress_in_pres_var = tk.BooleanVar(value=ctx.config.show_progress_bar_in_presentation)

    def toggle_progress_in_presentation() -> None:
        ctx.config.show_progress_bar_in_presentation = show_progress_in_pres_var.get()
        ctx.save_config()

    ttk.Checkbutton(
        frame, text="Show progress bar in presentation window", variable=show_progress_in_pres_var,
        command=toggle_progress_in_presentation,
    ).pack(anchor="w", pady=(0, 12))

    # Additive per-segment-type content (To-Do list, IDS list, Conclude
    # ratings, etc. - see segment_types.py::render_run_view()) - generic
    # segments render nothing extra here.
    extra_frame = ttk.Frame(frame)
    extra_frame.pack(fill="x", pady=(0, 20))

    # --- Agenda (left) + Segment Settings (right) -----------------------
    # Agenda no longer needs the whole width once the per-row time-adjust
    # buttons move into the settings panel - a real user suggested using
    # the freed space this way rather than just leaving it empty.
    columns_frame = ttk.Frame(frame)
    columns_frame.pack(fill="both", expand=True)

    agenda_col = ttk.Frame(columns_frame)
    agenda_col.pack(side="left", fill="both", expand=True, padx=(0, 20))
    ttk.Label(agenda_col, text="Agenda", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 8))
    agenda_frame = ttk.Frame(agenda_col)
    agenda_frame.pack(fill="x")

    settings_col = ttk.Frame(columns_frame, width=300)
    settings_col.pack(side="left", fill="y")
    settings_col.pack_propagate(False)
    ttk.Label(settings_col, text="Segment Settings", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 8))
    settings_frame = ttk.Frame(settings_col)
    settings_frame.pack(fill="x")

    # None = "follow" the currently active segment; an explicit index pins
    # the panel to that segment (e.g. to adjust an upcoming one) until
    # reset. This is what lets a segment other than the current one be
    # adjusted - both its duration and its own display toggles - without
    # jumping the meeting to it.
    selected_settings_index = {"value": None}
    settings_state = {"remaining_label": None, "is_current": False, "segment": None}

    def select_for_settings(idx: int) -> None:
        selected_settings_index["value"] = idx
        render_settings_panel()

    def reset_to_current() -> None:
        selected_settings_index["value"] = None
        render_settings_panel()

    def render_settings_panel() -> None:
        for child in settings_frame.winfo_children():
            child.destroy()
        effective_index = (
            selected_settings_index["value"] if selected_settings_index["value"] is not None else state.current_index
        )
        if not (0 <= effective_index < len(state.segments)):
            settings_state["remaining_label"] = None
            settings_state["is_current"] = False
            settings_state["segment"] = None
            return
        segment = state.segments[effective_index]
        is_current = effective_index == state.current_index

        ttk.Label(settings_frame, text=segment.name, style="CardTitle.TLabel").pack(anchor="w")
        if is_current:
            ttk.Label(settings_frame, text="(current segment)", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        else:
            RoundedButton(
                settings_frame, text="← Back to current segment", variant="tonal", command=reset_to_current,
            ).pack(anchor="w", pady=(4, 8))

        ttk.Label(settings_frame, text="Duration (min)", style="Label.TLabel").pack(anchor="w", pady=(4, 2))
        duration_var = tk.StringVar(value=str(segment.duration_minutes))

        def apply_duration(*_args, seg=segment, idx=effective_index) -> None:
            try:
                new_value = int(duration_var.get())
            except ValueError:
                return
            new_value = max(DURATION_MIN, min(DURATION_MAX, new_value))
            delta = new_value - seg.duration_minutes
            if delta != 0:
                state.adjust_segment_duration(idx, delta)

        duration_spin = ttk.Spinbox(
            settings_frame, from_=DURATION_MIN, to=DURATION_MAX, textvariable=duration_var, width=6,
            command=apply_duration,
        )
        duration_spin.pack(anchor="w")
        duration_spin.bind("<FocusOut>", apply_duration)
        duration_spin.bind("<Return>", apply_duration)

        remaining_label = None
        if is_current:
            ttk.Label(settings_frame, text="Remaining", style="Label.TLabel").pack(anchor="w", pady=(10, 2))
            remaining_label = ttk.Label(settings_frame, text="", style="Body.TLabel")
            remaining_label.pack(anchor="w")

        # The FULL reflected settings form - universal Display fields AND
        # whatever this segment's own type adds (Todo's show_open/show_done,
        # Generic's display_text, etc.) - the same form segment_editor.py
        # and segment_override_form.py already use, so editing here during
        # a live meeting is genuinely the same "meeting prep override"
        # surface, not a smaller live-only subset of it.
        ttk.Label(settings_frame, text="Display", style="Label.TLabel").pack(anchor="w", pady=(14, 4))
        config_frame = ttk.Frame(settings_frame)
        config_frame.pack(fill="x")

        def on_config_change(seg=segment, current=is_current) -> None:
            if current:
                rebuild_header(seg.config)
                rebuild_meeting_time(seg.config)
            state.notify_display_config_changed()

        st.get_segment_type(segment.type_id).render_settings_form(config_frame, segment.config, on_config_change)

        settings_state["remaining_label"] = remaining_label
        settings_state["is_current"] = is_current
        settings_state["segment"] = segment

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
                widget.bind("<Button-1>", lambda _e, i=idx: state.jump_to_segment(i))

            right_box = tk.Frame(row, background=bg)
            right_box.pack(side="right", padx=(4, 8), pady=4)
            dur_label = tk.Label(
                right_box, text=f"{segment.duration_minutes} min", background=bg, foreground=fg,
                font=("Segoe UI", 9), width=7, anchor="e",
            )
            dur_label.pack(side="left", padx=(0, 2))
            icon_button.icon_button(
                right_box, icon_button.GLYPH_EDIT, lambda i=idx: select_for_settings(i), background=bg,
            ).pack(side="left")

    # --- Personal notes (collapsible) ---
    notes_toggle_btn = RoundedButton(frame, text="▸ Notes", variant="tonal")
    notes_toggle_btn.pack(anchor="w", pady=(20, 4))

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
    last_extra_signature = {"value": None}
    last_agenda_signature = {"value": None}
    last_settings_signature = {"value": None}

    def refresh() -> None:
        if ctx.run_state is None:
            return
        current_state = ctx.run_state
        segment = current_state.current_segment
        seg_config = segment.config if segment is not None else {}

        if last_rendered_index["value"] != current_state.current_index:
            rebuild_header(seg_config)
            rebuild_meeting_time(seg_config)
            last_rendered_index["value"] = current_state.current_index

        if header_widgets["segment_label"] is not None:
            header_widgets["segment_label"].configure(text=segment.name if segment else "Meeting complete")

        segment_time = rs.format_mmss(current_state.segment_remaining_seconds)
        if header_widgets["countdown_label"] is not None:
            if current_state.segment_over_time:
                header_widgets["countdown_label"].configure(text=f"+{segment_time}", foreground=theme.DANGER)
            else:
                header_widgets["countdown_label"].configure(text=segment_time, foreground=theme.INK)

        if meeting_time_widgets["label"] is not None:
            overall_time = rs.format_mmss(current_state.overall_remaining_seconds)
            prefix = "+" if current_state.overall_over_time else ""
            end_time_text = _projected_end_time_text(current_state.overall_remaining_seconds)
            meeting_time_widgets["label"].configure(
                text=(
                    f"{prefix}{overall_time} left in meeting (ends ~{end_time_text})  ·  "
                    f"Total meeting length: {current_state.total_length_minutes} min"
                ),
            )

        progress_bar.update_state(current_state.segments, current_state.current_index, current_state.segment_remaining_seconds)

        toggle_btn.configure(text="Pause" if current_state.running else "Resume")
        next_btn.configure(text="Finish Meeting" if current_state.is_last_segment else "Next Segment →")

        agenda_signature = (
            current_state.current_index, tuple(s.duration_minutes for s in current_state.segments),
        )
        if last_agenda_signature["value"] != agenda_signature:
            render_agenda()
            last_agenda_signature["value"] = agenda_signature

        # The settings panel only rebuilds on a SELECTION change or (in
        # follow mode) a current-segment change - never on a duration edit,
        # since the only way a duration changes for whichever segment the
        # panel is showing is through that same panel's own Spinbox, and
        # rebuilding out from under an in-progress edit would fight the
        # user's own typing/focus.
        settings_signature = (selected_settings_index["value"], current_state.current_index)
        if last_settings_signature["value"] != settings_signature:
            render_settings_panel()
            last_settings_signature["value"] = settings_signature

        if settings_state["remaining_label"] is not None and settings_state["is_current"]:
            remaining_text = rs.format_mmss(current_state.segment_remaining_seconds)
            if current_state.segment_over_time:
                remaining_text = f"+{remaining_text} over"
            settings_state["remaining_label"].configure(text=remaining_text)

        extra_signature = (current_state.current_index, current_state.display_config_version)
        if last_extra_signature["value"] != extra_signature:
            for child in extra_frame.winfo_children():
                child.destroy()
            if segment is not None:
                st.get_segment_type(segment.type_id).render_run_view(extra_frame, segment, ctx)
            last_extra_signature["value"] = extra_signature

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
