"""First-run setup wizard: meeting info, then one or more repeating
instances. Every step is skippable - falls back to sensible defaults rather
than blocking the app. Reuses the same form widgets as the settings editor
(ui/meeting_info_form.py, ui/instance_form.py) so both stay in sync.
"""

from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox

import config as cfgmod
import schedule as sch
from ui import icon_button, schedule_entry_editor, theme
from ui.meeting_info_form import MeetingInfoForm
from ui.instance_form import RepeatingInstanceForm
from ui.rounded_card import RoundedCard
from ui.scrollable import ScrollableFrame


def _app_dir() -> Path:
    return Path(cfgmod.__file__).resolve().parent


def build(ctx, **kwargs) -> None:
    state = {"step": "info", "pending_instances": []}
    _render(ctx, state)


def _render(ctx, state) -> None:
    for child in ctx.content.winfo_children():
        child.destroy()

    scroll = ScrollableFrame(ctx.content)
    scroll.pack(fill="both", expand=True)
    frame = ttk.Frame(scroll.body)
    frame.pack(fill="both", expand=True, padx=theme.SPACE_XXL, pady=theme.SPACE_XL)

    if state["step"] == "info":
        _render_info_step(ctx, state, frame)
    elif state["step"] == "instances":
        _render_instances_step(ctx, state, frame)
    elif state["step"] == "add_instance":
        _render_add_instance_step(ctx, state, frame)


def _render_info_step(ctx, state, frame) -> None:
    ttk.Label(frame, text="Let's set up this L10", style="Heading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Label(
        frame, text="A couple of quick questions - you can change any of this later from Settings.",
        style="Muted.TLabel", wraplength=480,
    ).pack(anchor="w", pady=(0, 20))

    default_name = ctx.config.meeting.name or cfgmod.default_meeting_name(_app_dir())
    form = MeetingInfoForm(frame, name=default_name, description=ctx.config.meeting.description)
    form.pack(anchor="w")

    button_row = ttk.Frame(frame)
    button_row.pack(fill="x", pady=(24, 0))

    def skip_all() -> None:
        ctx.config.onboarded = True
        ctx.save_config()
        ctx.navigate("dashboard")

    def next_step() -> None:
        data = form.get_data()
        ctx.config.meeting = cfgmod.MeetingInfo(name=data["name"] or default_name, description=data["description"])
        state["step"] = "instances"
        _render(ctx, state)

    ttk.Button(button_row, text="Skip Setup", style="Secondary.TButton", command=skip_all).pack(side="left")
    ttk.Button(button_row, text="Next", style="Primary.TButton", command=next_step).pack(side="right")


def _render_instances_step(ctx, state, frame) -> None:
    ttk.Label(frame, text="Set up repeating meetings", style="Heading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Label(
        frame, text="Add one or more recurring L10 instances - e.g. a weekly leadership sync. "
                     "You can always add more later.",
        style="Muted.TLabel", wraplength=480,
    ).pack(anchor="w", pady=(0, 16))

    list_frame = ttk.Frame(frame)
    list_frame.pack(fill="both", expand=True, pady=(0, 12))

    if not state["pending_instances"]:
        ttk.Label(list_frame, text="No repeating meetings added yet.", style="Muted.TLabel").pack(anchor="w", pady=8)
    else:
        for idx, fields in enumerate(state["pending_instances"]):
            card = RoundedCard(list_frame)
            card.pack(fill="x", pady=4)
            row = card.body
            info = tk.Frame(row, background=theme.CARD_BG)
            info.pack(side="left", fill="both", expand=True, padx=12, pady=8)
            tk.Label(info, text=fields["name"], background=theme.CARD_BG, foreground=theme.INK,
                     font=("Segoe UI", 10, "bold")).pack(anchor="w")
            tk.Label(info, text=fields["recurrence"].describe(), background=theme.CARD_BG,
                     foreground=theme.MUTED, font=("Segoe UI", 9)).pack(anchor="w")
            icon_button.icon_button(
                row, icon_button.GLYPH_DELETE, lambda i=idx: _remove_instance(ctx, state, i), danger=True,
            ).pack(side="right", padx=8)

    ttk.Button(
        frame, text="+ Add a Repeating Meeting", style="Secondary.TButton",
        command=lambda: _goto_add_instance(ctx, state),
    ).pack(anchor="w", pady=(0, 20))

    button_row = ttk.Frame(frame)
    button_row.pack(fill="x")

    def back() -> None:
        state["step"] = "info"
        _render(ctx, state)

    def finish() -> None:
        for fields in state["pending_instances"]:
            ctx.config.repeating_instances.append(cfgmod.RepeatingInstance(
                name=fields["name"],
                description=fields["description"],
                default_length_minutes=fields["default_length_minutes"],
                recurrence=fields["recurrence"],
                schedule_id=fields["schedule_id"],
            ))
        ctx.config.onboarded = True
        ctx.save_config()
        ctx.navigate("dashboard")

    ttk.Button(button_row, text="Back", style="Secondary.TButton", command=back).pack(side="left")
    finish_label = "Finish" if state["pending_instances"] else "Finish (no repeating meetings for now)"
    ttk.Button(button_row, text=finish_label, style="Primary.TButton", command=finish).pack(side="right")


def _remove_instance(ctx, state, idx: int) -> None:
    del state["pending_instances"][idx]
    _render(ctx, state)


def _goto_add_instance(ctx, state) -> None:
    state["step"] = "add_instance"
    _render(ctx, state)


def _render_add_instance_step(ctx, state, frame) -> None:
    ttk.Label(frame, text="Add a repeating meeting", style="Heading.TLabel").pack(anchor="w", pady=(0, 16))

    def request_new_schedule(form_ref) -> None:
        def on_created(new_schedule) -> None:
            wrapper = sch.schedule_display_items([new_schedule], ctx.config.segments)[0]
            form_ref.add_schedule_option(wrapper)

        schedule_entry_editor.open_new_schedule_modal(ctx, on_created)

    form = RepeatingInstanceForm(
        frame, schedules=sch.schedule_display_items(ctx.config.schedules, ctx.config.segments),
        on_request_new_schedule=request_new_schedule,
    )
    form.pack(anchor="w", fill="x")

    button_row = ttk.Frame(frame)
    button_row.pack(fill="x", pady=(20, 0))

    def cancel() -> None:
        state["step"] = "instances"
        _render(ctx, state)

    def save() -> None:
        try:
            fields = form.get_instance_fields()
        except ValueError as exc:
            messagebox.showerror("Check the recurrence", str(exc))
            return
        state["pending_instances"].append(fields)
        state["step"] = "instances"
        _render(ctx, state)

    ttk.Button(button_row, text="Cancel", style="Secondary.TButton", command=cancel).pack(side="left")
    ttk.Button(button_row, text="Add", style="Primary.TButton", command=save).pack(side="right")
