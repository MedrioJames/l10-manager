"""Review - the post-meeting phase (see docs/L10-CONCEPT.md's Prep -> Run ->
Review mapping): confirm the cascading message got sent, make sure new
to-dos/issues were captured, and track the meeting rating over time.
Replaces the old "Conclude" placeholder nav item - the Conclude *agenda
item* itself (rating capture, cascading message) now lives as a live
segment type (segment_types.py::ConcludeType) run during the meeting; this
screen is what you check afterward, not during.

Past occurrence dates are found by calling recurrence.generate_occurrences()
with a historical range (rule.start_date through today) - the exact same
function ui/dashboard.py already calls with a forward-looking range; no new
backward-looking recurrence logic was needed.
"""

from datetime import date

import tkinter as tk
from tkinter import ttk

import config as cfgmod
import issues as iss
import recurrence as rec
import todos as td
from ui.notifications import show_error_banner
from ui.rounded_button import RoundedButton
from ui.scrollable import ScrollableFrame

RATING_HISTORY_LIMIT = 12


def build(ctx, **kwargs) -> None:
    scroll = ScrollableFrame(ctx.content)
    scroll.pack(fill="both", expand=True)
    frame = ttk.Frame(scroll.body)
    frame.pack(fill="both", expand=True, padx=32, pady=28)

    ttk.Label(frame, text="Review", style="Heading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Label(
        frame, text="Confirm the cascading message went out, new to-dos/issues were captured, "
                     "and see how the team's rated recent meetings.",
        style="Muted.TLabel", wraplength=520,
    ).pack(anchor="w", pady=(0, 16))

    instances = ctx.config.repeating_instances
    if not instances:
        ttk.Label(frame, text="No repeating meetings set up yet - nothing to review.", style="Muted.TLabel").pack(anchor="w")
        return

    picker_container = ttk.Frame(frame)
    picker_container.pack(fill="x")

    body = ttk.Frame(frame)
    body.pack(fill="both", expand=True)

    def show_instance(instance_id: str) -> None:
        for child in body.winfo_children():
            child.destroy()
        _render_instance_review(ctx, body, instance_id)

    if len(instances) > 1:
        name_by_instance = {ri.name: ri.id for ri in instances}
        instance_var = tk.StringVar(value=instances[0].name)

        def on_change(_event=None) -> None:
            show_instance(name_by_instance.get(instance_var.get()))

        row = ttk.Frame(picker_container)
        row.pack(fill="x", pady=(0, 12))
        ttk.Label(row, text="Meeting:", style="Body.TLabel").pack(side="left", padx=(0, 8))
        combo = ttk.Combobox(
            row, textvariable=instance_var, state="readonly", width=30, values=list(name_by_instance.keys()),
        )
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", on_change)

    show_instance(instances[0].id)


def _render_instance_review(ctx, parent, instance_id: str) -> None:
    ri = ctx.config.find_instance(instance_id)
    if ri is None:
        ttk.Label(parent, text="Couldn't find that repeating meeting.", style="Body.TLabel").pack(anchor="w")
        return

    today = date.today()
    past_dates = sorted(
        (d for d in rec.generate_occurrences(ri.recurrence, ri.recurrence.start_date, today) if d < today),
        reverse=True,
    )

    if not past_dates:
        ttk.Label(
            parent, text="No past occurrences yet for this meeting.", style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 16))
        return

    most_recent_key = cfgmod.occurrence_key(instance_id, past_dates[0])
    try:
        most_recent_occ = cfgmod.get_occurrence(most_recent_key)
    except cfgmod.DataLoadError:
        most_recent_occ = None
        show_error_banner(ctx, "Data/occurrences.json couldn't be read - a backup may be available at occurrences.json.bak.")

    ttk.Label(parent, text="Most Recent Meeting", style="SectionHeading.TLabel").pack(anchor="w", pady=(8, 4))
    ttk.Label(parent, text=past_dates[0].strftime("%A, %B %d, %Y"), style="Muted.TLabel").pack(anchor="w", pady=(0, 8))

    try:
        open_todos = len(td.list_todos(repeating_instance_id=instance_id))
    except cfgmod.DataLoadError:
        open_todos = 0
    try:
        open_issues = len(iss.list_issues())
    except cfgmod.DataLoadError:
        open_issues = 0
    ttk.Label(
        parent, text=f"{open_todos} open to-do(s) for this meeting  ·  {open_issues} open issue(s) overall",
        style="Body.TLabel",
    ).pack(anchor="w", pady=(0, 12))

    ttk.Label(parent, text="Cascading Message", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    message_text = tk.Text(parent, height=3, width=60, font=("Segoe UI", 9), wrap="word")
    message_text.pack(anchor="w", pady=(0, 4))
    if most_recent_occ and most_recent_occ.cascading_message:
        message_text.insert("1.0", most_recent_occ.cascading_message)

    status_label = ttk.Label(parent, text="", style="Muted.TLabel")

    def save_message() -> None:
        try:
            occ = cfgmod.get_or_create_occurrence(ctx.config, most_recent_key)
        except cfgmod.DataLoadError:
            status_label.configure(text="Couldn't save - Data/occurrences.json couldn't be read.")
            return
        if occ is None:
            status_label.configure(text="Couldn't save.")
            return
        occ.cascading_message = message_text.get("1.0", "end-1c")
        cfgmod.save_occurrence(occ, key=most_recent_key)
        status_label.configure(text="Saved.")

    RoundedButton(parent, text="Save Message", variant="tonal", command=save_message).pack(anchor="w", pady=(0, 4))
    status_label.pack(anchor="w", pady=(0, 16))

    ttk.Label(parent, text="Rating History", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 8))
    history_frame = ttk.Frame(parent)
    history_frame.pack(fill="x")

    shown_any = False
    for occ_date in past_dates[:RATING_HISTORY_LIMIT]:
        key = cfgmod.occurrence_key(instance_id, occ_date)
        try:
            occ = cfgmod.get_occurrence(key)
        except cfgmod.DataLoadError:
            occ = None
        if not occ or not occ.ratings:
            continue
        shown_any = True
        average = sum(occ.ratings.values()) / len(occ.ratings)
        row = ttk.Frame(history_frame)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=occ_date.strftime("%b %d, %Y"), style="Body.TLabel", width=16).pack(side="left")
        ttk.Label(
            row, text=f"Average rating: {average:.1f} ({len(occ.ratings)} response(s))", style="Body.TLabel",
        ).pack(side="left")

    if not shown_any:
        ttk.Label(
            history_frame, text="No ratings recorded yet - captured live during the Conclude segment.",
            style="Muted.TLabel",
        ).pack(anchor="w")
