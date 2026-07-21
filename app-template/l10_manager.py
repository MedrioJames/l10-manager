"""L10 Manager - entry point.

Real Prep/Run/Review tooling is real now; Scorecard and Rocks are hidden
placeholders for now (see ui/placeholders.py, unwired from NAV_ITEMS/the
registry - not deleted, just not reachable yet). What IS real: first-run
setup, repeating meetings with full recurrence rules, a global Segment
library + Schedules built from it, per-occurrence schedule customization, a
live Run Meeting timer + presentation window (with real To-Do/IDS/Conclude
segment behavior - see segment_types.py) + a Review screen, and a visual
Issues board with optional Jira sync.
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
from ui import dashboard, prep, review, run_meeting, schedule_builder, schedule_editor, settings, wizard
from ui import issues as issues_screen
from ui.rounded_button import RoundedButton


def relaunch() -> None:
    script = Path(__file__).resolve()
    subprocess.Popen([sys.executable, str(script)], cwd=str(script.parent))


def build_registry() -> dict:
    return {
        "dashboard": dashboard.build,
        "issues": issues_screen.build,
        "review": review.build,
        "schedule_builder": schedule_builder.build,
        "settings": settings.build,
        "wizard": wizard.build,
        "prep": prep.build,
        "schedule_editor": schedule_editor.build,
        "run_meeting": run_meeting.build,
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


def show_restart_dialog(root: tk.Tk, new_version: str) -> None:
    """Shown right after files are already updated on disk - a real choice
    (Restart Now / Restart Later), not a dead-end "OK" that restarts no
    matter what you click. Restart Later just closes the dialog: the update
    already happened on disk, so the current (old-code-in-memory) process
    keeps running harmlessly until the next natural launch."""
    win = tk.Toplevel(root)
    win.title("Updated")
    win.configure(bg=theme.BG)
    win.resizable(False, False)
    win.transient(root)

    tk.Label(
        win, text=f"Updated to v{new_version}.", bg=theme.BG, fg=theme.INK,
        font=("Segoe UI", 11, "bold"),
    ).pack(padx=24, pady=(20, 4))
    tk.Label(
        win, text="Restart now to use the new version, or keep working and restart later.",
        bg=theme.BG, fg=theme.MUTED, font=("Segoe UI", 9), wraplength=320, justify="left",
    ).pack(padx=24, pady=(0, 16))

    button_frame = tk.Frame(win, bg=theme.BG)
    button_frame.pack(pady=(0, 20))

    def restart_now() -> None:
        win.destroy()
        relaunch()
        root.destroy()

    RoundedButton(button_frame, text="Restart Now", variant="filled", command=restart_now).pack(side="left", padx=6)
    RoundedButton(button_frame, text="Restart Later", variant="tonal", command=win.destroy).pack(side="left", padx=6)

    win.update_idletasks()
    x = root.winfo_x() + (root.winfo_width() - win.winfo_width()) // 2
    y = root.winfo_y() + (root.winfo_height() - win.winfo_height()) // 2
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.grab_set()


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
        show_restart_dialog(root, new_version)

    def do_wait() -> None:
        win.destroy()

    def do_skip() -> None:
        updater.set_skipped_version(new_version)
        win.destroy()

    RoundedButton(button_frame, text="Update Now", variant="filled", command=do_update).pack(side="left", padx=6)
    RoundedButton(button_frame, text="Wait", variant="tonal", command=do_wait).pack(side="left", padx=6)
    RoundedButton(button_frame, text="Skip This Release", variant="tonal", command=do_skip).pack(side="left", padx=6)

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


def _load_config_or_recover(root: tk.Tk):
    """Loads Data/config.json, and if it's corrupted beyond the automatic
    .bak fallback (see config.py's DataLoadError), stops and asks the user
    what to do rather than silently proceeding with a blank config that
    would then get saved right back over whatever's actually on disk."""
    try:
        return cfgmod.load_config()
    except cfgmod.DataLoadError as exc:
        result = {"config": None}

        win = tk.Toplevel(root)
        win.title("Data file couldn't be read")
        win.configure(bg=theme.BG)
        win.resizable(False, False)
        win.transient(root)

        tk.Label(
            win, text="Your configuration file looks corrupted.", bg=theme.BG, fg=theme.INK,
            font=("Segoe UI", 11, "bold"),
        ).pack(padx=24, pady=(20, 4))
        tk.Label(
            win, text=f"{exc.path}\n(and its .bak backup) couldn't be read.",
            bg=theme.BG, fg=theme.MUTED, font=("Segoe UI", 9), justify="left",
        ).pack(padx=24, pady=(0, 4))
        tk.Label(
            win,
            text="Nothing has been changed on disk yet. You can quit now and try to\n"
                 "recover the file yourself, or start over with a blank configuration\n"
                 "(this will NOT touch the file until you save something).",
            bg=theme.BG, fg=theme.INK, font=("Segoe UI", 9), justify="left",
        ).pack(padx=24, pady=(0, 16))

        button_frame = tk.Frame(win, bg=theme.BG)
        button_frame.pack(pady=(0, 20))

        def start_blank() -> None:
            result["config"] = cfgmod.MeetingConfig()
            win.destroy()

        def quit_app() -> None:
            win.destroy()
            root.destroy()

        RoundedButton(button_frame, text="Start with a blank configuration", variant="tonal",
                   command=start_blank).pack(side="left", padx=6)
        RoundedButton(button_frame, text="Quit without changing anything", variant="filled",
                   command=quit_app).pack(side="left", padx=6)

        win.protocol("WM_DELETE_WINDOW", quit_app)
        win.update_idletasks()
        x = root.winfo_x() + max((root.winfo_width() - win.winfo_width()) // 2, 0)
        y = root.winfo_y() + max((root.winfo_height() - win.winfo_height()) // 2, 0)
        win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        win.grab_set()
        win.wait_window()

        return result["config"]


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

    config = _load_config_or_recover(root)
    if config is None:
        # User chose to quit rather than proceed with unreadable data.
        return
    start_screen = "dashboard" if config.onboarded else "wizard"
    AppShell(root, config, build_registry(), start_screen=start_screen)

    build_menu(root)

    root.after(1500, lambda: check_for_updates(root, manual=False))

    root.mainloop()


if __name__ == "__main__":
    main()
