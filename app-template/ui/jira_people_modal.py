"""Jira people-matching review modal - reached from a "Review Jira People
Matches" button in Settings > Jira (see ui/settings.py). This is the
deliberate, reviewed counterpart to jira_sync.py's routine automatic sync:
it calls the heavier IssueConnector.list_project_members() to see everyone
Jira considers assignable on the project, then lets the user reconcile that
against the team's local People list.

Two tabs - "Local People" and "Jira Members" - rather than three. The
original "Needs Your Review" tab (potential name-only matches) is folded
directly into Local People as one more row-state instead of a separate
tab: a real user found "not sure what Needs Review is for" as a standalone
concept, and every local person - matched, potential, unmatched, or marked
unmatched - now shows up in ONE list with whatever actions apply to their
current state (confirm/reject, unlink/relink/sync-email, find-a-match/
leave-unmatched, or undo). Rows needing action (potential matches,
unmatched) sort before settled ones (linked, marked unmatched) - "show
untouched people first, then everyone else," per that same feedback.

render_active_tab() rebuilds only the currently active tab (not all
sections every click), and on_tab_change() also destroys the tab being
LEFT (not just rebuilding the one being entered) so total live widget
count - and therefore Toplevel-destroy time on Close - stays to one tab's
worth regardless of how many tabs were visited in a session. The whole
tab's ScrollableFrame is unpacked before tearing down/rebuilding its
children and re-packed only once fully built, so a tab switch reads as
one clean swap instead of visibly populating row-by-row (a real user
described switching to Jira Members as "loads weird in steps").

Every mutating action calls schedule_save() - a fire-and-forget background
thread per action (coalesced: if a save is already in flight when another
mutation happens, it's marked pending and re-runs once the current one
finishes, rather than piling up concurrent writers) - "save as you go"
rather than batching until Close. Data/ can live on a Google Drive/OneDrive/
Dropbox sync mount (see config.py's atomic_write_json retry-with-backoff
comment for the WinError 5 history), so even a single atomic write blocking
the main thread made Close feel slow - now Close just destroys the window;
whatever save is in flight keeps running independently and doesn't touch
Tkinter, so it can't be blocked by (or block) the window closing.
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

TAB_LOCAL_PEOPLE = 0
TAB_JIRA_MEMBERS = 1


def open_jira_people_matches_modal(ctx, remote_members) -> None:
    win = tk.Toplevel(ctx.root)
    win.title("Review Jira People Matches")
    win.configure(bg=theme.BG)
    win.transient(ctx.root)
    win.geometry("620x680")

    header = ttk.Frame(win)
    header.pack(fill="x", padx=20, pady=(20, 8))
    ttk.Label(header, text="Jira People Matches", style="Heading.TLabel").pack(anchor="w")
    summary_label = ttk.Label(header, text="", style="Body.TLabel")
    summary_label.pack(anchor="w", pady=(4, 0))

    tabs_container = ttk.Frame(win)
    tabs_container.pack(fill="both", expand=True, padx=20)

    def on_tab_change(index: int) -> None:
        previous = state["active_tab"]
        if previous != index:
            for child in pages[previous].winfo_children():
                child.destroy()
        state["active_tab"] = index
        render_active_tab()

    tabs = TabBar(tabs_container, ["Local People", "Jira Members"], on_change=on_tab_change)
    tabs.pack(fill="both", expand=True)

    scrolls = [ScrollableFrame(tabs.page(i)) for i in range(2)]
    for scroll in scrolls:
        scroll.pack(fill="both", expand=True)
    pages = [ttk.Frame(scroll.body) for scroll in scrolls]
    for page in pages:
        page.pack(fill="both", expand=True)

    show_ignored_remote = {"value": False}
    state = {"active_tab": TAB_LOCAL_PEOPLE}
    save_state = {"in_flight": False, "pending": False}

    def schedule_save() -> None:
        if save_state["in_flight"]:
            save_state["pending"] = True
            return
        save_state["in_flight"] = True

        def on_done() -> None:
            save_state["in_flight"] = False
            if save_state["pending"]:
                save_state["pending"] = False
                schedule_save()

        def worker() -> None:
            try:
                ctx.save_config()
            except Exception as exc:  # noqa: BLE001 - surface it, the window may already be gone
                ctx.root.after(0, lambda: show_error_banner(ctx, f"Couldn't save people changes: {exc}"))
            ctx.root.after(0, on_done)

        threading.Thread(target=worker, daemon=True).start()

    def render_active_tab() -> None:
        report = jps.build_match_report(remote_members, ctx.config)
        if report.auto_matched:
            schedule_save()

        summary = f"{len(report.linked)} linked"
        if report.auto_matched:
            summary += f", {len(report.auto_matched)} just auto-linked by matching email"
        summary_label.configure(text=summary + ".")

        index = state["active_tab"]
        scroll = scrolls[index]
        page = pages[index]
        # Unpack while rebuilding so the whole tab swaps in atomically once
        # instead of visibly populating row-by-row as each widget is added
        # to an already-visible parent.
        scroll.pack_forget()
        for child in page.winfo_children():
            child.destroy()

        if index == TAB_LOCAL_PEOPLE:
            _render_local_people_tab(page, ctx, report, render_active_tab, schedule_save)
        else:
            _render_jira_members_tab(page, ctx, report, render_active_tab, show_ignored_remote, schedule_save)

        scroll.pack(fill="both", expand=True)

    render_active_tab()

    RoundedButton(win, text="Close", variant="tonal", command=win.destroy).pack(pady=(0, 16))
    win.protocol("WM_DELETE_WINDOW", win.destroy)

    win.update_idletasks()
    x = ctx.root.winfo_x() + max((ctx.root.winfo_width() - win.winfo_width()) // 2, 0)
    y = ctx.root.winfo_y() + max((ctx.root.winfo_height() - win.winfo_height()) // 2, 0)
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.grab_set()


def _render_local_people_tab(parent, ctx, report, refresh, schedule_save) -> None:
    # "Untouched" (needs a decision) sorts before "settled" (already
    # resolved one way or another) - a real user asked for this ordering.
    untouched = [(m.person, "potential", m.remote) for m in report.potential]
    untouched += [(p, "unmatched", None) for p in report.unmatched_local]
    settled = [(m.person, "linked", m.remote) for m in report.linked]
    settled += [(p, "marked_unmatched", None) for p in report.unmatched_local_ignored]

    if not untouched and not settled:
        ttk.Label(parent, text="No local people yet.", style="Muted.TLabel").pack(anchor="w", pady=8)
        return

    for person, kind, remote in untouched + settled:
        _render_person_row(parent, ctx, person, kind, remote, report, refresh, schedule_save)


def _render_person_row(parent, ctx, person, kind, remote, report, refresh, schedule_save) -> None:
    card = RoundedCard(parent)
    card.pack(fill="x", pady=3)
    row = card.body
    info = tk.Frame(row, background=theme.CARD_BG)
    info.pack(side="left", fill="both", expand=True, padx=12, pady=8)
    actions = tk.Frame(row, background=theme.CARD_BG)
    actions.pack(side="right", padx=8, pady=6)

    if kind == "potential":
        tk.Label(info, text=f"{person.name}  ↔  {remote.display_name}", background=theme.CARD_BG,
                 foreground=theme.INK, font=("Segoe UI", 10, "bold")).pack(anchor="w")

        # Shown whenever Jira has an email we don't already have recorded
        # for this person - including when the local record has no email
        # at all yet.
        remote_email = remote.email
        person_email = person.email
        show_email_checkbox = bool(remote_email) and (
            not person_email or person_email.lower() != remote_email.lower()
        )
        sync_email_var = tk.BooleanVar(value=not person_email)
        if show_email_checkbox:
            label = f"Also update email to {remote_email}" if person_email else f"Add email: {remote_email}"
            ttk.Checkbutton(info, text=label, variable=sync_email_var).pack(anchor="w")

        def confirm(p=person, r=remote, var=sync_email_var) -> None:
            jps.confirm_potential_match(p, r, sync_email=var.get())
            schedule_save()
            refresh()

        def reject(p=person, r=remote) -> None:
            jps.reject_potential_match(ctx.config, p, r)
            schedule_save()
            refresh()

        icon_button.icon_button(actions, icon_button.GLYPH_SAVE, confirm).pack(side="left", padx=2)
        icon_button.icon_button(actions, icon_button.GLYPH_CANCEL, reject, danger=True).pack(side="left", padx=2)
        return

    tk.Label(info, text=person.name, background=theme.CARD_BG, foreground=theme.INK,
             font=("Segoe UI", 10, "bold")).pack(anchor="w")

    if kind == "linked":
        status_text = f"Linked to {remote.display_name}"
        tk.Label(info, text=status_text, background=theme.CARD_BG, foreground=theme.SUCCESS,
                 font=("Segoe UI", 9)).pack(anchor="w")

        remote_email = remote.email
        person_email = person.email
        needs_email_sync = bool(remote_email) and (
            not person_email or person_email.lower() != remote_email.lower()
        )
        if needs_email_sync:
            label = f"Add email from Jira: {remote_email}" if not person_email else f"Update email to {remote_email}"

            def sync_email(p=person, r=remote) -> None:
                jps.sync_email_from_remote(p, r)
                schedule_save()
                refresh()

            RoundedButton(info, text=label, variant="tonal", command=sync_email).pack(anchor="w", pady=(4, 0))

        other_remote = [r for r in report.unmatched_remote]
        relink_var = tk.StringVar(value=UNMATCHED_REMOTE_SENTINEL)
        if other_remote:
            relink_combo = ttk.Combobox(
                actions, textvariable=relink_var, state="readonly", width=18,
                values=[UNMATCHED_REMOTE_SENTINEL] + [r.display_name for r in other_remote],
            )
            relink_combo.pack(side="top", pady=(0, 4))

            def do_relink(_event=None, p=person, var=relink_var) -> None:
                if var.get() == UNMATCHED_REMOTE_SENTINEL:
                    return
                match = next((r for r in other_remote if r.display_name == var.get()), None)
                if match:
                    jps.link_existing_person(p, match)
                    schedule_save()
                    refresh()

            relink_combo.bind("<<ComboboxSelected>>", do_relink)

        def unlink(p=person) -> None:
            jps.unlink_person(p)
            schedule_save()
            refresh()

        RoundedButton(actions, text="Unlink", variant="tonal", command=unlink).pack(side="top")
        return

    if kind == "marked_unmatched":
        tk.Label(info, text="Marked as not on Jira", background=theme.CARD_BG, foreground=theme.MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w")

        def undo(p=person) -> None:
            jps.set_person_unmatched(p, False)
            schedule_save()
            refresh()

        icon_button.icon_button(actions, icon_button.GLYPH_RESTORE, undo).pack(side="top")
        return

    # kind == "unmatched"
    tk.Label(info, text="No Jira link", background=theme.CARD_BG, foreground=theme.MUTED,
             font=("Segoe UI", 9)).pack(anchor="w")

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
            schedule_save()
            refresh()

    find_combo.bind("<<ComboboxSelected>>", do_find)

    def leave_unmatched(p=person) -> None:
        jps.set_person_unmatched(p, True)
        schedule_save()
        refresh()

    RoundedButton(actions, text="Leave unmatched", variant="tonal", command=leave_unmatched).pack(side="top")


def _render_jira_members_tab(parent, ctx, report, refresh, show_ignored, schedule_save) -> None:
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
        # that could read as "something's missing/excluded."
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
                schedule_save()
                refresh()

        link_combo.bind("<<ComboboxSelected>>", do_link)

        button_row = tk.Frame(actions, background=theme.CARD_BG)
        button_row.pack(side="top")

        def add_new(r=remote) -> None:
            jps.create_person_from_remote(ctx.config, r)
            schedule_save()
            show_toast(ctx, f"Added {r.display_name} to People.")
            refresh()

        def ignore(r=remote) -> None:
            jps.set_remote_ignored(ctx.config, r, True)
            schedule_save()
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
                    schedule_save()
                    refresh()

                icon_button.icon_button(row, icon_button.GLYPH_RESTORE, unignore).pack(side="right")
