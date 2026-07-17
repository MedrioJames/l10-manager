"""L10 Manager - placeholder application.

This is a stand-in for the real app. It proves the install -> shortcut ->
launcher -> app chain works end to end. Real L10 features (Scorecard,
Rocks, Issues, IDS, Conclude) land in later phases.
"""

import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import updater


def meeting_name() -> str:
    app_dir = Path(__file__).resolve().parent
    return app_dir.parent.name or "L10 Manager"


def version() -> str:
    return updater.local_version()


def relaunch() -> None:
    script = Path(__file__).resolve()
    subprocess.Popen([sys.executable, str(script)], cwd=str(script.parent))


def show_update_dialog(root: tk.Tk, manifest: dict) -> None:
    new_version = str(manifest.get("version", "?"))

    win = tk.Toplevel(root)
    win.title("Update Available")
    win.resizable(False, False)
    win.transient(root)

    tk.Label(
        win, text=f"L10 Manager v{new_version} is available.",
        font=("Segoe UI", 11, "bold"),
    ).pack(padx=24, pady=(20, 4))
    tk.Label(
        win, text=f"You're currently on v{version()}.",
        font=("Segoe UI", 9), fg="gray",
    ).pack(padx=24, pady=(0, 16))

    button_frame = tk.Frame(win)
    button_frame.pack(pady=(0, 20))

    def do_update() -> None:
        win.destroy()
        try:
            updater.apply_update(manifest)
        except Exception:
            messagebox.showerror(
                "Update failed",
                "Couldn't download the update. Please try again later.",
            )
            return
        messagebox.showinfo(
            "Updated",
            f"Updated to v{new_version}. L10 Manager will restart now.",
        )
        relaunch()
        root.destroy()

    def do_wait() -> None:
        win.destroy()

    def do_skip() -> None:
        updater.set_skipped_version(new_version)
        win.destroy()

    tk.Button(button_frame, text="Update Now", width=12, command=do_update).pack(side="left", padx=6)
    tk.Button(button_frame, text="Wait", width=12, command=do_wait).pack(side="left", padx=6)
    tk.Button(button_frame, text="Skip This Release", width=16, command=do_skip).pack(side="left", padx=6)

    win.update_idletasks()
    x = root.winfo_x() + (root.winfo_width() - win.winfo_width()) // 2
    y = root.winfo_y() + (root.winfo_height() - win.winfo_height()) // 2
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.grab_set()


def check_for_updates(root: tk.Tk, manual: bool) -> None:
    def worker() -> None:
        manifest = updater.check_for_update(ignore_skip=manual)
        if manifest:
            root.after(0, lambda: show_update_dialog(root, manifest))
        elif manual:
            root.after(
                0,
                lambda: messagebox.showinfo(
                    "Up to date", f"You're on the latest version (v{version()})."
                ),
            )

    threading.Thread(target=worker, daemon=True).start()


def main() -> None:
    root = tk.Tk()
    root.title("L10 Manager")
    root.geometry("480x320")
    root.resizable(False, False)

    menubar = tk.Menu(root)
    help_menu = tk.Menu(menubar, tearoff=0)
    help_menu.add_command(
        label="Check for Updates...",
        command=lambda: check_for_updates(root, manual=True),
    )
    menubar.add_cascade(label="Help", menu=help_menu)
    root.config(menu=menubar)

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

    root.after(1500, lambda: check_for_updates(root, manual=False))

    root.mainloop()


if __name__ == "__main__":
    main()
