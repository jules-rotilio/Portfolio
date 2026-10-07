"""Run blocking media probes off the Qt UI thread and deliver their results."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QThreadPool, Signal

from media_toolkit.logging_setup import name_current_thread

LOGGER = logging.getLogger(__name__)


class BackgroundCalls(QObject):
    """Run callables on the global thread pool, one live request per key.

    Results and errors are delivered on the thread that owns this object (the
    UI thread). Submitting again for a key supersedes the previous request:
    superseded work that has not started is skipped, and late results are
    dropped, so a slow probe cannot overwrite a newer selection.
    """

    _finished = Signal(str, int, object, object)

    def __init__(self, parent: QObject | None = None) -> None:
        """Create an empty request table bound to the owning thread."""
        super().__init__(parent)
        self._generations: dict[str, int] = {}
        self._callbacks: dict[
            str, tuple[Callable[[Any], None], Callable[[Exception], None] | None]
        ] = {}
        self._finished.connect(self._deliver)

    def submit(
        self,
        key: str,
        function: Callable[[], Any],
        on_result: Callable[[Any], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Run function in the pool and call on_result or on_error with its outcome."""
        generation = self._generations.get(key, 0) + 1
        self._generations[key] = generation
        self._callbacks[key] = (on_result, on_error)

        def run() -> None:
            if self._generations.get(key) != generation:
                return
            name_current_thread(f"Background-{key}")
            result: Any = None
            error: Exception | None = None
            try:
                result = function()
            except Exception as caught:  # Delivered to on_error or logged below.
                error = caught
            try:
                self._finished.emit(key, generation, result, error)
            except RuntimeError:
                # The owning widget was destroyed while the call was running.
                pass

        QThreadPool.globalInstance().start(run)

    def cancel(self, key: str) -> None:
        """Drop the pending result for key; work already running still finishes."""
        if key in self._generations:
            self._generations[key] += 1
        self._callbacks.pop(key, None)

    def cancel_all(self) -> None:
        """Drop every pending result."""
        for key in list(self._generations):
            self.cancel(key)

    def _deliver(
        self, key: str, generation: int, result: Any, error: Exception | None
    ) -> None:
        """Invoke the current callbacks for a finished, still-wanted request."""
        if self._generations.get(key) != generation or key not in self._callbacks:
            return
        on_result, on_error = self._callbacks.pop(key)
        if error is None:
            on_result(result)
        elif on_error is not None:
            on_error(error)
        else:
            LOGGER.error(
                "Background call %r failed",
                key,
                exc_info=(type(error), error, error.__traceback__),
            )
