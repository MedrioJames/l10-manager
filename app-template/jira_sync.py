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
    show it and the user can correct it.

    Also records raw_status into config.jira.known_status_names, additive-
    only and independent of status_mapping - status_mapping's keys can
    shrink (a status's mapped pill being removed in Settings deletes that
    key outright) or simply not get re-seen if that status's issues fall
    outside pull_issues()'s un-paginated 100-issue window on a later sync;
    known_status_names is what keeps that name available in the "add a
    Jira status" picker regardless."""
    if raw_status and raw_status not in config.jira.known_status_names:
        config.jira.known_status_names.append(raw_status)
    mapped = config.jira.status_mapping.get(raw_status)
    if mapped and config.find_status(mapped):
        return mapped
    guessed = _guess_default_status(raw_status, config)
    config.jira.status_mapping[raw_status] = guessed
    return guessed


def reclassify_local_issues(raw_status: str, config: cfgmod.MeetingConfig) -> int:
    """Immediately re-applies config.jira.status_mapping's CURRENT answer for
    raw_status to every already-synced local issue whose cached
    Issue.jira_raw_status matches it - called right after Settings removes
    or reassigns a status-mapping pill, so affected issues update on the
    spot instead of silently keeping their old status until whenever the
    next Sync Now happens to re-pull them. A plain "next sync fixes it" was
    the previous behavior, and a real user rejected it outright ("Issues
    should be updated appropriately when a link is detached") - re-syncing
    isn't just slower, it can genuinely never reach a given issue at all,
    since pull_issues() only fetches the 100 most-recently-updated issues
    with no pagination; an issue that hasn't changed in Jira recently could
    stay stuck forever. This needs no network call at all - jira_raw_status
    is already cached locally from the last real sync, so this is a pure
    local reclassification. Returns how many issues actually changed."""
    new_status_id = map_remote_status(raw_status, config)
    all_issues = iss.load_issues()
    changed = 0
    for issue in all_issues.values():
        if issue.jira_raw_status == raw_status and issue.status != new_status_id:
            issue.status = new_status_id
            changed += 1
    if changed:
        iss.save_issues(all_issues)
    return changed


def reclassify_local_assignees(account_id: str, config: cfgmod.MeetingConfig) -> int:
    """The assignee counterpart to reclassify_local_issues() above, for the
    exact same reason: linking a Person to a Jira account (see
    jira_people_sync.py's confirm/link/create actions) used to have zero
    effect on issues that already synced before the link existed - they'd
    stay unassigned locally until whenever the next Sync Now happened to
    re-pull them, which pull_issues()'s un-paginated 100-issue window might
    never do for an issue that's gone quiet. Every synced issue now caches
    Issue.jira_assignee_account_id regardless of whether it resolved to a
    Person at the time (see sync_from_jira()), so this can immediately
    assign every matching issue to the now-linked Person with no network
    call. Returns how many issues actually changed; 0 (not an error) if
    account_id doesn't resolve to any local Person yet."""
    person = next((p for p in config.people if p.jira_account_id == account_id), None)
    if person is None:
        return 0
    all_issues = iss.load_issues()
    changed = 0
    for issue in all_issues.values():
        if issue.jira_assignee_account_id == account_id and issue.assignee_id != person.id:
            issue.assignee_id = person.id
            changed += 1
    if changed:
        iss.save_issues(all_issues)
    return changed


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
            existing.jira_raw_status = remote.status
            existing.jira_assignee_account_id = remote.assignee_account_id
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
                jira_raw_status=remote.status,
                jira_assignee_account_id=remote.assignee_account_id,
            )
            iss.save_issue(new_issue)
            created += 1

    if config_changed or len(config.jira.status_mapping) != mapping_size_before:
        cfgmod.save_config(config)

    return created, updated
