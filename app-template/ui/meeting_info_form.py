"""Meeting name/description form - shared by the setup wizard and the
settings editor so both stay in sync automatically."""

import tkinter as tk
from tkinter import ttk


class MeetingInfoForm(ttk.Frame):
    def __init__(self, parent, name: str = "", description: str = ""):
        super().__init__(parent)
        self.name_var = tk.StringVar(value=name)

        ttk.Label(self, text="Meeting name", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Entry(self, textvariable=self.name_var, width=42).pack(anchor="w", pady=(0, 12))

        ttk.Label(self, text="Description (optional)", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
        self.description_text = tk.Text(self, width=44, height=3, font=("Segoe UI", 10), wrap="word")
        self.description_text.insert("1.0", description)
        self.description_text.pack(anchor="w")

    def get_data(self) -> dict:
        return {
            "name": self.name_var.get().strip(),
            "description": self.description_text.get("1.0", "end").strip(),
        }
