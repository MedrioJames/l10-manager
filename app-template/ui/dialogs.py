"""Small themed modal input dialogs - tkinter.simpledialog looks dated and
isn't easily themed, so these are minimal replacements for the couple of
prompts the schedule editor needs (a section name, a section length)."""

import tkinter as tk
from tkinter import ttk

from ui.rounded_button import RoundedButton


def ask_text(root, title: str, prompt: str, initial: str = ""):
    result = {"value": None}
    win = tk.Toplevel(root)
    win.title(title)
    win.resizable(False, False)
    win.transient(root)

    ttk.Label(win, text=prompt).pack(padx=20, pady=(16, 6))
    var = tk.StringVar(value=initial)
    entry = ttk.Entry(win, textvariable=var, width=30)
    entry.pack(padx=20, pady=(0, 12))
    entry.focus_set()

    def confirm(_event=None):
        result["value"] = var.get().strip()
        win.destroy()

    def cancel():
        win.destroy()

    button_row = ttk.Frame(win)
    button_row.pack(pady=(0, 16))
    RoundedButton(button_row, text="Cancel", variant="tonal", command=cancel).pack(side="left", padx=4)
    RoundedButton(button_row, text="OK", variant="filled", command=confirm).pack(side="left", padx=4)

    win.bind("<Return>", confirm)
    win.grab_set()
    win.wait_window()
    return result["value"]


def ask_minutes(root, title: str, prompt: str, initial: int = 10):
    result = {"value": None}
    win = tk.Toplevel(root)
    win.title(title)
    win.resizable(False, False)
    win.transient(root)

    ttk.Label(win, text=prompt).pack(padx=20, pady=(16, 6))
    var = tk.StringVar(value=str(initial))
    entry = ttk.Spinbox(win, from_=1, to=240, textvariable=var, width=8)
    entry.pack(padx=20, pady=(0, 12))
    entry.focus_set()

    def confirm(_event=None):
        try:
            result["value"] = int(var.get())
        except ValueError:
            result["value"] = initial
        win.destroy()

    def cancel():
        win.destroy()

    button_row = ttk.Frame(win)
    button_row.pack(pady=(0, 16))
    RoundedButton(button_row, text="Cancel", variant="tonal", command=cancel).pack(side="left", padx=4)
    RoundedButton(button_row, text="OK", variant="filled", command=confirm).pack(side="left", padx=4)

    win.bind("<Return>", confirm)
    win.grab_set()
    win.wait_window()
    return result["value"]
