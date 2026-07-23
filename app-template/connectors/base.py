"""Abstract interface for third-party issue-tracker connectors.

The issues system never talks to Jira (or any tracker) directly - it only
goes through this interface, so a different connector (Asana, Linear,
whatever comes next) could be swapped in later without touching the issue
board or data model at all. Jira (jira.py) is the only one built so far.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class RemoteProject:
    key: str
    name: str


@dataclass
class RemoteIssue:
    key: str
    title: str
    description: str
    status: str  # the tracker's own raw status name (e.g. "In Progress") - callers map this to a local status
    url: str
    assignee_email: Optional[str] = None
    assignee_name: Optional[str] = None
    assignee_account_id: Optional[str] = None


@dataclass
class RemoteUser:
    """A member of a remote project - used for the Jira people-matching
    review (see jira_people_sync.py), not the routine issue sync itself.
    account_id is the stable, GDPR-safe identifier (Jira orgs can hide
    email addresses entirely depending on privacy settings, so email is
    optional and best-effort only)."""

    account_id: str
    display_name: str
    email: Optional[str] = None


class IssueConnector(ABC):
    """One instance = one configured connection to one external tracker."""

    name: str = "base"
    display_name: str = "Base Connector"

    @abstractmethod
    def test_connection(self) -> Tuple[bool, str]:
        """Returns (ok, message) - message is shown to the user either way."""
        raise NotImplementedError

    @abstractmethod
    def list_projects(self) -> List[RemoteProject]:
        raise NotImplementedError

    @abstractmethod
    def pull_issues(self, project_key: str, full: bool = False) -> List[RemoteIssue]:
        """By default (full=False) fetches only the most-recently-updated
        page of issues - fast, fine for a routine Sync Now, but means an
        issue that's gone quiet in Jira may never get re-pulled. full=True
        pages through every issue in the project instead - slower, meant
        for an explicit "Sync All Issues" action, not routine use, since a
        large project could mean many requests."""
        raise NotImplementedError

    @abstractmethod
    def create_issue(self, project_key: str, title: str, description: str) -> RemoteIssue:
        raise NotImplementedError

    @abstractmethod
    def list_project_members(self, project_key: str) -> List[RemoteUser]:
        """Everyone assignable on this project - used only for the explicit
        "Review Jira People Matches" flow, never during a routine sync."""
        raise NotImplementedError
