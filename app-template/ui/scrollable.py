"""A vertically-scrollable frame for screens whose content can exceed the
visible window height (forms, long lists). Use `.body` as the parent for
your widgets - this class just hosts the canvas + scrollbar plumbing."""

import tkinter as tk
from tkinter import ttk

from ui import theme


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)

        canvas = tk.Canvas(self, background=theme.BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.body = ttk.Frame(canvas)

        self.body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_window = canvas.create_window((0, 0), window=self.body, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width))

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        # Mousewheel binding is scoped to Enter/Leave rather than a
        # permanent bind_all - it only listens while the pointer is over
        # this canvas, and is cleaned up the moment it leaves (Tkinter's
        # bind_all is process-wide, so a permanent one would leak across
        # screen navigation, where old screens are destroyed and rebuilt).
        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
