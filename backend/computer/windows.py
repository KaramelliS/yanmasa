"""Ön plandaki pencere — girdi göndermeden önceki emniyet kilidi.

Bu modül Faz 1 doğrulaması sırasında bir kazadan doğdu: Notepad açılması
beklenirken öne gelmedi ve yazılan metin o an odakta olan başka bir pencereye,
bir sohbet kutusuna gitti; ardından gelen Return mesajı gönderdi.

Ders: `type_text` ve `press` hedefsizdir — nereye gittiklerini bilmezler,
odakta ne varsa oraya yazarlar. Ajan döngüsünde her klavye eylemi önce
`assert_foreground` ile hangi pencereye yazdığını doğrulamalı. Ekran
görüntüsündeki pencere ile odaktaki pencere aynı olmayabilir; arada geçen
saniyede kullanıcı sekme değiştirmiş olabilir.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes


class FocusError(RuntimeError):
    """Beklenen pencere odakta değil — girdi gönderilmedi."""


def foreground_title() -> str:
    """Ön plandaki pencerenin başlığı. Pencere yoksa boş dize."""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def foreground_process() -> str:
    """Ön plandaki pencerenin çalıştırılabilir dosya adı, örn. `notepad.exe`."""
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(260)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(size)
        ):
            return ""
        return buffer.value.rsplit("\\", 1)[-1]
    finally:
        kernel32.CloseHandle(handle)


def wait_for_foreground(
    process: str | None = None,
    title_contains: str | None = None,
    timeout: float = 5.0,
    poll: float = 0.1,
) -> bool:
    """Beklenen pencere öne gelene kadar bekler. Geldiyse True."""
    if process is None and title_contains is None:
        raise ValueError("process ya da title_contains verilmeli")

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if matches_foreground(process, title_contains):
            return True
        time.sleep(poll)
    return False


def matches_foreground(process: str | None, title_contains: str | None) -> bool:
    if process is not None and foreground_process().lower() != process.lower():
        return False
    if title_contains is not None and title_contains.lower() not in foreground_title().lower():
        return False
    return True


def assert_foreground(
    process: str | None = None, title_contains: str | None = None
) -> None:
    """Beklenen pencere odakta değilse hata fırlatır — klavye eylemi öncesi kilit."""
    if not matches_foreground(process, title_contains):
        expected = process or f"başlığında {title_contains!r} geçen pencere"
        raise FocusError(
            f"{expected} bekleniyordu ama odakta "
            f"{foreground_process() or '<yok>'} / {foreground_title()!r} var. "
            f"Girdi gönderilmedi."
        )
