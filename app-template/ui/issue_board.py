"""Reusable visual issue board - a Kanban-style view of Issues grouped by
board *column* (not raw status - multiple statuses can share a column, see
config.Column/Status). Cards are dragged between columns; dropping on a
column with more than one status prompts the user to pick which one.

Call build_issue_board() from any screen; pass a different `scope` to
reuse it for a narrower context later without touching this module.
"""

import tkinter as tk
from tkinter import messagebox, ttk

import config as cfgmod
import issues as iss
from ui import theme
from ui.dialogs import ask_text
from ui.notifications import show_error_banner
from ui.rounded_button import RoundedButton
from ui.rounded_card import RoundedCard
from ui.scrollable import ScrollableFrame

UNASSIGNED_SENTINEL = "Unassigned"
ADD_PERSON_SENTINEL = "+ Add New Person..."
DRAG_THRESHOLD_PX = 6
DESCRIPTION_SNIPPET_LEN = 90
TITLE_MAX_CHARS = 80

# A colored left-edge-reading accent per column position - cycles through a
# small fixed palette by column order rather than a new persisted field, so
# each column reads as visually distinct at a glance (a real user's 82-issue
# "Open" column had every card looking identical). Not literal single-edge
# borders - RoundedCard only draws a uniform outline - so this colors the
# whole card border instead of adding a new widget just for one edge.
CARD_ACCENT_PALETTE = [theme.PRIMARY, theme.SUCCESS, theme.WARNING_ON_DARK, theme.DANGER, theme.MUTED]


def _truncate_words(text: str, max_chars: int = TITLE_MAX_CHARS) -> str:
    """Hard-truncates at the last whole word before max_chars, rather than
    relying on a Label's wraplength to break cleanly - a long unbroken run of
    words can still force Tkinter to split a word mid-character once it no
    longer fits a single line."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars].rsplit(" ", 1)[0].rstrip()
    return (truncated or text[:max_chars]).rstrip() + "…"


def build_issue_board(parent, ctx, scope: str = iss.DEFAULT_SCOPE, title: str = "Issues") -> None:
    """Renders a full Kanban-style board into `parent` (an already-cleared
    frame). Reusable: a caller elsewhere just needs its own scope string."""
    root_frame = ttk.Frame(parent)
    root_frame.pack(fill="both", expand=True)

    header_row = ttk.Frame(root_frame)
    header_row.pack(fill="x", padx=32, pady=(28, 12))
    ttk.Label(header_row, text=title, style="Heading.TLabel").pack(side="left")
    RoundedButton(
        header_row, text="+ New Issue", variant="filled",
        command=lambda: open_issue_dialog(ctx, scope, None, refresh),
    ).pack(side="right")

    board_frame = ttk.Frame(root_frame)
    board_frame.pack(fill="both", expand=True, padx=32, pady=(0, 8))

    hidden_label = ttk.Label(root_frame, text="", style="Muted.TLabel")
    hidden_label.pack(anchor="w", padx=32, pady=(0, 20))

    # Shared across all cards' drag handlers for this board instance.
    drag_state = {"dragging": False, "issue": None, "ghost": None, "start_x": 0, "start_y": 0}
    column_frames = {}  # column_id -> the Frame widget, for hit-testing drops

    def refresh() -> None:
        for child in board_frame.winfo_children():
            child.destroy()
        column_frames.clear()

        columns = ctx.config.sorted_columns()
        try:
            all_issues = iss.list_issues(scope=scope)
        except cfgmod.DataLoadError:
            show_error_banner(
                ctx, "Data/issues.json couldn't be read - a backup may be available at issues.json.bak.",
            )
            all_issues = []
        issues_by_status = {}
        for issue in all_issues:
            issues_by_status.setdefault(issue.status, []).append(issue)

        for col_index, column in enumerate(columns):
            board_frame.grid_columnconfigure(col_index, weight=1, uniform="board_col")
            board_frame.grid_rowconfigure(0, weight=1)

            col = tk.Frame(board_frame, background=theme.SUBTLE_BG)
            col.grid(row=0, column=col_index, sticky="nsew", padx=6)
            column_frames[column.id] = col

            statuses_here = ctx.config.statuses_in_column(column.id)
            status_ids_here = {s.id for s in statuses_here}
            column_issues = [i for i in all_issues if i.status in status_ids_here]

            tk.Label(
                col, text=f"{column.name} ({len(column_issues)})",
                background=theme.SUBTLE_BG, foreground=theme.INK, font=("Segoe UI", 10, "bold"),
            ).pack(fill="x", padx=10, pady=(10, 6))

            cards_scroll = ScrollableFrame(col, background=theme.SUBTLE_BG)
            cards_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 10))
            cards_frame = cards_scroll.body

            accent_color = CARD_ACCENT_PALETTE[column.order % len(CARD_ACCENT_PALETTE)]
            for issue in column_issues:
                _build_card(cards_frame, ctx, issue, scope, refresh, drag_state, column_frames, accent_color)

        hidden_count = sum(len(issues_by_status.get(s.id, [])) for s in ctx.config.hidden_statuses())
        hidden_label.configure(text=f"{hidden_count} hidden issue(s) (status not shown on the board)" if hidden_count else "")

    refresh()


def _build_card(parent, ctx, issue: iss.Issue, scope: str, refresh_callback, drag_state, column_frames, accent_color: str) -> None:
    display = ctx.config.board_display
    card = RoundedCard(parent, border_color=accent_color, border_width=2)
    card.configure(cursor="fleur")
    card.pack(fill="x", pady=4)

    inner = tk.Frame(card.body, background=theme.CARD_BG)
    inner.pack(fill="x", padx=10, pady=8)

    title_label = tk.Label(
        inner, text=_truncate_words(issue.title), background=theme.CARD_BG, foreground=theme.INK,
        font=("Segoe UI", 10, "bold"), anchor="w", justify="left", wraplength=220,
    )
    title_label.pack(fill="x", anchor="w")

    widgets_to_bind = [card.body, inner, title_label]
    desc_label = None

    if display.show_status:
        status = ctx.config.find_status(issue.status)
        status_label = tk.Label(
            inner, text=status.name if status else issue.status, background=theme.CARD_BG,
            foreground=theme.PRIMARY, font=("Segoe UI", 9, "bold"),
        )
        status_label.pack(fill="x", anchor="w", pady=(2, 0))
        widgets_to_bind.append(status_label)

    if display.show_description and issue.description:
        snippet = issue.description.strip().replace("\n", " ")
        if len(snippet) > DESCRIPTION_SNIPPET_LEN:
            snippet = snippet[:DESCRIPTION_SNIPPET_LEN].rstrip() + "…"
        desc_label = tk.Label(
            inner, text=snippet, background=theme.CARD_BG, foreground=theme.INK,
            font=("Segoe UI", 10), anchor="w", justify="left", wraplength=220,
        )
        desc_label.pack(fill="x", anchor="w", pady=(2, 0))
        widgets_to_bind.append(desc_label)

    # Columns are user-configurable (any count/width), so a fixed wraplength
    # either clips long titles in narrow columns or under-wraps in wide ones -
    # re-measure against the card's actual rendered width instead.
    def _sync_wraplength(event) -> None:
        width = max(event.width - 4, 60)
        title_label.configure(wraplength=width)
        if desc_label is not None:
            desc_label.configure(wraplength=width)
        # RoundedCard sizes its canvas height from card.body's reqheight at
        # the moment card.body's own <Configure> fires - which happens when
        # the canvas first assigns body its width, BEFORE this handler (bound
        # to `inner`, a child of body) has corrected the wraplength. That
        # left the card's height locked in against the label's un-corrected
        # (often shorter) wrap, clipping whatever extra line(s) the real
        # column width forced - a real user saw long titles cut off mid-word
        # in a real, wide 83-issue column. Forcing body to re-measure and
        # re-fire its own <Configure> after the wraplength correction lets
        # RoundedCard's existing height-sync logic pick up the corrected,
        # now-final reqheight instead.
        inner.update_idletasks()
        card.body.event_generate("<Configure>")

    inner.bind("<Configure>", _sync_wraplength)

    if display.show_assignee:
        assignee = ctx.config.find_person(issue.assignee_id)
        assignee_label = tk.Label(
            inner, text=assignee.name if assignee else UNASSIGNED_SENTINEL, background=theme.CARD_BG,
            foreground=theme.PRIMARY if assignee else theme.MUTED, font=("Segoe UI", 9),
        )
        assignee_label.pack(fill="x", anchor="w", pady=(2, 0))
        widgets_to_bind.append(assignee_label)
        if issue.external_ref:
            # De-emphasized Meta-size text - the Jira key is secondary
            # metadata, not something that should compete with the assignee
            # name at the same size/weight (a real user flagged this).
            ref_label = tk.Label(
                inner, text=issue.external_ref.key, background=theme.CARD_BG,
                foreground=theme.MUTED, font=("Segoe UI", 8),
            )
            ref_label.pack(fill="x", anchor="w")
            widgets_to_bind.append(ref_label)
    elif issue.external_ref:
        ref_label = tk.Label(
            inner, text=issue.external_ref.key, background=theme.CARD_BG,
            foreground=theme.MUTED, font=("Segoe UI", 9),
        )
        ref_label.pack(fill="x", anchor="w", pady=(2, 0))
        widgets_to_bind.append(ref_label)

    def on_press(event) -> None:
        drag_state["dragging"] = False
        drag_state["issue"] = issue
        drag_state["start_x"] = event.x_root
        drag_state["start_y"] = event.y_root
        drag_state["origin_card"] = card

    def on_motion(event) -> None:
        if drag_state.get("issue") is not issue:
            return
        dx = abs(event.x_root - drag_state["start_x"])
        dy = abs(event.y_root - drag_state["start_y"])

        if not drag_state["dragging"]:
            if dx < DRAG_THRESHOLD_PX and dy < DRAG_THRESHOLD_PX:
                return
            drag_state["dragging"] = True
            ghost = tk.Toplevel(ctx.root)
            ghost.overrideredirect(True)
            ghost.attributes("-topmost", True)
            tk.Label(
                ghost, text=issue.title, background=theme.PRIMARY, foreground="white",
                font=("Segoe UI", 9, "bold"), padx=10, pady=6,
            ).pack()
            drag_state["ghost"] = ghost

        ghost = drag_state.get("ghost")
        if ghost is not None:
            ghost.geometry(f"+{event.x_root + 12}+{event.y_root + 12}")

    def on_release(event) -> None:
        if drag_state.get("issue") is not issue:
            return
        ghost = drag_state.get("ghost")
        if ghost is not None:
            ghost.destroy()
        was_dragging = drag_state["dragging"]
        drag_state["dragging"] = False
        drag_state["issue"] = None
        drag_state["ghost"] = None

        if not was_dragging:
            open_issue_dialog(ctx, scope, issue, refresh_callback)
            return

        target_column_id = _column_at_point(column_frames, event.x_root, event.y_root)
        if not target_column_id:
            return  # dropped outside any column - leave it where it was

        current_status = ctx.config.find_status(issue.status)
        if current_status and current_status.column_id == target_column_id:
            return  # dropped back on its own column - no-op

        statuses_here = ctx.config.statuses_in_column(target_column_id)
        if not statuses_here:
            return
        if len(statuses_here) == 1:
            _apply_status_change(issue, statuses_here[0].id, refresh_callback)
        else:
            _choose_status_dialog(ctx, issue, statuses_here, refresh_callback)

    for widget in widgets_to_bind:
        widget.bind("<ButtonPress-1>", on_press)
        widget.bind("<B1-Motion>", on_motion)
        widget.bind("<ButtonRelease-1>", on_release)


def _column_at_point(column_frames: dict, root_x: int, root_y: int):
    for column_id, frame in column_frames.items():
        if not frame.winfo_exists():
            continue
        left = frame.winfo_rootx()
        top = frame.winfo_rooty()
        right = left + frame.winfo_width()
        bottom = top + frame.winfo_height()
        if left <= root_x <= right and top <= root_y <= bottom:
            return column_id
    return None


def _apply_status_change(issue: iss.Issue, new_status_id: str, refresh_callback) -> None:
    issue.status = new_status_id
    iss.save_issue(issue)
    refresh_callback()


def set_issue_status(issue_id: str, new_status_id: str, refresh_callback) -> None:
    """Public wrapper around _apply_status_change() for callers that only
    have an issue id in hand, not the Issue object itself - e.g.
    segment_types.py's IDS segment quick-action buttons."""
    issue = iss.get_issue(issue_id)
    if issue is not None:
        _apply_status_change(issue, new_status_id, refresh_callback)


def _choose_status_dialog(ctx, issue: iss.Issue, statuses, refresh_callback) -> None:
    win = tk.Toplevel(ctx.root)
    win.title("Which status?")
    win.configure(bg=theme.BG)
    win.resizable(False, False)
    win.transient(ctx.root)

    ttk.Label(
        win, text="This column has more than one status - which did you mean?",
        style="Body.TLabel", wraplength=280,
    ).pack(padx=20, pady=(20, 12))

    for status in statuses:
        def pick(status_id=status.id) -> None:
            win.destroy()
            _apply_status_change(issue, status_id, refresh_callback)
        RoundedButton(win, text=status.name, variant="tonal", command=pick).pack(
            fill="x", padx=20, pady=4,
        )

    RoundedButton(win, text="Cancel", variant="tonal", command=win.destroy).pack(
        fill="x", padx=20, pady=(8, 20),
    )

    win.update_idletasks()
    x = ctx.root.winfo_x() + (ctx.root.winfo_width() - win.winfo_width()) // 2
    y = ctx.root.winfo_y() + (ctx.root.winfo_height() - win.winfo_height()) // 2
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.grab_set()


def open_issue_dialog(ctx, scope: str, issue, refresh_callback) -> None:
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
    body.pack(padx=theme.SPACE_XL, pady=theme.SPACE_XL)

    ttk.Label(
        body, text="New Issue" if is_new else "Edit Issue", style="Heading.TLabel",
    ).pack(anchor="w", pady=(0, theme.SPACE_LG))

    ttk.Label(body, text="Title", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, theme.SPACE_XS))
    title_var = tk.StringVar(value=issue.title if issue else "")
    ttk.Entry(body, textvariable=title_var, width=52).pack(anchor="w", pady=(0, theme.SPACE_LG))

    ttk.Label(body, text="Description (optional)", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, theme.SPACE_XS))
    description_text = tk.Text(body, width=54, height=4, font=("Segoe UI", 10), wrap="word")
    description_text.insert("1.0", issue.description if issue else "")
    description_text.pack(anchor="w", pady=(0, theme.SPACE_LG))

    ttk.Label(body, text="Status", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, theme.SPACE_XS))
    statuses = ctx.config.statuses
    status_names = [s.name for s in statuses]
    current_status = ctx.config.find_status(issue.status) if issue else ctx.config.find_status(iss.DEFAULT_STATUS_ID)
    status_var = tk.StringVar(value=current_status.name if current_status else (status_names[0] if status_names else ""))
    ttk.Combobox(body, textvariable=status_var, state="readonly", width=28, values=status_names).pack(anchor="w", pady=(0, theme.SPACE_LG))

    ttk.Label(body, text="Assignee", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, theme.SPACE_XS))

    def person_names():
        return [UNASSIGNED_SENTINEL] + [p.name for p in ctx.config.people] + [ADD_PERSON_SENTINEL]

    current_person = ctx.config.find_person(issue.assignee_id) if issue else None
    assignee_var = tk.StringVar(value=current_person.name if current_person else UNASSIGNED_SENTINEL)
    assignee_combo = ttk.Combobox(body, textvariable=assignee_var, state="readonly", width=34, values=person_names())
    assignee_combo.pack(anchor="w", pady=(0, theme.SPACE_LG))

    # Only actionable when this issue is itself linked to Jira - a purely
    # local issue's assignee never needs to sync anywhere.
    unmatched_warning_label = None
    if issue and issue.external_ref:
        unmatched_warning_label = ttk.Label(body, text="", style="Muted.TLabel", wraplength=380, justify="left")
        unmatched_warning_label.pack(anchor="w", pady=(0, theme.SPACE_SM))

    def _update_unmatched_warning() -> None:
        if unmatched_warning_label is None:
            return
        person = next((p for p in ctx.config.people if p.name == assignee_var.get()), None)
        if person is not None and not person.jira_account_id:
            unmatched_warning_label.configure(
                text="This person isn't linked to Jira - assigning them here won't sync back until they're linked.",
            )
        else:
            unmatched_warning_label.configure(text="")

    def on_assignee_selected(_event=None) -> None:
        if assignee_var.get() == ADD_PERSON_SENTINEL:
            new_name = ask_text(ctx.root, "Add Person", "Name:")
            if new_name:
                ctx.config.people.append(cfgmod.Person(name=new_name))
                ctx.save_config()
                assignee_combo.configure(values=person_names())
                assignee_var.set(new_name)
            else:
                assignee_var.set(UNASSIGNED_SENTINEL)
        _update_unmatched_warning()

    assignee_combo.bind("<<ComboboxSelected>>", on_assignee_selected)
    _update_unmatched_warning()

    if issue and issue.external_ref:
        ttk.Label(
            body, text=f"Linked to {issue.external_ref.connector.title()}: {issue.external_ref.key}",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, theme.SPACE_MD))

    button_row = ttk.Frame(body)
    button_row.pack(fill="x", pady=(theme.SPACE_SM, 0))

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
        status_match = next((s for s in statuses if s.name == status_var.get()), None)
        status_id = status_match.id if status_match else iss.DEFAULT_STATUS_ID

        assignee_name = assignee_var.get()
        assignee_id = None
        if assignee_name not in (UNASSIGNED_SENTINEL, ADD_PERSON_SENTINEL):
            match = next((p for p in ctx.config.people if p.name == assignee_name), None)
            assignee_id = match.id if match else None

        description = description_text.get("1.0", "end").strip()
        if issue:
            issue.title = title
            issue.description = description
            issue.status = status_id
            issue.assignee_id = assignee_id
            iss.save_issue(issue)
        else:
            iss.save_issue(iss.Issue(
                title=title, description=description, status=status_id,
                assignee_id=assignee_id, scope=scope,
            ))

        win.destroy()
        refresh_callback()

    if not is_new:
        RoundedButton(button_row, text="Delete", variant="tonal", command=delete).pack(side="left")
    RoundedButton(button_row, text="Cancel", variant="tonal", command=cancel).pack(side="right", padx=(6, 0))
    RoundedButton(button_row, text="Save", variant="filled", command=save).pack(side="right")

    win.update_idletasks()
    x = ctx.root.winfo_x() + (ctx.root.winfo_width() - win.winfo_width()) // 2
    y = ctx.root.winfo_y() + (ctx.root.winfo_height() - win.winfo_height()) // 2
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.grab_set()


def open_backlog_modal(ctx, scope: str = iss.DEFAULT_SCOPE) -> None:
    """Issues whose status is hidden from the board but still active (not
    is_closed) - see MeetingConfig.backlog_statuses(). Reachable from Prep
    so there's somewhere to browse "not on the board, not done" items
    without them just being a count in the board's footer label."""
    win = tk.Toplevel(ctx.root)
    win.title("Backlog")
    win.configure(bg=theme.BG)
    win.transient(ctx.root)
    win.geometry("420x520")

    header = ttk.Frame(win)
    header.pack(fill="x", padx=20, pady=(20, 8))
    ttk.Label(header, text="Backlog", style="Heading.TLabel").pack(anchor="w")
    ttk.Label(
        header, text="Issues not currently shown on the board, but not dropped/closed either.",
        style="Muted.TLabel", wraplength=380,
    ).pack(anchor="w", pady=(4, 0))

    scroll = ScrollableFrame(win)
    scroll.pack(fill="both", expand=True, padx=20)
    list_frame = ttk.Frame(scroll.body)
    list_frame.pack(fill="both", expand=True)

    def refresh() -> None:
        for child in list_frame.winfo_children():
            child.destroy()
        backlog_status_ids = {s.id for s in ctx.config.backlog_statuses()}
        try:
            backlog_issues = [i for i in iss.list_issues(scope=scope) if i.status in backlog_status_ids]
        except cfgmod.DataLoadError:
            show_error_banner(ctx, "Data/issues.json couldn't be read - a backup may be available at issues.json.bak.")
            backlog_issues = []

        if not backlog_issues:
            ttk.Label(list_frame, text="Nothing in the backlog.", style="Muted.TLabel").pack(anchor="w", pady=8)

        for issue in backlog_issues:
            card = RoundedCard(list_frame)
            card.pack(fill="x", pady=3)
            row = card.body
            info = tk.Frame(row, background=theme.CARD_BG)
            info.pack(side="left", fill="both", expand=True, padx=10, pady=8)
            tk.Label(info, text=issue.title, background=theme.CARD_BG, foreground=theme.INK,
                     font=("Segoe UI", 10, "bold")).pack(anchor="w")
            status = ctx.config.find_status(issue.status)
            tk.Label(info, text=status.name if status else issue.status, background=theme.CARD_BG,
                     foreground=theme.MUTED, font=("Segoe UI", 9)).pack(anchor="w")
            RoundedButton(
                row, text="Open", variant="tonal",
                command=lambda i=issue: open_issue_dialog(ctx, scope, i, refresh),
            ).pack(side="right", padx=8)

    refresh()

    RoundedButton(win, text="Close", variant="tonal", command=win.destroy).pack(pady=16)

    win.update_idletasks()
    x = ctx.root.winfo_x() + max((ctx.root.winfo_width() - win.winfo_width()) // 2, 0)
    y = ctx.root.winfo_y() + max((ctx.root.winfo_height() - win.winfo_height()) // 2, 0)
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.grab_set()
