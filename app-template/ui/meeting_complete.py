"""Meeting Complete - shown by ui/run_meeting.py::build() once
ctx.run_state.ended is True (natural last-segment completion or an explicit
"End Meeting..." click), replacing the old dead-end ctx.navigate("conclude")
call that crashed with "Unknown screen: conclude" (that nav key was retired
two rounds ago when ui/review.py replaced the Conclude placeholder). Just a
quick landing point with a way forward (Review) or out (Dashboard) - both
clear ctx.run_state first so a later visit to Run Meeting shows the normal
"pick a meeting" picker again instead of this same stale summary.
"""

from tkinter import ttk

import config as cfgmod
import issues as iss
import run_state as rs
import todos as td
from ui.rounded_button import RoundedButton


def build(ctx) -> None:
    state = ctx.run_state

    frame = ttk.Frame(ctx.content)
    frame.pack(fill="both", expand=True, padx=32, pady=28)

    ttk.Label(frame, text="Meeting Complete", style="Heading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Label(frame, text=state.occurrence_title, style="Body.TLabel").pack(anchor="w", pady=(0, 16))

    ttk.Label(
        frame, text=f"Total time: {rs.format_mmss(state.elapsed_seconds)}", style="Body.TLabel",
    ).pack(anchor="w", pady=(0, 4))

    view = cfgmod.resolve_occurrence_view(ctx.config, state.occurrence_key)
    instance_id = view["repeating_instance_id"] if view else None
    try:
        open_todos = len(td.list_todos(repeating_instance_id=instance_id))
    except cfgmod.DataLoadError:
        open_todos = 0
    try:
        open_issues = len(iss.list_issues())
    except cfgmod.DataLoadError:
        open_issues = 0
    ttk.Label(
        frame, text=f"{open_todos} open to-do(s) for this meeting  ·  {open_issues} open issue(s) overall",
        style="Body.TLabel",
    ).pack(anchor="w", pady=(0, 24))

    button_row = ttk.Frame(frame)
    button_row.pack(anchor="w")

    def go_to_review() -> None:
        ctx.run_state = None
        ctx.navigate("review")

    def back_to_dashboard() -> None:
        ctx.run_state = None
        ctx.navigate("dashboard")

    RoundedButton(button_row, text="Go to Review", variant="filled", command=go_to_review).pack(side="left", padx=(0, 8))
    RoundedButton(button_row, text="Back to Dashboard", variant="tonal", command=back_to_dashboard).pack(side="left")
