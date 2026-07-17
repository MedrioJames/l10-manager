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

## Architecture

```
install.ps1                  Bootstrapper: builds a new L10 install folder. Fetched fresh from GitHub
                              either via the one-liner (irm ... | iex) or via L10-Manager-Setup.bat.
L10-Manager-Setup.bat        Thin double-click stub — downloads and runs install.ps1.
manifest.json                Declares current app version + the file list install.ps1 deploys into App/.
app-template/                 Source of truth for everything deployed into a new install's App/ folder.
  l10_manager.py               The actual app (currently a dummy Tkinter placeholder).
  launcher.ps1                 What the desktop-folder shortcut runs: status splash, Python check,
                                lightweight update check, then launches l10_manager.py.
  lib/PythonCheck.ps1          Shared Python-detection/guided-install logic, used by both install.ps1
                                and launcher.ps1 — don't duplicate this logic elsewhere.
assets/l10-manager-icon.ico   Placeholder icon for the per-install shortcut.
templates/README.html         Per-install read-me template (rendered with meeting name/date/version).
```

A finished install looks like:

```
<Chosen Location>/<Meeting Name> L10/
  Start L10 Manager.lnk      Shortcut -> App/launcher.ps1, custom icon
  README.html                 Rendered from templates/README.html
  App/                         Deployed from app-template/ + manifest.json
  Data/                        Empty, reserved for future local data
```

## Key rules

- **Update mechanism**: the installer script is always fetched fresh from GitHub, so it never needs its own update-check logic. The *deployed app* (`App/`) is what gets version-checked and updated in place by `launcher.ps1`, comparing local `App/version.txt` to `manifest.json` on GitHub. `Data/` is never touched by an update.
- **Python detection**: always go through `app-template/lib/PythonCheck.ps1`. It must handle the Microsoft Store `python.exe` stub trap and never install anything without an explicit user confirmation.
- Full rationale and phase-1 design decisions live in the plan history; ask before assuming scope beyond what's currently built.
