import dataclasses
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401  (before valkyrie: no real config files)

import captures  # noqa: E402
from valkyrie import keys, model  # noqa: E402

BASE_TABLE = bytes.fromhex(
    '0e 01000000 02000000 03000000 19810301 17000000 18000000 0a000000 09000000'
    ' 05000000 1000e200 1000e000 1000e100 04000000 0d000000')


def block_kind(addr):
    if addr >= 0x500:
        return 'macro'
    return {0x4F: 'dpi', 0x90: 'buttons', 0xF1: 'light'}.get(addr & 0xFF)


def all_vcfg_blocks():
    for name in captures.ALL:
        for _, addr, payload in captures.writes(name):
            kind = block_kind(addr)
            if kind:
                yield name, addr, kind, payload


def fresh(obj):
    """Copy without the raw bytes remembered from decoding."""
    return dataclasses.replace(obj, raw=None)


class RoundTrip(unittest.TestCase):
    def test_every_vcfg_block_reencodes_identically(self):
        count = 0
        for name, addr, kind, payload in all_vcfg_blocks():
            with self.subTest(capture=name, addr=hex(addr)):
                if kind == 'dpi':
                    self.assertEqual(model.encode_dpi(*model.decode_dpi(payload)), payload)
                elif kind == 'light':
                    self.assertEqual(model.encode_light(model.decode_light(payload)), payload)
                elif kind == 'macro':
                    self.assertEqual(model.encode_macro(model.decode_macro(payload)), payload)
                    self.assertEqual(model.encode_macro(fresh(model.decode_macro(payload))), payload)
                else:
                    actions = model.decode_buttons(payload)
                    self.assertEqual(model.encode_buttons(actions), payload)
                    lengths = {a.code: a.raw[2] for a in actions if a.kind == 'macro'}
                    self.assertEqual(model.encode_buttons([fresh(a) for a in actions], lengths), payload)
                count += 1
        self.assertGreater(count, 150)

    def test_action_strings_round_trip(self):
        for name, addr, kind, payload in all_vcfg_blocks():
            if kind != 'buttons':
                continue
            for a in model.decode_buttons(payload):
                if a.kind != 'unknown':
                    self.assertEqual(model.parse_action(model.action_to_str(a)), a)


class KnownValues(unittest.TestCase):
    def test_base_profile_buttons(self):
        labels = [model.describe_action(a) for a in model.decode_buttons(BASE_TABLE)]
        self.assertEqual(labels, [
            'Left click', 'Right click', 'Middle click', 'Fire key: Left click x3, 1 ms apart',
            'Report rate +', 'Report rate -', 'DPI +', 'DPI -', 'Key: LeftAlt', 'Key: LeftCtrl',
            'Key: LeftShift', 'Forward (button 5)', 'Back (button 4)', 'Profile switch'])

    def test_actions_vcfg_sent_for_button_10(self):
        # (action string, bytes VCFG sent for button 10, captures cap6-cap8)
        cases = [
            ('disable', '0e000000'), ('key:Q', '10001400'), ('shortcut:Ctrl+Shift+Z', '0f031d00'),
            ('shortcut:Ctrl+X', '0f011b00'), ('shortcut:Alt+Tab', '0f042b00'),
            ('dpi-cycle', '08000000'), ('rate-up', '17000000'), ('middle', '03000000'),
            ('fire:middle,9,60', '1984093c'), ('fire:K,10,57', '190e0a39'),
            ('shortcut:Win+E', '0f080800'), ('shortcut:Win+R', '0f081500'),
            ('shortcut:Win+L', '0f080f00'), ('media:browser-home', '0e002302'),
            ('media:browser-back', '0e002402'), ('media:email', '0e008a01'),
            ('media:stop', '0e00b700'), ('media:media-player', '0e008301'),
            ('media:play-pause', '0e00cd00'), ('shortcut:Ctrl+C', '0f010600'),
            ('shortcut:Alt+F4', '0f043d00'), ('shortcut:Win+D', '0f080700'),
        ]
        slot = model.SLOT_BUTTONS.index(10)
        for text, expected in cases:
            with self.subTest(text):
                self.assertEqual(model.encode_action(model.parse_action(text), slot).hex(), expected)

    def test_left_click_depends_on_button(self):
        left = model.parse_action('left')
        self.assertEqual(model.encode_action(left, model.SLOT_BUTTONS.index(1)).hex(), '01000000')
        self.assertEqual(model.encode_action(left, model.SLOT_BUTTONS.index(12)).hex(), '01010000')

    def test_macro_button_entry(self):
        a = model.parse_action('macro:2,repeat')
        self.assertEqual(model.encode_action(a, 9, macro_len=15).hex(), '11810f00')

    def test_macros_from_screenshots(self):
        m = model.Macro(model.parse_steps(
            'A down, wait 661, A up, wait 1367, B down, wait 74, B up, '
            'mouse:left down, wait 10, mouse:left up'), loops=3)
        self.assertEqual(model.encode_macro(m).hex(' '),
                         '84 04 00 06 95 02 04 04 00 06 57 05 84 05 00 06 4a 00 04 05 00 '
                         '81 01 00 06 0a 00 01 01 00 07 03 00')
        m = model.Macro(model.parse_steps(
            'mouse:right down, mouse:right up, mouse:middle down, mouse:middle up'))
        self.assertEqual(model.encode_macro(m).hex(' '),
                         '81 02 00 01 02 00 81 04 00 01 04 00 07 00 00')

    def test_macro_with_shift_from_mouse_memory(self):
        # Slot 2 of captures/memory-0000-0fff.bin: "Introuvable" typed on AZERTY
        raw = captures.memory_dump()[0x690:0x690 + 0x4B]
        m = model.decode_macro(raw)
        self.assertEqual([model.step_to_str(s) for s in m.steps[:5]],
                         ['RightShift down', 'I down', 'I up', 'RightShift up', 'N down'])
        self.assertEqual(model.encode_macro(dataclasses.replace(m, raw=None)), raw)

    def test_macro_text_round_trip(self):
        text = 'G down, wait 5 ms, G up, mouse:right down, mouse:right up'
        steps = model.parse_steps(text)
        self.assertEqual(', '.join(model.step_to_str(s) for s in steps), text)

    def test_light(self):
        light = model.decode_light(bytes.fromhex('941e1c020300'))
        self.assertEqual((light.rgb, light.brightness, light.breathing), ((107, 225, 227), 2, 3))

    def test_dpi_rounding_like_vcfg(self):
        # What the mouse got from VCFG for the factory 400/800/1600/3200 and for the
        # user's 1700/1900/2200 (seen in the mouse's memory); ties go down (Dpi_SnapToIndex).
        for given, used in [(400, 500), (800, 750), (1600, 1500), (1700, 1750), (1900, 2000),
                            (2200, 2250), (3200, 3250), (4000, 4000), (375, 250), (625, 500),
                            (250, 250), (100, 250), (5000, 4000)]:
            self.assertEqual(model.snap_dpi(given), used, given)

    def test_shortcuts_with_one_or_two_keys(self):
        self.assertEqual(keys.parse_shortcut('Ctrl+Shift+Z'), (0x03, 0x1D, 0))
        self.assertEqual(keys.parse_shortcut('Ctrl+K+C'), (0x01, 0x0E, 0x06))
        self.assertEqual(keys.parse_shortcut('Alt'), (0, 0xE2, 0))            # a modifier alone is a key
        self.assertRaises(ValueError, keys.parse_shortcut, 'Ctrl+A+B+C')
        a = model.decode_action(bytes.fromhex('0f010e06'))
        self.assertEqual((a.kind, a.mods, a.code, a.code2), ('shortcut', 1, 0x0E, 0x06))
        self.assertEqual(model.describe_action(a), 'Shortcut: Ctrl+K+C')
        self.assertEqual(model.parse_action('shortcut:Ctrl+K+C'), a)

    def test_macro_step_limit(self):
        steps = [model.MacroStep('delay', 5)] * model.MACRO_MAX_STEPS
        self.assertEqual(len(model.encode_macro(model.Macro(steps))), 3 * 61)
        with self.assertRaisesRegex(ValueError, '60'):
            model.encode_macro(model.Macro(steps + steps[:1]))

    def test_dpi_asked_for(self):
        self.assertEqual(model.dpi_value('1900'), 1900)
        self.assertEqual(model.dpi_value(1925), 1950)          # VCFG's sliders move by 50
        self.assertEqual(model.dpi_value(250), 250)
        for bad in (100, 249, 4200):
            self.assertRaises(ValueError, model.dpi_value, bad)

    def test_dpi_level_set_like_vcfg(self):
        lv = model.DpiLevel(True, 0, 0)
        lv.set(1900)
        self.assertEqual((lv.x, lv.y, lv.wanted, lv.exact), (2000, 2000, (1900, 1900), False))
        lv.set(1600, 800)                   # the mouse gets max(x, y) for both axes
        self.assertEqual((lv.x, lv.y, lv.wanted), (1500, 1500, (1600, 800)))
        lv.set(2000)
        self.assertEqual((lv.x, lv.y, lv.req_x, lv.req_y, lv.exact), (2000, 2000, None, None, True))
        self.assertEqual(model.encode_dpi(5, 0, [lv] * 5)[2:10], bytes.fromhex('0108000800000000'))

    def test_disabled_dpi_level_is_zeros(self):
        count, selected, levels = model.decode_dpi(bytes.fromhex(
            '0502 0102000200000000 0103000300000000 0108000800000000'
            ' 010d000d00000000 0110001000000000'))
        levels[0].enabled = False
        self.assertEqual(model.encode_dpi(count, selected, levels)[2:10], bytes(8))


class Rejects(unittest.TestCase):
    def test_bad_actions(self):
        for text in ('fire:left,0,1', 'fire:left,3,300', 'macro:0', 'jump', 'key:NoSuchKey',
                     'unknown:01020304', 'shortcut:Hyper+A', 'left:1'):
            with self.subTest(text):
                self.assertRaises(ValueError, model.parse_action, text)

    def test_bad_macro_steps(self):
        for text in ('A press', 'wait', 'wait 70000', 'mouse:side down', ''):
            with self.subTest(text):
                self.assertRaises(ValueError, model.parse_steps, text)

    def test_macro_too_long(self):
        m = model.Macro([model.MacroStep('key', 4, True)] * 70)
        self.assertRaises(ValueError, model.encode_macro, m)


if __name__ == '__main__':
    unittest.main()
