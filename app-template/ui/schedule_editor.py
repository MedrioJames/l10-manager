"""Per-occurrence schedule editor: skip/restore sections, add extra ones,
adjust a section's length - all layered on top of the base template as
overrides (see schedule.py), never modifying the template itself. Skipped
sections stay listed (marked skipped) so they can be restored.
"""

import tkinter as tk
from tkinter import ttk

import config as cfgmod
import schedule as sch
from ui import theme
from ui.dialogs import ask_minutes, ask_text
from ui.scrollable import ScrollableFrame


def build(ctx, occurrence_key, view=None, **kwargs) -> None:
    resolved = view or cfgmod.resolve_occurrence_view(ctx.config, occurrence_key)
    if not resolved:
        frame = ttk.Frame(ctx.content)
        frame.pack(fill="both", expand=True, padx=32, pady=28)
        ttk.Label(frame, text="Couldn't find that meeting.", style="Body.TLabel").pack(anchor="w")
        return

    template = ctx.config.find_template(resolved["schedule_template_id"])
    if not template:
        frame = ttk.Frame(ctx.content)
        frame.pack(fill="both", expand=True, padx=32, pady=28)
        ttk.Label(frame, text="This meeting has no schedule template to edit.", style="Body.TLabel").pack(anchor="w")
        return

    occ = cfgmod.get_occurrence(occurrence_key)
    state = {"overrides": list(occ.overrides) if occ else []}
    _render(ctx, state, resolved, template, occurrence_key)


def _render(ctx, state, view, template, occurrence_key) -> None:
    for child in ctx.content.winfo_children():
        child.destroy()

    scroll = ScrollableFrame(ctx.content)
    scroll.pack(fill="both", expand=True)
    frame = ttk.Frame(scroll.body)
    frame.pack(fill="both", expand=True, padx=32, pady=28)

    ttk.Label(frame, text=f"Edit Schedule - {view['title']}", style="Heading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Label(
        frame, text="Skipped sections stay listed so you can restore them. Adjustments and extras are marked.",
        style="Muted.TLabel", wraplength=520,
    ).pack(anchor="w", pady=(0, 16))

    list_frame = ttk.Frame(frame)
    list_frame.pack(fill="x", pady=(0, 8))

    total_label = ttk.Label(frame, text="", style="Body.TLabel")

    def render_list() -> None:
        for child in list_frame.winfo_children():
            child.destroy()
        current = sch.compute_effective_schedule(template, state["overrides"])
        for section in current:
            row = tk.Frame(list_frame, background=theme.CARD_BG, highlightbackground=theme.LINE, highlightthickness=1)
            row.pack(fill="x", pady=2)

            left = tk.Frame(row, background=theme.CARD_BG)
            left.pack(side="left", fill="both", expand=True, padx=12, pady=8)
            label_color = theme.MUTED if section.status == "skipped" else theme.INK
            weight = "normal" if section.status == "skipped" else "bold"
            tk.Label(left, text=section.name, background=theme.CARD_BG, foreground=label_color,
                     font=("Segoe UI", 10, weight)).pack(anchor="w")

            tag = ""
            if section.status == "skipped":
                tag = "Skipped"
            elif section.status == "extra":
                tag = "Extra"
            elif section.status == "adjusted":
                tag = f"Adjusted (was {section.original_duration_minutes} min)"
            if tag:
                tk.Label(left, text=tag, background=theme.CARD_BG, foreground=theme.PRIMARY,
                         font=("Segoe UI", 8)).pack(anchor="w")

            right = tk.Frame(row, background=theme.CARD_BG)
            right.pack(side="right", padx=10, pady=6)
            tk.Label(right, text=f"{section.duration_minutes} min", background=theme.CARD_BG,
                     foreground=label_color, font=("Segoe UI", 9)).pack(side="left", padx=(0, 10))

            is_template_section = any(s.id == section.id for s in template.sections)

            if section.status == "skipped":
                ttk.Button(right, text="Restore", style="Secondary.TButton",
                           command=lambda sid=section.id: restore_section(sid)).pack(side="left", padx=2)
            elif is_template_section:
                ttk.Button(right, text="Skip", style="Secondary.TButton",
                           command=lambda sid=section.id: skip_section(sid)).pack(side="left", padx=2)
                ttk.Button(right, text="Adjust", style="Secondary.TButton",
                           command=lambda sid=section.id, cur=section.duration_minutes: adjust_section(sid, cur)).pack(side="left", padx=2)
            else:
                ttk.Button(right, text="Remove", style="Secondary.TButton",
                           command=lambda sid=section.id: remove_extra(sid)).pack(side="left", padx=2)

        total_label.configure(text=f"Total: {sch.effective_total_minutes(current)} minutes")

    def skip_section(section_id: str) -> None:
        state["overrides"] = [
            o for o in state["overrides"] if not (o.kind == sch.OVERRIDE_SKIP and o.section_id == section_id)
        ]
        state["overrides"].append(sch.SectionOverride(kind=sch.OVERRIDE_SKIP, section_id=section_id))
        render_list()

    def restore_section(section_id: str) -> None:
        state["overrides"] = [
            o for o in state["overrides"]
            if not (o.kind in (sch.OVERRIDE_SKIP, sch.OVERRIDE_ADJUST) and o.section_id == section_id)
        ]
        render_list()

    def adjust_section(section_id: str, current_minutes: int) -> None:
        new_value = ask_minutes(ctx.root, "Adjust length", "New length (minutes):", current_minutes)
        if new_value is None:
            return
        state["overrides"] = [
            o for o in state["overrides"] if not (o.kind == sch.OVERRIDE_ADJUST and o.section_id == section_id)
        ]
        state["overrides"].append(sch.SectionOverride(
            kind=sch.OVERRIDE_ADJUST, section_id=section_id, new_duration_minutes=new_value,
        ))
        render_list()

    def remove_extra(section_id: str) -> None:
        state["overrides"] = [
            o for o in state["overrides"]
            if not (o.kind == sch.OVERRIDE_ADD and o.added_section and o.added_section.id == section_id)
        ]
        render_list()

    def add_extra_section() -> None:
        name = ask_text(ctx.root, "Add section", "Section name:")
        if not name:
            return
        minutes = ask_minutes(ctx.root, "Add section", "Length (minutes):", 10)
        if minutes is None:
            return
        new_section = sch.Section(name=name, duration_minutes=minutes)
        state["overrides"].append(sch.SectionOverride(kind=sch.OVERRIDE_ADD, added_section=new_section))
        render_list()

    render_list()

    ttk.Button(frame, text="+ Add Extra Section", style="Secondary.TButton",
               command=add_extra_section).pack(anchor="w", pady=(8, 4))
    total_label.pack(anchor="w", pady=(4, 20))

    button_row = ttk.Frame(frame)
    button_row.pack(fill="x")

    def cancel() -> None:
        ctx.navigate("prep", occurrence_key=occurrence_key, view=view)

    def save() -> None:
        occ = cfgmod.get_occurrence(occurrence_key)
        if occ is None:
            occ = cfgmod.Occurrence(
                id=occurrence_key, date=view["date"], repeating_instance_id=view["repeating_instance_id"],
                title=view["title"], schedule_template_id=view["schedule_template_id"], overrides=[],
            )
        occ.overrides = state["overrides"]
        cfgmod.save_occurrence(occ, key=occurrence_key)
        ctx.navigate("prep", occurrence_key=occurrence_key)

    ttk.Button(button_row, text="Cancel", style="Secondary.TButton", command=cancel).pack(side="left")
    ttk.Button(button_row, text="Save Schedule", style="Primary.TButton", command=save).pack(side="right")
