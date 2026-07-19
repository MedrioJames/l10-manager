"""Prep screen for one specific meeting occurrence: shows its effective
schedule (template + any per-occurrence overrides) and links to the
Schedule Editor. Also handles creating a standalone one-off meeting that
isn't tied to any repeating instance.
"""

from datetime import date

import tkinter as tk
from tkinter import ttk, messagebox

import config as cfgmod
import schedule as sch
from ui import theme
from ui.scrollable import ScrollableFrame


def build(ctx, occurrence_key=None, view=None, create_one_off=False, **kwargs) -> None:
    scroll = ScrollableFrame(ctx.content)
    scroll.pack(fill="both", expand=True)
    frame = ttk.Frame(scroll.body)
    frame.pack(fill="both", expand=True, padx=32, pady=28)

    if create_one_off:
        _render_create_one_off(ctx, frame)
        return

    resolved = view or cfgmod.resolve_occurrence_view(ctx.config, occurrence_key)
    if not resolved:
        ttk.Label(frame, text="Couldn't find that meeting.", style="Body.TLabel").pack(anchor="w")
        ttk.Button(frame, text="Back to Dashboard", style="Secondary.TButton",
                   command=lambda: ctx.navigate("dashboard")).pack(anchor="w", pady=(12, 0))
        return

    _render_prep(ctx, frame, resolved)


def _render_create_one_off(ctx, frame) -> None:
    ttk.Label(frame, text="Create a One-Off Meeting", style="Heading.TLabel").pack(anchor="w", pady=(0, 16))

    title_var = tk.StringVar(value="Special L10")
    ttk.Label(frame, text="Title", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Entry(frame, textvariable=title_var, width=36).pack(anchor="w", pady=(0, 12))

    date_var = tk.StringVar(value=date.today().isoformat())
    ttk.Label(frame, text="Date (YYYY-MM-DD)", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Entry(frame, textvariable=date_var, width=16).pack(anchor="w", pady=(0, 12))

    templates = ctx.config.schedule_templates
    template_name_var = tk.StringVar(value=templates[0].name if templates else "")
    ttk.Label(frame, text="Schedule template", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Combobox(
        frame, textvariable=template_name_var, state="readonly",
        values=[t.name for t in templates], width=34,
    ).pack(anchor="w", pady=(0, 16))

    button_row = ttk.Frame(frame)
    button_row.pack(fill="x")

    def cancel() -> None:
        ctx.navigate("dashboard")

    def create() -> None:
        try:
            occurrence_date = date.fromisoformat(date_var.get().strip())
        except ValueError:
            messagebox.showerror("Check the date", "Date must be in YYYY-MM-DD format")
            return
        template = next((t for t in templates if t.name == template_name_var.get()), None)
        new_id = sch.new_id()
        occ = cfgmod.Occurrence(
            id=new_id, date=occurrence_date, repeating_instance_id=None,
            title=title_var.get().strip() or "Special L10",
            schedule_template_id=template.id if template else None,
            overrides=[],
        )
        cfgmod.save_occurrence(occ, key=new_id)
        ctx.navigate("prep", occurrence_key=new_id)

    ttk.Button(button_row, text="Cancel", style="Secondary.TButton", command=cancel).pack(side="left")
    ttk.Button(button_row, text="Create", style="Primary.TButton", command=create).pack(side="right")


def _render_prep(ctx, frame, view) -> None:
    date_str = f"{view['date'].strftime('%A, %B')} {view['date'].day}, {view['date'].year}"
    ttk.Label(frame, text=view["title"], style="Heading.TLabel").pack(anchor="w")
    ttk.Label(frame, text=date_str, style="Muted.TLabel").pack(anchor="w", pady=(0, 20))

    template = ctx.config.find_template(view["schedule_template_id"])
    if not template:
        ttk.Label(frame, text="No schedule template is set for this meeting.", style="Body.TLabel").pack(anchor="w", pady=(0, 16))
    else:
        occ = cfgmod.get_occurrence(view["key"])
        overrides = occ.overrides if occ else []
        effective = sch.compute_effective_schedule(template, overrides)

        list_frame = ttk.Frame(frame)
        list_frame.pack(fill="x", pady=(0, 12))
        for section in effective:
            row = tk.Frame(list_frame, background=theme.CARD_BG, highlightbackground=theme.LINE, highlightthickness=1)
            row.pack(fill="x", pady=2)
            label_color = theme.MUTED if section.status == "skipped" else theme.INK
            name_text = section.name
            if section.status == "skipped":
                name_text += "  (skipped)"
            elif section.status == "extra":
                name_text += "  (extra)"
            elif section.status == "adjusted":
                name_text += f"  (was {section.original_duration_minutes} min)"
            tk.Label(row, text=name_text, background=theme.CARD_BG, foreground=label_color,
                     font=("Segoe UI", 10)).pack(side="left", padx=12, pady=6)
            tk.Label(row, text=f"{section.duration_minutes} min", background=theme.CARD_BG,
                     foreground=label_color, font=("Segoe UI", 9)).pack(side="right", padx=12, pady=6)

        total = sch.effective_total_minutes(effective)
        ttk.Label(frame, text=f"Total: {total} minutes", style="Body.TLabel").pack(anchor="w", pady=(0, 16))

    button_row = ttk.Frame(frame)
    button_row.pack(fill="x")
    ttk.Button(button_row, text="Back to Dashboard", style="Secondary.TButton",
               command=lambda: ctx.navigate("dashboard")).pack(side="left")
    if template:
        ttk.Button(
            button_row, text="Edit Schedule for This Meeting", style="Primary.TButton",
            command=lambda: ctx.navigate("schedule_editor", occurrence_key=view["key"], view=view),
        ).pack(side="right")
