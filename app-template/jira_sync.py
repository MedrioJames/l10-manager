"""Glue between a configured IssueConnector and the local issues/people
store. "Sync rather than depend": Jira is only ever consulted when the
user explicitly asks (Test Connection, Sync Now) - the issue board itself
always reads from the local store and never needs Jira reachable.
"""

from typing import Optional, Tuple

import config as cfgmod
import issues as iss
from connectors.base import IssueConnector

# Jira workflow status names vary per project/instance (custom workflows),
# so this is a best-effort keyword match rather than an exact lookup.
_STATUS_KEYWORDS = {
    iss.STATUS_SOLVED: ("done", "closed", "resolved"),
    iss.STATUS_IN_PROGRESS: ("progress", "review"),
}


def map_remote_status(raw_status: str) -> str:
    lowered = (raw_status or "").lower()
    for local_status, keywords in _STATUS_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return local_status
    return iss.STATUS_OPEN


def _find_or_create_person(config: cfgmod.MeetingConfig, email: str, name: str) -> Optional[cfgmod.Person]:
    if not email and not name:
        return None
    if email:
        existing = next((p for p in config.people if p.email and p.email.lower() == email.lower()), None)
        if existing:
            return existing
    if name:
        existing = next((p for p in config.people if p.name == name), None)
        if existing:
            return existing
    if not name:
        return None
    person = cfgmod.Person(name=name, email=email or "")
    config.people.append(person)
    return person


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
    config_changed = False

    for remote in remote_issues:
        assignee = None
        if remote.assignee_email or remote.assignee_name:
            assignee = _find_or_create_person(config, remote.assignee_email or "", remote.assignee_name or "")
            if assignee is not None:
                config_changed = True

        external_ref = iss.ExternalRef(connector=connector.name, key=remote.key, url=remote.url)
        existing = by_jira_key.get(remote.key)
        if existing:
            existing.title = remote.title
            existing.description = remote.description
            existing.status = map_remote_status(remote.status)
            if assignee is not None:
                existing.assignee_id = assignee.id
            existing.external_ref = external_ref
            iss.save_issue(existing)
            updated += 1
        else:
            new_issue = iss.Issue(
                title=remote.title,
                description=remote.description,
                status=map_remote_status(remote.status),
                assignee_id=assignee.id if assignee else None,
                external_ref=external_ref,
            )
            iss.save_issue(new_issue)
            created += 1

    if config_changed:
        cfgmod.save_config(config)

    return created, updated
