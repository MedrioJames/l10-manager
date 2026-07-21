"""A rounded-corner replacement for the app's ubiquitous "card row" idiom -
tk.Frame(background=CARD_BG, highlightbackground=LINE, highlightthickness=1).
No shadow (flat/tonal elevation only, matching the rest of the app - see
ui/theme.py), just a canvas-drawn rounded rectangle behind a real embedded
content frame (`.body`), using the same canvas.create_window() technique
ui/scrollable.py already uses for its scroll viewport.

Sizing is a two-way negotiation a plain Frame gets for free from pack/grid
but a bare Canvas does not: width flows top-down from this widget's own
<Configure> (whatever its parent's layout assigns it), height flows
bottom-up from `.body`'s <Configure> (its natural reqheight, replicating
pack's shrink-to-fit). Both handlers guard on "did the value actually
change" before acting, so the two can't retrigger each other in a loop.

`.body`'s square corners sit inset from the canvas edges by enough that they
fall inside the rounded curve rather than poking past it (see _corner_inset)
- callers pack/grid their real content into `.body` exactly as they did into
the old flat Frame; nothing else changes.
"""

import tkinter as tk

from ui import canvas_shapes as shapes
from ui import theme


def _corner_inset(radius: int, border_width: int) -> int:
    # A body-frame corner inset by >= radius * (1 - 1/sqrt(2)) (~0.293) stays
    # inside the polygon's quarter-circle curve instead of poking past it;
    # 0.4 adds a small safety margin without wasting much content padding.
    return max(border_width, round(radius * 0.4))


class RoundedCard(tk.Canvas):
    def __init__(
        self,
        parent,
        background: str = None,
        outer_background: str = None,
        border_color: str = None,
        border_width: int = 1,
        radius: int = 10,
    ):
        background = background if background is not None else theme.CARD_BG
        border_color = border_color if border_color is not None else theme.LINE
        if outer_background is None:
            try:
                # A ttk widget (e.g. ttk.Frame) doesn't support a plain
                # "background" cget the way a classic tk widget does - most
                # of this app's card lists sit inside a ttk.Frame on the
                # page's BG, so fall back to that rather than erroring.
                outer_background = parent.cget("background")
            except tk.TclError:
                outer_background = theme.BG

        super().__init__(parent, background=outer_background, highlightthickness=0, bd=0)

        self._radius = radius
        self._inset = _corner_inset(radius, border_width)
        self._last_size = None
        self._last_target_height = None

        self.body = tk.Frame(self, background=background)
        self._window_id = self.create_window(self._inset, self._inset, window=self.body, anchor="nw")
        self._shape_id = self.create_polygon(
            *shapes.rounded_rect_points(0, 0, 1, 1, radius),
            smooth=True, splinesteps=shapes.SPLINESTEPS,
            fill=background, outline=border_color, width=border_width,
        )
        self.tag_lower(self._shape_id)

        self.bind("<Configure>", self._on_canvas_configure)
        self.body.bind("<Configure>", self._on_body_configure)

    def set_active(self, is_active: bool) -> None:
        """Border color/width swap for a selected/current-row indicator
        (people_modal.py's editing row, run_meeting.py's current segment)."""
        self.itemconfigure(
            self._shape_id,
            outline=theme.PRIMARY if is_active else theme.LINE,
            width=2 if is_active else 1,
        )

    def set_fill(self, background: str) -> None:
        """Swap both the shape's fill and .body's background - for rows
        whose fill changes too, not just their border (run_meeting.py's
        current segment; hover tints)."""
        self.body.configure(background=background)
        self.itemconfigure(self._shape_id, fill=background)

    def _on_canvas_configure(self, event) -> None:
        size = (event.width, event.height)
        if size == self._last_size:
            return
        self._last_size = size
        if event.width > 1 and event.height > 1:
            self.coords(self._shape_id, *shapes.rounded_rect_points(0, 0, event.width, event.height, self._radius))
        self.itemconfigure(self._window_id, width=max(1, event.width - 2 * self._inset))

    def _on_body_configure(self, _event) -> None:
        target_height = self.body.winfo_reqheight() + 2 * self._inset
        if target_height == self._last_target_height:
            return
        self._last_target_height = target_height
        self.configure(height=target_height)
