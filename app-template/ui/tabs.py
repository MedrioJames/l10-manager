"""A minimal Material-style tab bar - flat, no boxy chrome, a colored
underline under the active tab, identical sizing for every tab regardless
of selection state. Replaces ttk.Notebook, whose "clam" theme has a real,
hard-to-fully-override quirk: clam's built-in tab layout applies its own
internal per-state padding map to the selected tab (to visually "connect"
it to the page below), which silently wins over a flat style.configure()
default - the selected tab ends up a different size than the others no
matter what padding you configure. Rather than fight clam's theme
internals further, this follows the same pattern already used elsewhere in
this app when a stock ttk/tk widget falls short of what's needed
(icon_button.py, the drag-and-drop reordering, notifications.py's toast) -
a small hand-rolled widget instead.
"""

import tkinter as tk
from tkinter import ttk

from ui import theme

UNDERLINE_HEIGHT = 3


class TabBar(ttk.Frame):
    """tabs = TabBar(parent, ["A", "B"], on_change=...)
    tabs.pack(fill="both", expand=True)
    build_a_content_into(tabs.page(0))
    build_b_content_into(tabs.page(1))
    tabs.select(1)
    """

    def __init__(self, parent, labels, on_change=None):
        super().__init__(parent)
        self._on_change = on_change
        self._active = 0
        self._tab_labels = []
        self._underlines = []
        self._pages = []

        header = tk.Frame(self, background=theme.BG)
        header.pack(fill="x")

        rule = tk.Frame(self, background=theme.LINE, height=1)
        rule.pack(fill="x")

        self._content = ttk.Frame(self)
        self._content.pack(fill="both", expand=True)

        for idx, label in enumerate(labels):
            col = tk.Frame(header, background=theme.BG)
            col.pack(side="left")

            lbl = tk.Label(
                col, text=label, background=theme.BG, foreground=theme.MUTED,
                font=("Segoe UI", 10), padx=20, pady=12, cursor="hand2",
            )
            lbl.pack()
            underline = tk.Frame(col, background=theme.BG, height=UNDERLINE_HEIGHT)
            underline.pack(fill="x")

            lbl.bind("<Button-1>", lambda _e, i=idx: self.select(i))
            lbl.bind("<Enter>", lambda _e, i=idx: self._on_hover(i, True))
            lbl.bind("<Leave>", lambda _e, i=idx: self._on_hover(i, False))

            self._tab_labels.append(lbl)
            self._underlines.append(underline)
            self._pages.append(ttk.Frame(self._content))

        self._refresh_styles()
        self._pages[0].pack(fill="both", expand=True)

    def page(self, index: int) -> ttk.Frame:
        return self._pages[index]

    def select(self, index: int) -> None:
        if not (0 <= index < len(self._pages)) or index == self._active:
            return
        self._pages[self._active].pack_forget()
        self._active = index
        self._pages[index].pack(fill="both", expand=True)
        self._refresh_styles()
        if self._on_change:
            self._on_change(index)

    def _on_hover(self, idx: int, entering: bool) -> None:
        if idx == self._active:
            return
        self._tab_labels[idx].configure(foreground=theme.INK if entering else theme.MUTED)

    def _refresh_styles(self) -> None:
        for i, (lbl, underline) in enumerate(zip(self._tab_labels, self._underlines)):
            is_active = i == self._active
            lbl.configure(
                foreground=theme.PRIMARY if is_active else theme.MUTED,
                font=("Segoe UI", 10, "bold" if is_active else "normal"),
            )
            underline.configure(background=theme.PRIMARY if is_active else theme.BG)
