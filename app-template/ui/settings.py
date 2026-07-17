"""Settings editor - the same meeting-info and repeating-instance fields the
setup wizard collects, but always reachable and editable, not a one-time
flow. Reuses ui/meeting_info_form.py and ui/instance_form.py so the two
stay in sync automatically.
"""

import tkinter as tk
from tkinter import ttk, messagebox

import config as cfgmod
from ui import theme
from ui.meeting_info_form import MeetingInfoForm
from ui.instance_form import RepeatingInstanceForm
from ui.scrollable import ScrollableFrame


def build(ctx, **kwargs) -> None:
    state = {"mode": "overview", "editing_id": None}
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
        _render_edit_instance(ctx, state, frame)


def _render_overview(ctx, state, frame) -> None:
    ttk.Label(frame, text="Settings", style="Heading.TLabel").pack(anchor="w", pady=(0, 16))

    ttk.Label(frame, text="Meeting Info", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 8))
    info_form = MeetingInfoForm(frame, name=ctx.config.meeting.name, description=ctx.config.meeting.description)
    info_form.pack(anchor="w")

    def save_info() -> None:
        data = info_form.get_data()
        ctx.config.meeting = cfgmod.MeetingInfo(name=data["name"], description=data["description"])
        ctx.save_config()
        _render(ctx, state)

    ttk.Button(frame, text="Save Meeting Info", style="Primary.TButton", command=save_info).pack(anchor="w", pady=(10, 24))

    ttk.Label(frame, text="Repeating Meetings", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 8))

    if not ctx.config.repeating_instances:
        ttk.Label(frame, text="No repeating meetings yet.", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
    else:
        for instance in ctx.config.repeating_instances:
            row = tk.Frame(frame, background=theme.CARD_BG, highlightbackground=theme.LINE, highlightthickness=1)
            row.pack(fill="x", pady=4)
            info = tk.Frame(row, background=theme.CARD_BG)
            info.pack(side="left", fill="both", expand=True, padx=12, pady=8)
            tk.Label(info, text=instance.name, background=theme.CARD_BG, foreground=theme.INK,
                     font=("Segoe UI", 10, "bold")).pack(anchor="w")
            tk.Label(info, text=f"{instance.recurrence.describe()} - {instance.default_length_minutes} min",
                     background=theme.CARD_BG, foreground=theme.MUTED, font=("Segoe UI", 8)).pack(anchor="w")

            button_box = tk.Frame(row, background=theme.CARD_BG)
            button_box.pack(side="right", padx=8)
            ttk.Button(button_box, text="Edit", style="Secondary.TButton",
                       command=lambda i=instance.id: _goto_edit(ctx, state, i)).pack(side="left", padx=2)
            ttk.Button(button_box, text="Remove", style="Secondary.TButton",
                       command=lambda i=instance.id: _remove_instance(ctx, state, i)).pack(side="left", padx=2)

    ttk.Button(
        frame, text="+ Add a Repeating Meeting", style="Secondary.TButton",
        command=lambda: _goto_edit(ctx, state, None),
    ).pack(anchor="w", pady=(12, 0))


def _goto_edit(ctx, state, instance_id) -> None:
    state["mode"] = "edit_instance"
    state["editing_id"] = instance_id
    _render(ctx, state)


def _remove_instance(ctx, state, instance_id) -> None:
    if not messagebox.askyesno("Remove meeting", "Remove this repeating meeting? This can't be undone."):
        return
    ctx.config.repeating_instances = [r for r in ctx.config.repeating_instances if r.id != instance_id]
    ctx.save_config()
    _render(ctx, state)


def _render_edit_instance(ctx, state, frame) -> None:
    instance = ctx.config.find_instance(state["editing_id"])
    title = "Edit Repeating Meeting" if instance else "Add a Repeating Meeting"
    ttk.Label(frame, text=title, style="Heading.TLabel").pack(anchor="w", pady=(0, 16))

    form = RepeatingInstanceForm(frame, templates=ctx.config.schedule_templates, instance=instance)
    form.pack(anchor="w", fill="x")

    button_row = ttk.Frame(frame)
    button_row.pack(fill="x", pady=(20, 0))

    def cancel() -> None:
        state["mode"] = "overview"
        _render(ctx, state)

    def save() -> None:
        try:
            fields = form.get_instance_fields()
        except ValueError as exc:
            messagebox.showerror("Check the recurrence", str(exc))
            return
        if instance:
            instance.name = fields["name"]
            instance.description = fields["description"]
            instance.default_length_minutes = fields["default_length_minutes"]
            instance.schedule_template_id = fields["schedule_template_id"]
            instance.recurrence = fields["recurrence"]
        else:
            ctx.config.repeating_instances.append(cfgmod.RepeatingInstance(
                name=fields["name"],
                description=fields["description"],
                default_length_minutes=fields["default_length_minutes"],
                recurrence=fields["recurrence"],
                schedule_template_id=fields["schedule_template_id"],
            ))
        ctx.save_config()
        state["mode"] = "overview"
        _render(ctx, state)

    ttk.Button(button_row, text="Cancel", style="Secondary.TButton", command=cancel).pack(side="left")
    ttk.Button(button_row, text="Save", style="Primary.TButton", command=save).pack(side="right")
