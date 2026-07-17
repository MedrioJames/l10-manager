"""L10 Manager - entry point.

Real Prep/Run/Review tooling is still arriving in phases; Scorecard, Rocks,
Issues, and Conclude are placeholders for now (see ui/placeholders.py). What
IS real: first-run setup, repeating meetings with full recurrence rules,
schedule templates, and per-occurrence schedule customization.
"""

import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

import config as cfgmod
import updater
from ui import theme
from ui.shell import AppShell
from ui import dashboard, placeholders, prep, schedule_editor, schedule_templates, settings, wizard


def relaunch() -> None:
    script = Path(__file__).resolve()
    subprocess.Popen([sys.executable, str(script)], cwd=str(script.parent))


def build_registry() -> dict:
    return {
        "dashboard": dashboard.build,
        "scorecard": placeholders.build_scorecard,
        "rocks": placeholders.build_rocks,
        "issues": placeholders.build_issues,
        "conclude": placeholders.build_conclude,
        "schedule_templates": schedule_templates.build,
        "settings": settings.build,
        "wizard": wizard.build,
        "prep": prep.build,
        "schedule_editor": schedule_editor.build,
    }


def setup_another_meeting(root: tk.Tk) -> None:
    def worker() -> None:
        try:
            updater.launch_new_install()
        except Exception:
            root.after(
                0,
                lambda: messagebox.showerror(
                    "Couldn't start setup",
                    "Couldn't download the setup script. Check your internet connection and try again.",
                ),
            )

    threading.Thread(target=worker, daemon=True).start()


def show_update_dialog(root: tk.Tk, manifest: dict) -> None:
    new_version = str(manifest.get("version", "?"))

    win = tk.Toplevel(root)
    win.title("Update Available")
    win.configure(bg=theme.BG)
    win.resizable(False, False)
    win.transient(root)

    tk.Label(
        win, text=f"L10 Manager v{new_version} is available.", bg=theme.BG, fg=theme.INK,
        font=("Segoe UI", 11, "bold"),
    ).pack(padx=24, pady=(20, 4))
    tk.Label(
        win, text=f"You're currently on v{updater.local_version()}.", bg=theme.BG, fg=theme.MUTED,
        font=("Segoe UI", 9),
    ).pack(padx=24, pady=(0, 16))

    button_frame = tk.Frame(win, bg=theme.BG)
    button_frame.pack(pady=(0, 20))

    def do_update() -> None:
        win.destroy()
        try:
            updater.apply_update(manifest)
        except Exception:
            messagebox.showerror("Update failed", "Couldn't download the update. Please try again later.")
            return
        messagebox.showinfo("Updated", f"Updated to v{new_version}. L10 Manager will restart now.")
        relaunch()
        root.destroy()

    def do_wait() -> None:
        win.destroy()

    def do_skip() -> None:
        updater.set_skipped_version(new_version)
        win.destroy()

    ttk.Button(button_frame, text="Update Now", style="Primary.TButton", command=do_update).pack(side="left", padx=6)
    ttk.Button(button_frame, text="Wait", style="Secondary.TButton", command=do_wait).pack(side="left", padx=6)
    ttk.Button(button_frame, text="Skip This Release", style="Secondary.TButton", command=do_skip).pack(side="left", padx=6)

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
                    "Up to date", f"You're on the latest version (v{updater.local_version()})."
                ),
            )

    threading.Thread(target=worker, daemon=True).start()


def build_menu(root: tk.Tk) -> None:
    menubar = tk.Menu(root)

    file_menu = tk.Menu(menubar, tearoff=0)
    file_menu.add_command(label="Set Up Another Meeting...", command=lambda: setup_another_meeting(root))
    file_menu.add_separator()
    file_menu.add_command(label="Exit", command=root.destroy)
    menubar.add_cascade(label="File", menu=file_menu)

    help_menu = tk.Menu(menubar, tearoff=0)
    help_menu.add_command(label="Check for Updates...", command=lambda: check_for_updates(root, manual=True))
    help_menu.add_separator()
    help_menu.add_command(label="View on GitHub", command=lambda: webbrowser.open(updater.GITHUB_URL))
    menubar.add_cascade(label="Help", menu=help_menu)

    root.config(menu=menubar)


def icon_path() -> Path:
    return Path(__file__).resolve().parent / "icon" / "l10-manager-icon.ico"


def main() -> None:
    root = tk.Tk()
    root.title("L10 Manager")
    root.geometry("1000x700")
    root.minsize(760, 520)

    icon = icon_path()
    if icon.exists():
        try:
            root.iconbitmap(default=str(icon))
        except tk.TclError:
            pass

    theme.apply_theme(root)

    config = cfgmod.load_config()
    start_screen = "dashboard" if config.onboarded else "wizard"
    AppShell(root, config, build_registry(), start_screen=start_screen)

    build_menu(root)

    root.after(1500, lambda: check_for_updates(root, manual=False))

    root.mainloop()


if __name__ == "__main__":
    main()
