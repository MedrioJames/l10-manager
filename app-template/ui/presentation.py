"""The presentation window - a second, non-modal, long-lived Toplevel meant
to be dragged to a projector/second monitor. Every other Toplevel in this
codebase (l10_manager.py's update dialog, ui/dialogs.py's prompts,
ui/issue_board.py's status-choice/issue-edit dialogs) is modal and
short-lived (created and destroyed within one user interaction); the only
non-modal one, issue_board.py's drag-ghost, is purely cosmetic and gone in
under a second. This one has no grab_set()/wait_window() - it returns
immediately and stays open across the whole meeting, reflecting pause/
resume/segment changes made from the main window in real time via the
same ctx.run_state listener the Run screen and indicator bar use.
"""

import tkinter as tk
from tkinter import ttk

import run_state as rs
import segment_types as st
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

    # Segment title/countdown each individually toggleable via the
    # segment's own display config (universal show_segment_title/
    # show_time_remaining fields - see segment_types.py::DisplayConfig) -
    # rebuilt (not just hidden) on a segment change, same reasoning as
    # ui/run_meeting.py's own header_frame: no gap left behind, no
    # widget-reordering to get wrong.
    header_frame = tk.Frame(win, background=theme.PRIMARY_DARK)
    header_frame.pack()
    header_widgets = {"segment_label": None, "segment_time_label": None}

    def rebuild_header(seg_config: dict) -> None:
        for child in header_frame.winfo_children():
            child.destroy()
        header_widgets["segment_label"] = None
        header_widgets["segment_time_label"] = None
        if seg_config.get(st.FIELD_SHOW_SEGMENT_TITLE, True):
            lbl = tk.Label(
                header_frame, text="", background=theme.PRIMARY_DARK, foreground="white",
                font=("Segoe UI", 36, "bold"), wraplength=840, justify="center",
            )
            lbl.pack(pady=(50, 20))
            header_widgets["segment_label"] = lbl
        if seg_config.get(st.FIELD_SHOW_TIME_REMAINING, True):
            lbl = tk.Label(
                header_frame, text="", background=theme.PRIMARY_DARK, foreground="white",
                font=("Segoe UI", 72, "bold"),
            )
            lbl.pack(pady=(0, 30))
            header_widgets["segment_time_label"] = lbl

    overall_time_label = tk.Label(
        win, text="", background=theme.PRIMARY_DARK, foreground=theme.ON_PRIMARY_DARK_MUTED,
        font=("Segoe UI", 20),
    )
    overall_time_label.pack()

    extra_frame = ttk.Frame(win)
    extra_frame.pack(pady=(20, 0))

    last_rendered_index = {"value": None}
    last_header_signature = {"value": None}

    def refresh() -> None:
        if ctx.run_state is None or ctx.run_state.ended:
            on_close()
            return
        if not win.winfo_exists():
            return

        state = ctx.run_state
        segment = state.current_segment
        seg_config = segment.config if segment is not None else {}

        # Keyed on the segment index AND its two display flags, not index
        # alone - a live toggle applied to the CURRENT segment (from
        # ui/run_meeting.py's inline Display controls) changes only the
        # flags, never the index, and this window has no toggle controls
        # of its own to trigger a rebuild directly - it only ever finds
        # out via this listener, so the signature has to catch it too.
        header_signature = (
            state.current_index, seg_config.get(st.FIELD_SHOW_SEGMENT_TITLE, True),
            seg_config.get(st.FIELD_SHOW_TIME_REMAINING, True),
        )
        if last_header_signature["value"] != header_signature:
            rebuild_header(seg_config)
            last_header_signature["value"] = header_signature

        if header_widgets["segment_label"] is not None:
            header_widgets["segment_label"].configure(text=segment.name if segment else "Meeting")

        segment_time = rs.format_mmss(state.segment_remaining_seconds)
        if header_widgets["segment_time_label"] is not None:
            if state.segment_over_time:
                header_widgets["segment_time_label"].configure(text=f"+{segment_time}", foreground=theme.WARNING_ON_DARK)
            else:
                header_widgets["segment_time_label"].configure(text=segment_time, foreground="white")

        overall_time = rs.format_mmss(state.overall_remaining_seconds)
        prefix = "+" if state.overall_over_time else ""
        overall_time_label.configure(text=f"{prefix}{overall_time} left in meeting")

        if last_rendered_index["value"] != state.current_index:
            for child in extra_frame.winfo_children():
                child.destroy()
            if segment is not None:
                st.get_segment_type(segment.type_id).render_presentation_view(extra_frame, segment, ctx)
            last_rendered_index["value"] = state.current_index

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
