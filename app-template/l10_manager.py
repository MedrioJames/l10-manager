"""L10 Manager - placeholder application.

This is a stand-in for the real app. It proves the install -> shortcut ->
launcher -> app chain works end to end. Real L10 features (Scorecard,
Rocks, Issues, IDS, Conclude) land in later phases.
"""

import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

import updater

# Same palette as templates/README.html, so the app and the per-install
# read-me feel like one product rather than two different eras of software.
PRIMARY = "#145A82"
PRIMARY_DARK = "#0F3C5F"
BG = "#F5F8FA"
INK = "#1C2733"
MUTED = "#5B6B7A"
LINE = "#DBE4EC"
SUBTLE_BG = "#EAF0F5"


def meeting_name() -> str:
    app_dir = Path(__file__).resolve().parent
    return app_dir.parent.name or "L10 Manager"


def version() -> str:
    return updater.local_version()


def icon_path() -> Path:
    return Path(__file__).resolve().parent / "icon" / "l10-manager-icon.ico"


def relaunch() -> None:
    script = Path(__file__).resolve()
    subprocess.Popen([sys.executable, str(script)], cwd=str(script.parent))


def apply_theme(root: tk.Tk) -> None:
    root.configure(bg=BG)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure("TFrame", background=BG)
    style.configure("Header.TFrame", background=PRIMARY)

    style.configure("TLabel", background=BG, foreground=INK, font=("Segoe UI", 10))
    style.configure("Title.TLabel", background=PRIMARY, foreground="white", font=("Segoe UI", 16, "bold"))
    style.configure("Subtitle.TLabel", background=PRIMARY, foreground="#D8E6EF", font=("Segoe UI", 10))
    style.configure("Body.TLabel", background=BG, foreground=INK, font=("Segoe UI", 10))
    style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 8))
    style.configure("Link.TLabel", background=BG, foreground=PRIMARY, font=("Segoe UI", 9, "underline"))

    style.configure("TButton", font=("Segoe UI", 9), padding=(14, 8), relief="flat", borderwidth=0, focuscolor=BG)
    style.configure("Primary.TButton", background=PRIMARY, foreground="white")
    style.map(
        "Primary.TButton",
        background=[("active", PRIMARY_DARK), ("pressed", PRIMARY_DARK)],
    )
    style.configure("Secondary.TButton", background=SUBTLE_BG, foreground=INK)
    style.map("Secondary.TButton", background=[("active", LINE)])


def build_header(root: tk.Tk) -> None:
    header = ttk.Frame(root, style="Header.TFrame")
    header.pack(fill="x")
    inner = ttk.Frame(header, style="Header.TFrame")
    inner.pack(fill="x", padx=24, pady=(18, 16))
    ttk.Label(inner, text="L10 Manager", style="Title.TLabel").pack(anchor="w")
    ttk.Label(inner, text=meeting_name(), style="Subtitle.TLabel").pack(anchor="w", pady=(2, 0))


def build_body(root: tk.Tk) -> None:
    body = ttk.Frame(root)
    body.pack(fill="both", expand=True, padx=24, pady=20)

    message = (
        "This is a placeholder.\n\n"
        "Soon this window will help you Prep, Run, and Review\n"
        "your Level 10 Meeting - Scorecard, Rocks, Issues,\n"
        "IDS, and Conclude - right from this folder."
    )
    ttk.Label(body, text=message, style="Body.TLabel", justify="center").pack(expand=True)

    ttk.Button(body, text="Close", style="Secondary.TButton", command=root.destroy).pack(pady=(0, 4))


def open_github() -> None:
    webbrowser.open(updater.GITHUB_URL)


def build_footer(root: tk.Tk) -> None:
    footer = ttk.Frame(root)
    footer.pack(fill="x", side="bottom")

    divider = tk.Frame(footer, background=LINE, height=1)
    divider.pack(fill="x", side="top")

    row = ttk.Frame(footer)
    row.pack(fill="x", padx=20, pady=10)

    ttk.Label(row, text=f"version {version()}", style="Muted.TLabel").pack(side="left")

    github_link = ttk.Label(row, text="GitHub", style="Link.TLabel", cursor="hand2")
    github_link.pack(side="right")
    github_link.bind("<Button-1>", lambda _event: open_github())


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
    help_menu.add_command(label="View on GitHub", command=open_github)
    menubar.add_cascade(label="Help", menu=help_menu)

    root.config(menu=menubar)


def show_update_dialog(root: tk.Tk, manifest: dict) -> None:
    new_version = str(manifest.get("version", "?"))

    win = tk.Toplevel(root)
    win.title("Update Available")
    win.configure(bg=BG)
    win.resizable(False, False)
    win.transient(root)

    ttk.Label(
        win, text=f"L10 Manager v{new_version} is available.", style="Body.TLabel",
        font=("Segoe UI", 11, "bold"),
    ).pack(padx=24, pady=(20, 4))
    ttk.Label(
        win, text=f"You're currently on v{version()}.", style="Muted.TLabel",
    ).pack(padx=24, pady=(0, 16))

    button_frame = ttk.Frame(win)
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
                    "Up to date", f"You're on the latest version (v{version()})."
                ),
            )

    threading.Thread(target=worker, daemon=True).start()


def main() -> None:
    root = tk.Tk()
    root.title("L10 Manager")
    root.geometry("520x400")
    root.resizable(False, False)

    icon = icon_path()
    if icon.exists():
        try:
            root.iconbitmap(default=str(icon))
        except tk.TclError:
            pass

    apply_theme(root)
    build_menu(root)
    build_header(root)
    build_body(root)
    build_footer(root)

    root.after(1500, lambda: check_for_updates(root, manual=False))

    root.mainloop()


if __name__ == "__main__":
    main()
