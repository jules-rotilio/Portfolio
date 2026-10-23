"""valkyrie-monitor on Windows: a tray program in place of VMON.exe.

It listens to the mouse's vendor collection (several programs can, VMON included),
shows the notifications from its tray icon, and on a profile switch applies that
profile's Windows pointer settings, which is VMON's main job (winsettings.py).

exact_dpi is not available yet: Windows has no uinput, and scaling one mouse needs
a driver. VCFG's filter driver does it (re/FINDINGS.md section 7), but the layout of
the CPI table it takes is still unknown. Off-grid DPI values therefore behave as on
Linux without the monitor: the mouse uses the nearest step of 250.

Run VMON or this, not both: VMON re-applies its own settings on every profile switch.
"""
import time

from . import device, hid_windows, winsettings, winui
from .autoclick import log
from .monitor import BaseDaemon


class Daemon(BaseDaemon):
    def make_notifier(self):
        return winui.Notifier(log)

    def exact_dpi_available(self):
        log('exact_dpi is not available on Windows yet (it needs VCFG\'s driver); '
            'the mouse uses the nearest step of 250')
        return False

    def scaling_changed(self):
        pass

    def close_proxy(self):
        pass

    def on_profile(self):
        """Apply the new profile's Windows pointer settings, as VMON does."""
        if not self.config.pointer_settings:
            return
        settings = self.tracker.windows.get(self.tracker.active)
        if settings is None:
            log('no Windows pointer settings known for this profile (open it in the window and Apply)')
            return
        try:
            winsettings.apply(settings)
            log(f'pointer speed {settings.pointer_speed}, acceleration {settings.acceleration}, '
                f'scroll {settings.scroll_lines} lines, double-click {settings.double_click_ms} ms')
        except OSError as e:
            log(str(e))

    def loop(self):
        if 'vmon.exe' in hid_windows.processes():
            log('VMON.exe is running too: it re-applies its own settings on profile switches; '
                'remove it from startup to use valkyrie-monitor alone')
        self.host_changed()
        self.load_host()                    # until the mouse is read
        try:
            while not self.stopping:
                if self.reload_wanted:
                    self.reload()
                self.periodic()
                if self.listener is None:
                    time.sleep(0.25)
                    continue
                try:
                    got = self.listener.read(timeout=0.25)       # short: Quit and reload stay quick
                except device.DeviceError:
                    self.mouse_gone()
                    continue
                self.on_events(got)
        finally:
            self.close_listener()

    def run(self):
        self.reload()                  # here, so a broken settings file stops the program with its error
        winui.run('Drakkar Valkyrie monitor', self.loop, self.stop, self.request_reload, self.notifier)
