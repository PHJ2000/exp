from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from dataclasses import dataclass


APP_PID = os.getpid()
TERMINALS = {"windowsterminal.exe", "wezterm-gui.exe", "conhost.exe", "powershell.exe", "pwsh.exe", "cmd.exe", "mintty.exe", "alacritty.exe", "rio.exe", "code.exe", "cursor.exe"}
EXCLUDED_TARGET_PROCS = {"autohotkey64.exe", "shellexperiencehost.exe", "dwm.exe"}
EXCLUDED_TARGET_CLASSES = {"TkTopLevel", "Shell_TrayWnd", "Progman", "WorkerW"}
INPUT_FOCUS_CLASSES = {"Edit", "RichEdit20A", "RichEdit20W", "RichEdit50W", "Scintilla", "Chrome_RenderWidgetHostHWND", "Internet Explorer_Server"}
WEB_INPUT_PROCS = {"chrome.exe", "msedge.exe", "brave.exe", "whale.exe", "firefox.exe", "kakaotalk.exe", "discord.exe", "slack.exe", "telegram.exe"}
BROWSER_FALLBACK_PROCS = {"chrome.exe", "msedge.exe", "brave.exe", "whale.exe", "firefox.exe", "discord.exe", "slack.exe", "telegram.exe"}
BROWSER_WINDOW_CLASSES = {"Chrome_WidgetWin_1", "MozillaWindowClass"}
WINDOWS_SEARCH_PROCS = {"searchhost.exe", "startmenuexperiencehost.exe", "searchapp.exe"}
SYSTEM_INPUT_PROCS = {"systemsettings.exe", "applicationframehost.exe", "explorer.exe"}
SYSTEM_INPUT_CLASSES = {"ApplicationFrameWindow", "Windows.UI.Core.CoreWindow", "CabinetWClass", "#32770", "XamlExplorerHostIslandWindow"}
SINGLE_INSTANCE_MUTEX_NAME = "Local\\CodexDictationSingleton"
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
CLIPBOARD_OPEN_RETRIES = 20
CLIPBOARD_OPEN_DELAY = 0.025

_single_instance_handle = None


@dataclass
class WinInfo:
    hwnd: int
    pid: int
    title: str
    cls: str
    proc: str


@dataclass
class FocusInfo:
    focus_hwnd: int
    focus_cls: str
    caret_hwnd: int
    caret_cls: str
    caret_visible: bool


def _configure_clipboard_api():
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL


_configure_clipboard_api()


def _open_clipboard_with_retry(user32) -> bool:
    for _ in range(CLIPBOARD_OPEN_RETRIES):
        if user32.OpenClipboard(None):
            return True
        time.sleep(CLIPBOARD_OPEN_DELAY)
    return False


def get_clipboard_text() -> str:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if not _open_clipboard_with_retry(user32):
        return ""
    handle = None
    locked = None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        locked = kernel32.GlobalLock(handle)
        if not locked:
            return ""
        return ctypes.wstring_at(locked)
    except Exception:
        return ""
    finally:
        if locked:
            kernel32.GlobalUnlock(handle)
        user32.CloseClipboard()


def set_clipboard_text(text: str) -> bool:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    data = (text or "") + "\0"
    buf_size = len(data) * ctypes.sizeof(ctypes.c_wchar)
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, buf_size)
    if not handle:
        return False
    locked = None
    try:
        locked = kernel32.GlobalLock(handle)
        if not locked:
            return False
        ctypes.memmove(locked, ctypes.create_unicode_buffer(data), buf_size)
        kernel32.GlobalUnlock(handle)
        locked = None
        if not _open_clipboard_with_retry(user32):
            return False
        try:
            user32.EmptyClipboard()
            if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                return False
            handle = None
            return True
        finally:
            user32.CloseClipboard()
    finally:
        if locked:
            kernel32.GlobalUnlock(handle)
        if handle:
            kernel32.GlobalFree(handle)


def acquire_single_instance() -> bool:
    global _single_instance_handle
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetLastError(0)
        handle = kernel32.CreateMutexW(None, False, SINGLE_INSTANCE_MUTEX_NAME)
        if not handle:
            return True
        if kernel32.GetLastError() == 183:
            kernel32.CloseHandle(handle)
            return False
        _single_instance_handle = handle
        return True
    except Exception:
        return True


def safe_proc(pid: int) -> str:
    try:
        import psutil

        return psutil.Process(pid).name().lower()
    except Exception:
        return ""


def has_codex(pid: int) -> bool:
    try:
        import psutil

        process = psutil.Process(pid)
        for child in [process, *process.children(recursive=True)]:
            if "codex" in " ".join([child.name(), *child.cmdline()]).lower():
                return True
    except Exception:
        return False
    return False


def fg_info() -> WinInfo | None:
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    length = user32.GetWindowTextLengthW(hwnd)
    title = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, title, length + 1)
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return WinInfo(int(hwnd), int(pid.value), title.value, cls.value, safe_proc(int(pid.value)))


def hwnd_class(hwnd: int) -> str:
    if not hwnd:
        return ""
    user32 = ctypes.windll.user32
    cls = ctypes.create_unicode_buffer(256)
    try:
        user32.GetClassNameW(hwnd, cls, 256)
        return cls.value
    except Exception:
        return ""


def fmt_info(info: WinInfo | None) -> str:
    if not info:
        return "No active window"
    return f"{info.proc or 'unknown'} | {(info.title or '(no title)')} | {info.cls or 'unknown'} | hwnd={info.hwnd}"


def is_terminal(info: WinInfo | None) -> bool:
    return bool(info and (info.proc in TERMINALS or info.cls in {"CASCADIA_HOSTING_WINDOW_CLASS", "ConsoleWindowClass"} or any(token in (info.title or "").lower() for token in ["terminal", "powershell", "pwsh", "cmd"])))


def is_codex_terminal(info: WinInfo | None) -> bool:
    return bool(info and is_terminal(info) and ("codex" in info.title.lower() or has_codex(info.pid)))


def gui_focus_info(info: WinInfo | None) -> FocusInfo | None:
    if not info:
        return None

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class GUITHREADINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("flags", ctypes.c_ulong),
            ("hwndActive", ctypes.c_void_p),
            ("hwndFocus", ctypes.c_void_p),
            ("hwndCapture", ctypes.c_void_p),
            ("hwndMenuOwner", ctypes.c_void_p),
            ("hwndMoveSize", ctypes.c_void_p),
            ("hwndCaret", ctypes.c_void_p),
            ("rcCaret", RECT),
        ]

    user32 = ctypes.windll.user32
    try:
        thread_id = user32.GetWindowThreadProcessId(info.hwnd, None)
        gui = GUITHREADINFO()
        gui.cbSize = ctypes.sizeof(GUITHREADINFO)
        if not user32.GetGUIThreadInfo(thread_id, ctypes.byref(gui)):
            return None
        focus_hwnd = int(gui.hwndFocus or 0)
        caret_hwnd = int(gui.hwndCaret or 0)
        caret_rect = gui.rcCaret
        caret_visible = any(int(value) != 0 for value in (caret_rect.left, caret_rect.top, caret_rect.right, caret_rect.bottom))
        return FocusInfo(focus_hwnd, hwnd_class(focus_hwnd), caret_hwnd, hwnd_class(caret_hwnd), caret_visible)
    except Exception:
        return None


def is_general_input_target(info: WinInfo | None) -> bool:
    if not info:
        return False
    if info.pid == APP_PID or info.proc in EXCLUDED_TARGET_PROCS or info.cls in EXCLUDED_TARGET_CLASSES:
        return False
    if info.proc not in WINDOWS_SEARCH_PROCS and not (info.title or "").strip() and not is_terminal(info):
        return False
    focus = gui_focus_info(info)
    if not focus:
        return False
    if info.proc in WINDOWS_SEARCH_PROCS:
        return True
    if focus.caret_hwnd or focus.caret_visible:
        return True
    if focus.focus_cls in INPUT_FOCUS_CLASSES or focus.caret_cls in INPUT_FOCUS_CLASSES:
        return True
    if info.proc in SYSTEM_INPUT_PROCS and info.cls in SYSTEM_INPUT_CLASSES:
        return True
    if info.proc in WEB_INPUT_PROCS and focus.focus_hwnd and focus.focus_hwnd != info.hwnd:
        return True
    if info.proc in BROWSER_FALLBACK_PROCS and info.cls in BROWSER_WINDOW_CLASSES:
        return True
    return False


def has_precise_text_focus(info: WinInfo | None) -> bool:
    if not info:
        return False
    focus = gui_focus_info(info)
    if not focus:
        return False
    if focus.caret_hwnd or focus.caret_visible:
        return True
    return focus.focus_cls in INPUT_FOCUS_CLASSES or focus.caret_cls in INPUT_FOCUS_CLASSES


def is_target_window(info: WinInfo | None) -> bool:
    return bool(info and (is_terminal(info) or is_general_input_target(info)))


def list_terminal_windows() -> list[WinInfo]:
    user32 = ctypes.windll.user32
    windows = []
    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def _cb(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            info = WinInfo(int(hwnd), int(pid.value), title.value, cls.value, safe_proc(int(pid.value)))
            if is_terminal(info):
                windows.append(info)
        except Exception:
            pass
        return True

    user32.EnumWindows(enum_proc(_cb), 0)
    return windows


def focus_window(hwnd: int) -> bool:
    user32 = ctypes.windll.user32
    if not hwnd:
        return False
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def focus_best_terminal() -> bool:
    windows = list_terminal_windows()
    if not windows:
        return False
    return focus_window(windows[0].hwnd)


def control_window_state(info: WinInfo | None, action: str) -> bool:
    if not info:
        return False
    if info.pid == APP_PID or info.proc in EXCLUDED_TARGET_PROCS or info.cls in EXCLUDED_TARGET_CLASSES:
        return False
    user32 = ctypes.windll.user32
    show_map = {"maximize": 3, "minimize": 6, "restore": 9}
    cmd = show_map.get(action)
    if cmd is None:
        return False
    try:
        user32.ShowWindow(info.hwnd, cmd)
        if action != "minimize":
            user32.SetForegroundWindow(info.hwnd)
        return True
    except Exception:
        return False


def send_media_virtual_key(vk_code: int) -> bool:
    user32 = ctypes.windll.user32
    keyeventf_keyup = 0x0002
    try:
        user32.keybd_event(vk_code, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(vk_code, 0, keyeventf_keyup, 0)
        return True
    except Exception:
        return False
