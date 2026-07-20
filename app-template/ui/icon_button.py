"""Small flat icon-only buttons - replaces the repeated text Edit/Delete/
Remove button-pair pattern found across settings.py, schedule_templates.py,
and schedule_editor.py with compact Unicode-glyph buttons, mirroring the
"X" dismiss button already used in ui/notifications.py.
"""

import tkinter as tk

from ui import theme

GLYPH_EDIT = "✎"        # pencil
GLYPH_DELETE = "\U0001F5D1"  # wastebasket
GLYPH_DUPLICATE = "⧉"   # two joined squares
GLYPH_DRAG = "⠿"        # braille all-dots, used as a drag handle
GLYPH_SAVE = "✓"        # check mark
GLYPH_CANCEL = "✕"      # multiplication x
GLYPH_SKIP = "⊘"        # circled slash - "skip this section"
GLYPH_RESTORE = "↺"     # undo arrow - "restore a skipped section"


def icon_button(parent, glyph: str, command, danger: bool = False, background: str = None) -> tk.Button:
    bg = background if background is not None else theme.CARD_BG
    fg = theme.DANGER if danger else theme.PRIMARY
    return tk.Button(
        parent, text=glyph, command=command, background=bg, foreground=fg,
        relief="flat", bd=0, font=("Segoe UI Symbol", 11), cursor="hand2",
        activebackground=theme.LINE, activeforeground=fg, highlightthickness=0,
        padx=6, pady=2,
    )
