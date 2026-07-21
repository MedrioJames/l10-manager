"""A rounded-corner button - a lighter-weight sibling of ui/rounded_card.py,
reusing the same ui/canvas_shapes.py rounded-rectangle helper. Deliberately
minimal: only the two variants actually used at volume across this app
("filled" for the old Primary.TButton call sites, "tonal" for Secondary.
TButton) - no disabled state (nothing in this app ever sets one on a
button today) and no shadow (this app's flat/tonal elevation approach has
no drop-shadow rendering anywhere - would be inconsistent with
ui/rounded_card.py, and hard to do well on a stdlib Tk canvas without
Pillow).

Simpler than RoundedCard in one respect: no embedded child window (just two
canvas items - a rounded-rect shape and a centered text label), so there's
no bidirectional sizing negotiation to get right - the button sizes itself
once from its text via font.measure(), the same way ttk.Button auto-sizes.

Supports .configure(text=...) / .configure(command=...) so it's a close
drop-in replacement at the handful of existing call sites that dynamically
retext a button after creation (e.g. ui/run_meeting.py's Pause/Resume and
Next Segment/End Meeting toggles).
"""

import tkinter as tk
import tkinter.font as tkfont

from ui import canvas_shapes as shapes
from ui import theme

RADIUS = 8
PAD_X = 14
PAD_Y = 8

_VARIANT_COLORS = {
    "filled": {"fill": theme.PRIMARY, "hover": theme.PRIMARY_DARK, "text": "white"},
    "tonal": {"fill": theme.SUBTLE_BG, "hover": theme.LINE, "text": theme.INK},
}


class RoundedButton(tk.Canvas):
    def __init__(self, parent, text: str = "", command=None, variant: str = "filled", font=None):
        try:
            outer_background = parent.cget("background")
        except tk.TclError:
            outer_background = theme.BG

        super().__init__(parent, background=outer_background, highlightthickness=0, bd=0, cursor="hand2")

        self._colors = _VARIANT_COLORS.get(variant, _VARIANT_COLORS["filled"])
        self._text = text
        self._command = command
        self._pressed = False
        self._font = tkfont.Font(font=font or ("Segoe UI", 9))
        self._last_size = None

        self._shape_id = self.create_polygon(
            *shapes.rounded_rect_points(0, 0, 1, 1, RADIUS),
            smooth=True, splinesteps=shapes.SPLINESTEPS, fill=self._colors["fill"], outline="",
        )
        self._text_id = self.create_text(0, 0, text=text, fill=self._colors["text"], font=self._font, anchor="center")

        self.bind("<Configure>", self._on_configure)
        self.bind("<Enter>", lambda _e: self._set_fill(self._colors["hover"]))
        self.bind("<Leave>", lambda _e: self._set_fill(self._colors["fill"]))
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

        self._resize_to_fit()

    def _set_fill(self, color: str) -> None:
        self.itemconfigure(self._shape_id, fill=color)

    def _on_press(self, _event) -> None:
        self._pressed = True
        self._set_fill(self._colors["hover"])

    def _on_release(self, event) -> None:
        was_pressed = self._pressed
        self._pressed = False
        # Use the size from the last real <Configure> event rather than
        # winfo_width()/winfo_height() live-querying - those only reflect
        # actual on-screen geometry once mapped, which lags behind (or, in
        # a headless/withdrawn test root, never happens at all).
        width, height = self._last_size or (self.winfo_width(), self.winfo_height())
        inside = 0 <= event.x < width and 0 <= event.y < height
        self._set_fill(self._colors["hover"] if inside else self._colors["fill"])
        if was_pressed and inside and self._command:
            self._command()

    def _on_configure(self, event) -> None:
        size = (event.width, event.height)
        if size == self._last_size:
            return
        self._last_size = size
        if event.width > 1 and event.height > 1:
            self.coords(self._shape_id, *shapes.rounded_rect_points(0, 0, event.width, event.height, RADIUS))
        self.coords(self._text_id, event.width / 2, event.height / 2)

    def _resize_to_fit(self) -> None:
        text_w = self._font.measure(self._text) if self._text else 0
        line_h = self._font.metrics("linespace")
        width = max(text_w + 2 * PAD_X, 2 * RADIUS)
        height = max(line_h + 2 * PAD_Y, 2 * RADIUS)
        tk.Canvas.configure(self, width=width, height=height)

    def configure(self, cnf=None, **kwargs) -> None:
        if cnf:
            kwargs.update(cnf)
        if "text" in kwargs:
            self._text = kwargs.pop("text")
            self.itemconfigure(self._text_id, text=self._text)
            self._resize_to_fit()
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if kwargs:
            tk.Canvas.configure(self, **kwargs)

    config = configure
