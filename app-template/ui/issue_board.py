"""Reusable visual issue board - a Kanban-style view of Issues grouped by
status, with click-based status moves (not drag-and-drop, to keep this
simple and robust in Tkinter). Call build_issue_board() from any screen;
pass a different `scope` to reuse it for a narrower context later (e.g.
one meeting's issues) without touching this module at all.
"""

import tkinter as tk
from tkinter import messagebox, ttk

import config as cfgmod
import issues as iss
from ui import theme
from ui.dialogs import ask_text

BOARD_COLUMNS = [iss.STATUS_OPEN, iss.STATUS_IN_PROGRESS, iss.STATUS_SOLVED]

UNASSIGNED_SENTINEL = "Unassigned"
ADD_PERSON_SENTINEL = "+ Add New Person..."


def build_issue_board(parent, ctx, scope: str = iss.DEFAULT_SCOPE, title: str = "Issues") -> None:
    """Renders a full Kanban-style board into `parent` (an already-cleared
    frame). Reusable: a caller elsewhere just needs its own scope string."""
    root_frame = ttk.Frame(parent)
    root_frame.pack(fill="both", expand=True)

    header_row = ttk.Frame(root_frame)
    header_row.pack(fill="x", padx=32, pady=(28, 12))
    ttk.Label(header_row, text=title, style="Heading.TLabel").pack(side="left")
    ttk.Button(
        header_row, text="+ New Issue", style="Primary.TButton",
        command=lambda: _open_issue_dialog(ctx, scope, None, refresh),
    ).pack(side="right")

    board_frame = ttk.Frame(root_frame)
    board_frame.pack(fill="both", expand=True, padx=32, pady=(0, 8))

    dropped_label = ttk.Label(root_frame, text="", style="Muted.TLabel")
    dropped_label.pack(anchor="w", padx=32, pady=(0, 20))

    def refresh() -> None:
        for child in board_frame.winfo_children():
            child.destroy()

        all_issues = iss.list_issues(scope=scope)
        by_status = {status: [] for status in BOARD_COLUMNS}
        dropped_count = 0
        for issue in all_issues:
            if issue.status == iss.STATUS_DROPPED:
                dropped_count += 1
            elif issue.status in by_status:
                by_status[issue.status].append(issue)
            else:
                by_status[iss.STATUS_OPEN].append(issue)

        for col_index, status in enumerate(BOARD_COLUMNS):
            board_frame.grid_columnconfigure(col_index, weight=1, uniform="board_col")
            board_frame.grid_rowconfigure(0, weight=1)

            col = tk.Frame(board_frame, background=theme.SUBTLE_BG)
            col.grid(row=0, column=col_index, sticky="nsew", padx=6)

            tk.Label(
                col, text=f"{iss.STATUS_LABELS[status]} ({len(by_status[status])})",
                background=theme.SUBTLE_BG, foreground=theme.INK, font=("Segoe UI", 10, "bold"),
            ).pack(fill="x", padx=10, pady=(10, 6))

            cards_frame = tk.Frame(col, background=theme.SUBTLE_BG)
            cards_frame.pack(fill="both", expand=True, padx=8, pady=(0, 10))

            for issue in by_status[status]:
                _build_card(cards_frame, ctx, issue, status, scope, refresh)

        dropped_label.configure(text=f"{dropped_count} dropped issue(s) hidden" if dropped_count else "")

    refresh()


def _build_card(parent, ctx, issue: iss.Issue, status: str, scope: str, refresh_callback) -> None:
    card = tk.Frame(parent, background=theme.CARD_BG, highlightbackground=theme.LINE, highlightthickness=1, cursor="hand2")
    card.pack(fill="x", pady=4)

    inner = tk.Frame(card, background=theme.CARD_BG)
    inner.pack(fill="x", padx=10, pady=8)

    title_label = tk.Label(
        inner, text=issue.title, background=theme.CARD_BG, foreground=theme.INK,
        font=("Segoe UI", 10, "bold"), anchor="w", justify="left", wraplength=220,
    )
    title_label.pack(fill="x", anchor="w")

    assignee = ctx.config.find_person(issue.assignee_id)
    assignee_text = assignee.name if assignee else UNASSIGNED_SENTINEL
    if issue.external_ref:
        assignee_text += f"  •  {issue.external_ref.key}"
    tk.Label(
        inner, text=assignee_text, background=theme.CARD_BG,
        foreground=theme.PRIMARY if assignee else theme.MUTED, font=("Segoe UI", 8),
    ).pack(fill="x", anchor="w", pady=(2, 6))

    button_row = tk.Frame(inner, background=theme.CARD_BG)
    button_row.pack(fill="x")

    idx = BOARD_COLUMNS.index(status)
    if idx > 0:
        ttk.Button(
            button_row, text="←", style="Secondary.TButton", width=3,
            command=lambda: _move_status(issue, BOARD_COLUMNS[idx - 1], refresh_callback),
        ).pack(side="left")
    if idx < len(BOARD_COLUMNS) - 1:
        ttk.Button(
            button_row, text="→", style="Secondary.TButton", width=3,
            command=lambda: _move_status(issue, BOARD_COLUMNS[idx + 1], refresh_callback),
        ).pack(side="left", padx=(4, 0))
    ttk.Button(
        button_row, text="Edit", style="Secondary.TButton",
        command=lambda: _open_issue_dialog(ctx, scope, issue, refresh_callback),
    ).pack(side="right")

    def clicked(_event):
        _open_issue_dialog(ctx, scope, issue, refresh_callback)

    for widget in (card, inner, title_label):
        widget.bind("<Button-1>", clicked)


def _move_status(issue: iss.Issue, new_status: str, refresh_callback) -> None:
    issue.status = new_status
    iss.save_issue(issue)
    refresh_callback()


def _open_issue_dialog(ctx, scope: str, issue, refresh_callback) -> None:
    """Modal create/edit dialog. The assignee picker supports adding a new
    person inline via ui/dialogs.ask_text, rather than forcing a detour to
    a separate People screen."""
    is_new = issue is None
    win = tk.Toplevel(ctx.root)
    win.title("New Issue" if is_new else "Edit Issue")
    win.configure(bg=theme.BG)
    win.resizable(False, False)
    win.transient(ctx.root)

    body = ttk.Frame(win)
    body.pack(padx=20, pady=20)

    ttk.Label(body, text="Title", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    title_var = tk.StringVar(value=issue.title if issue else "")
    ttk.Entry(body, textvariable=title_var, width=44).pack(anchor="w", pady=(0, 12))

    ttk.Label(body, text="Description (optional)", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    description_text = tk.Text(body, width=46, height=4, font=("Segoe UI", 10), wrap="word")
    description_text.insert("1.0", issue.description if issue else "")
    description_text.pack(anchor="w", pady=(0, 12))

    ttk.Label(body, text="Status", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    status_var = tk.StringVar(value=iss.STATUS_LABELS.get(issue.status if issue else iss.STATUS_OPEN, "Open"))
    ttk.Combobox(
        body, textvariable=status_var, state="readonly", width=20,
        values=[iss.STATUS_LABELS[s] for s in iss.STATUS_ORDER],
    ).pack(anchor="w", pady=(0, 12))

    ttk.Label(body, text="Assignee", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))

    def person_names():
        return [UNASSIGNED_SENTINEL] + [p.name for p in ctx.config.people] + [ADD_PERSON_SENTINEL]

    current_person = ctx.config.find_person(issue.assignee_id) if issue else None
    assignee_var = tk.StringVar(value=current_person.name if current_person else UNASSIGNED_SENTINEL)
    assignee_combo = ttk.Combobox(body, textvariable=assignee_var, state="readonly", width=30, values=person_names())
    assignee_combo.pack(anchor="w", pady=(0, 16))

    def on_assignee_selected(_event=None) -> None:
        if assignee_var.get() != ADD_PERSON_SENTINEL:
            return
        new_name = ask_text(ctx.root, "Add Person", "Name:")
        if new_name:
            ctx.config.people.append(cfgmod.Person(name=new_name))
            ctx.save_config()
            assignee_combo.configure(values=person_names())
            assignee_var.set(new_name)
        else:
            assignee_var.set(UNASSIGNED_SENTINEL)

    assignee_combo.bind("<<ComboboxSelected>>", on_assignee_selected)

    if issue and issue.external_ref:
        ttk.Label(
            body, text=f"Linked to {issue.external_ref.connector.title()}: {issue.external_ref.key}",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 12))

    button_row = ttk.Frame(body)
    button_row.pack(fill="x", pady=(8, 0))

    def cancel() -> None:
        win.destroy()

    def delete() -> None:
        if issue and messagebox.askyesno("Delete issue", "Delete this issue? This can't be undone."):
            iss.delete_issue(issue.id)
            win.destroy()
            refresh_callback()

    def save() -> None:
        title = title_var.get().strip()
        if not title:
            messagebox.showerror("Title required", "Give this issue a title.")
            return
        status_key = next((k for k, v in iss.STATUS_LABELS.items() if v == status_var.get()), iss.STATUS_OPEN)

        assignee_name = assignee_var.get()
        assignee_id = None
        if assignee_name not in (UNASSIGNED_SENTINEL, ADD_PERSON_SENTINEL):
            match = next((p for p in ctx.config.people if p.name == assignee_name), None)
            assignee_id = match.id if match else None

        description = description_text.get("1.0", "end").strip()
        if issue:
            issue.title = title
            issue.description = description
            issue.status = status_key
            issue.assignee_id = assignee_id
            iss.save_issue(issue)
        else:
            iss.save_issue(iss.Issue(
                title=title, description=description, status=status_key,
                assignee_id=assignee_id, scope=scope,
            ))

        win.destroy()
        refresh_callback()

    if not is_new:
        ttk.Button(button_row, text="Delete", style="Secondary.TButton", command=delete).pack(side="left")
    ttk.Button(button_row, text="Cancel", style="Secondary.TButton", command=cancel).pack(side="right", padx=(6, 0))
    ttk.Button(button_row, text="Save", style="Primary.TButton", command=save).pack(side="right")

    win.update_idletasks()
    x = ctx.root.winfo_x() + (ctx.root.winfo_width() - win.winfo_width()) // 2
    y = ctx.root.winfo_y() + (ctx.root.winfo_height() - win.winfo_height()) // 2
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.grab_set()
