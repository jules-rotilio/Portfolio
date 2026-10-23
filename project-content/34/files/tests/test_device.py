import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401  (before valkyrie: no real config files)

import captures  # noqa: E402
from valkyrie import device, model  # noqa: E402


def memory_after_vcfg():
    """Mouse memory as VCFG left it, rebuilt from every write in the captures."""
    mem = bytearray(b'\xff' * 0x1000)
    for name in captures.ALL:
        for _, addr, payload in captures.writes(name):
            mem[addr:addr + len(payload)] = payload
    return mem


class Frames(unittest.TestCase):
    def test_rebuilds_every_frame_vcfg_sent(self):
        count = 0
        for name in captures.ALL:
            for _, kind, rid, frame in captures.transfers(name):
                if kind != 'set':
                    continue
                cmd = frame[1]
                addr, length = frame[2] | frame[3] << 8, frame[4] | frame[5] << 8
                if cmd == device.WRITE:
                    rebuilt = device.data_frame(cmd, addr, length, frame[8:8 + length])
                elif cmd == device.READ:
                    rebuilt = device.data_frame(cmd, addr, length)
                else:
                    rebuilt = device.command_frame(cmd, *frame[2:].rstrip(b'\0'))
                with self.subTest(capture=name, frame=frame[:8].hex(' ')):
                    self.assertEqual(rebuilt, frame)
                count += 1
        self.assertGreater(count, 500)


class Reading(unittest.TestCase):
    def test_read_matches_vcfg_frames(self):
        fake = device.FakeMouse(memory_after_vcfg())
        mouse = device.Mouse(fake, pace=False)
        with mouse.session():
            mouse.read(0x43, 1)
            mouse.read(device.dpi_addr(4), 42)
        # VCFG's startup in cap.bin: 06 00, read 0x43, GET 2, read 0x44f, GET 3, 06 01
        vcfg = [(k, f) for _, k, _, f in captures.transfers('cap.bin')[:6]]
        self.assertEqual([(k, f[:8]) for k, f in fake.frames], [(k, f[:8]) for k, f in vcfg])
        self.assertEqual([f for k, f in fake.frames if k == 'set'], [f for k, f in vcfg if k == 'set'])

    def test_read_state_decodes_vcfg_memory(self):
        mem = memory_after_vcfg()
        mem[0x43] = 4
        state = device.Mouse(device.FakeMouse(mem), pace=False).read_state()
        self.assertEqual(state.active, 4)
        p = state.profiles[0]
        self.assertEqual(p.polling_hz, 500)
        self.assertEqual([lv.x for lv in p.dpi_levels], [1000, 1500, 2250, 3250, 4000])
        self.assertEqual(model.describe_action(p.buttons[3]), 'Media: Mute')
        # VCFG never wrote profiles 2-4 in the captures: reported, not a crash
        self.assertEqual(sorted(state.profiles), [0, 4])
        self.assertEqual(sorted(state.errors), [1, 2, 3])

    def test_wrong_echo_is_detected(self):
        class Confused(device.FakeMouse):
            def get_feature(self, rid):
                reply = bytearray(super().get_feature(rid))
                reply[2] ^= 0xFF            # an answer to some other address
                return bytes(reply)
        mouse = device.Mouse(Confused(), pace=False)
        self.assertRaises(device.DeviceError, mouse.read, 0x43, 1)


def vcfg_applies(name):
    """Every VCFG Apply in a capture: the transfers from its 06 00, 06 00 to its 01 01 00."""
    found = []
    for burst in captures.bursts(name):
        tr = [(kind, rid, frame) for _, kind, rid, frame in burst]
        i = 0
        while i < len(tr) - 1:
            if all(k == 'set' and f[:3] == b'\x02\x06\x00' for k, _, f in tr[i:i + 2]):
                end = next((j for j in range(i, len(tr)) if tr[j][2][:4] == b'\x02\x01\x01\x00'), None)
                if end is None:
                    break
                found.append(tr[i:end + 1])
                i = end
            i += 1
    return found


def vcfg_apply(name, index):
    """Frames of the index-th VCFG Apply in a capture, and the blocks and macros it wrote."""
    frames = vcfg_applies(name)[index]
    blocks, macros = {}, {}
    for kind, rid, f in frames:
        if kind == 'set' and f[1] == device.WRITE:
            addr, length = f[2] | f[3] << 8, f[4] | f[5] << 8
            data = f[8:8 + length]
            if addr >= device.MACRO_BASE:
                macros[(addr - device.MACRO_BASE) // model.MACRO_SIZE] = data
            elif addr & 0xFF == 0x4F:
                blocks['dpi'] = data
            elif addr & 0xFF == 0x90:
                blocks['buttons'] = data
            elif addr & 0xFF == 0xF1:
                blocks['light'] = data
            elif device.POLLING <= addr < device.POLLING + device.PROFILES:
                blocks['polling'] = data
    return frames, blocks, macros


class Writing(unittest.TestCase):
    def check_same_as_vcfg(self, name, burst_index, n):
        frames, blocks, macros = vcfg_apply(name, burst_index)
        fake = device.FakeMouse(memory_after_vcfg())
        fake.memory[0x43] = 4
        device.Mouse(fake, pace=False).apply_blocks(n, blocks, macros)
        ours = [(k, f if k == 'set' else f[0]) for k, f in fake.frames]
        theirs = [(k, f if k == 'set' else rid) for k, rid, f in frames]
        self.assertEqual(ours, theirs)

    def test_apply_is_identical_to_vcfg(self):
        self.check_same_as_vcfg('cap.bin', 1, 4)         # 20:56:48, plain Apply

    def test_apply_with_macro_is_identical_to_vcfg(self):
        self.check_same_as_vcfg('cap5.bin', 0, 4)        # 21:58:54, Apply with Macro1

    def test_switch_profile_is_identical_to_vcfg(self):
        fake = device.FakeMouse()
        device.Mouse(fake, pace=False).switch_profile(3)
        burst = next(b for b in captures.bursts('cap.bin')
                     if [f[:9] for _, k, _, f in b][:1] == [bytes.fromhex('02 02 43 00 01 00 fa fa 03')])
        self.assertEqual([f for k, f in fake.frames], [f for _, _, _, f in burst[:2]])

    def test_apply_profile_round_trip_and_verify(self):
        fake = device.FakeMouse(memory_after_vcfg())
        mouse = device.Mouse(fake, pace=False)
        state = mouse.read_state(profiles=[4])
        p = state.profiles[4]
        p.light = model.Light((0, 170, 255), 3, 0)
        p.buttons[9] = model.parse_action('macro:2,repeat')
        macros = {1: model.Macro(model.parse_steps('G down, G up'))}
        blocks, data = mouse.apply_profile(4, p, macros)
        self.assertEqual(mouse.verify(4, blocks, data), [])
        again = mouse.read_state(profiles=[4]).profiles[4]
        self.assertEqual(again.light, p.light)
        self.assertEqual(again.buttons[9], p.buttons[9])
        fake.memory[device.light_addr(4)] ^= 1           # the mouse did not store it
        self.assertEqual(mouse.verify(4, blocks, data), ['light'])

    def test_real_mouse_memory_reencodes_identically(self):
        state = device.Mouse(device.FakeMouse(captures.memory_dump()), pace=False).read_state()
        self.assertEqual(state.errors, {})
        for n, p in state.profiles.items():
            self.assertEqual(model.encode_profile(p), state.blocks[n])


class LiveDpiLevel(unittest.TestCase):
    """VCFG's Apply reads the active profile's DPI block first and keeps the level
    picked on the mouse (Dev_ReadActiveProfileAndDpi)."""

    def setUp(self):
        self.fake = device.FakeMouse(captures.memory_dump())          # profile 5 active, level 3
        self.mouse = device.Mouse(self.fake, pace=False)
        self.state = self.mouse.read_state()

    def picked_on_mouse(self, n, level):
        self.fake.memory[device.dpi_addr(n) + 1] = level

    def test_kept_for_the_active_profile(self):
        self.picked_on_mouse(4, 0)                    # DPI button pressed after reading
        p = self.state.profiles[4]
        p.light.breathing = 0
        blocks, _ = self.mouse.apply_profile(4, p, keep_stage=True)
        self.assertEqual(blocks['dpi'][1], 0)
        self.assertEqual(self.fake.memory[device.dpi_addr(4) + 1], 0)
        self.assertEqual(self.mouse.verify(4, blocks), [])

    def test_not_kept_when_asked_for_or_for_other_profiles(self):
        self.picked_on_mouse(4, 0)
        p = self.state.profiles[4]
        blocks, _ = self.mouse.apply_profile(4, p)                     # the level chosen here wins
        self.assertEqual(blocks['dpi'][1], 2)
        self.picked_on_mouse(4, 0)
        blocks, _ = self.mouse.apply_profile(3, self.state.profiles[3], keep_stage=True)
        self.assertEqual(blocks['dpi'][1], self.state.profiles[3].dpi_selected)

    def test_not_kept_if_that_level_is_now_off(self):
        self.picked_on_mouse(4, 0)
        p = self.state.profiles[4]
        p.dpi_levels[0].enabled = False
        blocks, _ = self.mouse.apply_profile(4, p, keep_stage=True)
        self.assertEqual(blocks['dpi'][1], 2)

    def test_reads_the_active_profile_like_vcfg(self):
        self.fake.frames.clear()
        self.mouse.apply_profile(1, self.state.profiles[1])
        reads = [f[2] | f[3] << 8 for k, f in self.fake.frames if k == 'set' and f[1] == device.READ]
        self.assertEqual(reads, [device.ACTIVE_PROFILE, device.dpi_addr(4)])


class MacroSlots(unittest.TestCase):
    def test_thirty_slots(self):
        self.assertEqual(device.MACRO_SLOTS, 30)
        device.check_writable(device.macro_addr(29), model.MACRO_SIZE)
        self.assertEqual(device.macro_addr(29) + model.MACRO_SIZE, 0x1C70)

    def test_empty_slot_costs_one_read(self):
        fake = device.FakeMouse(captures.memory_dump())
        mouse = device.Mouse(fake, pace=False)
        self.assertIsNone(mouse.read_macro_slot(25))
        self.assertEqual(sum(1 for k, _ in fake.frames if k == 'get'), 1)

    def test_slot_above_4k(self):
        fake = device.FakeMouse()
        mouse = device.Mouse(fake, pace=False)
        macro = model.Macro(model.parse_steps('A down, A up'))
        mouse.write(device.macro_addr(29), model.encode_macro(macro))
        self.assertEqual(mouse.read_macro_slot(29), macro)


class Safety(unittest.TestCase):
    def test_allowlist(self):
        for addr, length in [(0x43, 1), (0x4C, 1), (0x44F, 42), (0x90, 57), (0x3F1, 6), (0x500, 200)]:
            device.check_writable(addr, length)
        for addr, length in [(0x44, 1), (0x47, 1), (0x00, 1), (0x4F, 43), (0x4D, 1),
                             (0x500 + 200 * device.MACRO_SLOTS, 1), (0x42, 2)]:
            with self.subTest(addr=hex(addr), length=length):
                self.assertRaises(ValueError, device.check_writable, addr, length)

    def test_refused_write_sends_nothing(self):
        fake = device.FakeMouse()
        self.assertRaises(ValueError, device.Mouse(fake, pace=False).write, 0x44, b'\x00')
        self.assertEqual(fake.frames, [])

    def test_report_choice_matches_vcfg(self):
        for length, rid in [(1, 2), (6, 2), (8, 2), (9, 3), (24, 3), (42, 3), (56, 3), (57, 4), (200, 4)]:
            self.assertEqual(device.report_for(length), rid)


if __name__ == '__main__':
    unittest.main()
