"""Update checking/applying for L10 Manager.

Stdlib only. Deliberately never executes or evaluates downloaded content -
every fetch either becomes plain data (the manifest) or raw bytes written
straight to a file. Same posture as install.ps1/launcher.ps1: download to a
real file, never eval in memory.
"""

import json
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO_OWNER = "MedrioJames"
REPO_NAME = "l10-manager"
BRANCH = "main"
GITHUB_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{BRANCH}"
MANIFEST_URL = f"{RAW_BASE}/manifest.json"
INSTALLER_URL = f"{RAW_BASE}/install.ps1"
MANIFEST_TIMEOUT_SECONDS = 5
FILE_TIMEOUT_SECONDS = 30


def app_dir() -> Path:
    return Path(__file__).resolve().parent


def is_dev_checkout() -> bool:
    """True when this code is running straight out of the git repo's
    app-template/ folder rather than a deployed install's App/ folder - the
    two are structurally identical (same relative imports, same files), so
    nothing else here can otherwise tell them apart. A real install is
    never a git working tree; app-template/'s parent always is. This
    matters because local_version() defaults to "0.0.0" when no
    version.txt exists (true of a fresh git checkout, since that file is
    only ever created by apply_update()/install.ps1) - without this guard,
    running l10_manager.py directly from app-template/ for local testing
    looks exactly like a brand-new install running an ancient version, and
    the auto-updater will happily overwrite the dev checkout's own source
    files with whatever's currently published on GitHub the moment someone
    clicks Update Now (this happened for real during development - the
    working tree's uncommitted changes were silently clobbered)."""
    return (app_dir().parent / ".git").exists()


def local_version() -> str:
    version_file = app_dir() / "version.txt"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    return "0.0.0"


def _parse_version(v: str) -> tuple:
    parts = []
    for chunk in v.strip().split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(remote: str, local: str) -> bool:
    remote_t, local_t = _parse_version(remote), _parse_version(local)
    length = max(len(remote_t), len(local_t))
    remote_t = remote_t + (0,) * (length - len(remote_t))
    local_t = local_t + (0,) * (length - len(local_t))
    return remote_t > local_t


def fetch_manifest(timeout: float = MANIFEST_TIMEOUT_SECONDS) -> dict:
    with urllib.request.urlopen(MANIFEST_URL, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _prefs_path() -> Path:
    return app_dir() / "update_prefs.json"


def get_skipped_version() -> str:
    path = _prefs_path()
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return str(data.get("skip_version", ""))
    except (ValueError, OSError):
        return ""


def set_skipped_version(version: str) -> None:
    _prefs_path().write_text(json.dumps({"skip_version": version}), encoding="utf-8")


def check_for_update(ignore_skip: bool = False):
    """Returns the manifest dict if an update is available (and not skipped), else None."""
    if is_dev_checkout():
        return None
    try:
        manifest = fetch_manifest()
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None

    remote_version = str(manifest.get("version", "")).strip()
    if not remote_version or not is_newer(remote_version, local_version()):
        return None
    if not ignore_skip and remote_version == get_skipped_version():
        return None
    return manifest


def apply_update(manifest: dict, on_progress=None) -> None:
    """Downloads every manifest file into place and bumps version.txt.

    Only ever writes raw bytes to disk - nothing here is executed or
    evaluated as code. on_progress(completed_count, total_count, filename),
    if given, is called after each file finishes downloading - this runs on
    whatever thread calls apply_update() (l10_manager.py runs it on a
    background thread so the UI can show a progress bar without blocking
    the Tk mainloop for the whole download), so the callback itself must
    only touch thread-safe state, not Tkinter widgets directly.
    """
    if is_dev_checkout():
        raise RuntimeError(
            "Refusing to self-update a git checkout (app-template/) - this would overwrite "
            "uncommitted local changes with whatever's published on GitHub."
        )
    app_files = manifest.get("app_files", [])
    total = len(app_files)
    for index, entry in enumerate(app_files, start=1):
        url = f"{RAW_BASE}/{entry['src']}"
        dest = app_dir() / entry["dest"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=FILE_TIMEOUT_SECONDS) as resp:
            dest.write_bytes(resp.read())
        if on_progress is not None:
            on_progress(index, total, entry["dest"])

    version_text = str(manifest["version"])
    (app_dir() / "version.txt").write_text(version_text, encoding="utf-8")


def launch_new_install() -> None:
    """Sets up another L10 meeting by downloading install.ps1 to a real temp
    file and running it with -File - the same installer everyone else uses,
    same safe download-then-run pattern (never piped into iex/eval).
    """
    with urllib.request.urlopen(INSTALLER_URL, timeout=FILE_TIMEOUT_SECONDS) as resp:
        installer_bytes = resp.read()

    tmp = tempfile.NamedTemporaryFile(
        prefix="l10-manager-install-", suffix=".ps1", delete=False
    )
    try:
        tmp.write(installer_bytes)
    finally:
        tmp.close()

    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            tmp.name,
        ],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
