"""CLI entry point for the MediaToolkit application.

This module starts the desktop app when run as a script.
"""

from media_toolkit.app import run


if __name__ == "__main__":
    raise SystemExit(run())
