import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401  (before valkyrie: no real config files)

from valkyrie import autoclick  # noqa: E402

LEFT = autoclick.BUTTONS['left']
# Key codes as this system reads them: evdev on Linux (F13 = 183), scan codes on Windows (F13 = 0x64).
F13, F14, F15, F16, F24 = (autoclick.key_code(f'F{n}') for n in (13, 14, 15, 16, 24))


def binding(**kw):
    d = {'key': 'F13', 'button': 'left', 'rate': 10, 'mode': 'hold'}
    d.update(kw)
    return autoclick.Binding(d, 1)


def simulate(clicker, presses, until, step=0.001):
    """presses: {time: key value}. -> [(time, button, value)] sent."""
    out, t = [], 0.0
    while t <= until + 1e-9:
        for when, value in presses.items():
            if abs(when - t) < step / 2:
                clicker.key(value, t)
        out += [(round(t, 3), b, v) for b, v in clicker.due(t)]
        t += step
    return out


class Settings(unittest.TestCase):
    def test_default_config_is_valid(self):
        config = autoclick.Config(autoclick.DEFAULT_CONFIG)
        self.assertEqual([b.describe() for b in config.bindings], ['F13: left click 15/s (toggle), F14 slower, F15 faster, F16 mode'])
        self.assertEqual(config.keys, {F13, F14, F15, F16})             # F14-F16 are the controls

    def test_refuses_bad_settings(self):
        for text in ['', 'swallow = true', '[[click]]\nkey = "F13"\nrate = 0',
                     '[[click]]\nkey = "F13"\nrate = 10\nmode = "spam"',
                     '[[click]]\nkey = "Nope"\nrate = 10',
                     '[[click]]\nkey = "F13"\nrate = 10\nbutton = "side"',
                     '[[click]]\nkey = "F13"\nrate = 10\npress_ms = 200',
                     '[[click]]\nkey = "F13"\nrate = 10\n[[click]]\nkey = "F13"\nrate = 5',
                     '[[click]]\nkey = "F13"\nrate = 10\nspeed = 3', 'rate = [',
                     '[[click]]\nkey = "F13"\nrate = 10\nfaster_key = "F13"',
                     '[[click]]\nkey = "F13"\nrate = 10\nslower_key = "Nope"',
                     '[[click]]\nkey = "F13"\nrate = 10\nstep = 0']:
            with self.subTest(text):
                with self.assertRaises(ValueError):
                    autoclick.Config(text)

    def test_reload_key(self):
        config = autoclick.Config('reload_key = "F24"\n[[click]]\nkey = "F13"\nrate = 5')
        self.assertEqual(config.keys, {F13, F24})

    def test_key_codes_of_this_system(self):
        from valkyrie import keys
        if sys.platform == 'win32':
            self.assertEqual((F13, F24), (0x64, 0x76))
            self.assertEqual(keys.scancode_to_hid(0x11D), keys.key_code('RightCtrl'))
            self.assertEqual(keys.scancode_to_hid(0x45), keys.key_code('Pause'))
            self.assertEqual(keys.scancode_to_hid(0x145), keys.key_code('NumLock'))
        else:
            self.assertEqual((F13, F24), (183, 194))
        for name in ('Q', 'F5', 'Enter', 'NumEnter', 'Left', 'RightAlt', 'PrintScreen', 'F13'):
            self.assertEqual(keys.native_table()[autoclick.key_code(name)], keys.key_code(name), name)


class Clicking(unittest.TestCase):
    def test_hold_clicks_at_the_rate_while_held(self):
        sent = simulate(autoclick.Clicker(binding(rate=10)), {0.0: 1, 0.35: 0}, 1.0)
        presses = [t for t, _, v in sent if v == 1]
        self.assertEqual(presses, [0.0, 0.1, 0.2, 0.3])
        self.assertEqual(len([v for _, _, v in sent if v == 0]), 4)      # every press released
        self.assertEqual(sent[1], (0.02, LEFT, 0))                       # held 20 ms

    def test_toggle_starts_and_stops_on_presses(self):
        c = autoclick.Clicker(binding(rate=20, mode='toggle'))
        sent = simulate(c, {0.0: 1, 0.01: 0, 0.5: 1, 0.51: 0}, 1.0)
        presses = [t for t, _, v in sent if v == 1]
        self.assertEqual(len(presses), 10)                               # 0.00 .. 0.45
        self.assertEqual(sent[-1][2], 0)

    def test_press_time_is_half_the_period_when_fast(self):
        sent = simulate(autoclick.Clicker(binding(rate=50)), {0.0: 1}, 0.05)
        self.assertEqual(sent[:2], [(0.0, LEFT, 1), (0.01, LEFT, 0)])

    def test_stop_releases_the_button(self):
        c = autoclick.Clicker(binding())
        c.key(1, 0.0)
        c.due(0.0)
        self.assertEqual(c.stop(), [(LEFT, 0)])
        self.assertIsNone(c.deadline())

    def test_key_reports_start_and_stop(self):
        c = autoclick.Clicker(binding(mode='toggle'))
        self.assertEqual([c.key(1, 0.0), c.key(0, 0.1), c.key(1, 0.5), c.key(0, 0.6)],
                         [True, None, False, None])
        c = autoclick.Clicker(binding(mode='hold'))
        self.assertEqual([c.key(1, 0.0), c.key(0, 0.1)], [True, False])

    def test_chime_pitches(self):
        import io, wave, struct
        def peaks(data):
            with wave.open(io.BytesIO(data)) as w:
                frames = w.readframes(w.getnframes())
            values = struct.unpack(f'<{len(frames) // 2}h', frames)
            half = len(values) // 2
            # count zero crossings in each half: more crossings = higher pitch
            cross = lambda v: sum(1 for a, b in zip(v, v[1:]) if (a < 0) != (b < 0))
            return cross(values[:half]), cross(values[half:])
        first, second = peaks(autoclick.chime((autoclick.LOW, autoclick.HIGH), 0.3))
        self.assertLess(first, second)
        first, second = peaks(autoclick.chime((autoclick.HIGH, autoclick.LOW), 0.3))
        self.assertGreater(first, second)

    def test_faster_while_clicking_keeps_going_at_the_new_rate(self):
        c = autoclick.Clicker(binding(rate=10, mode='toggle'))
        c.key(1, 0.0)
        c.due(0.0)                                    # click at 0.0
        c.due(0.02)                                   # released
        self.assertEqual(c.set_rate(20), 20)
        self.assertAlmostEqual(c.next_press(), 0.05)  # one new period after the last click
        self.assertAlmostEqual(c.b.press, 0.020)
        self.assertEqual(c.set_rate(500), autoclick.MAX_RATE)
        self.assertEqual(c.set_rate(-3), 1)

    def test_max_rate(self):
        config = autoclick.Config(autoclick.DEFAULT_CONFIG)
        self.assertEqual(config.max_rate, 20)
        c = autoclick.Clicker(config.bindings[0])
        self.assertEqual(c.set_rate(21), 20)                # faster_key stops at max_rate
        config = autoclick.Config('max_rate = 30\n[[click]]\nkey = "F13"\nrate = 25')
        self.assertEqual(autoclick.Clicker(config.bindings[0]).set_rate(500), 30)
        for text in ('max_rate = 20\n[[click]]\nkey = "F13"\nrate = 25',     # rate above max_rate
                     'max_rate = 150\n[[click]]\nkey = "F13"\nrate = 5',
                     'max_rate = 0\n[[click]]\nkey = "F13"\nrate = 5'):
            with self.subTest(text):
                self.assertRaises(ValueError, autoclick.Config, text)

    def test_press_time_shrinks_with_the_period(self):
        b = binding(rate=10, press_ms=40)
        self.assertAlmostEqual(b.press, 0.040)
        b.set_rate(50)
        self.assertAlmostEqual(b.press, 0.010)       # half of 20 ms

    def test_switch_mode_stops_clicking(self):
        c = autoclick.Clicker(binding(mode='toggle'))
        c.key(1, 0.0)
        self.assertEqual(c.switch_mode(), ('hold', True))
        self.assertFalse(c.active)
        self.assertEqual(c.switch_mode(), ('toggle', False))

    def test_late_wakeup_skips_missed_clicks(self):
        c = autoclick.Clicker(binding(rate=10))
        c.key(1, 0.0)
        c.due(0.0)
        c.due(0.02)
        self.assertEqual(c.due(0.55), [(LEFT, 1)])                       # one click, not five
        self.assertAlmostEqual(c.next_press(), 0.6)


if __name__ == '__main__':
    unittest.main()
