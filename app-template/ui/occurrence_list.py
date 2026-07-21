"""Shared "list of upcoming meetings, pick one" rendering - factored out of
ui/dashboard.py (its original home) since ui/prep.py's standalone entry and
ui/run_meeting.py's "nothing running" picker both need the same list, just
with a different action when a row is picked (Dashboard navigates to Prep;
Prep sets local state and re-renders; Run Meeting starts the meeting).
"""

from datetime import date, timedelta

import tkinter as tk
from tkinter import ttk

import config as cfgmod
from ui import theme
from ui.notifications import show_error_banner
from ui.rounded_button import RoundedButton
from ui.rounded_card import RoundedCard

DEFAULT_WEEKS = 8


def render_occurrence_list(
    parent, ctx, on_pick, weeks: int = DEFAULT_WEEKS, button_label: str = "Prep",
    max_items: int = None, show_button: bool = True,
) -> list:
    """Renders rows into `parent` (an already-built container) for each
    upcoming occurrence in the next `weeks` weeks. Calls on_pick(view) when
    a row's button is clicked. Returns the full view list (even when
    max_items truncates what's rendered), so a caller like the Dashboard
    overview can use it for counts/a "next meeting" hero without a second
    query."""
    config = ctx.config
    if not config.repeating_instances:
        ttk.Label(parent, text="No repeating meetings set up yet.", style="Body.TLabel").pack(anchor="w", pady=(20, 4))
        ttk.Label(
            parent, text="Head to Settings to add one, or create a one-off meeting.",
            style="Muted.TLabel",
        ).pack(anchor="w")
        return []

    today = date.today()
    try:
        views = cfgmod.upcoming_occurrence_views(config, today, today + timedelta(weeks=weeks))
    except cfgmod.DataLoadError:
        show_error_banner(
            ctx, "Data/occurrences.json couldn't be read - a backup may be available at occurrences.json.bak.",
        )
        views = []

    if not views:
        ttk.Label(
            parent, text=f"Nothing on the schedule in the next {weeks} weeks.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=20)
        return []

    shown = views[:max_items] if max_items is not None else views
    for view in shown:
        card = RoundedCard(parent)
        card.pack(fill="x", pady=4)
        row = card.body

        left = tk.Frame(row, background=theme.CARD_BG)
        left.pack(side="left", fill="both", expand=True, padx=14, pady=10)
        date_str = f"{view['date'].strftime('%A, %B')} {view['date'].day}"
        ttk.Label(left, text=date_str, style="CardMuted.TLabel").pack(anchor="w")
        ttk.Label(left, text=view["title"], style="CardTitle.TLabel").pack(anchor="w")
        if view["is_customized"]:
            tk.Label(left, text="Customized schedule", background=theme.CARD_BG, foreground=theme.PRIMARY,
                     font=("Segoe UI", 9)).pack(anchor="w")

        if show_button:
            RoundedButton(
                row, text=button_label, variant="filled",
                command=lambda v=view: on_pick(v),
            ).pack(side="right", padx=14, pady=10)

    return views
