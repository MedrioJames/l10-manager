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
DANGER = "#B3261E"


def apply_theme(root: tk.Tk) -> ttk.Style:
    root.configure(bg=BG)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=CARD_BG)
    style.configure("Header.TFrame", background=PRIMARY)

    style.configure("TLabel", background=BG, foreground=INK, font=("Segoe UI", 10))
    style.configure("Card.TLabel", background=CARD_BG, foreground=INK, font=("Segoe UI", 10))
    style.configure("Title.TLabel", background=PRIMARY, foreground="white", font=("Segoe UI", 16, "bold"))
    style.configure("Subtitle.TLabel", background=PRIMARY, foreground="#D8E6EF", font=("Segoe UI", 10))
    style.configure("Body.TLabel", background=BG, foreground=INK, font=("Segoe UI", 10))
    style.configure("Heading.TLabel", background=BG, foreground=INK, font=("Segoe UI", 18, "bold"))
    style.configure("SectionHeading.TLabel", background=BG, foreground=INK, font=("Segoe UI", 12, "bold"))
    style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 8))
    style.configure("CardMuted.TLabel", background=CARD_BG, foreground=MUTED, font=("Segoe UI", 8))
    style.configure("Link.TLabel", background=BG, foreground=PRIMARY, font=("Segoe UI", 9, "underline"))

    style.configure("TButton", font=("Segoe UI", 9), padding=(14, 8), relief="flat", borderwidth=0, focuscolor=BG)
    style.configure("Primary.TButton", background=PRIMARY, foreground="white")
    style.map("Primary.TButton", background=[("active", PRIMARY_DARK), ("pressed", PRIMARY_DARK)])
    style.configure("Secondary.TButton", background=SUBTLE_BG, foreground=INK)
    style.map("Secondary.TButton", background=[("active", LINE)])
    style.configure("Danger.TButton", background=DANGER, foreground="white")
    style.map("Danger.TButton", background=[("active", "#8C1D17")])

    style.configure("TEntry", padding=6)
    style.configure("TCombobox", padding=6)
    style.configure("TCheckbutton", background=BG, foreground=INK, font=("Segoe UI", 10))
    style.configure("TRadiobutton", background=BG, foreground=INK, font=("Segoe UI", 10))

    style.configure("Nav.TFrame", background=SIDEBAR_BG)

    # Flat scrollbar styling - the "clam" theme's default (grey trough,
    # grey arrows) is dated; recolor to the app palette. (Tabs are handled
    # by ui/tabs.py's hand-rolled TabBar, not ttk.Notebook - see that
    # module's docstring for why.)
    style.configure(
        "Vertical.TScrollbar", background=SUBTLE_BG, troughcolor=BG, bordercolor=BG,
        arrowcolor=MUTED, gripcount=0, relief="flat", borderwidth=0, arrowsize=14,
    )
    style.map("Vertical.TScrollbar", background=[("active", LINE), ("pressed", LINE)])

    return style
