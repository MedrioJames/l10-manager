"""Persistent mid-meeting indicator bar - the mechanism that lets you flip
to Issues/Settings while a meeting is running without losing the timer.
Packed into ctx.indicator_slot (see ui/shell.py::AppShell._build_layout),
a slot reserved above ctx.content specifically so this bar pushes content
down instead of overlapping it - an earlier place()-overlay approach on
ctx.root covered up screen titles underneath it. ctx.indicator_slot itself
survives AppShell.navigate()'s teardown of ctx.content (it's a sibling, not
a child, of content), so this still rides ctx.run_state's existing 1Hz tick
rather than running a second timer, and tears itself down when the run ends.
"""

import tkinter as tk

import run_state as rs
from ui import icon_button, theme

BAR_HEIGHT = 40


def mount(ctx) -> None:
    if ctx.run_indicator is not None:
        return

    bar = tk.Frame(ctx.indicator_slot, background=theme.PRIMARY_DARK, height=BAR_HEIGHT)
    bar.pack(fill="x")
    bar.pack_propagate(False)
    ctx.run_indicator = bar

    label = tk.Label(
        bar, text="", background=theme.PRIMARY_DARK, foreground="white",
        font=("Segoe UI", 9, "bold"), anchor="w",
    )
    label.pack(side="left", padx=(16, 8), fill="x", expand=True)

    button_row = tk.Frame(bar, background=theme.PRIMARY_DARK)
    button_row.pack(side="right", padx=12)

    def toggle_pause() -> None:
        if ctx.run_state is not None:
            ctx.run_state.toggle_start_pause()

    def back_to_run() -> None:
        if ctx.run_state is not None:
            ctx.navigate("run_meeting", occurrence_key=ctx.run_state.occurrence_key)

    def present() -> None:
        from ui import presentation
        presentation.open_presentation(ctx)

    pause_btn = icon_button.icon_button(button_row, "⏸", toggle_pause, background=theme.PRIMARY_DARK)
    pause_btn.configure(foreground="white", activeforeground="white")
    pause_btn.pack(side="left", padx=2)

    back_btn = tk.Button(
        button_row, text="Back to Run", command=back_to_run, relief="flat", bd=0,
        background=theme.PRIMARY_DARK, foreground="white", activebackground=theme.PRIMARY,
        activeforeground="white", font=("Segoe UI", 9), cursor="hand2", padx=8,
    )
    back_btn.pack(side="left", padx=2)

    present_btn = tk.Button(
        button_row, text="Present", command=present, relief="flat", bd=0,
        background=theme.PRIMARY_DARK, foreground="white", activebackground=theme.PRIMARY,
        activeforeground="white", font=("Segoe UI", 9), cursor="hand2", padx=8,
    )
    present_btn.pack(side="left", padx=2)

    def refresh() -> None:
        if ctx.run_state is None or ctx.run_state.ended:
            _teardown()
            return
        if not bar.winfo_exists():
            return

        state = ctx.run_state
        segment = state.current_segment
        segment_name = segment.name if segment else "Meeting"
        segment_time = rs.format_mmss(state.segment_remaining_seconds)
        if state.segment_over_time:
            segment_time = f"+{segment_time} over"
        overall_time = rs.format_mmss(state.overall_remaining_seconds)
        if state.overall_over_time:
            overall_time = f"+{overall_time} over"

        status = "Running" if state.running else "Paused"
        icon = "●" if state.running else "⏸"
        label.configure(
            text=f"{icon} {status} - {segment_name} - {segment_time} left · {overall_time} meeting",
            foreground=theme.WARNING_ON_DARK if state.segment_over_time else "white",
        )
        pause_btn.configure(text="⏸" if state.running else "▶")

        # "Back to Run" is a link TO the Run Meeting screen - showing it
        # while already there is a dead, confusing no-op a real user
        # pointed out directly. This can't rely on run_state's own 1Hz
        # tick to catch a navigation change (a PAUSED run never ticks), so
        # it's re-checked from the dedicated screen-change hook below too,
        # not just from here.
        if ctx.current_screen_key == "run_meeting":
            back_btn.pack_forget()
        else:
            back_btn.pack(side="left", padx=2, before=present_btn)

    def _teardown() -> None:
        if ctx.run_state is not None:
            ctx.run_state.remove_listener(refresh)
        ctx.remove_screen_change_listener(refresh)
        if bar.winfo_exists():
            bar.destroy()
        ctx.run_indicator = None

    ctx.run_state.add_listener(refresh)
    ctx.add_screen_change_listener(refresh)
    refresh()
