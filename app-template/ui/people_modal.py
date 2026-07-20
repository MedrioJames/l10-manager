"""People management modal - add/edit/delete all in one window instead of
the old scroll-down/click-Edit/scroll-back-up round trip through a Settings
tab. Editing a person swaps that row's labels for Entry widgets in place
(no nested popup); a small "Add Person" form is pinned at the bottom,
always visible. Modeled on ui/issue_board.py's _open_issue_dialog Toplevel
pattern (transient/grab_set/centered).
"""

import tkinter as tk
from tkinter import messagebox, ttk

import config as cfgmod
from ui import icon_button, theme
from ui.notifications import show_toast
from ui.scrollable import ScrollableFrame


def open_people_modal(ctx) -> None:
    win = tk.Toplevel(ctx.root)
    win.title("Manage People")
    win.configure(bg=theme.BG)
    win.transient(ctx.root)
    win.geometry("480x560")

    header = ttk.Frame(win)
    header.pack(fill="x", padx=20, pady=(20, 8))
    ttk.Label(header, text="People", style="Heading.TLabel").pack(anchor="w")

    scroll = ScrollableFrame(win)
    scroll.pack(fill="both", expand=True, padx=20)
    list_frame = ttk.Frame(scroll.body)
    list_frame.pack(fill="both", expand=True)

    state = {"editing_id": None}

    def refresh() -> None:
        for child in list_frame.winfo_children():
            child.destroy()

        if not ctx.config.people:
            ttk.Label(list_frame, text="No people added yet.", style="Muted.TLabel").pack(anchor="w", pady=8)

        for person in ctx.config.people:
            if state["editing_id"] == person.id:
                _render_edit_row(list_frame, person)
            else:
                _render_view_row(list_frame, person)

    def _render_view_row(parent, person) -> None:
        row = tk.Frame(parent, background=theme.CARD_BG, highlightbackground=theme.LINE, highlightthickness=1)
        row.pack(fill="x", pady=3)
        info = tk.Frame(row, background=theme.CARD_BG)
        info.pack(side="left", fill="both", expand=True, padx=12, pady=8)
        tk.Label(info, text=person.name, background=theme.CARD_BG, foreground=theme.INK,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        if person.email:
            tk.Label(info, text=person.email, background=theme.CARD_BG,
                     foreground=theme.MUTED, font=("Segoe UI", 8)).pack(anchor="w")

        btns = tk.Frame(row, background=theme.CARD_BG)
        btns.pack(side="right", padx=8)

        def start_edit() -> None:
            state["editing_id"] = person.id
            refresh()

        def delete() -> None:
            if not messagebox.askyesno(
                "Remove person", "Remove this person? Any issues assigned to them will show as unassigned.",
            ):
                return
            ctx.config.people = [p for p in ctx.config.people if p.id != person.id]
            ctx.save_config()
            refresh()

        icon_button.icon_button(btns, icon_button.GLYPH_EDIT, start_edit).pack(side="left", padx=2)
        icon_button.icon_button(btns, icon_button.GLYPH_DELETE, delete, danger=True).pack(side="left", padx=2)

    def _render_edit_row(parent, person) -> None:
        row = tk.Frame(parent, background=theme.CARD_BG, highlightbackground=theme.PRIMARY, highlightthickness=1)
        row.pack(fill="x", pady=3)
        fields = tk.Frame(row, background=theme.CARD_BG)
        fields.pack(side="left", fill="both", expand=True, padx=10, pady=8)

        name_var = tk.StringVar(value=person.name)
        email_var = tk.StringVar(value=person.email)
        ttk.Entry(fields, textvariable=name_var, width=22).pack(anchor="w", pady=(0, 4))
        ttk.Entry(fields, textvariable=email_var, width=22).pack(anchor="w")

        btns = tk.Frame(row, background=theme.CARD_BG)
        btns.pack(side="right", padx=8)

        def save_edit() -> None:
            name = name_var.get().strip()
            if not name:
                messagebox.showerror("Name required", "Give this person a name.")
                return
            person.name = name
            person.email = email_var.get().strip()
            ctx.save_config()
            state["editing_id"] = None
            show_toast(ctx, "Person saved.")
            refresh()

        def cancel_edit() -> None:
            state["editing_id"] = None
            refresh()

        icon_button.icon_button(btns, icon_button.GLYPH_SAVE, save_edit).pack(side="left", padx=2)
        icon_button.icon_button(btns, icon_button.GLYPH_CANCEL, cancel_edit).pack(side="left", padx=2)

    refresh()

    add_frame = ttk.Frame(win)
    add_frame.pack(fill="x", padx=20, pady=16)
    ttk.Separator(add_frame).pack(fill="x", pady=(0, 12))
    ttk.Label(add_frame, text="Add Person", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 6))

    add_row = ttk.Frame(add_frame)
    add_row.pack(fill="x")
    new_name_var = tk.StringVar()
    new_email_var = tk.StringVar()
    ttk.Entry(add_row, textvariable=new_name_var, width=16).pack(side="left", padx=(0, 6))
    ttk.Entry(add_row, textvariable=new_email_var, width=16).pack(side="left", padx=(0, 6))

    def add_person() -> None:
        name = new_name_var.get().strip()
        if not name:
            messagebox.showerror("Name required", "Give this person a name.")
            return
        ctx.config.people.append(cfgmod.Person(name=name, email=new_email_var.get().strip()))
        ctx.save_config()
        new_name_var.set("")
        new_email_var.set("")
        show_toast(ctx, "Person added.")
        refresh()

    ttk.Button(add_row, text="+ Add", style="Primary.TButton", command=add_person).pack(side="left")

    ttk.Button(win, text="Close", style="Secondary.TButton", command=win.destroy).pack(pady=(0, 16))

    win.update_idletasks()
    x = ctx.root.winfo_x() + max((ctx.root.winfo_width() - win.winfo_width()) // 2, 0)
    y = ctx.root.winfo_y() + max((ctx.root.winfo_height() - win.winfo_height()) // 2, 0)
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.grab_set()
    win.wait_window()
