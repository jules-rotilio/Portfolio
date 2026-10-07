from pynput import keyboard
import ctypes
from ctypes import wintypes
import threading
import time
from os import name as osname
from os import system
from random import randint
from subprocess import Popen
import pyperclip




user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

MAPVK_VK_TO_VSC = 0

VK_F = 0x46
VK_A = 0x41
VK_V = 0x56
VK_NUMPAD0 = 0x60
VK_NUMPAD1 = 0x61
VK_NUMPAD2 = 0x62
VK_NUMPAD3 = 0x63
VK_NUMPAD4 = 0x64
VK_NUMPAD5 = 0x65
VK_NUMPAD6 = 0x66
VK_NUMPAD7 = 0x67
VK_NUMPAD8 = 0x68
VK_NUMPAD9 = 0x69
VK_CONTROL = 0x11



# C struct definitions

wintypes.ULONG_PTR = wintypes.WPARAM


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.ULONG_PTR),
    )


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.ULONG_PTR),
    )

    def __init__(self, *args, **kwds):
        super(KEYBDINPUT, self).__init__(*args, **kwds)
        if not self.wScan and self.wVk:
            self.wScan = user32.MapVirtualKeyExW(self.wVk, MAPVK_VK_TO_VSC, 0)


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = (("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT))

    _anonymous_ = ("_input",)
    _fields_ = (("type", wintypes.DWORD), ("_input", _INPUT))


LPINPUT = ctypes.POINTER(INPUT)


def press_key(hexKeyCode):
    x = INPUT(type=INPUT_KEYBOARD, _input=INPUT._INPUT(ki=KEYBDINPUT(wVk=hexKeyCode)))
    user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))


def release_key(hexKeyCode):
    x = INPUT(
        type=INPUT_KEYBOARD,
        _input=INPUT._INPUT(ki=KEYBDINPUT(wVk=hexKeyCode, dwFlags=KEYEVENTF_KEYUP)),
    )
    user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))


# Track the state of the 'A' key
av_key_pressed = False

selected_key = VK_A

def toggle_a_key():
    global av_key_pressed
    if av_key_pressed:
        release_key(selected_key)  # Release 'A' key
    else:
        press_key(selected_key)  # Press 'A' key
    av_key_pressed = not av_key_pressed
    print_status()


toggle_f = False


def press_f():
    global toggle_f
    while toggle_f:
        press_key(VK_F)
        time.sleep(0.05)
        release_key(VK_F)
        time.sleep(0.05)


def print_status():
    global toggle_f
    global av_key_pressed
    global selected_key
    if selected_key == VK_A:
        status = "open mic" if av_key_pressed else "push to talk"
        key = "A"
    else:
        status = "open radio" if av_key_pressed else "push to radio"
        key = "V"
        
    f_status = "blind" if toggle_f else "normal"
    # Clear line
    clear_console()
    # Print the status
    print(
        " F key status: {}\n {} key status: {}".format(f_status, key, status),
        end="",
        flush=True,
    )
    print("\n\n")
    print("""1.\tgreetings\n2.\tyes\n3.\tnoo\n4.\tmadness\n5.\twe're doomed\n6.\tkilling scientists\n7.\tfreeman you fool\n8.\thiding spot\n9.\tdon't shoot""")


def clear_console():
    if osname == 'nt':
        system('cls')
    else:
        return

numpads = [
    VK_NUMPAD1,
    VK_NUMPAD2,
    VK_NUMPAD3,
    VK_NUMPAD4,
    VK_NUMPAD5,
    VK_NUMPAD6,
    VK_NUMPAD7,
    VK_NUMPAD8,
    VK_NUMPAD9,
]

def on_press(key):
    global toggle_f
    global selected_key
    global av_key_pressed
    try:
        if hasattr(key, "vk"):
            if key.vk == VK_NUMPAD0:
                toggle_f = not toggle_f
                if toggle_f:
                    threading.Thread(target=press_f).start()
                print_status()
            elif key.vk in numpads:
                if key.vk == VK_NUMPAD1:
                    if randint(0, 7) > 6:
                        Popen(["C:\\Program Files\\VideoLAN\\VLC\\vlc.exe", "--one-instance", "C:\\Users\\jules\\Music\\HL - scientists\\goodmorninggordon.wav"])
                    elif randint(0, 7) > 4:
                        Popen(["C:\\Program Files\\VideoLAN\\VLC\\vlc.exe", "--one-instance", "C:\\Users\\jules\\Music\\HL - scientists\\gooodmorninggordon.wav"])
                    elif randint(0, 7) > 2:
                        Popen(["C:\\Program Files\\VideoLAN\\VLC\\vlc.exe", "--one-instance", "C:\\Users\\jules\\Music\\HL - scientists\\greetings.wav"])
                    else:
                        Popen(["C:\\Program Files\\VideoLAN\\VLC\\vlc.exe", "--one-instance", "C:\\Users\\jules\\Music\\HL - scientists\\greetings2.wav"])
                elif key.vk == VK_NUMPAD2:
                    if randint(0, 9) > 4:
                        Popen(["C:\\Program Files\\VideoLAN\\VLC\\vlc.exe", "--one-instance", "C:\\Users\\jules\\Music\\HL - scientists\\yes.wav"])
                    else:
                        Popen(["C:\\Program Files\\VideoLAN\\VLC\\vlc.exe", "--one-instance", "C:\\Users\\jules\\Music\\HL - scientists\\yes2.wav"])
                elif key.vk == VK_NUMPAD3:
                    if randint(0, 9) > 4:
                        Popen(["C:\\Program Files\\VideoLAN\\VLC\\vlc.exe", "--one-instance", "C:\\Users\\jules\\Music\\HL - scientists\\noo.wav"])
                    else:
                        Popen(["C:\\Program Files\\VideoLAN\\VLC\\vlc.exe", "--one-instance", "C:\\Users\\jules\\Music\\HL - scientists\\no!.wav"])
                elif key.vk == VK_NUMPAD4:
                    Popen(["C:\\Program Files\\VideoLAN\\VLC\\vlc.exe", "--one-instance", "C:\\Users\\jules\\Music\\HL - scientists\\madness.wav"])
                elif key.vk == VK_NUMPAD5:
                    Popen(["C:\\Program Files\\VideoLAN\\VLC\\vlc.exe", "--one-instance", "C:\\Users\\jules\\Music\\HL - scientists\\ohmygodweredoomed.wav"])
                elif key.vk == VK_NUMPAD6:
                    Popen(["C:\\Program Files\\VideoLAN\\VLC\\vlc.exe", "--one-instance", "C:\\Users\\jules\\Music\\HL - scientists\\killingscientits.wav"])
                elif key.vk == VK_NUMPAD7:
                    Popen(["C:\\Program Files\\VideoLAN\\VLC\\vlc.exe", "--one-instance", "C:\\Users\\jules\\Music\\HL - scientists\\freemanyoufool.wav"])
                elif key.vk == VK_NUMPAD8:
                    Popen(["C:\\Program Files\\VideoLAN\\VLC\\vlc.exe", "--one-instance", "C:\\Users\\jules\\Music\\HL - scientists\\thisismyhidingspot.wav"])
                elif key.vk == VK_NUMPAD9:
                    Popen(["C:\\Program Files\\VideoLAN\\VLC\\vlc.exe", "--one-instance", "--input-slave", "C:\\Users\\jules\\Music\\HL - scientists\\dontshootimwiththescienceteam.wav"])
        elif key == keyboard.Key.scroll_lock:
            toggle_a_key()
        elif key == keyboard.Key.pause:
            exit(0)
        elif key == keyboard.Key.insert:
            if selected_key == VK_A:
                selected_key = VK_V
            else:
                selected_key = VK_A
            release_key(VK_A)
            release_key(VK_V)
            av_key_pressed = False
            print_status()
    except AttributeError:
        pass

print_status()

Popen(["C:\\Program Files\\VideoLAN\\VLC\\vlc.exe", "--one-instance"])

with keyboard.Listener(on_press=on_press) as listener:
    listener.join()
