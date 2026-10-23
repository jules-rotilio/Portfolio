import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401  (before valkyrie: no real config files)

import captures  # noqa: E402
from test_device import vcfg_apply  # noqa: E402
from valkyrie import device, keys, model, ops, pfd, store  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')


def fixture(name):
    return os.path.join(FIXTURES, name)


def read_back(data):
    """pfd.to_profile of `data` saved as a file (closed first: Windows cannot open it twice)."""
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, 'test.pfd')
        with open(path, 'wb') as f:
            f.write(data)
        return pfd.to_profile(path)


class Import(unittest.TestCase):
    def test_vcfg_profiles_equal_what_is_on_the_mouse(self):
        # VCFG's Profile1-5.pfd and the mouse memory dump were taken the same evening.
        state = device.Mouse(device.FakeMouse(captures.memory_dump()), pace=False).read_state()
        for n in range(5):
            with self.subTest(profile=n + 1):
                profile, macros = pfd.to_profile(fixture(f'vcfg-profile{n + 1}.pfd'))
                self.assertEqual(model.encode_profile(profile), state.blocks[n])
                self.assertEqual(macros, {})

    def test_base_pfd_gives_the_bytes_vcfg_sent(self):
        frames, blocks, _ = vcfg_apply('cap.bin', 5)            # VCFG applying base.pfd
        profile, _ = pfd.to_profile(fixture('base.pfd'))
        self.assertEqual(model.encode_profile(profile), blocks)

    def test_macro_pfd_gives_the_bytes_vcfg_sent(self):
        frames, blocks, macros = vcfg_apply('cap5.bin', 0)     # VCFG applying Macro1 on button 4
        profile, imported = pfd.to_profile(fixture('macro1.pfd'))
        data = {slot: model.encode_macro(m) for slot, m in imported.items()}
        self.assertEqual(data, macros)
        encoded = model.encode_profile(profile, {slot: len(b) for slot, b in data.items()})
        self.assertEqual(encoded['buttons'], blocks['buttons'])

    def test_shortcut_modifiers(self):
        profile, _ = pfd.to_profile(fixture('vcfg-profile2.pfd'))
        names = [model.action_to_str(profile.buttons[b]) for b in (3, 6, 11, 12)]
        self.assertEqual(names, ['shortcut:Ctrl+W', 'shortcut:Ctrl+Shift+Tab',
                                 'shortcut:Alt+F4', 'shortcut:Win+D'])

    def test_vk_to_hid(self):
        cases = {0x41: 0x04, 0x42: 0x05, 0x44: 0x07, 0x47: 0x0A, 0x73: 0x3D, 0x25: 0x50,
                 0x27: 0x4F, 0xA4: 0xE2, 0xA2: 0xE0, 0xA0: 0xE1, 0x57: 0x1A, 0x09: 0x2B,
                 0x6B: 0x57, 0x6D: 0x56}
        for vk, hid in cases.items():
            self.assertEqual(keys.vk_to_hid(vk), hid, hex(vk))

    def test_extended_key_flag_like_vcfg(self):
        # VCFG's Key_VkToHid: the flag stored beside the VK code picks the table.
        for vk, flag, hid in [(0x25, 1, 0x50), (0x25, 0, 0x5C), (0x27, 1, 0x4F), (0x27, 0, 0x5E),
                              (0x0D, 0, 0x28), (0x0D, 1, 0x58), (0x2E, 1, 0x4C), (0x2E, 0, 0x63),
                              (0x5B, 0, 0xE3), (0x5B, 1, 0xE3), (0x41, 0, 0x04), (0x10, 0, 0xE1)]:
            self.assertEqual(keys.vcfg_to_hid(vk, flag), hid, (hex(vk), flag))
        self.assertEqual(keys.hid_to_vcfg(0x50), (0x25, 1))       # Left arrow
        self.assertEqual(keys.hid_to_vcfg(0x5C), (0x64, 0))       # Num 4
        self.assertEqual(keys.hid_to_vcfg(0x58), (0x0D, 1))       # keypad Enter
        for hid in sorted(keys.HID_KEYS):
            try:
                vk, flag = keys.hid_to_vcfg(hid)
            except ValueError:
                continue
            self.assertEqual(keys.vcfg_to_hid(vk, flag), hid, keys.key_name(hid))

    def test_vcfg_stores_arrows_with_the_flag(self):
        # VCFG's own file: Right and Left arrows on buttons 7 and 8 (flag 1).
        profile, _ = pfd.to_profile(fixture('vcfg-arrows.pfd'))
        self.assertEqual([model.action_to_str(profile.buttons[b]) for b in (6, 7)], ['key:Right', 'key:Left'])

    def test_windows_settings(self):
        profile, _ = pfd.to_profile(fixture('base.pfd'))
        self.assertEqual(profile.windows, model.WindowsSettings(3, 550, 9, 0))
        self.assertEqual(pfd.parse(fixture('base.pfd'))['windows']['pointer_speed'], 9)

    def test_dpi_asked_for_is_kept(self):
        # data-misc.pfd: VCFG sliders at 400, 800, 1900, 3200; the mouse got 500, 750, 2000, 3250.
        profile, _ = pfd.to_profile(fixture('data-misc.pfd'))
        self.assertEqual([lv.wanted[0] for lv in profile.dpi_levels], [400, 800, 1900, 3200, 4000])
        self.assertEqual([lv.x for lv in profile.dpi_levels[:4]], [500, 750, 2000, 3250])

    def test_factory_settings_match_vcfg(self):
        # valkyrie/data/factory.json holds VCFG's five restore-to-default profiles.
        base, _ = pfd.to_profile(fixture('base.pfd'))
        for n in range(5):
            with self.subTest(profile=n + 1):
                vcfg, macros = pfd.to_profile(fixture(f'factory-game{n + 1}.pfd'))
                ours = ops.factory_profile(n, base)
                self.assertEqual(store.profile_to_dict(ours), store.profile_to_dict(vcfg))
                self.assertEqual(model.encode_profile(ours), model.encode_profile(vcfg))
                self.assertEqual(macros, {})

    def test_too_many_macro_steps(self):
        profile, macros = pfd.to_profile(fixture('macro1.pfd'))
        macros = {s: model.Macro([model.MacroStep('delay', 5)] * 61) for s in macros}
        with self.assertRaisesRegex(ValueError, '60 steps'):
            pfd.from_profile(profile, macros)



class Export(unittest.TestCase):
    FILES = ['base.pfd', 'macro1.pfd', 'data-media.pfd', 'data-misc.pfd'] + \
        [f'vcfg-profile{n}.pfd' for n in range(1, 6)]

    def exported(self, name):
        profile, macros = pfd.to_profile(fixture(name))
        data = pfd.from_profile(profile, macros)
        return (profile, macros), read_back(data), data

    def test_round_trip(self):
        for name in self.FILES:
            with self.subTest(name):
                original, again, _ = self.exported(name)
                self.assertEqual(again, original)

    def test_button_records_match_vcfg(self):
        # Every header (function, category, type, parameter) equals the one VCFG wrote.
        for name in self.FILES:
            with open(fixture(name), 'rb') as f:
                vcfg = f.read()
            _, _, ours = self.exported(name)
            for n in range(pfd.BUTTONS):
                h = pfd.HEADER0 + n * pfd.STRIDE
                with self.subTest(name, button=n + 1):
                    self.assertEqual(ours[h:h + 16], vcfg[h:h + 16])

    def test_macro_record_matches_vcfg(self):
        with open(fixture('macro1.pfd'), 'rb') as f:
            vcfg = f.read()
        _, _, ours = self.exported('macro1.pfd')
        h = pfd.HEADER0 + 3 * pfd.STRIDE
        # VCFG leaves the previous fire-key values at +0xfe4; everything else is equal.
        start = h - pfd.REC_DATA
        self.assertEqual(ours[start:start + 0xFE4], vcfg[start:start + 0xFE4])

    def test_function_table(self):
        for func, (kind, param) in [(16, (0x0F, 902)), (19, (0x0F, 905)), (22, (0x0E, 908)),
                                    (29, (0x0E, 1001)), (35, (0x0E, 1007)), (41, (0x0A, 1302)),
                                    (46, (0x18, 1502)), (47, (0x0E, 16))]:
            self.assertEqual(pfd.FUNCTIONS[func], (kind, param))
        self.assertEqual(len(pfd.FUNCTIONS), 48)

    def test_fire_with_keyboard_key(self):
        with open(fixture('data-misc.pfd'), 'rb') as f:
            vcfg = f.read()
        _, _, ours = self.exported('data-misc.pfd')
        start = pfd.HEADER0 + 4 * pfd.STRIDE - pfd.REC_DATA + 0xFE4
        self.assertEqual(ours[start:start + 8], vcfg[start:start + 8])      # 3x, 50 ms, K
        profile, _ = pfd.to_profile(fixture('data-misc.pfd'))
        self.assertEqual(model.action_to_str(profile.buttons[4]), 'fire:K,3,50')

    def test_dpi_level_off(self):
        profile, _ = pfd.to_profile(fixture('data-misc.pfd'))
        self.assertEqual([lv.enabled for lv in profile.dpi_levels], [True] * 4 + [False])
        with open(fixture('data-misc.pfd'), 'rb') as f:
            vcfg = f.read()
        _, _, ours = self.exported('data-misc.pfd')
        # The whole table, slider values (400, 1900...) included, is what VCFG saved.
        table = slice(pfd.DPI_TABLE, pfd.DPI_TABLE + 50)
        self.assertEqual(ours[table], vcfg[table])
        self.assertEqual(ours[0x12898:0x128A2], vcfg[0x12898:0x128A2])

    def test_windows_settings_exported(self):
        profile, macros = pfd.to_profile(fixture('base.pfd'))
        profile.windows = model.WindowsSettings(7, 400, 14, 2)
        data = pfd.from_profile(profile, macros)
        self.assertEqual(pfd.windows_settings(data), profile.windows)
        profile.windows = None                              # unknown: Windows' defaults
        self.assertEqual(pfd.windows_settings(pfd.from_profile(profile, macros)), model.WindowsSettings())

    def test_arrow_keys_get_the_extended_flag(self):
        profile, macros = pfd.to_profile(fixture('base.pfd'))
        profile.buttons[6] = model.Action('key', code=0x50)              # Left arrow
        profile.buttons[7] = model.Action('key', code=0x5C)              # Num 4
        data = pfd.from_profile(profile, macros)
        for n, expected in ((6, (0x25, 1)), (7, (0x64, 0))):
            start = pfd.HEADER0 + n * pfd.STRIDE - pfd.REC_DATA
            self.assertEqual(pfd.struct.unpack_from('<HH', data, start + 2), expected)
        again, _ = read_back(data)
        self.assertEqual(again.buttons[6:8], profile.buttons[6:8])

    def test_shortcut_with_two_keys(self):
        profile, macros = pfd.to_profile(fixture('base.pfd'))
        profile.buttons[5] = model.parse_action('shortcut:Ctrl+K+C')
        data = pfd.from_profile(profile, macros)
        h = pfd.HEADER0 + 5 * pfd.STRIDE
        start = h - pfd.REC_DATA
        # VCFG's record: key 1, its flag, key 2, its flag, then the modifiers (Ctrl = 2 in .pfd files).
        self.assertEqual(pfd.struct.unpack_from('<5H', data, start + 0x44), (0x4B, 0, 0x43, 0, 2))
        self.assertEqual(pfd.struct.unpack_from('<H', data, h + 2)[0], pfd.CUSTOM_SHORTCUT)
        again, _ = read_back(data)
        self.assertEqual(again.buttons[5], profile.buttons[5])
        self.assertEqual(model.encode_action(again.buttons[5], 5).hex(), '0f010e06')

    def test_separate_x_and_y_like_vcfg(self):
        profile, macros = pfd.to_profile(fixture('base.pfd'))
        profile.dpi_levels[2].set(1600, 800)
        again, _ = read_back(pfd.from_profile(profile, macros))
        lv = again.dpi_levels[2]
        self.assertEqual((lv.wanted, lv.x, lv.y), ((1600, 800), 1500, 1500))   # max(X, Y) for both

    def test_refuses_what_vcfg_has_no_entry_for(self):
        profile, macros = pfd.to_profile(fixture('base.pfd'))
        profile.buttons[4] = model.Action('media', code=0x18A)        # Email
        with self.assertRaisesRegex(ValueError, 'button 5'):
            pfd.from_profile(profile, macros)


if __name__ == '__main__':
    unittest.main()
