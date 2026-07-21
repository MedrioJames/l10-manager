"""Small flat icon-only buttons - replaces the repeated text Edit/Delete/
Remove button-pair pattern found across settings.py, schedule_builder.py,
and schedule_editor.py with compact Unicode-glyph buttons, mirroring the
"X" dismiss button already used in ui/notifications.py.
"""

import tkinter as tk

from ui import theme

# Segoe MDL2 Assets - the standard Windows 10+ monochrome UI icon font,
# not a scattered mix of Unicode symbol/emoji codepoints from different
# blocks with inconsistent font coverage. GLYPH_DELETE used to be the
# emoji-range wastebasket U+1F5D1, which isn't in "Segoe UI Symbol" and
# fell back to colorful "Segoe UI Emoji," clashing with every other flat
# glyph next to it - a real user reported the icons "don't fit."
ICON_FONT = "Segoe MDL2 Assets"
GLYPH_EDIT = ""        # Edit (pencil)
GLYPH_DELETE = ""      # Delete (trash can)
GLYPH_DUPLICATE = ""   # Copy
GLYPH_DRAG = ""        # GripperTool - a drag-handle grip
GLYPH_SAVE = ""        # Accept (check mark)
GLYPH_CANCEL = ""      # Cancel (x)
GLYPH_SKIP = ""        # Blocked2 (circle-slash) - "skip"/"drop"
GLYPH_RESTORE = ""     # Undo


def icon_button(parent, glyph: str, command, danger: bool = False, background: str = None) -> tk.Button:
    bg = background if background is not None else theme.CARD_BG
    fg = theme.DANGER if danger else theme.PRIMARY
    return tk.Button(
        parent, text=glyph, command=command, background=bg, foreground=fg,
        relief="flat", bd=0, font=(ICON_FONT, 11), cursor="hand2",
        activebackground=theme.LINE, activeforeground=fg, highlightthickness=0,
        padx=6, pady=2,
    )
