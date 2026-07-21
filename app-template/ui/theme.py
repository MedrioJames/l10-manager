"""Shared color palette and ttk styling for the whole app.

Every screen should use these constants/styles rather than inventing new
ones, so the app (and templates/README.html, which uses the same palette)
reads as one consistent product.
"""

import tkinter as tk
from tkinter import ttk

PRIMARY = "#145A82"
PRIMARY_DARK = "#0F3C5F"
BG = "#F5F8FA"
INK = "#1C2733"
MUTED = "#5B6B7A"
LINE = "#DBE4EC"
SUBTLE_BG = "#EAF0F5"
CARD_BG = "#FFFFFF"
SIDEBAR_BG = PRIMARY_DARK
SIDEBAR_ACTIVE = PRIMARY
SIDEBAR_HOVER = "#11456A"
ON_PRIMARY_DARK_MUTED = "#A9C2D6"
WARNING_ON_DARK = "#FF6B6B"
SUCCESS = "#1E7B34"
ON_SUCCESS = "#FFFFFF"
OUTLINE = "#AEBAC4"
DANGER = "#B3261E"

# Spacing scale - use these instead of ad hoc padx/pady literals.
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24
SPACE_XXL = 32


def apply_theme(root: tk.Tk) -> ttk.Style:
    root.configure(bg=BG)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure("TFrame", background=BG)

    # Type scale: Display (44, the Run Meeting countdown only) / Headline (20) /
    # Title (13, section headings + card/row primary titles) / Body (10, default
    # reading text) / Label (9 bold, badges/tags/chips) / Meta (9, captions -
    # dates, version text). Nothing in the app should render below 9pt.
    style.configure("TLabel", background=BG, foreground=INK, font=("Segoe UI", 10))
    style.configure("Card.TLabel", background=CARD_BG, foreground=INK, font=("Segoe UI", 10))
    style.configure("Body.TLabel", background=BG, foreground=INK, font=("Segoe UI", 10))
    style.configure("Heading.TLabel", background=BG, foreground=INK, font=("Segoe UI", 20, "bold"))
    style.configure("SectionHeading.TLabel", background=BG, foreground=INK, font=("Segoe UI", 13, "bold"))
    style.configure("Title.TLabel", background=BG, foreground=INK, font=("Segoe UI", 13, "bold"))
    style.configure("CardTitle.TLabel", background=CARD_BG, foreground=INK, font=("Segoe UI", 13, "bold"))
    style.configure("Label.TLabel", background=BG, foreground=INK, font=("Segoe UI", 9, "bold"))
    style.configure("CardLabel.TLabel", background=CARD_BG, foreground=INK, font=("Segoe UI", 9, "bold"))
    style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
    style.configure("CardMuted.TLabel", background=CARD_BG, foreground=MUTED, font=("Segoe UI", 9))
    style.configure("Link.TLabel", background=BG, foreground=PRIMARY, font=("Segoe UI", 9, "underline"))

    # No ttk button styles here anymore - every button in the app now goes
    # through ui/rounded_button.py's RoundedButton (canvas-drawn, rounded
    # corners) instead of ttk.Button/Primary.TButton/Secondary.TButton.

    style.configure("TEntry", padding=6)
    style.configure("TCombobox", padding=6)
    style.configure("TCheckbutton", background=BG, foreground=INK, font=("Segoe UI", 10))
    style.configure("TRadiobutton", background=BG, foreground=INK, font=("Segoe UI", 10))

    style.configure("Nav.TFrame", background=SIDEBAR_BG)

    # Flat scrollbar styling - the "clam" theme's default (grey trough,
    # grey arrows) is dated; recolor to the app palette. (Tabs are handled
    # by ui/tabs.py's hand-rolled TabBar, not ttk.Notebook - see that
    # module's docstring for why.) Thumb color is MUTED, not SUBTLE_BG -
    # ScrollableFrame can now sit on a SUBTLE_BG background too (each Kanban
    # column in ui/issue_board.py), and a SUBTLE_BG thumb on a SUBTLE_BG
    # column is invisible; MUTED reads clearly against any light background
    # this app uses (BG, SUBTLE_BG, or white).
    style.configure(
        "Vertical.TScrollbar", background=MUTED, troughcolor=BG, bordercolor=BG,
        arrowcolor=MUTED, gripcount=0, relief="flat", borderwidth=0, arrowsize=14,
    )
    style.map("Vertical.TScrollbar", background=[("active", INK), ("pressed", INK)])

    return style
