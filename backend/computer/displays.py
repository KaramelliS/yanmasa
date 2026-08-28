"""Monitör envanteri ve koordinat çevirisi.

Modelin gördüğü her ekran görüntüsü tek bir monitöre ait ve sol üst köşesi
(0, 0). Windows'un imleç API'si ise sanal masaüstü koordinatlarını bekliyor —
ikinci monitör burada x=1920'den başlıyor. Bu modül iki uzayı birbirine çevirir.

Sanal masaüstünün tamamını (3840x1080) tek kare olarak göndermek bir seçenek
değil: uzun kenar modelin 2576 px sınırını aşıyor, küçültmek gerekirdi ve o
anda koordinatlar 1:1 olmaktan çıkardı. Monitör başına yakalayınca 1920x1080
sınırın altında kalıyor ve ölçek matematiği hiç doğmuyor.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

# Modelin görsel token tieri: uzun kenar en fazla bu kadar piksel olabilir.
MAX_LONG_EDGE_PX = 2576


@dataclass(frozen=True)
class Display:
    """Sanal masaüstü üzerinde bir monitör."""

    index: int
    left: int
    top: int
    width: int
    height: int
    primary: bool

    @property
    def long_edge(self) -> int:
        return max(self.width, self.height)

    @property
    def needs_downscale(self) -> bool:
        return self.long_edge > MAX_LONG_EDGE_PX

    def to_virtual(self, x: int, y: int) -> tuple[int, int]:
        """Ekran görüntüsü koordinatını sanal masaüstü koordinatına çevirir."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError(
                f"({x}, {y}) {self.width}x{self.height} boyutundaki "
                f"{self.index}. ekranın dışında"
            )
        return self.left + x, self.top + y

    def from_virtual(self, vx: int, vy: int) -> tuple[int, int]:
        """Sanal masaüstü koordinatını ekran görüntüsü koordinatına çevirir."""
        return vx - self.left, vy - self.top

    def contains_virtual(self, vx: int, vy: int) -> bool:
        return (
            self.left <= vx < self.left + self.width
            and self.top <= vy < self.top + self.height
        )


class DisplayMap:
    """Sıralı monitör listesi. Birincil ekran her zaman 0. indekste."""

    def __init__(self, displays: list[Display]) -> None:
        if not displays:
            raise ValueError("En az bir monitör gerekli")
        self._displays = displays

    def __len__(self) -> int:
        return len(self._displays)

    def __iter__(self):
        return iter(self._displays)

    def __getitem__(self, index: int) -> Display:
        try:
            return self._displays[index]
        except IndexError:
            raise IndexError(
                f"{index}. ekran yok — bu makinede {len(self._displays)} ekran var"
            ) from None

    def locate_virtual(self, vx: int, vy: int) -> Display | None:
        """Verilen sanal koordinatı içeren monitörü döndürür."""
        for display in self._displays:
            if display.contains_virtual(vx, vy):
                return display
        return None

    def locate_rect(self, left: int, top: int, right: int, bottom: int) -> Display:
        """Bir pencerenin **çoğunlukla** hangi monitörde olduğunu söyler.

        Sol üst köşeye bakmak yetmiyor: Windows'ta ekranı kaplayan bir
        pencere kenarlığı yüzünden birkaç piksel komşu monitöre taşıyor.
        Discord'un penceresi sol=1912 ile başlıyordu ve 1920'de başlayan
        ikinci ekranda olmasına rağmen birinci ekranda sayılıyordu — o
        yüzden ekran görüntüsü yanlış monitörden alınıyor ve ajan
        Discord'u hiç göremiyordu.

        Örtüşme alanı en büyük olan monitör kazanıyor.
        """
        en_iyi, en_buyuk = self._displays[0], -1
        for display in self._displays:
            genislik = min(right, display.left + display.width) - max(left, display.left)
            yukseklik = min(bottom, display.top + display.height) - max(top, display.top)
            alan = max(0, genislik) * max(0, yukseklik)
            if alan > en_buyuk:
                en_iyi, en_buyuk = display, alan
        return en_iyi

    def describe(self) -> str:
        """Sistem promptuna gömülecek insan okunur özet."""
        lines = []
        for d in self._displays:
            tag = " (primary)" if d.primary else ""
            lines.append(f"  {d.index}: {d.width}x{d.height}{tag}")
        return "\n".join(lines)


# --- Windows'tan gerçek monitörleri okuma -------------------------------------

_MONITORINFOF_PRIMARY = 0x1


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", ctypes.c_ulong),
    ]


def enumerate_displays() -> DisplayMap:
    """Bağlı monitörleri Windows'tan okur. Birincil ekran başa alınır."""
    user32 = ctypes.windll.user32
    found: list[tuple[_RECT, bool]] = []

    proc_type = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(_RECT), ctypes.c_double
    )

    def _callback(hmonitor, _hdc, _rect_ptr, _data):
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            found.append((info.rcMonitor, bool(info.dwFlags & _MONITORINFOF_PRIMARY)))
        return 1

    if not user32.EnumDisplayMonitors(None, None, proc_type(_callback), 0):
        raise OSError("EnumDisplayMonitors başarısız")

    # Birincil önce, sonra soldan sağa.
    found.sort(key=lambda item: (not item[1], item[0].left, item[0].top))

    return DisplayMap(
        [
            Display(
                index=i,
                left=rect.left,
                top=rect.top,
                width=rect.right - rect.left,
                height=rect.bottom - rect.top,
                primary=primary,
            )
            for i, (rect, primary) in enumerate(found)
        ]
    )


def virtual_screen_rect() -> tuple[int, int, int, int]:
    """Sanal masaüstünün (left, top, width, height) değeri.

    SendInput'un mutlak fare koordinatlarını normalize etmek için gerekli.
    """
    user32 = ctypes.windll.user32
    SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
    SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
    return (
        user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )


def set_dpi_awareness() -> None:
    """Süreci monitör başına DPI farkındalığına alır.

    Bu çağrı olmadan Windows koordinatları ölçekler ve yakaladığımız kare ile
    tıkladığımız nokta birbirini tutmaz. Süreç başlangıcında, pencere
    oluşturulmadan önce çağrılmalı.
    """
    DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(
            DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        )
    except (AttributeError, OSError):
        # Windows 8.1–10 1607 öncesi: eski API.
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
