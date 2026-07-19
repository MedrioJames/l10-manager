"""Windows Credential Manager wrapper (via ctypes + advapi32.dll).

Secrets (right now: just the Jira API token) must never live in Data/ -
that folder is designed to be shared with teammates for coverage, and
anything in Data/config.json could end up in someone else's hands. Storing
secrets in the OS credential store instead means they stay on the machine
that entered them: a teammate covering via the same shared folder on their
own PC gets prompted for their own token rather than inheriting yours,
since Windows Credential Manager is scoped to the local Windows user
account, not to a file path.

Target names are scoped by a hash of the install's own folder path, so
multiple L10 installs on the same machine (different meetings) don't
collide with each other.
"""

import ctypes
import hashlib
from ctypes import wintypes
from pathlib import Path
from typing import Optional

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class _CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
_advapi32.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIAL), wintypes.DWORD]
_advapi32.CredWriteW.restype = wintypes.BOOL
_advapi32.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(_CREDENTIAL))]
_advapi32.CredReadW.restype = wintypes.BOOL
_advapi32.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
_advapi32.CredDeleteW.restype = wintypes.BOOL
_advapi32.CredFree.argtypes = [ctypes.c_void_p]


def _target_name(app_dir: Path, secret_name: str) -> str:
    path_hash = hashlib.sha256(str(Path(app_dir).resolve()).encode("utf-8")).hexdigest()[:16]
    return f"L10Manager/{path_hash}/{secret_name}"


def set_secret(app_dir: Path, secret_name: str, value: str) -> None:
    target = _target_name(app_dir, secret_name)
    blob = value.encode("utf-16-le")
    blob_buffer = (ctypes.c_byte * len(blob)).from_buffer_copy(blob)

    cred = _CREDENTIAL()
    ctypes.memset(ctypes.byref(cred), 0, ctypes.sizeof(cred))
    cred.Type = CRED_TYPE_GENERIC
    cred.TargetName = target
    cred.CredentialBlobSize = len(blob)
    cred.CredentialBlob = ctypes.cast(blob_buffer, ctypes.POINTER(ctypes.c_byte))
    cred.Persist = CRED_PERSIST_LOCAL_MACHINE

    ok = _advapi32.CredWriteW(ctypes.byref(cred), 0)
    if not ok:
        raise OSError(f"Failed to save credential (Windows error {ctypes.get_last_error()})")


def get_secret(app_dir: Path, secret_name: str) -> Optional[str]:
    target = _target_name(app_dir, secret_name)
    cred_ptr = ctypes.POINTER(_CREDENTIAL)()
    ok = _advapi32.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(cred_ptr))
    if not ok:
        return None
    try:
        cred = cred_ptr.contents
        size = cred.CredentialBlobSize
        if size == 0:
            return ""
        raw = ctypes.string_at(cred.CredentialBlob, size)
        return raw.decode("utf-16-le")
    finally:
        _advapi32.CredFree(cred_ptr)


def delete_secret(app_dir: Path, secret_name: str) -> None:
    target = _target_name(app_dir, secret_name)
    _advapi32.CredDeleteW(target, CRED_TYPE_GENERIC, 0)
