"""Reusable visual issue board - a Kanban-style view of Issues grouped by
board *column* (not raw status - multiple statuses can share a column, see
config.Column/Status). Cards are dragged between columns; dropping on a
column with more than one status prompts the user to pick which one.

Call build_issue_board() from any screen; pass a different `scope` to
reuse it for a narrower context later without touching this module.
"""

import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from tkinter import messagebox, ttk
from typing import Optional

import config as cfgmod
import issues as iss
from ui import canvas_shapes as shapes
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
TITLE_MAX_LINES = 2
AVATAR_SIZE = 24

# A colored left-edge-reading accent per column position - cycles through a
# small fixed palette by column order rather than a new persisted field, so
# each column reads as visually distinct at a glance (a real user's 82-issue
# "Open" column had every card looking identical). Not literal single-edge
# borders - RoundedCard only draws a uniform outline - so this colors the
# whole card border instead of adding a new widget just for one edge.
CARD_ACCENT_PALETTE = [theme.PRIMARY, theme.SUCCESS, theme.WARNING_ON_DARK, theme.DANGER, theme.MUTED]


def resolve_status_color(status, config: cfgmod.MeetingConfig) -> str:
    """A real user asked to be able to pick each status's own color rather
    than the board making it up - Status.color is None until someone
    customizes it in Settings > Board, and this is the one place that
    decides what to fall back to meanwhile, so cards, the status-mapping
    picker, and Settings' own color swatch all agree on the same color for
    a not-yet-customized status. Falls back to the existing column-order
    palette cycling for a column-having status (unchanged look for anyone
    who hasn't customized anything yet), or theme.MUTED for a hidden status
    with no column to cycle by."""
    if status.color:
        return status.color
    column = config.find_column(status.column_id) if status.column_id else None
    if column is not None:
        return CARD_ACCENT_PALETTE[column.order % len(CARD_ACCENT_PALETTE)]
    return theme.MUTED

# A separate small palette (deliberately distinct hues from CARD_ACCENT_PALETTE
# above, which already means "column/status") for per-person avatar circles -
# picked by a stable hash of the person's name so the same person always gets
# the same color across cards and app restarts (Python's built-in hash() is
# randomized per-process for strings, so it can't be used here).
_AVATAR_PALETTE = ["#6B4FBB", "#1D8A99", "#C2410C", "#B5179E", "#2563EB", "#059669"]


def _avatar_color(name: str) -> str:
    return _AVATAR_PALETTE[sum(ord(c) for c in name) % len(_AVATAR_PALETTE)]


def _fits_in_lines(text: str, font: tkfont.Font, wraplength: int, max_lines: int) -> bool:
    """Simulates the same greedy word-wrap a Label with this wraplength would
    do, without actually rendering anything, to check whether it needs more
    than max_lines. A single word wider than wraplength on its own also
    counts as "doesn't fit" (it would overflow/clip that line) rather than
    only checking width when concatenating onto a previous word."""
    words = text.split()
    if not words:
        return True
    lines = 1
    current = words[0]
    if font.measure(current) > wraplength:
        return False
    for word in words[1:]:
        candidate = f"{current} {word}"
        if font.measure(candidate) <= wraplength:
            current = candidate
        else:
            lines += 1
            if lines > max_lines:
                return False
            current = word
            if font.measure(current) > wraplength:
                return False
    return True


def _clamp_to_lines(text: str, font: tkfont.Font, wraplength: int, max_lines: int = TITLE_MAX_LINES) -> str:
    """Hard-truncates `text` (at the last whole word, appending "…") to the
    longest prefix that still word-wraps within max_lines at this font/
    wraplength - tied to the actual rendered width/font rather than a fixed
    character count, so it stays correct as columns resize or the font
    changes. Falls back to a mid-word cut only for a single word too long to
    fit any line at all."""
    if _fits_in_lines(text, font, wraplength, max_lines):
        return text
    words = text.split()
    lo, hi = 1, len(words)
    best = ""
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = " ".join(words[:mid]).rstrip() + "…"
        if _fits_in_lines(candidate, font, wraplength, max_lines):
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    if best:
        return best
    word = words[0] if words else text
    return word[: max(1, len(word) // 2)] + "…"


def _bind_tooltip(widget, ctx, text_provider) -> None:
    """Shows a small borderless Toplevel with whatever text_provider()
    currently returns while the pointer hovers `widget` - re-evaluated on
    every hover rather than bound to a fixed string, since e.g. the card
    title's truncation state itself changes as the column resizes."""
    state = {"win": None}

    def show(_event=None) -> None:
        text = text_provider()
        if not text or state["win"] is not None:
            return
        win = tk.Toplevel(ctx.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.geometry(f"+{widget.winfo_rootx()}+{widget.winfo_rooty() + widget.winfo_height() + 4}")
        tk.Label(
            win, text=text, background="#333333", foreground="white",
            font=("Segoe UI", 9), padx=8, pady=4, wraplength=260, justify="left",
        ).pack()
        state["win"] = win

    def hide(_event=None) -> None:
        win = state["win"]
        if win is not None:
            win.destroy()
            state["win"] = None

    widget.bind("<Enter>", show, add="+")
    widget.bind("<Leave>", hide, add="+")


def _make_avatar(parent, name: Optional[str]) -> tk.Canvas:
    """A small colored badge with initials for an assignee, or a plain
    outlined (unfilled) badge for Unassigned - always occupies the same
    slot so a card's header doesn't shift width depending on assignment.
    Drawn as a heavily-rounded rect (radius = half the size, i.e. as close
    to a circle as a rounded rect gets) via the same rounded_rect_points()
    polygon + smooth=True/splinesteps used everywhere else in this app,
    rather than canvas.create_oval() - a raw oval has no anti-aliasing
    control at all on a stdlib Tk canvas and looked visibly jagged/
    pixelated at this small size, a real user reported "not really a
    circle;" the polygon route at least gets the same splinesteps
    smoothing already relied on for every other shape in this app."""
    canvas = tk.Canvas(
        parent, width=AVATAR_SIZE, height=AVATAR_SIZE, background=theme.CARD_BG, highlightthickness=0,
    )
    points = shapes.rounded_rect_points(1, 1, AVATAR_SIZE - 1, AVATAR_SIZE - 1, AVATAR_SIZE / 2)
    if name:
        initials = "".join(part[0].upper() for part in name.split()[:2]) or "?"
        canvas.create_polygon(*points, smooth=True, splinesteps=shapes.SPLINESTEPS, fill=_avatar_color(name), outline="")
        canvas.create_text(AVATAR_SIZE / 2, AVATAR_SIZE / 2, text=initials, fill="white", font=("Segoe UI", 8, "bold"))
    else:
        canvas.create_polygon(*points, smooth=True, splinesteps=shapes.SPLINESTEPS, fill="", outline=theme.LINE, width=1)
    return canvas


def build_issue_board(
    parent, ctx, scope: str = iss.DEFAULT_SCOPE, title: str = "Issues", show_header: bool = True,
    on_focus_issue=None, focused_issue_id: Optional[str] = None,
) -> None:
    """Renders a full Kanban-style board into `parent` (an already-cleared
    frame). Reusable: a caller elsewhere just needs its own scope string.

    on_focus_issue (optional) - segment_types.py's IdsType embeds this same
    board on the Run Meeting screen and needs a way to spotlight one issue
    for the presentation window ("look at the board just like it displays
    in issues, but also the ability to select a particular item to focus
    on" - a real user asked for this directly). When provided, each card
    gets a Focus/Unfocus RoundedButton calling on_focus_issue(issue_id or
    None); focused_issue_id says which one (if any) is currently spotlit,
    for that card's own highlight. Neither param is used by the plain
    Issues nav screen. show_header=False skips the title/+New Issue row -
    the IDS embed already has the segment's own name shown above it via
    ui/run_meeting.py's header."""
    root_frame = ttk.Frame(parent)
    root_frame.pack(fill="both", expand=True)

    header_row = ttk.Frame(root_frame)
    header_row.pack(fill="x", padx=32, pady=(28, 12) if show_header else (0, 12))
    if show_header:
        ttk.Label(header_row, text=title, style="Heading.TLabel").pack(side="left")
    RoundedButton(
        header_row, text="+ New Issue", variant="filled",
        command=lambda: open_issue_dialog(ctx, scope, None, refresh),
    ).pack(side="right")

    # Columns with Column.hidden_by_default=True start collapsed out of the
    # board (see config.py's Column docstring) - a different concept from a
    # hidden Status (no column at all, never shown), this column still has
    # real cards, just one click away instead of always taking up space. A
    # real user wanted their "Solved" column out of the way day-to-day.
    # show_hidden_columns is ephemeral, per viewing session only (resets to
    # collapsed again next time this screen builds) - not a persisted
    # preference, since the STARTING state is what Column.hidden_by_default
    # already controls.
    board_state = {"show_hidden_columns": False}

    hidden_columns_button_holder = ttk.Frame(root_frame)
    hidden_columns_button_holder.pack(anchor="w", padx=32, pady=(0, 10))

    board_frame = ttk.Frame(root_frame)
    board_frame.pack(fill="both", expand=True, padx=32, pady=(0, 8))

    hidden_label = ttk.Label(root_frame, text="", style="Muted.TLabel")
    hidden_label.pack(anchor="w", padx=32, pady=(0, 20))

    # Shared across all cards' drag handlers for this board instance.
    drag_state = {"dragging": False, "issue": None, "ghost": None, "start_x": 0, "start_y": 0}
    column_frames = {}  # column_id -> the Frame widget, for hit-testing drops
    # Built once per board, not once per card (font.Font() creation and a
    # per-card RoundedCard were together the biggest chunk of a real, visible
    # slowdown loading 83 real issues - fonts are shared here, and the status
    # badge below was simplified from its own RoundedCard down to plain text).
    title_font = tkfont.Font(family="Segoe UI", size=10)

    def toggle_hidden_columns() -> None:
        board_state["show_hidden_columns"] = not board_state["show_hidden_columns"]
        refresh()

    def refresh() -> None:
        for child in board_frame.winfo_children():
            child.destroy()
        column_frames.clear()

        all_columns = ctx.config.sorted_columns()
        collapsed_columns = [c for c in all_columns if c.hidden_by_default]
        if board_state["show_hidden_columns"]:
            columns = all_columns
        else:
            columns = [c for c in all_columns if not c.hidden_by_default]

        for child in hidden_columns_button_holder.winfo_children():
            child.destroy()
        if collapsed_columns:
            label = (
                f"Hide {len(collapsed_columns)} column(s)" if board_state["show_hidden_columns"]
                else f"Show {len(collapsed_columns)} hidden column(s) ({', '.join(c.name for c in collapsed_columns)})"
            )
            RoundedButton(
                hidden_columns_button_holder, text=label, variant="tonal", command=toggle_hidden_columns,
            ).pack(anchor="w")

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

        # Reset every grid column slot up to the widest this board has ever
        # needed before reconfiguring the ones actually shown below -
        # destroying board_frame's children (above) doesn't also clear its
        # OWN grid column configuration, so toggling "Show hidden columns"
        # down to fewer columns than a previous render left stale
        # weight=1/uniform entries claiming equal-width space for indices no
        # widget occupies anymore, squeezing the real columns into less than
        # the full board width. len(all_columns), not len(columns), is the
        # right upper bound since that's the most columns this board could
        # ever show in one render.
        for reset_index in range(len(all_columns)):
            board_frame.grid_columnconfigure(reset_index, weight=0, uniform="")

        # Two passes: create every column's frame/header/ScrollableFrame
        # FIRST, then populate cards in a second pass below. A real user
        # watched a large board render as one tall unbroken list that only
        # snapped into columns once everything finished loading - populating
        # a column's cards in the SAME pass that creates it meant later
        # columns' existence (and grid's weight=1/uniform sizing, which only
        # settles once ALL sibling columns exist) wasn't in place yet, so the
        # board had no correct column layout to render into until the very
        # end. update_idletasks() after the first pass forces that layout to
        # settle before card population (the slower part) even begins.
        column_setup = []
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

            column_setup.append((cards_scroll.body, column_issues))

        board_frame.update_idletasks()

        for cards_frame, column_issues in column_setup:
            for issue in column_issues:
                # Per-STATUS now, not per-column - a column can hold several
                # statuses, and a real user asked to color-code by status,
                # not just by whichever column it happens to land in.
                issue_status = ctx.config.find_status(issue.status)
                accent_color = resolve_status_color(issue_status, ctx.config) if issue_status else theme.MUTED
                _build_card(
                    cards_frame, ctx, issue, scope, refresh, drag_state, column_frames, accent_color, title_font,
                    on_focus_issue=on_focus_issue, is_focused=(issue.id == focused_issue_id),
                )

        hidden_count = sum(len(issues_by_status.get(s.id, [])) for s in ctx.config.hidden_statuses())
        hidden_label.configure(text=f"{hidden_count} hidden issue(s) (status not shown on the board)" if hidden_count else "")

    refresh()


def _build_card(
    parent, ctx, issue: iss.Issue, scope: str, refresh_callback, drag_state, column_frames,
    accent_color: str, title_font: tkfont.Font, on_focus_issue=None, is_focused: bool = False,
) -> None:
    display = ctx.config.board_display
    card = RoundedCard(
        parent, border_color=theme.PRIMARY if is_focused else accent_color, border_width=3 if is_focused else 2,
    )
    card.configure(cursor="fleur")
    card.pack(fill="x", pady=4)

    inner = tk.Frame(card.body, background=theme.CARD_BG)
    inner.pack(fill="x", padx=10, pady=8)

    widgets_to_bind = [card.body, inner]

    # Header: an assignee avatar (or an empty outlined badge for Unassigned,
    # so the header never changes width/shifts the title based on
    # assignment) beside the title. Title is regular weight, not bold - bold
    # competed for space with long real titles and made the card read as
    # "everything is emphasized," i.e. nothing is. Regular weight plus the
    # 2-line clamp below (with a hover tooltip for the full text) reads
    # closer to how Jira/Linear pack a card header into little space.
    # grid (not pack) for this row specifically - pack's per-slave -anchor
    # only takes visible effect once the row's final height has settled
    # from ALL its children, and a real user compared a short one-line title
    # against a long two-line one side by side and saw the avatar sit at a
    # visibly different relative height between them. Both cells deliberately
    # have NO vertical sticky (not "n"/top) - Tk's default is to center a
    # widget in its cell, so whichever of avatar (fixed ~24px) or title
    # (1 or 2 lines) is taller in a given row dictates that row's height, and
    # the other one centers against it. Top-aligning ("n") was tried first and
    # looked right only for a 1-line title (where the taller avatar happens to
    # make top-align and center-align look almost the same) - for a 2-line
    # title, which is taller than the avatar, top-aligning left the avatar
    # sitting above the true vertical center of the whole two-line block,
    # visibly higher than a real user expected.
    header_row = tk.Frame(inner, background=theme.CARD_BG)
    header_row.pack(fill="x", anchor="w")
    header_row.grid_columnconfigure(1, weight=1)
    widgets_to_bind.append(header_row)

    assignee = ctx.config.find_person(issue.assignee_id) if display.show_assignee else None
    title_col = 0
    if display.show_assignee:
        avatar = _make_avatar(header_row, assignee.name if assignee else None)
        avatar.grid(row=0, column=0, padx=(0, 8))
        widgets_to_bind.append(avatar)
        _bind_tooltip(avatar, ctx, lambda: assignee.name if assignee else UNASSIGNED_SENTINEL)
        title_col = 1

    title_label = tk.Label(
        header_row, text=_clamp_to_lines(issue.title, title_font, 220), background=theme.CARD_BG,
        foreground=theme.INK, font=title_font, anchor="w", justify="left", wraplength=220,
    )
    title_label.grid(row=0, column=title_col, sticky="ew")
    widgets_to_bind.append(title_label)
    title_state = {"truncated": False}
    _bind_tooltip(title_label, ctx, lambda: issue.title if title_state["truncated"] else None)

    desc_label = None
    if display.show_description and issue.description:
        snippet = issue.description.strip().replace("\n", " ")
        if len(snippet) > DESCRIPTION_SNIPPET_LEN:
            snippet = snippet[:DESCRIPTION_SNIPPET_LEN].rstrip() + "…"
        desc_label = tk.Label(
            inner, text=snippet, background=theme.CARD_BG, foreground=theme.MUTED,
            font=("Segoe UI", 10), anchor="w", justify="left", wraplength=220,
        )
        desc_label.pack(fill="x", anchor="w", pady=(4, 0))
        widgets_to_bind.append(desc_label)

    # Footer: status on the left, Jira key as a real clickable link on the
    # right - a real user asked for these on one row instead of each
    # stacked on its own line, packing more into less vertical space. Status
    # is plain colored text, not its own little RoundedCard box - a second
    # real user round found that box added real per-card cost (its own
    # canvas, polygon draw, and Configure bindings) toward a genuinely slow
    # load with 80+ real issues, for a "badge" look that read as visual
    # clutter rather than useful signal once seen against real data.
    footer_row = tk.Frame(inner, background=theme.CARD_BG)
    if display.show_status:
        status = ctx.config.find_status(issue.status)
        status_label = tk.Label(
            footer_row, text=status.name if status else issue.status, background=theme.CARD_BG,
            foreground=accent_color, font=("Segoe UI", 8, "bold"),
        )
        status_label.pack(side="left")
        widgets_to_bind.append(status_label)
    if issue.external_ref:
        link = tk.Label(
            footer_row, text=f"{issue.external_ref.key} ↗", background=theme.CARD_BG,
            foreground=theme.PRIMARY, font=("Segoe UI", 8, "underline"), cursor="hand2",
        )
        link.pack(side="right")
        url = issue.external_ref.url
        if url:
            link.bind("<Button-1>", lambda _e: webbrowser.open(url))
    if footer_row.winfo_children():
        footer_row.pack(fill="x", anchor="w", pady=(10, 0))

    # A separate row (not packed into footer_row, which already has its own
    # fixed status/Jira-link layout) - only rendered when the caller passed
    # on_focus_issue (segment_types.py's IdsType embedding this board on the
    # Run Meeting screen). A real user asked for "the ability to select a
    # particular item to focus on," spotlit on the presentation window,
    # controlled from here - the presentation window itself has no button
    # of its own, it's read-only output (see ui/presentation.py).
    if on_focus_issue is not None:
        focus_row = tk.Frame(inner, background=theme.CARD_BG)
        focus_row.pack(fill="x", anchor="w", pady=(8, 0))
        RoundedButton(
            focus_row, text="Unfocus" if is_focused else "Focus", variant="tonal",
            command=lambda: on_focus_issue(None if is_focused else issue.id),
        ).pack(anchor="w")

    # Columns are user-configurable (any count/width), so a fixed wraplength
    # either clips long titles in narrow columns or under-wraps in wide ones -
    # re-measure against the card's actual rendered width instead.
    def _sync_wraplength(event) -> None:
        width = max(event.width - AVATAR_SIZE - 12, 60) if display.show_assignee else max(event.width - 4, 60)
        clamped = _clamp_to_lines(issue.title, title_font, width)
        title_state["truncated"] = clamped != issue.title
        title_label.configure(text=clamped, wraplength=width)
        if desc_label is not None:
            desc_label.configure(wraplength=max(event.width - 4, 60))
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


