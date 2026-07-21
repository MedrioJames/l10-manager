"""A vertically-scrollable frame for screens whose content can exceed the
visible window height (forms, long lists). Use `.body` as the parent for
your widgets - this class just hosts the canvas + scrollbar plumbing.

The scrollbar auto-hides when content fits without scrolling (checked on
both the body's and canvas's <Configure> events). Deliberately no
"skip if unchanged" guard the way ui/rounded_card.py's resize handlers use -
canvas.winfo_height() can still be Tk's pre-layout placeholder on the very
first Configure this fires for, and comparing against that stale read once
left the scrollbar permanently packed-but-zero-sized (registered while the
canvas had no real size yet, then never reconciled again since a later
correct check saw the same boolean and skipped re-packing). pack()/
pack_forget() are cheap/idempotent, so this just reconciles every time
instead. `background` defaults to theme.BG but can be overridden -
e.g. ui/issue_board.py wraps each Kanban column's card list in one of these
with background=theme.SUBTLE_BG to match the column."""

import tkinter as tk
from tkinter import ttk

from ui import theme


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent, background: str = None):
        super().__init__(parent)
        background = background if background is not None else theme.BG

        canvas = tk.Canvas(self, background=background, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        # A plain tk.Frame (not ttk.Frame) so it can take the same explicit
        # background as the canvas - a ttk.Frame here would always render
        # theme.BG regardless of what's passed, leaving a mismatched patch
        # behind the content whenever background != theme.BG.
        self.body = tk.Frame(canvas, background=background)
        self._scrollbar = scrollbar
        self._scrollbar_visible = None

        def _update_scrollbar_visibility() -> None:
            # Deliberately no "skip if unchanged" guard here (unlike
            # RoundedCard's resize handlers) - canvas.winfo_height() can
            # still be a stale placeholder (Tk's pre-layout default) on the
            # very first Configure this fires for, before real geometry has
            # settled. Re-deciding "unchanged" against that stale read once
            # left the scrollbar permanently packed-but-zero-sized (pack()
            # registered while the canvas had no real size yet, then never
            # re-called once it did, since the guard saw the same boolean
            # both times). pack()/pack_forget() are cheap/idempotent, so
            # just reconcile every time instead of trying to be clever.
            bbox = canvas.bbox("all")
            content_height = bbox[3] - bbox[1] if bbox else 0
            needed = content_height > canvas.winfo_height()
            self._scrollbar_visible = needed
            if needed:
                scrollbar.pack(side="right", fill="y")
            else:
                scrollbar.pack_forget()

        def _on_body_configure(_e) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))
            _update_scrollbar_visibility()

        self.body.bind("<Configure>", _on_body_configure)
        canvas_window = canvas.create_window((0, 0), window=self.body, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_canvas_configure(e) -> None:
            canvas.itemconfig(canvas_window, width=e.width)
            _update_scrollbar_visibility()

        canvas.bind("<Configure>", _on_canvas_configure)

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
        # scrollbar itself is packed/unpacked on demand by
        # _update_scrollbar_visibility() above, not unconditionally here.
