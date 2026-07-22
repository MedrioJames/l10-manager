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

Cards for the active tab are built ONCE - via a skeleton-then-progressive
fill (see _fill_in_progressively) so a long list still gives instant visual
feedback and never blocks the event loop building many cards back-to-back -
and then CACHED as (widget, search_keys) pairs in state["rows"]. Search is
just showing/hiding those already-built widgets (_apply_search_filter),
never rebuilding them. This split exists because an earlier version
recomputed jps.build_match_report() and rebuilt every card from scratch on
every keystroke (even with a debounce collapsing rapid keystrokes down to
one rebuild): a real user reported that typing still "sits and sits" and
the window going "Not Responding," since a full rebuild's cost scales with
list size and a longer Jira member list made even one rebuild slow, and
clearing the search back to the full list paid the same cost all over
again. Since remote_members is already fetched once, in full, before this
modal ever opens (see ui/settings.py's caller), and the local People list
doesn't change while you type, there was never any real reason for a
keystroke to touch the data or the widgets at all - only which of the
already-built rows are visible needs to change, and that's a cheap
pack_forge/pack pass regardless of list size (see _apply_search_filter).

render_active_tab(recompute, force_rebuild) separates two independent
questions: whether jps.build_match_report() needs to rerun (recompute -
only true for an actual mutation: confirm/reject/link/unlink/etc.), and
whether the tab's row widgets need to be thrown away and rebuilt
(force_rebuild - true for a mutation, a tab switch, or the "Show/Hide
ignored" toggle, since none of those are "the same rows, different
filter"). A pure search-text change passes neither, so it hits the fast
path: state["rows"] already holds this tab's built widgets, so
render_active_tab just re-filters them and returns - no report recompute,
no destroy, no rebuild, no matter how long the list is.

generation still guards the async progressive fill against a stale build
touching widgets that a newer render (or the window closing - see
on_close) has already torn down; every scheduled fill-in step checks its
own captured generation before doing anything.

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

CARD_FILL_DELAY_MS = 20


def _matches_search(search_text: str, *names: str) -> bool:
    if not search_text:
        return True
    needle = search_text.lower()
    return any(needle in (name or "").lower() for name in names)


def _apply_search_filter(rows, search_text: str) -> None:
    """rows: list of (widget, search_keys) already fully built. Shows only
    the ones matching search_text, in their original build order - forgetting
    every row first (cheap) and re-packing only the matches (in list order)
    avoids Tk's pack() re-appending a previously-hidden widget at the END of
    the stacking order instead of back where it was."""
    for widget, _keys in rows:
        widget.pack_forget()
    for widget, keys in rows:
        if _matches_search(search_text, *keys):
            widget.pack(fill="x", pady=3)


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


def _fill_in_progressively(
    ctx, parent, items, name_fn, build_fn, search_keys_fn, get_search_text,
    row_sink, generation, my_generation, on_complete=None,
) -> None:
    """items: the FULL, unfiltered list of rows for this tab - search
    filtering is applied only to visibility, never to which items get built.
    Shows a skeleton card per item immediately, then replaces them one at a
    time - build_fn(item, before_widget) must build the real card, pack it
    with before=before_widget (positioning it where the skeleton was), and
    return the built widget. Each finished (widget, search_keys) pair is
    appended to row_sink - the SAME list a search-text change later filters
    via _apply_search_filter with no rebuild - and hidden immediately if it
    doesn't match whatever's currently in the search box (get_search_text()
    is called live, not captured up front, since typing can happen while
    this is still running). on_complete(), if given, runs once every item
    has been built (or immediately if items is empty)."""
    if not items:
        if on_complete is not None:
            on_complete()
        return
    placeholders = [_render_skeleton_card(parent, name_fn(item)) for item in items]

    def build_next(i: int = 0) -> None:
        if generation.get("value") != my_generation:
            return  # a newer render (or the window closing) superseded this one
        if i >= len(items):
            if on_complete is not None:
                on_complete()
            return
        skeleton = placeholders[i]
        widget = build_fn(items[i], skeleton)
        skeleton.destroy()
        keys = search_keys_fn(items[i])
        row_sink.append((widget, keys))
        if not _matches_search(get_search_text(), *keys):
            widget.pack_forget()
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
    ttk.Label(search_row, text="Search (name or email):", style="Body.TLabel").pack(side="left", padx=(0, 6))
    ttk.Entry(search_row, textvariable=search_var, width=32).pack(side="left")

    tabs_container = ttk.Frame(win)
    tabs_container.pack(fill="both", expand=True, padx=20)

    def on_tab_change(index: int) -> None:
        previous = state["active_tab"]
        if previous != index:
            for child in pages[previous].winfo_children():
                child.destroy()
        state["active_tab"] = index
        render_active_tab(recompute=False)

    tabs = TabBar(tabs_container, ["Local People", "Jira Members"], on_change=on_tab_change)
    tabs.pack(fill="both", expand=True)

    scrolls = [ScrollableFrame(tabs.page(i)) for i in range(2)]
    for scroll in scrolls:
        scroll.pack(fill="both", expand=True)
    pages = [ttk.Frame(scroll.body) for scroll in scrolls]
    for page in pages:
        page.pack(fill="both", expand=True)

    show_ignored_remote = {"value": False}
    state = {
        "active_tab": TAB_LOCAL_PEOPLE,
        "rows": [],           # (widget, search_keys) built for the currently-active tab
        "rows_tab": None,     # which tab index `rows` was built for
        "build_complete": True,
        "empty_label": None,
        "empty_text_fn": None,
    }
    save_state = {"in_flight": False, "pending": False}
    generation = {"value": 0}
    report_state = {"value": None}

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

    def get_search_text() -> str:
        return search_var.get().strip()

    def refresh_empty_label() -> None:
        label = state["empty_label"]
        if label is None:
            return
        if not state["build_complete"]:
            return  # don't flash "no matches" while rows are still trickling in
        # Checked via _matches_search directly, NOT widget.winfo_ismapped() -
        # Tk defers actually updating a widget's mapped state to its idle
        # queue, so querying it immediately after a pack()/pack_forget() call
        # (same synchronous pass) can read stale state and show "no matches"
        # even when rows really did just become visible.
        search_text = get_search_text()
        any_visible = any(_matches_search(search_text, *keys) for _widget, keys in state["rows"])
        if state["rows"] and not any_visible:
            label.configure(text=state["empty_text_fn"](search_text))
            label.pack(anchor="w", pady=8)
        else:
            label.pack_forget()

    def render_active_tab(recompute: bool = True, force_rebuild: bool = None) -> None:
        index = state["active_tab"]
        if force_rebuild is None:
            force_rebuild = recompute

        if not force_rebuild and state["rows_tab"] == index:
            # Nothing about the underlying row set changed (this is a pure
            # search-text change) - just show/hide the widgets already built
            # for this tab. No report recompute, no widget rebuilding at
            # all, regardless of list size - see module docstring.
            _apply_search_filter(state["rows"], get_search_text())
            refresh_empty_label()
            return

        generation["value"] += 1
        my_generation = generation["value"]

        # remote_members was already fetched once, in full, before this modal
        # ever opened (see ui/settings.py's caller) - matching against it is
        # a pure in-memory computation, never a Jira API call.
        if recompute or report_state["value"] is None:
            report = jps.build_match_report(remote_members, ctx.config)
            report_state["value"] = report
            if report.auto_matched:
                schedule_save()
        else:
            report = report_state["value"]

        summary = f"{len(report.linked)} linked"
        if report.auto_matched:
            summary += f", {len(report.auto_matched)} just auto-linked by matching email"
        summary_label.configure(text=summary + ".")

        page = pages[index]
        for child in page.winfo_children():
            child.destroy()

        state["rows"] = []
        state["rows_tab"] = index
        state["build_complete"] = False
        state["empty_label"] = None
        state["empty_text_fn"] = None

        def on_build_complete() -> None:
            state["build_complete"] = True
            refresh_empty_label()

        if index == TAB_LOCAL_PEOPLE:
            _render_local_people_tab(
                page, ctx, report, render_active_tab, schedule_save,
                get_search_text, state, generation, my_generation, on_build_complete,
            )
        else:
            _render_jira_members_tab(
                page, ctx, report, render_active_tab, show_ignored_remote, schedule_save,
                get_search_text, state, generation, my_generation, on_build_complete,
            )

    def on_search_changed(*_args) -> None:
        render_active_tab(recompute=False)

    search_var.trace_add("write", on_search_changed)
    render_active_tab()

    def on_close() -> None:
        # Invalidate any progressive fill still trickling in so its next
        # scheduled step no-ops instead of touching widgets this destroys.
        generation["value"] += 1
        win.destroy()

    RoundedButton(win, text="Close", variant="tonal", command=on_close).pack(pady=(0, 16))
    win.protocol("WM_DELETE_WINDOW", on_close)

    win.update_idletasks()
    x = ctx.root.winfo_x() + max((ctx.root.winfo_width() - win.winfo_width()) // 2, 0)
    y = ctx.root.winfo_y() + max((ctx.root.winfo_height() - win.winfo_height()) // 2, 0)
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.grab_set()


def _render_local_people_tab(
    parent, ctx, report, refresh, schedule_save, get_search_text, state,
    generation, my_generation, on_build_complete,
) -> None:
    # "Untouched" (needs a decision) sorts before "settled" (already
    # resolved one way or another) - a real user asked for this ordering.
    untouched = [(m.person, "potential", m.remote) for m in report.potential]
    untouched += [(p, "unmatched", None) for p in report.unmatched_local]
    settled = [(m.person, "linked", m.remote) for m in report.linked]
    settled += [(p, "marked_unmatched", None) for p in report.unmatched_local_ignored]

    if not untouched and not settled:
        ttk.Label(parent, text="No local people yet.", style="Muted.TLabel").pack(anchor="w", pady=8)
        on_build_complete()
        return

    rows = untouched + settled

    state["empty_label"] = ttk.Label(parent, style="Muted.TLabel")
    state["empty_text_fn"] = lambda search_text: f"No people matching \"{search_text}\"."

    def name_fn(row_item):
        person, _kind, _remote = row_item
        return person.name

    def search_keys_fn(row_item):
        person, _kind, remote = row_item
        return (person.name, person.email, remote.display_name if remote else None, remote.email if remote else None)

    def build_fn(row_item, before_widget):
        person, kind, remote = row_item
        return _render_person_row(parent, ctx, person, kind, remote, report, refresh, schedule_save, before=before_widget)

    _fill_in_progressively(
        ctx, parent, rows, name_fn, build_fn, search_keys_fn, get_search_text,
        state["rows"], generation, my_generation, on_build_complete,
    )


def _render_person_row(parent, ctx, person, kind, remote, report, refresh, schedule_save, before=None):
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
        return card

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
        return card

    if kind == "marked_unmatched":
        tk.Label(info, text="Marked as not on Jira", background=theme.CARD_BG, foreground=theme.MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w")

        def undo(p=person) -> None:
            jps.set_person_unmatched(p, False)
            schedule_save()
            refresh()

        icon_button.icon_button(actions, icon_button.GLYPH_RESTORE, undo).pack(side="top")
        card.update_idletasks()
        return card

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
    return card


def _render_jira_members_tab(
    parent, ctx, report, refresh, show_ignored, schedule_save, get_search_text,
    state, generation, my_generation, on_build_complete,
) -> None:
    unlinked_people = [p for p in ctx.config.people if not p.jira_account_id]

    if not report.unmatched_remote:
        ttk.Label(parent, text="Every active Jira member is matched.", style="Muted.TLabel").pack(anchor="w", pady=(8, 8))
        on_build_complete()
    else:
        state["empty_label"] = ttk.Label(parent, style="Muted.TLabel")
        state["empty_text_fn"] = lambda search_text: f"No Jira members matching \"{search_text}\"."

        def build_fn(remote, before_widget):
            return _render_jira_member_row(parent, ctx, remote, unlinked_people, refresh, schedule_save, before=before_widget)

        _fill_in_progressively(
            ctx, parent, report.unmatched_remote, lambda r: r.display_name, build_fn,
            lambda r: (r.display_name, r.email), get_search_text, state["rows"], generation, my_generation,
            on_build_complete,
        )

    # The "ignored" footer is rebuilt directly (not cached/filtered like the
    # main list above) since it's small and collapsed by default - it only
    # reflects the search text as of the last full rebuild, not live typing,
    # an accepted tradeoff since this section is opt-in and rarely used.
    search_text = get_search_text()
    visible_ignored = [r for r in report.unmatched_remote_ignored if _matches_search(search_text, r.display_name, r.email)]
    if visible_ignored:
        def toggle() -> None:
            show_ignored["value"] = not show_ignored["value"]
            refresh(recompute=False, force_rebuild=True)

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


def _render_jira_member_row(parent, ctx, remote, unlinked_people, refresh, schedule_save, before=None):
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
    return card
