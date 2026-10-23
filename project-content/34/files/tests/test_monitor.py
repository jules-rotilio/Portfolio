import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401  (before valkyrie: no real config files)

import captures  # noqa: E402
from valkyrie import device, events, host, model, monitor  # noqa: E402

try:
    from valkyrie import linux_input
except ImportError:                      # Windows: no fcntl
    linux_input = None


def report(text):
    """A report as hidraw returns it (the mouse pads reports 7 and 8 to 8 bytes)."""
    return bytes.fromhex(text) + bytes(8 - len(bytes.fromhex(text)))


class Events(unittest.TestCase):
    def test_reports_seen_on_the_mouse(self):
        # From a live read on 2026-10-19: profile button, DPI button, report-rate buttons.
        for text, kind, value in [('08 01 03', 'profile', 3), ('08 02 01', 'dpi', 1), ('08 06 08', 'rate', 8),
                                  ('08 06 01', 'rate', 1)]:
            event = events.decode(report(text))
            self.assertEqual((event.kind, event.value), (kind, value))
        self.assertEqual(events.decode(report('08 06 02')).describe(), 'report rate 500 Hz')
        self.assertEqual(events.decode(report('08 01 00')).describe(), 'profile 1')

    def test_other_reports(self):
        self.assertIsNone(events.decode(report('01 23 03')))       # consumer key after a profile switch
        keys = events.decode(report('07 05 00 80'))
        self.assertEqual((keys.kind, keys.value), ('keys', 0x800005))
        self.assertEqual(keys.describe(), 'virtual keys 1, 3, 24')
        self.assertEqual(events.decode(report('08 09 01')).kind, 'unknown')


class Host(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = host.CONFIG_DIR
        host.CONFIG_DIR = self.tmp.name
        self.mouse = device.Mouse(device.FakeMouse(captures.memory_dump()), pace=False)

    def tearDown(self):
        host.CONFIG_DIR = self.saved
        self.tmp.cleanup()

    def test_dpi_asked_for_comes_back(self):
        state = self.mouse.read_state()
        p = state.profiles[4]
        p.dpi_levels[2].set(1900)
        p.windows = model.WindowsSettings(5, 600, 12, 1)
        host.record({4: p}, 4)
        again = host.attach(self.mouse.read_state())
        self.assertEqual(again.profiles[4].dpi_levels[2].wanted, (1900, 1900))
        self.assertEqual(again.profiles[4].windows, p.windows)
        self.assertTrue(again.profiles[0].dpi_levels[2].exact)           # nothing known for profile 1

    def test_forgotten_when_the_mouse_changed(self):
        state = self.mouse.read_state()
        p = state.profiles[4]
        p.dpi_levels[2].set(1900)                     # the mouse holds 2000...
        self.mouse.apply_profile(4, p)
        host.record({4: p})
        self.assertEqual(host.attach(self.mouse.read_state()).profiles[4].dpi_levels[2].wanted, (1900, 1900))
        p.dpi_levels[2].set(1250)                     # ...until another program writes 1250
        self.mouse.apply_profile(4, p)
        again = host.attach(self.mouse.read_state())
        self.assertTrue(again.profiles[4].dpi_levels[2].exact)

    def test_keep_wanted_for_raw_restores(self):
        state = self.mouse.read_state()
        p = state.profiles[4]
        held = p.dpi_levels[1].x
        p.dpi_levels[1].req_x = p.dpi_levels[1].req_y = held - 100
        host.record({4: p})
        raw = self.mouse.read_state().profiles[4]      # no wanted values
        host.record({4: raw}, keep_wanted=True)
        self.assertEqual(host.load()['profiles']['5']['levels'][1]['want'], [held - 100] * 2)
        host.record({4: raw})
        self.assertNotIn('want', host.load()['profiles']['5']['levels'][1])

    def test_broken_file_is_ignored(self):
        with open(host.path(), 'w', encoding='utf-8') as f:
            f.write('{not json')
        self.assertEqual(host.load(), host.empty())


def host_data(levels, selected=2, polling=1, active=1):
    return {'format': host.FORMAT, 'active_profile': active, 'profiles': {
        str(active): {'polling': polling, 'selected': selected, 'levels': levels}}}


class Tracker(unittest.TestCase):
    LEVELS = [{'on': True, 'x': 500, 'y': 500, 'want': [400, 400]},
              {'on': True, 'x': 1000, 'y': 1000},
              {'on': True, 'x': 2000, 'y': 2000, 'want': [1900, 1900]},
              {'on': True, 'x': 1500, 'y': 1500, 'want': [1600, 800]},
              {'on': False, 'x': 0, 'y': 0}]

    def test_factors_follow_the_level_in_use(self):
        t = monitor.Tracker(host_data(self.LEVELS))
        self.assertEqual(t.factors(), (1900 / 2000, 1900 / 2000))
        t.apply(events.decode(report('08 02 01')))
        self.assertEqual(t.factors(), (1.0, 1.0))
        t.apply(events.decode(report('08 02 03')))
        self.assertEqual(t.factors(), (1600 / 1500, 800 / 1500))
        t.apply(events.decode(report('08 01 04')))          # profile 5: nothing known
        self.assertEqual(t.factors(), (1.0, 1.0))

    def test_messages(self):
        t = monitor.Tracker(host_data(self.LEVELS))
        e = events.decode(report('08 02 00'))
        t.apply(e)
        self.assertEqual(t.message(e), ('400 DPI (mouse: 500)', 'Level 1 of profile 1'))
        self.assertEqual(t.message(e, scaling=True), ('400 DPI', 'Level 1 of profile 1'))
        e = events.decode(report('08 06 04'))
        t.apply(e)
        self.assertEqual(t.message(e), ('Report rate 250 Hz', ''))
        e = events.decode(report('08 01 00'))
        t.apply(e)
        self.assertEqual(t.message(e, scaling=True), ('Profile 1', '400 DPI · 250 Hz'))


class Scaler(unittest.TestCase):
    def test_remainders_are_carried(self):
        s = monitor.Scaler()
        s.set(0.8, 1.0)
        self.assertTrue(s.needed)
        self.assertEqual(sum(s.scale(monitor.REL_X, 1) for _ in range(10)), 8)
        self.assertEqual(sum(s.scale(monitor.REL_X, -3) for _ in range(5)), -12)
        self.assertEqual(s.scale(monitor.REL_Y, 7), 7)
        self.assertEqual(s.scale(8, 1), 1)                  # the wheel is never scaled

    def test_new_factors_reset_the_remainder(self):
        s = monitor.Scaler()
        s.set(0.5, 0.5)
        s.scale(monitor.REL_X, 1)                           # 0.5 left over
        s.set(0.9, 0.9)
        self.assertEqual(s.scale(monitor.REL_X, 1), 0)
        s.set(1.0, 1.0)
        self.assertFalse(s.needed)


@unittest.skipUnless(sys.platform.startswith('linux'), 'the pointer proxy is Linux only (evdev, uinput)')
class Proxy(unittest.TestCase):
    """The pointer proxy, with pipes standing in for the event node and /dev/uinput."""

    def setUp(self):
        from valkyrie import monitor_linux
        self.scaler = monitor.Scaler()
        p = monitor_linux.Proxy.__new__(monitor_linux.Proxy)
        self.src_r, self.src_w = os.pipe()
        self.out_r, p.out = os.pipe()
        os.set_blocking(self.out_r, False)
        p.fd, p.path, p.scaler, p.grabbed, p.held, p.batch = self.src_r, 'test', self.scaler, False, set(), []
        self.grabs = []
        p.set_grab = self.grabs.append
        self.proxy = p

    def tearDown(self):
        for fd in (self.src_r, self.src_w, self.out_r, self.proxy.out):
            os.close(fd)

    def feed(self, *items):
        os.write(self.src_w, b''.join(linux_input.EVENT.pack(0, 0, t, c, v) for t, c, v in items))
        self.proxy.read()

    def sent(self):
        try:
            data = os.read(self.out_r, 4096)
        except BlockingIOError:
            return []
        return [linux_input.EVENT.unpack_from(data, i)[2:] for i in range(0, len(data), linux_input.EVENT.size)]

    def test_scales_only_while_needed(self):
        syn = (linux_input.EV_SYN, linux_input.SYN_REPORT, 0)
        self.feed((linux_input.EV_REL, linux_input.REL_X, 5), syn)
        self.assertEqual(self.sent(), [])                    # not grabbed: the desktop reads the mouse
        self.scaler.set(0.5, 1.0)
        self.proxy.update_grab()
        self.assertEqual(self.grabs, [True])
        self.feed((linux_input.EV_REL, linux_input.REL_X, 3), (linux_input.EV_REL, linux_input.REL_Y, 2), syn,
                  (linux_input.EV_REL, linux_input.REL_X, 3), (linux_input.EV_REL, 8, -1), syn)
        self.assertEqual(self.sent(), [(linux_input.EV_REL, linux_input.REL_X, 1),
                                       (linux_input.EV_REL, linux_input.REL_Y, 2), syn,
                                       (linux_input.EV_REL, linux_input.REL_X, 2), (linux_input.EV_REL, 8, -1), syn])

    def test_waits_for_buttons_to_be_released(self):
        syn = (linux_input.EV_SYN, linux_input.SYN_REPORT, 0)
        self.feed((linux_input.EV_KEY, 0x110, 1), syn)           # left button held
        self.scaler.set(0.8, 0.8)
        self.proxy.update_grab()
        self.assertEqual(self.grabs, [])
        self.feed((linux_input.EV_KEY, 0x110, 0), syn)
        self.assertEqual(self.grabs, [True])                 # grabbed once it was released


class Config(unittest.TestCase):
    def test_default_file(self):
        c = monitor.Config(monitor.DEFAULT_CONFIG)
        self.assertEqual((c.notify, c.exact_dpi), (True, False))

    def test_errors(self):
        for text in ('notify = 1', 'speed = 2', 'exact_dpi = '):
            self.assertRaises(ValueError, monitor.Config, text)


if __name__ == '__main__':
    unittest.main()
