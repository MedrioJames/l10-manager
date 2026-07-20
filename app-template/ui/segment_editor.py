"""Global Segment library editor - create/edit a named, reusable Segment
(name, duration, type, and the type's own config). Type is only pickable
when creating a new segment; editing an existing one shows its type
locked/read-only, since changing a segment's type after the fact would
orphan its config in confusing ways - delete-and-recreate is the intended
path for "picked the wrong type".
"""

import tkinter as tk
from tkinter import messagebox, ttk

import schedule as sch
import segment_types as st
from ui import theme


def open_segment_editor_modal(ctx, segment=None, locked_type=None, on_saved=None) -> None:
    is_new = segment is None
    win = tk.Toplevel(ctx.root)
    win.title("New Segment" if is_new else "Edit Segment")
    win.configure(bg=theme.BG)
    win.transient(ctx.root)

    body = ttk.Frame(win)
    body.pack(fill="both", expand=True, padx=20, pady=20)
    ttk.Label(body, text="New Segment" if is_new else "Edit Segment", style="Heading.TLabel").pack(anchor="w", pady=(0, 12))

    name_var = tk.StringVar(value=segment.name if segment else "")
    ttk.Label(body, text="Name", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Entry(body, textvariable=name_var, width=36).pack(anchor="w", pady=(0, 10))

    duration_var = tk.StringVar(value=str(segment.duration_minutes if segment else 5))
    ttk.Label(body, text="Default duration (minutes)", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Spinbox(body, from_=1, to=180, width=6, textvariable=duration_var).pack(anchor="w", pady=(0, 10))

    all_types = st.all_segment_types()
    type_by_display = {t.display_name: t.type_id for t in all_types}
    default_type_id = locked_type or all_types[0].type_id

    ttk.Label(body, text="Type", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    if segment:
        current_type = st.get_segment_type(segment.type_id)
        type_var = tk.StringVar(value=current_type.display_name)
        ttk.Label(body, textvariable=type_var, style="Body.TLabel").pack(anchor="w", pady=(0, 10))
        type_combo = None
    else:
        type_var = tk.StringVar(value=st.get_segment_type(default_type_id).display_name)
        type_combo = ttk.Combobox(
            body, textvariable=type_var, state="readonly", width=28, values=list(type_by_display.keys()),
        )
        type_combo.pack(anchor="w", pady=(0, 10))

    config_frame = ttk.Frame(body)
    config_frame.pack(fill="x", pady=(4, 10))

    values = dict(segment.config) if segment else {}

    def current_type_id() -> str:
        if segment:
            return segment.type_id
        return type_by_display.get(type_var.get(), default_type_id)

    def render_config_form() -> None:
        for child in config_frame.winfo_children():
            child.destroy()
        st.get_segment_type(current_type_id()).render_settings_form(config_frame, values, lambda: None)

    render_config_form()
    if type_combo is not None:
        def on_type_change(_event=None) -> None:
            values.clear()
            render_config_form()
        type_combo.bind("<<ComboboxSelected>>", on_type_change)

    button_row = ttk.Frame(body)
    button_row.pack(fill="x", pady=(10, 0))

    def cancel() -> None:
        win.destroy()

    def save() -> None:
        name = name_var.get().strip()
        if not name:
            messagebox.showerror("Name required", "Give this segment a name.")
            return
        try:
            duration = int(duration_var.get())
        except ValueError:
            duration = 5

        if segment:
            segment.name = name
            segment.duration_minutes = duration
            segment.config = dict(values)
            result = segment
        else:
            result = sch.Segment(
                type_id=current_type_id(), name=name, duration_minutes=duration, config=dict(values),
            )
            ctx.config.segments.append(result)
        ctx.save_config()
        win.destroy()
        if on_saved:
            on_saved(result)

    ttk.Button(button_row, text="Cancel", style="Secondary.TButton", command=cancel).pack(side="left")
    ttk.Button(button_row, text="Save", style="Primary.TButton", command=save).pack(side="right")

    win.update_idletasks()
    x = ctx.root.winfo_x() + max((ctx.root.winfo_width() - win.winfo_width()) // 2, 0)
    y = ctx.root.winfo_y() + max((ctx.root.winfo_height() - win.winfo_height()) // 2, 0)
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.grab_set()
