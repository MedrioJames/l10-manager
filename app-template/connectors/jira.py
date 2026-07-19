"""Jira Cloud connector - implements connectors.base.IssueConnector using
the Jira Cloud REST API v3 via urllib (stdlib only, no `requests`).

NOTE: this has been built carefully to the documented Jira Cloud REST API
v3 spec, but there is no real Jira instance available to test it against
in the environment this was built in. Treat it as "should work" rather
than "verified" until you've run it against your actual Jira - especially
create_issue()'s Atlassian Document Format handling and the status-name
mapping in jira_sync.py, since those are the most Jira-instance-specific
parts (custom workflows/issue types can vary between projects).

Auth is HTTP Basic with an account email + API token (the standard way to
authenticate to Jira Cloud - see id.atlassian.com/manage-profile/security/api-tokens).
The token itself is never handled here - callers pass it in per-request;
see credential_store.py for where it actually lives.
"""

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Tuple

from connectors.base import IssueConnector, RemoteIssue, RemoteProject

REQUEST_TIMEOUT_SECONDS = 15


def _text_to_adf(text: str) -> dict:
    """Wraps plain text in the minimal Atlassian Document Format Jira Cloud
    v3 requires for the `description` field - a bare string is rejected."""
    paragraphs = text.split("\n") if text else [""]
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": line}]} if line else {"type": "paragraph"}
            for line in paragraphs
        ],
    }


def _adf_to_text(adf) -> str:
    """Flattens an Atlassian Document Format value back to plain text.
    Jira Cloud v3 returns `description` in this shape, not as a string."""
    if adf is None:
        return ""
    if isinstance(adf, str):
        return adf

    lines = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "text":
                lines.append(node.get("text", ""))
            for child in node.get("content", []) or []:
                walk(child)
            if node.get("type") == "paragraph":
                lines.append("\n")
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(adf.get("content", []))
    return "".join(lines).strip()


class JiraConnector(IssueConnector):
    name = "jira"
    display_name = "Jira"

    def __init__(self, base_url: str, email: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.api_token = api_token

    def _auth_header(self) -> str:
        raw = f"{self.email}:{self.api_token}".encode("utf-8")
        return "Basic " + base64.b64encode(raw).decode("ascii")

    def _request(self, method: str, path: str, body: dict = None):
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", self._auth_header())
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}

    def test_connection(self) -> Tuple[bool, str]:
        try:
            me = self._request("GET", "/rest/api/3/myself")
            display_name = me.get("displayName", self.email)
            return True, f"Connected as {display_name}."
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                return False, "Authentication failed - check the email and API token."
            return False, f"Jira returned an error (HTTP {exc.code})."
        except urllib.error.URLError as exc:
            return False, f"Couldn't reach {self.base_url} ({exc.reason})."
        except Exception as exc:  # noqa: BLE001 - surface anything unexpected to the user, not a crash
            return False, f"Unexpected error: {exc}"

    def list_projects(self) -> List[RemoteProject]:
        data = self._request("GET", "/rest/api/3/project/search?maxResults=100")
        return [RemoteProject(key=p["key"], name=p.get("name", p["key"])) for p in data.get("values", [])]

    def pull_issues(self, project_key: str) -> List[RemoteIssue]:
        jql = urllib.parse.quote(f"project={project_key} ORDER BY updated DESC")
        fields = "summary,description,status,assignee"
        path = f"/rest/api/3/search?jql={jql}&maxResults=100&fields={fields}"
        data = self._request("GET", path)

        results = []
        for raw_issue in data.get("issues", []):
            issue_fields = raw_issue.get("fields", {})
            assignee = issue_fields.get("assignee") or {}
            status = issue_fields.get("status", {}).get("name", "")
            results.append(RemoteIssue(
                key=raw_issue["key"],
                title=issue_fields.get("summary", ""),
                description=_adf_to_text(issue_fields.get("description")),
                status=status,
                url=f"{self.base_url}/browse/{raw_issue['key']}",
                assignee_email=assignee.get("emailAddress"),
                assignee_name=assignee.get("displayName"),
            ))
        return results

    def create_issue(self, project_key: str, title: str, description: str) -> RemoteIssue:
        body = {
            "fields": {
                "project": {"key": project_key},
                "summary": title,
                "description": _text_to_adf(description),
                "issuetype": {"name": "Task"},
            }
        }
        created = self._request("POST", "/rest/api/3/issue", body=body)
        key = created["key"]
        return RemoteIssue(
            key=key,
            title=title,
            description=description,
            status="",
            url=f"{self.base_url}/browse/{key}",
        )
