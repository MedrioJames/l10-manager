"""Jira people-matching review - a deliberate, user-reviewed action (the
Settings > Jira tab's "Review Jira People Matches" button), kept separate
from jira_sync.py's automatic routine sync. jira_sync.py never fabricates a
Person for an unrecognized assignee anymore (see its own docstring for why);
this module is where a user actually reconciles the team's local People
against everyone Jira considers assignable on the project, deciding what to
do with anyone left over on either side.

build_match_report() takes a fresh List[RemoteUser] (from
IssueConnector.list_project_members(), a separate/heavier call than the
routine sync) and classifies every remote member and local Person into one
of five buckets:
  - linked: Person.jira_account_id already set and still resolves to a real
    remote member.
  - auto_matched: an unlinked remote member whose email exactly matches an
    unlinked local Person's email - linked immediately, no user action
    ("assume matches when emails match"). NOTE: this is the one bucket that
    is a side effect, not just a classification - build_match_report()
    mutates config.people in place for these pairs. The caller (the modal)
    is responsible for calling ctx.save_config() afterward, same as any
    other config-mutating UI action in this app.
  - potential: a name-only match (no email overlap, but the display names
    match) - needs an explicit confirm/reject from the user, since nicknames
    or coincidental name collisions make this too risky to assume silently.
  - unmatched_remote / unmatched_remote_ignored: remote members with no
    local match, split by whether they're on the "ignored" ledger.
  - unmatched_local / unmatched_local_ignored: local People with no Jira
    link, split by Person.jira_unmatched (the "I looked, they're not on
    Jira" flag).
"""

from dataclasses import dataclass
from typing import List

import config as cfgmod
from connectors.base import RemoteUser


@dataclass
class PersonMatch:
    person: cfgmod.Person
    remote: RemoteUser


@dataclass
class MatchReport:
    linked: List[PersonMatch]
    auto_matched: List[PersonMatch]
    potential: List[PersonMatch]
    unmatched_remote: List[RemoteUser]
    unmatched_remote_ignored: List[RemoteUser]
    unmatched_local: List[cfgmod.Person]
    unmatched_local_ignored: List[cfgmod.Person]


def _normalize_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def build_match_report(remote_members: List[RemoteUser], config: cfgmod.MeetingConfig) -> MatchReport:
    people = config.people
    rejected_pairs = {tuple(pair) for pair in config.jira.rejected_match_pairs}
    ignored_account_ids = set(config.jira.ignored_account_ids)

    claimed_person_ids = set()
    claimed_account_ids = set()

    linked = []
    for person in people:
        if not person.jira_account_id:
            continue
        remote = next((m for m in remote_members if m.account_id == person.jira_account_id), None)
        if remote is not None:
            linked.append(PersonMatch(person=person, remote=remote))
            claimed_person_ids.add(person.id)
            claimed_account_ids.add(remote.account_id)

    auto_matched = []
    for remote in remote_members:
        if remote.account_id in claimed_account_ids or remote.account_id in ignored_account_ids or not remote.email:
            continue
        match = next(
            (p for p in people if p.id not in claimed_person_ids and p.email
             and _normalize_email(p.email) == _normalize_email(remote.email)),
            None,
        )
        if match is not None:
            match.jira_account_id = remote.account_id  # side effect - see docstring
            auto_matched.append(PersonMatch(person=match, remote=remote))
            claimed_person_ids.add(match.id)
            claimed_account_ids.add(remote.account_id)

    potential = []
    for remote in remote_members:
        if remote.account_id in claimed_account_ids or remote.account_id in ignored_account_ids:
            continue
        match = next(
            (p for p in people if p.id not in claimed_person_ids
             and (p.id, remote.account_id) not in rejected_pairs
             and _normalize_name(p.name) == _normalize_name(remote.display_name)),
            None,
        )
        if match is not None:
            potential.append(PersonMatch(person=match, remote=remote))
            claimed_person_ids.add(match.id)
            claimed_account_ids.add(remote.account_id)

    unmatched_remote, unmatched_remote_ignored = [], []
    for remote in remote_members:
        if remote.account_id in claimed_account_ids:
            continue
        (unmatched_remote_ignored if remote.account_id in ignored_account_ids else unmatched_remote).append(remote)

    unmatched_local, unmatched_local_ignored = [], []
    for person in people:
        if person.id in claimed_person_ids or person.jira_account_id:
            continue
        (unmatched_local_ignored if person.jira_unmatched else unmatched_local).append(person)

    return MatchReport(
        linked=linked, auto_matched=auto_matched, potential=potential,
        unmatched_remote=unmatched_remote, unmatched_remote_ignored=unmatched_remote_ignored,
        unmatched_local=unmatched_local, unmatched_local_ignored=unmatched_local_ignored,
    )


# --- Mutating actions - callers save via ctx.save_config() afterward -------

def confirm_potential_match(person: cfgmod.Person, remote: RemoteUser, sync_email: bool = False) -> None:
    person.jira_account_id = remote.account_id
    if sync_email and remote.email:
        person.email = remote.email


def reject_potential_match(config: cfgmod.MeetingConfig, person: cfgmod.Person, remote: RemoteUser) -> None:
    pair = [person.id, remote.account_id]
    if pair not in config.jira.rejected_match_pairs:
        config.jira.rejected_match_pairs.append(pair)


def link_existing_person(person: cfgmod.Person, remote: RemoteUser) -> None:
    person.jira_account_id = remote.account_id


def create_person_from_remote(config: cfgmod.MeetingConfig, remote: RemoteUser) -> cfgmod.Person:
    person = cfgmod.Person(name=remote.display_name, email=remote.email or "", jira_account_id=remote.account_id)
    config.people.append(person)
    return person


def set_remote_ignored(config: cfgmod.MeetingConfig, remote: RemoteUser, ignored: bool = True) -> None:
    ids = config.jira.ignored_account_ids
    if ignored and remote.account_id not in ids:
        ids.append(remote.account_id)
    elif not ignored and remote.account_id in ids:
        ids.remove(remote.account_id)


def set_person_unmatched(person: cfgmod.Person, unmatched: bool = True) -> None:
    person.jira_unmatched = unmatched
