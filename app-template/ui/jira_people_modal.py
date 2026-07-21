"""Jira people-matching review modal - reached from a "Review Jira People
Matches" button in Settings > Jira (see ui/settings.py). This is the
deliberate, reviewed counterpart to jira_sync.py's routine automatic sync:
it calls the heavier IssueConnector.list_project_members() to see everyone
Jira considers assignable on the project, then lets the user reconcile that
against the team's local People list - confirm/reject name-only matches,
link or add unmatched Jira members, and mark local people who just aren't
on Jira so they stop reappearing in review after review.

Same Toplevel/ScrollableFrame/refresh-in-place idiom as ui/people_modal.py.
Every mutating action mutates ctx.config in memory and calls refresh() so
the report (from jira_people_sync.build_match_report()) is always
recomputed fresh rather than patched incrementally - but does NOT call
ctx.save_config() per click. Data/ can live on a Google Drive/OneDrive/
Dropbox sync mount (see config.py's atomic_write_json retry-with-backoff
comment for the WinError 5 history), so a real project's worth of clicks
here each triggering their own full atomic write made this modal feel
laggy on every action, including Close. A single `dirty` flag tracks
whether anything changed; the actual save happens once, on close.
"""

import tkinter as tk
from tkinter import messagebox, ttk

import jira_people_sync as jps
from ui import icon_button, theme
from ui.notifications import show_toast
from ui.rounded_button import RoundedButton
from ui.rounded_card import RoundedCard
from ui.scrollable import ScrollableFrame

UNLINKED_SENTINEL = "(choose a person)"
UNMATCHED_REMOTE_SENTINEL = "(choose a Jira member)"


def open_jira_people_matches_modal(ctx, remote_members) -> None:
    win = tk.Toplevel(ctx.root)
    win.title("Review Jira People Matches")
    win.configure(bg=theme.BG)
    win.transient(ctx.root)
    win.geometry("560x640")

    header = ttk.Frame(win)
    header.pack(fill="x", padx=20, pady=(20, 8))
    ttk.Label(header, text="Jira People Matches", style="Heading.TLabel").pack(anchor="w")

    scroll = ScrollableFrame(win)
    scroll.pack(fill="both", expand=True, padx=20)
    body = ttk.Frame(scroll.body)
    body.pack(fill="both", expand=True)

    show_ignored_remote = {"value": False}
    show_ignored_local = {"value": False}
    dirty = {"value": False}

    def mark_dirty() -> None:
        dirty["value"] = True

    def refresh() -> None:
        report = jps.build_match_report(remote_members, ctx.config)
        if report.auto_matched:
            mark_dirty()

        for child in body.winfo_children():
            child.destroy()

        summary = f"{len(report.linked)} linked"
        if report.auto_matched:
            summary += f", {len(report.auto_matched)} just auto-linked by matching email"
        ttk.Label(body, text=summary + ".", style="Body.TLabel").pack(anchor="w", pady=(0, 16))

        _render_potential_section(body, ctx, report, refresh, mark_dirty)
        _render_unmatched_remote_section(body, ctx, report, refresh, show_ignored_remote, mark_dirty)
        _render_unmatched_local_section(body, ctx, report, refresh, show_ignored_local, mark_dirty)

    refresh()

    def close() -> None:
        if dirty["value"]:
            ctx.save_config()
        win.destroy()

    RoundedButton(win, text="Close", variant="tonal", command=close).pack(pady=(0, 16))
    win.protocol("WM_DELETE_WINDOW", close)

    win.update_idletasks()
    x = ctx.root.winfo_x() + max((ctx.root.winfo_width() - win.winfo_width()) // 2, 0)
    y = ctx.root.winfo_y() + max((ctx.root.winfo_height() - win.winfo_height()) // 2, 0)
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.grab_set()


def _render_potential_section(parent, ctx, report, refresh, mark_dirty) -> None:
    ttk.Label(parent, text="Needs Your Review", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    if not report.potential:
        ttk.Label(parent, text="Nothing to review right now.", style="Muted.TLabel").pack(anchor="w", pady=(0, 16))
        return

    for match in report.potential:
        person, remote = match.person, match.remote
        card = RoundedCard(parent)
        card.pack(fill="x", pady=3)
        row = card.body
        info = tk.Frame(row, background=theme.CARD_BG)
        info.pack(side="left", fill="both", expand=True, padx=12, pady=8)
        tk.Label(info, text=f"{person.name}  ↔  {remote.display_name}", background=theme.CARD_BG,
                 foreground=theme.INK, font=("Segoe UI", 10, "bold")).pack(anchor="w")

        # Shown whenever Jira has an email we don't already have recorded
        # for this person - including when the local record has no email
        # at all yet. Previously this only fired when BOTH sides already
        # had an email that happened to differ, so a person entered
        # without one had no way to pick up their email from this confirm
        # action at all (a real user reported the email "didn't sync").
        remote_email = remote.email
        person_email = person.email
        show_email_checkbox = bool(remote_email) and (
            not person_email or person_email.lower() != remote_email.lower()
        )
        sync_email_var = tk.BooleanVar(value=not person_email)
        if show_email_checkbox:
            label = f"Also update email to {remote_email}" if person_email else f"Add email: {remote_email}"
            ttk.Checkbutton(info, text=label, variable=sync_email_var).pack(anchor="w")

        btns = tk.Frame(row, background=theme.CARD_BG)
        btns.pack(side="right", padx=8)

        def confirm(p=person, r=remote, var=sync_email_var) -> None:
            jps.confirm_potential_match(p, r, sync_email=var.get())
            mark_dirty()
            refresh()

        def reject(p=person, r=remote) -> None:
            jps.reject_potential_match(ctx.config, p, r)
            mark_dirty()
            refresh()

        icon_button.icon_button(btns, icon_button.GLYPH_SAVE, confirm).pack(side="left", padx=2)
        icon_button.icon_button(btns, icon_button.GLYPH_CANCEL, reject, danger=True).pack(side="left", padx=2)

    ttk.Frame(parent).pack(pady=(0, 12))


def _render_unmatched_remote_section(parent, ctx, report, refresh, show_ignored, mark_dirty) -> None:
    ttk.Label(parent, text="Unmatched Jira Project Members", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    unlinked_people = [p for p in ctx.config.people if not p.jira_account_id]

    if not report.unmatched_remote:
        ttk.Label(parent, text="Every active Jira member is matched.", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
    for remote in report.unmatched_remote:
        card = RoundedCard(parent)
        card.pack(fill="x", pady=3)
        row = card.body
        info = tk.Frame(row, background=theme.CARD_BG)
        info.pack(side="left", fill="both", expand=True, padx=12, pady=8)
        tk.Label(info, text=remote.display_name, background=theme.CARD_BG, foreground=theme.INK,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        if remote.email:
            tk.Label(info, text=remote.email, background=theme.CARD_BG, foreground=theme.MUTED,
                     font=("Segoe UI", 9)).pack(anchor="w")

        actions = tk.Frame(row, background=theme.CARD_BG)
        actions.pack(side="right", padx=8, pady=4)

        link_var = tk.StringVar(value=UNLINKED_SENTINEL)
        link_combo = ttk.Combobox(
            actions, textvariable=link_var, state="readonly", width=18,
            values=[UNLINKED_SENTINEL] + [p.name for p in unlinked_people],
        )
        link_combo.pack(side="top", pady=(0, 4))

        def do_link(_event=None, r=remote, var=link_var) -> None:
            if var.get() == UNLINKED_SENTINEL:
                return
            match = next((p for p in unlinked_people if p.name == var.get()), None)
            if match:
                jps.link_existing_person(match, r)
                mark_dirty()
                refresh()

        link_combo.bind("<<ComboboxSelected>>", do_link)

        button_row = tk.Frame(actions, background=theme.CARD_BG)
        button_row.pack(side="top")

        def add_new(r=remote) -> None:
            jps.create_person_from_remote(ctx.config, r)
            mark_dirty()
            show_toast(ctx, f"Added {r.display_name} to People.")
            refresh()

        def ignore(r=remote) -> None:
            jps.set_remote_ignored(ctx.config, r, True)
            mark_dirty()
            refresh()

        RoundedButton(button_row, text="+ Add", variant="tonal", command=add_new).pack(side="left", padx=(0, 4))
        icon_button.icon_button(button_row, icon_button.GLYPH_SKIP, ignore).pack(side="left")

    if report.unmatched_remote_ignored:
        def toggle() -> None:
            show_ignored["value"] = not show_ignored["value"]
            refresh()

        RoundedButton(
            parent, text=f"{'Hide' if show_ignored['value'] else 'Show'} ignored ({len(report.unmatched_remote_ignored)})",
            variant="tonal", command=toggle,
        ).pack(anchor="w", pady=(4, 8))

        if show_ignored["value"]:
            for remote in report.unmatched_remote_ignored:
                row = ttk.Frame(parent)
                row.pack(fill="x", pady=2)
                ttk.Label(row, text=remote.display_name, style="Muted.TLabel").pack(side="left")

                def unignore(r=remote) -> None:
                    jps.set_remote_ignored(ctx.config, r, False)
                    mark_dirty()
                    refresh()

                icon_button.icon_button(row, icon_button.GLYPH_RESTORE, unignore).pack(side="right")

    ttk.Frame(parent).pack(pady=(0, 12))


def _render_unmatched_local_section(parent, ctx, report, refresh, show_ignored, mark_dirty) -> None:
    ttk.Label(parent, text="Local People Without a Jira Link", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))

    if not report.unmatched_local:
        ttk.Label(parent, text="Every active local person is linked or marked unmatched.", style="Muted.TLabel").pack(
            anchor="w", pady=(0, 8),
        )
    for person in report.unmatched_local:
        card = RoundedCard(parent)
        card.pack(fill="x", pady=3)
        row = card.body
        info = tk.Frame(row, background=theme.CARD_BG)
        info.pack(side="left", fill="both", expand=True, padx=12, pady=8)
        tk.Label(info, text=person.name, background=theme.CARD_BG, foreground=theme.INK,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")

        actions = tk.Frame(row, background=theme.CARD_BG)
        actions.pack(side="right", padx=8, pady=4)

        find_var = tk.StringVar(value=UNMATCHED_REMOTE_SENTINEL)
        find_combo = ttk.Combobox(
            actions, textvariable=find_var, state="readonly", width=18,
            values=[UNMATCHED_REMOTE_SENTINEL] + [r.display_name for r in report.unmatched_remote],
        )
        find_combo.pack(side="top", pady=(0, 4))

        def do_find(_event=None, p=person, var=find_var) -> None:
            if var.get() == UNMATCHED_REMOTE_SENTINEL:
                return
            match = next((r for r in report.unmatched_remote if r.display_name == var.get()), None)
            if match:
                jps.link_existing_person(p, match)
                mark_dirty()
                refresh()

        find_combo.bind("<<ComboboxSelected>>", do_find)

        def leave_unmatched(p=person) -> None:
            jps.set_person_unmatched(p, True)
            mark_dirty()
            refresh()

        RoundedButton(actions, text="Leave unmatched", variant="tonal", command=leave_unmatched).pack(side="top")

    if report.unmatched_local_ignored:
        def toggle() -> None:
            show_ignored["value"] = not show_ignored["value"]
            refresh()

        RoundedButton(
            parent, text=f"{'Hide' if show_ignored['value'] else 'Show'} marked unmatched ({len(report.unmatched_local_ignored)})",
            variant="tonal", command=toggle,
        ).pack(anchor="w", pady=(4, 8))

        if show_ignored["value"]:
            for person in report.unmatched_local_ignored:
                row = ttk.Frame(parent)
                row.pack(fill="x", pady=2)
                ttk.Label(row, text=person.name, style="Muted.TLabel").pack(side="left")

                def undo(p=person) -> None:
                    jps.set_person_unmatched(p, False)
                    mark_dirty()
                    refresh()

                icon_button.icon_button(row, icon_button.GLYPH_RESTORE, undo).pack(side="right")
