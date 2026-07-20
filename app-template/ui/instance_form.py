"""Repeating-instance form (name, description, default length, schedule
template, recurrence) - shared by the setup wizard and the settings editor.
"""

import tkinter as tk
from tkinter import ttk

from ui.recurrence_widget import RecurrenceEditor


def _display_name(template) -> str:
    return f"{template.name} ({template.total_minutes} min)"


class RepeatingInstanceForm(ttk.Frame):
    def __init__(self, parent, templates, instance=None, on_request_new_template=None):
        super().__init__(parent)
        self.templates = list(templates)
        self.on_request_new_template = on_request_new_template

        name = instance.name if instance else ""
        description = instance.description if instance else ""
        length = instance.default_length_minutes if instance else 90
        rule = instance.recurrence if instance else None
        template_id = instance.schedule_template_id if instance else (self.templates[0].id if self.templates else None)

        self.name_var = tk.StringVar(value=name)
        self.description_var = tk.StringVar(value=description)
        self.length_var = tk.StringVar(value=str(length))

        self.template_id_by_display = {_display_name(t): t.id for t in self.templates}
        initial_display = next(
            (_display_name(t) for t in self.templates if t.id == template_id),
            (_display_name(self.templates[0]) if self.templates else ""),
        )
        self.template_name_var = tk.StringVar(value=initial_display)

        ttk.Label(self, text="Name", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Entry(self, textvariable=self.name_var, width=38).pack(anchor="w", pady=(0, 10))

        ttk.Label(self, text="Description (optional)", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Entry(self, textvariable=self.description_var, width=38).pack(anchor="w", pady=(0, 10))

        length_row = ttk.Frame(self)
        length_row.pack(anchor="w", pady=(0, 10))
        ttk.Label(length_row, text="Default length (minutes)").pack(side="left", padx=(0, 8))
        ttk.Spinbox(length_row, from_=15, to=240, increment=5, width=6, textvariable=self.length_var).pack(side="left")

        ttk.Label(self, text="Schedule template", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
        template_row = ttk.Frame(self)
        template_row.pack(anchor="w", pady=(0, 12))
        self.template_combo = ttk.Combobox(
            template_row, textvariable=self.template_name_var, state="readonly",
            values=list(self.template_id_by_display.keys()), width=32,
        )
        self.template_combo.pack(side="left")
        if self.on_request_new_template:
            ttk.Button(
                template_row, text="+ New Template", style="Secondary.TButton",
                command=lambda: self.on_request_new_template(self),
            ).pack(side="left", padx=(8, 0))

        ttk.Label(self, text="Recurrence", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
        self.recurrence_editor = RecurrenceEditor(self, initial_rule=rule)
        self.recurrence_editor.pack(anchor="w", fill="x")

    def add_template_option(self, template) -> None:
        """Adds a newly-created template to the combobox in place and
        selects it - used by the "+ New Template" shortcut so the rest of
        this form (name/description/length/recurrence already typed in)
        never gets rebuilt or loses its values."""
        self.templates.append(template)
        display = _display_name(template)
        self.template_id_by_display[display] = template.id
        self.template_combo.configure(values=list(self.template_id_by_display.keys()))
        self.template_name_var.set(display)

    def get_instance_fields(self) -> dict:
        try:
            length = int(self.length_var.get())
        except ValueError:
            length = 90
        template_id = self.template_id_by_display.get(self.template_name_var.get())
        rule = self.recurrence_editor.get_rule()  # raises ValueError on bad input
        return {
            "name": self.name_var.get().strip() or "Untitled Meeting",
            "description": self.description_var.get().strip(),
            "default_length_minutes": length,
            "schedule_template_id": template_id,
            "recurrence": rule,
        }
