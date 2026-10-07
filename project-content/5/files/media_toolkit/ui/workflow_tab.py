"""Workflow builder UI for saving, loading, and running multi-step media processing sequences."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from media_toolkit.core.database import MediaDatabase
from media_toolkit.logging_setup import name_current_thread
from media_toolkit.processing.workflow import OUTPUT_FORMATS, run_workflow

LOGGER = logging.getLogger(__name__)


class WorkflowWorker(QThread):
    """Background executor that runs a workflow and reports created vs. failed outputs."""

    completed = Signal(object, object)

    def __init__(
        self,
        inputs: list[Path],
        output_folder: Path,
        steps: list[dict[str, str]],
    ) -> None:
        super().__init__()
        self.inputs = inputs
        self.output_folder = output_folder
        self.steps = steps

    def run(self) -> None:
        """Run the queued processing steps in a worker thread so the UI stays responsive."""
        name_current_thread("WorkflowWorker")
        LOGGER.info(
            "Starting workflow for %d input(s) into %s",
            len(self.inputs),
            self.output_folder,
        )
        try:
            outcomes = run_workflow(
                self.inputs,
                self.output_folder,
                self.steps,
                should_cancel=self.isInterruptionRequested,
            )
        except (OSError, ValueError) as error:
            LOGGER.exception("Workflow failed")
            self.completed.emit([], [str(error)])
        else:
            successes = [line for line in outcomes if line.startswith("Created ")]
            failures = [line for line in outcomes if not line.startswith("Created ")]
            for outcome in outcomes:
                (LOGGER.info if outcome.startswith("Created ") else LOGGER.error)(
                    "Workflow: %s", outcome
                )
            self.completed.emit(successes, failures)


class WorkflowWidget(QWidget):
    """Collect processing blocks, saved workflow names, and selected media for execution."""

    def __init__(self, database: MediaDatabase, parent: QWidget | None = None) -> None:
        """Initialize the workflow editor, saved workflow list, and run controls."""
        super().__init__(parent)
        self.database = database
        self.input_paths: list[Path] = []
        self.steps: list[dict[str, str]] = []
        self.output_folder = Path.home() / "MediaToolkit Output"
        self.worker: WorkflowWorker | None = None

        layout = QVBoxLayout(self)
        saved_bar = QHBoxLayout()
        self.saved_workflows = QComboBox()
        load_button = QPushButton("Load")
        save_button = QPushButton("Save")
        saved_bar.addWidget(QLabel("Saved workflows"))
        saved_bar.addWidget(self.saved_workflows, stretch=1)
        saved_bar.addWidget(load_button)
        saved_bar.addWidget(save_button)
        layout.addLayout(saved_bar)
        load_button.clicked.connect(self.load_workflow)
        save_button.clicked.connect(self.save_workflow)
        self._reload_workflow_names()

        block_bar = QHBoxLayout()
        self.block_type = QComboBox()
        self.block_type.addItems(["Trim", "Resize", "Convert format", "Extract audio"])
        add_block = QPushButton("Add block")
        remove_block = QPushButton("Remove block")
        block_bar.addWidget(self.block_type, stretch=1)
        block_bar.addWidget(add_block)
        block_bar.addWidget(remove_block)
        layout.addLayout(block_bar)
        add_block.clicked.connect(self.add_block)
        remove_block.clicked.connect(self.remove_block)

        self.steps_list = QListWidget()
        self.steps_list.setToolTip("Blocks run in order; format conversion should be last.")
        layout.addWidget(self.steps_list, stretch=2)

        input_bar = QHBoxLayout()
        self.input_label = QLabel("No input media selected")
        input_button = QPushButton("Choose input media…")
        input_bar.addWidget(self.input_label, stretch=1)
        input_bar.addWidget(input_button)
        layout.addLayout(input_bar)
        input_button.clicked.connect(self.choose_inputs)

        output_bar = QHBoxLayout()
        self.output_label = QLabel(str(self.output_folder))
        output_button = QPushButton("Output folder…")
        output_bar.addWidget(QLabel("Output"))
        output_bar.addWidget(self.output_label, stretch=1)
        output_bar.addWidget(output_button)
        layout.addLayout(output_bar)
        output_button.clicked.connect(self.choose_output_folder)

        run_bar = QHBoxLayout()
        self.run_button = QPushButton("Run workflow")
        self.status = QLabel("Add processing blocks, choose media, then run.")
        run_bar.addWidget(self.run_button)
        run_bar.addWidget(self.status, stretch=1)
        layout.addLayout(run_bar)
        self.run_button.clicked.connect(self.run)

        layout.addWidget(
            QLabel(
                "Blocks: trim by time, resize video, convert to MP4/WebM/GIF/WebP, "
                "or extract audio as MP3/WAV."
            )
        )

    def _reload_workflow_names(self) -> None:
        current = self.saved_workflows.currentText()
        self.saved_workflows.clear()
        self.saved_workflows.addItems(sorted(self.database.workflows()))
        if current:
            self.saved_workflows.setCurrentText(current)

    def _render_steps(self) -> None:
        self.steps_list.clear()
        for position, step in enumerate(self.steps, start=1):
            options = ", ".join(
                f"{key}={value}" for key, value in step.items() if key != "operation"
            )
            self.steps_list.addItem(f"{position}. {step['operation']}: {options}")

    def add_block(self) -> None:
        operation = self.block_type.currentText()
        operation_order = {
            "Trim": 0,
            "Resize": 1,
            "Convert format": 2,
            "Extract audio": 2,
        }
        if any(step["operation"] == operation for step in self.steps):
            QMessageBox.information(
                self,
                "Block already exists",
                "Use each processing block at most once in a workflow.",
            )
            return
        if self.steps and operation_order[operation] < operation_order[self.steps[-1]["operation"]]:
            QMessageBox.information(
                self,
                "Block order",
                "Add blocks in order: Trim, Resize, then one output format block.",
            )
            return
        if operation == "Trim":
            start, accepted = QInputDialog.getDouble(
                self, "Trim", "Start time (seconds):", 0, 0, 86400, 2
            )
            if not accepted:
                return
            duration, accepted = QInputDialog.getDouble(
                self, "Trim", "Duration (seconds):", 10, 0.01, 86400, 2
            )
            if not accepted:
                return
            step = {"operation": operation, "start": str(start), "duration": str(duration)}
        elif operation == "Resize":
            width, accepted = QInputDialog.getInt(
                self, "Resize", "Width:", 1280, 2, 16384
            )
            if not accepted:
                return
            height, accepted = QInputDialog.getInt(
                self, "Resize", "Height:", 720, 2, 16384
            )
            if not accepted:
                return
            step = {"operation": operation, "width": str(width), "height": str(height)}
        else:
            choices = (
                ["MP3", "WAV"]
                if operation == "Extract audio"
                else list(OUTPUT_FORMATS)
            )
            output_format, accepted = QInputDialog.getItem(
                self, operation, "Output format:", choices, 0, False
            )
            if not accepted:
                return
            step = {"operation": operation, "format": output_format}
        self.steps.append(step)
        self._render_steps()

    def remove_block(self) -> None:
        row = self.steps_list.currentRow()
        if 0 <= row < len(self.steps):
            del self.steps[row]
            self._render_steps()

    def choose_inputs(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Choose media files", str(Path.home())
        )
        if files:
            self.input_paths = [Path(path) for path in files]
            self.input_label.setText(f"{len(self.input_paths)} media file(s) selected")

    def choose_output_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose output folder", str(self.output_folder)
        )
        if folder:
            self.output_folder = Path(folder)
            self.output_label.setText(folder)

    def save_workflow(self) -> None:
        """Persist the current block list under a user-selected workflow name."""
        if not self.steps:
            QMessageBox.information(self, "Empty workflow", "Add at least one block first.")
            return
        name, accepted = QInputDialog.getText(self, "Save workflow", "Workflow name:")
        if not accepted or not name.strip():
            return
        try:
            self.database.save_workflow(name.strip(), self.steps)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Could not save workflow", str(error))
            return
        self._reload_workflow_names()
        self.saved_workflows.setCurrentText(name.strip())
        self.status.setText(f"Saved workflow: {name.strip()}")

    def load_workflow(self) -> None:
        """Load a saved workflow into the list and update the status message."""
        name = self.saved_workflows.currentText()
        steps = self.database.workflows().get(name)
        if steps is None:
            return
        self.steps = steps
        self._render_steps()
        self.status.setText(f"Loaded workflow: {name}")

    def is_busy(self) -> bool:
        """Return whether a workflow is being processed."""
        return self.worker is not None and self.worker.isRunning()

    def stop_background_work(self) -> list[QThread]:
        """Cancel a running workflow without reporting back; return its thread.

        The running FFmpeg process is killed and its partial output removed.
        """
        if self.worker is None or not self.worker.isRunning():
            return []
        self.worker.completed.disconnect()
        self.worker.requestInterruption()
        return [self.worker]

    def run(self) -> None:
        """Validate the selected media and launch the worker for the current step list."""
        if self.worker is not None and self.worker.isRunning():
            return
        if not self.input_paths:
            QMessageBox.information(self, "No input media", "Choose one or more media files.")
            return
        if not self.steps:
            QMessageBox.information(self, "Empty workflow", "Add at least one block.")
            return
        self.run_button.setEnabled(False)
        self.status.setText("Processing media…")
        # The worker thread owns the long-running processing loop so the form can
        # remain interactive while media is being converted and written to disk.
        worker = WorkflowWorker(self.input_paths, self.output_folder, list(self.steps))
        worker.completed.connect(self._on_completed)
        worker.start()
        self.worker = worker

    def _on_completed(self, successes: list[str], failures: list[str]) -> None:
        """Update the status bar after the background job finishes and surface any failures."""
        self.run_button.setEnabled(True)
        message = f"Created {len(successes)} output file(s); {len(failures)} failed/skipped."
        self.status.setText(message)
        if failures:
            QMessageBox.warning(self, "Workflow finished with issues", "\n".join(failures))
