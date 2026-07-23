"""Issue tracking - the data layer behind the visual, reusable issue board.

Issues live in Data/issues.json, separate from config.json since they
change far more often. Status is always a local field the user controls
directly; an optional `external_ref` links an issue to a synced Jira
issue, but Jira is never a dependency - everything here works with zero
Jira configuration. `scope` exists so the same board can be reused for a
narrower context later (e.g. one meeting's issues) without a data model
change - for now every issue just uses the default "general" scope.

Status ids are just strings here on purpose - the set of valid statuses
(and which board column each belongs to) is user-configurable, defined in
config.py's Status/Column and MeetingConfig.statuses/columns, not in this
module. "open" is the default id, matching config.DEFAULT_STATUS_OPEN_ID,
so a fresh Issue lines up with the default seeded statuses without this
module needing to import config's status/column machinery at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import config as cfgmod
import schedule as sch

ISSUES_FILENAME = "issues.json"
DEFAULT_SCOPE = "general"
DEFAULT_STATUS_ID = "open"


def _issues_path() -> Path:
    return cfgmod.data_dir() / ISSUES_FILENAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ExternalRef:
    connector: str  # e.g. "jira" - matches an IssueConnector.name
    key: str  # e.g. "PROJ-123"
    url: str = ""

    def to_dict(self) -> dict:
        return {"connector": self.connector, "key": self.key, "url": self.url}

    @staticmethod
    def from_dict(d: dict) -> "ExternalRef":
        return ExternalRef(connector=d.get("connector", ""), key=d.get("key", ""), url=d.get("url", ""))


@dataclass
class Issue:
    id: str = field(default_factory=sch.new_id)
    title: str = ""
    description: str = ""
    status: str = DEFAULT_STATUS_ID
    assignee_id: Optional[str] = None
    scope: str = DEFAULT_SCOPE
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    external_ref: Optional[ExternalRef] = None
    # The raw Jira status name this issue had as of its last sync (e.g.
    # "Completed") - None for a purely local issue. Cached here specifically
    # so that changing a status mapping in Settings (removing or
    # reassigning a pill) can immediately reclassify every affected issue
    # offline, via jira_sync.reclassify_local_issues() - without this,
    # there'd be no way to find "every issue that came from raw status X"
    # short of re-querying Jira, which pull_issues()'s un-paginated 100-
    # issue window might not even reach for an issue that hasn't changed
    # recently.
    jira_raw_status: Optional[str] = None
    # The raw Jira assignee account id this issue had as of its last sync -
    # None for a purely local issue, or a synced issue whose assignee Jira
    # reports as unassigned. Same reasoning as jira_raw_status above, applied
    # to assignee: without a cached raw identifier, linking a Person to Jira
    # later (see jira_people_sync.py) has no way to find "every issue Jira
    # already said belongs to this account" short of a fresh sync reaching
    # it again.
    jira_assignee_account_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "assignee_id": self.assignee_id,
            "scope": self.scope,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "external_ref": self.external_ref.to_dict() if self.external_ref else None,
            "jira_raw_status": self.jira_raw_status,
            "jira_assignee_account_id": self.jira_assignee_account_id,
        }

    @staticmethod
    def from_dict(d: dict) -> "Issue":
        return Issue(
            id=d.get("id", sch.new_id()),
            title=d.get("title", ""),
            description=d.get("description", ""),
            status=d.get("status", DEFAULT_STATUS_ID),
            assignee_id=d.get("assignee_id"),
            scope=d.get("scope", DEFAULT_SCOPE),
            created_at=d.get("created_at") or _now_iso(),
            updated_at=d.get("updated_at") or _now_iso(),
            external_ref=ExternalRef.from_dict(d["external_ref"]) if d.get("external_ref") else None,
            jira_raw_status=d.get("jira_raw_status"),
            jira_assignee_account_id=d.get("jira_assignee_account_id"),
        )


def load_issues() -> Dict[str, Issue]:
    data = cfgmod.load_json_with_fallback(_issues_path())
    if data is None:
        return {}
    try:
        return {key: Issue.from_dict(value) for key, value in data.items()}
    except (ValueError, KeyError) as exc:
        raise cfgmod.DataLoadError(_issues_path()) from exc


def save_issues(issues: Dict[str, Issue]) -> None:
    payload = {key: issue.to_dict() for key, issue in issues.items()}
    cfgmod.atomic_write_json(_issues_path(), payload)


def save_issue(issue: Issue) -> None:
    issues = load_issues()
    issue.updated_at = _now_iso()
    issues[issue.id] = issue
    save_issues(issues)


def delete_issue(issue_id: str) -> None:
    issues = load_issues()
    if issue_id in issues:
        del issues[issue_id]
        save_issues(issues)


def get_issue(issue_id: str) -> Optional[Issue]:
    return load_issues().get(issue_id)


def list_issues(scope: Optional[str] = None) -> List[Issue]:
    """All issues, optionally filtered to one scope, sorted by creation
    date. Status/column-aware grouping happens in ui/issue_board.py, which
    has access to the user's configured statuses/columns - this module
    doesn't, by design."""
    issues = list(load_issues().values())
    if scope is not None:
        issues = [i for i in issues if i.scope == scope]
    issues.sort(key=lambda i: i.created_at)
    return issues
