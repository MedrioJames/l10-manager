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

Cards for the active tab are built ONCE per genuine data change (tab open,
a mutation, or the ignored-toggle) via _fill_in_progressively, which builds
each card one at a time, paced via after() so a long list never blocks the
event loop, and PACKS IT IMMEDIATELY - extending the visible list right
there - if it currently matches the search box and the visible cap
(PAGE_SIZE, see below) hasn't been reached; otherwise the card is simply
never packed at all. Every built card, shown or not, is appended to
state["rows"] regardless, so a later search-text change or "Show more"
click can reveal any of them via _apply_search_filter with no rebuild.

This is the THIRD design here, each fixing a real problem the previous one
caused. The first built every card synchronously, which froze the UI for
however long a long list took. The second (this file's previous version)
built every card HIDDEN in the background and revealed them all together
once the whole batch finished, specifically to stop a search typed
mid-build from producing a visibly broken mix of correctly-filtered real
cards and skeleton placeholders that had no search keys to check. That fix
introduced a worse regression: _render_person_row/_render_jira_member_row
call card.pack() then card.update_idletasks() (forcing an actual paint) as
part of building EVERY card, and the hidden-build version then immediately
called pack_forget() right after - so every single card, shown or not,
flashed visibly into existence and back out, for the ENTIRE list, on every
normal tab open ("blinks a thousand times" - a real, and much more visible,
bug than the one being fixed). The fix this time: _render_person_row/
_render_jira_member_row no longer pack themselves or call
update_idletasks() at all - they just build content into card.body and
return the (unpacked) card. The CALLER decides: pack it + update_idletasks()
only for a card that's actually going to stay visible; a card that won't be
shown is simply never packed, so there's nothing to have painted and
nothing to flash. A widget that's never been given to a geometry manager
can't have been drawn on screen - Tk only schedules a paint once something
maps it, and since build_next() decides show-or-not in the same synchronous
step a card finishes building (no update()/mainloop turn happens in
between), an unshown card's pending idle tasks are never processed before
it would've mattered anyway. The mid-build search problem the SECOND design
solved is still solved here too, just differently: since there are no
skeleton placeholders anymore (nothing to show for an item that hasn't been
built yet), a search typed mid-build only ever affects cards that already
exist, which independently re-check their own match state - there's no
"inert placeholder ignoring the filter" to produce a broken mix.

PAGE_SIZE caps how many matching cards are ever packed at once - a real
user asked for pagination on top of the flash fix, so a very long Jira
member list doesn't render hundreds of live widgets by default. This is a
visibility cap, not a data cap: _fill_in_progressively still builds every
item in the background regardless (so search always works across the full
set, not just the current page), and a "Show N more" control (built once
per full rebuild, positioned via a stable zero-height anchor Frame so newly
revealed rows always insert themselves directly above it rather than at
the end of the whole page) only appears once the build is fully complete
and there's more to show - clicking it just raises state["visible_cap"] and
re-applies the filter, no rebuild. A new search resets the cap back to
PAGE_SIZE, so each search starts its own fresh first page.

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
PAGE_SIZE = 30


def _matches_search(search_text: str, *names: str) -> bool:
    if not search_text:
        return True
    needle = search_text.lower()
    return any(needle in (name or "").lower() for name in names)


def _apply_search_filter(rows, search_text: str, cap, before=None):
    """rows: list of (widget, search_keys) already fully built. Shows only
    the ones matching search_text, up to `cap` of them (None = unlimited),
    in their original build order - forgetting every row first (cheap) and
    re-packing only the matches avoids Tk's pack() re-appending a
    previously-hidden widget at the END of the stacking order instead of
    back where it was. `before`, if given, keeps every shown row inserted
    directly above that stable anchor widget rather than at the end of
    whatever else lives in the same parent (the "Show more" control and any
    trailing footer content). Returns (shown_count, total_match_count)."""
    for widget, _keys in rows:
        widget.pack_forget()
    shown = 0
    total = 0
    for widget, keys in rows:
        if _matches_search(search_text, *keys):
            total += 1
            if cap is None or shown < cap:
                pack_kwargs = {"fill": "x", "pady": 3}
                if before is not None:
                    pack_kwargs["before"] = before
                widget.pack(**pack_kwargs)
                shown += 1
    return shown, total


def _fill_in_progressively(
    ctx, parent, items, build_fn, search_keys_fn, get_search_text, get_cap,
    row_sink, generation, my_generation, anchor, on_complete=None,
) -> None:
    """items: the FULL, unfiltered list of rows for this tab - search
    filtering and the visible cap only affect which built cards get packed,
    never which ones get built. Builds one card at a time, paced via
    after() so a long list never blocks the event loop. Each finished card
    is appended to row_sink immediately (so a search or "Show more" click
    can always find it later, whether or not it's currently packed), and is
    packed right away - extending the visible list on the spot - only if it
    currently matches get_search_text() and the running shown-count is
    still under get_cap() (both read live, not captured up front, since
    typing or clicking "Show more" can happen while this is still running).
    A card that won't be shown is simply never packed - see the module
    docstring for why that's what avoids the visible flash an earlier
    version had. on_complete(), if given, runs once every item has been
    built (or immediately if items is empty)."""
    if not items:
        if on_complete is not None:
            on_complete()
        return

    shown_count = {"value": 0}

    def build_next(i: int = 0) -> None:
        if generation.get("value") != my_generation:
            return  # a newer render (or the window closing) superseded this one
        if i >= len(items):
            if on_complete is not None:
                on_complete()
            return
        card = build_fn(items[i])
        keys = search_keys_fn(items[i])
        row_sink.append((card, keys))
        if _matches_search(get_search_text(), *keys) and shown_count["value"] < get_cap():
            pack_kwargs = {"fill": "x", "pady": 3}
            if anchor is not None:
                pack_kwargs["before"] = anchor
            card.pack(**pack_kwargs)
            card.update_idletasks()
            shown_count["value"] += 1
        ctx.root.after(CARD_FILL_DELAY_MS, lambda: build_next(i + 1))

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
        "anchor": None,       # stable zero-height Frame rows/show-more insert themselves before
        "show_more_btn": None,
        "visible_cap": PAGE_SIZE,
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

    def get_cap() -> int:
        return state["visible_cap"]

    def show_more() -> None:
        state["visible_cap"] += PAGE_SIZE
        refresh_visible_rows()

    def refresh_visible_rows() -> None:
        """Re-applies the search filter and visible cap to whatever's
        already in state["rows"] - safe to call at any time, including
        mid-build (row_sink only ever grows, so this just reflects however
        much has been built so far)."""
        search_text = get_search_text()
        anchor = state["anchor"]
        shown, total = _apply_search_filter(state["rows"], search_text, state["visible_cap"], before=anchor)

        label = state["empty_label"]
        if label is not None:
            # Gated on build_complete only - not shown/total - so a search
            # that doesn't match anything BUILT YET doesn't flash "no
            # matches" while the rest of the list is still being built.
            if state["build_complete"] and state["rows"] and total == 0:
                label.configure(text=state["empty_text_fn"](search_text))
                label.pack(anchor="w", pady=8, before=anchor)
            else:
                label.pack_forget()

        btn = state["show_more_btn"]
        if btn is not None:
            remaining = total - shown
            if state["build_complete"] and remaining > 0:
                btn.configure(text=f"Show {min(remaining, PAGE_SIZE)} more ({remaining} left)")
                pack_kwargs = {"anchor": "w", "pady": (4, 8)}
                if anchor is not None:
                    pack_kwargs["before"] = anchor
                btn.pack(**pack_kwargs)
            else:
                btn.pack_forget()

    def render_active_tab(recompute: bool = True, force_rebuild: bool = None) -> None:
        index = state["active_tab"]
        if force_rebuild is None:
            force_rebuild = recompute

        if not force_rebuild and state["rows_tab"] == index:
            # Nothing about the underlying row set changed (this is a pure
            # search-text change) - just show/hide the widgets already built
            # for this tab, resetting to the first page of the new search.
            # No report recompute, no widget rebuilding at all, regardless
            # of list size - see module docstring.
            state["visible_cap"] = PAGE_SIZE
            refresh_visible_rows()
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
        state["visible_cap"] = PAGE_SIZE

        anchor = tk.Frame(page, height=0)
        anchor.pack(fill="x")
        state["anchor"] = anchor
        state["show_more_btn"] = None  # created by the tab-render fn below, only if it has a non-empty list

        def on_build_complete() -> None:
            state["build_complete"] = True
            refresh_visible_rows()

        if index == TAB_LOCAL_PEOPLE:
            _render_local_people_tab(
                page, ctx, report, render_active_tab, schedule_save,
                get_search_text, get_cap, show_more, state, generation, my_generation, on_build_complete,
            )
        else:
            _render_jira_members_tab(
                page, ctx, report, render_active_tab, show_ignored_remote, schedule_save,
                get_search_text, get_cap, show_more, state, generation, my_generation, on_build_complete,
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
    parent, ctx, report, refresh, schedule_save, get_search_text, get_cap, show_more, state,
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

    state["show_more_btn"] = RoundedButton(parent, text="Show more", variant="tonal", command=show_more)
    state["empty_label"] = ttk.Label(parent, style="Muted.TLabel")
    state["empty_text_fn"] = lambda search_text: f"No people matching \"{search_text}\"."

    def search_keys_fn(row_item):
        person, _kind, remote = row_item
        return (person.name, person.email, remote.display_name if remote else None, remote.email if remote else None)

    def build_fn(row_item):
        person, kind, remote = row_item
        return _render_person_row(parent, ctx, person, kind, remote, report, refresh, schedule_save)

    _fill_in_progressively(
        ctx, parent, rows, build_fn, search_keys_fn, get_search_text, get_cap,
        state["rows"], generation, my_generation, state["anchor"], on_build_complete,
    )


def _render_person_row(parent, ctx, person, kind, remote, report, refresh, schedule_save):
    card = RoundedCard(parent)
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
        return card

    if kind == "marked_unmatched":
        tk.Label(info, text="Marked as not on Jira", background=theme.CARD_BG, foreground=theme.MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w")

        def undo(p=person) -> None:
            jps.set_person_unmatched(p, False)
            schedule_save()
            refresh()

        icon_button.icon_button(actions, icon_button.GLYPH_RESTORE, undo).pack(side="top")
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
    return card


def _render_jira_members_tab(
    parent, ctx, report, refresh, show_ignored, schedule_save, get_search_text, get_cap, show_more,
    state, generation, my_generation, on_build_complete,
) -> None:
    unlinked_people = [p for p in ctx.config.people if not p.jira_account_id]

    if not report.unmatched_remote:
        ttk.Label(parent, text="Every active Jira member is matched.", style="Muted.TLabel").pack(anchor="w", pady=(8, 8))
        on_build_complete()
    else:
        state["show_more_btn"] = RoundedButton(parent, text="Show more", variant="tonal", command=show_more)
        state["empty_label"] = ttk.Label(parent, style="Muted.TLabel")
        state["empty_text_fn"] = lambda search_text: f"No Jira members matching \"{search_text}\"."

        def build_fn(remote):
            return _render_jira_member_row(parent, ctx, remote, unlinked_people, refresh, schedule_save)

        _fill_in_progressively(
            ctx, parent, report.unmatched_remote, build_fn, lambda r: (r.display_name, r.email),
            get_search_text, get_cap, state["rows"], generation, my_generation, state["anchor"],
            on_build_complete,
        )

    # The "ignored" footer is rebuilt directly (not cached/filtered like the
    # main list above) since it's small and collapsed by default - it only
    # reflects the search text as of the last full rebuild, not live typing,
    # an accepted tradeoff since this section is opt-in and rarely used. It
    # naturally lands after the anchor (and therefore after the main list
    # and "Show more" control, wherever those currently sit) since it's
    # packed here with no `before=`, appending to whatever's already in the
    # stacking order at this point in a full rebuild.
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


def _render_jira_member_row(parent, ctx, remote, unlinked_people, refresh, schedule_save):
    card = RoundedCard(parent)
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

    return card
