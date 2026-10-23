import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401  (before valkyrie: no real config files)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import captures  # noqa: E402
from valkyrie import device, events, host, model, store  # noqa: E402

try:
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from valkyrie import gui
except ImportError:
    gui = None


@unittest.skipIf(gui is None, 'PyQt6 is not installed')
class WindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.fake = device.FakeMouse(captures.memory_dump())
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = (device.conflicting_programs, store.BACKUP_DIR, QMessageBox.question)
        self.saved_host = host.CONFIG_DIR
        self.config_dir = tempfile.TemporaryDirectory()
        host.CONFIG_DIR = self.config_dir.name
        device.conflicting_programs = lambda: []
        store.BACKUP_DIR = self.tmp.name
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
        self.window = gui.MainWindow(lambda: device.Mouse(self.fake, pace=False), threaded=False)
        self.applied_windows = []           # never change this PC's real pointer settings
        self.window.apply_windows_settings = self.applied_windows.append
        self.app.processEvents()            # runs the initial read

    def tearDown(self):
        device.conflicting_programs, store.BACKUP_DIR, QMessageBox.question = self.saved
        host.CONFIG_DIR = self.saved_host
        self.config_dir.cleanup()
        self.window.deleteLater()
        self.tmp.cleanup()

    def writes(self):
        return [f for kind, f in self.fake.frames if kind == 'set' and f[1] == device.WRITE]

    def test_reads_the_mouse(self):
        w = self.window
        self.assertEqual(w.current, w.state.active)
        self.assertEqual(w.action_buttons[0].text(), model.describe_action(w.profile().buttons[0]))
        self.assertFalse(w.apply_button.isEnabled())

    def test_edit_and_apply_writes_like_the_cli(self):
        w = self.window
        n = w.current
        w.set_button(9, model.Action('key', code=0x14))
        w.set_color('#00aaff')
        self.assertTrue(w.apply_button.isEnabled())
        self.assertIn('*', w.profile_buttons[n].text())
        w.apply()
        self.assertEqual(self.fake.memory[device.light_addr(n):device.light_addr(n) + 6].hex()[:6], 'ff5500')
        slot = model.SLOT_BUTTONS.index(10)
        addr = device.buttons_addr(n) + 1 + 4 * slot
        self.assertEqual(bytes(self.fake.memory[addr:addr + 4]).hex(), '10001400')
        self.assertFalse(w.dirty())                          # read back after the write
        self.assertEqual(len(os.listdir(self.tmp.name)), 1)  # backup

    def test_revert_writes_nothing(self):
        w = self.window
        w.set_button(9, model.Action('disable'))
        w.revert()
        self.assertFalse(w.dirty())
        self.assertEqual(self.writes(), [])

    def test_new_macro_on_a_button(self):
        w = self.window
        free = next(s for s in range(device.MACRO_SLOTS) if not w.macro_users(s))
        w.slot_list.setCurrentRow(free)
        w.set_steps(model.parse_steps('B down, B up, O down, O up'))
        w.set_button(8, model.Action('macro', code=free))
        w.apply()
        data = model.encode_macro(w.macros[free])          # keeps the loops stored in the slot
        start = device.macro_addr(free)
        self.assertEqual(bytes(self.fake.memory[start:start + len(data)]), data)
        self.assertFalse(w.dirty())

    def test_dpi_default_level_cannot_be_turned_off(self):
        w = self.window
        p = w.profile()
        gui.QMessageBox.information = staticmethod(lambda *a, **k: None)
        w.dpi_rows[p.dpi_selected][0].setChecked(False)
        self.assertTrue(p.dpi_levels[p.dpi_selected].enabled)
        self.assertFalse(w.dirty())

    def test_every_dialog_can_be_accepted(self):
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QSpinBox
        w = self.window

        def accept(delay=None):
            d = self.app.activeModalWidget()
            if delay is not None:
                d.findChildren(QSpinBox)[1].setValue(delay)
            d.accept()
        for name, expected in [('edit_key', 'key:A'), ('edit_shortcut', 'shortcut:C'),
                               ('edit_fire', 'fire:left,3,20'), ('edit_macro_action', 'macro:1')]:
            with self.subTest(name):
                QTimer.singleShot(0, lambda: accept(20 if name == 'edit_fire' else None))
                getattr(w, name)(3)
                self.assertEqual(model.action_to_str(w.profile().buttons[3]), expected)
        for name in ('add_key_step', 'add_mouse_step'):
            with self.subTest(name):
                before = len(w.macro().steps)
                QTimer.singleShot(0, accept)
                getattr(w, name)()
                self.assertEqual(len(w.macro().steps), before + 2)

    def test_mouse_pictures(self):
        if gui.find_vcfg_images() is None:
            self.skipTest("VCFG's images are not installed")
        from PyQt6.QtCore import QPointF
        w = self.window
        w.resize(900, 620)
        self.app.processEvents()
        for name, view in w.views.items():
            t = view.target()
            scale = t.width() / view.pixmap.width()
            for b, (x, y, r) in view.spots.items():
                with self.subTest(view=name, button=b + 1):
                    self.assertEqual(view.spot_at(QPointF(t.x() + x * scale, t.y() + y * scale)), b)
            self.assertEqual(view.spot_at(QPointF(t.x() + 2, t.y() + 2)), -1)
        self.assertEqual(sorted(b for v in w.views.values() for b in v.spots), list(range(13)))
        w.show_button_on_picture(10)                       # button 11 is on the side
        self.assertIs(w.view_stack.currentWidget(), w.views['side'])
        self.assertEqual(w.views['side'].marked, 10)
        w.show_button_on_picture(0)
        self.assertIs(w.view_stack.currentWidget(), w.views['front'])

    def test_factory_settings_then_apply(self):
        w = self.window
        w.load_factory([0, 1])
        self.assertEqual(self.writes(), [])                  # nothing before Apply
        w.show_profile(0)
        self.assertEqual(w.dpi_rows[0][2].value(), 400)
        self.assertEqual(w.dpi_used[0].text(), '<b>500 *</b>')
        self.assertEqual(w.windows_fields['pointer_speed'].value(), 10)
        # Edited and applied on Windows; greyed out on Linux.
        self.assertEqual(w.windows_fields['pointer_speed'].isEnabled(), sys.platform == 'win32')
        w.apply()
        state = device.Mouse(self.fake, pace=False).read_state()
        self.assertEqual(state.profiles[1].light.rgb, (0, 255, 0))
        self.assertEqual(model.action_to_str(state.profiles[1].buttons[3]), 'shortcut:Ctrl+W')
        self.assertEqual(w.profile().dpi_levels[0].wanted, (400, 400))   # kept on the PC

    def test_dpi_in_steps_of_50(self):
        w = self.window
        w.show_profile(4)
        w.dpi_rows[1][1].setValue(1900 // model.DPI_FINE_STEP)           # slider
        lv = w.profile().dpi_levels[1]
        self.assertEqual((lv.wanted, lv.x), ((1900, 1900), 2000))
        self.assertIn('the mouse uses the value shown' if sys.platform == 'win32' else 'valkyrie-monitor',
                      w.dpi_note.text())

    def test_windows_pointer_settings(self):
        w = self.window
        n = w.state.active
        w.show_profile(n)
        self.assertFalse(w.dirty())                          # showing a profile is not an edit
        w.windows_fields['scroll_lines'].setValue(7)
        if sys.platform != 'win32':
            return                                           # greyed out: only kept for .pfd files
        self.assertTrue(w.dirty())
        w.apply()
        self.assertEqual(self.writes(), [])                  # nothing for the mouse...
        self.assertEqual(self.applied_windows, [n])          # ...applied to Windows instead
        self.assertEqual(host.load()['profiles'][str(n + 1)]['windows']['scroll_lines'], 7)

    def test_follows_the_mouse_buttons(self):
        w = self.window
        n = w.state.active
        w.mouse_event(events.Event('dpi', 0))
        self.assertEqual(w.profile().dpi_selected, 0)
        self.assertTrue(w.default_group.button(0).isChecked())
        self.assertFalse(w.dirty())                          # the mouse already holds it
        w.mouse_event(events.Event('rate', 8))
        self.assertEqual(w.state.profiles[n].polling, 8)
        self.assertTrue(w.polling_group.button(8).isChecked())
        w.mouse_event(events.Event('profile', 1))
        self.assertEqual(w.state.active, 1)
        self.assertIn('2 (active)', w.profile_buttons[1].text())
        self.assertEqual(self.writes(), [])

    def test_shortcut_with_a_second_key(self):
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QCheckBox
        w = self.window

        def accept():
            d = self.app.activeModalWidget()
            boxes = {b.text(): b for b in d.findChildren(QCheckBox)}
            boxes['Ctrl'].setChecked(True)
            boxes['Second key'].setChecked(True)
            first, second = d.findChildren(gui.KeyPicker)
            first.set_code(0x0E)                            # K
            second.set_code(0x06)                           # C
            d.accept()
        QTimer.singleShot(0, accept)
        w.edit_shortcut(5)
        self.assertEqual(model.action_to_str(w.profile().buttons[5]), 'shortcut:Ctrl+K+C')
        self.assertEqual(model.encode_action(w.profile().buttons[5], 5).hex(), '0f010e06')

    def test_preview_is_not_a_write(self):
        w = self.window
        w.set_color('#123456')
        w._send_preview()
        self.assertEqual(self.writes(), [])
        previews = [f for kind, f in self.fake.frames if kind == 'set' and f[1] == device.PREVIEW]
        self.assertEqual(len(previews), 2)
        self.assertEqual(previews[0][2:5].hex(), 'edcba9')


if __name__ == '__main__':
    unittest.main()
