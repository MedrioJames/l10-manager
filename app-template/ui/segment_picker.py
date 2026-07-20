"""Segment picker - a searchable modal over the global Segment library
(ctx.config.segments), with a "+ New Segment" escape hatch that creates a
segment (saved into the library first) and hands it straight back to
whichever flow asked for one. Used both by the Schedule builder's "+ Add
Segment" and the per-occurrence Schedule Editor's "+ Add Segment" flow.
"""

import tkinter as tk
from tkinter import ttk

import segment_types as st
from ui import theme
from ui.scrollable import ScrollableFrame
from ui.segment_editor import open_segment_editor_modal


def open_segment_picker(ctx, on_selected, title: str = "Add Segment") -> None:
    win = tk.Toplevel(ctx.root)
    win.title(title)
    win.configure(bg=theme.BG)
    win.transient(ctx.root)
    win.geometry("420x520")

    header = ttk.Frame(win)
    header.pack(fill="x", padx=20, pady=(20, 8))
    ttk.Label(header, text=title, style="Heading.TLabel").pack(anchor="w")

    search_var = tk.StringVar()
    search_row = ttk.Frame(win)
    search_row.pack(fill="x", padx=20, pady=(0, 8))
    ttk.Entry(search_row, textvariable=search_var, width=36).pack(fill="x")

    scroll = ScrollableFrame(win)
    scroll.pack(fill="both", expand=True, padx=20)
    list_frame = ttk.Frame(scroll.body)
    list_frame.pack(fill="both", expand=True)

    def choose(segment) -> None:
        win.destroy()
        on_selected(segment)

    def render_list(*_args) -> None:
        for child in list_frame.winfo_children():
            child.destroy()
        query = search_var.get().strip().lower()
        if not ctx.config.segments:
            ttk.Label(list_frame, text="No segments yet - create one below.", style="Muted.TLabel").pack(anchor="w", pady=8)
        for segment in ctx.config.segments:
            seg_type = st.get_segment_type(segment.type_id)
            haystack = f"{segment.name} {seg_type.display_name}".lower()
            if query and query not in haystack:
                continue
            row = tk.Frame(list_frame, background=theme.CARD_BG, highlightbackground=theme.LINE, highlightthickness=1)
            row.pack(fill="x", pady=3)
            info = tk.Frame(row, background=theme.CARD_BG)
            info.pack(side="left", fill="both", expand=True, padx=10, pady=8)
            tk.Label(info, text=segment.name, background=theme.CARD_BG, foreground=theme.INK,
                     font=("Segoe UI", 10, "bold")).pack(anchor="w")
            tk.Label(
                info, text=f"{seg_type.display_name} - {segment.duration_minutes} min",
                background=theme.CARD_BG, foreground=theme.MUTED, font=("Segoe UI", 8),
            ).pack(anchor="w")
            ttk.Button(row, text="Use", style="Primary.TButton",
                       command=lambda s=segment: choose(s)).pack(side="right", padx=8)

    search_var.trace_add("write", render_list)
    render_list()

    def new_segment() -> None:
        open_segment_editor_modal(ctx, segment=None, locked_type=None, on_saved=choose)

    footer = ttk.Frame(win)
    footer.pack(fill="x", padx=20, pady=16)
    ttk.Button(footer, text="+ New Segment", style="Secondary.TButton", command=new_segment).pack(side="left")
    ttk.Button(footer, text="Cancel", style="Secondary.TButton", command=win.destroy).pack(side="right")

    win.update_idletasks()
    x = ctx.root.winfo_x() + max((ctx.root.winfo_width() - win.winfo_width()) // 2, 0)
    y = ctx.root.winfo_y() + max((ctx.root.winfo_height() - win.winfo_height()) // 2, 0)
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.grab_set()
