"""Schedule template manager - CRUD for reusable named agenda blueprints
(name, description, ordered sections with default durations). One prebuilt
template (the standard L10 agenda) always ships; users can add more and
attach any of them to a repeating instance.
"""

import tkinter as tk
from tkinter import ttk, messagebox

import schedule as sch
from ui import icon_button, theme
from ui.schedule_template_editor import build_section_editor
from ui.scrollable import ScrollableFrame


def build(ctx, **kwargs) -> None:
    state = {
        "mode": "overview", "editing_id": None,
        "working_sections": None, "working_name": None, "working_description": None,
    }
    _render(ctx, state)


def _render(ctx, state) -> None:
    for child in ctx.content.winfo_children():
        child.destroy()

    scroll = ScrollableFrame(ctx.content)
    scroll.pack(fill="both", expand=True)
    frame = ttk.Frame(scroll.body)
    frame.pack(fill="both", expand=True, padx=32, pady=28)

    if state["mode"] == "overview":
        _render_overview(ctx, state, frame)
    else:
        _render_edit(ctx, state, frame)


def _render_overview(ctx, state, frame) -> None:
    ttk.Label(frame, text="Schedule Templates", style="Heading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Label(
        frame, text="Reusable agenda blueprints you can attach to any repeating meeting.",
        style="Muted.TLabel", wraplength=520,
    ).pack(anchor="w", pady=(0, 16))

    for template in ctx.config.schedule_templates:
        row = tk.Frame(frame, background=theme.CARD_BG, highlightbackground=theme.LINE, highlightthickness=1)
        row.pack(fill="x", pady=4)
        info = tk.Frame(row, background=theme.CARD_BG)
        info.pack(side="left", fill="both", expand=True, padx=14, pady=10)
        tk.Label(info, text=template.name, background=theme.CARD_BG, foreground=theme.INK,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(
            info, text=f"{len(template.sections)} sections - {template.total_minutes} min",
            background=theme.CARD_BG, foreground=theme.MUTED, font=("Segoe UI", 8),
        ).pack(anchor="w")

        button_box = tk.Frame(row, background=theme.CARD_BG)
        button_box.pack(side="right", padx=10)
        icon_button.icon_button(
            button_box, icon_button.GLYPH_EDIT, lambda t=template.id: _goto_edit(ctx, state, t),
        ).pack(side="left", padx=2)
        icon_button.icon_button(
            button_box, icon_button.GLYPH_DUPLICATE, lambda t=template.id: _duplicate_template(ctx, state, t),
        ).pack(side="left", padx=2)
        icon_button.icon_button(
            button_box, icon_button.GLYPH_DELETE, lambda t=template.id: _delete_template(ctx, state, t), danger=True,
        ).pack(side="left", padx=2)

    ttk.Button(
        frame, text="+ New Template", style="Secondary.TButton",
        command=lambda: _goto_edit(ctx, state, None),
    ).pack(anchor="w", pady=(12, 0))


def _goto_edit(ctx, state, template_id) -> None:
    template = ctx.config.find_template(template_id) if template_id else None
    state["mode"] = "edit"
    state["editing_id"] = template_id
    state["working_sections"] = [
        sch.Section(id=s.id, name=s.name, duration_minutes=s.duration_minutes)
        for s in (template.sections if template else [])
    ]
    state["working_name"] = template.name if template else ""
    state["working_description"] = template.description if template else ""
    _render(ctx, state)


def _duplicate_template(ctx, state, template_id) -> None:
    template = ctx.config.find_template(template_id)
    if not template:
        return
    ctx.config.schedule_templates.append(sch.ScheduleTemplate(
        name=f"{template.name} (Copy)",
        description=template.description,
        sections=[
            sch.Section(name=s.name, duration_minutes=s.duration_minutes)
            for s in template.sections
        ],
    ))
    ctx.save_config()
    _render(ctx, state)


def _delete_template(ctx, state, template_id) -> None:
    if len(ctx.config.schedule_templates) <= 1:
        messagebox.showwarning("Can't delete", "You need at least one schedule template.")
        return
    in_use = any(r.schedule_template_id == template_id for r in ctx.config.repeating_instances)
    if in_use and not messagebox.askyesno(
        "Template in use",
        "One or more repeating meetings use this template. Delete it anyway?",
    ):
        return
    ctx.config.schedule_templates = [t for t in ctx.config.schedule_templates if t.id != template_id]
    ctx.save_config()
    _render(ctx, state)


def _render_edit(ctx, state, frame) -> None:
    is_new = state["editing_id"] is None
    ttk.Label(frame, text="New Template" if is_new else "Edit Template", style="Heading.TLabel").pack(anchor="w", pady=(0, 16))

    name_var = tk.StringVar(value=state["working_name"])
    ttk.Label(frame, text="Name", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Entry(frame, textvariable=name_var, width=40).pack(anchor="w", pady=(0, 12))

    description_var = tk.StringVar(value=state["working_description"])
    ttk.Label(frame, text="Description (optional)", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Entry(frame, textvariable=description_var, width=40).pack(anchor="w", pady=(0, 16))

    ttk.Label(frame, text="Sections", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))

    total_label = ttk.Label(frame, text="", style="Body.TLabel")

    def update_total() -> None:
        total = sum(s.duration_minutes for s in state["working_sections"])
        total_label.configure(text=f"Total: {total} minutes")

    build_section_editor(frame, ctx, state["working_sections"], on_change=update_total)
    total_label.pack(anchor="w", pady=(4, 20))

    button_row = ttk.Frame(frame)
    button_row.pack(fill="x")

    def cancel() -> None:
        state["mode"] = "overview"
        _render(ctx, state)

    def save() -> None:
        name = name_var.get().strip() or "Untitled Template"
        description = description_var.get().strip()
        if not state["working_sections"]:
            messagebox.showerror("Add a section", "A template needs at least one section.")
            return
        if is_new:
            ctx.config.schedule_templates.append(sch.ScheduleTemplate(
                name=name, description=description, sections=state["working_sections"],
            ))
        else:
            template = ctx.config.find_template(state["editing_id"])
            template.name = name
            template.description = description
            template.sections = state["working_sections"]
        ctx.save_config()
        state["mode"] = "overview"
        _render(ctx, state)

    ttk.Button(button_row, text="Cancel", style="Secondary.TButton", command=cancel).pack(side="left")
    ttk.Button(button_row, text="Save", style="Primary.TButton", command=save).pack(side="right")
