"""Repeating-instance form (name, description, default length, schedule,
recurrence) - shared by the setup wizard and the settings editor.

Deliberately duck-typed against `schedules` (no schedule.py/config.py
import): each item just needs `.id`/`.name`/`.total_minutes`. Since
schedule.Schedule no longer has a bare `.total_minutes` (resolving a
schedule's total now needs the segment library), callers pass lightweight
wrapper objects (e.g. types.SimpleNamespace) computed via
schedule.schedule_total_minutes() instead of raw Schedule instances.
"""

import tkinter as tk
from tkinter import ttk

from ui.recurrence_widget import RecurrenceEditor
from ui.rounded_button import RoundedButton


def _display_name(schedule) -> str:
    return f"{schedule.name} ({schedule.total_minutes} min)"


class RepeatingInstanceForm(ttk.Frame):
    def __init__(self, parent, schedules, instance=None, on_request_new_schedule=None):
        super().__init__(parent)
        self.schedules = list(schedules)
        self.on_request_new_schedule = on_request_new_schedule

        name = instance.name if instance else ""
        description = instance.description if instance else ""
        length = instance.default_length_minutes if instance else 90
        rule = instance.recurrence if instance else None
        schedule_id = instance.schedule_id if instance else (self.schedules[0].id if self.schedules else None)

        self.name_var = tk.StringVar(value=name)
        self.description_var = tk.StringVar(value=description)
        self.length_var = tk.StringVar(value=str(length))

        self.schedule_id_by_display = {_display_name(s): s.id for s in self.schedules}
        initial_display = next(
            (_display_name(s) for s in self.schedules if s.id == schedule_id),
            (_display_name(self.schedules[0]) if self.schedules else ""),
        )
        self.schedule_name_var = tk.StringVar(value=initial_display)

        ttk.Label(self, text="Name", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Entry(self, textvariable=self.name_var, width=38).pack(anchor="w", pady=(0, 10))

        ttk.Label(self, text="Description (optional)", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Entry(self, textvariable=self.description_var, width=38).pack(anchor="w", pady=(0, 10))

        length_row = ttk.Frame(self)
        length_row.pack(anchor="w", pady=(0, 10))
        ttk.Label(length_row, text="Default length (minutes)").pack(side="left", padx=(0, 8))
        ttk.Spinbox(length_row, from_=15, to=240, increment=5, width=6, textvariable=self.length_var).pack(side="left")

        ttk.Label(self, text="Schedule", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
        schedule_row = ttk.Frame(self)
        schedule_row.pack(anchor="w", pady=(0, 12))
        self.schedule_combo = ttk.Combobox(
            schedule_row, textvariable=self.schedule_name_var, state="readonly",
            values=list(self.schedule_id_by_display.keys()), width=32,
        )
        self.schedule_combo.pack(side="left")
        if self.on_request_new_schedule:
            RoundedButton(
                schedule_row, text="+ New Schedule", variant="tonal",
                command=lambda: self.on_request_new_schedule(self),
            ).pack(side="left", padx=(8, 0))

        ttk.Label(self, text="Recurrence", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
        self.recurrence_editor = RecurrenceEditor(self, initial_rule=rule)
        self.recurrence_editor.pack(anchor="w", fill="x")

    def add_schedule_option(self, schedule) -> None:
        """Adds a newly-created schedule to the combobox in place and
        selects it - used by the "+ New Schedule" shortcut so the rest of
        this form (name/description/length/recurrence already typed in)
        never gets rebuilt or loses its values."""
        self.schedules.append(schedule)
        display = _display_name(schedule)
        self.schedule_id_by_display[display] = schedule.id
        self.schedule_combo.configure(values=list(self.schedule_id_by_display.keys()))
        self.schedule_name_var.set(display)

    def get_instance_fields(self) -> dict:
        try:
            length = int(self.length_var.get())
        except ValueError:
            length = 90
        schedule_id = self.schedule_id_by_display.get(self.schedule_name_var.get())
        rule = self.recurrence_editor.get_rule()  # raises ValueError on bad input
        return {
            "name": self.name_var.get().strip() or "Untitled Meeting",
            "description": self.description_var.get().strip(),
            "default_length_minutes": length,
            "schedule_id": schedule_id,
            "recurrence": rule,
        }
