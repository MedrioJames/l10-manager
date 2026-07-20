"""Persistent mid-meeting indicator bar - the mechanism that lets you flip
to Issues/Scorecard/Settings while a meeting is running without losing the
timer. Modeled directly on ui/notifications.py's root-parented,
self-rescheduling pattern: this Frame is parented to ctx.root (not
ctx.content), so AppShell.navigate()'s teardown of ctx.content's children
never touches it. It rides ctx.run_state's existing 1Hz tick rather than
running a second timer, and tears itself down when the run ends.
"""

import tkinter as tk

import run_state as rs
from ui import icon_button, theme

BAR_HEIGHT = 40
SIDEBAR_WIDTH = 180


def mount(ctx) -> None:
    if ctx.run_indicator is not None:
        return

    bar = tk.Frame(ctx.root, background=theme.PRIMARY_DARK, height=BAR_HEIGHT)
    bar.place(x=SIDEBAR_WIDTH, y=0, relwidth=1.0, width=-SIDEBAR_WIDTH, height=BAR_HEIGHT)
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
        activeforeground="white", font=("Segoe UI", 8), cursor="hand2", padx=8,
    )
    back_btn.pack(side="left", padx=2)

    present_btn = tk.Button(
        button_row, text="Present", command=present, relief="flat", bd=0,
        background=theme.PRIMARY_DARK, foreground="white", activebackground=theme.PRIMARY,
        activeforeground="white", font=("Segoe UI", 8), cursor="hand2", padx=8,
    )
    present_btn.pack(side="left", padx=2)

    def refresh() -> None:
        if ctx.run_state is None or ctx.run_state.ended:
            _teardown()
            return
        if not bar.winfo_exists():
            return

        state = ctx.run_state
        section = state.current_section
        section_name = section.name if section else "Meeting"
        section_time = rs.format_mmss(state.section_remaining_seconds)
        if state.section_over_time:
            section_time = f"+{section_time} over"
        overall_time = rs.format_mmss(state.overall_remaining_seconds)
        if state.overall_over_time:
            overall_time = f"+{overall_time} over"

        status = "Running" if state.running else "Paused"
        icon = "●" if state.running else "⏸"
        label.configure(
            text=f"{icon} {status} - {section_name} - {section_time} left · {overall_time} meeting",
            foreground="#FF6B6B" if state.section_over_time else "white",
        )
        pause_btn.configure(text="⏸" if state.running else "▶")

    def _teardown() -> None:
        if ctx.run_state is not None:
            ctx.run_state.remove_listener(refresh)
        if bar.winfo_exists():
            bar.destroy()
        ctx.run_indicator = None

    ctx.run_state.add_listener(refresh)
    refresh()
