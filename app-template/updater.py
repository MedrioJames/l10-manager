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


def apply_update(manifest: dict) -> None:
    """Downloads every manifest file into place and bumps version.txt.

    Only ever writes raw bytes to disk - nothing here is executed or
    evaluated as code.
    """
    for entry in manifest.get("app_files", []):
        url = f"{RAW_BASE}/{entry['src']}"
        dest = app_dir() / entry["dest"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=FILE_TIMEOUT_SECONDS) as resp:
            dest.write_bytes(resp.read())

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
