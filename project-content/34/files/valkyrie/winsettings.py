"""A profile's Windows pointer settings, applied the way VCFG does on Apply and on a
profile switch (Win_ApplyMouseSettings 0x634fe8, re/FINDINGS.md section 6). Windows
only: on Linux the desktop's own mouse settings do this."""
import ctypes

SPI_SETMOUSE, SPI_SETWHEELSCROLLLINES, SPI_SETMOUSESPEED = 0x0004, 0x0069, 0x0071
SPIF = 0x03                     # SPIF_UPDATEINIFILE | SPIF_SENDCHANGE, as VCFG passes
# VCFG's 4 acceleration levels: mouse thresholds 1 and 2, and the acceleration.
ACCELERATION = [(0, 0, 0), (7, 0, 1), (4, 6, 2), (4, 0, 1)]


def apply(w):
    """Apply a model.WindowsSettings. Raises OSError if Windows refuses one."""
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    spi = user32.SystemParametersInfoW
    spi.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
    accel = (ctypes.c_int * 3)(*ACCELERATION[w.acceleration])
    calls = [('acceleration', lambda: spi(SPI_SETMOUSE, 0, ctypes.cast(accel, ctypes.c_void_p), SPIF)),
             ('pointer speed', lambda: spi(SPI_SETMOUSESPEED, 0, ctypes.c_void_p(w.pointer_speed), SPIF)),
             ('scroll lines', lambda: spi(SPI_SETWHEELSCROLLLINES, w.scroll_lines, None, SPIF)),
             ('double-click time', lambda: user32.SetDoubleClickTime(w.double_click_ms))]
    for what, call in calls:
        if not call():
            raise OSError(f'Windows refused the {what}: {ctypes.FormatError(ctypes.get_last_error())}')
