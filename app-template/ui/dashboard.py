"""Dashboard: a lightweight overview, not a full meeting browser (that's
ui/prep.py's job now - see NAV_ITEMS). Shows the next few upcoming meetings
(reusing ui/occurrence_list.py) plus small at-a-glance counts (open issues,
outstanding to-dos) so there's a real reason to land here first, distinct
from Prep's full unlimited list.
"""

from tkinter import ttk

import issues as iss
import todos as td
from ui.occurrence_list import render_occurrence_list
from ui.rounded_button import RoundedButton

DASHBOARD_ITEM_COUNT = 3


def build(ctx, **kwargs) -> None:
    frame = ttk.Frame(ctx.content)
    frame.pack(fill="both", expand=True, padx=32, pady=28)

    header_row = ttk.Frame(frame)
    header_row.pack(fill="x", pady=(0, 16))
    ttk.Label(header_row, text="Dashboard", style="Heading.TLabel").pack(side="left")
    RoundedButton(
        header_row, text="+ One-Off Meeting", variant="tonal",
        command=lambda: ctx.navigate("prep", occurrence_key=None, create_one_off=True),
    ).pack(side="right")

    at_a_glance = ttk.Frame(frame)
    at_a_glance.pack(fill="x", pady=(0, 20))
    try:
        open_issues = len([i for i in iss.list_issues() if not _is_closed(ctx, i.status)])
    except Exception:  # noqa: BLE001 - a glance count should never crash the dashboard
        open_issues = 0
    outstanding_todos = len(td.list_todos())
    ttk.Label(
        at_a_glance, text=f"{open_issues} open issue(s)  ·  {outstanding_todos} outstanding to-do(s)",
        style="Muted.TLabel",
    ).pack(anchor="w")

    ttk.Label(frame, text="Upcoming Meetings", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 8))
    render_occurrence_list(
        frame, ctx, on_pick=lambda v: ctx.navigate("prep", occurrence_key=v["key"], view=v),
        max_items=DASHBOARD_ITEM_COUNT,
    )
    ttk.Label(
        frame, text="See the Prep tab for the full list.", style="Muted.TLabel",
    ).pack(anchor="w", pady=(4, 0))


def _is_closed(ctx, status_id: str) -> bool:
    status = ctx.config.find_status(status_id)
    return bool(status and status.is_closed)
