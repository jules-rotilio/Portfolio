"""The command line end to end, against a simulated mouse holding the real memory dump."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401  (before valkyrie: no real config files)

import captures  # noqa: E402
from valkyrie import cli, device, host, model, store  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')


class CliTest(unittest.TestCase):
    def setUp(self):
        self.fake = device.FakeMouse(captures.memory_dump())
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = (device.open_mouse, device.conflicting_programs, store.BACKUP_DIR)
        self.saved_host = host.CONFIG_DIR
        self.config_dir = tempfile.TemporaryDirectory()
        host.CONFIG_DIR = self.config_dir.name
        device.open_mouse = lambda path=None: device.Mouse(self.fake, pace=False)
        device.conflicting_programs = lambda: []
        store.BACKUP_DIR = self.tmp.name

    def tearDown(self):
        device.open_mouse, device.conflicting_programs, store.BACKUP_DIR = self.saved
        host.CONFIG_DIR = self.saved_host
        self.config_dir.cleanup()
        self.tmp.cleanup()

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            status = cli.main(list(argv))
        return status, out.getvalue()

    def block(self, addr, length):
        return bytes(self.fake.memory[addr:addr + length])

    def writes(self):
        return [f for kind, f in self.fake.frames if kind == 'set' and f[1] == device.WRITE]

    def test_set_writes_backs_up_and_verifies(self):
        status, out = self.run_cli('set', '--color', '#00aaff', '--breathing', 'off', '--button', '10=key:Q')
        self.assertEqual(status, 0, out)
        self.assertIn('written and verified', out)
        self.assertEqual(self.block(device.light_addr(4), 6).hex(), 'ff5500020000')
        slot = model.SLOT_BUTTONS.index(10)
        self.assertEqual(self.block(device.buttons_addr(4) + 1 + 4 * slot, 4).hex(), '10001400')
        self.assertEqual(len(os.listdir(self.tmp.name)), 1)

    def test_dry_run_sends_no_writes(self):
        before = bytes(self.fake.memory)
        status, out = self.run_cli('set', '--dpi', '3=1600', '--dry-run')
        self.assertEqual(status, 0, out)
        self.assertIn('02 02 4f 04 2a 00 fa fa', out.replace('03 02', '02 02'))
        self.assertEqual(self.writes(), [])
        self.assertEqual(bytes(self.fake.memory), before)

    def test_refuses_while_vcfg_runs(self):
        device.conflicting_programs = lambda: ['vmon.exe']
        status, out = self.run_cli('set', '--color', '#ffffff')
        self.assertEqual(status, 1)
        self.assertIn('vmon.exe', out)
        self.assertEqual(self.writes(), [])

    def test_refuses_bad_values(self):
        for argv in (['set', '--dpi', '3=9000'], ['set', '--button', '14=left'],
                     ['set', '--dpi-off', '3'], ['set'], ['set', '--button', '4=macro:31'],
                     ['set', '--button', '4=macro:9'], ['set', '--dpi', '3=200']):
            with self.subTest(argv=argv):
                status, _ = self.run_cli(*argv)
                self.assertEqual(status, 1)
        self.assertEqual(self.writes(), [])

    def test_import_pfd(self):
        status, out = self.run_cli('import-pfd', os.path.join(FIXTURES, 'vcfg-profile2.pfd'), '--profile', '5')
        self.assertEqual(status, 0, out)
        for addr, size in ((device.dpi_addr, 42), (device.buttons_addr, 57), (device.light_addr, 6)):
            self.assertEqual(self.block(addr(4), size), self.block(addr(1), size))   # same as profile 2
        self.assertEqual(self.fake.memory[device.POLLING + 4], 2)      # 500 Hz like profile 2

    def test_macro_is_shared_and_lengths_follow(self):
        status, out = self.run_cli('macro', '1', 'A down, wait 50, A up', '--button', '9')
        self.assertEqual(status, 0, out)
        data = model.encode_macro(model.Macro(model.parse_steps('A down, wait 50, A up')))
        self.assertEqual(self.block(device.macro_addr(0), len(data)), data)
        entry = device.buttons_addr(4) + 1 + 4 * model.SLOT_BUTTONS.index(9)
        self.assertEqual(self.block(entry, 4), bytes([0x11, 0, len(data), 0]))
        # Longer content without --button: profile 5 still uses it and gets the new length
        status, out = self.run_cli('macro', '1', 'A down, A up, B down, B up')
        self.assertEqual(status, 0, out)
        self.assertEqual(self.fake.memory[entry + 2], 15)

    def test_export_edit_apply(self):
        path = os.path.join(self.tmp.name, 'profiles.json')
        self.assertEqual(self.run_cli('export', path)[0], 0)
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        data['profiles']['5']['buttons']['10'] = 'shortcut:Ctrl+Shift+Z'
        data['profiles']['5']['dpi']['levels'][1] = 1000
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        status, out = self.run_cli('apply', path, '--profile', '5')
        self.assertEqual(status, 0, out)
        self.assertIn('buttons.10: key:LeftCtrl -> shortcut:Ctrl+Shift+Z', out)
        state = device.open_mouse().read_state()
        self.assertEqual(state.profiles[4].dpi_levels[1].x, 1000)
        self.assertEqual(model.action_to_str(state.profiles[4].buttons[9]), 'shortcut:Ctrl+Shift+Z')

    def test_restore_undoes_changes(self):
        original = bytes(self.fake.memory)
        self.run_cli('backup', os.path.join(self.tmp.name, 'b.json'))
        self.run_cli('set', '--color', '#123456', '--polling', '125')
        self.assertNotEqual(bytes(self.fake.memory), original)
        status, out = self.run_cli('restore', os.path.join(self.tmp.name, 'b.json'))
        self.assertEqual(status, 0, out)
        self.assertEqual(bytes(self.fake.memory[:0x500]), original[:0x500])

    def test_dpi_between_the_mouse_steps(self):
        status, out = self.run_cli('set', '--dpi', '3=1900')
        self.assertEqual(status, 0, out)
        self.assertIn('it uses 2000', out)
        self.assertEqual(self.block(device.dpi_addr(4) + 2 + 16, 5).hex(), '0108000800')   # 2000 for X and Y
        status, out = self.run_cli('show')
        self.assertIn('3: 1900 (mouse 2000) (selected)', out)
        status, out = self.run_cli('set', '--dpi', '3=1600x800')                         # max(X, Y) like VCFG
        self.assertEqual(self.block(device.dpi_addr(4) + 2 + 16, 5).hex(), '0106000600')
        self.assertIn('3: 1600x800 (mouse 1500)', self.run_cli('show')[1])

    def test_only_pc_side_change_writes_nothing(self):
        status, out = self.run_cli('set', '--dpi', '3=2000')       # what profile 5 holds already...
        self.assertEqual(status, 1)                                  # ...is nothing to change
        before = len(self.writes())
        self.run_cli('set', '--dpi', '3=1950')                      # still 2000 on the mouse
        self.assertEqual(len(self.writes()), before)
        self.assertIn('1950 (mouse 2000)', self.run_cli('show')[1])

    def test_factory_reset(self):
        status, out = self.run_cli('factory-reset', '--dry-run')
        self.assertEqual(status, 0, out)
        self.assertEqual(self.writes(), [])
        status, out = self.run_cli('factory-reset', '--profile', '1')
        self.assertEqual(status, 0, out)
        state = device.open_mouse().read_state()
        p = state.profiles[0]
        self.assertEqual([lv.x for lv in p.dpi_levels], [500, 750, 1500, 3250, 4000])
        self.assertEqual(p.light.rgb, (255, 255, 0))
        self.assertEqual(model.action_to_str(p.buttons[3]), 'media:mute')
        out = self.run_cli('show', '--profile', '1')[1]
        self.assertIn('1: 400 (mouse 500)', out)
        self.assertIn('Windows only   pointer speed 10', out)

    def test_shortcut_with_two_keys(self):
        status, out = self.run_cli('set', '--button', '6=shortcut:Ctrl+K+C')
        self.assertEqual(status, 0, out)
        entry = device.buttons_addr(4) + 1 + 4 * model.SLOT_BUTTONS.index(6)
        self.assertEqual(self.block(entry, 4).hex(), '0f010e06')
        self.assertIn('Shortcut: Ctrl+K+C', self.run_cli('show')[1])

    def test_macro_slots_beyond_five(self):
        status, out = self.run_cli('macro', '30', 'A down, A up', '--button', '9')
        self.assertEqual(status, 0, out)
        data = model.encode_macro(model.Macro(model.parse_steps('A down, A up')))
        self.assertEqual(self.block(device.macro_addr(29), len(data)), data)

    def test_switch_profile(self):
        status, out = self.run_cli('profile', '2')
        self.assertEqual(status, 0, out)
        self.assertEqual(self.fake.memory[device.ACTIVE_PROFILE], 1)


class JsonRoundTrip(unittest.TestCase):
    def test_every_profile_survives_export_and_apply(self):
        state = device.Mouse(device.FakeMouse(captures.memory_dump()), pace=False).read_state()
        data = json.loads(json.dumps(store.export_dict(state, sorted(state.profiles))))
        for n, p in state.profiles.items():
            again = store.profile_from_dict(data['profiles'][str(n + 1)], p)
            self.assertEqual(model.encode_profile(again), model.encode_profile(p))


if __name__ == '__main__':
    unittest.main()
