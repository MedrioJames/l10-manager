"""Jira people-matching review modal - reached from a "Review Jira People
Matches" button in Settings > Jira (see ui/settings.py). This is the
deliberate, reviewed counterpart to jira_sync.py's routine automatic sync:
it calls the heavier IssueConnector.list_project_members() to see everyone
Jira considers assignable on the project, then lets the user reconcile that
against the team's local People list - confirm/reject name-only matches,
link or add unmatched Jira members, and mark local people who just aren't
on Jira so they stop reappearing in review after review.

Same Toplevel/ScrollableFrame/refresh-in-place idiom as ui/people_modal.py.
Every mutating action calls ctx.save_config() then refresh() so the report
(from jira_people_sync.build_match_report()) is always recomputed fresh
rather than patched incrementally.
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

    def refresh() -> None:
        report = jps.build_match_report(remote_members, ctx.config)
        if report.auto_matched:
            ctx.save_config()

        for child in body.winfo_children():
            child.destroy()

        summary = f"{len(report.linked)} linked"
        if report.auto_matched:
            summary += f", {len(report.auto_matched)} just auto-linked by matching email"
        ttk.Label(body, text=summary + ".", style="Body.TLabel").pack(anchor="w", pady=(0, 16))

        _render_potential_section(body, ctx, report, refresh)
        _render_unmatched_remote_section(body, ctx, report, refresh, show_ignored_remote)
        _render_unmatched_local_section(body, ctx, report, refresh, show_ignored_local)

    refresh()

    RoundedButton(win, text="Close", variant="tonal", command=win.destroy).pack(pady=(0, 16))

    win.update_idletasks()
    x = ctx.root.winfo_x() + max((ctx.root.winfo_width() - win.winfo_width()) // 2, 0)
    y = ctx.root.winfo_y() + max((ctx.root.winfo_height() - win.winfo_height()) // 2, 0)
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.grab_set()


def _render_potential_section(parent, ctx, report, refresh) -> None:
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

        emails_differ = bool(person.email and remote.email and person.email.lower() != remote.email.lower())
        sync_email_var = tk.BooleanVar(value=False)
        if emails_differ:
            ttk.Checkbutton(
                info, text=f"Also update email to {remote.email}", variable=sync_email_var,
            ).pack(anchor="w")

        btns = tk.Frame(row, background=theme.CARD_BG)
        btns.pack(side="right", padx=8)

        def confirm(p=person, r=remote, var=sync_email_var) -> None:
            jps.confirm_potential_match(p, r, sync_email=var.get())
            ctx.save_config()
            refresh()

        def reject(p=person, r=remote) -> None:
            jps.reject_potential_match(ctx.config, p, r)
            ctx.save_config()
            refresh()

        icon_button.icon_button(btns, icon_button.GLYPH_SAVE, confirm).pack(side="left", padx=2)
        icon_button.icon_button(btns, icon_button.GLYPH_CANCEL, reject, danger=True).pack(side="left", padx=2)

    ttk.Frame(parent).pack(pady=(0, 12))


def _render_unmatched_remote_section(parent, ctx, report, refresh, show_ignored) -> None:
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
                ctx.save_config()
                refresh()

        link_combo.bind("<<ComboboxSelected>>", do_link)

        button_row = tk.Frame(actions, background=theme.CARD_BG)
        button_row.pack(side="top")

        def add_new(r=remote) -> None:
            jps.create_person_from_remote(ctx.config, r)
            ctx.save_config()
            show_toast(ctx, f"Added {r.display_name} to People.")
            refresh()

        def ignore(r=remote) -> None:
            jps.set_remote_ignored(ctx.config, r, True)
            ctx.save_config()
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
                    ctx.save_config()
                    refresh()

                icon_button.icon_button(row, icon_button.GLYPH_RESTORE, unignore).pack(side="right")

    ttk.Frame(parent).pack(pady=(0, 12))


def _render_unmatched_local_section(parent, ctx, report, refresh, show_ignored) -> None:
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
                ctx.save_config()
                refresh()

        find_combo.bind("<<ComboboxSelected>>", do_find)

        def leave_unmatched(p=person) -> None:
            jps.set_person_unmatched(p, True)
            ctx.save_config()
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
                    ctx.save_config()
                    refresh()

                icon_button.icon_button(row, icon_button.GLYPH_RESTORE, undo).pack(side="right")
