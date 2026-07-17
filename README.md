# L10 Manager

A lightweight, self-contained tool for prepping, running, and reviewing an EOS/Traction-style **Level 10 Meeting (L10)** — the weekly leadership-team meeting format from *Traction*. New to L10s? See [docs/L10-CONCEPT.md](docs/L10-CONCEPT.md) for a primer on the agenda and the terms this project uses.

## How it's designed

- **One install = one L10.** Each installed folder is a single team's meeting, so the whole thing — app, data, shortcut — can be handed to a teammate covering for you.
- **One folder, fully self-contained.** Everything lives together so the folder can be dropped on Google Drive, OneDrive, or Dropbox and shared.
- **No technical hurdles.** Installing is: run one file, answer a couple of prompts, done.
- **Easy to update.** The app checks for a newer version each time it launches and offers to update itself.

This repo is currently in early infrastructure: the installer builds a real, working folder + shortcut + read-me, but the app itself is still a placeholder. Real L10 features (Scorecard, Rocks, Issues, IDS, Conclude/cascading messages) come next.

## Installing a new L10

Pick whichever is more comfortable:

**Option A — copy/paste one-liner**: open PowerShell (Start menu &rarr; search "PowerShell") and paste this in:

```powershell
irm https://raw.githubusercontent.com/MedrioJames/l10-manager/main/install.ps1 | iex
```

**Option B — download and double-click**: grab [`L10-Manager-Setup.bat`](L10-Manager-Setup.bat) and double-click it. No need to open PowerShell yourself first - the file does that for you.

Either way, the installer will:
1. Confirm Python is installed (and help you install it if not).
2. Let you pick (or create) a folder for this L10 — ideally somewhere synced, like Google Drive/OneDrive/Dropbox.
3. Build the folder: a `Start L10 Manager` shortcut, a read-me, the app, and a data folder.
4. Open the folder and walk you through what to do next.

## Repo layout

See [CLAUDE.md](CLAUDE.md) for the full architecture breakdown (bootstrapper, per-install app template, update mechanism).

## Contributing

This repository is public — never commit Medrio-internal information, credentials, or anything company-confidential. See the top of [CLAUDE.md](CLAUDE.md) for the full rule.
