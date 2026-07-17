"""Dashboard: upcoming meetings generated from repeating instances' recurrence
rules, plus the ability to create an unusual (one-off) meeting. Click into
one to Prep it."""

from datetime import date, timedelta

import tkinter as tk
from tkinter import ttk

import config as cfgmod
from ui import theme
from ui.scrollable import ScrollableFrame

UPCOMING_WEEKS = 8


def build(ctx, **kwargs) -> None:
    scroll = ScrollableFrame(ctx.content)
    scroll.pack(fill="both", expand=True)
    frame = ttk.Frame(scroll.body)
    frame.pack(fill="both", expand=True, padx=32, pady=28)

    header_row = ttk.Frame(frame)
    header_row.pack(fill="x", pady=(0, 16))
    ttk.Label(header_row, text="Upcoming Meetings", style="Heading.TLabel").pack(side="left")
    ttk.Button(
        header_row, text="+ Unusual Meeting", style="Secondary.TButton",
        command=lambda: ctx.navigate("prep", occurrence_key=None, create_unusual=True),
    ).pack(side="right")

    config = ctx.config
    if not config.repeating_instances:
        ttk.Label(frame, text="No repeating meetings set up yet.", style="Body.TLabel").pack(anchor="w", pady=(20, 4))
        ttk.Label(
            frame, text="Head to Settings to add one, or create a one-off meeting above.",
            style="Muted.TLabel",
        ).pack(anchor="w")
        return

    today = date.today()
    views = cfgmod.upcoming_occurrence_views(config, today, today + timedelta(weeks=UPCOMING_WEEKS))

    if not views:
        ttk.Label(
            frame, text=f"Nothing on the schedule in the next {UPCOMING_WEEKS} weeks.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=20)
        return

    for view in views:
        row = tk.Frame(frame, background=theme.CARD_BG, highlightbackground=theme.LINE, highlightthickness=1)
        row.pack(fill="x", pady=4)

        left = tk.Frame(row, background=theme.CARD_BG)
        left.pack(side="left", fill="both", expand=True, padx=14, pady=10)
        date_str = f"{view['date'].strftime('%A, %B')} {view['date'].day}"
        tk.Label(left, text=date_str, background=theme.CARD_BG, foreground=theme.MUTED,
                 font=("Segoe UI", 8)).pack(anchor="w")
        tk.Label(left, text=view["title"], background=theme.CARD_BG, foreground=theme.INK,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        if view["is_customized"]:
            tk.Label(left, text="Customized schedule", background=theme.CARD_BG, foreground=theme.PRIMARY,
                     font=("Segoe UI", 8)).pack(anchor="w")

        ttk.Button(
            row, text="Prep", style="Primary.TButton",
            command=lambda v=view: ctx.navigate("prep", occurrence_key=v["key"], view=v),
        ).pack(side="right", padx=14, pady=10)
