"""Settings - sectioned into tabs (Meeting & Schedule / People / Board /
Jira) via ui/tabs.py's TabBar, rather than one long scrolling page. Each
tab keeps its own edit sub-mode; state["active_tab"] tracks which tab to
return to after a save/cancel rebuild.
"""

from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox

import config as cfgmod
import credential_store
import issues as iss
import jira_sync
import schedule as sch
from connectors.jira import JiraConnector
from ui import icon_button, people_modal, schedule_entry_editor, theme
from ui.meeting_info_form import MeetingInfoForm
from ui.instance_form import RepeatingInstanceForm
from ui.notifications import show_error_banner, show_toast
from ui.rounded_button import RoundedButton
from ui.rounded_card import RoundedCard
from ui.scrollable import ScrollableFrame
from ui.tabs import TabBar

JIRA_TOKEN_SECRET_NAME = "jira_api_token"
HIDDEN_SENTINEL = "Hidden (not shown on board)"

TAB_MEETING = 0
TAB_PEOPLE = 1
TAB_BOARD = 2
TAB_JIRA = 3


def _app_dir() -> Path:
    return Path(cfgmod.__file__).resolve().parent


def build(ctx, edit_instance_id: str = None, **kwargs) -> None:
    if edit_instance_id is not None:
        state = {"sub_mode": "edit_instance", "editing_id": edit_instance_id, "active_tab": TAB_MEETING}
    else:
        state = {"sub_mode": "overview", "editing_id": None, "active_tab": TAB_MEETING}
    _render(ctx, state)


def _render(ctx, state) -> None:
    for child in ctx.content.winfo_children():
        child.destroy()

    outer = ttk.Frame(ctx.content)
    outer.pack(fill="both", expand=True, padx=32, pady=28)
    ttk.Label(outer, text="Settings", style="Heading.TLabel").pack(anchor="w", pady=(0, 16))

    def on_tab_change(index: int) -> None:
        state["active_tab"] = index

    tabs = TabBar(outer, ["Meeting & Schedule", "People", "Board", "Jira"], on_change=on_tab_change)
    tabs.pack(fill="both", expand=True)

    meeting_tab = ScrollableFrame(tabs.page(TAB_MEETING))
    meeting_tab.pack(fill="both", expand=True)
    people_tab = ScrollableFrame(tabs.page(TAB_PEOPLE))
    people_tab.pack(fill="both", expand=True)
    board_tab = ScrollableFrame(tabs.page(TAB_BOARD))
    board_tab.pack(fill="both", expand=True)
    jira_tab = ScrollableFrame(tabs.page(TAB_JIRA))
    jira_tab.pack(fill="both", expand=True)

    _render_meeting_tab(ctx, state, _padded(meeting_tab.body))
    _render_people_tab(ctx, state, _padded(people_tab.body))
    _render_board_tab(ctx, state, _padded(board_tab.body))
    _render_jira_tab(ctx, state, _padded(jira_tab.body))

    tabs.select(state.get("active_tab", TAB_MEETING))


def _padded(parent) -> ttk.Frame:
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=True, padx=16, pady=16)
    return frame


# --- Meeting & Schedule tab ------------------------------------------------

def _render_meeting_tab(ctx, state, frame) -> None:
    if state["sub_mode"] == "edit_instance":
        _render_edit_instance(ctx, state, frame)
        return

    ttk.Label(frame, text="Meeting Info", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 8))
    info_form = MeetingInfoForm(frame, name=ctx.config.meeting.name, description=ctx.config.meeting.description)
    info_form.pack(anchor="w")

    def save_info() -> None:
        data = info_form.get_data()
        ctx.config.meeting = cfgmod.MeetingInfo(name=data["name"], description=data["description"])
        ctx.save_config()
        show_toast(ctx, "Meeting info saved.")
        state["active_tab"] = TAB_MEETING
        _render(ctx, state)

    RoundedButton(frame, text="Save Meeting Info", variant="filled", command=save_info).pack(anchor="w", pady=(10, 28))

    ttk.Label(frame, text="Repeating Meetings", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 8))

    if not ctx.config.repeating_instances:
        ttk.Label(frame, text="No repeating meetings yet.", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
    else:
        for instance in ctx.config.repeating_instances:
            card = RoundedCard(frame)
            card.pack(fill="x", pady=4)
            row = card.body
            info = tk.Frame(row, background=theme.CARD_BG)
            info.pack(side="left", fill="both", expand=True, padx=12, pady=8)
            tk.Label(info, text=instance.name, background=theme.CARD_BG, foreground=theme.INK,
                     font=("Segoe UI", 10, "bold")).pack(anchor="w")
            tk.Label(info, text=f"{instance.recurrence.describe()} - {instance.default_length_minutes} min",
                     background=theme.CARD_BG, foreground=theme.MUTED, font=("Segoe UI", 9)).pack(anchor="w")

            button_box = tk.Frame(row, background=theme.CARD_BG)
            button_box.pack(side="right", padx=8)
            icon_button.icon_button(
                button_box, icon_button.GLYPH_EDIT, lambda i=instance.id: _goto_edit_instance(ctx, state, i),
            ).pack(side="left", padx=2)
            icon_button.icon_button(
                button_box, icon_button.GLYPH_DELETE, lambda i=instance.id: _remove_instance(ctx, state, i), danger=True,
            ).pack(side="left", padx=2)

    RoundedButton(
        frame, text="+ Add a Repeating Meeting", variant="tonal",
        command=lambda: _goto_edit_instance(ctx, state, None),
    ).pack(anchor="w", pady=(12, 0))


def _goto_edit_instance(ctx, state, instance_id) -> None:
    state["sub_mode"] = "edit_instance"
    state["editing_id"] = instance_id
    state["active_tab"] = TAB_MEETING
    _render(ctx, state)


def _remove_instance(ctx, state, instance_id) -> None:
    if not messagebox.askyesno("Remove meeting", "Remove this repeating meeting? This can't be undone."):
        return
    ctx.config.repeating_instances = [r for r in ctx.config.repeating_instances if r.id != instance_id]
    ctx.save_config()
    state["active_tab"] = TAB_MEETING
    _render(ctx, state)


def _render_edit_instance(ctx, state, frame) -> None:
    instance = ctx.config.find_instance(state["editing_id"])
    title = "Edit Repeating Meeting" if instance else "Add a Repeating Meeting"
    ttk.Label(frame, text=title, style="Heading.TLabel").pack(anchor="w", pady=(0, 16))

    def request_new_schedule(form_ref) -> None:
        def on_created(new_schedule) -> None:
            wrapper = sch.schedule_display_items([new_schedule], ctx.config.segments)[0]
            form_ref.add_schedule_option(wrapper)

        schedule_entry_editor.open_new_schedule_modal(ctx, on_created)

    form = RepeatingInstanceForm(
        frame, schedules=sch.schedule_display_items(ctx.config.schedules, ctx.config.segments), instance=instance,
        on_request_new_schedule=request_new_schedule,
    )
    form.pack(anchor="w", fill="x")

    button_row = ttk.Frame(frame)
    button_row.pack(fill="x", pady=(20, 0))

    def cancel() -> None:
        state["sub_mode"] = "overview"
        state["active_tab"] = TAB_MEETING
        _render(ctx, state)

    def save() -> None:
        try:
            fields = form.get_instance_fields()
        except ValueError as exc:
            show_error_banner(ctx, f"Check the recurrence: {exc}")
            return
        if instance:
            instance.name = fields["name"]
            instance.description = fields["description"]
            instance.default_length_minutes = fields["default_length_minutes"]
            instance.schedule_id = fields["schedule_id"]
            instance.recurrence = fields["recurrence"]
        else:
            ctx.config.repeating_instances.append(cfgmod.RepeatingInstance(
                name=fields["name"],
                description=fields["description"],
                default_length_minutes=fields["default_length_minutes"],
                recurrence=fields["recurrence"],
                schedule_id=fields["schedule_id"],
            ))
        ctx.save_config()
        show_toast(ctx, "Repeating meeting saved.")
        state["sub_mode"] = "overview"
        state["active_tab"] = TAB_MEETING
        _render(ctx, state)

    RoundedButton(button_row, text="Cancel", variant="tonal", command=cancel).pack(side="left")
    RoundedButton(button_row, text="Save", variant="filled", command=save).pack(side="right")


# --- People tab -------------------------------------------------------------

def _render_people_tab(ctx, state, frame) -> None:
    ttk.Label(frame, text="People", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 8))

    if not ctx.config.people:
        ttk.Label(frame, text="No people added yet.", style="Muted.TLabel").pack(anchor="w", pady=(0, 12))
    else:
        names = ", ".join(p.name for p in ctx.config.people)
        ttk.Label(
            frame, text=f"{len(ctx.config.people)} people: {names}", style="Body.TLabel",
            wraplength=520, justify="left",
        ).pack(anchor="w", pady=(0, 12))

    def open_modal() -> None:
        people_modal.open_people_modal(ctx)
        _render(ctx, state)

    RoundedButton(frame, text="Manage People...", variant="filled", command=open_modal).pack(anchor="w")


# --- Board tab (columns, statuses, card display) ----------------------------

def _render_board_tab(ctx, state, frame) -> None:
    if state["sub_mode"] == "edit_column":
        _render_edit_column(ctx, state, frame)
        return
    if state["sub_mode"] == "edit_status":
        _render_edit_status(ctx, state, frame)
        return

    ttk.Label(frame, text="Card Display", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 8))
    show_status_var = tk.BooleanVar(value=ctx.config.board_display.show_status)
    show_desc_var = tk.BooleanVar(value=ctx.config.board_display.show_description)
    show_assignee_var = tk.BooleanVar(value=ctx.config.board_display.show_assignee)
    ttk.Checkbutton(frame, text="Show status on cards", variable=show_status_var).pack(anchor="w")
    ttk.Checkbutton(frame, text="Show description snippet on cards", variable=show_desc_var).pack(anchor="w")
    ttk.Checkbutton(frame, text="Show assignee on cards", variable=show_assignee_var).pack(anchor="w", pady=(0, 8))

    def save_display() -> None:
        ctx.config.board_display = cfgmod.BoardDisplaySettings(
            show_status=show_status_var.get(),
            show_description=show_desc_var.get(),
            show_assignee=show_assignee_var.get(),
        )
        ctx.save_config()
        show_toast(ctx, "Display settings saved.")

    RoundedButton(frame, text="Save Display Settings", variant="filled", command=save_display).pack(anchor="w", pady=(0, 24))

    ttk.Label(frame, text="Columns", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Label(
        frame, text="Columns are what you see on the board. Multiple statuses can share one column - "
                     "dragging a card there will ask which status you mean.",
        style="Muted.TLabel", wraplength=520,
    ).pack(anchor="w", pady=(0, 8))

    for column in ctx.config.sorted_columns():
        card = RoundedCard(frame)
        card.pack(fill="x", pady=4)
        row = card.body
        info = tk.Frame(row, background=theme.CARD_BG)
        info.pack(side="left", fill="both", expand=True, padx=12, pady=8)
        tk.Label(info, text=column.name, background=theme.CARD_BG, foreground=theme.INK,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        statuses_here = ctx.config.statuses_in_column(column.id)
        status_text = ", ".join(s.name for s in statuses_here) or "(no statuses assigned yet)"
        tk.Label(info, text=status_text, background=theme.CARD_BG, foreground=theme.MUTED,
                 font=("Segoe UI", 9), wraplength=380, justify="left").pack(anchor="w")

        btns = tk.Frame(row, background=theme.CARD_BG)
        btns.pack(side="right", padx=8)
        icon_button.icon_button(
            btns, icon_button.GLYPH_EDIT, lambda c=column.id: _goto_edit_column(ctx, state, c),
        ).pack(side="left", padx=2)
        icon_button.icon_button(
            btns, icon_button.GLYPH_DELETE, lambda c=column.id: _delete_column(ctx, state, c), danger=True,
        ).pack(side="left", padx=2)

    RoundedButton(
        frame, text="+ Add Column", variant="tonal",
        command=lambda: _goto_edit_column(ctx, state, None),
    ).pack(anchor="w", pady=(8, 28))

    ttk.Label(frame, text="Statuses", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Label(
        frame, text="Each status belongs to one column, or can be hidden from the board entirely.",
        style="Muted.TLabel", wraplength=520,
    ).pack(anchor="w", pady=(0, 8))

    for status in ctx.config.statuses:
        card = RoundedCard(frame)
        card.pack(fill="x", pady=4)
        row = card.body
        info = tk.Frame(row, background=theme.CARD_BG)
        info.pack(side="left", fill="both", expand=True, padx=12, pady=8)
        tk.Label(info, text=status.name, background=theme.CARD_BG, foreground=theme.INK,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        col = ctx.config.find_column(status.column_id)
        tk.Label(info, text=(f"Column: {col.name}" if col else "Hidden from board"), background=theme.CARD_BG,
                 foreground=theme.MUTED, font=("Segoe UI", 9)).pack(anchor="w")

        btns = tk.Frame(row, background=theme.CARD_BG)
        btns.pack(side="right", padx=8)
        icon_button.icon_button(
            btns, icon_button.GLYPH_EDIT, lambda s=status.id: _goto_edit_status(ctx, state, s),
        ).pack(side="left", padx=2)
        icon_button.icon_button(
            btns, icon_button.GLYPH_DELETE, lambda s=status.id: _delete_status(ctx, state, s), danger=True,
        ).pack(side="left", padx=2)

    RoundedButton(
        frame, text="+ Add Status", variant="tonal",
        command=lambda: _goto_edit_status(ctx, state, None),
    ).pack(anchor="w", pady=(8, 0))


def _goto_edit_column(ctx, state, column_id) -> None:
    state["sub_mode"] = "edit_column"
    state["editing_id"] = column_id
    state["active_tab"] = TAB_BOARD
    _render(ctx, state)


def _delete_column(ctx, state, column_id) -> None:
    if ctx.config.statuses_in_column(column_id):
        show_error_banner(ctx, "Can't delete a column that still has statuses assigned to it - move or delete those statuses first.")
        return
    ctx.config.columns = [c for c in ctx.config.columns if c.id != column_id]
    ctx.save_config()
    state["active_tab"] = TAB_BOARD
    _render(ctx, state)


def _render_edit_column(ctx, state, frame) -> None:
    column = ctx.config.find_column(state["editing_id"])
    ttk.Label(frame, text="Edit Column" if column else "Add Column", style="Heading.TLabel").pack(anchor="w", pady=(0, 16))

    name_var = tk.StringVar(value=column.name if column else "")
    ttk.Label(frame, text="Name", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Entry(frame, textvariable=name_var, width=30).pack(anchor="w", pady=(0, 16))

    button_row = ttk.Frame(frame)
    button_row.pack(fill="x")

    def cancel() -> None:
        state["sub_mode"] = "overview"
        state["active_tab"] = TAB_BOARD
        _render(ctx, state)

    def save() -> None:
        name = name_var.get().strip()
        if not name:
            show_error_banner(ctx, "Give this column a name.")
            return
        if column:
            column.name = name
        else:
            max_order = max((c.order for c in ctx.config.columns), default=-1)
            ctx.config.columns.append(cfgmod.Column(name=name, order=max_order + 1))
        ctx.save_config()
        show_toast(ctx, "Column saved.")
        state["sub_mode"] = "overview"
        state["active_tab"] = TAB_BOARD
        _render(ctx, state)

    RoundedButton(button_row, text="Cancel", variant="tonal", command=cancel).pack(side="left")
    RoundedButton(button_row, text="Save", variant="filled", command=save).pack(side="right")


def _goto_edit_status(ctx, state, status_id) -> None:
    state["sub_mode"] = "edit_status"
    state["editing_id"] = status_id
    state["active_tab"] = TAB_BOARD
    _render(ctx, state)


def _delete_status(ctx, state, status_id) -> None:
    if any(i.status == status_id for i in iss.load_issues().values()):
        show_error_banner(ctx, "Can't delete a status that's currently used by an issue - move those issues to a different status first.")
        return
    ctx.config.statuses = [s for s in ctx.config.statuses if s.id != status_id]
    ctx.save_config()
    state["active_tab"] = TAB_BOARD
    _render(ctx, state)


def _render_edit_status(ctx, state, frame) -> None:
    status = ctx.config.find_status(state["editing_id"])
    ttk.Label(frame, text="Edit Status" if status else "Add Status", style="Heading.TLabel").pack(anchor="w", pady=(0, 16))

    name_var = tk.StringVar(value=status.name if status else "")
    ttk.Label(frame, text="Name", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Entry(frame, textvariable=name_var, width=30).pack(anchor="w", pady=(0, 12))

    columns = ctx.config.sorted_columns()
    column_names = [c.name for c in columns] + [HIDDEN_SENTINEL]
    current_column = ctx.config.find_column(status.column_id) if status else None
    default_choice = current_column.name if current_column else (HIDDEN_SENTINEL if status else (columns[0].name if columns else HIDDEN_SENTINEL))
    column_var = tk.StringVar(value=default_choice)
    ttk.Label(frame, text="Column", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Combobox(frame, textvariable=column_var, state="readonly", width=28, values=column_names).pack(anchor="w", pady=(0, 16))

    button_row = ttk.Frame(frame)
    button_row.pack(fill="x")

    def cancel() -> None:
        state["sub_mode"] = "overview"
        state["active_tab"] = TAB_BOARD
        _render(ctx, state)

    def save() -> None:
        name = name_var.get().strip()
        if not name:
            show_error_banner(ctx, "Give this status a name.")
            return
        chosen_column = None if column_var.get() == HIDDEN_SENTINEL else next(
            (c for c in ctx.config.columns if c.name == column_var.get()), None,
        )
        if status:
            status.name = name
            status.column_id = chosen_column.id if chosen_column else None
        else:
            ctx.config.statuses.append(cfgmod.Status(name=name, column_id=chosen_column.id if chosen_column else None))
        ctx.save_config()
        show_toast(ctx, "Status saved.")
        state["sub_mode"] = "overview"
        state["active_tab"] = TAB_BOARD
        _render(ctx, state)

    RoundedButton(button_row, text="Cancel", variant="tonal", command=cancel).pack(side="left")
    RoundedButton(button_row, text="Save", variant="filled", command=save).pack(side="right")


# --- Jira tab ----------------------------------------------------------------

def _render_jira_tab(ctx, state, frame) -> None:
    ttk.Label(frame, text="Jira Integration", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Label(
        frame, text="Optional - Issues work fine without this. Sync pulls Jira issues into your local "
                     "list; the board never depends on Jira being reachable.",
        style="Muted.TLabel", wraplength=520,
    ).pack(anchor="w", pady=(0, 10))

    enabled_var = tk.BooleanVar(value=ctx.config.jira.enabled)
    ttk.Checkbutton(frame, text="Enable Jira sync", variable=enabled_var).pack(anchor="w", pady=(0, 4))

    sync_only_visible_var = tk.BooleanVar(value=ctx.config.jira.sync_only_visible_statuses)
    ttk.Checkbutton(
        frame, text="Only sync issues whose status is shown on the board (skip new backlog items)",
        variable=sync_only_visible_var,
    ).pack(anchor="w", pady=(0, 10))

    ttk.Label(frame, text="Jira base URL (e.g. https://yourcompany.atlassian.net)").pack(anchor="w")
    base_url_var = tk.StringVar(value=ctx.config.jira.base_url)
    ttk.Entry(frame, textvariable=base_url_var, width=42).pack(anchor="w", pady=(0, 8))

    ttk.Label(frame, text="Jira account email").pack(anchor="w")
    email_var = tk.StringVar(value=ctx.config.jira.email)
    ttk.Entry(frame, textvariable=email_var, width=42).pack(anchor="w", pady=(0, 8))

    ttk.Label(frame, text="API token").pack(anchor="w")
    existing_token = credential_store.get_secret(_app_dir(), JIRA_TOKEN_SECRET_NAME) or ""
    token_var = tk.StringVar(value=existing_token)
    ttk.Entry(frame, textvariable=token_var, width=42, show="*").pack(anchor="w", pady=(0, 4))
    ttk.Label(
        frame, text="Stored locally via Windows Credential Manager - never written to this shared folder.",
        style="Muted.TLabel",
    ).pack(anchor="w", pady=(0, 12))

    connection_status_label = ttk.Label(frame, text="", style="Muted.TLabel", wraplength=500, justify="left")
    project_lookup = {}  # display string ("KEY - Name") -> (key, name)

    initial_display = ""
    if ctx.config.jira.project_key:
        initial_display = (
            f"{ctx.config.jira.project_key} - {ctx.config.jira.project_name}"
            if ctx.config.jira.project_name else ctx.config.jira.project_key
        )
        project_lookup[initial_display] = (ctx.config.jira.project_key, ctx.config.jira.project_name)
    project_display_var = tk.StringVar(value=initial_display)

    def test_connection() -> None:
        connector = JiraConnector(base_url_var.get().strip(), email_var.get().strip(), token_var.get())
        ok, message = connector.test_connection()
        if not ok:
            connection_status_label.configure(text=f"✗ {message}", foreground=theme.DANGER)
            return
        try:
            projects = connector.list_projects()
            project_lookup.clear()
            display_values = []
            for p in projects:
                display = f"{p.key} - {p.name}" if p.name and p.name != p.key else p.key
                project_lookup[display] = (p.key, p.name)
                display_values.append(display)
            project_combo.configure(values=display_values)
            if display_values and project_display_var.get() not in display_values:
                project_display_var.set(display_values[0])
            connection_status_label.configure(text=f"✓ {message} Found {len(projects)} project(s).", foreground=theme.SUCCESS)
        except Exception as exc:  # noqa: BLE001 - show inline, never crash the settings page
            connection_status_label.configure(text=f"✓ {message} (Couldn't list projects: {exc})", foreground=theme.DANGER)

    RoundedButton(
        frame, text="Test Connection & Load Projects", variant="tonal", command=test_connection,
    ).pack(anchor="w", pady=(0, 4))
    connection_status_label.pack(anchor="w", pady=(0, 12))

    ttk.Label(frame, text="Project").pack(anchor="w")
    project_combo = ttk.Combobox(
        frame, textvariable=project_display_var, state="readonly", width=38,
        values=list(project_lookup.keys()),
    )
    project_combo.pack(anchor="w", pady=(0, 12))

    def save_jira() -> None:
        chosen_display = project_display_var.get()
        if chosen_display in project_lookup:
            key, name = project_lookup[chosen_display]
        else:
            key, name = ctx.config.jira.project_key, ctx.config.jira.project_name
        ctx.config.jira.enabled = enabled_var.get()
        ctx.config.jira.sync_only_visible_statuses = sync_only_visible_var.get()
        ctx.config.jira.base_url = base_url_var.get().strip()
        ctx.config.jira.email = email_var.get().strip()
        ctx.config.jira.project_key = key
        ctx.config.jira.project_name = name
        ctx.save_config()
        credential_store.set_secret(_app_dir(), JIRA_TOKEN_SECRET_NAME, token_var.get())
        show_toast(ctx, "Jira settings saved.")
        state["active_tab"] = TAB_JIRA
        _render(ctx, state)

    RoundedButton(frame, text="Save Jira Settings", variant="filled", command=save_jira).pack(anchor="w", pady=(0, 24))

    ttk.Label(frame, text="Jira Status Mapping", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    if not ctx.config.jira.status_mapping:
        ttk.Label(
            frame, text="No Jira statuses discovered yet - run a sync first, then come back here to review the mapping.",
            style="Muted.TLabel", wraplength=500,
        ).pack(anchor="w", pady=(0, 12))
    else:
        local_status_names = [s.name for s in ctx.config.statuses]
        for jira_status_name, local_status_id in sorted(ctx.config.jira.status_mapping.items()):
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=jira_status_name, width=24).pack(side="left")
            current = ctx.config.find_status(local_status_id)
            mapping_var = tk.StringVar(value=current.name if current else (local_status_names[0] if local_status_names else ""))
            combo = ttk.Combobox(row, textvariable=mapping_var, state="readonly", width=22, values=local_status_names)
            combo.pack(side="left", padx=(8, 0))

            def on_map_change(_event=None, jira_name=jira_status_name, var=mapping_var) -> None:
                match = next((s for s in ctx.config.statuses if s.name == var.get()), None)
                if match:
                    ctx.config.jira.status_mapping[jira_name] = match.id
                    ctx.save_config()
                    show_toast(ctx, f"Mapped '{jira_name}' to {match.name}.")

            combo.bind("<<ComboboxSelected>>", on_map_change)

    if ctx.config.jira.enabled and ctx.config.jira.project_key:
        def sync_now() -> None:
            token = credential_store.get_secret(_app_dir(), JIRA_TOKEN_SECRET_NAME) or ""
            connector = JiraConnector(ctx.config.jira.base_url, ctx.config.jira.email, token)
            try:
                created, updated = jira_sync.sync_from_jira(connector, ctx.config.jira.project_key, ctx.config)
                show_toast(ctx, f"Synced: {created} new issue(s), {updated} updated.")
                state["active_tab"] = TAB_JIRA
                _render(ctx, state)
            except Exception as exc:  # noqa: BLE001 - a failed sync should never crash the app
                show_error_banner(ctx, f"Jira sync failed: {exc}")

        RoundedButton(frame, text="Sync Now", variant="tonal", command=sync_now).pack(anchor="w", pady=(16, 0))
