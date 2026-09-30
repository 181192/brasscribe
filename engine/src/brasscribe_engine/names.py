"""Names that reach the file system: job, audio and reference ids, relative file names, audio suffixes.

Every id a client sends is checked here before it is joined to a directory. The checks are on the
string alone, so they hold for Windows paths too: a backslash, a drive letter or a `\\\\host\\share`
prefix never gets as far as a path join (which would replace the root) or a file-system call.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath

ID = re.compile(r"[A-Za-z0-9._-]{1,200}")
# What a job may read as its input, and what uploads keep as their suffix: audio, and video with a sound track.
AUDIO_SUFFIXES = frozenset({
    ".wav", ".wave", ".flac", ".mp3", ".m4a", ".m4b", ".aac", ".ogg", ".oga", ".opus", ".aif", ".aiff", ".aifc",
    ".caf", ".wma", ".amr", ".3gp", ".3gpp", ".3g2", ".mka", ".weba",
    ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".wmv", ".mpg", ".mpeg",
})


def valid_id(value: str | None) -> bool:
    """Letters, digits, '.', '_' and '-'; not '.' or '..'. A trailing '.' is refused too: Windows drops it."""
    return bool(value) and ID.fullmatch(value) is not None and not value.endswith(".")


def valid_relpath(value: str | None) -> bool:
    """A relative file name below a directory, '/'-separated: no absolute path, drive, backslash or '..'."""
    if not value or "\\" in value or ":" in value or "\0" in value:
        return False
    if PurePosixPath(value).is_absolute() or PureWindowsPath(value).anchor:
        return False
    return all(part not in ("", ".", "..") for part in value.split("/"))



def is_audio(path: Path | str) -> bool:
    return Path(path).suffix.lower() in AUDIO_SUFFIXES
