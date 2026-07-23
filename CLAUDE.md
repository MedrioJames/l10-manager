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
                                (auto-check shortly after startup - Update / Wait / Skip This Release, then
                                show_update_progress_dialog(), then after a successful apply_update() a separate
                                Restart Now / Restart Later dialog rather than an unconditional restart-after-OK
                                popup - Restart Later just closes the dialog, since the files are already updated
                                on disk and the current process can keep running until the next natural launch -
                                plus Help > Check for Updates... on demand). show_update_progress_dialog() runs
                                updater.apply_update() on a background thread with a determinate ttk.Progressbar
                                (one tick per manifest file, via apply_update()'s on_progress callback) -
                                replaces the old behavior of calling apply_update() directly on the Tk main
                                thread, which blocked the whole UI with no feedback for as long as the download
                                took (a real user asked for this after seeing what looked like a frozen app).
                                Deliberately does NOT withdraw/hide or grab_set() the main window while
                                downloading - the files being replaced are the app's own on-disk source, and
                                Python never reloads already-imported modules from disk on its own, so there's
                                nothing unsafe about staying fully open and usable during the download (same
                                reason "Restart Later" already safely lets the old process keep running
                                post-update) - a real user asked for this specifically after an earlier version
                                hid the main window during the download. Progress ticks are marshaled back to
                                the main thread via root.after(0, ...), since the download thread must never
                                touch a Tkinter widget directly - this requires the main thread to genuinely be
                                inside root.mainloop() when the callback fires (confirmed via a real "main
                                thread is not in main loop" RuntimeError the one time this was tested with
                                manual root.update() polling instead of mainloop() - a real production run is
                                unaffected, since main() always calls mainloop()). show_restart_dialog() sets a
                                real WM_DELETE_WINDOW handler (falls back to Restart Later) instead of leaving
                                the close button unhandled - a real user reported the app appearing to just
                                vanish after an update, traced to this dialog being the one place in the update
                                flow that hadn't gotten a close-button handler. main() also calls
                                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MedrioJames.
                                L10Manager") before creating the root Tk window - without this, Windows'
                                taskbar shows pythonw.exe/python.exe's own icon for the running window instead
                                of root.iconbitmap()'s icon, since launcher.ps1 runs this script directly via
                                the system Python interpreter and Windows normally groups/icons a window by its
                                HOST EXECUTABLE's identity unless the process claims a distinct
                                AppUserModelID of its own - a real user asked why the taskbar showed a Python
                                logo instead of the L10 icon. Must be set before any window is created; wrapped
                                in a try/except (AttributeError, OSError) since it's purely cosmetic if it fails.
  config.py                    Persistence for MeetingConfig (meeting info, RepeatingInstance list, the global
                                Segment library, and Schedules built from it - see schedule.py) in
                                Data/config.json, and per-occurrence Occurrence records (schedule overrides,
                                one-off meetings, freeform notes, Conclude's ratings dict + cascading_message -
                                see segment_types.py) in Data/occurrences.json. get_or_create_occurrence(config,
                                occurrence_key, view=None) is the one shared get-or-create helper every writer of
                                per-occurrence data (notes, schedule assignment, Conclude's save) now goes
                                through, instead of three near-identical copies of the same
                                get-then-build-from-resolved-view pattern. upcoming_occurrence_views() and
                                resolve_occurrence_view() combine recurrence-generated dates with any stored
                                customization - most occurrences have no stored record at all until someone
                                customizes or renames one; ui/review.py calls the same underlying
                                recurrence.generate_occurrences() with a historical range instead (rule.start_date
                                through today) to find *past* occurrences - no separate backward-looking function
                                needed. Also owns the board's Column/Status model: a Status belongs to exactly
                                one Column (column_id=None means "hidden from the board, just counted") and a
                                Column can hold multiple Statuses - dropping a card on a multi-status column
                                prompts the user to disambiguate (see issue_board.py). Status.is_closed
                                distinguishes "hidden but still an active backlog item" from "hidden because
                                terminal" (only the seeded "Dropped" status defaults to is_closed=True) - used by
                                MeetingConfig.backlog_statuses() (hidden_statuses() minus is_closed ones) for the
                                Backlog view. JiraConfig.sync_only_visible_statuses (Settings > Jira) makes
                                jira_sync.sync_from_jira() skip creating brand-new local issues whose mapped
                                status is hidden. The four seeded ids
                                (DEFAULT_STATUS_OPEN_ID="open"/IN_PROGRESS_ID="in_progress"/SOLVED_ID="solved"/
                                DROPPED_ID="dropped") are fixed strings so old Data/issues.json records keep
                                resolving without a migration. BoardDisplaySettings holds the three
                                show_status/show_description/show_assignee card-display toggles (Settings >
                                Board). atomic_write_json()/load_json_with_fallback()/DataLoadError are the
                                data-safety layer every save/load in this file (issues.py, and now todos.py)
                                routes through - see "Data-safety" below before touching any read/write path.
                                atomic_write_json()'s final os.replace() retries a few times with a short backoff
                                on OSError before giving up - a real user hit `[WinError 5] Access is denied` on
                                a Jira sync, almost certainly Google Drive Desktop transiently locking the
                                destination file mid-sync; this is the standard mitigation for atomic replace on
                                a cloud-synced folder, not a sign the underlying approach was wrong.
                                Person.jira_unmatched and JiraConfig.ignored_account_ids/rejected_match_pairs are
                                additive fields for the Jira people-matching review (see jira_people_sync.py) -
                                all three are just "don't ask again" ledgers, not sync-affecting on their own.
  recurrence.py                RecurrenceRule + generate_occurrences() - a small hand-rolled recurrence engine
                                (daily/weekly/monthly/yearly, interval, specific weekdays, "day N" or "Nth
                                <weekday>" for monthly, never/on-date/after-N-occurrences endings). No
                                dateutil/rrule available - stdlib only. Thoroughly unit-tested; if you touch the
                                monthly/weekly iteration logic, re-verify the nth-weekday and month-clamping
                                cases (see git history for the test script) before trusting it.
  schedule.py                   Segment (a globally-defined, reusable, named building block - name, type_id,
                                duration, and a `config` dict of whatever its type needs - see segment_types.py)
                                and Schedule (renamed from ScheduleTemplate - just an ordered list of
                                ScheduleSegmentEntry, each referencing a Segment by id and optionally
                                overriding its name/duration/config for that schedule). SegmentOverride
                                (renamed/generalized from SectionOverride) is the occurrence-level layer on top
                                of that - skip (entry stays listed, marked skipped, so it can be restored -
                                "restore" is just deleting the skip override), adjust (remembers the
                                entry-resolved duration as "original", not the segment's raw default), add
                                (references a Segment from the library, not an inline freeform value).
                                compute_effective_schedule(schedule, segments, overrides) resolves the full
                                two-step cascade - global Segment -> Schedule entry override -> occurrence
                                override, the same fallthrough shape at each step - into EffectiveSegment
                                (renamed/expanded from EffectiveSection, now carrying type_id + the fully
                                resolved config dict so the Run screen/presentation window can dispatch to the
                                right type's rendering). default_segments()/default_schedule() seed the 7
                                standard L10 segments with fixed (non-random) ids, matching config.py's
                                DEFAULT_STATUS_*_ID convention - To-Do/IDS/Conclude now use type_id "todo"/"ids"/
                                "conclude" (were all "generic" before those types gained real behavior - see
                                segment_types.py); the ids themselves (TODO_ID/IDS_ID/CONCLUDE_ID) didn't change,
                                so existing Data/config.json segments just pick up the new behavior with no
                                migration. Schedule has no bare .total_minutes anymore
                                (resolving one now needs the segment library) - use schedule_total_minutes()
                                instead, or schedule_display_items() for the duck-typed id/name/total_minutes
                                wrappers ui/instance_form.py needs (see below).
  segment_types.py               SegmentType - the extensible catalog of segment "kinds." One class per type is
                                everything needed: a Config dataclass (None means no config at all - the
                                "generic" type, today's plain-segment equivalent) defining what's configurable,
                                plus render_settings_form()/render_run_view()/render_presentation_view() -
                                "write the class, you have what you need," no other file has to change to add a
                                type. render_run_view()/render_presentation_view() take a third `ctx` argument
                                (widened from just (parent, effective_segment) once To-Do/IDS/Conclude needed
                                real behavior - reaching ctx.config/ctx.run_state, the issues/todos stores, etc.
                                - a safe mechanical widen since none of the 5 original built-ins override either
                                method). The base class's render_settings_form() auto-generates a form by
                                reflecting on Config's dataclass fields (bool->Checkbutton, str->Entry,
                                int->Spinbox, List[str]->a small add/remove row-list) - a type only needs custom
                                UI code if it wants something that doesn't fit that reflection. Built-in types:
                                generic (no config), headlines (show_people), core_values (values: List[str] -
                                the actual list, since that's genuinely static/global), rocks (show_owner),
                                scorecard (show_trend_arrows) - Rocks/Scorecard configs are deliberately
                                display-setting-only, since real rock/scorecard data doesn't exist as a feature
                                yet (ui/placeholders.py stubs, currently unwired from nav). To-Do/IDS/Conclude are
                                the first types with real render_run_view() behavior, not just a Config: todo
                                shows not-done todos.py Todos for the current occurrence's repeating_instance_id
                                (resolved via cfgmod.resolve_occurrence_view) with a checkbox to mark done and an
                                inline add-form; ids shows a compact open/in-progress issues.py list (not the
                                full drag-and-drop Kanban board - too heavy embedded here) with quick
                                solve/drop icon-button actions via ui/issue_board.py's set_issue_status()/
                                open_issue_dialog() (both now public, not underscore-private, since this module
                                is a second caller); conclude renders a 1-10 rating Spinbox per ctx.config.people
                                plus a cascading-message Text box, saved via cfgmod.get_or_create_occurrence()
                                into Occurrence.ratings/cascading_message - render_presentation_view() for
                                conclude is a static "Rate the meeting 1-10!" prompt (no input - the
                                presentation window is display-only by design). SEGMENT_TYPES registry +
                                get_segment_type() (falls back to generic for an unknown type_id). Deliberately
                                imports tkinter/ui.icon_button/ui.rounded_button directly at module level (not
                                layered as "pure data" the way schedule.py is) - that's the whole point of this
                                module owning its own rendering. config.py/issues.py/todos.py are deliberately
                                NOT imported at module level, though - schedule.py already imports segment_types
                                (for get_segment_type()), and config.py/issues.py/todos.py all import schedule.py
                                (for schedule.new_id()), so a module-level import here would complete the cycle
                                and fail with "partially initialized module" at startup. They're imported inside
                                the functions that need them instead (same "import deferred to call time" trick
                                already used for `from ui import issue_board` here, just applied more broadly
                                now) - keep this pattern if you add more real behavior to a type.
  run_state.py                  MeetingRunState - the live meeting-run timer/controller, in-memory only (never
                                written to Data/ - see "Live meeting timer" below). Lives on ui.shell.AppContext
                                as ctx.run_state, since AppContext is the one object every screen receives that
                                survives AppShell.navigate()'s teardown of ctx.content; that's what lets the
                                timer keep ticking no matter what screen the user is on. Ticks via a single
                                root.after(1000, ...) loop using time.monotonic() (never wall-clock), notifying
                                subscribers via add_listener()/remove_listener() rather than touching widgets
                                directly - every UI surface (ui/run_meeting.py, ui/run_indicator.py,
                                ui/presentation.py) subscribes independently and is responsible for guarding its
                                own widget lifetime (check winfo_exists(), unsubscribe on <Destroy>). Its public
                                surface uses "segment" vocabulary throughout (segments, current_segment,
                                jump_to_segment(), segment_remaining_seconds, segment_over_time,
                                is_last_segment, adjust_segment_time()) - "section" was fully retired from this
                                app when the Segment/Schedule model replaced Section/ScheduleTemplate.
                                elapsed_seconds is a separate wall-clock tracker (_started_monotonic set at
                                __init__, _ended_monotonic set in stop()) purely for ui/meeting_complete.py's
                                summary - deliberately not derived from overall_remaining_seconds, since that
                                value gets mutated by the +/-time adjustment controls and no longer reflects real
                                elapsed time once a user has used them.
  updater.py                   Manifest fetch, version comparison, skip-version prefs, applying updates, and
                                launch_new_install() (downloads install.ps1 to a real temp file and runs it
                                with -File, for "Set Up Another Meeting") - stdlib-only, writes bytes to files,
                                never executes/evals downloaded content. apply_update(manifest, on_progress=None)
                                calls on_progress(completed_count, total_count, filename) after each file finishes
                                downloading - purely a data callback, no threading/Tkinter awareness here; see
                                l10_manager.py's show_update_progress_dialog() for the caller that runs this on a
                                background thread and marshals ticks onto a progress bar. is_dev_checkout()
                                (a sibling .git folder exists) gates both check_for_update() (returns None
                                silently) and apply_update() (raises) - a real deployed install is never a git
                                working tree, but app-template/ always is, and local_version() defaults to
                                "0.0.0" with no version.txt (true of a fresh checkout), so running
                                l10_manager.py directly from app-template/ during development looks exactly
                                like a brand-new install on an ancient version. Without this guard the
                                auto-updater treats it as exactly that and genuinely overwrites the dev
                                checkout's own source files with whatever's published on GitHub - this happened
                                for real during development and clobbered uncommitted local changes.
  issues.py                    Issue dataclass + Data/issues.json persistence - the reusable issue-tracking data
                                layer. `scope` exists so the same board can be reused for a narrower context
                                later (e.g. one meeting's issues) without a data model change; everything today
                                uses DEFAULT_SCOPE. `external_ref` optionally links an issue to a synced Jira
                                issue, but nothing here depends on Jira - status is always a local field.
                                Deliberately doesn't import config.py's Status/Column machinery - `status` is
                                just a string id here; the valid set (and which column each belongs to) lives in
                                MeetingConfig.statuses/columns instead.
  todos.py                      Todo dataclass + Data/todos.json persistence, mirroring issues.py's exact
                                shape/pattern (same atomic_write_json/load_json_with_fallback, same
                                load/save/delete/list function shapes) - the data layer behind
                                segment_types.py's TodoType. Deliberately minimal (title, assignee_id,
                                repeating_instance_id, done - no due dates, no priority), matching EOS's own
                                practice. Todos carry forward automatically every week until marked done
                                (list_todos(repeating_instance_id, include_done=False) - not scoped to "only
                                last week's") rather than being tied to a specific past occurrence - this avoids
                                needing to resolve "the previous occurrence" of a repeating instance, which
                                nothing in this app does today (see config.py's get_or_create_occurrence /
                                ui/review.py's historical recurrence.generate_occurrences() call for the one
                                place that DOES need a past date, which uses a different approach).
  jira_sync.py                  Glue between a connectors.base.IssueConnector and the local issues/people store.
                                map_remote_status() looks up config.jira.status_mapping (raw Jira status name ->
                                local status id, editable in Settings > Jira); the first time a given raw status
                                name is seen it's auto-seeded with a best-effort keyword guess
                                (_guess_default_status/_DEFAULT_GUESS_KEYWORDS - the Solved bucket matches
                                "done"/"closed"/"resolved"/"complete" as substrings, the last one added after a
                                real project's Jira status was literally named "Completed," which contains none
                                of the other three and was defaulting new syncs straight into Open) and recorded
                                in the mapping, but once a mapping entry exists - whether auto-seeded or
                                user-corrected - later syncs never overwrite it. sync_from_jira() matches on
                                external_ref.key so re-syncing
                                updates rather than duplicates. _resolve_assignee() NEVER fabricates a Person
                                (replaces the old _find_or_create_person, which auto-created a local Person for
                                any never-seen Jira assignee with zero confirmation - a real user found this
                                polluted their People list, and therefore meeting assignment, with people who
                                have nothing to do with this team). It only looks up Person.jira_account_id, or
                                self-heals an unlinked Person via a silent exact-email match (setting
                                jira_account_id once found) - otherwise the local issue's assignee_id is simply
                                left unset. Real reconciliation (name-only confirms, browsing the full project
                                roster, reviewing unmatched people on either side) is a separate, deliberately
                                heavier/reviewed flow - see jira_people_sync.py - never something a routine sync
                                triggers on its own. When config.jira.sync_only_visible_statuses is on, a
                                brand-new remote issue (no existing local match) whose mapped status resolves to
                                a hidden status (MeetingConfig.hidden_statuses()) is skipped entirely rather than
                                created - existing already-synced local issues are left alone even if their Jira
                                status later maps to hidden, to avoid surprising deletions.
  jira_people_sync.py           The deliberate, user-reviewed counterpart to jira_sync.py's automatic sync -
                                reached via Settings > Jira's "Review Jira People Matches..." button (see
                                ui/jira_people_modal.py), which calls the heavier
                                IssueConnector.list_project_members() (not part of a routine Sync Now).
                                build_match_report(remote_members, config) classifies every remote project
                                member and local Person into 5 buckets: linked (Person.jira_account_id already
                                resolves), auto_matched (exact email match - the one bucket that's a side effect,
                                not just a classification: it mutates config.people in place immediately, "assume
                                matches when emails match" - the caller still needs to ctx.save_config()),
                                potential (name-only match, needs an explicit confirm/reject - nicknames/
                                coincidental collisions make silent linking too risky here), and
                                unmatched_remote/unmatched_local (each split further into active vs. dismissed via
                                JiraConfig.ignored_account_ids / Person.jira_unmatched). Plus 8 mutating actions
                                (confirm_potential_match, reject_potential_match, link_existing_person,
                                create_person_from_remote, set_remote_ignored, set_person_unmatched, and
                                unlink_person/sync_email_from_remote - for the `linked` bucket, letting a user
                                break a bad link, re-link to a different account via link_existing_person, or
                                pull in an email Jira has that the local record is missing/differs from without
                                unlinking first) that just mutate config in place - same "caller calls
                                ctx.save_config()" convention as everywhere else in this app.
  credential_store.py          Windows Credential Manager wrapper (ctypes + advapi32.dll) for secrets that must
                                never live in Data/ - see "Secrets" below. Target names are scoped by a hash of
                                the install's own folder path, so multiple installs on one machine don't collide.
  connectors/                  base.py declares IssueConnector (test_connection/list_projects/pull_issues/
                                create_issue/list_project_members) so trackers are interchangeable; jira.py is
                                the only implementation built so far, using the Jira Cloud REST API v3 via urllib
                                (stdlib only). RemoteIssue.assignee_account_id and the RemoteUser dataclass
                                (account_id/display_name/email) exist for jira_sync.py's assignee resolution and
                                jira_people_sync.py's matching respectively - account_id (Jira's accountId) is the
                                stable, GDPR-safe identity link; email is best-effort only since Jira orgs can hide
                                it entirely depending on org privacy settings. list_project_members() pages through
                                `GET /rest/api/3/user/assignable/search` (the older startAt/maxResults scheme, no
                                cursor/isLast flag - a short page is the only "last page" signal), filtered to
                                accountType == "atlassian" to drop bots/service/app accounts. Jira
                                Cloud's `description` field uses Atlassian Document Format (a JSON tree, not a
                                plain string) - see _text_to_adf/_adf_to_text in jira.py before touching it.
                                pull_issues() calls `POST /rest/api/3/search/jql`, not `GET /rest/api/3/search` -
                                the GET endpoint is deprecated and returns `410 Gone` (confirmed against a real
                                Jira Cloud instance, the first part of this connector actually exercised against
                                real Jira rather than just a mock server). Only the first page (100 issues) is
                                fetched - no pagination loop yet, since search/jql uses cursor-based
                                `nextPageToken` pagination, not the old startAt/total scheme.
  ui/                           theme.py (shared ttk palette/styles - reuse PRIMARY/BG/INK/etc. rather than
                                inventing new ones, same palette as templates/README.html; also restyles
                                Vertical.TScrollbar away from "clam" theme's default grey chrome - every
                                ScrollableFrame picks this up automatically, no per-usage changes needed.
                                No ttk button styles here anymore (TButton/Primary.TButton/Secondary.TButton were
                                removed once every button in the app moved to rounded_button.py's RoundedButton -
                                see that entry). Extended for the Material-Design-3-
                                inspired redesign (v0.9.0): kept every existing constant name (BG/INK/MUTED/
                                LINE/SUBTLE_BG/CARD_BG/PRIMARY/PRIMARY_DARK/DANGER) rather than renaming to MD3
                                role vocabulary (SURFACE/ON_SURFACE/etc.) - the values were already a coherent
                                tonal system by accident (SUBTLE_BG is ~a 90%-white blend of PRIMARY; MUTED
                                shares PRIMARY's hue), so a pure rename would've touched 100+ call sites for no
                                functional benefit. New constants added instead: SIDEBAR_HOVER, ON_PRIMARY_DARK_
                                MUTED (consolidates three previously-divergent undocumented hex values used for
                                "muted text on the dark sidebar"), WARNING_ON_DARK, SUCCESS/ON_SUCCESS, OUTLINE,
                                and a SPACE_XS..SPACE_XXL (4/8/12/16/24/32) spacing scale. Type scale refined to
                                named roles - Display 44pt (Run Meeting countdown only, was 48), Headline 20pt
                                (Heading.TLabel, was 18), Title 13pt bold (SectionHeading.TLabel + new CardTitle.
                                TLabel, merges the old 12pt SectionHeading with a couple of screens' one-off
                                hardcoded 11pt row titles), Body 10pt, Label 9pt bold (new Label.TLabel/
                                CardLabel.TLabel, was 8pt), Meta 9pt (Muted.TLabel/CardMuted.TLabel, was 8pt) -
                                nothing in the app renders below 9pt now. Removed dead styles that had zero call
                                sites (Header.TFrame, the old PRIMARY-background Title.TLabel/Subtitle.TLabel,
                                Card.TFrame, Danger.TButton - deletes always go through icon_button.py's danger
                                glyph instead, never a full red button)), shell.py (AppShell: sidebar nav +
                                a right_column wrapper (content area; screens are plain build(ctx, **kwargs)
                                functions in a registry dict, not classes - ctx.navigate()/ctx.config/
                                ctx.save_config() is the whole contract) split into an indicator_slot (packed
                                side="top", fill="x", collapsed/empty by default - ui/run_indicator.py packs its
                                bar into this) stacked above ctx.content itself, so a running meeting's indicator
                                bar reserves real layout space and pushes content down instead of the earlier
                                place()-overlay approach, which covered up screen titles underneath it.
                                ctx.indicator_slot is a new AppContext attribute alongside run_state/
                                run_indicator/presentation_window. NAV_ITEMS entries can be ("group", "LABEL")
                                pseudo-entries rendered as a small (non-bold, 9pt) label with a thin divider line
                                above every group but the first - deliberately de-emphasized relative to the
                                actual nav links below them (a real user found the group labels and links similar
                                enough in weight to be hard to tell apart) - purely cosmetic grouping
                                (MEETINGS/TEAM DATA/REVIEW/SETUP), not phase-gating. Scorecard/Rocks are currently
                                hidden from NAV_ITEMS (and l10_manager.py's build_registry()) - not deleted, see
                                placeholders.py - while Issues/Prep/Review stay always-reachable. Prep is now
                                both a direct NAV_ITEMS entry (ui/prep.py::_render_picker handles being entered
                                with no occurrence in hand) and still reachable contextually from Dashboard's rows
                                (both routes call the same build()). Review replaced the old Conclude nav item -
                                see ui/review.py), tabs.py (TabBar - a hand-rolled flat/underline tab bar
                                replacing ttk.Notebook everywhere in this app; ttk's "clam" theme bakes its own
                                per-state padding into the selected tab's layout, which silently wins over any
                                style.configure() default - no matter what padding you set, the active tab
                                renders a different size than the others. Rather than keep fighting clam's
                                theme internals, TabBar just draws text + a colored underline for the active
                                tab, no per-tab box at all, so there's no "box size" left to differ - same
                                "build a small widget when ttk falls short" pattern as icon_button.py/
                                the drag-and-drop reordering/notifications.py's toast. settings.py and
                                schedule_builder.py both use it: tabs.page(i) is the container to build a tab's
                                content into, tabs.select(i)/on_change mirror ttk.Notebook's
                                select()/<<NotebookTabChanged>> just enough that swapping it in was a
                                near-drop-in replacement), canvas_shapes.py (rounded_rect_points() - the one
                                shared geometry helper behind this app's first canvas-drawn shapes; returns a
                                point list for canvas.create_polygon(smooth=True), one polygon item tracing an
                                entire rounded rectangle rather than compositing several arc/rectangle items
                                that could desync on a color change. No anti-aliasing is available on a stdlib
                                Tk canvas (no Pillow in this app) - splinesteps is bumped for smoother corners,
                                and small-radius jaggies are accepted the same way the "clam" theme's own
                                non-AA scrollbar arrows already are), rounded_card.py (RoundedCard(tk.Canvas) -
                                a rounded-corner replacement for the app's ubiquitous flat "card row" idiom
                                (tk.Frame + highlightbackground/highlightthickness), used at all 15 of its call
                                sites app-wide. Exposes `.body`, a real tk.Frame embedded via
                                canvas.create_window() - the same technique scrollable.py already uses for its
                                scroll viewport - so callers pack/grid real content into `.body` exactly as they
                                did into the old flat Frame. Sizing is a two-way negotiation a bare Canvas
                                doesn't get for free the way a Frame does: width flows top-down from the card's
                                own <Configure>, height flows bottom-up from `.body`'s <Configure>
                                (winfo_reqheight() drives the canvas's own configure(height=...), replicating
                                pack's shrink-to-fit) - both handlers guard on "did the value actually change"
                                so they can't retrigger each other in a loop. `.body`'s square corners sit
                                inset from the canvas edges by _corner_inset() (>= radius * ~0.3, the geometric
                                minimum to keep a square corner inside a quarter-circle curve) so they don't
                                poke out past the rounded curve. set_active(bool) swaps border color/width
                                (PRIMARY/2px vs LINE/1px) and set_fill(background) swaps both the shape's fill
                                and `.body`'s own background, for the 2 sites that need a post-creation toggle
                                (people_modal.py's editing row, run_meeting.py's current-segment row) - though
                                most call sites just pass the right colors as constructor args instead, since
                                they fully rebuild the row on every state change anyway. Whole-row hover
                                highlighting was deliberately NOT added on top of this: Tkinter's Enter/Leave
                                boundary-crossing semantics fire a <Leave> on a parent the instant the pointer
                                crosses onto any covering child widget (a real, documented X11/Tk quirk), which
                                would flicker for any of these rows that has more than one child packed into
                                `.body` - if this is revisited, every descendant widget needs its own Enter/
                                Leave binding (the same "bind to every descendant" pattern issue_board.py
                                already uses for its drag handlers), not just the card itself), rounded_button.py
                                (RoundedButton(tk.Canvas) - the button-rounding fast-follow flagged (and
                                deliberately deferred) when RoundedCard shipped; built once RoundedCard had proven
                                the canvas-widget pattern in real use. Simpler than RoundedCard in one respect -
                                no embedded child window, just two canvas items (a rounded-rect shape + a
                                centered create_text label) - so there's no bidirectional sizing negotiation to
                                get right; sizes itself once from its text via tkfont.Font.measure(), the same
                                way ttk.Button auto-sizes. Only "filled" (was Primary.TButton) and "tonal" (was
                                Secondary.TButton) variants exist - the two actually used at volume (28 + 47 call
                                sites) - no disabled state (nothing in the app ever set one on a button) and no
                                shadow (this app's flat/tonal elevation has no drop-shadow rendering anywhere,
                                same reasoning as RoundedCard). Overrides .configure()/.config() to intercept
                                text=/command= kwargs (re-measuring/redrawing on a text change) and pass anything
                                else straight to tk.Canvas.configure() - this is what keeps it a close drop-in
                                replacement at the handful of call sites that dynamically retext a button after
                                creation (e.g. ui/run_meeting.py's Pause/Resume toggle) without those call sites
                                needing to change. Migrated every ttk.Button(style="Primary.TButton"/
                                "Secondary.TButton") call site app-wide via a mechanical mass-edit script (not
                                hand-edited one file at a time) since the transformation was uniform across all
                                77 call sites - if you need to redo a similar mechanical migration, grep first to
                                confirm every call site really does follow one pattern before scripting it, the
                                same way this one was verified (77 ttk.Button( calls, 77 style="Primary.TButton"/
                                "Secondary.TButton" occurrences, exact match) before the rewrite), icon_button.py
                                (icon_button() - small flat icon-only buttons replacing the old repeated
                                text Edit/Delete/Remove button-pair pattern everywhere it showed up; mirrors the
                                "X" dismiss button already in notifications.py. Glyphs are Segoe MDL2 Assets (the
                                standard Windows 10+ monochrome UI icon font), not scattered Unicode symbol/emoji
                                codepoints from different blocks with inconsistent font coverage - the old
                                GLYPH_DELETE was an emoji-range wastebasket that fell back to colorful "Segoe UI
                                Emoji," clashing with every other flat glyph next to it (a real user reported the
                                icons "don't fit"). If you add a new GLYPH_* constant, write it via a Python
                                heredoc script containing the literal `\uXXXX` escape in source, not through a
                                direct file edit - editing tools in this environment have been observed silently
                                producing an empty string when a literal Private-Use-Area character is written
                                directly, and always verify the new glyph renders (no tofu/blank box) via a live
                                screenshot before trusting the codepoint), drag_reorder.py (DragReorder - the
                                shared drag-to-reorder mechanics (ButtonPress-1/B1-Motion/ButtonRelease-1, a
                                ghost Toplevel, pixel-threshold click-vs-drag disambiguation, index-at-point via
                                each row's midpoint) extracted from schedule_entry_editor.py's original
                                implementation once ui/settings.py's Board tab needed the identical technique for
                                reordering columns/statuses. One instance per rendered list: reset_rows() at the
                                start of a render, bind_handle() once per row in display order, on_drop(
                                start_index, insert_at) callback splices the caller's own list and re-renders.
                                orientation ("vertical" default, or "horizontal") picks which axis the midpoint
                                math reads - schedule_entry_editor.py's own list is vertical, but settings.py's
                                column strips are laid out side-by-side, and column_reorder was originally wired
                                through the vertical-only math anyway: a real, latent bug, since comparing Y
                                positions of strips that all sit at the same Y degenerates to "always index 0" or
                                "always append at the end" depending only on where vertically within the row you
                                released the mouse, never which column you'd actually dragged over. Caught and
                                fixed while adding real horizontal scrolling to that same tab (see settings.py's
                                Board tab below) - settings.py now constructs it with orientation="horizontal"),
                                scrollable.py (ScrollableFrame -
                                use it for any screen whose content can exceed the window height; mousewheel
                                binding is Enter/Leave-scoped, not a permanent bind_all, to avoid leaking across
                                screen navigation. Scrollbar auto-hides when content fits without scrolling
                                (checked on both body's and canvas's <Configure>, guarded so pack/pack_forget
                                only fires on an actual visibility change - a real user noticed scrollbars
                                showing on screens with nothing to scroll). Takes an optional `background` param
                                (default theme.BG) applied to BOTH the canvas and `.body` - `.body` is a plain
                                tk.Frame, not ttk.Frame, specifically so it CAN take that explicit background;
                                needed because ui/issue_board.py now wraps each Kanban column's card list in one
                                of these with background=theme.SUBTLE_BG to match the column, and a ttk.Frame
                                body would have silently rendered theme.BG regardless of what was passed).
                                `.body`'s width IS correctly forced to match the canvas via
                                canvas.itemconfig(canvas_window, width=...) on every canvas <Configure> - but
                                that alone doesn't reliably re-flow children `.body` already has packed with
                                fill="x": confirmed by direct instrumentation that for a column with enough
                                cards to need a scrollbar, `.body` genuinely narrows to the right width, yet its
                                already-packed card canvases stayed stuck at an earlier, wider size regardless
                                of how long afterward it's inspected - a real user saw a wide gap of empty
                                background between clipped card text and the card's own right border, only in
                                columns with enough issues to trigger the scrollbar. _resync_child_widths()
                                explicitly re-configures every existing child's width whenever the canvas
                                resizes, deferred via self.after_idle() rather than done inline in
                                _on_canvas_configure - doing it synchronously there fought with the scrollbar's
                                own pack()/geometry settling from the same resize cascade and left the
                                scrollbar permanently un-mapped despite being packed.
                                HScrollableFrame (same file) is the horizontal counterpart, built for Settings >
                                Board's row of column strips once a real user reported no way to reach columns
                                that overflowed the window's width - same auto-hide-scrollbar idiom (checked on
                                width instead of height), Shift+MouseWheel instead of plain MouseWheel, and one
                                deliberate divergence from ScrollableFrame: it does NOT force `.body`'s width to
                                match the canvas (that would clip content to the visible area and defeat
                                scrolling entirely) - only `.body`'s height is pinned to the canvas, since a
                                single row has one fixed height, not something to scroll within,
                                dialogs.py (themed ask_text/ask_minutes modals -
                                tkinter.simpledialog isn't themeable; ask_minutes's Spinbox is 1-240 only,
                                positive values - it's for "how long is this segment," not a signed adjustment),
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
                                opens this modal), jira_people_modal.py (open_jira_people_matches_modal(ctx,
                                remote_members) - the review UI for jira_people_sync.py's MatchReport, same
                                Toplevel/ScrollableFrame/refresh-in-place idiom as people_modal.py above. Two
                                tabs (see tabs.py), not three - the original "Needs Your Review" tab (potential
                                name-only matches) is folded directly into "Local People" as one more per-row
                                state instead of a separate tab, since a real user found "not sure what Needs
                                Review is for" as a standalone concept. Local People lists EVERY local person -
                                potential (name-only match: confirm/reject icon buttons, plus the same
                                email-sync checkbox as below), unmatched (find-a-match combobox + "Leave
                                unmatched"), linked (Unlink button, a relink combobox to switch to a different
                                remote account, and - the same email-sync checkbox condition as potential
                                matches, now also available for ALREADY-linked people, since a real user had
                                matched people whose local record was still missing an email Jira had - the
                                original checkbox only ever showed on unconfirmed potential matches, never on an
                                already-completed link), or marked-unmatched (an Undo icon) - sorted "untouched"
                                (potential + unmatched, i.e. needs a decision) before "settled" (linked +
                                marked-unmatched), per that same feedback. "Jira Members" (a
                                link-to-existing-person combobox, "+ Add" to create a new Person from the remote
                                member - shows "(no email on file)" rather than a blank line when the remote
                                member has none, so it's clear they're still importable - or an ignore icon
                                button, collapsed "Show ignored (N)" footer) comes second, after Local People,
                                since a real user checks their own team's gaps first. on_tab_change() destroys
                                the tab being left (not just rebuilding the one being entered) - total live
                                widget count stays to one tab's worth regardless of how many were visited,
                                keeping Close's teardown fast.

                                Each tab's cards are built ONCE per genuine data change and then CACHED as
                                (widget, search_keys) pairs in state["rows"] - typing in the search box never
                                rebuilds anything, only shows/hides what's already built (_apply_search_filter()).
                                This split is the result of three rounds of real user feedback converging on the
                                same root cause: an earlier version recomputed jps.build_match_report() (an
                                O(people x remote_members) matching pass) AND destroyed/rebuilt every card on
                                every keystroke - first with no debounce (visible per-keystroke lag, the window
                                going "Not Responding" while typing), then with a 200ms debounce (still "sits and
                                sits, then shows those letters," and clearing the search back to the full list
                                "has to go through the entire loading process again," since a debounce only
                                delays a rebuild whose cost still scales with list size - it doesn't remove the
                                rebuild). Since remote_members is fetched once, in full, before this modal ever
                                opens (see ui/settings.py's caller) and the local People list doesn't change while
                                you type, a keystroke never actually needed to touch the data or the widgets at
                                all - only which already-built row is visible needs to change, and toggling
                                pack()/pack_forget() on existing widgets is cheap regardless of list size.
                                render_active_tab(recompute, force_rebuild) is the resulting split: `recompute`
                                controls whether jps.build_match_report() reruns (only true for a real mutation -
                                confirm/reject/link/unlink/etc., via the `refresh` callback threaded through the
                                row builders); `force_rebuild` (defaults to `recompute`) controls whether the row
                                cache gets thrown out and rebuilt from scratch. A pure search-text change
                                (on_search_changed) passes neither, hitting the fast path: if state["rows_tab"]
                                already matches the active tab index, render_active_tab just calls
                                _apply_search_filter(state["rows"], ...) and returns - no report recompute, no
                                destroy, no rebuild, no matter the list size. _apply_search_filter() always
                                pack_forget()s every row before re-packing the matches (in their original build
                                order) rather than toggling in place, since a lone pack() on a previously-hidden
                                widget re-appends it at the END of the packing order instead of back where it
                                belongs otherwise. Tab switches and the "Show/Hide ignored" toggle both still
                                force a full rebuild (state["rows_tab"] won't match after a tab switch anyway;
                                the ignored-toggle passes force_rebuild=True explicitly, since it's a real
                                content change - the ignored footer itself is rebuilt directly rather than
                                cached/filtered like the main list, an accepted tradeoff since it's small and
                                collapsed by default). One correctness trap hit while building this: don't use
                                widget.winfo_ismapped() to decide whether any row is currently visible (e.g. for
                                the "no matches" empty-state label) - Tk defers actually updating a widget's
                                mapped state to its idle queue, so checking it in the same synchronous pass as
                                the pack()/pack_forget() calls that just ran can read stale state and show "no
                                matches" even when rows really did just become visible. refresh_empty_label()
                                instead recomputes visibility with the same _matches_search() logic used to do
                                the filtering, never by asking Tk what it's actually drawn.

                                The row cache is built via the shared _fill_in_progressively() helper, which
                                builds one card at a time, still paced via ctx.root.after(CARD_FILL_DELAY_MS,
                                ...) so a long list never blocks the event loop, and PACKS IT IMMEDIATELY -
                                extending the visible list right there - if it currently matches the search box
                                and the visible cap (PAGE_SIZE = 30) hasn't been reached; a card that won't be
                                shown is simply never packed at all. Every built card, shown or not, is still
                                appended to row_sink (state["rows"]) regardless, so a later search-text change or
                                "Show more" click can reveal any of them via _apply_search_filter with no rebuild.
                                This is the THIRD design _fill_in_progressively has gone through, each one fixing
                                a real problem the last one caused. The first built every card synchronously,
                                freezing the UI for however long a long list took. The second built every card
                                HIDDEN in the background and revealed them all together once the whole batch
                                finished, specifically to stop a search typed mid-build from producing a visibly
                                broken mix of correctly-filtered real cards and skeleton placeholders with no
                                search keys to check. That fix introduced a worse regression: _render_person_row/
                                _render_jira_member_row used to pack() themselves and call update_idletasks()
                                (forcing an actual paint) as part of building EVERY card, and the hidden-build
                                version then immediately called pack_forget() right after - so every single card,
                                shown or not, visibly flashed into existence and back out, for the ENTIRE list, on
                                every normal tab open ("blinks a thousand times," per a real user - a much more
                                visible bug than the one being fixed). The fix this time: those two row-builder
                                functions no longer pack themselves or call update_idletasks() at all - they just
                                build content into card.body and return the (unpacked) card; the CALLER
                                (build_next()) decides, and only calls pack()+update_idletasks() for a card that's
                                actually going to stay visible. A widget that's never been given to a geometry
                                manager can't have been drawn on screen - Tk only schedules a paint once something
                                maps it, and since the show-or-not decision happens in the same synchronous step a
                                card finishes building (no update()/mainloop turn in between), an unshown card's
                                idle tasks are never processed before it would have mattered. The mid-build search
                                problem the SECOND design solved is still solved here too, just differently: since
                                there are no skeleton placeholders anymore, a search typed mid-build only ever
                                affects cards that already exist, which independently re-check their own match
                                state - there's no inert placeholder to produce a broken mix.

                                PAGE_SIZE caps how many matching cards are ever packed at once - on top of the
                                flash fix, a real user also asked for pagination so a very long Jira member list
                                doesn't render hundreds of live widgets by default. This is a visibility cap, not
                                a data cap - _fill_in_progressively still builds every item in the background
                                regardless, so search always works across the full set, not just the current
                                page. A "Show N more (M left)" control (a RoundedButton, built once per full
                                rebuild alongside a stable zero-height anchor Frame that every shown row and the
                                button itself insert before via `before=`, so newly revealed rows always land
                                directly above it rather than at the end of the whole page) only appears once
                                on_build_complete() fires and there's more to show past the cap; clicking it just
                                raises state["visible_cap"] by PAGE_SIZE and calls refresh_visible_rows() - no
                                rebuild. A new search resets the cap back to PAGE_SIZE first, so each search
                                starts its own fresh first page instead of inheriting however far a previous
                                search (or the unfiltered list) had been paged into.

                                generation (an incrementing counter, captured as my_generation by each scheduled
                                step) is what lets a tab switch, a mutation-triggered rebuild, or the window
                                closing (on_close bumps it too) cleanly cancel a still-running progressive build
                                from a previous render - every build_next() step checks it first and silently
                                stops if a newer render (or the window itself) has superseded it, rather than
                                touching widgets that may already be destroyed.

                                Every mutating action calls schedule_save() - a fire-and-forget background-thread
                                save per action, coalesced (a mutation while a save is already in flight just
                                marks one more save as pending rather than spawning a second concurrent writer) -
                                "save as you go" rather than batching until Close, per direct feedback that Close
                                still felt slow even after an earlier per-click-save-elimination pass: Data/ can
                                live on a Google Drive/OneDrive/Dropbox sync mount (see config.py's
                                atomic_write_json retry-with-backoff comment for the WinError 5 history), so even
                                a single atomic write blocking win.destroy() could stall Close if Google Drive
                                Desktop happened to be holding a lock at that exact moment - now Close just
                                destroys the window; whatever save is in flight keeps running independently since
                                it never touches Tkinter.

                                A single search Entry (search_var, labeled "Search (name or email)") above the
                                tabs filters whichever tab is currently active by substring match against BOTH
                                the name(s) AND email(s) on each row (person.name/person.email, plus the matched
                                Jira member's display_name/email for potential-match rows, since both identities
                                are shown together there) - a real user asked to be able to search by email too,
                                since a name alone doesn't always narrow things down. Purely in-memory against
                                remote_members (fetched once, in full, before this modal ever opens), never a
                                live Jira lookup. See the row-caching description above for why typing no longer
                                rebuilds anything), wizard.py (first-run
                                setup, skippable at every step -
                                build() lands on a dedicated "you're already set up" gate (_render_already_configured_step)
                                instead of the normal info step whenever ctx.config.repeating_instances is
                                non-empty, with "Go to Dashboard" (sets onboarded=True and leaves) or "Continue
                                Setup Anyway" (proceeds into the normal wizard) - the wizard used to only ever
                                render a session-local pending_instances list and never looked at
                                ctx.config.repeating_instances at all, so a real install that somehow had
                                onboarded=False again (a legacy config predating that field, e.g.) saw what
                                looked like a completely blank wizard despite having real meetings configured
                                and safely untouched on disk - nothing was ever being deleted, but the wizard had
                                no way to show or account for what was already there. _render_instances_step()
                                now also lists ctx.config.repeating_instances (read-only, above the
                                session-local pending list) for the same reason, in case the user does continue
                                past the gate),
                                settings.py (a TabBar-sectioned (see tabs.py above) Meeting & Schedule / People /
                                Board / Jira layout, rather than one long scroll - each tab keeps its own edit
                                sub-mode and state["active_tab"] tracks which tab a save/cancel rebuild should
                                return to. Every plain settings toggle/field across all tabs autosaves - Meeting
                                Info (MeetingInfoForm's on_change callback, fired on <FocusOut> from either
                                field), the Board tab's Card Display checkboxes (command= fires immediately on
                                toggle), and every Jira connection field (checkboxes autosave on toggle, the
                                three text Entries on <FocusOut>, the project Combobox on <<ComboboxSelected>>>)
                                - replacing three separate explicit "Save X Settings" buttons that a real user
                                found inconsistent with the rest of the app (Column/Status CRUD already
                                autosaved every action). Genuine edit-a-record modals with a real Cancel
                                affordance (Issue, Column, Status, Segment, Schedule, Person, Instance forms)
                                deliberately keep explicit Save/Cancel - unlike a live settings page, a
                                multi-field record edit needs a way to back out uncommitted changes. The
                                Board tab itself is laid out as a real horizontal Kanban strip, one column per
                                strip, inside an HScrollableFrame (ui/scrollable.py) rather than a plain
                                grid-based row - a real user reported columns getting squeezed with no way to
                                scroll to the ones that didn't fit, and asked for narrower columns besides. Every
                                strip is built via make_strip(), pinned to a fixed STRIP_WIDTH (170px, narrowed
                                further after a real user found the columns still "don't need that much space")
                                regardless
                                of content via pack_propagate(False) with an explicit width - deliberately NOT
                                the simpler "zero-height spacer Frame" trick that would otherwise avoid needing
                                pack_propagate at all: a bare tk.Canvas (what every RoundedCard status card
                                actually is) has no real content-driven width of its own, so left to size
                                "naturally" it can end up latching onto whatever width HScrollableFrame's
                                deliberately-unconstrained body happened to have on an early layout pass, which
                                then feeds back into the strip's own width calculation - the strip and its cards
                                got stuck mutually reinforcing a much-too-wide size the one time this was tried.
                                Height, unlike width, is finalized via finalize_strip_height() called ONCE after
                                a whole column's cards are built - NOT via a live <Configure> binding that
                                resizes the strip as each card is added, which was tried first and turned out to
                                be the actual root cause of a real, reproducible bug: resizing the strip while
                                the NEXT card was still mid-construction re-triggered that card's own Configure
                                events out of order, leaving its Canvas stuck at its placeholder size - visually
                                either a missing card or an unexplained gap, exactly what a real user reported
                                seeing. render_status_card() itself still ends with its own card.update_idletasks()
                                per card (same fix already used throughout jira_people_modal.py) for the same
                                reason - both fixes are needed together, at their respective scopes (per-card,
                                then once per whole strip). Status cards are laid out as a SINGLE row - drag
                                handle, name, edit/delete right-aligned - matching the column header's own
                                layout, rather than the original two-row arrangement (name on top, edit/delete on
                                a row below it): a real user found the icons "in a weird spot" there and the
                                cards taking more vertical room than they needed. equalize_strip_heights(), called
                                once after every strip's own height has already been individually finalized via
                                finalize_strip_height(), re-applies the tallest strip's height to every strip -
                                dropping the earlier "stretch every column to the tallest one's height" grid
                                behavior in an prior round left a short/empty column visibly shorter than its
                                neighbors ("Parked is low for some reason"), so this restores equal-height columns
                                the same safe way finalize_strip_height() itself works: a single pass done AFTER
                                every card everywhere has already fully settled, never a live per-card resize, for
                                the exact same reason described above. Each column strip has its own header (drag
                                handle + edit/delete) and its status "cards" (RoundedCard, matching how an actual
                                Jira/Issues board card reads) packed directly into the strip - no per-column
                                vertical ScrollableFrame anymore, since strips just grow to their natural height
                                before being equalized, and the outer Settings page's own vertical scroll handles
                                any overflow beyond that - plus its own "+ Add Status" button at the bottom of the strip (calling
                                _goto_add_status_to_column(), which pre-selects that column in the add-status
                                form instead of always defaulting to the first column regardless of which strip
                                was clicked). "Hidden from Board" renders as one more strip at the end of the same
                                row, so dropping a status there is just one more group for the existing
                                cross-container drag to hit-test - no special-cased drop-zone shape needed (same
                                _group_at_point()/group_frames mechanic as before, mirroring the ghost-Toplevel/
                                threshold/bounding-box-hit-test technique from ui/issue_board.py's Kanban card
                                drag; DragReorder is a different, simpler mechanic used only for reordering
                                columns themselves via their header handle, which stays orthogonal to the status
                                cross-group drag - now constructed with orientation="horizontal" since these
                                strips sit side-by-side, not stacked - see drag_reorder.py above for the latent
                                bug this fixed). When Jira is enabled,
                                editing an EXISTING status (not a brand-new one being created, since it needs a
                                real id first) also shows a "Jira Status Mapping" section - which raw Jira
                                status names (from config.jira.status_mapping) already point here, shown as
                                individually removable pills (_render_status_pill/_render_wrapped_pills) rather
                                than one plain comma-joined line of text - a real user asked for "removable cards
                                or pills," since a flat text line gave no way to unmap just one Jira status
                                without going to the main Jira tab's table instead. Removing a pill just deletes
                                that one entry from config.jira.status_mapping outright (not reassigning it
                                anywhere) - the next sync re-guesses a default for that raw name via
                                jira_sync.py's map_remote_status(), same as if it had never been mapped at all.
                                _render_wrapped_pills() wraps pills onto a new row instead of one non-wrapping
                                line - a real, reproducible bug found while building this: with more than a
                                couple of names, or one long one, pills silently ran past the edge of the window
                                with no way to reach or remove them. Row membership is decided up front from each
                                name's font.measure()d width, since a Tkinter widget's parent can't change after
                                creation. That same measurement is also used to set each pill's WIDTH explicitly
                                (RoundedCard.configure(width=...)) rather than letting it size "naturally" - a
                                second real bug found in the same round: a bare tk.Canvas (what RoundedCard
                                actually is) has no real content-driven reqwidth of its own, so left alone every
                                pill's winfo_reqwidth() reported the SAME (wrong) value as whichever pill was
                                built first, regardless of its own text, squeezing or pushing later ones
                                off-screen - the identical failure mode make_strip() already worked around for
                                Board's column strips, hit again here for the same underlying reason. A combobox
                                offering EVERY known Jira status name (not just ones not yet mapped anywhere - a
                                real user asked for "all the statuses as options") lets you move one over.
                                Picking one already mapped to a DIFFERENT status now confirms via
                                messagebox.askyesno ("'X' is currently mapped to 'Y'. Switch it to 'Z' instead?")
                                before reassigning it, rather than silently stealing that mapping out from under
                                whatever it used to point to; picking one already mapped HERE is a harmless
                                no-op. This is also what makes mapping several Jira statuses to one app status
                                straightforward - the underlying config.jira.status_mapping is just a plain
                                name->status-id dict with no one-to-one constraint, so repeating the pick+confirm
                                for each additional Jira status name achieves it; the only thing missing before
                                was the confirmation guard, since silently reassigning already-mapped names made
                                repeating the action feel unsafe/unclear. So a user can wire up Jira's workflow
                                statuses to a local status while creating/editing it here, not only from the
                                separate Jira tab's full mapping table, per "if Jira is turned on, we should be
                                able to match Jira statuses while doing this." The Jira tab itself owns
                                connection/project setup - Test Connection & Load Projects sits
                                above the project picker and reports status inline, never via messagebox - plus
                                the Jira status-mapping table (each row already offers every local status
                                unfiltered and reassigning one is always unambiguous, unlike the per-status
                                editor's dropdown above, so it needs no confirm dialog of its own) and a
                                sync_only_visible_statuses checkbox. "Review Jira People Matches..." now gets its
                                own RoundedCard callout (heading + one-line description + a filled, not tonal,
                                button) right below Sync Now instead of being just another small tonal button at
                                the bottom of a long tab - a real user reported it was too easy to miss. The
                                button's own behavior is unchanged: it used to call
                                connector.list_project_members() synchronously on the main thread with zero
                                feedback while Jira's paginated API responded - a real user reported the button
                                "opens very slow" with no indication anything was happening. Now shows a small
                                indeterminate-progress loading dialog immediately and runs the lookup on a
                                background thread (root.after(0, ...) marshals the result back), only opening
                                ui/jira_people_modal.py once data arrives - same pattern as
                                l10_manager.py's update-progress dialog. (jira_sync.py's routine Sync Now button
                                right above it has the identical blocking-call shape and needs the same fix -
                                flagged, not yet done.) See jira_sync.py / jira_people_sync.py), occurrence_list.py (render_occurrence_list(parent, ctx, on_pick,
                                weeks=8, button_label="Prep", max_items=None, show_button=True) - the shared
                                "list of upcoming meetings, pick one" rendering, factored out of dashboard.py
                                once ui/prep.py's standalone entry and ui/run_meeting.py's "nothing running"
                                picker both needed the identical list with only the on-pick action differing.
                                Returns the full view list even when max_items truncates what's rendered, so
                                Dashboard's overview can use it for counts without a second query), dashboard.py
                                (a lightweight overview now, not a full meeting browser - that's Prep's job (see
                                shell.py above). Shows at-a-glance open-issue/outstanding-to-do counts (querying
                                issues.py/todos.py directly, is_closed-aware) plus the next few upcoming meetings
                                via occurrence_list.py with max_items=3 - "See the Prep tab for the full list"
                                below it points at the unlimited version), prep.py (effective schedule for one
                                occurrence, plus a "Start Meeting" button that hands off to
                                run_meeting.start_meeting(). build()'s standalone entry (occurrence_key=None,
                                view=None - reached from the sidebar, not a Dashboard row) renders
                                occurrence_list.py's picker instead of the old "Couldn't find that meeting" dead
                                end. The "no schedule set" branch (_render_no_schedule) offers two paths instead
                                of a static label: "Set Schedule for the Whole Series..." (only when
                                repeating_instance_id isn't None) routes to ctx.navigate("settings",
                                edit_instance_id=...) - settings.py's build() gained that optional kwarg to jump
                                straight into edit_instance sub-mode - or a combobox + button to set just this
                                occurrence's schedule via cfgmod.get_or_create_occurrence(). Also has a "View
                                Backlog" button opening issue_board.py's open_backlog_modal()), review.py
                                (Review - the post-meeting phase from docs/L10-CONCEPT.md's Prep->Run->Review
                                mapping; replaces the old Conclude nav placeholder - the Conclude *agenda item*
                                itself now lives as a live segment type (segment_types.py::ConcludeType) run
                                during the meeting, this screen is what you check afterward. Picks a repeating
                                instance (only shown if more than one exists), then for the most recent past
                                occurrence: the cascading message (view/edit, writes back via
                                cfgmod.get_or_create_occurrence()/save_occurrence()) and open to-do/issue counts
                                as a capture-confirmation, plus a chronological rating-history list averaging
                                each past Occurrence.ratings where a record exists (most won't - expected, per
                                config.py's own sparse-storage model). Past dates come from
                                recurrence.generate_occurrences(ri.recurrence, ri.recurrence.start_date, today)
                                filtered to date < today - the exact same function dashboard.py/prep.py already
                                call with a forward-looking range, just given a historical one instead; no new
                                backward-looking recurrence logic exists anywhere), schedule_editor.py
                                (per-occurrence skip/restore/add-segment UI, icon buttons instead of text;
                                "Adjust" and "+ Add Segment" both open segment_override_form.py's shared modal
                                rather than the old single-field ask_minutes prompt, since an override can now
                                touch name/duration/config, not just a number), schedule_builder.py (replaces
                                schedule_templates.py - a two-tab TabBar (see tabs.py above), same single-file
                                pattern as settings.py: a "Segments" tab for the global library (grouped by type,
                                Edit/Duplicate/Delete icon buttons, "+ New Segment" opens segment_editor.py) and
                                a "Schedules" tab for the reusable named Schedules built from it
                                (schedule_total_minutes() for the summary line; Duplicate now just deep-copies
                                entries with fresh entry ids - the referenced segment_ids are shared, not
                                copied, much simpler than the old inline-section duplication). _delete_segment()
                                also strips any ScheduleSegmentEntry referencing that segment_id out of every
                                Schedule, not just the library entry - schedule.py's _resolve() has always had a
                                graceful "(missing segment)"/0-min fallback for a dangling reference (so a
                                stale one was never a crash), but leaving that fallback as the only behavior
                                meant deleting a segment left a permanent ghost row behind in every schedule
                                that used it instead of the entry actually going away - a real user hit this
                                deleting and recreating a segment just to change its type), schedule_entry_editor.py
                                (renamed from schedule_template_editor.py now that entries reference global
                                Segments rather than holding inline section data - build_entry_list_editor()
                                shows each entry's resolved name/duration with a "(customized)" tag, an
                                Edit-pencil opens segment_override_form.py, "+ Add Segment" opens
                                segment_picker.py instead of creating a blank section inline; drag-reorder now
                                goes through the shared ui/drag_reorder.py::DragReorder helper (extracted from
                                this module's own original ghost-Toplevel implementation once ui/settings.py's
                                Board tab needed the identical technique for columns/statuses).
                                open_new_schedule_modal() is the "+ New Schedule" shortcut reachable from
                                instance_form.py's RepeatingInstanceForm without leaving that form, and now
                                starts with an empty entry list since there's no more "just type a name"
                                shortcut - segments must be picked/created from the library), segment_editor.py
                                (open_segment_editor_modal(ctx, segment, locked_type, on_saved) - create/edit a
                                library Segment; type is only pickable when creating new, locked/read-only when
                                editing an existing one, since changing a segment's type after the fact would
                                orphan its config - delete-and-recreate is the intended path for "wrong type"),
                                segment_picker.py (open_segment_picker(ctx, on_selected) - a searchable modal
                                over the global library with a "+ New Segment" escape hatch that saves to the
                                library first via segment_editor.py, then hands the new Segment back to the
                                caller - this is what makes "create a segment while prepping a meeting" still
                                add it to the reusable library rather than a throwaway one-off), segment_override_form.py
                                (open_override_modal(ctx, segment, resolved, on_save) - the one shared
                                name/duration/config override form used at both the Schedule-entry level and
                                the occurrence level; always saves back whatever's in the fields, no diffing
                                against the segment's own values - "override any of the existing data, explicit
                                is fine even if it matches"), issue_board.py (the reusable Kanban-style board - build_issue_board(parent, ctx,
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
                                badge/description snippet/assignee. Each column's card list is wrapped in a
                                ScrollableFrame(col, background=theme.SUBTLE_BG) instead of a bare tk.Frame - a
                                real user found a column with more cards than fit on screen had no way to reach
                                the rest; this reuses ScrollableFrame exactly as-is (per-column instead of
                                per-screen), no new component needed, and doesn't disturb
                                _column_at_point()'s drop hit-testing since that only reads the outer column
                                frame's screen bounds. open_issue_dialog() and set_issue_status() (a new public
                                wrapper around the existing _apply_status_change() for callers that only have an
                                issue id, not the Issue object) are both public now (open_issue_dialog dropped
                                its leading underscore) since segment_types.py's IDS type is now a second caller
                                of both. open_backlog_modal(ctx, scope) is a new Toplevel listing
                                MeetingConfig.backlog_statuses() issues (hidden from the board but not is_closed)
                                - reachable from Prep's "View Backlog" button - reusing open_issue_dialog() for
                                viewing/editing rather than duplicating card-rendering. Card layout was redesigned
                                (a real user compared it to Jira/Linear cards and asked for a header/footer
                                structure instead of one plain stack of left-aligned lines): a header row holds
                                an assignee avatar (_make_avatar() - a small tk.Canvas badge with initials,
                                colored by _avatar_color()'s stable per-name hash from a small _AVATAR_PALETTE
                                deliberately distinct from CARD_ACCENT_PALETTE below so "person" and "column/
                                status" color-coding never look like the same signal; an unassigned issue gets
                                an empty outlined badge in the same slot rather than no avatar at all, so the
                                header never changes width/shifts the title depending on assignment) beside the
                                title, which is regular weight now, not bold - bold competed with long real Jira
                                titles for space and made a card read as "everything is emphasized." The avatar
                                is drawn as a polygon via canvas_shapes.rounded_rect_points() (radius = half the
                                size, i.e. as close to a circle as a rounded rect gets) with smooth=True/
                                splinesteps, NOT canvas.create_oval() - a real user reported the first version's
                                raw oval looked visibly jagged/"not really a circle" at this small size, since a
                                stdlib Tk canvas has no anti-aliasing at all; the polygon route at least gets the
                                same splinesteps smoothing already relied on for every other shape in this app.
                                The header row uses grid, not pack, for the avatar/title pair specifically - pack's
                                per-slave -anchor only takes visible effect once the row's final height has
                                settled from ALL its children, and a real user compared a short one-line title
                                against a long two-line one side by side and saw the avatar sit at a visibly
                                different relative height between them. Neither cell sets a vertical sticky (no
                                "n") - grid's default is to center a widget within its cell, so whichever of
                                avatar (fixed ~24px) or title (1 or 2 lines) is taller in a given row sets that
                                row's height and the other centers against it. Top-aligning via sticky="n" was
                                tried first and only looked right for a 1-line title, where the taller avatar
                                happens to make top-align and center-align nearly indistinguishable - for a
                                2-line title (taller than the avatar), top-align left the avatar sitting visibly
                                above the true center of the whole two-line block, which is what the same real
                                user flagged on a second pass after the initial grid fix shipped. The title is clamped to
                                TITLE_MAX_LINES (2) via _clamp_to_lines()/_fits_in_lines(), a real word-wrap
                                simulation tied to the actual font and current (dynamically resized) wraplength -
                                not a fixed character count like the old _truncate_words() - with a hover tooltip
                                (_bind_tooltip(), a small borderless Toplevel, the same idiom as the drag ghost
                                below) showing the full title, but ONLY when truncation actually happened at the
                                current width (re-checked on every resize, since a title that fits at one column
                                width may not at another). A footer row holds the status as plain colored bold
                                text (left) and the Jira key rendered as a real clickable link with a "↗" suffix
                                (right, via webbrowser.open(issue.external_ref.url) - a real user specifically
                                asked for these two on one row instead of each stacked on its own line, and for
                                the key to actually be a link instead of inert text) - a card with neither status
                                nor an external_ref simply never packs the footer row at all, rather than
                                reserving empty vertical space for it. Status was originally its own little
                                RoundedCard "pill" badge (matching settings.py's Jira-status-mapping pills) but a
                                second real user round found that added real per-card cost - its own canvas,
                                polygon draw, and two Configure bindings - toward a genuinely slow load with 80+
                                real issues, for a "badge" look that read as visual clutter once seen against
                                real data rather than useful signal; plain text carries the same color-coding
                                (foreground=accent_color) for a fraction of the per-card cost. title_font is now
                                built ONCE in build_issue_board() and threaded down through refresh()/_build_card()
                                as a parameter rather than a fresh tkfont.Font() per card - Tk font object creation
                                isn't free, and building one per card (on top of the since-removed pill's own
                                per-card Font()) was measurably part of the same slowdown: a direct timing
                                comparison against the pre-fix version building 83 cards showed ~4.1ms/card before
                                these two changes vs ~1.2ms/card after, roughly a 3.5x improvement. refresh() itself
                                is now two passes - build every column's frame/header/ScrollableFrame FIRST, THEN
                                populate cards into them in a second pass - since a real user watched a large
                                board render as one tall unbroken list that only snapped into columns once
                                everything finished loading: populating a column's cards in the SAME pass that
                                creates it meant later columns' existence (and grid's weight=1/uniform sizing,
                                which only settles once ALL sibling columns exist) wasn't in place yet, so there
                                was no correct column layout to render into until the very end; a single
                                board_frame.update_idletasks() between the two passes forces that layout to settle
                                before card population - the slower part - even begins. CARD_ACCENT_PALETTE cycles
                                a small fixed color set by column.order % N for each card's RoundedCard
                                border_color/border_width (not a new persisted field) so each column reads as
                                visually distinct at a glance - a real 82-issue "Open" column had every card
                                looking identical - and doubles as the status text's own color, reusing the same
                                signal rather than inventing a second status-color scheme. open_issue_dialog()
                                also shows a small muted warning
                                under the Assignee field ("This person isn't linked to Jira...") when the issue
                                has a Jira external_ref and the selected Person has no jira_account_id - only
                                actionable there, so a purely local issue never shows it). _sync_wraplength()
                                (bound to `inner`'s <Configure>, re-measuring the title/description wraplength
                                against the card's actual rendered width - columns are user-resizable, so a
                                fixed wraplength either clips narrow columns or under-wraps wide ones) also
                                forces `card.body.event_generate("<Configure>")` after correcting the
                                wraplength - RoundedCard's own height-sync reads `.body.winfo_reqheight()` at
                                the moment `.body`'s width first changes (see rounded_card.py), which happens
                                BEFORE this handler (bound to `inner`, a child of `.body`) gets to correct the
                                wraplength, so without the forced re-fire the canvas locked in a height sized
                                for the label's un-corrected (often shorter) wrap and clipped whatever extra
                                line(s) the real column width forced - a real user's wide 83-issue column
                                showed long titles cut off mid-word. This also indirectly explained a second
                                real symptom from the same report (no scrollbar despite far more cards than fit
                                on screen): each undersized card under-reported its own height, so the column's
                                summed content height came out smaller than it really was too. issues.py (the nav screen wrapper - name
                                collides with the top-level issues.py data module; both resolve correctly since
                                Python's absolute imports use sys.path, not package-relative lookup, but alias on
                                import if it ever reads ambiguously), placeholders.py (Scorecard/Rocks stubs,
                                currently unwired from ui/shell.py's NAV_ITEMS/l10_manager.py's build_registry()
                                - not deleted, easy to re-add both lines later when built for real. The old
                                Conclude placeholder was deleted outright, not just unwired - genuinely
                                superseded, see ui/review.py/segment_types.py::ConcludeType, not "coming later"),
                                meeting_info_form.py / instance_form.py / recurrence_widget.py (reusable
                                form widgets shared by the wizard and settings - keep them shared, don't fork.
                                MeetingInfoForm takes an optional on_change callback, fired on <FocusOut> from
                                either the name Entry or the description Text - settings.py passes this for
                                autosave-on-blur; the wizard leaves it unset since its own Next button is
                                already the natural "confirm this step" action there, not a live settings page.
                                instance_form.py deliberately stays duck-typed (no schedule.py/config.py import)
                                - its "Schedule" combobox shows "Name (X min)" and needs only .id/.name/
                                .total_minutes off whatever's passed in, since schedule.Schedule no longer has a
                                bare .total_minutes (resolving one needs the segment library). Callers
                                (settings.py/wizard.py) build lightweight wrapper objects via
                                schedule.schedule_display_items(ctx.config.schedules, ctx.config.segments)
                                instead of passing raw Schedule instances. Its optional on_request_new_schedule
                                callback opens schedule_entry_editor.py's "+ New Schedule" modal and calls
                                RepeatingInstanceForm.add_schedule_option() (also wrapped the same way) to
                                select the new schedule in place - the surrounding name/description/length/
                                recurrence fields already typed in are never rebuilt or lost), run_meeting.py
                                (the Run Meeting screen - start_meeting(ctx, view) computes the effective
                                schedule once, filters out skipped segments, builds a run_state.MeetingRunState,
                                mounts run_indicator, and navigates here; when no run is active, build() shows
                                occurrence_list.py's picker (button_label="Start Meeting", on_pick calls
                                start_meeting directly) instead of a dead-end "No meeting is currently running" +
                                "Go to Dashboard" button - start_meeting() already handles the no-schedule/
                                nothing-to-run error cases via messagebox, so the picker itself needs no extra
                                validation. The active screen shows the current segment + big countdown, overall
                                time remaining, start/pause, next-segment-early (relabels to "Finish Meeting" on
                                the last segment - renamed from "End Meeting" once an always-visible, separate
                                "End Meeting..." button was added right next to it for ending a run early, e.g. a
                                user starting one by mistake; both labels used to collide), the new "End Meeting..."
                                button (messagebox.askyesno confirm, then state.stop() + ctx.navigate("run_meeting")
                                to force a rebuild), quick +/-5 min and Custom +/- time adjustment, a clickable
                                agenda list to jump to any segment directly, an "Open Presentation Window" button, a
                                collapsible personal-notes panel saved to Occurrence.notes on <FocusOut> (via
                                cfgmod.get_or_create_occurrence(), not its own inline copy of that pattern
                                anymore), and one additive frame rendered via
                                get_segment_type(segment.type_id).render_run_view() (now passed `ctx` as a third
                                arg - see segment_types.py) below the countdown - generic segments render
                                nothing extra, only Headlines/Core Values/Rocks/Scorecard/To-Do/IDS/Conclude add
                                content. Refresh only rebuilds the agenda list AND that extra frame when
                                current_index actually changes, not on every 1Hz tick. build() now branches three
                                ways: ctx.run_state is None (picker), ctx.run_state.ended (renders
                                meeting_complete.build(ctx) directly - no separate nav key needed), otherwise the
                                active screen above. This replaced a real bug: handle_next() used to call
                                ctx.navigate("conclude") on natural last-segment completion, a leftover nav key
                                from before "conclude" was replaced by "review" two rounds ago, which crashed
                                with "Unknown screen: conclude" the moment a meeting actually finished),
                                meeting_complete.py (build(ctx) - the landing screen for both the natural-
                                completion and explicit End Meeting paths, showing the meeting title,
                                run_state.elapsed_seconds, and a quick open-todo/open-issue count in the same
                                at-a-glance style as dashboard.py. "Go to Review" and "Back to Dashboard" both set
                                ctx.run_state = None before navigating, so a later visit to Run Meeting shows the
                                normal "pick a meeting" picker again instead of this same stale summary),
                                run_indicator.py (the
                                persistent mid-meeting bar - mount(ctx) once when a run starts; packed into
                                ctx.indicator_slot (fill="x") - a slot ui/shell.py::AppShell._build_layout()
                                reserves above ctx.content specifically so this bar pushes content down instead
                                of overlapping it (an earlier place()-overlay on ctx.root covered up screen
                                titles underneath it - a real user hit this). ctx.indicator_slot is a sibling of
                                ctx.content (both live inside the same right_column wrapper), so it still
                                survives navigate()'s ctx.content-only teardown - this is still the mechanism
                                that lets you flip to Issues/Settings mid-meeting without losing the timer. Tears
                                itself down when ctx.run_state.ended), presentation.py (open_presentation(ctx) - the
                                first non-modal, long-lived Toplevel in this codebase; every other Toplevel here
                                is modal and short-lived. No grab_set()/wait_window() - returns immediately,
                                meant to be dragged to a second monitor, reuses the existing window if already
                                open via ctx.presentation_window. Same additive render_presentation_view() frame
                                as run_meeting.py (also now passed `ctx` as a third arg), gated on its own
                                current_index tracker (this screen has no other per-tick rebuild to piggyback
                                on). WM_DELETE_WINDOW and the refresh listener both guard against the run ending
                                or the window closing out of order).
  launcher.ps1                 What the desktop-folder shortcut runs: status splash, Python check, then
                                launches l10_manager.py. Does NOT check for updates itself - that's owned by
                                the running app (updater.py) so the user isn't prompted twice.
  lib/PythonCheck.ps1          Shared Python-detection/guided-install logic, used by both install.ps1
                                and launcher.ps1 — don't duplicate this logic elsewhere.
assets/l10-manager-icon.ico   Icon for the per-install shortcut. Built from raw 32bpp pixel data written
                              directly into the ICO container (see git history for the generator script) -
                              NOT via Bitmap.GetHicon(), which silently quantizes colors to a 16-color VGA
                              palette. If regenerating, keep using the manual-DIB approach. The "L10" text
                              is deliberately rendered at ~84% of the canvas width (not stretched to fill
                              it) so real background color shows as padding on every side - a real user
                              found the original render's text touching the icon's edges, especially the
                              L, hard to distinguish from the background at small sizes. A first pass at
                              ~62% over-corrected (another real user report - "way too small, should be
                              almost the same size as before"); 84% is the balance that keeps the text
                              close to its original size while still leaving a visible margin. PowerShell gotcha
                              hit while regenerating: BinaryWriter.Write(byte[]) called via PowerShell can
                              silently resolve to the scalar Write(byte) overload instead, writing only the
                              array's first byte and corrupting the ICO with no error - cast explicitly
                              with Write([byte[]]$data) whenever writing a byte array through a .NET
                              BinaryWriter from PowerShell.
templates/README.html         Per-install read-me template (rendered with meeting name/date/version).
```

A finished install looks like:

```
<Chosen Location>/<Meeting Name> L10/
  Start L10 Manager.lnk      Shortcut -> App/launcher.ps1, custom icon
  README.html                 Rendered from templates/README.html
  App/                         Deployed from app-template/ + manifest.json
  Data/                        config.json, occurrences.json, issues.json, todos.json - never touched by an
                                update. Each gets a same-name .bak snapshot on every save (see "Data-safety" below).
```

## Key rules

- **Update mechanism**: the *running Python app* owns update-checking and applying (see `app-template/updater.py`), comparing local `App/version.txt` to `manifest.json` on GitHub. `launcher.ps1` deliberately does not duplicate this check, to avoid prompting the user twice on every launch. `Data/` is never touched by an update - only files listed in `manifest.json`'s `app_files` get overwritten.
- **Python detection**: always go through `app-template/lib/PythonCheck.ps1`. It must handle the Microsoft Store `python.exe` stub trap and never install anything without an explicit user confirmation.
- **Folder picking in install.ps1**: a real folder-only picker via `IFileOpenDialog` + `FOS_PICKFOLDERS` (COM interop through an inline C# `Add-Type` block) - not `FolderBrowserDialog` (legacy tree view, doesn't surface Quick Access/OneDrive/Google Drive well) and not a repurposed `OpenFileDialog` (confusing "file" affordances, and combining location-pick + name-type in one dialog caused a real double-nesting bug). Picking the location and typing the folder name are two separate steps (native dialog, then a console prompt) - install.ps1 doesn't ask about anything beyond that folder name; deeper meeting setup happens in the wizard, inside the running app. There's a `Read-Host` pause with explanatory text immediately before the picker call (interactive path only) - a first-time user reported the dialog just popping up with no warning was confusing.
- **Data-safety: every save is atomic, every load falls back to a backup, and a genuinely corrupt file is never silently treated as blank.** `config.py`'s `atomic_write_json()` snapshots the current file to `.bak` before writing (only if it currently parses - never snapshot corruption over a good backup), then writes to a `.tmp` sibling and `os.replace()`s it into place - no direct truncate-in-place write, ever. `load_json_with_fallback()` tries the main file, then `.bak`, and raises `DataLoadError` (not a silent blank default) only if both exist and both fail to parse - a missing file (first run) is a completely different, non-error case. This exists because a real user lost a whole `Data/config.json` (a configured repeating meeting vanished) almost certainly from the old direct-write + silent-blank-on-parse-failure combination racing with Google Drive's own sync process on the same folder - the old code would silently swap in a blank in-memory config on any read hiccup, and the *next* save would happily overwrite the real file with that blank data. `l10_manager.py`'s startup wraps `load_config()` in a blocking recovery dialog (explicit "start blank" vs. "quit without changing anything" - never a silent third option); `dashboard.py`/`prep.py`/`schedule_editor.py`/`issue_board.py`/`review.py` catch the same `DataLoadError` for `occurrences.json`/`issues.json`/`todos.json` and show an inline error banner instead of crashing. `atomic_write_json()`'s final `os.replace()` also retries a few times with a short backoff on `OSError` before giving up - a real user hit `[WinError 5] Access is denied` on a Jira sync, almost certainly Google Drive Desktop transiently locking the destination file mid-sync; this is the standard mitigation for atomic replace on a cloud-synced folder. Apply this same atomic-write-plus-fallback-plus-retry pattern to any future file this app persists to `Data/` (todos.py already does).
- **The live meeting timer (`run_state.py`) is in-memory only, on purpose.** It is never written to `Data/` - if the app closes mid-meeting, the next launch has no active run and the user starts over from Prep. This was an explicit tradeoff (not an oversight): persisting a live sub-second countdown means either near-continuous disk writes or a fuzzy "how long were we closed" reconciliation problem, on the same Google-Drive-synced folder that already caused the data-loss issue above, for a feature whose worst failure mode is "glance at a phone clock instead." Don't add persistence here without deciding this tradeoff again deliberately.
- **PowerShell empty-array gotcha**: a function that returns a zero-length array (e.g. reading a 0-byte file) gets unrolled to `$null` by PowerShell unless you prefix the return with a comma (`return , $bytes`). `Get-RepoBytes` in install.ps1 hit this for real with `app-template/ui/__init__.py` - keep it non-empty, and keep the comma if you touch that function.
- **Secrets never go in Data/.** `Data/` is designed to be shared with teammates for coverage, so anything in `config.json`/`issues.json` could end up in someone else's hands. The Jira API token is the first real secret in this app and it lives in Windows Credential Manager via `credential_store.py`, never in Data/ - keep this pattern for any future connector credential. This is the same reasoning that killed the "bake a GitHub token into the installer" idea (see above), applied to runtime app secrets instead of build-time ones.
- **The Jira connector is unverified against a real Jira instance.** It was built to the documented Jira Cloud REST API v3 spec and tested thoroughly against a local mock HTTP server (auth headers, ADF description parsing, error handling) plus the sync/merge logic against a mock connector - but no real Jira credentials were available while building it. If something's wrong, it's most likely in Jira-instance-specific details: workflow status names (`jira_sync.map_remote_status`'s keyword matching), custom issue types (`create_issue` hardcodes `"issuetype": {"name": "Task"}`), or ADF edge cases beyond plain paragraphs.
- Full rationale and phase-1 design decisions live in the plan history; ask before assuming scope beyond what's currently built.
