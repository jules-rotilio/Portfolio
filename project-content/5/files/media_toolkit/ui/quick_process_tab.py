"""Quick Process tab: one-off conversions of the file selected in Explorer."""

from __future__ import annotations

import logging
import math
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from media_toolkit.core.filesystem import media_kind
from media_toolkit.logging_setup import name_current_thread
from media_toolkit.media.ffmpeg_tools import ProcessingCancelled, find_tool, run_cancellable
from media_toolkit.processing.quick import (
    ANIMATED_CONVERSIONS,
    AUDIO_OUTPUT_SUFFIXES,
    FIXED_OUTPUT_SUFFIXES,
    available_operations,
    build_quick_command,
    convert_animated_webp_to_gif,
    extract_first_frame,
    format_part_length,
    probe_media_duration,
    probe_source,
    quick_output_path,
    selected_time_range,
    split_time_ranges,
)
from media_toolkit.processing.workflow import reserve_output_path
from media_toolkit.ui.background import BackgroundCalls
from media_toolkit.ui.preview import MediaPreviewWidget

LOGGER = logging.getLogger(__name__)


class _ProcessWorker(QThread):
    """Run a single long-lived processing task off the UI thread."""

    completed = Signal(str)

    def __init__(
        self,
        source: Path,
        companion: Path | None,
        destination: Path,
        options: dict[str, str],
    ) -> None:
        super().__init__()
        self.source = source
        self.companion = companion
        self.destination = destination
        self.options = options

    def run(self) -> None:
        """Execute the selected FFmpeg/Pillow operation and emit the final status message."""
        name_current_thread("QuickProcessWorker")
        LOGGER.info(
            "Starting quick process '%s' for %s -> %s",
            self.options.get("operation", "unknown"),
            self.source,
            self.destination,
        )
        if self.options["operation"] == "Extract first frame":
            try:
                extract_first_frame(self.source, self.destination)
            except (OSError, RuntimeError, ValueError) as error:
                self._report_failure(str(error), [self.destination])
            else:
                LOGGER.info("Quick process created %s", self.destination)
                self.completed.emit(f"Created {self.destination}")
            return

        destinations = [self.destination]
        try:
            part_count = int(self.options.get("split_count", "1"))
            if not 1 <= part_count <= 100:
                raise ValueError("Split count must be between 1 and 100.")
        except ValueError as error:
            self._report_failure(str(error), [self.destination])
            return
        part_options = [self.options]
        if part_count > 1:
            try:
                if self.options["operation"] not in ANIMATED_CONVERSIONS:
                    raise ValueError("Splitting is only supported for GIF/WebP conversions.")
                start, end = selected_time_range(self.options)
                if end is None:
                    end = probe_media_duration(self.source)
                ranges = split_time_ranges(start, end, part_count)
            except (OSError, RuntimeError, ValueError) as error:
                self._report_failure(str(error), [self.destination])
                return
            # Part files replace the single reserved destination, which only
            # served as the naming template.
            destinations = []
            try:
                for index in range(part_count):
                    destinations.append(self._split_destination(index + 1, part_count))
                self.destination.unlink(missing_ok=True)
            except OSError as error:
                self._report_failure(str(error), [self.destination, *destinations])
                return
            part_options = []
            for range_start, range_end in ranges:
                options = dict(self.options)
                options.update({
                    "start": str(range_start),
                    "end": str(range_end),
                    "from_start": "0",
                    "to_end": "0",
                })
                part_options.append(options)

        for destination, options in zip(destinations, part_options):
            if self.isInterruptionRequested():
                self._report_failure("Processing was cancelled.", destinations)
                return
            if options["operation"] == "Convert animated WebP to GIF":
                try:
                    convert_animated_webp_to_gif(self.source, destination, options)
                except (
                    Image.DecompressionBombError,
                    OSError,
                    RuntimeError,
                    ValueError,
                ) as error:
                    self._report_failure(str(error), destinations)
                    return
                continue

            try:
                ffmpeg = find_tool("ffmpeg")
                command = build_quick_command(
                    self.source, self.companion, destination, options, ffmpeg
                )
                # -y may only ever replace the placeholder reserved for this output.
                if Path(command[-1]) != destination:
                    raise ValueError(f"Output path does not match reserved {destination}.")
                result = run_cancellable(
                    command, timeout=3600, should_cancel=self.isInterruptionRequested
                )
            except ProcessingCancelled as error:
                self._report_failure(str(error), destinations)
                return
            except (
                OSError,
                RuntimeError,
                ValueError,
                subprocess.TimeoutExpired,
            ) as error:
                self._report_failure(str(error), destinations)
                return
            if result.returncode:
                self._report_failure(
                    result.stderr.strip() or "ffmpeg returned an error",
                    destinations,
                )
                return
        if part_count > 1:
            LOGGER.info(
                "Quick process created %d parts in %s",
                part_count,
                self.destination.parent,
            )
            self.completed.emit(f"Created {part_count} parts in {self.destination.parent}")
        else:
            LOGGER.info("Quick process created %s", self.destination)
            self.completed.emit(f"Created {self.destination}")

    def _split_destination(self, part_number: int, part_count: int) -> Path:
        return reserve_output_path(
            self.destination.parent,
            f"{self.destination.stem}_part_{part_number:02d}_of_{part_count:02d}",
            self.destination.suffix,
        )

    def _report_failure(self, reason: str, destinations: list[Path]) -> None:
        LOGGER.error("Quick process failed for %s: %s", self.source, reason)
        for destination in destinations:
            try:
                destination.unlink(missing_ok=True)
            except OSError as error:
                LOGGER.exception("Could not remove partial output %s", destination)
                reason += f"\nCould not remove partial output {destination}: {error}"
        self.completed.emit(f"Failed: {reason}")


class QuickProcessWidget(QWidget):
    """A compact media-processing form with source selection, timing controls, and output folder."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create the form controls, source preview, and processing worker lifecycle hooks."""
        super().__init__(parent)
        self.source: Path | None = None
        self.worker: _ProcessWorker | None = None
        self.companion_path: Path | None = None
        self._source_aspect_ratio: float | None = None
        self._source_duration: float | None = None
        self._probing_source = False
        self._background = BackgroundCalls(self)
        layout = QHBoxLayout(self)
        self.preview = MediaPreviewWidget()
        layout.addWidget(self.preview, 2)
        controls = QVBoxLayout()
        self.source_label = QLabel("Select a media file in Explorer.")
        self.source_label.setWordWrap(True)
        controls.addWidget(self.source_label)
        self.form = QFormLayout()
        self.operation = QComboBox()
        self.operation.currentTextChanged.connect(self._update_options_visibility)
        self.operation.currentTextChanged.connect(self._update_split_length_label)
        self.form.addRow("Operation", self.operation)
        self.from_start = QCheckBox("From start")
        self.from_start.setChecked(True)
        self.form.addRow("", self.from_start)
        self.start = QLineEdit("0")
        self.start.setDisabled(True)
        self.from_start.toggled.connect(self.start.setDisabled)
        self.form.addRow("Start time (seconds)", self.start)
        self.start.textChanged.connect(self._update_split_length_label)
        self.from_start.toggled.connect(self._update_split_length_label)
        self.to_end = QCheckBox("To end")
        self.to_end.setChecked(True)
        self.to_end.toggled.connect(self._update_split_length_label)
        self.form.addRow("", self.to_end)
        self.duration = QLineEdit("10")
        self.duration.setDisabled(True)
        self.to_end.toggled.connect(self.duration.setDisabled)
        self.duration.textChanged.connect(self._update_split_length_label)
        self.form.addRow("End time (seconds)", self.duration)
        self.fps = QLineEdit("30")
        self.form.addRow("Frame rate (fps)", self.fps)
        self.split_count = QSpinBox()
        self.split_count.setRange(1, 100)
        self.split_count.setValue(1)
        self.split_count.valueChanged.connect(self._update_split_length_label)
        self.split_length = QLabel("Each part: 00:00:00.000")
        split_row = QHBoxLayout()
        split_row.addWidget(self.split_count)
        split_row.addWidget(self.split_length, 1)
        self.form.addRow("Split into parts", split_row)
        self.max_colors = QComboBox()
        self.max_colors.addItems(["32", "64", "100", "128", "256"])
        self.max_colors.setCurrentText("100")
        self.form.addRow("Maximum GIF colors", self.max_colors)
        dimensions = QHBoxLayout()
        self.width = QLineEdit("1280")
        self.height = QLineEdit("720")
        self.width.textEdited.connect(self._update_height_from_width)
        self.height.textEdited.connect(self._update_width_from_height)
        dimensions.addWidget(self.width)
        dimensions.addWidget(QLabel("×"))
        dimensions.addWidget(self.height)
        self.form.addRow("Maximum dimensions (aspect ratio kept)", dimensions)
        webp_quality_row = QHBoxLayout()
        self.webp_quality_worst = QLabel("Worst")
        self.webp_quality = QSlider(Qt.Orientation.Horizontal)
        self.webp_quality.setRange(0, 100)
        self.webp_quality.setValue(80)
        self.webp_quality_value = QLabel("80")
        self.webp_quality_best = QLabel("Best")
        self.webp_quality.valueChanged.connect(
            lambda value: self.webp_quality_value.setText(str(value))
        )
        webp_quality_row.addWidget(self.webp_quality_worst)
        webp_quality_row.addWidget(self.webp_quality, 1)
        webp_quality_row.addWidget(self.webp_quality_value)
        webp_quality_row.addWidget(self.webp_quality_best)
        self.form.addRow("Animated WebP quality", webp_quality_row)
        self.audio_format = QComboBox()
        self.audio_format.addItems(list(AUDIO_OUTPUT_SUFFIXES))
        self.form.addRow("Audio format", self.audio_format)
        self.quality = QComboBox()
        self.quality.addItems(["Low", "Standard", "High"])
        self.quality.setCurrentText("Standard")
        self.form.addRow("Compression / quality", self.quality)
        self.sample_rate = QComboBox()
        self.sample_rate.addItems(["Original", "22050", "44100", "48000", "96000"])
        self.form.addRow("Sample rate (Hz)", self.sample_rate)
        self.companion = QLineEdit()
        self.companion.setReadOnly(True)
        browse_companion = QPushButton("Choose second file…")
        browse_companion.clicked.connect(self._choose_companion)
        companion_row = QHBoxLayout()
        companion_row.addWidget(self.companion, 1)
        companion_row.addWidget(browse_companion)
        self.form.addRow("Second media file", companion_row)
        self.output_folder = QLineEdit()
        browse_output = QPushButton("Browse…")
        browse_output.clicked.connect(self._choose_output_folder)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_folder, 1)
        output_row.addWidget(browse_output)
        self.form.addRow("Output folder", output_row)
        controls.addLayout(self.form)
        self.run_button = QPushButton("Process selected media")
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self._start_processing)
        controls.addWidget(self.run_button)
        self.status = QLabel()
        self.status.setWordWrap(True)
        controls.addWidget(self.status)
        controls.addStretch(1)
        layout.addLayout(controls, 3)
        self._update_options_visibility()
        self._update_split_length_label()

    def set_source(
        self, path: Path | None, metadata: dict[str, Any] | None = None
    ) -> None:
        """Bind a selected file to the widget and refresh runtime metadata for the active operation."""
        self._background.cancel("source")
        self._probing_source = False
        if path is None or media_kind(path) is None:
            self.source = None
            self._source_aspect_ratio = None
            self._source_duration = None
            self.companion_path = None
            self.companion.clear()
            self.source_label.setText("Select a supported media file in Explorer.")
            self.preview.clear_preview()
            self.operation.clear()
            self.run_button.setEnabled(False)
            return
        self.source = path
        self._source_aspect_ratio = None
        self._source_duration = None
        self.companion_path = None
        self.companion.clear()
        self.source_label.setText(str(path))
        self.output_folder.setText(str(path.parent))
        self.preview.show_file(path, metadata)
        # ffprobe/Pillow probing can take seconds, so it runs in the background;
        # processing stays disabled until the defaults below reflect this file.
        self._probing_source = True
        self.status.setText("Reading source settings…")
        self._background.submit(
            "source",
            lambda: probe_source(path),
            self._apply_source_probe,
        )
        self.operation.blockSignals(True)
        self.operation.clear()
        self.operation.addItems(available_operations(path))
        self.operation.blockSignals(False)
        self._update_run_button()
        self._update_options_visibility()
        self._update_split_length_label()

    def _apply_source_probe(
        self,
        probe: tuple[float | None, tuple[float, int, int] | None, str | None],
    ) -> None:
        """Fill duration, frame-rate, and size defaults from a finished probe."""
        duration, settings, settings_error = probe
        self._probing_source = False
        self._source_duration = duration
        if settings is None:
            self.status.setText(f"Could not read source frame settings: {settings_error}")
        else:
            fps, width, height = settings
            if width > 0 and height > 0:
                self._source_aspect_ratio = width / height
            self.fps.setText(f"{fps:.3f}".rstrip("0").rstrip(".") or "30")
            self.width.setText(str(width))
            self.height.setText(str(height))
            self.status.clear()
        self._update_run_button()
        self._update_options_visibility()
        self._update_split_length_label()

    def is_busy(self) -> bool:
        """Return whether a quick-process job is running."""
        return self.worker is not None and self.worker.isRunning()

    def stop_background_work(self) -> list[QThread]:
        """Cancel a running job without reporting back; return its thread.

        The running FFmpeg process is killed and its partial outputs removed.
        """
        self._background.cancel_all()
        if self.worker is None or not self.worker.isRunning():
            return []
        self.worker.completed.disconnect()
        self.worker.requestInterruption()
        return [self.worker]

    def _update_run_button(self) -> None:
        """Allow processing once a probed source is set and no job is running."""
        self.run_button.setEnabled(
            self.source is not None
            and not self._probing_source
            and (self.worker is None or not self.worker.isRunning())
        )

    def _update_height_from_width(self, width_text: str) -> None:
        """Keep dimensions proportional when the user edits width instead of height."""
        if self._source_aspect_ratio is None:
            return
        try:
            width = int(width_text)
        except ValueError:
            return
        if width > 0:
            height = max(1, round(width / self._source_aspect_ratio))
            self.height.setText(str(height))

    def _update_width_from_height(self, height_text: str) -> None:
        """Keep dimensions proportional when the user edits height instead of width."""
        if self._source_aspect_ratio is None:
            return
        try:
            height = int(height_text)
        except ValueError:
            return
        if height > 0:
            width = max(1, round(height * self._source_aspect_ratio))
            self.width.setText(str(width))

    def _choose_companion(self) -> None:
        """Choose an auxiliary media file for joins or append operations."""
        filename, _ = QFileDialog.getOpenFileName(self, "Select second media file")
        if filename:
            self.companion_path = Path(filename)
            self.companion.setText(filename)

    def _update_split_length_label(self, *_args: Any) -> None:
        """Refresh the per-part duration label for split conversions."""
        operation = self.operation.currentText()
        if operation not in ANIMATED_CONVERSIONS:
            self.split_length.setText("Each part: —")
            return
        try:
            start = 0.0 if self.from_start.isChecked() else float(self.start.text())
            end = (
                self._source_duration
                if self.to_end.isChecked()
                else float(self.duration.text())
            )
            if end is None or not math.isfinite(start) or not math.isfinite(end) or end <= start:
                raise ValueError
            each_length = (end - start) / self.split_count.value()
        except (ValueError, TypeError):
            self.split_length.setText("Each part: unavailable")
            return
        self.split_length.setText(f"Each part: {format_part_length(each_length)}")

    def _choose_output_folder(self) -> None:
        """Choose the folder that receives the converted output files."""
        initial = self.output_folder.text() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Select output folder", initial)
        if folder:
            self.output_folder.setText(folder)

    def _visible_options(self) -> dict[str, bool]:
        """Return which form rows the selected operation actually uses."""
        operation = self.operation.currentText()
        has_time_range = operation.startswith("Trim") or operation in ANIMATED_CONVERSIONS
        # Resizing keeps the frame rate setting only for moving sources: video,
        # or a GIF/WebP whose probe found more than one frame.
        moving_source = self.source is not None and (
            media_kind(self.source) == "video"
            or (
                self.source.suffix.lower() in {".gif", ".webp"}
                and bool(self._source_duration)
            )
        )
        return {
            "start": has_time_range,
            "from_start": has_time_range,
            "to_end": has_time_range,
            "duration": has_time_range,
            "fps": operation in ANIMATED_CONVERSIONS
            or (operation.startswith("Resize") and moving_source),
            # Only these operations build a GIF palette.
            "colors": operation in {"Convert video to GIF", "Convert animated WebP to GIF"},
            "dimensions": operation.startswith("Resize") or operation in ANIMATED_CONVERSIONS,
            "split": operation in ANIMATED_CONVERSIONS,
            "webp_quality": operation in {
                "Convert video to animated WebP",
                "Convert GIF to animated WebP",
            },
            "audio_format": operation == "Convert audio" or operation == "Extract audio",
            "quality": operation in {"Convert audio", "Trim audio", "Extract audio", "Append audio"},
            "sample_rate": operation in {"Convert audio", "Extract audio"},
            "companion": operation.startswith("Join") or operation.startswith("Append"),
        }

    def _update_options_visibility(self, _operation: str = "") -> None:
        """Show only the form rows the selected operation uses."""
        visibility = self._visible_options()
        row_indexes = {
            "from_start": 1,
            "start": 2,
            "to_end": 3,
            "duration": 4,
            "fps": 5,
            "split": 6,
            "colors": 7,
            "dimensions": 8,
            "webp_quality": 9,
            "audio_format": 10,
            "quality": 11,
            "sample_rate": 12,
            "companion": 13,
        }
        for row, row_index in row_indexes.items():
            self.form.setRowVisible(row_index, visibility[row])

    def _start_processing(self) -> None:
        """Validate the form and launch the background worker for the selected operation."""
        if self.source is None:
            return
        operation = self.operation.currentText()
        options = {
            "operation": operation,
            "start": self.start.text(),
            "end": self.duration.text(),
            "duration": self.duration.text(),
            "max_length": self.duration.text(),
            "from_start": "1" if self.from_start.isChecked() else "0",
            "to_end": "1" if self.to_end.isChecked() else "0",
            "fps": self.fps.text(),
            "max_colors": self.max_colors.currentText(),
            "width": self.width.text(),
            "height": self.height.text(),
            "split_count": str(self.split_count.value()),
            "webp_quality": str(self.webp_quality.value()),
            "format": self.audio_format.currentText(),
            "quality": self.quality.currentText(),
            "sample_rate": self.sample_rate.currentText(),
        }
        # Hidden rows keep values from other operations; do not let them apply.
        visible = self._visible_options()
        if not visible["from_start"]:
            options.update(from_start="1", to_end="1")
        if not visible["split"]:
            options["split_count"] = "1"
        if operation in {"Convert audio", "Extract audio"}:
            suffix = AUDIO_OUTPUT_SUFFIXES[self.audio_format.currentText()]
        else:
            suffix = FIXED_OUTPUT_SUFFIXES.get(operation, self.source.suffix)
        folder = Path(self.output_folder.text()).expanduser()
        if not folder.is_dir():
            QMessageBox.warning(self, "Invalid output folder", "Choose an existing output folder.")
            return
        try:
            destination = quick_output_path(self.source, folder, suffix)
        except OSError as error:
            QMessageBox.warning(self, "Could not create output file", str(error))
            return
        companion = self.companion_path
        self.run_button.setEnabled(False)
        self.status.setText("Processing…")
        # Long-running FFmpeg work is kept off the UI thread so the preview and
        # controls remain responsive during conversion or split-output generation.
        worker = _ProcessWorker(self.source, companion, destination, options)
        worker.completed.connect(self._processing_completed)
        # completed is emitted just before the thread stops running.
        worker.finished.connect(self._update_run_button)
        worker.start()
        self.worker = worker

    def _processing_completed(self, message: str) -> None:
        self.status.setText(message)
        self._update_run_button()
