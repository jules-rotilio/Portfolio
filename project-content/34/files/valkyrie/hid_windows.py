"""The mouse's vendor interface on Windows, through the HID class driver (ctypes only).

This is what VCFG does (re/FINDINGS.md section 2): SetupAPI lists the HID interfaces,
the one with VID/PID 04d9:fc06 and usage page 0xFFA0 is opened with shared access,
and every command is one HidD_SetFeature or HidD_GetFeature of the report's own
size. Windows gives each top-level collection its own path, so the mouse and
keyboard collections are simply skipped. No driver or permission setup is needed.

Input reports (the mouse's own buttons, events.py) are read with overlapped ReadFile
on a second handle; Windows gives every open handle its own copy of each report.
"""
import ctypes
from ctypes import wintypes

from .device import PRODUCT_ID, REPORT_SIZES, VENDOR_ID, DeviceError

VENDOR_USAGE_PAGE = 0xFFA0

_setupapi = ctypes.WinDLL('setupapi', use_last_error=True)
_hid = ctypes.WinDLL('hid', use_last_error=True)
_k32 = ctypes.WinDLL('kernel32', use_last_error=True)

DIGCF_PRESENT, DIGCF_DEVICEINTERFACE = 0x02, 0x10
GENERIC_READ, GENERIC_WRITE = 0x80000000, 0x40000000
FILE_SHARE_READ, FILE_SHARE_WRITE = 0x01, 0x02
OPEN_EXISTING, FILE_FLAG_OVERLAPPED = 3, 0x40000000
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
ERROR_ACCESS_DENIED, ERROR_SHARING_VIOLATION, ERROR_GEN_FAILURE = 5, 32, 31
ERROR_INVALID_PARAMETER, ERROR_NO_MORE_ITEMS, ERROR_OPERATION_ABORTED = 87, 259, 995
ERROR_IO_PENDING, ERROR_DEVICE_NOT_CONNECTED, ERROR_BAD_COMMAND = 997, 1167, 22
WAIT_OBJECT_0, WAIT_TIMEOUT, INFINITE = 0, 0x102, 0xFFFFFFFF
HIDP_STATUS_SUCCESS = 0x00110000
GONE = (ERROR_DEVICE_NOT_CONNECTED, ERROR_GEN_FAILURE, ERROR_BAD_COMMAND, ERROR_OPERATION_ABORTED)


class GUID(ctypes.Structure):
    _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD), ('Data3', wintypes.WORD),
                ('Data4', ctypes.c_ubyte * 8)]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('InterfaceClassGuid', GUID), ('Flags', wintypes.DWORD),
                ('Reserved', ctypes.c_size_t)]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [('Size', wintypes.ULONG), ('VendorID', wintypes.USHORT), ('ProductID', wintypes.USHORT),
                ('VersionNumber', wintypes.USHORT)]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [('Usage', wintypes.USHORT), ('UsagePage', wintypes.USHORT),
                ('InputReportByteLength', wintypes.USHORT), ('OutputReportByteLength', wintypes.USHORT),
                ('FeatureReportByteLength', wintypes.USHORT), ('Reserved', wintypes.USHORT * 17),
                ('NumberLinkCollectionNodes', wintypes.USHORT), ('NumberInputButtonCaps', wintypes.USHORT),
                ('NumberInputValueCaps', wintypes.USHORT), ('NumberInputDataIndices', wintypes.USHORT),
                ('NumberOutputButtonCaps', wintypes.USHORT), ('NumberOutputValueCaps', wintypes.USHORT),
                ('NumberOutputDataIndices', wintypes.USHORT), ('NumberFeatureButtonCaps', wintypes.USHORT),
                ('NumberFeatureValueCaps', wintypes.USHORT), ('NumberFeatureDataIndices', wintypes.USHORT)]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                ('Offset', wintypes.DWORD), ('OffsetHigh', wintypes.DWORD), ('hEvent', wintypes.HANDLE)]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD),
                ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', wintypes.DWORD),
                ('cntThreads', wintypes.DWORD), ('th32ParentProcessID', wintypes.DWORD),
                ('pcPriClassBase', wintypes.LONG), ('dwFlags', wintypes.DWORD),
                ('szExeFile', wintypes.WCHAR * 260)]


def _sig(dll, name, restype, *argtypes):
    fn = getattr(dll, name)
    fn.restype, fn.argtypes = restype, list(argtypes)


_sig(_hid, 'HidD_GetHidGuid', None, ctypes.POINTER(GUID))
_sig(_hid, 'HidD_GetAttributes', wintypes.BOOLEAN, wintypes.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES))
_sig(_hid, 'HidD_GetPreparsedData', wintypes.BOOLEAN, wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p))
_sig(_hid, 'HidD_FreePreparsedData', wintypes.BOOLEAN, ctypes.c_void_p)
_sig(_hid, 'HidP_GetCaps', wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS))
_sig(_hid, 'HidD_SetFeature', wintypes.BOOLEAN, wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG)
_sig(_hid, 'HidD_GetFeature', wintypes.BOOLEAN, wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG)
_sig(_setupapi, 'SetupDiGetClassDevsW', wintypes.HANDLE, ctypes.POINTER(GUID), wintypes.LPCWSTR,
     wintypes.HWND, wintypes.DWORD)
_sig(_setupapi, 'SetupDiEnumDeviceInterfaces', wintypes.BOOL, wintypes.HANDLE, ctypes.c_void_p,
     ctypes.POINTER(GUID), wintypes.DWORD, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA))
_sig(_setupapi, 'SetupDiGetDeviceInterfaceDetailW', wintypes.BOOL, wintypes.HANDLE,
     ctypes.POINTER(SP_DEVICE_INTERFACE_DATA), ctypes.c_void_p, wintypes.DWORD,
     ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p)
_sig(_setupapi, 'SetupDiDestroyDeviceInfoList', wintypes.BOOL, wintypes.HANDLE)
_sig(_k32, 'CreateFileW', wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
     wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
_sig(_k32, 'CloseHandle', wintypes.BOOL, wintypes.HANDLE)
_sig(_k32, 'CreateEventW', wintypes.HANDLE, wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR)
_sig(_k32, 'ResetEvent', wintypes.BOOL, wintypes.HANDLE)
_sig(_k32, 'ReadFile', wintypes.BOOL, wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
     ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(OVERLAPPED))
_sig(_k32, 'GetOverlappedResult', wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(OVERLAPPED),
     ctypes.POINTER(wintypes.DWORD), wintypes.BOOL)
_sig(_k32, 'CancelIoEx', wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(OVERLAPPED))
_sig(_k32, 'WaitForSingleObject', wintypes.DWORD, wintypes.HANDLE, wintypes.DWORD)
_sig(_k32, 'CreateToolhelp32Snapshot', wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD)
_sig(_k32, 'Process32FirstW', wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
_sig(_k32, 'Process32NextW', wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))


def _error(what, code=None):
    code = ctypes.get_last_error() if code is None else code
    if code in GONE:
        return DeviceError('the mouse was unplugged')
    if code in (ERROR_ACCESS_DENIED, ERROR_SHARING_VIOLATION):
        return DeviceError(f'{what}: access denied (another program holds the mouse exclusively)')
    return DeviceError(f'{what}: {ctypes.FormatError(code).strip()} (Windows error {code})')


def _open(path, access, flags=0):
    return _k32.CreateFileW(path, access, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, flags, None)


def _interfaces():
    """Paths of the HID interfaces present."""
    guid = GUID()
    _hid.HidD_GetHidGuid(ctypes.byref(guid))
    info = _setupapi.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if info == INVALID_HANDLE_VALUE:
        raise _error('listing HID devices')
    try:
        index = 0
        while True:
            data = SP_DEVICE_INTERFACE_DATA(cbSize=ctypes.sizeof(SP_DEVICE_INTERFACE_DATA))
            if not _setupapi.SetupDiEnumDeviceInterfaces(info, None, ctypes.byref(guid), index, ctypes.byref(data)):
                return
            index += 1
            size = wintypes.DWORD()
            _setupapi.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(data), None, 0, ctypes.byref(size), None)
            buf = ctypes.create_string_buffer(size.value)
            # SP_DEVICE_INTERFACE_DETAIL_DATA_W: cbSize is the size of the fixed part.
            ctypes.c_uint32.from_buffer(buf).value = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            if _setupapi.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(data), buf, size, None, None):
                yield ctypes.wstring_at(ctypes.addressof(buf) + 4)
    finally:
        _setupapi.SetupDiDestroyDeviceInfoList(info)


def caps(handle):
    pp = ctypes.c_void_p()
    if not _hid.HidD_GetPreparsedData(handle, ctypes.byref(pp)):
        return None
    try:
        c = HIDP_CAPS()
        return c if _hid.HidP_GetCaps(pp, ctypes.byref(c)) == HIDP_STATUS_SUCCESS else None
    finally:
        _hid.HidD_FreePreparsedData(pp)


def find_device():
    """Path of the mouse's vendor collection (usage page 0xFFA0)."""
    wanted = f'vid_{VENDOR_ID:04x}&pid_{PRODUCT_ID:04x}'
    for path in _interfaces():
        if wanted not in path.lower():
            continue
        h = _open(path, 0)                       # no access needed to read the attributes
        if h == INVALID_HANDLE_VALUE:
            continue
        try:
            attrs = HIDD_ATTRIBUTES(Size=ctypes.sizeof(HIDD_ATTRIBUTES))
            if not _hid.HidD_GetAttributes(h, ctypes.byref(attrs)):
                continue
            c = caps(h)
            if (attrs.VendorID, attrs.ProductID) == (VENDOR_ID, PRODUCT_ID) and c and \
                    c.UsagePage == VENDOR_USAGE_PAGE:
                return path
        finally:
            _k32.CloseHandle(h)
    raise DeviceError('Drakkar Valkyrie not found (is it plugged in?)')


class Device:
    def __init__(self, path=None):
        self.path = path or find_device()
        self.handle = _open(self.path, GENERIC_READ | GENERIC_WRITE)
        if self.handle == INVALID_HANDLE_VALUE:
            raise _error(f'cannot open the mouse ({self.path})')
        c = caps(self.handle)
        self.feature_size = c.FeatureReportByteLength if c else 0

    def set_feature(self, frame):
        buf = ctypes.create_string_buffer(bytes(frame), len(frame))
        if not _hid.HidD_SetFeature(self.handle, buf, len(frame)):
            raise _error('sending a feature report')

    def get_feature(self, rid):
        buf = ctypes.create_string_buffer(REPORT_SIZES[rid])
        buf[0] = rid
        if not _hid.HidD_GetFeature(self.handle, buf, REPORT_SIZES[rid]):
            raise _error('reading a feature report')
        return buf.raw

    def close(self):
        if self.handle is not None:
            _k32.CloseHandle(self.handle)
            self.handle = None


class Listener:
    """Reads the vendor collection's input reports. Several programs can listen at
    once (valkyrie-monitor, the window, VMON); each gets every report."""

    def __init__(self, path=None):
        self.path = path or find_device()
        self.handle = _open(self.path, GENERIC_READ, FILE_FLAG_OVERLAPPED)
        if self.handle == INVALID_HANDLE_VALUE:
            raise _error(f'cannot read the mouse ({self.path})')
        c = caps(self.handle)
        self.size = c.InputReportByteLength if c and c.InputReportByteLength else 64
        self.event = _k32.CreateEventW(None, True, False, None)
        self.overlapped = OVERLAPPED(hEvent=self.event)
        self.buf = ctypes.create_string_buffer(self.size)
        self.pending = False

    def _start(self):
        """Start a read; -> True if a report is already there."""
        _k32.ResetEvent(self.event)
        if _k32.ReadFile(self.handle, self.buf, self.size, None, ctypes.byref(self.overlapped)):
            self.pending = True
            return True
        code = ctypes.get_last_error()
        if code != ERROR_IO_PENDING:
            raise _error('reading the mouse', code)
        self.pending = True
        return False

    def _finish(self):
        n = wintypes.DWORD()
        self.pending = False
        if not _k32.GetOverlappedResult(self.handle, ctypes.byref(self.overlapped), ctypes.byref(n), False):
            raise _error('reading the mouse')
        return self.buf.raw[:n.value]

    def read(self, timeout=0):
        """-> list of raw reports (report ID first), waiting up to `timeout` seconds
        (None: until one comes) for the first. Raises DeviceError if the mouse is gone."""
        if self.handle is None:
            raise DeviceError('the listener is closed')
        reports = []
        wait = INFINITE if timeout is None else int(timeout * 1000)
        while True:
            if not self.pending:
                self._start()
            if _k32.WaitForSingleObject(self.event, wait) != WAIT_OBJECT_0:
                return reports                          # the read stays pending for next time
            reports.append(self._finish())
            wait = 0                                     # then only what is already there

    def close(self):
        if self.handle is None:
            return
        if self.pending:
            _k32.CancelIoEx(self.handle, ctypes.byref(self.overlapped))
            n = wintypes.DWORD()
            _k32.GetOverlappedResult(self.handle, ctypes.byref(self.overlapped), ctypes.byref(n), True)
            self.pending = False
        _k32.CloseHandle(self.handle)
        _k32.CloseHandle(self.event)
        self.handle = None


def processes():
    """Lower-case executable names of the running processes."""
    TH32CS_SNAPPROCESS = 0x02
    snap = _k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE:
        return set()
    names = set()
    try:
        entry = PROCESSENTRY32W(dwSize=ctypes.sizeof(PROCESSENTRY32W))
        ok = _k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            names.add(entry.szExeFile.lower())
            ok = _k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        _k32.CloseHandle(snap)
    return names


def conflicting_programs():
    """VCFG.exe, which writes the mouse's memory too. VMON.exe only listens to the
    mouse and ETGMSrv.exe only installs the driver, so neither blocks writes."""
    return sorted({'vcfg.exe'} & processes())


CONFLICT_WHERE = ''
