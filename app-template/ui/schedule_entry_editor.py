"""Shared entry-list editor (resolved name/duration, drag-to-reorder,
edit-override, remove) used both by the Schedules tab of
ui/schedule_builder.py and the compact "+ New Schedule" modal reachable
from ui/instance_form.py - extracted so neither has to duplicate the drag
mechanics. Renamed from schedule_template_editor.py's build_section_editor
now that entries reference global Segments rather than holding inline
section data.

Reordering uses the same drag technique proven in ui/issue_board.py
(ButtonPress-1/B1-Motion/ButtonRelease-1, a small ghost Toplevel, a pixel
threshold to disambiguate a click from a drag), simplified for a single
vertical list: the drop position is resolved by comparing the cursor's
final Y against each row's vertical midpoint, then the entry list is
spliced. The drag handle is a small glyph on the left of each row rather
than the whole row, so editing doesn't fight with starting a drag.
"""

import tkinter as tk
from tkinter import messagebox, ttk

import schedule as sch
from ui import icon_button, segment_override_form, segment_picker, theme
from ui.rounded_card import RoundedCard

DRAG_THRESHOLD_PX = 6


def _resolve_display(ctx, entry: sch.ScheduleSegmentEntry):
    segment = ctx.config.find_segment(entry.segment_id)
    if segment is None:
        return "(missing segment)", 0, False
    name = entry.name_override if entry.name_override is not None else segment.name
    duration = entry.duration_override if entry.duration_override is not None else segment.duration_minutes
    customized = (
        entry.name_override is not None or entry.duration_override is not None or bool(entry.config_overrides)
    )
    return name, duration, customized


def build_entry_list_editor(parent, ctx, entries: list, on_change=None) -> None:
    """entries is a mutable list of sch.ScheduleSegmentEntry, mutated in
    place. on_change() (if given) is called after any edit so the caller
    can refresh a running total or other dependent display."""
    on_change = on_change or (lambda: None)

    entries_frame = ttk.Frame(parent)
    entries_frame.pack(fill="x", pady=(0, 8))

    drag_state = {"dragging": False, "start_index": None, "ghost": None, "start_y": 0}
    row_widgets = []

    def render_entries() -> None:
        for child in entries_frame.winfo_children():
            child.destroy()
        row_widgets.clear()

        for idx, entry in enumerate(entries):
            card = RoundedCard(entries_frame)
            card.pack(fill="x", pady=2)
            row = card.body
            row_widgets.append(card)

            handle = tk.Label(
                row, text=icon_button.GLYPH_DRAG, background=theme.CARD_BG, foreground=theme.MUTED,
                cursor="fleur", font=("Segoe UI Symbol", 12),
            )
            handle.pack(side="left", padx=(10, 6), pady=8)

            name, duration, customized = _resolve_display(ctx, entry)
            info = tk.Frame(row, background=theme.CARD_BG)
            info.pack(side="left", fill="both", expand=True, padx=(0, 6), pady=6)
            tk.Label(info, text=name, background=theme.CARD_BG, foreground=theme.INK,
                     font=("Segoe UI", 10, "bold")).pack(anchor="w")
            tag = f"{duration} min" + (" (customized)" if customized else "")
            tk.Label(info, text=tag, background=theme.CARD_BG, foreground=theme.MUTED, font=("Segoe UI", 9)).pack(anchor="w")

            icon_button.icon_button(row, icon_button.GLYPH_EDIT, lambda i=idx: edit_entry(i)).pack(side="right", padx=2)
            icon_button.icon_button(
                row, icon_button.GLYPH_DELETE, lambda i=idx: remove_entry(i), danger=True,
            ).pack(side="right", padx=2)

            handle.bind("<ButtonPress-1>", lambda e, i=idx: on_press(e, i))
            handle.bind("<B1-Motion>", on_motion)
            handle.bind("<ButtonRelease-1>", on_release)

        on_change()

    def edit_entry(idx: int) -> None:
        entry = entries[idx]
        segment = ctx.config.find_segment(entry.segment_id)
        if segment is None:
            return
        name, duration, _ = _resolve_display(ctx, entry)
        resolved = {
            "name": name, "duration_minutes": duration,
            "config": {**segment.resolved_config(), **entry.config_overrides},
        }

        def on_save(fields) -> None:
            entry.name_override = fields["name_override"]
            entry.duration_override = fields["duration_override"]
            entry.config_overrides = fields["config_overrides"]
            render_entries()

        segment_override_form.open_override_modal(
            ctx, segment, resolved, on_save, title="Customize Segment for This Schedule",
        )

    def remove_entry(idx: int) -> None:
        del entries[idx]
        render_entries()

    def add_entry() -> None:
        def on_picked(segment) -> None:
            entries.append(sch.ScheduleSegmentEntry(segment_id=segment.id))
            render_entries()

        segment_picker.open_segment_picker(ctx, on_picked, title="Add Segment to Schedule")

    def on_press(event, idx: int) -> None:
        drag_state["dragging"] = False
        drag_state["start_index"] = idx
        drag_state["start_y"] = event.y_root

    def on_motion(event) -> None:
        if drag_state["start_index"] is None:
            return
        if not drag_state["dragging"] and abs(event.y_root - drag_state["start_y"]) > DRAG_THRESHOLD_PX:
            drag_state["dragging"] = True
            entry = entries[drag_state["start_index"]]
            name, _duration, _customized = _resolve_display(ctx, entry)
            ghost = tk.Toplevel(ctx.root)
            ghost.overrideredirect(True)
            ghost.attributes("-topmost", True)
            tk.Label(
                ghost, text=name, background=theme.PRIMARY, foreground="white",
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
                entry = entries.pop(start_index)
                entries.insert(insert_at, entry)
                render_entries()

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

    render_entries()
    ttk.Button(parent, text="+ Add Segment", style="Secondary.TButton", command=add_entry).pack(anchor="w", pady=(4, 4))


def open_new_schedule_modal(ctx, on_created) -> None:
    """A compact 'New Schedule' modal (name/description/entries) - lets a
    user create a schedule without leaving whatever form they're mid-way
    through filling out (see instance_form.py's "+ New Schedule" shortcut).
    Saves the new schedule into ctx.config.schedules and calls
    on_created(schedule) so the caller can select it in place. Starts with
    an empty entry list - segments must be picked/created from the global
    library, there's no more "just type a name" shortcut."""
    win = tk.Toplevel(ctx.root)
    win.title("New Schedule")
    win.configure(bg=theme.BG)
    win.transient(ctx.root)

    body = ttk.Frame(win)
    body.pack(fill="both", expand=True, padx=20, pady=20)

    ttk.Label(body, text="New Schedule", style="Heading.TLabel").pack(anchor="w", pady=(0, 12))

    name_var = tk.StringVar(value="")
    ttk.Label(body, text="Name", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Entry(body, textvariable=name_var, width=36).pack(anchor="w", pady=(0, 10))

    description_var = tk.StringVar(value="")
    ttk.Label(body, text="Description (optional)", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Entry(body, textvariable=description_var, width=36).pack(anchor="w", pady=(0, 12))

    working_entries: list = []

    ttk.Label(body, text="Segments", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    total_label = ttk.Label(body, text="", style="Body.TLabel")

    def update_total() -> None:
        temp_schedule = sch.Schedule(entries=working_entries)
        total = sch.schedule_total_minutes(temp_schedule, ctx.config.segments)
        total_label.configure(text=f"Total: {total} minutes")

    build_entry_list_editor(body, ctx, working_entries, on_change=update_total)
    total_label.pack(anchor="w", pady=(4, 16))

    button_row = ttk.Frame(body)
    button_row.pack(fill="x")

    def cancel() -> None:
        win.destroy()

    def save() -> None:
        if not working_entries:
            messagebox.showerror("Add a segment", "A schedule needs at least one segment.")
            return
        schedule = sch.Schedule(
            name=name_var.get().strip() or "Untitled Schedule",
            description=description_var.get().strip(),
            entries=working_entries,
        )
        ctx.config.schedules.append(schedule)
        ctx.save_config()
        win.destroy()
        on_created(schedule)

    ttk.Button(button_row, text="Cancel", style="Secondary.TButton", command=cancel).pack(side="left")
    ttk.Button(button_row, text="Save", style="Primary.TButton", command=save).pack(side="right")

    win.update_idletasks()
    x = ctx.root.winfo_x() + max((ctx.root.winfo_width() - win.winfo_width()) // 2, 0)
    y = ctx.root.winfo_y() + max((ctx.root.winfo_height() - win.winfo_height()) // 2, 0)
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.grab_set()
