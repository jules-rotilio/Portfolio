"""Tests for writing XDG metadata tags without raising on missing data.
"""

from __future__ import annotations

import errno
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_toolkit.core.xdg_tags import write_xdg_tags


class XdgTagTests(unittest.TestCase):
    """Exercises the XDG tag writer for no-op missing-tag cleanup."""
    def test_removing_absent_tags_is_a_successful_noop(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "media"
            path.touch()

            with patch(
                "media_toolkit.core.xdg_tags.os.removexattr",
                side_effect=OSError(errno.ENODATA, "No data available"),
            ):
                self.assertTrue(write_xdg_tags(path, set()))


if __name__ == "__main__":
    unittest.main()
