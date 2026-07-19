"""Settings editor - the same meeting-info and repeating-instance fields the
setup wizard collects, but always reachable and editable, not a one-time
flow. Reuses ui/meeting_info_form.py and ui/instance_form.py so the two
stay in sync automatically. Also owns People management and Jira
integration settings.
"""

from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox

import config as cfgmod
import credential_store
import jira_sync
from connectors.jira import JiraConnector
from ui import theme
from ui.meeting_info_form import MeetingInfoForm
from ui.instance_form import RepeatingInstanceForm
from ui.scrollable import ScrollableFrame

JIRA_TOKEN_SECRET_NAME = "jira_api_token"


def _app_dir() -> Path:
    return Path(cfgmod.__file__).resolve().parent


def build(ctx, **kwargs) -> None:
    state = {"mode": "overview", "editing_id": None}
    _render(ctx, state)


def _render(ctx, state) -> None:
    for child in ctx.content.winfo_children():
        child.destroy()

    scroll = ScrollableFrame(ctx.content)
    scroll.pack(fill="both", expand=True)
    frame = ttk.Frame(scroll.body)
    frame.pack(fill="both", expand=True, padx=32, pady=28)

    if state["mode"] == "overview":
        _render_overview(ctx, state, frame)
    elif state["mode"] == "edit_instance":
        _render_edit_instance(ctx, state, frame)
    elif state["mode"] == "edit_person":
        _render_edit_person(ctx, state, frame)


def _render_overview(ctx, state, frame) -> None:
    ttk.Label(frame, text="Settings", style="Heading.TLabel").pack(anchor="w", pady=(0, 16))

    # --- Meeting info ---
    ttk.Label(frame, text="Meeting Info", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 8))
    info_form = MeetingInfoForm(frame, name=ctx.config.meeting.name, description=ctx.config.meeting.description)
    info_form.pack(anchor="w")

    def save_info() -> None:
        data = info_form.get_data()
        ctx.config.meeting = cfgmod.MeetingInfo(name=data["name"], description=data["description"])
        ctx.save_config()
        _render(ctx, state)

    ttk.Button(frame, text="Save Meeting Info", style="Primary.TButton", command=save_info).pack(anchor="w", pady=(10, 28))

    # --- Repeating meetings ---
    ttk.Label(frame, text="Repeating Meetings", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 8))

    if not ctx.config.repeating_instances:
        ttk.Label(frame, text="No repeating meetings yet.", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
    else:
        for instance in ctx.config.repeating_instances:
            row = tk.Frame(frame, background=theme.CARD_BG, highlightbackground=theme.LINE, highlightthickness=1)
            row.pack(fill="x", pady=4)
            info = tk.Frame(row, background=theme.CARD_BG)
            info.pack(side="left", fill="both", expand=True, padx=12, pady=8)
            tk.Label(info, text=instance.name, background=theme.CARD_BG, foreground=theme.INK,
                     font=("Segoe UI", 10, "bold")).pack(anchor="w")
            tk.Label(info, text=f"{instance.recurrence.describe()} - {instance.default_length_minutes} min",
                     background=theme.CARD_BG, foreground=theme.MUTED, font=("Segoe UI", 8)).pack(anchor="w")

            button_box = tk.Frame(row, background=theme.CARD_BG)
            button_box.pack(side="right", padx=8)
            ttk.Button(button_box, text="Edit", style="Secondary.TButton",
                       command=lambda i=instance.id: _goto_edit_instance(ctx, state, i)).pack(side="left", padx=2)
            ttk.Button(button_box, text="Remove", style="Secondary.TButton",
                       command=lambda i=instance.id: _remove_instance(ctx, state, i)).pack(side="left", padx=2)

    ttk.Button(
        frame, text="+ Add a Repeating Meeting", style="Secondary.TButton",
        command=lambda: _goto_edit_instance(ctx, state, None),
    ).pack(anchor="w", pady=(12, 28))

    # --- People ---
    ttk.Label(frame, text="People", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 8))

    if not ctx.config.people:
        ttk.Label(frame, text="No people added yet.", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
    else:
        for person in ctx.config.people:
            row = tk.Frame(frame, background=theme.CARD_BG, highlightbackground=theme.LINE, highlightthickness=1)
            row.pack(fill="x", pady=4)
            info = tk.Frame(row, background=theme.CARD_BG)
            info.pack(side="left", fill="both", expand=True, padx=12, pady=8)
            tk.Label(info, text=person.name, background=theme.CARD_BG, foreground=theme.INK,
                     font=("Segoe UI", 10, "bold")).pack(anchor="w")
            if person.email:
                tk.Label(info, text=person.email, background=theme.CARD_BG,
                         foreground=theme.MUTED, font=("Segoe UI", 8)).pack(anchor="w")

            button_box = tk.Frame(row, background=theme.CARD_BG)
            button_box.pack(side="right", padx=8)
            ttk.Button(button_box, text="Edit", style="Secondary.TButton",
                       command=lambda i=person.id: _goto_edit_person(ctx, state, i)).pack(side="left", padx=2)
            ttk.Button(button_box, text="Remove", style="Secondary.TButton",
                       command=lambda i=person.id: _remove_person(ctx, state, i)).pack(side="left", padx=2)

    ttk.Button(
        frame, text="+ Add Person", style="Secondary.TButton",
        command=lambda: _goto_edit_person(ctx, state, None),
    ).pack(anchor="w", pady=(12, 28))

    # --- Jira integration ---
    _render_jira_section(ctx, state, frame)


def _goto_edit_instance(ctx, state, instance_id) -> None:
    state["mode"] = "edit_instance"
    state["editing_id"] = instance_id
    _render(ctx, state)


def _remove_instance(ctx, state, instance_id) -> None:
    if not messagebox.askyesno("Remove meeting", "Remove this repeating meeting? This can't be undone."):
        return
    ctx.config.repeating_instances = [r for r in ctx.config.repeating_instances if r.id != instance_id]
    ctx.save_config()
    _render(ctx, state)


def _render_edit_instance(ctx, state, frame) -> None:
    instance = ctx.config.find_instance(state["editing_id"])
    title = "Edit Repeating Meeting" if instance else "Add a Repeating Meeting"
    ttk.Label(frame, text=title, style="Heading.TLabel").pack(anchor="w", pady=(0, 16))

    form = RepeatingInstanceForm(frame, templates=ctx.config.schedule_templates, instance=instance)
    form.pack(anchor="w", fill="x")

    button_row = ttk.Frame(frame)
    button_row.pack(fill="x", pady=(20, 0))

    def cancel() -> None:
        state["mode"] = "overview"
        _render(ctx, state)

    def save() -> None:
        try:
            fields = form.get_instance_fields()
        except ValueError as exc:
            messagebox.showerror("Check the recurrence", str(exc))
            return
        if instance:
            instance.name = fields["name"]
            instance.description = fields["description"]
            instance.default_length_minutes = fields["default_length_minutes"]
            instance.schedule_template_id = fields["schedule_template_id"]
            instance.recurrence = fields["recurrence"]
        else:
            ctx.config.repeating_instances.append(cfgmod.RepeatingInstance(
                name=fields["name"],
                description=fields["description"],
                default_length_minutes=fields["default_length_minutes"],
                recurrence=fields["recurrence"],
                schedule_template_id=fields["schedule_template_id"],
            ))
        ctx.save_config()
        state["mode"] = "overview"
        _render(ctx, state)

    ttk.Button(button_row, text="Cancel", style="Secondary.TButton", command=cancel).pack(side="left")
    ttk.Button(button_row, text="Save", style="Primary.TButton", command=save).pack(side="right")


def _goto_edit_person(ctx, state, person_id) -> None:
    state["mode"] = "edit_person"
    state["editing_id"] = person_id
    _render(ctx, state)


def _remove_person(ctx, state, person_id) -> None:
    if not messagebox.askyesno("Remove person", "Remove this person? Any issues assigned to them will show as unassigned."):
        return
    ctx.config.people = [p for p in ctx.config.people if p.id != person_id]
    ctx.save_config()
    _render(ctx, state)


def _render_edit_person(ctx, state, frame) -> None:
    person = ctx.config.find_person(state["editing_id"])
    title = "Edit Person" if person else "Add Person"
    ttk.Label(frame, text=title, style="Heading.TLabel").pack(anchor="w", pady=(0, 16))

    name_var = tk.StringVar(value=person.name if person else "")
    ttk.Label(frame, text="Name", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Entry(frame, textvariable=name_var, width=36).pack(anchor="w", pady=(0, 12))

    email_var = tk.StringVar(value=person.email if person else "")
    ttk.Label(frame, text="Email (optional)", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Entry(frame, textvariable=email_var, width=36).pack(anchor="w", pady=(0, 16))

    button_row = ttk.Frame(frame)
    button_row.pack(fill="x")

    def cancel() -> None:
        state["mode"] = "overview"
        _render(ctx, state)

    def save() -> None:
        name = name_var.get().strip()
        if not name:
            messagebox.showerror("Name required", "Give this person a name.")
            return
        if person:
            person.name = name
            person.email = email_var.get().strip()
        else:
            ctx.config.people.append(cfgmod.Person(name=name, email=email_var.get().strip()))
        ctx.save_config()
        state["mode"] = "overview"
        _render(ctx, state)

    ttk.Button(button_row, text="Cancel", style="Secondary.TButton", command=cancel).pack(side="left")
    ttk.Button(button_row, text="Save", style="Primary.TButton", command=save).pack(side="right")


def _render_jira_section(ctx, state, frame) -> None:
    ttk.Label(frame, text="Jira Integration", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
    ttk.Label(
        frame, text="Optional - Issues work fine without this. Sync pulls Jira issues into your local "
                     "list; the board never depends on Jira being reachable.",
        style="Muted.TLabel", wraplength=520,
    ).pack(anchor="w", pady=(0, 10))

    enabled_var = tk.BooleanVar(value=ctx.config.jira.enabled)
    ttk.Checkbutton(frame, text="Enable Jira sync", variable=enabled_var).pack(anchor="w", pady=(0, 10))

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
    ).pack(anchor="w", pady=(0, 8))

    ttk.Label(frame, text="Project").pack(anchor="w")
    project_key_var = tk.StringVar(value=ctx.config.jira.project_key)
    project_values = [ctx.config.jira.project_key] if ctx.config.jira.project_key else []
    project_combo = ttk.Combobox(frame, textvariable=project_key_var, state="readonly", width=24, values=project_values)
    project_combo.pack(anchor="w", pady=(0, 12))

    def test_connection() -> None:
        connector = JiraConnector(base_url_var.get().strip(), email_var.get().strip(), token_var.get())
        ok, message = connector.test_connection()
        if not ok:
            messagebox.showerror("Jira", message)
            return
        try:
            projects = connector.list_projects()
            project_combo.configure(values=[p.key for p in projects])
            if projects and not project_key_var.get():
                project_key_var.set(projects[0].key)
            messagebox.showinfo("Jira", f"{message} Found {len(projects)} project(s).")
        except Exception as exc:  # noqa: BLE001 - surface to the user rather than crash the app
            messagebox.showwarning("Jira", f"{message} (Couldn't list projects: {exc})")

    ttk.Button(
        frame, text="Test Connection & Load Projects", style="Secondary.TButton", command=test_connection,
    ).pack(anchor="w", pady=(0, 12))

    def save_jira() -> None:
        ctx.config.jira = cfgmod.JiraConfig(
            enabled=enabled_var.get(),
            base_url=base_url_var.get().strip(),
            email=email_var.get().strip(),
            project_key=project_key_var.get().strip(),
        )
        ctx.save_config()
        credential_store.set_secret(_app_dir(), JIRA_TOKEN_SECRET_NAME, token_var.get())
        messagebox.showinfo("Jira", "Jira settings saved.")
        _render(ctx, state)

    ttk.Button(frame, text="Save Jira Settings", style="Primary.TButton", command=save_jira).pack(anchor="w", pady=(0, 12))

    if ctx.config.jira.enabled and ctx.config.jira.project_key:
        def sync_now() -> None:
            token = credential_store.get_secret(_app_dir(), JIRA_TOKEN_SECRET_NAME) or ""
            connector = JiraConnector(ctx.config.jira.base_url, ctx.config.jira.email, token)
            try:
                created, updated = jira_sync.sync_from_jira(connector, ctx.config.jira.project_key, ctx.config)
                messagebox.showinfo("Jira Sync", f"Synced: {created} new issue(s), {updated} updated.")
                _render(ctx, state)
            except Exception as exc:  # noqa: BLE001 - a failed sync should never crash the app
                messagebox.showerror("Jira Sync failed", str(exc))

        ttk.Button(frame, text="Sync Now", style="Secondary.TButton", command=sync_now).pack(anchor="w")
