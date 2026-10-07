"""Light and dark colour themes: Qt palette, stylesheet, and status colours."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

THEME_MODES = ("System", "Light", "Dark")
# Chevron images for drop-down lists, one per theme name.
_ICONS = Path(__file__).resolve().parent / "icons"


@dataclass(frozen=True)
class StatusColors:
    """Background and text colour for one catalog status."""

    background: str
    text: str


@dataclass(frozen=True)
class Theme:
    """A complete set of colours for the app."""

    name: str
    window: str  # Page background behind panels.
    surface: str  # Lists, inputs, and panels.
    surface_alt: str  # Alternating rows and hovered buttons.
    border: str
    text: str
    muted_text: str
    disabled_text: str  # Exempt from contrast minimums; must look inactive.
    accent: str  # Primary buttons, focus, and selection.
    accent_text: str
    danger: str
    statuses: dict[str, StatusColors]


# Text/background pairs are at least 4.5:1 (WCAG AA) in both themes.
LIGHT = Theme(
    name="Light",
    window="#f3f4f6",
    surface="#ffffff",
    surface_alt="#e9ecf1",
    border="#cfd4dc",
    text="#1f2328",
    muted_text="#57606a",
    disabled_text="#a3aab3",
    accent="#2563eb",
    accent_text="#ffffff",
    danger="#b42318",
    statuses={
        "not-indexed": StatusColors("#e5e7eb", "#374151"),
        "indexed": StatusColors("#fdf0c4", "#7a3e06"),
        "tagged": StatusColors("#d9f5e3", "#14532d"),
        "duplicate": StatusColors("#fde0dd", "#8a1c13"),
    },
)
DARK = Theme(
    name="Dark",
    window="#16181c",
    surface="#1f2227",
    surface_alt="#2a2e35",
    border="#3a3f47",
    text="#e6e8eb",
    muted_text="#a0a8b2",
    disabled_text="#5f6670",
    accent="#5b8cff",
    accent_text="#0b1020",
    danger="#ff8a80",
    statuses={
        "not-indexed": StatusColors("#2c3138", "#cfd5dc"),
        "indexed": StatusColors("#43350f", "#f8d77f"),
        "tagged": StatusColors("#173b28", "#9ee7b9"),
        "duplicate": StatusColors("#4a1f1d", "#ffb4ab"),
    },
)


def _palette(theme: Theme) -> QPalette:
    """Build the Qt palette that standard widgets draw with."""
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: theme.window,
        QPalette.ColorRole.WindowText: theme.text,
        QPalette.ColorRole.Base: theme.surface,
        QPalette.ColorRole.AlternateBase: theme.surface_alt,
        QPalette.ColorRole.Text: theme.text,
        QPalette.ColorRole.PlaceholderText: theme.muted_text,
        QPalette.ColorRole.Button: theme.surface,
        QPalette.ColorRole.ButtonText: theme.text,
        QPalette.ColorRole.ToolTipBase: theme.surface,
        QPalette.ColorRole.ToolTipText: theme.text,
        QPalette.ColorRole.Highlight: theme.accent,
        QPalette.ColorRole.HighlightedText: theme.accent_text,
        QPalette.ColorRole.Link: theme.accent,
        QPalette.ColorRole.BrightText: theme.danger,
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(theme.disabled_text))
    return palette


def _icon(name: str, theme: Theme) -> str:
    """Return the path of the theme's variant of an icon, for use in url()."""
    return (_ICONS / f"{name}-{theme.name.lower()}.svg").as_posix()


def _stylesheet(theme: Theme) -> str:
    """Return the stylesheet for buttons, inputs, tabs, and toolbars."""
    return f"""
    QPushButton, QToolButton {{
        background: {theme.surface};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: 6px;
        padding: 4px 10px;
    }}
    QPushButton:hover, QToolButton:hover {{ background: {theme.surface_alt}; }}
    QPushButton:pressed, QToolButton:pressed, QToolButton:checked {{
        background: {theme.border};
    }}
    QPushButton:disabled, QToolButton:disabled {{
        color: {theme.disabled_text};
        background: {theme.window};
    }}
    QPushButton:focus, QToolButton:focus {{ border-color: {theme.accent}; }}
    QToolButton[popupMode="2"] {{ padding-right: 20px; }}
    QToolButton::menu-indicator {{
        image: url("{_icon("chevron-down", theme)}");
        width: 10px;
        height: 6px;
        subcontrol-origin: padding;
        subcontrol-position: center right;
        right: 6px;
    }}
    QComboBox {{ padding-right: 22px; }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: center right;
        width: 20px;
        border: none;
    }}
    QComboBox::down-arrow {{
        image: url("{_icon("chevron-down", theme)}");
        width: 10px;
        height: 6px;
    }}
    QToolButton#navButton {{ padding: 4px 8px; font-size: 14px; }}
    QToolButton#primaryButton, QPushButton#primaryButton {{
        background: {theme.accent};
        color: {theme.accent_text};
        border-color: {theme.accent};
        font-weight: 600;
    }}
    QToolButton#primaryButton:disabled {{
        background: {theme.surface_alt};
        color: {theme.disabled_text};
        border-color: {theme.border};
    }}
    QToolButton[active="true"] {{
        border-color: {theme.accent};
        color: {theme.accent};
        font-weight: 600;
    }}
    QToolButton#dangerButton {{ color: {theme.danger}; }}
    QToolButton#dangerButton:disabled {{ color: {theme.disabled_text}; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background: {theme.surface};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: 6px;
        padding: 4px 6px;
        selection-background-color: {theme.accent};
        selection-color: {theme.accent_text};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {theme.accent}; }}
    QSpinBox, QDoubleSpinBox {{ padding-right: 22px; }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        subcontrol-origin: border;
        width: 20px;
        border: none;
        background: transparent;
    }}
    QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-position: top right; }}
    QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-position: bottom right; }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover,
    QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
        background: {theme.surface_alt};
    }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
        image: url("{_icon("chevron-up", theme)}");
        width: 10px;
        height: 6px;
    }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
        image: url("{_icon("chevron-down", theme)}");
        width: 10px;
        height: 6px;
    }}
    QCheckBox::indicator, QAbstractItemView::indicator {{
        width: 14px;
        height: 14px;
        border: 1px solid {theme.muted_text};
        border-radius: 3px;
        background: {theme.surface};
    }}
    QCheckBox::indicator:checked, QAbstractItemView::indicator:checked {{
        background: {theme.accent};
        border-color: {theme.accent};
        image: url("{_icon("check", theme)}");
    }}
    QCheckBox::indicator:disabled, QAbstractItemView::indicator:disabled {{
        border-color: {theme.disabled_text};
    }}
    QTreeView, QTreeWidget, QTableWidget, QListWidget {{
        background: {theme.surface};
        alternate-background-color: {theme.surface_alt};
        border: 1px solid {theme.border};
        border-radius: 6px;
    }}
    QHeaderView::section {{
        background: {theme.window};
        color: {theme.muted_text};
        border: none;
        border-bottom: 1px solid {theme.border};
        padding: 4px 6px;
    }}
    QTabWidget::pane {{ border: 1px solid {theme.border}; border-radius: 6px; top: -1px; }}
    QTabBar::tab {{
        background: transparent;
        color: {theme.muted_text};
        padding: 6px 14px;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{ color: {theme.text}; border-bottom-color: {theme.accent}; }}
    QTabBar::tab:hover {{ color: {theme.text}; }}
    QFrame#toolbarSeparator {{ background: {theme.border}; }}
    QLabel#mutedLabel {{ color: {theme.muted_text}; }}
    QProgressBar {{
        border: 1px solid {theme.border};
        border-radius: 6px;
        background: {theme.surface};
        text-align: center;
    }}
    QProgressBar::chunk {{ background: {theme.accent}; border-radius: 5px; }}
    QMenu {{ background: {theme.surface}; color: {theme.text}; border: 1px solid {theme.border}; }}
    QMenu::item:selected {{ background: {theme.accent}; color: {theme.accent_text}; }}
    QMenu::section {{ color: {theme.muted_text}; padding: 4px 8px; }}
    QStatusBar {{ color: {theme.muted_text}; }}
    """


class ThemeManager(QObject):
    """Hold the chosen mode, apply the matching theme, and announce changes."""

    changed = Signal()

    def __init__(self) -> None:
        """Start in System mode with the light theme until apply() runs."""
        super().__init__()
        self._mode = "System"
        self._theme = LIGHT
        self._applied = False
        self._following_system = False

    @property
    def mode(self) -> str:
        """Return "System", "Light", or "Dark"."""
        return self._mode

    @property
    def theme(self) -> Theme:
        """Return the theme currently applied."""
        return self._theme

    def set_mode(self, mode: str) -> None:
        """Choose a mode and apply its theme; System follows the desktop setting."""
        if mode not in THEME_MODES:
            mode = "System"
        self._mode = mode
        hints = QGuiApplication.styleHints()
        if mode == "System" and not self._following_system:
            hints.colorSchemeChanged.connect(self._on_system_scheme_changed)
            self._following_system = True
        elif mode != "System" and self._following_system:
            hints.colorSchemeChanged.disconnect(self._on_system_scheme_changed)
            self._following_system = False
        self._apply(self._resolve(mode))

    def _resolve(self, mode: str) -> Theme:
        """Return the theme for mode, asking the desktop in System mode."""
        if mode == "Dark":
            return DARK
        if mode == "Light":
            return LIGHT
        scheme = QGuiApplication.styleHints().colorScheme()
        return DARK if scheme == Qt.ColorScheme.Dark else LIGHT

    def _on_system_scheme_changed(self, _scheme: Qt.ColorScheme) -> None:
        """Re-apply when the desktop switches between light and dark."""
        self._apply(self._resolve("System"))

    def _apply(self, theme: Theme) -> None:
        """Install theme on the application and notify widgets if it changed."""
        if self._applied and theme is self._theme:
            return
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setStyle("Fusion")
            app.setPalette(_palette(theme))
            app.setStyleSheet(_stylesheet(theme))
        self._theme = theme
        self._applied = True
        self.changed.emit()


_manager: ThemeManager | None = None


def theme_manager() -> ThemeManager:
    """Return the app-wide theme manager, creating it on first use."""
    global _manager
    if _manager is None:
        _manager = ThemeManager()
    return _manager


def current_theme() -> Theme:
    """Return the theme currently applied."""
    return theme_manager().theme
