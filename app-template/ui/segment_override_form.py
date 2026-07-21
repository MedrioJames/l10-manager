"""Shared override-editing form - given a Segment and its currently
resolved effective values, lets the user override name/duration/config
for one specific position (a Schedule entry, or a single occurrence).
Always saves back whatever's currently in the fields - no diffing against
the segment's own values, since "override any of the existing data (or
data left empty)" means explicit is fine even when it happens to match.
"""

import tkinter as tk
from tkinter import ttk

import segment_types as st
from ui import theme
from ui.rounded_button import RoundedButton


def open_override_modal(ctx, segment, resolved: dict, on_save, title: str = "Customize Segment") -> None:
    win = tk.Toplevel(ctx.root)
    win.title(title)
    win.configure(bg=theme.BG)
    win.transient(ctx.root)

    body = ttk.Frame(win)
    body.pack(fill="both", expand=True, padx=20, pady=20)
    ttk.Label(body, text=title, style="Heading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Label(body, text=f"Based on: {segment.name}", style="Muted.TLabel").pack(anchor="w", pady=(0, 12))

    name_var = tk.StringVar(value=resolved.get("name", segment.name))
    ttk.Label(body, text="Name", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Entry(body, textvariable=name_var, width=36).pack(anchor="w", pady=(0, 10))

    duration_var = tk.StringVar(value=str(resolved.get("duration_minutes", segment.duration_minutes)))
    ttk.Label(body, text="Duration (minutes)", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Spinbox(body, from_=1, to=180, width=6, textvariable=duration_var).pack(anchor="w", pady=(0, 10))

    config_frame = ttk.Frame(body)
    config_frame.pack(fill="x", pady=(4, 10))
    values = dict(resolved.get("config", segment.resolved_config()))
    seg_type = st.get_segment_type(segment.type_id)
    seg_type.render_settings_form(config_frame, values, lambda: None)

    button_row = ttk.Frame(body)
    button_row.pack(fill="x", pady=(10, 0))

    def cancel() -> None:
        win.destroy()

    def save() -> None:
        try:
            duration = int(duration_var.get())
        except ValueError:
            duration = segment.duration_minutes
        win.destroy()
        on_save({
            "name_override": name_var.get().strip() or segment.name,
            "duration_override": duration,
            "config_overrides": dict(values),
        })

    RoundedButton(button_row, text="Cancel", variant="tonal", command=cancel).pack(side="left")
    RoundedButton(button_row, text="Save", variant="filled", command=save).pack(side="right")

    win.update_idletasks()
    x = ctx.root.winfo_x() + max((ctx.root.winfo_width() - win.winfo_width()) // 2, 0)
    y = ctx.root.winfo_y() + max((ctx.root.winfo_height() - win.winfo_height()) // 2, 0)
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.grab_set()
