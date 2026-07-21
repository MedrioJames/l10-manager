"""Glue between a configured IssueConnector and the local issues/people
store. "Sync rather than depend": Jira is only ever consulted when the
user explicitly asks (Test Connection, Sync Now) - the issue board itself
always reads from the local store and never needs Jira reachable.
"""

from typing import Optional, Tuple

import config as cfgmod
import issues as iss
from connectors.base import IssueConnector

# Used only the first time a given raw Jira status name is seen, to seed a
# sensible default entry in config.jira.status_mapping - after that, the
# mapping table (editable in Settings) is what's actually consulted. Jira
# workflow status names are custom per project, so this is necessarily a
# best-effort guess, not an authoritative mapping.
_DEFAULT_GUESS_KEYWORDS = (
    (("done", "closed", "resolved", "complete"), cfgmod.DEFAULT_STATUS_SOLVED_ID),
    (("progress", "review"), cfgmod.DEFAULT_STATUS_IN_PROGRESS_ID),
)


def _guess_default_status(raw_status: str, config: cfgmod.MeetingConfig) -> str:
    lowered = (raw_status or "").lower()
    for keywords, status_id in _DEFAULT_GUESS_KEYWORDS:
        if any(keyword in lowered for keyword in keywords) and config.find_status(status_id):
            return status_id
    if config.find_status(cfgmod.DEFAULT_STATUS_OPEN_ID):
        return cfgmod.DEFAULT_STATUS_OPEN_ID
    return config.statuses[0].id if config.statuses else cfgmod.DEFAULT_STATUS_OPEN_ID


def map_remote_status(raw_status: str, config: cfgmod.MeetingConfig) -> str:
    """Looks up config.jira.status_mapping for this raw Jira status name. If
    it's never been seen before, guesses a default and records that guess
    in the mapping (mutates config.jira.status_mapping) so Settings can
    show it and the user can correct it."""
    mapped = config.jira.status_mapping.get(raw_status)
    if mapped and config.find_status(mapped):
        return mapped
    guessed = _guess_default_status(raw_status, config)
    config.jira.status_mapping[raw_status] = guessed
    return guessed


def _resolve_assignee(config: cfgmod.MeetingConfig, remote) -> Tuple[Optional[cfgmod.Person], bool]:
    """Looks up the local Person for a remote Jira assignee - never
    fabricates one. A routine sync used to silently create a new Person for
    any never-seen assignee, which polluted the People list (and therefore
    meeting assignment) with anyone ever assigned a Jira issue, whether or
    not they're actually on this team - see jira_people_sync.py, which is
    the real (reviewed, explicit) way to reconcile people now.

    Tries Person.jira_account_id first (the stable link set by that review
    flow), then falls back to a silent email match to self-heal a Person who
    was linked by email but not yet by account id. If neither resolves,
    returns None rather than inventing a Person - the local issue's
    assignee_id is simply left unset. Returns (person_or_None, config_changed)."""
    account_id = remote.assignee_account_id
    if account_id:
        existing = next((p for p in config.people if p.jira_account_id == account_id), None)
        if existing:
            return existing, False

    email = remote.assignee_email
    if email:
        existing = next(
            (p for p in config.people if p.email and p.email.lower() == email.lower() and not p.jira_account_id),
            None,
        )
        if existing:
            if account_id:
                existing.jira_account_id = account_id
                return existing, True
            return existing, False

    return None, False


def sync_from_jira(connector: IssueConnector, project_key: str, config: cfgmod.MeetingConfig) -> Tuple[int, int]:
    """Pulls issues from Jira and merges them into the local store, matched
    by external_ref.key. Returns (created_count, updated_count). Purely
    local issues (never linked to Jira) are left untouched."""
    remote_issues = connector.pull_issues(project_key)
    local_issues = iss.load_issues()
    by_jira_key = {
        issue.external_ref.key: issue
        for issue in local_issues.values()
        if issue.external_ref and issue.external_ref.connector == connector.name
    }

    created = 0
    updated = 0
    mapping_size_before = len(config.jira.status_mapping)
    config_changed = False

    for remote in remote_issues:
        assignee, assignee_changed = _resolve_assignee(config, remote)
        if assignee_changed:
            config_changed = True

        external_ref = iss.ExternalRef(connector=connector.name, key=remote.key, url=remote.url)
        existing = by_jira_key.get(remote.key)
        if existing:
            existing.title = remote.title
            existing.description = remote.description
            existing.status = map_remote_status(remote.status, config)
            if assignee is not None:
                existing.assignee_id = assignee.id
            existing.external_ref = external_ref
            iss.save_issue(existing)
            updated += 1
        else:
            status_id = map_remote_status(remote.status, config)
            if config.jira.sync_only_visible_statuses:
                hidden_ids = {s.id for s in config.hidden_statuses()}
                if status_id in hidden_ids:
                    continue
            new_issue = iss.Issue(
                title=remote.title,
                description=remote.description,
                status=status_id,
                assignee_id=assignee.id if assignee else None,
                external_ref=external_ref,
            )
            iss.save_issue(new_issue)
            created += 1

    if config_changed or len(config.jira.status_mapping) != mapping_size_before:
        cfgmod.save_config(config)

    return created, updated
