"""Fare ve klavye — doğrudan Win32 SendInput.

pyautogui yerine ham SendInput kullanılıyor, iki nedenle: pyautogui Türkçe
karakterleri aktif klavye düzenine bağlı olarak yazıyor (İngilizce düzende
`ğüşıöç` düşüyor), ve fareyi sanal masaüstü yerine birincil ekrana göre
konumlandırıyor — ikinci monitörde yanlış yere tıklıyor.

Buradaki yaklaşım: fare için MOUSEEVENTF_VIRTUALDESK ile sanal masaüstüne
normalize mutlak koordinat, klavye için KEYEVENTF_UNICODE ile ham kod noktası.
İkincisi klavye düzeninden tamamen bağımsız.
"""

from __future__ import annotations

import ctypes
import time
from contextlib import contextmanager
from ctypes import wintypes

from .displays import virtual_screen_rect

ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

WHEEL_DELTA = 120

# Fare tuşu adı -> (basma bayrağı, bırakma bayrağı)
_BUTTONS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _send(*events: _INPUT) -> None:
    array = (_INPUT * len(events))(*events)
    sent = ctypes.windll.user32.SendInput(
        len(events), ctypes.byref(array), ctypes.sizeof(_INPUT)
    )
    if sent != len(events):
        raise OSError(
            f"SendInput sent {sent} of {len(events)} events "
            f"(GetLastError={ctypes.get_last_error()})"
        )


def normalize_absolute(vx: int, vy: int, rect: tuple[int, int, int, int]) -> tuple[int, int]:
    """Sanal masaüstü pikselini SendInput'un 0–65535 mutlak uzayına çevirir.

    Windows bu değeri `piksel = deger * genislik / 65536` ile geri çeviriyor,
    yani (genislik - 1) ile ölçekleyip yuvarlamak son sütuna/satıra da
    ulaşmayı garantiliyor.
    """
    left, top, width, height = rect
    if width <= 1 or height <= 1:
        raise ValueError(f"Invalid virtual desktop size: {width}x{height}")
    nx = round((vx - left) * 65535 / (width - 1))
    ny = round((vy - top) * 65535 / (height - 1))
    return max(0, min(65535, nx)), max(0, min(65535, ny))


def move_to(vx: int, vy: int) -> None:
    """İmleci sanal masaüstü koordinatına taşır."""
    nx, ny = normalize_absolute(vx, vy, virtual_screen_rect())
    _send(
        _INPUT(
            type=INPUT_MOUSE,
            mi=_MOUSEINPUT(
                dx=nx,
                dy=ny,
                mouseData=0,
                dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
                time=0,
                dwExtraInfo=0,
            ),
        )
    )


def cursor_position() -> tuple[int, int]:
    point = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def click(vx: int, vy: int, button: str = "left", count: int = 1) -> None:
    """Verilen noktaya tıklar. count=2 çift, count=3 üçlü tıklama."""
    if button not in _BUTTONS:
        raise ValueError(f"Unknown mouse button: {button}")
    down, up = _BUTTONS[button]
    move_to(vx, vy)
    for i in range(count):
        if i:
            # Windows'un çift tıklama eşiği varsayılan 500 ms; 60 ms güvenli.
            time.sleep(0.06)
        _send(
            _INPUT(type=INPUT_MOUSE, mi=_MOUSEINPUT(0, 0, 0, down, 0, 0)),
            _INPUT(type=INPUT_MOUSE, mi=_MOUSEINPUT(0, 0, 0, up, 0, 0)),
        )


def mouse_down(button: str = "left") -> None:
    _send(_INPUT(type=INPUT_MOUSE, mi=_MOUSEINPUT(0, 0, 0, _BUTTONS[button][0], 0, 0)))


def mouse_up(button: str = "left") -> None:
    _send(_INPUT(type=INPUT_MOUSE, mi=_MOUSEINPUT(0, 0, 0, _BUTTONS[button][1], 0, 0)))


def drag(from_xy: tuple[int, int], to_xy: tuple[int, int], steps: int = 24) -> None:
    """Basılı tutarak sürükler.

    Ara adımlar şart: tek sıçrayışta çoğu uygulama sürüklemeyi algılamıyor,
    çünkü WM_MOUSEMOVE akışı görmüyorlar.
    """
    move_to(*from_xy)
    mouse_down("left")
    try:
        x0, y0 = from_xy
        x1, y1 = to_xy
        for i in range(1, steps + 1):
            t = i / steps
            move_to(round(x0 + (x1 - x0) * t), round(y0 + (y1 - y0) * t))
            time.sleep(0.008)
    finally:
        mouse_up("left")


def scroll(direction: str, amount: int, at: tuple[int, int] | None = None) -> None:
    """Tekerlek kaydırma. amount, tık sayısı."""
    if at is not None:
        move_to(*at)
    axis = {"up": (MOUSEEVENTF_WHEEL, 1), "down": (MOUSEEVENTF_WHEEL, -1),
            "right": (MOUSEEVENTF_HWHEEL, 1), "left": (MOUSEEVENTF_HWHEEL, -1)}
    if direction not in axis:
        raise ValueError(f"Unknown scroll direction: {direction}")
    flag, sign = axis[direction]
    delta = ctypes.c_long(sign * WHEEL_DELTA * amount).value & 0xFFFFFFFF
    _send(_INPUT(type=INPUT_MOUSE, mi=_MOUSEINPUT(0, 0, delta, flag, 0, 0)))


# --- Klavye -------------------------------------------------------------------

# Modelin kullandığı X11 tarzı tuş adları -> Windows sanal tuş kodları.
VK_NAMES: dict[str, int] = {
    "backspace": 0x08, "tab": 0x09, "return": 0x0D, "enter": 0x0D,
    "shift": 0x10, "ctrl": 0x11, "control": 0x11, "alt": 0x12,
    "pause": 0x13, "caps_lock": 0x14, "escape": 0x1B, "esc": 0x1B,
    "space": 0x20, "page_up": 0x21, "page_down": 0x22,
    "end": 0x23, "home": 0x24,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "print": 0x2C, "insert": 0x2D, "delete": 0x2E,
    "super": 0x5B, "win": 0x5B, "menu": 0x5D,
    "num_lock": 0x90, "scroll_lock": 0x91,
}
VK_NAMES.update({f"f{i}": 0x6F + i for i in range(1, 25)})  # F1=0x70
VK_NAMES.update({str(d): 0x30 + d for d in range(10)})
VK_NAMES.update({chr(c): c for c in range(ord("A"), ord("Z") + 1)})
VK_NAMES.update({chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)})

# Genişletilmiş bayrak gereken tuşlar — yoksa numpad eşdeğerleri olarak gider.
_EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x5D, 0x90}


def _key_event(vk: int, up: bool) -> _INPUT:
    flags = KEYEVENTF_KEYUP if up else 0
    if vk in _EXTENDED:
        flags |= KEYEVENTF_EXTENDEDKEY
    return _INPUT(type=INPUT_KEYBOARD, ki=_KEYBDINPUT(vk, 0, flags, 0, 0))


def parse_combo(combo: str) -> list[int]:
    """`"ctrl+shift+s"` -> sanal tuş kodu listesi, değiştiriciler önce."""
    codes = []
    for part in combo.split("+"):
        name = part.strip().lower()
        if not name:
            raise ValueError(f"Empty key name: {combo!r}")
        if name not in VK_NAMES:
            raise ValueError(f"Unknown key: {part!r} (in {combo!r})")
        codes.append(VK_NAMES[name])
    return codes


def press(combo: str, repeat: int = 1) -> None:
    """Tuş ya da kombinasyon basar: `"Return"`, `"ctrl+s"`, `"alt+F4"`."""
    codes = parse_combo(combo)
    for _ in range(repeat):
        _send(*[_key_event(vk, up=False) for vk in codes])
        _send(*[_key_event(vk, up=True) for vk in reversed(codes)])
        time.sleep(0.01)


@contextmanager
def modifiers_held(combo: str | None):
    """Değiştirici tuşları basılı tutarken içerideki eylemi çalıştırır.

    Model tıklama ve kaydırma aksiyonlarında `text` alanıyla değiştirici
    gönderebiliyor: `left_click` + `"shift"` = shift'li tıklama. Bırakma
    `finally` içinde, çünkü ortada bir hata olursa ctrl basılı kalırsa
    kullanıcının klavyesi kullanılamaz hale gelir.
    """
    if not combo:
        yield
        return

    codes = parse_combo(combo)
    _send(*[_key_event(vk, up=False) for vk in codes])
    try:
        yield
    finally:
        _send(*[_key_event(vk, up=True) for vk in reversed(codes)])


def hold(combo: str, duration: float) -> None:
    """Tuşu belirtilen saniye boyunca basılı tutar."""
    codes = parse_combo(combo)
    _send(*[_key_event(vk, up=False) for vk in codes])
    try:
        time.sleep(duration)
    finally:
        _send(*[_key_event(vk, up=True) for vk in reversed(codes)])


#: Karakterler arası bekleme. Ölçülerek bulundu — aşağıdaki nota bakın.
TYPE_DELAY = 0.012


def type_text(text: str, delay: float = TYPE_DELAY) -> None:
    """Metni harfi harfine yazar, klavye düzeninden bağımsız.

    KEYEVENTF_UNICODE her karakteri ham kod noktası olarak gönderir, yani
    `ğüşıöç` ve `İ` Türkçe Q düzeni kurulu olmasa da doğru düşer. BMP dışı
    karakterler (emoji) UTF-16 vekil çiftine ayrılıyor.

    **Karakter başına bir SendInput çağrısı, arada bekleme ile.** İlk sürüm
    24 karakteri tek çağrıda toplu gönderiyordu; ölçümde 55 karakterlik bir
    metin Notepad'e 39 karakter olarak düştü — olaylar hedefin mesaj
    kuyruğunun tükettiğinden hızlı geliyordu ve arada kalanlar bozuluyordu.
    Kısa dizelerde sorun görünmüyordu, bu yüzden ancak tam metinle test
    edilince ortaya çıktı. Toplu gönderim bu iş için yanlış optimizasyon.

    Uzun metinlerde bu yavaş (~12 ms/karakter). Panoya yazıp Ctrl+V ile
    yapıştırmak çok daha hızlı ama kullanıcının panosunu eziyor ve her alanda
    çalışmıyor; o yol Faz 2'de ayrı bir fonksiyon olarak, yalnızca uzun
    metinler için eklenecek.
    """
    raw = text.encode("utf-16-le")
    units = [int.from_bytes(raw[i:i + 2], "little") for i in range(0, len(raw), 2)]

    for unit in units:
        _send(
            _INPUT(type=INPUT_KEYBOARD, ki=_KEYBDINPUT(0, unit, KEYEVENTF_UNICODE, 0, 0)),
            _INPUT(
                type=INPUT_KEYBOARD,
                ki=_KEYBDINPUT(0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0),
            ),
        )
        time.sleep(delay)
