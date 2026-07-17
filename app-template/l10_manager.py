"""L10 Manager - placeholder application.

This is a stand-in for the real app. It proves the install -> shortcut ->
launcher -> app chain works end to end. Real L10 features (Scorecard,
Rocks, Issues, IDS, Conclude) land in later phases.
"""

import tkinter as tk
from pathlib import Path


def meeting_name() -> str:
    app_dir = Path(__file__).resolve().parent
    return app_dir.parent.name or "L10 Manager"


def version() -> str:
    version_file = Path(__file__).resolve().parent / "version.txt"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    return "dev"


def main() -> None:
    root = tk.Tk()
    root.title("L10 Manager")
    root.geometry("480x320")
    root.resizable(False, False)

    tk.Label(root, text="L10 Manager", font=("Segoe UI", 20, "bold")).pack(pady=(28, 4))
    tk.Label(root, text=meeting_name(), font=("Segoe UI", 12)).pack(pady=(0, 20))

    message = (
        "This is a placeholder.\n\n"
        "Soon this window will help you Prep, Run, and Review\n"
        "your Level 10 Meeting — Scorecard, Rocks, Issues,\n"
        "IDS, and Conclude — right from this folder."
    )
    tk.Label(root, text=message, font=("Segoe UI", 10), justify="center").pack(pady=10)

    tk.Label(root, text=f"version {version()}", font=("Segoe UI", 8), fg="gray").pack(side="bottom", pady=8)

    tk.Button(root, text="Close", width=12, command=root.destroy).pack(pady=10)

    root.mainloop()


if __name__ == "__main__":
    main()
