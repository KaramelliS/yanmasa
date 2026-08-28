"""Ekran yakalama — monitör başına PNG.

Modele giden her kare tek bir monitör. Bu bir performans tercihi değil,
koordinat doğruluğu tercihi: 1920x1080 modelin 2576 px sınırının altında
kaldığı için kare hiç küçültülmüyor ve modelin verdiği piksel doğrudan
tıklanabilir bir piksel oluyor.

`zoom` aksiyonu aynı kaynaktan bölge kırpıyor — yeniden yakalama değil, çünkü
model kırpmayı istediğinde baktığı kare o an ekranda olan kare olmayabilir.
"""

from __future__ import annotations

import io
import threading
from dataclasses import dataclass

import mss
from PIL import Image

from .displays import Display, DisplayMap


@dataclass(frozen=True)
class Frame:
    """Yakalanmış bir kare ve hangi monitöre ait olduğu."""

    display_index: int
    width: int
    height: int
    image: Image.Image

    def to_png(self, optimize: bool = False) -> bytes:
        buffer = io.BytesIO()
        # optimize=True kareyi ~%15 küçültüyor ama 1080p'de ~120 ms sürüyor;
        # ajan döngüsünde bu her adıma binen bir gecikme, varsayılan kapalı.
        self.image.save(buffer, format="PNG", optimize=optimize, compress_level=1)
        return buffer.getvalue()

    def encode(self) -> tuple[bytes, str]:
        """Modele gidecek kare ve MIME türü.

        Ölçüm, 1920x1080 bir masaüstü karesi için:

            biçim                base64 boyut   kodlama
            PNG  compress=1       632-1843 KB    40-94 ms
            WebP kayıpsız m=0      315-795 KB    71-241 ms
            WebP kalite 90         264-308 KB    87-89 ms
            JPEG kalite 90         401-459 KB     7-11 ms

        (İki değer iki monitörden: biri yoğun görselli, diğeri düz arayüz.)

        **WebP kayıpsız, method=0** seçildi. PNG'nin 2-6 katı küçük ve
        kayıpsız — küçük yazı, ince çizgi bozulmuyor, ki ajanın baktığı şey
        tam olarak o. Yanlış okunan bir etiket yanlış tıklama demek ve
        bunun maliyeti birkaç yüz kilobayttan çok daha yüksek.

        `method` sıkıştırma çabası: 1 daha küçük dosya veriyor ama aynı
        karede 910 ms sürüyor, 0 ise 241 ms. Kazandırdığı yer, her adıma
        binen 700 ms'e değmiyor.
        """
        buffer = io.BytesIO()
        self.image.save(buffer, format="WEBP", lossless=True, method=0)
        return buffer.getvalue(), "image/webp"

    def crop(self, region: tuple[int, int, int, int]) -> Image.Image:
        """`zoom` için bölge kırpar. region = (x0, y0, x1, y1)."""
        x0, y0, x1, y1 = region
        if not (0 <= x0 < x1 <= self.width and 0 <= y0 < y1 <= self.height):
            raise ValueError(
                f"The region {region} is outside the {self.width}x{self.height} frame"
            )
        return self.image.crop(region)


class ScreenCapture:
    """mss oturumunu canlı tutan yakalayıcı.

    mss her `mss.mss()` çağrısında yeni bir cihaz bağlamı açıyor; ajan
    döngüsünde adım başına bir tane açmak birkaç yüz adımda tükenmeye
    yaklaşıyor. Tek oturum açıp yeniden kullanıyoruz.

    **Oturum thread başına.** mss Windows'ta cihaz bağlamını
    `threading.local()` içinde tutuyor; bir thread'de açılan oturumu başka
    bir thread'den kullanmak

        AttributeError: '_thread._local' object has no attribute 'srcdc'

    veriyor. Bu uygulamada yakalayıcı arayüz thread'inde kuruluyor ama ajan
    ayrı bir thread'de çalışıyor, yani her ekran görüntüsü bu hatayla
    düşüyordu — ajan bilgisayara hiç bakamıyordu. Her thread kendi
    oturumunu tembel açıyor, hepsi kapanışta toplanıyor.
    """

    def __init__(self, displays: DisplayMap) -> None:
        self._displays = displays
        self._local = threading.local()
        self._lock = threading.Lock()
        self._sessions: list = []

    @property
    def _sct(self):
        session = getattr(self._local, "sct", None)
        if session is None:
            session = mss.mss()
            self._local.sct = session
            with self._lock:
                self._sessions.append(session)
        return session

    def close(self) -> None:
        with self._lock:
            sessions, self._sessions = self._sessions, []
        for session in sessions:
            # Başka bir thread'in bağlamını kapatmak hata verebiliyor;
            # kapanışta bunun için uygulamayı düşürmenin anlamı yok.
            try:
                session.close()
            except Exception:
                pass
        self._local = threading.local()

    def __enter__(self) -> ScreenCapture:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def grab(self, display: Display | int) -> Frame:
        target = self._displays[display] if isinstance(display, int) else display
        raw = self._sct.grab(
            {
                "left": target.left,
                "top": target.top,
                "width": target.width,
                "height": target.height,
            }
        )
        image = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        return Frame(
            display_index=target.index,
            width=target.width,
            height=target.height,
            image=image,
        )
