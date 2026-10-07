"""Dialog for selecting a subset of media tags from a taxonomy tree."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class TagEditorDialog(QDialog):
    """Present tagged media categories in a scrollable checkbox dialog."""

    def __init__(
        self,
        taxonomy: dict[str, list[str]],
        selected_tags: set[str],
        parent: QWidget | None = None,
    ) -> None:
        """Create a checkbox grid for each taxonomy category and preselect active tags."""
        super().__init__(parent)
        self.setWindowTitle("Edit Media Tags")
        self.resize(480, 620)
        self.checkboxes: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        contents = QWidget()
        groups_layout = QVBoxLayout(contents)
        for category, tags in taxonomy.items():
            group = QGroupBox(category)
            group_layout = QVBoxLayout(group)
            for tag in tags:
                checkbox = QCheckBox(tag)
                checkbox.setChecked(tag in selected_tags)
                self.checkboxes[tag] = checkbox
                group_layout.addWidget(checkbox)
            groups_layout.addWidget(group)
        groups_layout.addStretch(1)
        scroll.setWidget(contents)
        layout.addWidget(scroll)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_tags(self) -> set[str]:
        """Return the set of checked tags as a normalized value for the parent workflow."""
        return {
            tag for tag, checkbox in self.checkboxes.items() if checkbox.isChecked()
        }
