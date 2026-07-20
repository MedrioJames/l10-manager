"""The presentation window - a second, non-modal, long-lived Toplevel meant
to be dragged to a projector/second monitor. Every other Toplevel in this
codebase (l10_manager.py's update dialog, ui/dialogs.py's prompts,
ui/issue_board.py's status-choice/issue-edit dialogs) is modal and
short-lived (created and destroyed within one user interaction); the only
non-modal one, issue_board.py's drag-ghost, is purely cosmetic and gone in
under a second. This one has no grab_set()/wait_window() - it returns
immediately and stays open across the whole meeting, reflecting pause/
resume/section changes made from the main window in real time via the
same ctx.run_state listener the Run screen and indicator bar use.
"""

import tkinter as tk

import run_state as rs
from ui import theme


def open_presentation(ctx) -> None:
    if ctx.presentation_window is not None and ctx.presentation_window.winfo_exists():
        ctx.presentation_window.lift()
        ctx.presentation_window.focus_force()
        return

    win = tk.Toplevel(ctx.root)
    win.title("L10 Manager - Presentation")
    win.configure(bg=theme.PRIMARY_DARK)
    win.transient(ctx.root)
    win.geometry("900x500")
    ctx.presentation_window = win

    section_label = tk.Label(
        win, text="", background=theme.PRIMARY_DARK, foreground="white",
        font=("Segoe UI", 36, "bold"), wraplength=840, justify="center",
    )
    section_label.pack(pady=(50, 20))

    section_time_label = tk.Label(
        win, text="", background=theme.PRIMARY_DARK, foreground="white",
        font=("Segoe UI", 72, "bold"),
    )
    section_time_label.pack(pady=(0, 30))

    overall_time_label = tk.Label(
        win, text="", background=theme.PRIMARY_DARK, foreground="#B9D3E4",
        font=("Segoe UI", 20),
    )
    overall_time_label.pack()

    def refresh() -> None:
        if ctx.run_state is None or ctx.run_state.ended:
            on_close()
            return
        if not win.winfo_exists():
            return

        state = ctx.run_state
        section = state.current_section
        section_label.configure(text=section.name if section else "Meeting")

        section_time = rs.format_mmss(state.section_remaining_seconds)
        if state.section_over_time:
            section_time_label.configure(text=f"+{section_time}", foreground="#FF8A8A")
        else:
            section_time_label.configure(text=section_time, foreground="white")

        overall_time = rs.format_mmss(state.overall_remaining_seconds)
        prefix = "+" if state.overall_over_time else ""
        overall_time_label.configure(text=f"{prefix}{overall_time} left in meeting")

    def on_close() -> None:
        if ctx.run_state is not None:
            ctx.run_state.remove_listener(refresh)
        if win.winfo_exists():
            win.destroy()
        if ctx.presentation_window is win:
            ctx.presentation_window = None

    win.protocol("WM_DELETE_WINDOW", on_close)

    if ctx.run_state is not None:
        ctx.run_state.add_listener(refresh)
    refresh()
