"""Meeting name/description form - shared by the setup wizard and the
settings editor so both stay in sync automatically."""

import tkinter as tk
from tkinter import ttk


class MeetingInfoForm(ttk.Frame):
    def __init__(self, parent, name: str = "", description: str = "", on_change=None):
        super().__init__(parent)
        self.name_var = tk.StringVar(value=name)

        ttk.Label(self, text="Meeting name", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
        name_entry = ttk.Entry(self, textvariable=self.name_var, width=42)
        name_entry.pack(anchor="w", pady=(0, 12))

        ttk.Label(self, text="Description (optional)", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
        self.description_text = tk.Text(self, width=44, height=3, font=("Segoe UI", 10), wrap="word")
        self.description_text.insert("1.0", description)
        self.description_text.pack(anchor="w")

        # Autosave on blur (matching run_meeting.py's notes panel) rather
        # than requiring an explicit Save button - used by the Settings
        # editor; the wizard leaves on_change unset since its own Next
        # button is the natural "confirm this step" action there.
        if on_change is not None:
            name_entry.bind("<FocusOut>", lambda _e: on_change())
            self.description_text.bind("<FocusOut>", lambda _e: on_change())

    def get_data(self) -> dict:
        return {
            "name": self.name_var.get().strip(),
            "description": self.description_text.get("1.0", "end").strip(),
        }
