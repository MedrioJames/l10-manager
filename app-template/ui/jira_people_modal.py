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

on_tab_change() destroys the tab being LEFT (not just rebuilding the one
being entered) so total live widget count - and therefore Toplevel-destroy
time on Close - stays to one tab's worth regardless of how many tabs were
visited in a session.

Cards load progressively rather than all at once: render_active_tab()
immediately shows a grey, non-interactive skeleton card per row (just the
name + "Loading...", built and settled in one cheap pass), then replaces
each skeleton with its fully-built real card one at a time via
ctx.root.after() scheduling. A real user hit a multi-second blank freeze
on a long Jira member list once an earlier fix made every card settle its
own layout synchronously before the next one started (see
_render_person_row/_render_jira_member_row's per-card update_idletasks())
- building the WHOLE tab that way, hidden, then showing it all at once,
meant nothing was visible for however long that took. Showing the
skeleton list immediately and filling it in via after()-scheduled steps
keeps the UI responsive (each step yields back to Tk's event loop, so the
screen actually repaints between cards) and gives real progress feedback
instead of a freeze. state["render_generation"] is bumped at the start of
every render_active_tab() call; each scheduled fill-in step captures its
own generation number and checks it before doing anything, so switching
tabs, changing the search text, or any mutation-triggered refresh cleanly
cancels a still-running progressive build from a previous render instead
of racing with it.

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

A single search Entry (search_var) above the tabs filters whichever tab is
currently active by substring match against the name(s) shown on each row.
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

CARD_FILL_DELAY_MS = 20


def _matches_search(search_text: str, *names: str) -> bool:
    if not search_text:
        return True
    needle = search_text.lower()
    return any(needle in (name or "").lower() for name in names)


def _render_skeleton_card(parent, display_name: str):
    """A cheap, non-interactive placeholder shown immediately for a row
    that hasn't been fully built yet - just a name and a muted "Loading..."
    label, no comboboxes/buttons. Settles its own layout right away (it's
    simple enough that this is fast) so it doesn't itself contribute to
    any later Configure-event backlog."""
    card = RoundedCard(parent, background=theme.SUBTLE_BG)
    card.pack(fill="x", pady=3)
    row = card.body
    tk.Label(row, text=display_name, background=theme.SUBTLE_BG, foreground=theme.MUTED,
             font=("Segoe UI", 10, "bold")).pack(side="left", padx=12, pady=10)
    tk.Label(row, text="Loading...", background=theme.SUBTLE_BG, foreground=theme.MUTED,
             font=("Segoe UI", 9)).pack(side="right", padx=12, pady=10)
    card.update_idletasks()
    return card


def _fill_in_progressively(ctx, parent, items, name_fn, build_fn, generation, my_generation) -> None:
    """items: list of whatever build_fn/name_fn need. Shows a skeleton card
    per item immediately, then replaces them one at a time - build_fn(item,
    before_widget) must build the real card and pack it with
    before=before_widget, positioning it where the skeleton was."""
    if not items:
        return
    placeholders = [_render_skeleton_card(parent, name_fn(item)) for item in items]

    def build_next(i: int = 0) -> None:
        if generation.get("value") != my_generation:
            return  # a newer render superseded this one
        if i >= len(items):
            return
        skeleton = placeholders[i]
        build_fn(items[i], skeleton)
        skeleton.destroy()
        ctx.root.after(CARD_FILL_DELAY_MS, lambda: build_next(i + 1))

    # Deferred even for the first card, so every skeleton (including the
    # first) is actually shown - and a real paint cycle happens - before
    # any real card starts building.
    ctx.root.after(CARD_FILL_DELAY_MS, build_next)


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
    summary_label.pack(anchor="w", pady=(4, 8))

    search_var = tk.StringVar()
    search_row = ttk.Frame(header)
    search_row.pack(fill="x")
    ttk.Label(search_row, text="Search:", style="Body.TLabel").pack(side="left", padx=(0, 6))
    ttk.Entry(search_row, textvariable=search_var, width=32).pack(side="left")

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
    generation = {"value": 0}

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
        generation["value"] += 1
        my_generation = generation["value"]

        report = jps.build_match_report(remote_members, ctx.config)
        if report.auto_matched:
            schedule_save()

        summary = f"{len(report.linked)} linked"
        if report.auto_matched:
            summary += f", {len(report.auto_matched)} just auto-linked by matching email"
        summary_label.configure(text=summary + ".")

        index = state["active_tab"]
        page = pages[index]
        for child in page.winfo_children():
            child.destroy()

        search_text = search_var.get().strip()
        if index == TAB_LOCAL_PEOPLE:
            _render_local_people_tab(page, ctx, report, render_active_tab, schedule_save, search_text, generation, my_generation)
        else:
            _render_jira_members_tab(
                page, ctx, report, render_active_tab, show_ignored_remote, schedule_save, search_text, generation, my_generation,
            )

    search_var.trace_add("write", lambda *_args: render_active_tab())
    render_active_tab()

    RoundedButton(win, text="Close", variant="tonal", command=win.destroy).pack(pady=(0, 16))
    win.protocol("WM_DELETE_WINDOW", win.destroy)

    win.update_idletasks()
    x = ctx.root.winfo_x() + max((ctx.root.winfo_width() - win.winfo_width()) // 2, 0)
    y = ctx.root.winfo_y() + max((ctx.root.winfo_height() - win.winfo_height()) // 2, 0)
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.grab_set()


def _render_local_people_tab(parent, ctx, report, refresh, schedule_save, search_text, generation, my_generation) -> None:
    # "Untouched" (needs a decision) sorts before "settled" (already
    # resolved one way or another) - a real user asked for this ordering.
    untouched = [(m.person, "potential", m.remote) for m in report.potential]
    untouched += [(p, "unmatched", None) for p in report.unmatched_local]
    settled = [(m.person, "linked", m.remote) for m in report.linked]
    settled += [(p, "marked_unmatched", None) for p in report.unmatched_local_ignored]

    if not untouched and not settled:
        ttk.Label(parent, text="No local people yet.", style="Muted.TLabel").pack(anchor="w", pady=8)
        return

    rows = untouched + settled
    if search_text:
        rows = [
            (person, kind, remote) for person, kind, remote in rows
            if _matches_search(search_text, person.name, remote.display_name if remote else None)
        ]
        if not rows:
            ttk.Label(parent, text=f"No people matching \"{search_text}\".", style="Muted.TLabel").pack(anchor="w", pady=8)
            return

    def name_fn(row_item):
        person, _kind, _remote = row_item
        return person.name

    def build_fn(row_item, before_widget):
        person, kind, remote = row_item
        _render_person_row(parent, ctx, person, kind, remote, report, refresh, schedule_save, before=before_widget)

    _fill_in_progressively(ctx, parent, rows, name_fn, build_fn, generation, my_generation)


def _render_person_row(parent, ctx, person, kind, remote, report, refresh, schedule_save, before=None) -> None:
    card = RoundedCard(parent)
    pack_kwargs = {"fill": "x", "pady": 3}
    if before is not None:
        pack_kwargs["before"] = before
    card.pack(**pack_kwargs)
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
        card.update_idletasks()
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
        card.update_idletasks()
        return

    if kind == "marked_unmatched":
        tk.Label(info, text="Marked as not on Jira", background=theme.CARD_BG, foreground=theme.MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w")

        def undo(p=person) -> None:
            jps.set_person_unmatched(p, False)
            schedule_save()
            refresh()

        icon_button.icon_button(actions, icon_button.GLYPH_RESTORE, undo).pack(side="top")
        card.update_idletasks()
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
    card.update_idletasks()


def _render_jira_members_tab(parent, ctx, report, refresh, show_ignored, schedule_save, search_text, generation, my_generation) -> None:
    unlinked_people = [p for p in ctx.config.people if not p.jira_account_id]

    visible_remote = report.unmatched_remote
    visible_ignored = report.unmatched_remote_ignored
    if search_text:
        visible_remote = [r for r in visible_remote if _matches_search(search_text, r.display_name)]
        visible_ignored = [r for r in visible_ignored if _matches_search(search_text, r.display_name)]

    if not visible_remote:
        text = f"No Jira members matching \"{search_text}\"." if search_text else "Every active Jira member is matched."
        ttk.Label(parent, text=text, style="Muted.TLabel").pack(anchor="w", pady=(8, 8))
    else:
        def build_fn(remote, before_widget):
            _render_jira_member_row(parent, ctx, remote, unlinked_people, refresh, schedule_save, before=before_widget)

        _fill_in_progressively(ctx, parent, visible_remote, lambda r: r.display_name, build_fn, generation, my_generation)

    if visible_ignored:
        def toggle() -> None:
            show_ignored["value"] = not show_ignored["value"]
            refresh()

        RoundedButton(
            parent, text=f"{'Hide' if show_ignored['value'] else 'Show'} ignored ({len(visible_ignored)})",
            variant="tonal", command=toggle,
        ).pack(anchor="w", pady=(4, 8))

        if show_ignored["value"]:
            for remote in visible_ignored:
                row = ttk.Frame(parent)
                row.pack(fill="x", pady=2)
                ttk.Label(row, text=remote.display_name, style="Muted.TLabel").pack(side="left")

                def unignore(r=remote) -> None:
                    jps.set_remote_ignored(ctx.config, r, False)
                    schedule_save()
                    refresh()

                icon_button.icon_button(row, icon_button.GLYPH_RESTORE, unignore).pack(side="right")


def _render_jira_member_row(parent, ctx, remote, unlinked_people, refresh, schedule_save, before=None) -> None:
    card = RoundedCard(parent)
    pack_kwargs = {"fill": "x", "pady": 3}
    if before is not None:
        pack_kwargs["before"] = before
    card.pack(**pack_kwargs)
    row = card.body
    info = tk.Frame(row, background=theme.CARD_BG)
    info.pack(side="left", fill="both", expand=True, padx=12, pady=8)
    tk.Label(info, text=remote.display_name, background=theme.CARD_BG, foreground=theme.INK,
             font=("Segoe UI", 10, "bold")).pack(anchor="w")
    # Emailless members are still fully importable via "+ Add" below - this
    # just makes that explicit rather than leaving a blank line that could
    # read as "something's missing/excluded."
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

    # Force this card's RoundedCard to finish its (two-phase) resize right
    # now, before the next card starts building - see module docstring.
    card.update_idletasks()
