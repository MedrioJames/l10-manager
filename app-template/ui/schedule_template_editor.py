"""Shared section-list editor (name/duration, drag-to-reorder, remove) used
both by the full Schedules page (ui/schedule_templates.py) and the compact
"+ New Template" modal reachable from ui/instance_form.py - extracted so
neither has to duplicate the drag mechanics.

Reordering uses the same drag technique proven in ui/issue_board.py
(ButtonPress-1/B1-Motion/ButtonRelease-1, a small ghost Toplevel, a pixel
threshold to disambiguate a click from a drag), simplified for a single
vertical list: the drop position is resolved by comparing the cursor's
final Y against each row's vertical midpoint, then the section list is
spliced. The drag handle is a small glyph on the left of each row rather
than the whole row, so editing the name/duration fields doesn't fight with
starting a drag.
"""

import tkinter as tk
from tkinter import messagebox, ttk

import schedule as sch
from ui import icon_button, theme

DRAG_THRESHOLD_PX = 6


def build_section_editor(parent, ctx, working_sections: list, on_change=None) -> None:
    """working_sections is a mutable list of sch.Section, mutated in place.
    on_change() (if given) is called after any edit so the caller can
    refresh a running total or other dependent display."""
    on_change = on_change or (lambda: None)

    sections_frame = ttk.Frame(parent)
    sections_frame.pack(fill="x", pady=(0, 8))

    drag_state = {"dragging": False, "start_index": None, "ghost": None, "start_y": 0}
    row_widgets = []

    def render_sections() -> None:
        for child in sections_frame.winfo_children():
            child.destroy()
        row_widgets.clear()

        for idx, section in enumerate(working_sections):
            row = tk.Frame(sections_frame, background=theme.CARD_BG, highlightbackground=theme.LINE, highlightthickness=1)
            row.pack(fill="x", pady=2)
            row_widgets.append(row)

            handle = tk.Label(
                row, text=icon_button.GLYPH_DRAG, background=theme.CARD_BG, foreground=theme.MUTED,
                cursor="fleur", font=("Segoe UI Symbol", 12),
            )
            handle.pack(side="left", padx=(10, 6), pady=8)

            name_v = tk.StringVar(value=section.name)
            dur_v = tk.StringVar(value=str(section.duration_minutes))

            def on_name_change(*_a, i=idx, v=name_v) -> None:
                working_sections[i].name = v.get()

            def on_dur_change(*_a, i=idx, v=dur_v) -> None:
                try:
                    working_sections[i].duration_minutes = int(v.get())
                except ValueError:
                    return
                on_change()

            name_v.trace_add("write", on_name_change)
            dur_v.trace_add("write", on_dur_change)

            ttk.Entry(row, textvariable=name_v, width=26).pack(side="left", padx=(0, 6), pady=6)
            ttk.Spinbox(row, from_=1, to=180, width=5, textvariable=dur_v).pack(side="left", padx=(0, 6))
            ttk.Label(row, text="min").pack(side="left", padx=(0, 10))

            icon_button.icon_button(
                row, icon_button.GLYPH_DELETE, lambda i=idx: remove_section(i), danger=True,
            ).pack(side="right", padx=8)

            handle.bind("<ButtonPress-1>", lambda e, i=idx: on_press(e, i))
            handle.bind("<B1-Motion>", on_motion)
            handle.bind("<ButtonRelease-1>", on_release)

        on_change()

    def remove_section(idx: int) -> None:
        del working_sections[idx]
        render_sections()

    def add_section() -> None:
        working_sections.append(sch.Section(name="New Section", duration_minutes=5))
        render_sections()

    def on_press(event, idx: int) -> None:
        drag_state["dragging"] = False
        drag_state["start_index"] = idx
        drag_state["start_y"] = event.y_root

    def on_motion(event) -> None:
        if drag_state["start_index"] is None:
            return
        if not drag_state["dragging"] and abs(event.y_root - drag_state["start_y"]) > DRAG_THRESHOLD_PX:
            drag_state["dragging"] = True
            section = working_sections[drag_state["start_index"]]
            ghost = tk.Toplevel(ctx.root)
            ghost.overrideredirect(True)
            ghost.attributes("-topmost", True)
            tk.Label(
                ghost, text=section.name, background=theme.PRIMARY, foreground="white",
                font=("Segoe UI", 9, "bold"), padx=10, pady=4,
            ).pack()
            drag_state["ghost"] = ghost
        if drag_state["dragging"] and drag_state["ghost"] is not None:
            drag_state["ghost"].geometry(f"+{event.x_root + 12}+{event.y_root + 12}")

    def on_release(event) -> None:
        if drag_state["ghost"] is not None:
            drag_state["ghost"].destroy()
            drag_state["ghost"] = None

        if drag_state["dragging"]:
            start_index = drag_state["start_index"]
            target_index = _index_at_point(row_widgets, event.y_root)
            if target_index is not None and target_index != start_index:
                insert_at = target_index - 1 if target_index > start_index else target_index
                section = working_sections.pop(start_index)
                working_sections.insert(insert_at, section)
                render_sections()

        drag_state["dragging"] = False
        drag_state["start_index"] = None

    def _index_at_point(rows, root_y: int) -> int:
        for i, row in enumerate(rows):
            if not row.winfo_exists():
                continue
            midpoint = row.winfo_rooty() + row.winfo_height() / 2
            if root_y < midpoint:
                return i
        return len(rows)

    render_sections()
    ttk.Button(parent, text="+ Add Section", style="Secondary.TButton", command=add_section).pack(anchor="w", pady=(4, 4))


def open_new_template_modal(ctx, on_created) -> None:
    """A compact 'New Template' modal (name/description/sections) - lets a
    user create a template without leaving whatever form they're mid-way
    through filling out (see instance_form.py's "+ New Template" shortcut).
    Saves the new template into ctx.config.schedule_templates and calls
    on_created(template) so the caller can select it in place."""
    win = tk.Toplevel(ctx.root)
    win.title("New Schedule Template")
    win.configure(bg=theme.BG)
    win.transient(ctx.root)

    body = ttk.Frame(win)
    body.pack(fill="both", expand=True, padx=20, pady=20)

    ttk.Label(body, text="New Template", style="Heading.TLabel").pack(anchor="w", pady=(0, 12))

    name_var = tk.StringVar(value="")
    ttk.Label(body, text="Name", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Entry(body, textvariable=name_var, width=36).pack(anchor="w", pady=(0, 10))

    description_var = tk.StringVar(value="")
    ttk.Label(body, text="Description (optional)", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Entry(body, textvariable=description_var, width=36).pack(anchor="w", pady=(0, 12))

    working_sections = [sch.Section(name="New Section", duration_minutes=5)]

    ttk.Label(body, text="Sections", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    total_label = ttk.Label(body, text="", style="Body.TLabel")

    def update_total() -> None:
        total_label.configure(text=f"Total: {sum(s.duration_minutes for s in working_sections)} minutes")

    build_section_editor(body, ctx, working_sections, on_change=update_total)
    total_label.pack(anchor="w", pady=(4, 16))

    button_row = ttk.Frame(body)
    button_row.pack(fill="x")

    def cancel() -> None:
        win.destroy()

    def save() -> None:
        if not working_sections:
            messagebox.showerror("Add a section", "A template needs at least one section.")
            return
        template = sch.ScheduleTemplate(
            name=name_var.get().strip() or "Untitled Template",
            description=description_var.get().strip(),
            sections=working_sections,
        )
        ctx.config.schedule_templates.append(template)
        ctx.save_config()
        win.destroy()
        on_created(template)

    ttk.Button(button_row, text="Cancel", style="Secondary.TButton", command=cancel).pack(side="left")
    ttk.Button(button_row, text="Save", style="Primary.TButton", command=save).pack(side="right")

    win.update_idletasks()
    x = ctx.root.winfo_x() + max((ctx.root.winfo_width() - win.winfo_width()) // 2, 0)
    y = ctx.root.winfo_y() + max((ctx.root.winfo_height() - win.winfo_height()) // 2, 0)
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.grab_set()
