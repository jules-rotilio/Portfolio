"""The Preferences dialog for appearance, indexing, duplicates, and logs."""

from __future__ import annotations

import os

from PySide6.QtGui import QShowEvent

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from media_toolkit.app_settings import INT_SETTINGS, AppSettings
from media_toolkit.ui.theme import THEME_MODES


class SettingsDialog(QDialog):
    """Edit an AppSettings value; read the result with settings()."""

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        """Create the form, filled in from settings."""
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(520)
        self._spins: dict[str, QSpinBox] = {}
        self._group_boxes: list[QGroupBox] = []
        self._help_labels: list[QLabel] = []

        self.theme = QComboBox()
        self.theme.addItems(THEME_MODES)
        appearance = self._group("Appearance")
        self._add_row(appearance, "Theme", self.theme)
        self._add_setting(
            appearance,
            "Thumbnail size",
            "thumbnail_size",
            " px",
            "Width and height of thumbnails in grid view.",
        )

        indexing = self._group("Indexing")
        self._add_setting(
            indexing,
            "Files indexed at once",
            "index_threads",
            "",
            f"This computer has {os.cpu_count() or 1} CPU threads. Lower it "
            "to keep the system responsive, or on a slow hard disk.",
        )

        duplicates = self._group("Duplicates")
        self._add_setting(
            duplicates,
            "Image similarity",
            "duplicate_distance",
            " bits",
            "Differing bits allowed between two image fingerprints: 0 finds "
            "only near-identical images; higher values find more but risk "
            "false matches. Applies at the next Refresh duplicate groups.",
        )
        self._add_setting(
            duplicates,
            "Matching video frames",
            "duplicate_min_frames",
            " of 10",
            "Sampled frames that must look alike for two videos or animated "
            "GIFs to count as duplicates.",
        )

        logs = self._group("Logs")
        self._add_setting(
            logs,
            "Log files kept",
            "log_files_kept",
            "",
            "Older session logs are deleted at the next launch.",
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            lambda: self._load(AppSettings())
        )
        layout = QVBoxLayout(self)
        for group in self._group_boxes:
            layout.addWidget(group)
        layout.addWidget(buttons)
        self._load(settings)

    def _group(self, title: str) -> QVBoxLayout:
        """Create a titled section and return its layout."""
        box = QGroupBox(title, self)
        self._group_boxes.append(box)
        return QVBoxLayout(box)

    @staticmethod
    def _add_row(group: QVBoxLayout, label: str, field: QWidget) -> None:
        """Add a "label  field" row to a section."""
        row = QHBoxLayout()
        name = QLabel(label)
        name.setMinimumWidth(170)
        row.addWidget(name)
        row.addWidget(field, stretch=1)
        group.addLayout(row)

    def _add_setting(
        self, group: QVBoxLayout, label: str, name: str, suffix: str, help_text: str
    ) -> None:
        """Add a bounded number field and, below it, a line explaining it.

        The help text is a direct child of the section layout so it wraps to
        its full height (wrapped labels nested in form rows get clipped).
        """
        rule = INT_SETTINGS[name]
        spin = QSpinBox()
        spin.setRange(rule.minimum, rule.maximum)
        spin.setSuffix(suffix)
        spin.setToolTip(help_text)
        self._spins[name] = spin
        self._add_row(group, label, spin)
        help_label = QLabel(help_text)
        help_label.setObjectName("mutedLabel")
        help_label.setWordWrap(True)
        group.addWidget(help_label)
        self._help_labels.append(help_label)

    def showEvent(self, event: QShowEvent) -> None:
        """Size wrapped help texts for their real width, then fit the dialog.

        A window's size ignores how tall wrapped labels become, so without
        this the longer explanations overlap the next row.
        """
        super().showEvent(event)
        for label in self._help_labels:
            label.setMinimumHeight(label.heightForWidth(label.width()))
        self.adjustSize()

    def _load(self, settings: AppSettings) -> None:
        """Show settings in the form."""
        self.theme.setCurrentText(settings.theme)
        for name, spin in self._spins.items():
            spin.setValue(getattr(settings, name))

    def settings(self) -> AppSettings:
        """Return the values currently in the form."""
        return AppSettings(
            theme=self.theme.currentText(),
            **{name: spin.value() for name, spin in self._spins.items()},
        )
