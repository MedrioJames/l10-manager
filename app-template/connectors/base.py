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
    def pull_issues(self, project_key: str) -> List[RemoteIssue]:
        raise NotImplementedError

    @abstractmethod
    def create_issue(self, project_key: str, title: str, description: str) -> RemoteIssue:
        raise NotImplementedError
