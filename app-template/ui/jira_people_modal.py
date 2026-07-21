"""Jira people-matching review modal - reached from a "Review Jira People
Matches" button in Settings > Jira (see ui/settings.py). This is the
deliberate, reviewed counterpart to jira_sync.py's routine automatic sync:
it calls the heavier IssueConnector.list_project_members() to see everyone
Jira considers assignable on the project, then lets the user reconcile that
against the team's local People list - confirm/reject name-only matches,
link or add unmatched Jira members, and mark local people who just aren't
on Jira so they stop reappearing in review after review.

Three tabs (see ui/tabs.py's TabBar) rather than one long scrolling page -
"Needs Review" / "Local People" / "Jira Members", Local People before Jira
Members since that's the list a user checks first (a real user asked for
this ordering). Splitting into tabs also lets refresh() rebuild only the
ACTIVE tab's widgets after a mutation instead of all three sections every
single click - a real perf win when a project has a long unmatched-member
list, on top of the batched-save fix below.

Every mutating action mutates ctx.config in memory; ctx.save_config() is
called at most once, when the modal closes, not per click (Data/ can live
on a Google Drive/OneDrive/Dropbox sync mount - see config.py's
atomic_write_json retry-with-backoff comment for the WinError 5 history,
so a real project's worth of clicks each triggering their own full atomic
write made every action feel laggy). That save now also runs on a
background thread so closing the window is never blocked on a slow/
Google-Drive-locked write either - a real user reported Close itself still
felt slow even after the per-click saves were removed.
"""

import threading
import tkinter as tk
from tkinter import ttk

import jira_people_sync as jps
from ui import icon_button, theme
from ui.notifications import show_error_banner, show_toast
from ui.rounded_button import RoundedButton
from ui.rounded_card import RoundedCard
from ui.scrollable import ScrollableFrame
from ui.tabs import TabBar

UNLINKED_SENTINEL = "(choose a person)"
UNMATCHED_REMOTE_SENTINEL = "(choose a Jira member)"

TAB_NEEDS_REVIEW = 0
TAB_LOCAL_PEOPLE = 1
TAB_JIRA_MEMBERS = 2


def open_jira_people_matches_modal(ctx, remote_members) -> None:
    win = tk.Toplevel(ctx.root)
    win.title("Review Jira People Matches")
    win.configure(bg=theme.BG)
    win.transient(ctx.root)
    win.geometry("560x640")

    header = ttk.Frame(win)
    header.pack(fill="x", padx=20, pady=(20, 8))
    ttk.Label(header, text="Jira People Matches", style="Heading.TLabel").pack(anchor="w")
    summary_label = ttk.Label(header, text="", style="Body.TLabel")
    summary_label.pack(anchor="w", pady=(4, 0))

    tabs_container = ttk.Frame(win)
    tabs_container.pack(fill="both", expand=True, padx=20)

    def on_tab_change(index: int) -> None:
        state["active_tab"] = index
        render_active_tab()

    tabs = TabBar(tabs_container, ["Needs Review", "Local People", "Jira Members"], on_change=on_tab_change)
    tabs.pack(fill="both", expand=True)

    scrolls = [ScrollableFrame(tabs.page(i)) for i in range(3)]
    for scroll in scrolls:
        scroll.pack(fill="both", expand=True)
    pages = [ttk.Frame(scroll.body) for scroll in scrolls]
    for page in pages:
        page.pack(fill="both", expand=True)

    show_ignored_remote = {"value": False}
    show_ignored_local = {"value": False}
    dirty = {"value": False}
    state = {"active_tab": TAB_NEEDS_REVIEW}

    def mark_dirty() -> None:
        dirty["value"] = True

    def render_active_tab() -> None:
        report = jps.build_match_report(remote_members, ctx.config)
        if report.auto_matched:
            mark_dirty()

        summary = f"{len(report.linked)} linked"
        if report.auto_matched:
            summary += f", {len(report.auto_matched)} just auto-linked by matching email"
        summary_label.configure(text=summary + ".")

        index = state["active_tab"]
        page = pages[index]
        for child in page.winfo_children():
            child.destroy()

        if index == TAB_NEEDS_REVIEW:
            _render_potential_section(page, ctx, report, render_active_tab, mark_dirty)
        elif index == TAB_LOCAL_PEOPLE:
            _render_unmatched_local_section(page, ctx, report, render_active_tab, show_ignored_local, mark_dirty)
        else:
            _render_unmatched_remote_section(page, ctx, report, render_active_tab, show_ignored_remote, mark_dirty)

    render_active_tab()

    def close() -> None:
        if dirty["value"]:
            # A single atomic write can still be slow if Google Drive
            # Desktop happens to be holding a lock on Data/config.json at
            # that moment (see the retry-with-backoff in config.py) - don't
            # make the user wait on it just to close this window.
            def save_worker() -> None:
                try:
                    ctx.save_config()
                except Exception as exc:  # noqa: BLE001 - the window is already gone, surface it, don't crash
                    ctx.root.after(0, lambda: show_error_banner(ctx, f"Couldn't save people changes: {exc}"))

            threading.Thread(target=save_worker, daemon=True).start()
        win.destroy()

    RoundedButton(win, text="Close", variant="tonal", command=close).pack(pady=(0, 16))
    win.protocol("WM_DELETE_WINDOW", close)

    win.update_idletasks()
    x = ctx.root.winfo_x() + max((ctx.root.winfo_width() - win.winfo_width()) // 2, 0)
    y = ctx.root.winfo_y() + max((ctx.root.winfo_height() - win.winfo_height()) // 2, 0)
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.grab_set()


def _render_potential_section(parent, ctx, report, refresh, mark_dirty) -> None:
    if not report.potential:
        ttk.Label(parent, text="Nothing to review right now.", style="Muted.TLabel").pack(anchor="w", pady=(8, 16))
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


def _render_unmatched_remote_section(parent, ctx, report, refresh, show_ignored, mark_dirty) -> None:
    unlinked_people = [p for p in ctx.config.people if not p.jira_account_id]

    if not report.unmatched_remote:
        ttk.Label(parent, text="Every active Jira member is matched.", style="Muted.TLabel").pack(anchor="w", pady=(8, 8))
    for remote in report.unmatched_remote:
        card = RoundedCard(parent)
        card.pack(fill="x", pady=3)
        row = card.body
        info = tk.Frame(row, background=theme.CARD_BG)
        info.pack(side="left", fill="both", expand=True, padx=12, pady=8)
        tk.Label(info, text=remote.display_name, background=theme.CARD_BG, foreground=theme.INK,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        # Emailless members are still fully importable via "+ Add" below -
        # this just makes that explicit rather than leaving a blank line
        # that could read as "something's missing/excluded" (a real user
        # asked whether emailless people would show up as importable).
        if remote.email:
            tk.Label(info, text=remote.email, background=theme.CARD_BG, foreground=theme.MUTED,
                     font=("Segoe UI", 9)).pack(anchor="w")
        else:
            tk.Label(info, text="(no email on file)", background=theme.CARD_BG, foreground=theme.MUTED,
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


def _render_unmatched_local_section(parent, ctx, report, refresh, show_ignored, mark_dirty) -> None:
    if not report.unmatched_local:
        ttk.Label(parent, text="Every active local person is linked or marked unmatched.", style="Muted.TLabel").pack(
            anchor="w", pady=(8, 8),
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
