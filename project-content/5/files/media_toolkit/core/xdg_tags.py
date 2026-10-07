"""Read and write comma-separated XDG tags in user extended attributes."""

from __future__ import annotations

import errno
import os
from pathlib import Path


_UNSUPPORTED_ERRNOS = {
    errno.ENODATA,
    errno.ENOTSUP,
    errno.EOPNOTSUPP,
    errno.ENOSYS,
}


def read_xdg_tags(path: Path) -> set[str] | None:
    """Return tags, or None when user xattrs are not supported on this file.

    The stored value is a comma-separated list of trimmed tags.
    """
    try:
        raw = os.getxattr(path, "user.xdg.tags")
    except OSError as error:
        if error.errno in _UNSUPPORTED_ERRNOS:
            return None
        raise
    return {tag.strip() for tag in raw.decode("utf-8").split(",") if tag.strip()}


def write_xdg_tags(path: Path, tags: set[str]) -> bool:
    """Write XDG tags and return False if the filesystem lacks xattr support.

    An empty set removes the attribute; removing an already absent attribute
    succeeds. Returns False only when user xattrs are unsupported.
    """
    try:
        if tags:
            os.setxattr(path, "user.xdg.tags", ",".join(sorted(tags)).encode("utf-8"))
        else:
            os.removexattr(path, "user.xdg.tags")
    except OSError as error:
        if not tags and error.errno == errno.ENODATA:
            return True
        if error.errno in _UNSUPPORTED_ERRNOS:
            return False
        raise
    return True
