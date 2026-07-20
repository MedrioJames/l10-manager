# CLAUDE.md

Guidance for Claude Code (or any agent) working in this repository.

## Project

**L10 Manager** — a self-contained tool for prepping, running, and reviewing an EOS/Traction-style **Level 10 Meeting (L10)**. See [docs/L10-CONCEPT.md](docs/L10-CONCEPT.md) for the meeting structure and the vocabulary this project standardizes on (Segue, Scorecard, Rock, Headline, To-Do, Issue, IDS, Conclude). Use those terms — don't invent synonyms.

## This repo is public

**Treat every file here as already public, because it is (or will be).** Never commit:
- Medrio-internal information, business data, or company-confidential content
- Credentials, API keys, tokens, or connection strings — including "read-only" ones
- Real people's personal data beyond what a user explicitly enters into their own local install

If a feature seems to need a secret baked into a shared file, that's a sign to redesign the feature, not to add the secret. (This came up during initial setup — baking a GitHub token into the installer was considered and rejected in favor of just making the repo public, since a token embedded in a widely-shared file gets leaked or auto-revoked the moment it's exposed.)

## Design constraints (v1)

- **Audience**: users with typical computer skills — minimize technical hurdles at every step.
- **One install = one L10.** Each installed folder represents a single team's meeting, so the whole thing can be shared for coverage.
- **Self-contained folder.** Everything an install needs lives in one folder a user can put on Google Drive / OneDrive / Dropbox and share as a unit.
- **Windows-only for now.** Cross-platform is a later phase.
- **stdlib-only for the deployed app** (`app-template/`) — no `pip install` step for end users. Tkinter for UI.
- **No silent/unattended system changes.** Anything that touches the user's machine (installing Python, downloading files, overwriting an existing folder) is explicit and confirmed, never silent.
- **No fileless script evaluation.** Never pipe downloaded content into `iex`/`Invoke-Expression`/`ScriptBlock::Create`, and never `exec()`/`eval()` downloaded Python. Always download to a real file (or read bytes as plain data) and run/dot-source *that file* instead. This isn't just style — Medrio Security flagged the original `irm | iex` one-liner as malware-like behavior, because fileless remote-code execution is one of the most heavily signatured techniques in EDR/AV tooling regardless of what the content actually does. Every download-and-run path in this repo (install.ps1, launcher.ps1, updater.py) follows this rule; keep it that way.

## Architecture

```
install.ps1                  Bootstrapper: builds a new L10 install folder. Downloaded to a real file and
                              run with -File — either via L10-Manager-Setup.bat or the README one-liner.
L10-Manager-Setup.bat        Thin double-click stub — downloads install.ps1 to disk, then runs it with -File.
manifest.json                Declares current app version + the file list install.ps1/updater.py deploy into App/.
app-template/                 Source of truth for everything deployed into a new install's App/ folder.
  l10_manager.py               Entry point: loads config, shows the first-run wizard if not onboarded yet
                                (otherwise the dashboard), builds the File/Help menus, and owns update-checking
                                (auto-check shortly after startup - Update / Wait / Skip This Release - plus
                                Help > Check for Updates... on demand).
  config.py                    Persistence for MeetingConfig (meeting info, RepeatingInstance list, schedule
                                templates) in Data/config.json, and per-occurrence Occurrence records (schedule
                                overrides, one-off meetings, freeform notes) in Data/occurrences.json.
                                upcoming_occurrence_views() and resolve_occurrence_view() combine
                                recurrence-generated dates with any stored customization - most occurrences have
                                no stored record at all until someone customizes or renames one. Also owns the
                                board's Column/Status model: a Status belongs to exactly one Column
                                (column_id=None means "hidden from the board, just counted") and a Column can
                                hold multiple Statuses - dropping a card on a multi-status column prompts the
                                user to disambiguate (see issue_board.py). The four seeded ids
                                (DEFAULT_STATUS_OPEN_ID="open"/IN_PROGRESS_ID="in_progress"/SOLVED_ID="solved"/
                                DROPPED_ID="dropped") are fixed strings so old Data/issues.json records keep
                                resolving without a migration. BoardDisplaySettings holds the three
                                show_status/show_description/show_assignee card-display toggles (Settings >
                                Board). atomic_write_json()/load_json_with_fallback()/DataLoadError are the
                                data-safety layer every save/load in this file (and issues.py) routes through -
                                see "Data-safety" below before touching any read/write path.
  recurrence.py                RecurrenceRule + generate_occurrences() - a small hand-rolled recurrence engine
                                (daily/weekly/monthly/yearly, interval, specific weekdays, "day N" or "Nth
                                <weekday>" for monthly, never/on-date/after-N-occurrences endings). No
                                dateutil/rrule available - stdlib only. Thoroughly unit-tested; if you touch the
                                monthly/weekly iteration logic, re-verify the nth-weekday and month-clamping
                                cases (see git history for the test script) before trusting it.
  schedule.py                   ScheduleTemplate/Section (reusable named agenda blueprints - default_template()
                                is the standard L10 agenda from docs/L10-CONCEPT.md) and SectionOverride/
                                compute_effective_schedule() for per-occurrence customization: skip (section
                                stays listed, marked skipped, so it can be restored - "restore" is just deleting
                                the skip override), adjust (remembers the original duration), add (marked extra).
                                default_template()'s name is just "Standard L10" (no baked-in duration) - anywhere
                                a template is picked or listed, the duration is computed live from
                                ScheduleTemplate.total_minutes and shown separately, so it can't drift out of
                                sync with the actual sections.
  run_state.py                  MeetingRunState - the live meeting-run timer/controller, in-memory only (never
                                written to Data/ - see "Live meeting timer" below). Lives on ui.shell.AppContext
                                as ctx.run_state, since AppContext is the one object every screen receives that
                                survives AppShell.navigate()'s teardown of ctx.content; that's what lets the
                                timer keep ticking no matter what screen the user is on. Ticks via a single
                                root.after(1000, ...) loop using time.monotonic() (never wall-clock), notifying
                                subscribers via add_listener()/remove_listener() rather than touching widgets
                                directly - every UI surface (ui/run_meeting.py, ui/run_indicator.py,
                                ui/presentation.py) subscribes independently and is responsible for guarding its
                                own widget lifetime (check winfo_exists(), unsubscribe on <Destroy>).
  updater.py                   Manifest fetch, version comparison, skip-version prefs, applying updates, and
                                launch_new_install() (downloads install.ps1 to a real temp file and runs it
                                with -File, for "Set Up Another Meeting") - stdlib-only, writes bytes to files,
                                never executes/evals downloaded content.
  issues.py                    Issue dataclass + Data/issues.json persistence - the reusable issue-tracking data
                                layer. `scope` exists so the same board can be reused for a narrower context
                                later (e.g. one meeting's issues) without a data model change; everything today
                                uses DEFAULT_SCOPE. `external_ref` optionally links an issue to a synced Jira
                                issue, but nothing here depends on Jira - status is always a local field.
                                Deliberately doesn't import config.py's Status/Column machinery - `status` is
                                just a string id here; the valid set (and which column each belongs to) lives in
                                MeetingConfig.statuses/columns instead.
  jira_sync.py                  Glue between a connectors.base.IssueConnector and the local issues/people store.
                                map_remote_status() looks up config.jira.status_mapping (raw Jira status name ->
                                local status id, editable in Settings > Jira); the first time a given raw status
                                name is seen it's auto-seeded with a best-effort keyword guess
                                (_guess_default_status/_DEFAULT_GUESS_KEYWORDS) and recorded in the mapping, but
                                once a mapping entry exists - whether auto-seeded or user-corrected - later syncs
                                never overwrite it. sync_from_jira() matches on external_ref.key so re-syncing
                                updates rather than duplicates, and auto-creates People by matching remote
                                assignee email/name.
  credential_store.py          Windows Credential Manager wrapper (ctypes + advapi32.dll) for secrets that must
                                never live in Data/ - see "Secrets" below. Target names are scoped by a hash of
                                the install's own folder path, so multiple installs on one machine don't collide.
  connectors/                  base.py declares IssueConnector (test_connection/list_projects/pull_issues/
                                create_issue) so trackers are interchangeable; jira.py is the only implementation
                                built so far, using the Jira Cloud REST API v3 via urllib (stdlib only). Jira
                                Cloud's `description` field uses Atlassian Document Format (a JSON tree, not a
                                plain string) - see _text_to_adf/_adf_to_text in jira.py before touching it.
                                pull_issues() calls `POST /rest/api/3/search/jql`, not `GET /rest/api/3/search` -
                                the GET endpoint is deprecated and returns `410 Gone` (confirmed against a real
                                Jira Cloud instance, the first part of this connector actually exercised against
                                real Jira rather than just a mock server). Only the first page (100 issues) is
                                fetched - no pagination loop yet, since search/jql uses cursor-based
                                `nextPageToken` pagination, not the old startAt/total scheme.
  ui/                           theme.py (shared ttk palette/styles - reuse PRIMARY/BG/INK/etc. and the
                                Primary.TButton/Secondary.TButton/etc. styles rather than inventing new ones,
                                same palette as templates/README.html; also restyles Vertical.TScrollbar and
                                TNotebook/TNotebook.Tab away from "clam" theme's default grey chrome - every
                                ScrollableFrame/ttk.Notebook picks this up automatically, no per-usage changes
                                needed), shell.py (AppShell: sidebar nav + content area; screens are plain
                                build(ctx, **kwargs) functions in a registry dict, not classes -
                                ctx.navigate()/ctx.config/ctx.save_config() is the whole contract. NAV_ITEMS
                                entries can be ("group", "LABEL") pseudo-entries rendered as a small uppercase
                                label instead of a nav button - purely cosmetic grouping (MEETINGS/TEAM
                                DATA/REVIEW/SETUP), not phase-gating: Scorecard/Rocks/Issues stay always-reachable
                                since they're referenced live during both Prep and Run. AppContext also carries
                                run_state/run_indicator/presentation_window - see run_state.py above), icon_button.py
                                (icon_button() - small flat Unicode-glyph buttons replacing the old repeated
                                text Edit/Delete/Remove button-pair pattern everywhere it showed up; mirrors the
                                "X" dismiss button already in notifications.py), scrollable.py (ScrollableFrame -
                                use it for any screen whose content can exceed the window height; mousewheel
                                binding is Enter/Leave-scoped, not a permanent bind_all, to avoid leaking across
                                screen navigation), dialogs.py (themed ask_text/ask_minutes modals -
                                tkinter.simpledialog isn't themeable; ask_minutes's Spinbox is 1-240 only,
                                positive values - it's for "how long is this section," not a signed adjustment),
                                notifications.py (show_toast/show_error_banner - replaces messagebox popups for
                                anything that isn't a genuine decision the user needs to make: toast for
                                confirmations like "Settings saved", error banner for real failures like a failed
                                Jira sync or an unreadable data file, so raw exception text never lands in an
                                intrusive popup again. Both attach to ctx.root, not ctx.content, so they survive
                                the screen navigation that often follows the same action - the same
                                root-parented/self-rescheduling pattern run_indicator.py and presentation.py
                                build on for a timer that must survive navigation too), people_modal.py
                                (open_people_modal(ctx) - add/edit/delete people all inside one Toplevel modal,
                                inline-editable rows plus an always-visible "Add Person" mini-form pinned at the
                                bottom, replacing the old scroll-down/click-Edit/scroll-back-up round trip
                                through the Settings > People tab, which is now just a summary + a button that
                                opens this modal), wizard.py (first-run setup, skippable at every step),
                                settings.py (a ttk.Notebook sectioned into Meeting & Schedule / People / Board /
                                Jira tabs, rather than one long scroll - each tab keeps its own edit sub-mode and
                                state["active_tab"] tracks which tab a save/cancel rebuild should return to; the
                                Board tab owns Column/Status CRUD and the BoardDisplaySettings checkboxes, the
                                Jira tab owns connection/project setup - Test Connection & Load Projects sits
                                above the project picker and reports status inline, never via messagebox - plus
                                the Jira status-mapping table), dashboard.py (upcoming occurrences + one-off
                                meeting creation), prep.py (effective schedule for one occurrence, plus a "Start
                                Meeting" button that hands off to run_meeting.start_meeting()), schedule_editor.py
                                (skip/restore/adjust/add-extra UI, icon buttons instead of text), schedule_templates.py
                                (template CRUD - Edit/Duplicate/Delete as icon buttons; Duplicate deep-copies with
                                fresh template AND section ids, since section ids are override-targeting keys
                                elsewhere and a copy must not share them), schedule_template_editor.py
                                (build_section_editor() - the section name/duration/drag-reorder/remove list
                                shared by the full Schedules page and the compact open_new_template_modal(), so
                                neither duplicates the drag mechanics; reordering uses the same ghost-Toplevel
                                drag technique as issue_board.py, simplified for a single vertical list - the
                                drag handle is a small glyph on the left of each row, not the whole row, so
                                editing name/duration fields doesn't fight with starting a drag.
                                open_new_template_modal() is the "+ New Template" shortcut reachable from
                                instance_form.py's RepeatingInstanceForm without leaving that form - see below),
                                issue_board.py (the reusable Kanban-style board - build_issue_board(parent, ctx,
                                scope, title) is the entry point; issues.py's nav screen is a two-line wrapper
                                around it - reuse this function directly for any future narrower-scope board
                                rather than forking it. Cards are moved by real drag-and-drop, not arrow buttons:
                                a floating overrideredirect Toplevel "ghost" follows the cursor, a
                                DRAG_THRESHOLD_PX pixel-distance check disambiguates a click (opens the edit
                                dialog - there's no separate Edit button, since a click that isn't a drag already
                                does that) from a drag, and dropping hit-tests the cursor position against each
                                column's bounding box. Columns are grouped, not statuses - if the target column
                                holds more than one Status, _choose_status_dialog asks the user which one they
                                meant. Cards read BoardDisplaySettings to decide whether to render the status
                                badge/description snippet/assignee), issues.py (the nav screen wrapper - name
                                collides with the top-level issues.py data module; both resolve correctly since
                                Python's absolute imports use sys.path, not package-relative lookup, but alias on
                                import if it ever reads ambiguously), placeholders.py (Scorecard/Rocks/Conclude
                                stubs), meeting_info_form.py / instance_form.py / recurrence_widget.py (reusable
                                form widgets shared by the wizard and settings - keep them shared, don't fork.
                                instance_form.py's template combobox shows "Name (X min)", computed live from
                                ScheduleTemplate.total_minutes; its optional on_request_new_template callback
                                (wired by settings.py/wizard.py) opens schedule_template_editor's modal and calls
                                RepeatingInstanceForm.add_template_option() to select the new template in place -
                                the surrounding name/description/length/recurrence fields already typed in are
                                never rebuilt or lost), run_meeting.py (the Run Meeting screen -
                                start_meeting(ctx, view) computes the effective schedule once, filters out
                                skipped sections, builds a run_state.MeetingRunState, mounts run_indicator, and
                                navigates here; the screen itself shows the current section + big countdown,
                                overall time remaining, start/pause, next-section-early (relabels to "End
                                Meeting" on the last section), quick +/-5 min and Custom +/- time adjustment, a
                                clickable agenda list to jump to any section directly, an "Open Presentation
                                Window" button, and a collapsible personal-notes panel saved to
                                Occurrence.notes on <FocusOut>. Refresh only rebuilds the agenda list when
                                current_index actually changes, not on every 1Hz tick), run_indicator.py (the
                                persistent mid-meeting bar - mount(ctx) once when a run starts; parented to
                                ctx.root (not ctx.content) and docked above the content area via place(x=180,
                                relwidth=1.0, width=-180), so it's a sibling of AppShell's container and survives
                                navigate()'s ctx.content-only teardown - this is the mechanism that lets you flip
                                to Issues/Scorecard/Settings mid-meeting without losing the timer. Tears itself
                                down when ctx.run_state.ended), presentation.py (open_presentation(ctx) - the
                                first non-modal, long-lived Toplevel in this codebase; every other Toplevel here
                                is modal and short-lived. No grab_set()/wait_window() - returns immediately,
                                meant to be dragged to a second monitor, reuses the existing window if already
                                open via ctx.presentation_window. WM_DELETE_WINDOW and the refresh listener both
                                guard against the run ending or the window closing out of order).
  launcher.ps1                 What the desktop-folder shortcut runs: status splash, Python check, then
                                launches l10_manager.py. Does NOT check for updates itself - that's owned by
                                the running app (updater.py) so the user isn't prompted twice.
  lib/PythonCheck.ps1          Shared Python-detection/guided-install logic, used by both install.ps1
                                and launcher.ps1 — don't duplicate this logic elsewhere.
assets/l10-manager-icon.ico   Icon for the per-install shortcut. Built from raw 32bpp pixel data written
                              directly into the ICO container (see git history for the generator script) -
                              NOT via Bitmap.GetHicon(), which silently quantizes colors to a 16-color VGA
                              palette. If regenerating, keep using the manual-DIB approach.
templates/README.html         Per-install read-me template (rendered with meeting name/date/version).
```

A finished install looks like:

```
<Chosen Location>/<Meeting Name> L10/
  Start L10 Manager.lnk      Shortcut -> App/launcher.ps1, custom icon
  README.html                 Rendered from templates/README.html
  App/                         Deployed from app-template/ + manifest.json
  Data/                        config.json, occurrences.json, issues.json - never touched by an update. Each
                                gets a same-name .bak snapshot on every save (see "Data-safety" below).
```

## Key rules

- **Update mechanism**: the *running Python app* owns update-checking and applying (see `app-template/updater.py`), comparing local `App/version.txt` to `manifest.json` on GitHub. `launcher.ps1` deliberately does not duplicate this check, to avoid prompting the user twice on every launch. `Data/` is never touched by an update - only files listed in `manifest.json`'s `app_files` get overwritten.
- **Python detection**: always go through `app-template/lib/PythonCheck.ps1`. It must handle the Microsoft Store `python.exe` stub trap and never install anything without an explicit user confirmation.
- **Folder picking in install.ps1**: a real folder-only picker via `IFileOpenDialog` + `FOS_PICKFOLDERS` (COM interop through an inline C# `Add-Type` block) - not `FolderBrowserDialog` (legacy tree view, doesn't surface Quick Access/OneDrive/Google Drive well) and not a repurposed `OpenFileDialog` (confusing "file" affordances, and combining location-pick + name-type in one dialog caused a real double-nesting bug). Picking the location and typing the folder name are two separate steps (native dialog, then a console prompt) - install.ps1 doesn't ask about anything beyond that folder name; deeper meeting setup happens in the wizard, inside the running app. There's a `Read-Host` pause with explanatory text immediately before the picker call (interactive path only) - a first-time user reported the dialog just popping up with no warning was confusing.
- **Data-safety: every save is atomic, every load falls back to a backup, and a genuinely corrupt file is never silently treated as blank.** `config.py`'s `atomic_write_json()` snapshots the current file to `.bak` before writing (only if it currently parses - never snapshot corruption over a good backup), then writes to a `.tmp` sibling and `os.replace()`s it into place - no direct truncate-in-place write, ever. `load_json_with_fallback()` tries the main file, then `.bak`, and raises `DataLoadError` (not a silent blank default) only if both exist and both fail to parse - a missing file (first run) is a completely different, non-error case. This exists because a real user lost a whole `Data/config.json` (a configured repeating meeting vanished) almost certainly from the old direct-write + silent-blank-on-parse-failure combination racing with Google Drive's own sync process on the same folder - the old code would silently swap in a blank in-memory config on any read hiccup, and the *next* save would happily overwrite the real file with that blank data. `l10_manager.py`'s startup wraps `load_config()` in a blocking recovery dialog (explicit "start blank" vs. "quit without changing anything" - never a silent third option); `dashboard.py`/`prep.py`/`schedule_editor.py`/`issue_board.py` catch the same `DataLoadError` for `occurrences.json`/`issues.json` and show an inline error banner instead of crashing. Apply this same atomic-write-plus-fallback pattern to any future file this app persists to `Data/`.
- **The live meeting timer (`run_state.py`) is in-memory only, on purpose.** It is never written to `Data/` - if the app closes mid-meeting, the next launch has no active run and the user starts over from Prep. This was an explicit tradeoff (not an oversight): persisting a live sub-second countdown means either near-continuous disk writes or a fuzzy "how long were we closed" reconciliation problem, on the same Google-Drive-synced folder that already caused the data-loss issue above, for a feature whose worst failure mode is "glance at a phone clock instead." Don't add persistence here without deciding this tradeoff again deliberately.
- **PowerShell empty-array gotcha**: a function that returns a zero-length array (e.g. reading a 0-byte file) gets unrolled to `$null` by PowerShell unless you prefix the return with a comma (`return , $bytes`). `Get-RepoBytes` in install.ps1 hit this for real with `app-template/ui/__init__.py` - keep it non-empty, and keep the comma if you touch that function.
- **Secrets never go in Data/.** `Data/` is designed to be shared with teammates for coverage, so anything in `config.json`/`issues.json` could end up in someone else's hands. The Jira API token is the first real secret in this app and it lives in Windows Credential Manager via `credential_store.py`, never in Data/ - keep this pattern for any future connector credential. This is the same reasoning that killed the "bake a GitHub token into the installer" idea (see above), applied to runtime app secrets instead of build-time ones.
- **The Jira connector is unverified against a real Jira instance.** It was built to the documented Jira Cloud REST API v3 spec and tested thoroughly against a local mock HTTP server (auth headers, ADF description parsing, error handling) plus the sync/merge logic against a mock connector - but no real Jira credentials were available while building it. If something's wrong, it's most likely in Jira-instance-specific details: workflow status names (`jira_sync.map_remote_status`'s keyword matching), custom issue types (`create_issue` hardcodes `"issuetype": {"name": "Task"}`), or ADF edge cases beyond plain paragraphs.
- Full rationale and phase-1 design decisions live in the plan history; ask before assuming scope beyond what's currently built.
