"""SVG'den çizilen, motorla canlandırılan yüz.

Varlık `varliklar/svg/yuz.svg` ve onu `scripts/svg_yap.py` üretiyor.
Dosya parçalara ayrılmış — `govde`, `goz-<tür>-<taraf>` — ve Qt tek tek
eleman çizebiliyor. Bu ayrım olmasaydı durum başına ayrı bir dosya
tutmak ya da bütün yüzü tek karede çizmek gerekirdi; ikisi de gövdeyi
ezerken gözleri kaydırmayı imkânsız kılardı.

**Renkler yükleme anında değişiyor.** SVG'ye sabit renk gömülü olsaydı
tema değiştiğinde maskot yabancı kalırdı. Dosyadaki yer tutucular metin
olarak temanın renkleriyle değiştirilip öyle ayrıştırılıyor.

**Hareketin tamamı `motion` ile.** Kare başına sabit adım yok: gövdenin
ezilmesi, bakışın kayması, iniş tepkisi hep yay. Yolun ortasında hedef
değişirse hız korunuyor, ki akış sırasında hedef saniyede yirmi kez
değişiyor.

`AjanKafasi` ve `Bloub` ile aynı arayüz — `RunRing` hangisini
kullandığını bilmiyor.
"""

from __future__ import annotations

import random
from pathlib import Path

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget

from .fluent import Tokens
from .kafa import face_for
from .motion import Spring, clock

VARLIK = Path(__file__).resolve().parent.parent / "varliklar" / "svg" / "yuz.svg"

#: Dosyadaki yer tutucular. `scripts/svg_yap.py` ile aynı olmalı.
YER_GOVDE = "#E7BABD"
YER_OYUK = "#1C1C1C"

#: Durumdan göz türüne. Ağız yok: ifadeyi gözler ve gövde taşıyor.
DURUM_GOZ = {
    "bosta": "normal",
    "bakiyor": "genis",
    "tikliyor": "normal",
    "yaziyor": "kisik",
    "dusunuyor": "normal",
    "hata": "kizgin",
    "bitti": "gulen",
}

#: Gözbebeğinin kaçabileceği en uzak yer, 96'lık ızgarada.
#:
#: 7 ile bakış hiç okunmuyordu: halkanın içinde yüz ~32 piksele düşüyor
#: ve 7 birim orada 2.3 piksel ediyor. 13'te göz gerçekten kayıyor,
#: gövdenin dışına da taşmıyor.
GAZE = 13.0

#: Göz kırpma arası, saniye.
BLINK_MIN, BLINK_MAX = 2.4, 6.0
BLINK_SURE = 0.11

#: Ezilmenin sınırı. Sınırsızken hızlı akışta gövde yassılıyordu.
SQUASH_MAX = 0.16


def _renkli(t: Tokens, hata: bool = False) -> QByteArray:
    """SVG'yi temanın renkleriyle döndürür.

    Gövde vurgu renginin **kısılmış** hâli. Tam vurgu rengi olsaydı
    halkanın dilimleriyle aynı renk olurdu ve yüz, koşu kaydının önünü
    kapatırdı — ikisi de pembe, ikisi de üst üste. Kısılmış gövde arka
    plana bir adım yaklaşıyor ve dilimler önde kalıyor.
    """
    from .fluent import _blend

    govde = t.critical if hata else _blend(t.accent, 0.74, t.background)
    metin = VARLIK.read_text(encoding="utf-8")
    metin = metin.replace(YER_GOVDE, govde)
    metin = metin.replace(YER_OYUK, t.background)
    return QByteArray(metin.encode("utf-8"))


def varlik_var() -> bool:
    return VARLIK.is_file()


class SvgYuz(QWidget):
    """SVG parçalarından kurulan, yaylarla oynayan yüz."""

    #: Halkanın içinde kaplayacağı oran.
    #:
    #: 0.78'de yüz halkayı yiyordu: dilimler gövdenin arkasında kalıp
    #: koşu kaydı okunmaz oluyordu. SVG'nin kendi kenar boşluğu da var,
    #: yani gövde bu oranın %79'u kadar yer kaplıyor.
    fill = 0.62

    def __init__(self, t: Tokens, size: int = 52) -> None:
        super().__init__()
        self.t = t
        self.setFixedSize(size, size)
        # İki çizici: biri normal, biri hata rengi. Her durum
        # değişiminde SVG'yi yeniden ayrıştırmak kareyi düşürürdü.
        self._normal = QSvgRenderer(_renkli(t, False))
        self._hatali = QSvgRenderer(_renkli(t, True))
        self._vb = self._normal.viewBoxF()

        self._state = "bosta"
        self._goz = "normal"
        self._squash = Spring(0.0, stiffness=190.0, damping=13.0)
        self._gaze_x = Spring(0.0, stiffness=120.0)
        self._gaze_y = Spring(0.0, stiffness=120.0)
        self._blink = 0.0
        self._blink_at = random.uniform(BLINK_MIN, BLINK_MAX)
        self._gecen = 0.0
        self._live = False
        self._abone = False
        self.on_change = self.update

    # --- durum ------------------------------------------------------------

    def set_live(self, live: bool) -> None:
        if self._live == live:
            return
        self._live = live
        self._dinle(live)
        if not live:
            self._blink = 0.0
        self.on_change()

    def set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        self._goz = DURUM_GOZ.get(state, "normal")
        self.on_change()

    def set_tool(self, tool: str) -> None:
        self.set_state(face_for(tool))

    def look_at(self, x: float, y: float) -> None:
        self._gaze_x.to(max(-1.0, min(1.0, x)))
        self._gaze_y.to(max(-1.0, min(1.0, y)))
        self._dinle(True)

    def look_forward(self) -> None:
        self._gaze_x.to(0.0)
        self._gaze_y.to(0.0)

    def bump(self) -> None:
        """Bir şey geldi. Konum değişmiyor, gövde tepki veriyor."""
        self._squash.kick(1.6)
        self._dinle(True)

    # --- kare -------------------------------------------------------------

    def _dinle(self, ac: bool) -> None:
        if ac and not self._abone:
            clock().subscribe(self._tick)
            self._abone = True
        elif not ac and self._abone:
            clock().unsubscribe(self._tick)
            self._abone = False

    def hideEvent(self, event) -> None:
        self._dinle(False)
        super().hideEvent(event)

    def _tick(self, dt: float) -> None:
        self._gecen += dt
        self._squash.step(dt)
        self._squash.value = max(-SQUASH_MAX, min(SQUASH_MAX, self._squash.value))
        self._gaze_x.step(dt)
        self._gaze_y.step(dt)

        if self._live:
            if self._blink > 0.0:
                self._blink -= dt
            elif self._gecen >= self._blink_at:
                self._blink = BLINK_SURE
                self._blink_at = self._gecen + random.uniform(BLINK_MIN, BLINK_MAX)

        self.on_change()
        if (not self._live and self._squash.resting
                and self._gaze_x.resting and self._gaze_y.resting):
            self._dinle(False)

    # --- çizim ------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.paint(painter, self.width(), QPointF(0, 0))
        painter.end()

    def paint(self, painter: QPainter, size: float, origin: QPointF) -> None:
        cizici = self._hatali if self._state == "hata" else self._normal
        s = self._squash.value

        painter.save()
        painter.translate(origin)
        painter.scale(size / self._vb.width(), size / self._vb.height())

        # Gövde eziliyor: eni artarken boyu azalıyor, hacim korunuyor gibi.
        painter.save()
        painter.translate(self._vb.center())
        painter.scale(1.0 + s, 1.0 - s)
        painter.translate(-self._vb.center())
        cizici.render(painter, "govde", self._vb)
        painter.restore()

        self._gozleri_ciz(painter, cizici, s)
        painter.restore()

    def _gozleri_ciz(self, painter: QPainter, cizici: QSvgRenderer, s: float) -> None:
        tur = "kapali" if self._blink > 0.0 else self._goz
        dx = self._gaze_x.value * GAZE
        # Gövde ezilince gözler onunla gidiyor; sabit kalsalar yüzün
        # içinde kayıyormuş gibi görünürdü.
        dy = self._gaze_y.value * GAZE - s * self._vb.height() * 0.09

        for yon in ("sol", "sag"):
            ad = f"goz-{tur}-{yon}"
            if not cizici.elementExists(ad):
                ad = f"goz-normal-{yon}"
            kutu = cizici.boundsOnElement(ad)
            cizici.render(painter, ad, kutu.translated(dx, dy))
