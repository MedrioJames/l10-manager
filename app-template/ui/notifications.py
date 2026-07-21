"""Transient toast/error-banner notifications - replaces messagebox popups
for anything that isn't a genuine decision the user needs to make. Use
show_toast() for confirmations ("Settings saved") and show_error_banner()
for things that actually went wrong (a failed sync) and deserve to stick
around until acknowledged rather than auto-vanish.

Both attach directly to ctx.root (not ctx.content), so they survive screen
navigation triggered by the same action and always overlay the full window.
"""

import tkinter as tk

from ui import theme

TOAST_DURATION_MS = 3200

_COLORS = {
    "info": (theme.PRIMARY, "white"),
    "success": (theme.SUCCESS, theme.ON_SUCCESS),
    "error": (theme.DANGER, "white"),
}


def show_toast(ctx, message: str, kind: str = "success") -> None:
    """A small, auto-dismissing message at the bottom of the window."""
    bg, fg = _COLORS.get(kind, _COLORS["info"])
    root = ctx.root

    toast = tk.Frame(root, background=bg)
    tk.Label(
        toast, text=message, background=bg, foreground=fg,
        font=("Segoe UI", 9), padx=16, pady=8,
    ).pack()
    toast.place(relx=0.5, rely=1.0, anchor="s", y=-16)
    toast.lift()

    def dismiss() -> None:
        if toast.winfo_exists():
            toast.destroy()

    root.after(TOAST_DURATION_MS, dismiss)


def show_error_banner(ctx, message: str) -> None:
    """A more prominent, manually-dismissible banner across the bottom of
    the window - for real failures that shouldn't just flash and vanish."""
    bg, fg = _COLORS["error"]
    root = ctx.root

    banner = tk.Frame(root, background=bg)
    row = tk.Frame(banner, background=bg)
    row.pack(fill="x", padx=16, pady=10)

    tk.Label(
        row, text=message, background=bg, foreground=fg,
        font=("Segoe UI", 9), wraplength=700, justify="left",
    ).pack(side="left", fill="x", expand=True)

    def dismiss() -> None:
        if banner.winfo_exists():
            banner.destroy()

    tk.Button(
        row, text="✕", command=dismiss, background=bg, foreground=fg,
        relief="flat", bd=0, font=("Segoe UI", 10, "bold"), cursor="hand2",
        activebackground=bg, activeforeground=fg, highlightthickness=0,
    ).pack(side="right")

    banner.place(relx=0.5, rely=1.0, anchor="s", y=-16, relwidth=0.92)
    banner.lift()
