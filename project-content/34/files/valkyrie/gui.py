"""The valkyrie window (PyQt6).

Edits are kept in memory and only written when Apply is clicked, through the
same code as the command line (ops.py): backup, VCFG's write sequence, read-back
check. The only thing sent before Apply is the light preview, which the mouse
does not save.
"""
import copy
import json
import os
import sys
import time

from PyQt6.QtCore import QEvent, QPointF, QRect, QSettings, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QActionGroup, QColor, QPainter, QPalette, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QMainWindow, QMenu, QMessageBox, QPushButton, QRadioButton,
    QSlider, QSpinBox, QStackedWidget, QTabWidget, QToolButton, QToolTip, QVBoxLayout, QWidget,
)

from . import device, events, host, instance, keys, model, ops, paths, pfd, store, utf8_stdio

COMMON_SHORTCUTS = [
    ('Copy', 'Ctrl+C'), ('Paste', 'Ctrl+V'), ('Cut', 'Ctrl+X'), ('Undo', 'Ctrl+Z'),
    ('Redo', 'Ctrl+Shift+Z'), ('Select all', 'Ctrl+A'), ('Find', 'Ctrl+F'), ('Save', 'Ctrl+S'),
    ('New tab', 'Ctrl+T'), ('Close tab', 'Ctrl+W'), ('Switch window', 'Alt+Tab'),
    ('Close window', 'Alt+F4'), ('Show desktop', 'Win+D'), ('Lock screen', 'Win+L'),
]
COLOR_PRESETS = ['#FF0000', '#FF8000', '#FFFF00', '#00FF00', '#00FFFF', '#0000FF',
                 '#8000FF', '#FF00FF', '#FFFFFF']
MOUSE_NAMES = {'left': 'Left button', 'right': 'Right button', 'middle': 'Middle button'}
THEMES = [('system', 'Follow the desktop'), ('light', 'Light'), ('dark', 'Dark')]

# VCFG's pictures of the mouse (Konix artwork, read from the VCFG folder, not copied).
# Each view: file, visible part of the picture, and the numbered circle of each button
# (0-based button: centre x, centre y, radius) in picture pixels.
MOUSE_VIEWS = {
    'front': ('mouse-layout-front.png', QRect(32, 16, 425, 709),
              {0: (160, 177, 25), 1: (333, 178, 25), 2: (239, 175, 25), 3: (98, 201, 25),
               4: (285, 271, 25), 5: (285, 340, 25), 6: (195, 268, 25), 7: (192, 339, 25)}),
    'side': ('mouse-layout-side.png', QRect(0, 12, 1840, 640),
             {8: (846, 247, 62), 9: (1061, 215, 62), 10: (1270, 231, 62),
              11: (768, 431, 62), 12: (1302, 428, 62)}),
}
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_IMAGES = os.path.join('images', '0409', 'background')
# VCFG's folder next to this one, then (on Windows) where VCFG's setup installs it.
VCFG_IMAGES = [os.path.join(_REPO, folder, _IMAGES) for folder in ('Drakkar Valkyrie', 'Official Drakkar Valkyrie')]
if paths.WINDOWS:
    VCFG_IMAGES += [os.path.join(os.environ.get(var, ''), 'Drakkar Valkyrie', _IMAGES)
                    for var in ('ProgramFiles(x86)', 'ProgramFiles') if os.environ.get(var)]


def find_vcfg_images():
    """Folder holding VCFG's mouse pictures, or None."""
    candidates = [QSettings('valkyrie', 'valkyrie-gui').value('vcfg_images', ''),
                  os.environ.get('VALKYRIE_VCFG_IMAGES', ''), *VCFG_IMAGES]
    for folder in candidates:
        if folder and all(os.path.isfile(os.path.join(folder, f)) for f, _, _ in MOUSE_VIEWS.values()):
            return folder
    return None


class MouseView(QWidget):
    """One of VCFG's mouse pictures, with its numbered buttons clickable."""
    clicked = pyqtSignal(int, object)          # button (0-based), global position
    hovered = pyqtSignal(int)                  # button under the pointer, or -1

    def __init__(self, pixmap, crop, spots, describe):
        super().__init__()
        self.pixmap = pixmap.copy(crop)
        self.spots = {b: (x - crop.x(), y - crop.y(), r) for b, (x, y, r) in spots.items()}
        self.describe = describe               # button -> text for the tooltip
        self.hover = -1
        self.marked = -1                       # button highlighted from the list
        self.setMouseTracking(True)
        self.setMinimumSize(160, 100)

    def target(self):
        """Where the picture is drawn: as large as fits, keeping its shape."""
        size = self.pixmap.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        x, y = (self.width() - size.width()) // 2, (self.height() - size.height()) // 2
        return QRect(x, y, size.width(), size.height())

    def spot_at(self, pos):
        t = self.target()
        scale = t.width() / self.pixmap.width()
        for b, (x, y, r) in self.spots.items():
            dx, dy = pos.x() - (t.x() + x * scale), pos.y() - (t.y() + y * scale)
            if dx * dx + dy * dy <= (r * scale) ** 2:
                return b
        return -1

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self.target()
        p.drawPixmap(t, self.pixmap)
        scale = t.width() / self.pixmap.width()
        for b in {self.hover, self.marked} - {-1}:
            if b in self.spots:
                x, y, r = self.spots[b]
                p.setPen(QPen(self.palette().color(QPalette.ColorRole.Highlight), max(3.0, r * scale / 5)))
                p.drawEllipse(QPointF(t.x() + x * scale, t.y() + y * scale), r * scale + 2, r * scale + 2)

    def mouseMoveEvent(self, event):
        b = self.spot_at(event.position())
        if b != self.hover:
            self.hover = b
            self.setCursor(Qt.CursorShape.PointingHandCursor if b >= 0 else Qt.CursorShape.ArrowCursor)
            self.hovered.emit(b)
            self.update()
            if b >= 0:
                QToolTip.showText(event.globalPosition().toPoint(), f'Button {b + 1}: {self.describe(b)}', self)
            else:
                QToolTip.hideText()

    def leaveEvent(self, event):
        if self.hover != -1:
            self.hover = -1
            self.hovered.emit(-1)
            self.update()

    def mousePressEvent(self, event):
        b = self.spot_at(event.position())
        if b >= 0 and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(b, event.globalPosition().toPoint())

    def mark(self, b):
        if b != self.marked:
            self.marked = b
            self.update()


def dark_palette():
    p = QPalette()
    R, G = QPalette.ColorRole, QPalette.ColorGroup
    colors = {
        R.Window: '#202326', R.WindowText: '#fcfcfc', R.Base: '#141618', R.AlternateBase: '#1d1f22',
        R.ToolTipBase: '#292c30', R.ToolTipText: '#fcfcfc', R.PlaceholderText: '#8a8f94',
        R.Text: '#fcfcfc', R.Button: '#292c30', R.ButtonText: '#fcfcfc', R.BrightText: '#ff5555',
        R.Light: '#3a3e43', R.Midlight: '#31353a', R.Mid: '#4d5157', R.Dark: '#141618',
        R.Shadow: '#000000', R.Highlight: '#3daee9', R.HighlightedText: '#fcfcfc',
        R.Link: '#3daee9', R.LinkVisited: '#9b59b6',
    }
    for role, color in colors.items():
        p.setColor(role, QColor(color))
    for role in (R.WindowText, R.Text, R.ButtonText):
        p.setColor(G.Disabled, role, QColor('#6e7175'))
    p.setColor(G.Disabled, R.Highlight, QColor('#3a3e43'))
    return p


def apply_theme(app, name):
    """'system' keeps the desktop's style and colours; 'light'/'dark' use Fusion."""
    if not hasattr(app, 'system_look'):
        app.system_look = (app.style().name(), QPalette(app.palette()))
    style, palette = app.system_look
    if name == 'light':
        app.setStyle('Fusion')
        app.setPalette(app.style().standardPalette())
    elif name == 'dark':
        app.setStyle('Fusion')
        app.setPalette(dark_palette())
    else:
        app.setStyle(style)
        app.setPalette(palette)


def qt_mods(modifiers):
    """Qt keyboard modifiers -> the mouse's shortcut modifier bits."""
    bits = 0
    for flag, bit in ((Qt.KeyboardModifier.ControlModifier, 0x01), (Qt.KeyboardModifier.ShiftModifier, 0x02),
                      (Qt.KeyboardModifier.AltModifier, 0x04), (Qt.KeyboardModifier.MetaModifier, 0x08)):
        if modifiers & flag:
            bits |= bit
    return bits


def event_key(event):
    """HID usage of the physical key in a Qt key event (None if unknown).
    On Linux Qt reports the X/XKB key code, which is the Linux key code + 8; on
    Windows the set-1 scan code, with 0x100 added for extended (E0) keys."""
    if paths.WINDOWS:
        return keys.scancode_to_hid(event.nativeScanCode())
    return keys.evdev_to_hid(event.nativeScanCode() - 8)


def is_modifier(hid):
    return 0xE0 <= hid <= 0xE7


# --- Small widgets and dialogs ---------------------------------------------------

class KeyPicker(QWidget):
    """A key: chosen from a list, or captured by pressing it."""
    captured = pyqtSignal(int, int)          # HID usage, modifier bits held

    def __init__(self, code=0x04, skip_modifiers=False):
        super().__init__()
        self.skip_modifiers = skip_modifiers
        self.combo = QComboBox()
        for c, name in sorted(keys.HID_KEYS.items()):
            self.combo.addItem(name, c)
        self.set_code(code)
        self.button = QPushButton('Press a key…')
        self.button.setCheckable(True)
        self.button.toggled.connect(self._toggled)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.combo, 1)
        row.addWidget(self.button)

    def code(self):
        return self.combo.currentData()

    def set_code(self, code):
        i = self.combo.findData(code)
        if i >= 0:
            self.combo.setCurrentIndex(i)

    def _toggled(self, on):
        if on:
            self.button.setText('Waiting for a key…')
            self.grabKeyboard()
        else:
            self.button.setText('Press a key…')
            self.releaseKeyboard()

    def keyPressEvent(self, event):
        if not self.button.isChecked():
            return super().keyPressEvent(event)
        hid = event_key(event)
        if hid is None or (self.skip_modifiers and is_modifier(hid)):
            return
        self.set_code(hid)
        self.button.setChecked(False)
        self.captured.emit(hid, qt_mods(event.modifiers()))


def dialog(parent, title, layout_fn):
    """Run a small OK/Cancel dialog; layout_fn(form) adds the fields. -> accepted?"""
    d = QDialog(parent)
    d.setWindowTitle(title)
    form = QFormLayout(d)
    layout_fn(form)
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    box.accepted.connect(d.accept)
    box.rejected.connect(d.reject)
    form.addRow(box)
    # Keep the dialog (and so its fields) alive until the caller has read them.
    parent.last_dialog = d
    return d.exec() == QDialog.DialogCode.Accepted


class RecordDialog(QDialog):
    """Records key presses and releases (with the time between them) as macro steps."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('Record macro')
        self.steps = []
        self.last = None
        self.delays = QCheckBox('Record the delays between keys')
        self.delays.setChecked(True)
        self.view = QLabel('Press keys now. Mouse clicks and pauses can be added afterwards.')
        self.view.setWordWrap(True)
        self.view.setMinimumWidth(420)
        stop = QPushButton('Stop')
        stop.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        stop.clicked.connect(self.accept)
        cancel = QPushButton('Cancel')
        cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cancel.clicked.connect(self.reject)
        self.delays.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        lay = QVBoxLayout(self)
        lay.addWidget(self.delays)
        lay.addWidget(self.view)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(stop)
        lay.addLayout(row)

    def showEvent(self, event):
        super().showEvent(event)
        self.grabKeyboard()

    def done(self, result):
        self.releaseKeyboard()
        super().done(result)

    def _add(self, event, pressed):
        if event.isAutoRepeat():
            return
        hid = event_key(event)
        if hid is None:
            return
        now = time.monotonic()
        if self.delays.isChecked() and self.last is not None:
            self.steps.append(model.MacroStep('delay', max(1, min(65535, round((now - self.last) * 1000)))))
        self.last = now
        self.steps.append(model.MacroStep('key', hid, pressed))
        self.view.setText(', '.join(model.step_to_str(s) for s in self.steps))

    def keyPressEvent(self, event):
        self._add(event, True)

    def keyReleaseEvent(self, event):
        self._add(event, False)


class Task(QThread):
    finished_with = pyqtSignal(object, object)        # result, exception

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.finished_with.emit(self.fn(), None)
        except Exception as e:                       # shown to the user
            self.finished_with.emit(None, e)


class ListenThread(QThread):
    """Reads the mouse's own reports (events.Listener) and emits each event; on Linux
    and Windows alike. stop() returns within the read timeout."""
    reported = pyqtSignal(object)                    # events.Event
    lost = pyqtSignal()                              # the mouse was unplugged

    def __init__(self, listener):
        super().__init__()
        self.listener = listener
        self.stopping = False

    def run(self):
        try:
            while not self.stopping:
                for event in self.listener.read(timeout=0.25):
                    self.reported.emit(event)
        except (OSError, device.DeviceError):
            if not self.stopping:
                self.lost.emit()

    def stop(self):
        self.stopping = True
        self.wait()
        self.listener.close()


def monitor_scales(_cache=[0.0, False]):
    """True if valkyrie-monitor runs with exact_dpi on (so off-grid DPI is exact).
    Checked at most every 2 seconds (sliders call this while they move)."""
    from . import monitor
    if paths.WINDOWS:
        return False                            # no exact DPI on Windows yet (monitor_windows.py)
    if time.monotonic() - _cache[0] < 2.0:
        return _cache[1]
    try:
        scales = instance.running(monitor.NAME) and monitor.load_config(monitor.CONFIG).exact_dpi
    except (OSError, ValueError):
        scales = False
    _cache[:] = [time.monotonic(), scales]
    return scales


def load_from_mouse(mouse):
    """State of the mouse (with what the PC keeps beside it), plus macros in slots
    no button uses."""
    state = ops.read_state(mouse)
    extra = {}
    with mouse.session():
        for slot in range(device.MACRO_SLOTS):
            if slot not in state.macros:
                m = mouse.read_macro_slot(slot)
                if m is not None:
                    extra[slot] = m
    host.record(state.profiles, state.active)     # what valkyrie-monitor works from
    return state, extra


# --- Main window -------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, open_mouse=device.open_mouse, threaded=True, open_listener=None):
        super().__init__()
        self.open_mouse = open_mouse
        self.threaded = threaded
        self.open_listener = open_listener      # events.Listener: follow the mouse's own buttons
        self.listener = None
        self.mouse = None
        self.state = None
        self.edits = {}              # n -> Profile being edited
        self.saved_macros = {}       # slot -> Macro as on the mouse
        self.macros = {}             # slot -> Macro being edited
        self.current = None          # profile shown
        self.loading = False         # True while widgets are filled from the model
        self.previewed = False       # a light preview was sent since the last write
        self.task = None
        self.busy = False            # a task is talking to the mouse
        self.done_message = None     # shown once the mouse is read again after a write
        self.conflicts = []          # VCFG running (under Wine/Proton on Linux)
        self.setWindowTitle('Drakkar Valkyrie')
        self._menu()

        central = QWidget()
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.addLayout(self._top_row())
        self.tabs = QTabWidget()
        self.tabs.addTab(self._buttons_tab(), 'Buttons')
        self.tabs.addTab(self._dpi_tab(), 'DPI and polling')
        self.tabs.addTab(self._light_tab(), 'Light')
        self.tabs.addTab(self._macros_tab(), 'Macros')
        lay.addWidget(self.tabs, 1)
        lay.addLayout(self._bottom_row())

        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(60)
        self.preview_timer.timeout.connect(self._send_preview)

        self.conflict_timer = QTimer(self)
        self.conflict_timer.setInterval(3000)
        self.conflict_timer.timeout.connect(self.check_conflicts)
        self.conflict_timer.start()
        self.check_conflicts()
        QTimer.singleShot(0, self.reload)

    # Layout ------------------------------------------------------------------

    def _menu(self):
        settings = QSettings('valkyrie', 'valkyrie-gui')
        menu = self.menuBar().addMenu('&View').addMenu('&Theme')
        group = QActionGroup(self)
        current = settings.value('theme', 'system')
        for name, label in THEMES:
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(name == current)
            group.addAction(action)
            action.triggered.connect(lambda _=False, name=name: self.set_theme(name))
        self.menuBar().actions()[0].menu().addAction('Locate VCFG images…').triggered.connect(
            lambda: self.locate_images())
        if current != 'system':
            apply_theme(QApplication.instance(), current)

    def set_theme(self, name):
        QSettings('valkyrie', 'valkyrie-gui').setValue('theme', name)
        apply_theme(QApplication.instance(), name)

    def _top_row(self):
        row = QHBoxLayout()
        row.addWidget(QLabel('Profile:'))
        self.profile_group = QButtonGroup(self)
        self.profile_buttons = []
        for n in range(device.PROFILES):
            b = QPushButton(str(n + 1))
            b.setCheckable(True)
            self.profile_group.addButton(b, n)
            self.profile_buttons.append(b)
            row.addWidget(b)
        self.profile_group.idClicked.connect(self.show_profile)
        self.make_active = QPushButton('Make active')
        self.make_active.setToolTip('Switch the mouse to this profile (like pressing the button under it)')
        self.make_active.clicked.connect(self.activate_profile)
        row.addWidget(self.make_active)
        row.addStretch()
        self.status = QLabel()
        row.addWidget(self.status)
        reload_button = QPushButton('Reload')
        reload_button.setToolTip('Read the mouse again (unapplied changes are lost)')
        reload_button.clicked.connect(lambda: self.confirm_discard() and self.reload())
        row.addWidget(reload_button)
        return row

    def _buttons_tab(self):
        w = QWidget()
        outer = QHBoxLayout(w)
        self.picture = QWidget()
        outer.addWidget(self.picture, 1)
        self._mouse_pictures()
        lst = QWidget()
        outer.addWidget(lst)
        grid = QGridLayout(lst)
        grid.setContentsMargins(0, 0, 0, 0)
        self.action_buttons = []
        for b in range(model.BUTTONS):
            grid.addWidget(QLabel(f'Button {b + 1}'), b, 0)
            tb = QToolButton()
            tb.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            tb.setMinimumWidth(320)
            if b == model.BUTTONS - 1:
                tb.setEnabled(False)
                tb.setToolTip('The profile switch under the mouse; VCFG never changes it')
            else:
                tb.setMenu(self._action_menu(b))
                tb.installEventFilter(self)                 # hover -> mark it on the picture
            self.action_buttons.append(tb)
            grid.addWidget(tb, b, 1)
        grid.setRowStretch(model.BUTTONS, 1)
        return w

    def _mouse_pictures(self):
        """Front/side pictures beside the button list (needs VCFG's images)."""
        lay = self.picture.layout() or QVBoxLayout(self.picture)
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    item.layout().takeAt(0).widget().deleteLater()
        self.views = {}
        folder = find_vcfg_images()
        if folder is None:
            hint = QLabel('VCFG\'s mouse pictures were not found.\nView → Locate VCFG images… '
                          'and pick its images/0409/background folder.')
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setWordWrap(True)
            lay.addWidget(hint)
            return
        row = QHBoxLayout()
        self.view_stack = QStackedWidget()
        self.view_buttons = QButtonGroup(self)
        for i, (name, (file, crop, spots)) in enumerate(MOUSE_VIEWS.items()):
            view = MouseView(QPixmap(os.path.join(folder, file)), crop, spots,
                             lambda b: model.describe_action(self.profile().buttons[b]) if self.state else '')
            view.clicked.connect(self.picture_clicked)
            view.hovered.connect(self.picture_hovered)
            self.views[name] = view
            self.view_stack.addWidget(view)
            button = QPushButton(name.capitalize())
            button.setCheckable(True)
            button.setChecked(i == 0)
            self.view_buttons.addButton(button, i)
            row.addWidget(button)
        self.view_buttons.idClicked.connect(self.view_stack.setCurrentIndex)
        lay.addLayout(row)
        lay.addWidget(self.view_stack, 1)

    def locate_images(self):
        folder = QFileDialog.getExistingDirectory(self, 'VCFG images folder (images/0409/background)',
                                                  find_vcfg_images() or os.path.expanduser('~'))
        if not folder:
            return
        if not all(os.path.isfile(os.path.join(folder, f)) for f, _, _ in MOUSE_VIEWS.values()):
            QMessageBox.warning(self, 'Drakkar Valkyrie', 'That folder does not hold mouse-layout-front.png '
                                'and mouse-layout-side.png.')
            return
        QSettings('valkyrie', 'valkyrie-gui').setValue('vcfg_images', folder)
        self._mouse_pictures()

    def show_button_on_picture(self, b):
        """Mark button b on the picture that shows it (switching front/side), or clear."""
        for i, (name, view) in enumerate(self.views.items()):
            if b in view.spots:
                self.view_stack.setCurrentIndex(i)
                self.view_buttons.button(i).setChecked(True)
            view.mark(b if b in view.spots else -1)

    def picture_clicked(self, b, where):
        self.action_buttons[b].setFocus()
        self.action_buttons[b].menu().popup(where)

    def picture_hovered(self, b):
        for i, tb in enumerate(self.action_buttons):
            tb.setDown(i == b)              # show which row the picture's button is

    def eventFilter(self, obj, event):
        if obj in getattr(self, 'action_buttons', []) and getattr(self, 'views', None):
            if event.type() == QEvent.Type.Enter:
                self.show_button_on_picture(self.action_buttons.index(obj))
            elif event.type() == QEvent.Type.Leave:
                self.show_button_on_picture(-1)
        return super().eventFilter(obj, event)

    def _action_menu(self, b):
        menu = QMenu(self)

        def add(m, label, action):
            m.addAction(label).triggered.connect(lambda _=False: self.set_button(b, action))

        sub = menu.addMenu('Mouse button')
        for kind in ('left', 'right', 'middle', 'back', 'forward'):
            add(sub, model.SIMPLE[kind][1], model.Action(kind))
        sub = menu.addMenu('DPI')
        for kind in ('dpi-cycle', 'dpi-up', 'dpi-down'):
            add(sub, model.SIMPLE[kind][1], model.Action(kind))
        sub = menu.addMenu('Report rate')
        for kind in ('rate-up', 'rate-down'):
            add(sub, model.SIMPLE[kind][1], model.Action(kind))
        add(menu, 'Profile switch', model.Action('profile-switch'))
        sub = menu.addMenu('Media and browser')
        for usage, label in keys.CONSUMER.items():
            add(sub, label, model.Action('media', code=usage))
        sub = menu.addMenu('Common shortcuts')
        for label, text in COMMON_SHORTCUTS:
            mods, code, code2 = keys.parse_shortcut(text)
            add(sub, f'{label} ({text})', model.Action('shortcut', code=code, mods=mods, code2=code2))
        menu.addSeparator()
        menu.addAction('Key…').triggered.connect(lambda: self.edit_key(b))
        menu.addAction('Shortcut…').triggered.connect(lambda: self.edit_shortcut(b))
        menu.addAction('Fire key (repeated clicks)…').triggered.connect(lambda: self.edit_fire(b))
        menu.addAction('Macro…').triggered.connect(lambda: self.edit_macro_action(b))
        menu.addSeparator()
        add(menu, 'Disable', model.Action('disable'))
        return menu

    def _dpi_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        box = QGroupBox('DPI levels (the DPI button steps through the levels that are on)')
        grid = QGridLayout(box)
        for col, text in enumerate(['Level', 'On', '', 'DPI', 'Y DPI', 'Mouse uses', 'Default']):
            grid.addWidget(QLabel(f'<b>{text}</b>'), 0, col)
        self.dpi_rows = []
        self.dpi_used = []
        self.default_group = QButtonGroup(self)
        fine = model.DPI_FINE_STEP
        for i in range(model.DPI_LEVELS):
            on = QCheckBox()
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(model.DPI_MIN // fine, model.DPI_MAX // fine)
            slider.setPageStep(model.DPI_STEP // fine)
            slider.setMinimumWidth(260)
            x = QSpinBox()
            y = QSpinBox()
            for spin in (x, y):
                spin.setRange(model.DPI_MIN, model.DPI_MAX)
                spin.setSingleStep(fine)
            used = QLabel()
            used.setToolTip('The mouse only has steps of 250 and uses the larger of X and Y for both')
            default = QRadioButton()
            self.default_group.addButton(default, i)
            for col, widget in enumerate([QLabel(str(i + 1)), on, slider, x, y, used, default]):
                grid.addWidget(widget, i + 1, col)
            on.toggled.connect(lambda checked, i=i: self.dpi_toggled(i, checked))
            slider.valueChanged.connect(lambda v, i=i: self.dpi_changed(i, x=v * fine, slider=True))
            x.editingFinished.connect(lambda i=i: self.dpi_changed(i, x=self.dpi_rows[i][2].value()))
            y.editingFinished.connect(lambda i=i: self.dpi_changed(i, y=self.dpi_rows[i][3].value()))
            self.dpi_rows.append((on, slider, x, y))
            self.dpi_used.append(used)
        self.default_group.idClicked.connect(self.dpi_default)
        self.separate_y = QCheckBox('Separate X and Y DPI')
        self.separate_y.toggled.connect(self.separate_y_toggled)
        grid.addWidget(self.separate_y, model.DPI_LEVELS + 1, 0, 1, 4)
        self.dpi_note = QLabel()
        self.dpi_note.setWordWrap(True)
        grid.addWidget(self.dpi_note, model.DPI_LEVELS + 2, 0, 1, 7)
        lay.addWidget(box)

        box = QGroupBox('Polling rate')
        row = QHBoxLayout(box)
        self.polling_group = QButtonGroup(self)
        for value, hz in sorted(model.POLLING_HZ.items(), key=lambda kv: kv[1]):
            r = QRadioButton(f'{hz} Hz')
            self.polling_group.addButton(r, value)
            row.addWidget(r)
        row.addStretch()
        self.polling_group.idClicked.connect(self.polling_changed)
        lay.addWidget(box)
        lay.addWidget(self._windows_box())
        lay.addStretch()
        return w

    def _windows_box(self):
        """VCFG's Windows pointer settings: on Windows, edited and applied like in VCFG;
        on Linux shown greyed out and kept for .pfd files."""
        box = QGroupBox('Windows pointer settings' if paths.WINDOWS else
                        'Windows pointer settings (applied by VCFG and VMON on Windows only)')
        form = QFormLayout(box)
        self.windows_fields = {}
        for name, label, (low, high), suffix in [
                ('pointer_speed', 'Pointer speed', (1, 20), ' (10 = unchanged)'),
                ('acceleration', 'Acceleration', (0, 3), ' (0 = off)'),
                ('scroll_lines', 'Scroll speed', (1, 100), ' lines'),
                ('double_click_ms', 'Double-click speed', (1, 5000), ' ms')]:
            spin = QSpinBox()
            spin.setRange(low, high)
            spin.setSuffix(suffix)
            spin.valueChanged.connect(self.windows_changed)
            form.addRow(label, spin)
            self.windows_fields[name] = spin
        self.windows_note = QLabel()
        self.windows_note.setWordWrap(True)
        form.addRow(self.windows_note)
        if paths.WINDOWS:
            box.setToolTip('Applied to Windows on Apply and Make active, and by valkyrie-monitor when the '
                           'profile is switched on the mouse, as VCFG and VMON do.')
        else:
            box.setEnabled(False)
            box.setToolTip('Not used on Linux: set these in your desktop\'s mouse settings. valkyrie keeps '
                           'them from imported .pfd files and the factory settings, and writes them to '
                           'exported .pfd files.')
        return box

    def windows_changed(self):
        if self.loading:
            return
        values = {name: spin.value() for name, spin in self.windows_fields.items()}
        self.profile().windows = model.WindowsSettings(**values)
        self.fill_windows_note()
        self.changed()

    def apply_windows_settings(self, n):
        """On Windows, apply profile n's pointer settings (VCFG does on Apply and on a
        profile switch); ignored on Linux and where none are known."""
        w = self.edits.get(n).windows if n in self.edits else None
        if not paths.WINDOWS or w is None:
            return
        from . import winsettings
        try:
            winsettings.apply(w)
        except OSError as e:
            QMessageBox.warning(self, 'Drakkar Valkyrie', str(e))

    def _light_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        row = QHBoxLayout()
        self.color_button = QPushButton()
        self.color_button.setFixedSize(64, 32)
        self.color_button.clicked.connect(self.pick_color)
        self.color_edit = QLineEdit()
        self.color_edit.setInputMask('\\#HHHHHH')
        self.color_edit.setFixedWidth(90)
        self.color_edit.editingFinished.connect(lambda: self.set_color(self.color_edit.text()))
        row.addWidget(self.color_button)
        row.addWidget(self.color_edit)
        for hex_color in COLOR_PRESETS:
            b = QPushButton()
            b.setFixedSize(24, 24)
            b.setStyleSheet(f'background: {hex_color}; border: 1px solid palette(mid)')
            b.setToolTip(hex_color)
            b.clicked.connect(lambda _=False, c=hex_color: self.set_color(c))
            row.addWidget(b)
        row.addStretch()
        form.addRow('Colour', row)
        self.brightness = QComboBox()
        for value, name in model.BRIGHTNESS.items():
            self.brightness.addItem(name.capitalize(), value)
        self.brightness.activated.connect(self.light_changed)
        form.addRow('Brightness', self.brightness)
        self.breathing = QComboBox()
        for value, name in model.BREATHING.items():
            self.breathing.addItem('Off (steady)' if name == 'off' else f'{name.capitalize()} speed', value)
        self.breathing.activated.connect(self.light_changed)
        form.addRow('Breathing', self.breathing)
        self.live = QCheckBox('Show changes on the mouse right away (saved only by Apply)')
        self.live.setChecked(True)
        form.addRow('', self.live)
        return w

    def _macros_tab(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        self.slot_list = QListWidget()
        self.slot_list.setMaximumWidth(300)
        self.slot_list.currentRowChanged.connect(lambda _: self.fill_macro())
        lay.addWidget(self.slot_list)
        right = QVBoxLayout()
        self.macro_info = QLabel()
        self.macro_info.setWordWrap(True)
        right.addWidget(self.macro_info)
        self.step_list = QListWidget()
        right.addWidget(self.step_list, 1)
        text_row = QHBoxLayout()
        text_row.addWidget(QLabel('As text:'))
        self.steps_text = QLineEdit()
        self.steps_text.setPlaceholderText('A down, wait 50, A up, mouse:left down, mouse:left up')
        self.steps_text.editingFinished.connect(self.steps_text_edited)
        text_row.addWidget(self.steps_text)
        right.addLayout(text_row)
        loops_row = QHBoxLayout()
        loops_row.addWidget(QLabel('Run it'))
        self.loops = QSpinBox()
        self.loops.setRange(1, model.MACRO_MAX_LOOPS)
        self.loops.valueChanged.connect(self.loops_changed)
        loops_row.addWidget(self.loops)
        loops_row.addWidget(QLabel('time(s) per press. "Repeat while held" is chosen on the button.'))
        loops_row.addStretch()
        right.addLayout(loops_row)
        lay.addLayout(right, 1)
        col = QVBoxLayout()
        for label, slot in [('Add key…', self.add_key_step), ('Add mouse click…', self.add_mouse_step),
                            ('Add pause…', self.add_delay_step), ('Record keys…', self.record_steps),
                            (None, None), ('Move up', lambda: self.move_step(-1)),
                            ('Move down', lambda: self.move_step(1)), ('Delete', self.delete_step),
                            ('Clear', self.clear_steps)]:
            if label is None:
                col.addSpacing(12)
                continue
            b = QPushButton(label)
            b.clicked.connect(slot)
            col.addWidget(b)
        col.addStretch()
        lay.addLayout(col)
        return w

    def _bottom_row(self):
        row = QHBoxLayout()
        self.file_buttons = []
        for label, slot, tip in [
            ('Import .pfd…', self.import_pfd, 'Load a VCFG profile file into this profile'),
            ('Export .pfd…', self.export_pfd, 'Save this profile as a VCFG profile file'),
            ('Load JSON…', self.load_json, 'Load profiles saved with "Export JSON" or "valkyrie export"'),
            ('Export JSON…', self.export_json, 'Save all profiles as shown here'),
            ('Factory settings…', self.factory, 'Load VCFG\'s factory settings (written by Apply)'),
            ('Backup', self.backup, f'Save a raw copy of the mouse in {store.BACKUP_DIR}'),
            ('Restore…', self.restore, 'Write a backup back to the mouse'),
        ]:
            b = QPushButton(label)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            row.addWidget(b)
            self.file_buttons.append(b)
        row.addStretch()
        self.revert_button = QPushButton('Revert')
        self.revert_button.setToolTip('Forget the changes not applied yet')
        self.revert_button.clicked.connect(self.revert)
        row.addWidget(self.revert_button)
        self.apply_button = QPushButton('Apply')
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(self.apply)
        row.addWidget(self.apply_button)
        return row

    # Talking to the mouse ------------------------------------------------------

    def run(self, message, fn, then):
        """Run fn() (device I/O) off the GUI thread, then then(result)."""
        self.centralWidget().setEnabled(False)
        self.busy = True
        self.statusBar().showMessage(message)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        def finished(result, error):
            QApplication.restoreOverrideCursor()
            self.centralWidget().setEnabled(True)
            self.busy = False
            self.statusBar().clearMessage()
            if error is not None:
                self.update_status()
                QMessageBox.critical(self, 'Drakkar Valkyrie', str(error))
                return
            then(result)
            self.update_status()

        if not self.threaded:
            try:
                result, error = fn(), None
            except Exception as e:
                result, error = None, e
            finished(result, error)
            return
        if self.task is not None:
            self.task.wait()                # the previous thread may still be unwinding
        self.task = Task(fn)
        self.task.finished_with.connect(finished)
        self.task.start()

    def get_mouse(self):
        if self.mouse is None:
            self.mouse = self.open_mouse()
        return self.mouse

    def reload(self):
        def read():
            try:
                return load_from_mouse(self.get_mouse())
            except (OSError, device.DeviceError):
                self.mouse = None               # unplugged: open it again next time
                raise
        self.run('Reading the mouse…', read, self.loaded)

    def loaded(self, result):
        state, extra = result
        self.state = state
        self.edits = copy.deepcopy(state.profiles)
        self.saved_macros = {**extra, **state.macros}
        self.macros = copy.deepcopy(self.saved_macros)
        self.previewed = False
        if self.current is None or self.current not in self.edits:
            self.current = state.active if state.active in self.edits else min(self.edits, default=0)
        if state.errors:
            QMessageBox.warning(self, 'Drakkar Valkyrie', 'Some settings could not be decoded and cannot '
                                'be edited:\n' + '\n'.join(f'{k + 1 if isinstance(k, int) else k}: {v}'
                                                           for k, v in state.errors.items()))
        self.show_profile(self.current)
        if self.done_message:
            self.statusBar().showMessage(self.done_message, 8000)
            self.done_message = None
        self.start_listening()

    # The mouse's own buttons ----------------------------------------------------------

    def start_listening(self):
        if self.listener is not None or self.open_listener is None:
            return
        try:
            self.listener = ListenThread(self.open_listener())
        except (OSError, device.DeviceError):
            return
        self.listener.reported.connect(self.mouse_event)
        self.listener.lost.connect(self.stop_listening)
        self.listener.start()

    def stop_listening(self):
        if self.listener is not None:
            self.listener.stop()
            self.listener = None

    def mouse_event(self, event):
        """The profile, DPI level or report rate was changed with the mouse's buttons.
        The mouse saves it; values the user has not edited here follow it."""
        if self.state is None:
            return
        if event.kind == 'profile' and 0 <= event.value < device.PROFILES:
            self.state.active = event.value
            message = f'Profile {event.value + 1} chosen on the mouse'
        elif event.kind in ('dpi', 'rate') and self.state.active in self.state.profiles:
            n = self.state.active
            saved, edit, blocks = self.state.profiles[n], self.edits.get(n), self.state.blocks.get(n)
            if event.kind == 'dpi':
                if not 0 <= event.value < model.DPI_LEVELS:
                    return
                if edit is not None and edit.dpi_selected == saved.dpi_selected:
                    edit.dpi_selected = event.value
                saved.dpi_selected = event.value
                if blocks:
                    blocks['dpi'] = blocks['dpi'][:1] + bytes([event.value]) + blocks['dpi'][2:]
                message = f'DPI level {event.value + 1} chosen on the mouse (profile {n + 1})'
            else:
                if event.value not in model.POLLING_HZ:
                    return
                if edit is not None and edit.polling == saved.polling:
                    edit.polling = event.value
                saved.polling = event.value
                if blocks:
                    blocks['polling'] = bytes([event.value])
                message = f'Report rate {model.POLLING_HZ[event.value]} Hz chosen on the mouse (profile {n + 1})'
            if n == self.current:
                self.loading = True
                self.fill_dpi()
                self.loading = False
        else:
            return
        self.statusBar().showMessage(message, 6000)
        self.update_status()

    def write_allowed(self):
        found = device.conflicting_programs()
        if not found:
            return True
        answer = QMessageBox.warning(
            self, 'Drakkar Valkyrie',
            f'{device.conflict_text(found)} and also talks to the mouse, which can '
            'mix up the transfers. Close it first.\n\nWrite anyway?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    # State helpers ------------------------------------------------------------

    def profile(self):
        return self.edits[self.current]

    def profile_dirty(self, n):
        return (n in self.edits and
                store.profile_to_dict(self.edits[n]) != store.profile_to_dict(self.state.profiles[n]))

    def macro_dirty(self, slot):
        m, old = self.macros.get(slot), self.saved_macros.get(slot)
        if old is None:
            return bool(m and m.steps)
        if m is None:
            return True
        return m.loops != old.loops or m.steps != old.steps

    def dirty(self):
        return (self.state is not None and
                (any(self.profile_dirty(n) for n in self.edits) or
                 any(self.macro_dirty(s) for s in range(device.MACRO_SLOTS))))

    def macro_users(self, slot):
        return [(n, b) for n, p in sorted(self.edits.items())
                for b, a in enumerate(p.buttons) if a.kind == 'macro' and a.code == slot]

    def check_conflicts(self):
        found = device.conflicting_programs()
        if found != self.conflicts:
            self.conflicts = found
            self.update_status()

    def update_status(self):
        ready = self.state is not None
        for w in [self.tabs, self.make_active, self.apply_button, self.revert_button] + self.file_buttons:
            w.setEnabled(ready)
        if not ready:
            self.status.setText('Mouse not read')
            for b in self.profile_buttons:
                b.setEnabled(False)
            return
        text = f'Active profile: {self.state.active + 1}'
        if self.conflicts:
            text += f'   ⚠ {", ".join(self.conflicts)} running'
        self.status.setText(text)
        for n, b in enumerate(self.profile_buttons):
            label = str(n + 1)
            if n == self.state.active:
                label += ' (active)'
            if self.profile_dirty(n):
                label += ' *'
            b.setText(label)
            b.setEnabled(n in self.edits)
        dirty = self.dirty()
        self.apply_button.setEnabled(dirty)
        self.revert_button.setEnabled(dirty)
        self.make_active.setEnabled(self.current != self.state.active)
        self.setWindowTitle('Drakkar Valkyrie' + (' *' if dirty else ''))

    def changed(self):
        if not self.loading:
            self.update_status()

    # Filling the widgets ----------------------------------------------------------

    def show_profile(self, n):
        if n not in self.edits:
            return
        self.current = n
        self.profile_buttons[n].setChecked(True)
        self.loading = True
        try:
            self.fill_buttons()
            self.fill_dpi()
            self.fill_light()
            self.fill_slots()
        finally:
            self.loading = False
        self.update_status()

    def fill_buttons(self):
        for b, tb in enumerate(self.action_buttons):
            text = model.describe_action(self.profile().buttons[b])
            changed = self.profile().buttons[b] != self.state.profiles[self.current].buttons[b]
            tb.setText(text + ('   (changed)' if changed else ''))

    def fill_dpi(self):
        p = self.profile()
        separate = any(lv.wanted[0] != lv.wanted[1] or lv.x != lv.y for lv in p.dpi_levels if lv.enabled)
        if separate:
            self.separate_y.setChecked(True)
        for i, (on, slider, x, y) in enumerate(self.dpi_rows):
            lv = p.dpi_levels[i]
            # A level that is off may hold no value; show the minimum then.
            wx, wy = (max(v, model.DPI_MIN) for v in lv.wanted)
            on.setChecked(lv.enabled)
            slider.setValue(wx // model.DPI_FINE_STEP)
            x.setValue(wx)
            y.setValue(wy)
            y.setVisible(self.separate_y.isChecked())
            for widget in (slider, x, y):
                widget.setEnabled(lv.enabled)
            self.fill_dpi_used(i)
        self.default_group.button(p.dpi_selected).setChecked(True)
        button = self.polling_group.button(p.polling)
        if button:
            button.setChecked(True)
        self.fill_windows()

    def fill_dpi_used(self, i):
        lv = self.profile().dpi_levels[i]
        used = self.dpi_used[i]
        if not lv.enabled:
            used.setText('')
        else:
            text = str(lv.x) if lv.x == lv.y else f'{lv.x} × {lv.y}'
            used.setText(text if lv.exact else f'<b>{text} *</b>')
        off = [n + 1 for n, level in enumerate(self.profile().dpi_levels) if level.enabled and not level.exact]
        if not off:
            self.dpi_note.setText('The mouse has DPI steps of 250 (250-4000). Values in between can be '
                                  'asked for in steps of 50, as in VCFG.')
        elif paths.WINDOWS:
            self.dpi_note.setText('* Between the mouse\'s steps of 250: the mouse uses the value shown '
                                  '(exact values need VCFG\'s driver, which valkyrie cannot drive yet). '
                                  'Exported .pfd files keep the exact value.')
        elif monitor_scales():
            self.dpi_note.setText('* Between the mouse\'s steps of 250: valkyrie-monitor scales the '
                                  'movement, so the DPI asked for is exact (like VCFG\'s driver on Windows).')
        else:
            self.dpi_note.setText('* Between the mouse\'s steps of 250: the mouse uses the value shown. '
                                  'To get the exact value, run valkyrie-monitor with exact_dpi = true '
                                  '(it scales the movement, like VCFG\'s driver on Windows). Exported '
                                  '.pfd files keep the exact value.')

    def fill_windows(self):
        w = self.profile().windows
        loading, self.loading = self.loading, True          # setValue is not an edit
        for name, spin in self.windows_fields.items():
            spin.setValue(getattr(w or model.WindowsSettings(), name))
        self.loading = loading
        self.fill_windows_note()

    def fill_windows_note(self):
        w = self.profile().windows
        if paths.WINDOWS:
            self.windows_note.setText('Applied to Windows on Apply and Make active; kept on this PC and '
                                      'written to exported .pfd files.' if w is not None else
                                      'Not set for this profile: change a value to use it, or Windows keeps '
                                      'its own settings.')
        else:
            self.windows_note.setText(
                'From the imported .pfd file or the factory settings; written to exported .pfd files.'
                if w is not None else 'Not set for this profile: exported .pfd files get these defaults.')

    def fill_light(self):
        light = self.profile().light
        hex_color = '#{:02X}{:02X}{:02X}'.format(*light.rgb)
        self.color_button.setStyleSheet(f'background: {hex_color}; border: 1px solid palette(mid)')
        self.color_edit.setText(hex_color)
        self.brightness.setCurrentIndex(self.brightness.findData(light.brightness))
        self.breathing.setCurrentIndex(self.breathing.findData(light.breathing))

    def fill_slots(self):
        row = max(self.slot_list.currentRow(), 0)
        self.slot_list.blockSignals(True)
        self.slot_list.clear()
        for slot in range(device.MACRO_SLOTS):
            m = self.macros.get(slot)
            users = self.macro_users(slot)
            text = f'Macro {slot + 1}'
            if m is None or not m.steps:
                text += ' (empty)'
            if users:
                text += ': ' + ', '.join(f'P{n + 1} button {b + 1}' for n, b in users)
            elif m is not None and m.steps:
                text += ': not used'
            if self.macro_dirty(slot):
                text += ' *'
            self.slot_list.addItem(text)
        self.slot_list.setCurrentRow(row)
        self.slot_list.blockSignals(False)
        self.fill_macro()

    def slot(self):
        return max(self.slot_list.currentRow(), 0)

    def fill_macro(self):
        slot = self.slot()
        m = self.macros.get(slot)
        steps = m.steps if m else []
        self.step_list.clear()
        self.step_list.addItems([model.step_to_str(s) for s in steps])
        self.steps_text.setText(', '.join(model.step_to_str(s).replace(' ms', '') for s in steps))
        self.steps_text.setCursorPosition(0)
        was = self.loading
        self.loading = True
        self.loops.setValue(m.loops if m else 1)
        self.loading = was
        users = self.macro_users(slot)
        info = f'Macro {slot + 1}: {len(steps)} of {model.MACRO_MAX_STEPS} steps. '
        if users:
            info += 'Used by ' + ', '.join(f'profile {n + 1} button {b + 1}' for n, b in users) + '.'
        else:
            info += ('No button uses it, so it is only saved once you assign it to a button '
                     '(Buttons tab → Macro…).')
        self.macro_info.setText(info)

    # Editing: buttons --------------------------------------------------------------

    def set_button(self, b, action):
        self.profile().buttons[b] = action
        self.fill_buttons()
        self.fill_slots()
        self.changed()

    def edit_key(self, b):
        current = self.profile().buttons[b]
        picker = KeyPicker(current.code if current.kind == 'key' else 0x04)
        if dialog(self, f'Button {b + 1}: key', lambda f: (
                f.addRow(QLabel('The key is a position on a US keyboard: on AZERTY, "Q" types "a".\n'
                                '"Press a key…" captures the key you press, whatever your layout.')),
                f.addRow('Key', picker))):
            self.set_button(b, model.Action('key', code=picker.code()))

    def edit_shortcut(self, b):
        current = self.profile().buttons[b]
        picker = KeyPicker(current.code if current.kind == 'shortcut' else 0x06, skip_modifiers=True)
        boxes = {}
        for name, bit in keys.MODIFIERS:
            boxes[bit] = QCheckBox(name)
            boxes[bit].setChecked(current.kind == 'shortcut' and bool(current.mods & bit))

        def captured(_hid, mods):
            for bit, box in boxes.items():
                box.setChecked(bool(mods & bit))
        picker.captured.connect(captured)
        has_second = current.kind == 'shortcut' and bool(current.code2)
        picker2 = KeyPicker(current.code2 if has_second else 0x06, skip_modifiers=True)
        second = QCheckBox('Second key')
        second.setToolTip('Pressed together with the first key, e.g. Ctrl+K+C. VCFG stores two keys '
                          'too; check it on the mouse before relying on it.')
        second.setChecked(has_second)
        picker2.setEnabled(has_second)
        second.toggled.connect(picker2.setEnabled)

        def layout(f):
            row = QHBoxLayout()
            for box in boxes.values():
                row.addWidget(box)
            f.addRow(QLabel('Tick the modifiers, or press the whole shortcut after "Press a key…".\n'
                            'Shortcuts the desktop uses itself (Alt+Tab, Win+L) must be ticked.'))
            f.addRow('Modifiers', row)
            f.addRow('Key', picker)
            f.addRow(second, picker2)
        if dialog(self, f'Button {b + 1}: shortcut', layout):
            mods = sum(bit for bit, box in boxes.items() if box.isChecked())
            code2 = picker2.code() if second.isChecked() and picker2.code() != picker.code() else 0
            self.set_button(b, model.Action('shortcut', code=picker.code(), mods=mods, code2=code2))

    def edit_fire(self, b):
        current = self.profile().buttons[b]
        target = QComboBox()
        for name, bit in model.MOUSE_BITS.items():
            target.addItem(MOUSE_NAMES[name], 0x80 | bit)
        target.addItem('Keyboard key', 0)
        picker = KeyPicker()
        times, delay = QSpinBox(), QSpinBox()
        times.setRange(1, 255)
        delay.setRange(1, 255)
        delay.setSuffix(' ms')
        times.setValue(3)
        delay.setValue(10)
        if current.kind == 'fire':
            if current.code & 0x80:
                target.setCurrentIndex(max(target.findData(current.code), 0))
            else:
                target.setCurrentIndex(target.findData(0))
                picker.set_code(current.code)
            times.setValue(current.times)
            delay.setValue(current.delay)
        picker.setEnabled(target.currentData() == 0)
        target.currentIndexChanged.connect(lambda _: picker.setEnabled(target.currentData() == 0))
        if dialog(self, f'Button {b + 1}: fire key', lambda f: (
                f.addRow('Press', target), f.addRow('Key', picker),
                f.addRow('Times', times), f.addRow('Time between presses', delay))):
            code = target.currentData() or picker.code()
            self.set_button(b, model.Action('fire', code=code, times=times.value(), delay=delay.value()))

    def edit_macro_action(self, b):
        current = self.profile().buttons[b]
        slots = QComboBox()
        for slot in range(device.MACRO_SLOTS):
            m = self.macros.get(slot)
            summary = ', '.join(model.step_to_str(s) for s in m.steps) if m and m.steps else '(empty)'
            if len(summary) > 60:
                summary = summary[:57] + '…'
            slots.addItem(f'Macro {slot + 1}: {summary}', slot)
        repeat = QCheckBox('Repeat while the button is held')
        if current.kind == 'macro':
            slots.setCurrentIndex(max(slots.findData(current.code), 0))
            repeat.setChecked(current.repeat)
        if dialog(self, f'Button {b + 1}: macro', lambda f: (
                f.addRow(QLabel('Edit the macro itself in the Macros tab.')),
                f.addRow('Macro', slots), f.addRow('', repeat))):
            self.set_button(b, model.Action('macro', code=slots.currentData(), repeat=repeat.isChecked()))

    # Editing: DPI and polling -------------------------------------------------------

    def dpi_toggled(self, i, checked):
        if self.loading:
            return
        p = self.profile()
        lv = p.dpi_levels[i]
        if not checked and i == p.dpi_selected:
            self.refuse('This is the default level; choose another default first.')
        elif not checked and sum(level.enabled for level in p.dpi_levels) == 1:
            self.refuse('At least one DPI level must stay on.')
        elif checked:
            lv.enabled = True
            spins = self.dpi_rows[i]
            lv.set(*(lv.wanted if all(lv.wanted) else (spins[2].value(), spins[3].value()
                                                       if self.separate_y.isChecked() else spins[2].value())))
        else:
            lv.enabled = False
        self.loading = True
        self.fill_dpi()
        self.loading = False
        self.changed()

    def dpi_changed(self, i, x=None, y=None, slider=False):
        if self.loading:
            return
        lv = self.profile().dpi_levels[i]
        wx, wy = lv.wanted
        if x is not None:
            wx = model.dpi_value(x)
            if not self.separate_y.isChecked():
                wy = wx
        if y is not None:
            wy = model.dpi_value(y)
        if (wx, wy) != lv.wanted or lv.x != lv.y:
            lv.set(wx, wy)
        self.loading = True
        on, sl, xs, ys = self.dpi_rows[i]
        if not slider:
            sl.setValue(wx // model.DPI_FINE_STEP)
        xs.setValue(wx)
        ys.setValue(wy)
        self.fill_dpi_used(i)
        self.loading = False
        self.changed()

    def dpi_default(self, i):
        p = self.profile()
        if not p.dpi_levels[i].enabled:
            self.refuse(f'DPI level {i + 1} is off.')
            self.default_group.button(p.dpi_selected).setChecked(True)
            return
        p.dpi_selected = i
        self.changed()

    def separate_y_toggled(self, on):
        for _, _, _, y in self.dpi_rows:
            y.setVisible(on)
        if not on and not self.loading and self.state is not None:
            for lv in self.profile().dpi_levels:
                if lv.enabled and (lv.wanted[0] != lv.wanted[1] or lv.x != lv.y):
                    lv.set(lv.wanted[0])
            self.loading = True
            self.fill_dpi()
            self.loading = False
            self.changed()

    def polling_changed(self, value):
        self.profile().polling = value
        self.changed()

    def refuse(self, message):
        QMessageBox.information(self, 'Drakkar Valkyrie', message)

    # Editing: light -------------------------------------------------------------

    def pick_color(self):
        light = self.profile().light
        before = light.rgb
        d = QColorDialog(QColor(*light.rgb), self)
        d.currentColorChanged.connect(lambda c: self.set_color(c.name()))
        if d.exec() != QDialog.DialogCode.Accepted:
            self.set_color('#{:02X}{:02X}{:02X}'.format(*before))

    def set_color(self, text):
        try:
            rgb = model.light_color(text)
        except ValueError:
            return
        self.profile().light.rgb = rgb
        self.light_changed()

    def light_changed(self, *_):
        light = self.profile().light
        light.brightness = self.brightness.currentData()
        light.breathing = self.breathing.currentData()
        self.loading = True
        self.fill_light()
        self.loading = False
        if self.live.isChecked():
            self.preview_timer.start()
        self.changed()

    def _send_preview(self):
        if self.mouse is None:
            return
        if self.busy:
            self.preview_timer.start()
            return
        try:
            self.mouse.preview_light(self.profile().light)
            self.previewed = True
        except (OSError, device.DeviceError) as e:
            self.statusBar().showMessage(f'Preview failed: {e}', 8000)

    def undo_preview(self):
        """Show the active profile's saved light again after previews."""
        if self.previewed and self.mouse is not None and self.state.active in self.state.profiles:
            try:
                self.mouse.preview_light(self.state.profiles[self.state.active].light)
            except (OSError, device.DeviceError):
                pass
            self.previewed = False

    # Editing: macros --------------------------------------------------------------

    def macro(self, create=True):
        slot = self.slot()
        if slot not in self.macros and create:
            self.macros[slot] = model.Macro([])
        return self.macros.get(slot)

    def set_steps(self, steps, select=None):
        m = self.macro()
        candidate = model.Macro(list(steps), m.loops)
        try:
            model.encode_macro(candidate)
        except ValueError as e:
            self.refuse(str(e))
            return
        m.steps, m.raw = list(steps), None
        self.loading = True
        self.fill_slots()
        self.loading = False
        if select is not None:
            self.step_list.setCurrentRow(select)
        self.changed()

    def insert_at(self):
        row = self.step_list.currentRow()
        return len(self.macro().steps) if row < 0 else row + 1

    def add_key_step(self):
        picker = KeyPicker()
        how = QComboBox()
        how.addItems(['Press and release', 'Press (down) only', 'Release (up) only'])
        if not dialog(self, 'Add key', lambda f: (f.addRow('Key', picker), f.addRow('', how))):
            return
        code = picker.code()
        new = {0: [model.MacroStep('key', code, True), model.MacroStep('key', code, False)],
               1: [model.MacroStep('key', code, True)],
               2: [model.MacroStep('key', code, False)]}[how.currentIndex()]
        self._insert(new)

    def add_mouse_step(self):
        button = QComboBox()
        for name, bit in model.MOUSE_BITS.items():
            button.addItem(MOUSE_NAMES[name], bit)
        how = QComboBox()
        how.addItems(['Press and release', 'Press (down) only', 'Release (up) only'])
        if not dialog(self, 'Add mouse click', lambda f: (f.addRow('Button', button), f.addRow('', how))):
            return
        bit = button.currentData()
        new = {0: [model.MacroStep('mouse', bit, True), model.MacroStep('mouse', bit, False)],
               1: [model.MacroStep('mouse', bit, True)],
               2: [model.MacroStep('mouse', bit, False)]}[how.currentIndex()]
        self._insert(new)

    def add_delay_step(self):
        ms, ok = QInputDialog.getInt(self, 'Add pause', 'Pause (ms)', 50, 1, 65535)
        if ok:
            self._insert([model.MacroStep('delay', ms)])

    def _insert(self, new):
        at = self.insert_at()
        steps = self.macro().steps
        self.set_steps(steps[:at] + new + steps[at:], select=at + len(new) - 1)

    def record_steps(self):
        d = RecordDialog(self)
        if d.exec() == QDialog.DialogCode.Accepted and d.steps:
            self._insert(d.steps)

    def move_step(self, delta):
        row = self.step_list.currentRow()
        steps = list(self.macro().steps)
        if row < 0 or not 0 <= row + delta < len(steps):
            return
        steps[row], steps[row + delta] = steps[row + delta], steps[row]
        self.set_steps(steps, select=row + delta)

    def delete_step(self):
        row = self.step_list.currentRow()
        steps = list(self.macro().steps)
        if 0 <= row < len(steps):
            del steps[row]
            self.set_steps(steps, select=min(row, len(steps) - 1))

    def clear_steps(self):
        self.set_steps([])

    def steps_text_edited(self):
        text = self.steps_text.text().strip()
        current = self.macro(create=False)
        if text == ', '.join(model.step_to_str(s).replace(' ms', '') for s in (current.steps if current else [])):
            return
        try:
            steps = model.parse_steps(text) if text else []
        except ValueError as e:
            self.refuse(str(e))
            return
        self.set_steps(steps)

    def loops_changed(self, value):
        if self.loading:
            return
        m = self.macro()
        m.loops, m.raw = value, None
        self.loading = True
        self.fill_slots()
        self.loading = False
        self.changed()

    # Files -----------------------------------------------------------------------

    def import_pfd(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Import VCFG profile', '', 'VCFG profiles (*.pfd)')
        if not path:
            return
        try:
            profile, macros = pfd.to_profile(path)
            bad = [s + 1 for s in macros if s >= device.MACRO_SLOTS]
            if bad:
                raise ValueError(f'the file uses macro {bad[0]}; this mouse has slots 1-{device.MACRO_SLOTS}')
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, 'Import .pfd', str(e))
            return
        base = self.profile()
        profile.dpi_count = base.dpi_count
        for new, old in zip(profile.dpi_levels, base.dpi_levels):
            new.extra = old.extra
        self.edits[self.current] = profile
        self.macros.update(macros)
        self.show_profile(self.current)
        self.statusBar().showMessage(f'{os.path.basename(path)} loaded into profile {self.current + 1}; '
                                     'click Apply to write it')

    def export_pfd(self):
        try:
            data = pfd.from_profile(self.profile(), {s: m for s, m in self.macros.items()
                                                     if s in self.profile().macro_slots()})
        except ValueError as e:
            QMessageBox.critical(self, 'Export .pfd', str(e))
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export VCFG profile', f'Profile{self.current + 1}.pfd',
                                              'VCFG profiles (*.pfd)')
        if not path:
            return
        try:
            with open(path, 'wb') as f:
                f.write(data)
        except OSError as e:
            QMessageBox.critical(self, 'Export .pfd', str(e))
            return
        self.statusBar().showMessage(f'Profile {self.current + 1} saved to {os.path.basename(path)}', 8000)

    def view_state(self):
        return device.State(self.state.active, self.edits, self.macros, {}, {})

    def export_json(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export profiles', 'profiles.json', 'JSON (*.json)')
        if not path:
            return
        data = store.export_dict(self.view_state(), sorted(self.edits))
        try:
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(data, f, indent=2)
                f.write('\n')
        except OSError as e:
            QMessageBox.critical(self, 'Export JSON', str(e))

    def load_json(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Load profiles', '', 'JSON (*.json)')
        if not path:
            return
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            if data.get('format') != store.PROFILES_FORMAT:
                raise ValueError('this file was not written by "Export JSON" or "valkyrie export"')
            edits = copy.deepcopy(self.edits)
            for key, d in data['profiles'].items():
                n = int(key) - 1
                if n not in edits:
                    raise ValueError(f'profile {key} cannot be edited')
                edits[n] = store.profile_from_dict(d, edits[n])
            macros = store.macros_from_dict(data.get('macros', {}))
            bad = [s + 1 for s in macros if s >= device.MACRO_SLOTS]
            if bad:
                raise ValueError(f'the file uses macro {bad[0]}; this mouse has slots 1-{device.MACRO_SLOTS}')
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            QMessageBox.critical(self, 'Load JSON', str(e))
            return
        self.edits = edits
        self.macros.update(macros)
        self.show_profile(self.current)
        self.statusBar().showMessage(f'{os.path.basename(path)} loaded; click Apply to write it')

    def factory(self):
        box = QMessageBox(self)
        box.setWindowTitle('Factory settings')
        box.setText('Load VCFG\'s factory settings? Nothing is written before Apply.')
        box.setInformativeText('Profile 1 is a media layout (yellow), profile 2 a browser layout '
                               '(green), profiles 3-5 a gaming layout (blue, magenta, red). All use '
                               '500 Hz and DPI 400, 800, 1600, 3200 and 4000.')
        this = box.addButton(f'Profile {self.current + 1}', QMessageBox.ButtonRole.AcceptRole)
        every = box.addButton('All profiles', QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() in (this, every):
            self.load_factory([self.current] if box.clickedButton() is this else sorted(self.edits))

    def load_factory(self, numbers):
        try:
            for n in numbers:
                self.edits[n] = ops.factory_profile(n, self.state.profiles[n])
        except (OSError, ValueError, KeyError) as e:
            QMessageBox.critical(self, 'Factory settings', str(e))
            return
        self.show_profile(self.current)
        self.statusBar().showMessage('Factory settings loaded into profile(s) ' +
                                     ', '.join(str(n + 1) for n in numbers) + '; click Apply to write them')

    def backup(self):
        self.run('Saving a backup…', lambda: store.save_backup(self.get_mouse().read_state()),
                 lambda path: QMessageBox.information(self, 'Backup', f'Saved to {path}'))

    def restore(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Restore backup', store.BACKUP_DIR, 'Backups (*.json)')
        if not path:
            return
        try:
            active, plan = ops.restore_plan(path)
        except (OSError, ValueError, KeyError) as e:
            QMessageBox.critical(self, 'Restore', str(e))
            return
        numbers = ', '.join(str(n + 1) for n in plan)
        if QMessageBox.question(self, 'Restore', f'Write profile(s) {numbers} from {os.path.basename(path)} '
                                'to the mouse? Unapplied changes here are lost. A backup of the current '
                                'state is saved first.') != QMessageBox.StandardButton.Yes:
            return
        if not self.write_allowed():
            return
        log = []
        self.run('Restoring…', lambda: ops.write_restore(self.get_mouse(), active, plan, log.append),
                 lambda _: self.after_write('Restored and verified'))

    # Apply / revert / switch --------------------------------------------------------

    def revert(self):
        self.edits = copy.deepcopy(self.state.profiles)
        self.macros = copy.deepcopy(self.saved_macros)
        self.undo_preview()
        self.show_profile(self.current)

    def plan(self):
        """-> ({n: (profile, macros)}, notes) for everything changed here."""
        profiles = {n: copy.deepcopy(p) for n, p in self.edits.items() if self.profile_dirty(n)}
        for slot in range(device.MACRO_SLOTS):
            if self.macro_dirty(slot):
                for n, _ in self.macro_users(slot):
                    profiles.setdefault(n, copy.deepcopy(self.edits[n]))
        for n, p in profiles.items():
            if not any(lv.enabled for lv in p.dpi_levels) or not p.dpi_levels[p.dpi_selected].enabled:
                raise ValueError(f'profile {n + 1}: the default DPI level must be on')
            for slot in p.macro_slots():
                if slot >= device.MACRO_SLOTS:
                    raise ValueError(f'profile {n + 1} uses macro {slot + 1}; slots are 1-{device.MACRO_SLOTS}')
                if not (self.macros.get(slot) and self.macros[slot].steps):
                    raise ValueError(f'profile {n + 1} uses macro {slot + 1}, which is empty')
        used = {s for p in profiles.values() for s in p.macro_slots()}
        notes = []
        changes = ops.plan_changes(self.state, profiles, {s: self.macros[s] for s in used},
                                   note=lambda text: notes.append(text.strip().removeprefix('note: ')))
        unsaved = [s + 1 for s in range(device.MACRO_SLOTS) if self.macro_dirty(s) and not self.macro_users(s)]
        if unsaved:
            notes.append('macro ' + ', '.join(map(str, unsaved)) + ' is not saved: no button uses it')
        return changes, notes

    def apply(self):
        try:
            changes, notes = self.plan()
        except ValueError as e:
            QMessageBox.critical(self, 'Apply', str(e))
            return
        if not changes:
            QMessageBox.information(self, 'Apply', 'Nothing to write.\n' + '\n'.join(notes))
            return
        if notes and QMessageBox.question(
                self, 'Apply', 'Write profile(s) ' + ', '.join(str(n + 1) for n in sorted(changes)) +
                '?\n\n' + '\n'.join(notes)) != QMessageBox.StandardButton.Yes:
            return
        if not self.write_allowed():
            return
        log = []
        active = self.state.active

        def written(_):
            if active in changes:
                self.apply_windows_settings(active)
            self.after_write('Written and verified')
        self.run('Writing…', lambda: ops.write_changes(self.get_mouse(), self.state, changes, log.append), written)

    def after_write(self, message):
        self.previewed = False                  # the commit shows the saved light again
        self.done_message = message
        self.reload()

    def activate_profile(self):
        if not self.write_allowed():
            return
        n = self.current

        def switch():
            mouse = self.get_mouse()
            mouse.switch_profile(n)
            with mouse.session():
                return mouse.read_active()

        def done(active):
            self.state.active = active
            self.previewed = False
            host.record({}, active)
            self.apply_windows_settings(active)
            if active != n:
                QMessageBox.warning(self, 'Drakkar Valkyrie', f'The mouse reports profile {active + 1} as active.')
        self.run(f'Switching to profile {n + 1}…', switch, done)

    def confirm_discard(self):
        if not self.dirty():
            return True
        return QMessageBox.question(self, 'Drakkar Valkyrie', 'Discard the changes not applied yet?') \
            == QMessageBox.StandardButton.Yes

    def closeEvent(self, event):
        if self.busy or not self.confirm_discard():
            event.ignore()
            return
        self.undo_preview()
        self.stop_listening()
        if self.mouse is not None:
            self.mouse.io.close()
        event.accept()


def main():
    utf8_stdio()
    app = QApplication(sys.argv)
    app.setApplicationName('valkyrie')
    app.setDesktopFileName('valkyrie-gui')
    window = MainWindow(open_listener=events.Listener)
    window.resize(980, 720)
    window.show()
    return app.exec()
