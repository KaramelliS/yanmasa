"""SVG pozlarından şekil değiştiren, motorla canlandırılan yüz.

Varlıklar `varliklar/svg/` altında ve `scripts/svg_yap.py` üretiyor:
her poz bir `poz-*.svg`, gözler ayrı bir `gozler.svg`.

**Gövde şekil değiştiriyor.** Tek bir şekli ezip germek sadeydi ve öyle
göründü. Burada gövde pozlar arasında geçiyor: bekleme yavaşça nefes
alıyor, iş sıkışıp geniyor, ofis dikleşip belgeye benziyor, düşünme
bulutlaşıyor. Bütün pozlar aynı nokta sayısında üretildiği için geçiş
noktaları karıştırmaktan ibaret — farklı sayıda olsalardı ara karelerde
şekil bozulurdu.

**Gözler ayrı.** Gövde şekil değiştirirken gözler kendi başına kayıyor.
Çalışırken bakış gerçek koordinata gidiyor: ajan ekranın sağ altına
tıklayacaksa gözler oraya bakıyor. Boştayken yavaşça sağa sola
geziniyor — buradaki tek uydurma hareket bu ve anlamı var: hiçbir şey
olmuyor, bekliyorum.

Hareketin tamamı `motion` ile: kare başına sabit adım yok.
"""

from __future__ import annotations

import random
import re
from pathlib import Path

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget

from .fluent import Tokens
from .motion import Spring, clock, ease_in_out

SVG_DIZIN = Path(__file__).resolve().parent.parent / "varliklar" / "svg"

#: Dosyadaki yer tutucular. `scripts/svg_yap.py` ile aynı olmalı.
YER_GOVDE = "#E7BABD"
YER_OYUK = "#1C1C1C"

#: Animasyonlar: (poz, poz, tek geçişin süresi). Gövde ikisi arasında
#: gidip geliyor ve süre karakteri belirliyor — bekleme ağır, iş çabuk.
ANIMASYON = {
    "bosta": ("bosta", "bosta-b", 2.1),
    "is": ("is", "is-b", 0.42),
    "ofis": ("ofis", "ofis-b", 1.0),
    "dusun": ("dusun", "dusun-b", 0.62),
    "hata": ("hata", "hata", 1.0),
    "bitti": ("bitti", "bitti", 1.0),
}

#: Araçtan animasyona. Ofis işleri kendi animasyonunu hak ediyor: belge
#: üstünde çalışmak ekranda tıklamaya benzemiyor ve aynı hareketi
#: göstermek ikisini aynı şey sanmana yol açardı.
ARAC_ANIMASYON = {
    "office_open": "ofis", "office_read": "ofis", "office_edit": "ofis",
    "office_write": "ofis", "office_save": "ofis", "office_close": "ofis",
    "office_history": "ofis",
    "wait": "dusun", "read_ui_tree": "dusun",
}

#: Araçtan göz türüne.
ARAC_GOZ = {
    "screenshot": "genis", "zoom": "genis", "switch_display": "genis",
    "read_ui_tree": "genis", "cursor_position": "genis",
    "type": "kisik", "key": "kisik", "hold_key": "kisik",
    "write_file": "kisik", "write_files": "kisik", "edit_file": "kisik",
    "office_edit": "kisik", "office_write": "kisik", "skill_write": "kisik",
}

DURUM_GOZ = {"hata": "kizgin", "bitti": "gulen", "bakiyor": "genis",
             "yaziyor": "kisik"}

#: Durumdan animasyona. `RunRing.begin()` "dusunuyor" diyor ve bu tablo
#: olmasaydı tanınmayıp beklemeye düşerdi.
DURUM_ANIMASYON = {
    "bosta": "bosta", "dusunuyor": "dusun", "bakiyor": "bosta",
    "tikliyor": "is", "yaziyor": "is", "hata": "hata", "bitti": "bitti",
}

#: Gözün kaçabileceği en uzak yer, 96'lık ızgarada. 7'de bakış hiç
#: okunmuyordu: yüz halkanın içinde ~32 piksele düşüyor ve 7 birim orada
#: 2.3 piksel ediyor.
GAZE = 13.0

#: Boştayken bakışın gezinme aralığı, saniye.
GEZINME_MIN, GEZINME_MAX = 1.8, 4.2

#: Göz kırpma.
BLINK_MIN, BLINK_MAX, BLINK_SURE = 2.4, 6.0, 0.11

#: Ezilmenin sınırı. Sınırsızken hızlı akışta gövde yassılıyordu.
SQUASH_MAX = 0.16

_SAYI = re.compile(r"-?\d+\.?\d*")


def varlik_var() -> bool:
    return ((SVG_DIZIN / "gozler.svg").is_file()
            and (SVG_DIZIN / "poz-bosta.svg").is_file())


def _poz_noktalari(ad: str) -> list[QPointF]:
    """Poz dosyasındaki yolu nokta listesine çevirir.

    Yol `M x y L x y ... Z` biçiminde ve üreten betik onu hep böyle
    yazıyor; genel bir SVG ayrıştırıcıya gerek yok.
    """
    yol = SVG_DIZIN / f"poz-{ad}.svg"
    if not yol.is_file():
        return []
    eslesme = re.search(r'id="govde"\s+d="([^"]+)"', yol.read_text(encoding="utf-8"))
    if not eslesme:
        return []
    s = [float(x) for x in _SAYI.findall(eslesme.group(1))]
    return [QPointF(s[i], s[i + 1]) for i in range(0, len(s) - 1, 2)]


def _gozler_renkli(t: Tokens) -> QByteArray:
    metin = (SVG_DIZIN / "gozler.svg").read_text(encoding="utf-8")
    return QByteArray(metin.replace(YER_OYUK, t.background).encode("utf-8"))


class SvgYuz(QWidget):
    """Pozlar arası geçen gövde, kendi başına bakan gözler."""

    #: Halkanın içinde kaplayacağı oran. 0.78'de yüz halkayı yiyor ve
    #: koşu kaydı okunmaz oluyordu.
    fill = 0.66

    def __init__(self, t: Tokens, size: int = 52) -> None:
        super().__init__()
        self.t = t
        self.setFixedSize(size, size)
        self._pozlar = {
            ad: _poz_noktalari(ad)
            for ad in {p for a in ANIMASYON.values() for p in a[:2]}
        }
        self._gozler = QSvgRenderer(_gozler_renkli(t))

        self._anim = "bosta"
        self._faz = 0.0
        self._yon = 1.0
        self._goz = "normal"
        self._state = "bosta"
        self._hata = False

        self._squash = Spring(0.0, stiffness=190.0, damping=13.0)
        self._gaze_x = Spring(0.0, stiffness=110.0)
        self._gaze_y = Spring(0.0, stiffness=110.0)
        self._gezinme_at = random.uniform(GEZINME_MIN, GEZINME_MAX)
        self._blink = 0.0
        self._blink_at = random.uniform(BLINK_MIN, BLINK_MAX)
        self._gecen = 0.0
        self._takip = False        # bakış gerçek koordinatta mı
        self._live = False
        self._abone = False
        self.on_change = self.update

    # --- durum ------------------------------------------------------------

    def set_live(self, live: bool) -> None:
        self._live = live
        if not live:
            self._blink = 0.0
        self.on_change()

    def set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        self._hata = state == "hata"
        self._goz = DURUM_GOZ.get(state, "normal")
        self._anim = DURUM_ANIMASYON.get(state, "bosta")
        self.on_change()

    def set_tool(self, tool: str) -> None:
        """Araç yüzü belirliyor: animasyon ve göz ayrı ayrı seçiliyor."""
        self._hata = False
        self._state = "calisiyor"
        self._anim = ARAC_ANIMASYON.get(tool, "is")
        self._goz = ARAC_GOZ.get(tool, "normal")
        self.on_change()

    def look_at(self, x: float, y: float) -> None:
        self._takip = True
        self._gaze_x.to(max(-1.0, min(1.0, x)))
        self._gaze_y.to(max(-1.0, min(1.0, y)))

    def look_forward(self) -> None:
        self._takip = False
        self._gaze_x.to(0.0)
        self._gaze_y.to(0.0)

    def bump(self) -> None:
        self._squash.kick(1.6)

    # --- kare -------------------------------------------------------------

    def _dinle(self, ac: bool) -> None:
        if ac and not self._abone:
            clock().subscribe(self._tick)
            self._abone = True
        elif not ac and self._abone:
            clock().unsubscribe(self._tick)
            self._abone = False

    def hideEvent(self, event) -> None:
        # Görünmeyeni canlandırmak boşa iş.
        self._dinle(False)
        super().hideEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._dinle(True)

    def _tick(self, dt: float) -> None:
        self.step(dt)
        self.on_change()

    def step(self, dt: float) -> None:
        """Bir kare ilerlet.

        Dışarıya açık, çünkü kafa `RunRing`in içinde **gizli bir çocuk
        widget** olarak duruyor: kendi `showEvent`i hiç gelmiyor ve
        kendi başına saate abone olamıyor. Halka onu kendi karesinden
        sürüyor. Bunu fark etmeden bıraksaydım yüz hiç kıpırdamazdı.
        """
        self._gecen += dt
        self._squash.step(dt)
        self._squash.value = max(-SQUASH_MAX, min(SQUASH_MAX, self._squash.value))
        self._gaze_x.step(dt)
        self._gaze_y.step(dt)

        # Gövde iki poz arasında gidip geliyor.
        self._faz += self._yon * dt / ANIMASYON[self._anim][2]
        if self._faz >= 1.0:
            self._faz, self._yon = 1.0, -1.0
        elif self._faz <= 0.0:
            self._faz, self._yon = 0.0, 1.0

        if self._live:
            self._kirp(dt)
        elif not self._takip:
            self._gezin()

    def _kirp(self, dt: float) -> None:
        if self._blink > 0.0:
            self._blink -= dt
        elif self._gecen >= self._blink_at:
            self._blink = BLINK_SURE
            self._blink_at = self._gecen + random.uniform(BLINK_MIN, BLINK_MAX)

    def _gezin(self) -> None:
        """Boştayken bakış yavaşça sağa sola geziniyor.

        Buradaki tek uydurma hareket bu ve anlamı var: hiçbir şey
        olmuyor, bekliyorum. Çalışırken devreye girmiyor — orada bakış
        gerçek koordinata ait.
        """
        if self._gecen < self._gezinme_at:
            return
        self._gezinme_at = self._gecen + random.uniform(GEZINME_MIN, GEZINME_MAX)
        self._gaze_x.to(random.uniform(-0.85, 0.85))
        self._gaze_y.to(random.uniform(-0.35, 0.35))

    # --- çizim ------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.paint(painter, self.width(), QPointF(0, 0))
        painter.end()

    def paint(self, painter: QPainter, size: float, origin: QPointF) -> None:
        s = self._squash.value
        painter.save()
        painter.translate(origin)
        painter.scale(size / 96.0, size / 96.0)

        painter.save()
        painter.translate(48.0, 48.0)
        painter.scale(1.0 + s, 1.0 - s)
        painter.translate(-48.0, -48.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._govde_rengi()))
        painter.drawPath(self._govde_yolu())
        painter.restore()

        self._gozleri_ciz(painter, s)
        painter.restore()

    def _govde_rengi(self) -> str:
        """Gövde vurgu renginin kısılmış hâli.

        Tam vurgu olsaydı halkanın dilimleriyle aynı renk olurdu ve yüz
        koşu kaydının önünü kapatırdı — çizip baktım, iki pembe üst üste
        biniyordu.
        """
        from .fluent import _blend

        if self._hata:
            return self.t.critical
        return _blend(self.t.accent, 0.74, self.t.background)

    def taban_yolu(self) -> QPainterPath:
        """Nötr siluet — eller bunun küçültülmüş hâli.

        El için ayrı bir daire çizmek maskotu birbirine yapıştırılmış
        parçalar gibi gösterirdi; el de aynı yaratıktan.
        """
        return self._yoldan(self._pozlar.get("bosta") or [])

    def _yoldan(self, noktalar) -> QPainterPath:
        yol = QPainterPath()
        for i, p in enumerate(noktalar):
            yol.moveTo(p) if i == 0 else yol.lineTo(p)
        if noktalar:
            yol.closeSubpath()
        return yol

    def _govde_yolu(self) -> QPainterPath:
        a, b, _ = ANIMASYON[self._anim]
        ilk, ikinci = self._pozlar.get(a), self._pozlar.get(b)
        yol = QPainterPath()
        if not ilk:
            return yol
        k = ease_in_out(self._faz)
        for i, p in enumerate(ilk):
            q = ikinci[i] if ikinci and i < len(ikinci) else p
            nokta = QPointF(p.x() + (q.x() - p.x()) * k,
                            p.y() + (q.y() - p.y()) * k)
            yol.moveTo(nokta) if i == 0 else yol.lineTo(nokta)
        yol.closeSubpath()
        return yol

    def _gozleri_ciz(self, painter: QPainter, s: float) -> None:
        tur = "kapali" if self._blink > 0.0 else self._goz
        dx = self._gaze_x.value * GAZE
        # Gövde ezilince gözler onunla gidiyor; sabit kalsalar yüzün
        # içinde kayıyormuş gibi görünürdü.
        dy = self._gaze_y.value * GAZE - s * 8.6
        for yon in ("sol", "sag"):
            ad = f"goz-{tur}-{yon}"
            if not self._gozler.elementExists(ad):
                ad = f"goz-normal-{yon}"
            kutu: QRectF = self._gozler.boundsOnElement(ad)
            self._gozler.render(painter, ad, kutu.translated(dx, dy))
