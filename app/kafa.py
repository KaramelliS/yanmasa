"""Ajanın yüzü.

Karikatür bir kafa: dolu bir squircle gövde ve iki eğik yarık göz. Tam
daire değil — uygulamanın bütün yüzeyleri yuvarlatılmış dikdörtgen ve
kafa da onlardan biri gibi durmalı. Başka bir yerden alınmış bir maskot
burada yabancı dururdu.

**Gözler gerçekten baktığı yere bakıyor.** Ajan ekranın sağ altına
tıklayacaksa gözbebekleri oraya kayıyor; koordinat zaten elimizde. Bu
projedeki bütün hareket aynı kuralda: `MicDot`un halkası gerçek ses
şiddetini, `RunRing`in dilimleri gerçek adımları gösteriyor. Rastgele
kıpırdayan bir maskot bu kuralı bozardı ve süs olurdu.

Yüz ifadesi de uydurma değil, ajanın o an ne yaptığı:

- **bakiyor** — yarıklar açılıyor, gözler irileşiyor
- **tikliyor** — yarıklar hedefe kayıyor
- **yaziyor** — yarıklar kısılıyor, dikkat toplanıyor
- **dusunuyor** — bakış yukarı sola
- **hata** — yarıklar içeri dönüyor, gövde kırmızı
- **bitti** — yarıklar yukarı kıvrılıyor

Ağız yok, kontur yok: dolu bir gövde ve iki eğik yarık. İfadeyi taşıyan
tek şey gözler, ve gövde onlarla birlikte eziliyor.

Göz kırpma tek rastgele şey ve sebebi var: hiç kırpmayan bir yüz ölü
görünüyor. Kırpma tur sürerken oluyor, boştayken durmuyor.
"""

from __future__ import annotations

import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .fluent import Tokens
from .motion import clock

#: Çizim 24 birimlik ızgarada, glyph'lerle aynı.
GRID = 24.0

#: Kare aralığı.
FRAME_MS = 33

#: Göz kırpma arası, saniye. Sabit aralık mekanik görünüyor.
BLINK_MIN, BLINK_MAX = 2.2, 5.5

#: Kırpmanın süresi, kare sayısı.
BLINK_FRAMES = 4

#: Gövdenin çapı, ızgara birimi.
BODY = 20.0

#: Köşe yarıçapı. 10 tam daire yapardı; 7.4 squircle bırakıyor — bütün
#: yüzeylerimiz yuvarlatılmış dikdörtgen ve kafa da onlardan biri.
CORNER = 7.4

#: Yarık gözün eni, boyu ve eğimi.
SLIT_W, SLIT_H, SLIT_TILT = 1.8, 6.0, 13.0

#: Gözlerin merkeze uzaklığı.
EYE_X, EYE_Y = 2.9, -1.4

#: Ezilip uzama yayının katsayıları. Sertlik yüksek, sönüm orta: itki
#: hızla sönüyor, yoksa kafa boşta da sallanmaya devam ederdi.
SPRING_K, SPRING_DAMP = 0.28, 0.26

#: Bir olayın gövdeye verdiği itki.
IMPULSE = 0.055

#: Ezilmenin sınırı. Sınırsızken kafa krep oluyordu: iki kare arasında
#: gelen itkiler toplanıyor ve akış hızlandığında gövde yassılıyordu.
#: Ölçtüm — tek karede on bir itki biriktiğinde 2.5:1 bir hap çıkıyor.
SQUASH_MAX = 0.16

#: Gözbebeğinin kaçabileceği en uzak yer, ızgara birimi.
#:
#: 1.7 ile başladım ve çizip baktığımda bakış hiç okunmuyordu: kafa
#: halkanın içinde 37 piksele düşüyor, 1.7 birim orada 2.6 piksel ediyor.
#: 2.6 birimde göz gerçekten kayıyor ve gövdenin dışına da taşmıyor.
GAZE = 2.6

#: Araçtan yüz durumuna. Her araç bir şeye bakıyor, bir şey yazıyor ya da
#: bir şey düşünüyor; hepsine aynı yüzü koymak yüzü anlamsız kılardı.
TOOL_FACE = {
    "screenshot": "bakiyor", "zoom": "bakiyor", "switch_display": "bakiyor",
    "read_ui_tree": "bakiyor", "cursor_position": "bakiyor",
    "left_click": "tikliyor", "right_click": "tikliyor",
    "middle_click": "tikliyor", "double_click": "tikliyor",
    "triple_click": "tikliyor", "mouse_move": "tikliyor",
    "left_mouse_down": "tikliyor", "left_mouse_up": "tikliyor",
    "left_click_drag": "tikliyor", "scroll": "tikliyor",
    "type": "yaziyor", "key": "yaziyor", "hold_key": "yaziyor",
    "write_file": "yaziyor", "write_files": "yaziyor", "edit_file": "yaziyor",
    "office_edit": "yaziyor", "office_write": "yaziyor",
    "skill_write": "yaziyor", "button_write": "yaziyor",
    "wait": "dusunuyor",
}


def face_for(tool: str) -> str:
    return TOOL_FACE.get(tool, "dusunuyor")


class AjanKafasi(QWidget):
    """Ajanın yüzü. Durumu ve bakışı dışarıdan geliyor."""

    #: Halkanın içinde kaplayacağı oran. Dolu gövde ağır bastığı için
    #: konturlu hâlinden küçük duruyor.
    fill = 0.56

    def __init__(self, t: Tokens, size: int = 44) -> None:
        super().__init__()
        self.t = t
        self.setFixedSize(size, size)
        self._state = "bosta"
        self._gaze = QPointF(0.0, 0.0)
        self._gaze_hedef = QPointF(0.0, 0.0)
        self._blink = 0
        # İlk kırpma rastgele bir geleceğe kuruluyor. Sıfırdan başlarken
        # yüz açılır açılmaz gözünü kırpıyordu — ve tur kısa sürerse
        # bütün ömrünü gözü kapalı geçiriyordu.
        self._blink_at = random.uniform(BLINK_MIN, BLINK_MAX) * (1000 / FRAME_MS)
        self._live = False
        self._squash = 0.0         # + geniş ve basık, - dar ve uzun
        self._vel = 0.0
        self._frame = 0
        #: Yüz değiştiğinde çağrılıyor. Kafa `RunRing`in içine boyandığında
        #: kendi widget'ı görünmez oluyor; yeniden çizmesi gereken halka.
        self.on_change = self.update
        self._abone = False

    # --- durum ------------------------------------------------------------

    def set_live(self, live: bool) -> None:
        """Tur sürüyor mu. Boştayken kırpma da durur — hareket, bir şeyin
        olduğu anlamına gelmeli."""
        if self._live == live:
            return
        self._live = live
        if live:
            clock().subscribe(self._tick)
            self._abone = True
        elif self._abone:
            clock().unsubscribe(self._tick)
            self._abone = False
            self._blink = 0
        self.on_change()

    def set_state(self, state: str) -> None:
        self._state = state
        self.on_change()

    def set_tool(self, tool: str) -> None:
        self.set_state(face_for(tool))

    def look_at(self, x: float, y: float) -> None:
        """Bakışı yönlendirir. `x` ve `y` -1 ile 1 arasında, ekranın
        neresine bakıldığını anlatıyor."""
        self._gaze_hedef = QPointF(
            max(-1.0, min(1.0, x)), max(-1.0, min(1.0, y))
        )

    def look_forward(self) -> None:
        self._gaze_hedef = QPointF(0.0, 0.0)

    # --- kare -------------------------------------------------------------

    def _tick(self, dt: float = FRAME_MS / 1000) -> None:
        # Kare sayısı yerine geçen zaman: kare düşerse animasyon
        # yavaşlamamalı. `motion` bunun testini taşıyor.
        self._frame += dt / (FRAME_MS / 1000)
        # Bakış hedefe yumuşak kayıyor: göz ışınlanmıyor.
        self._gaze += (self._gaze_hedef - self._gaze) * 0.22

        if self._blink > 0:
            self._blink -= 1
        elif self._frame >= self._blink_at:
            self._blink = BLINK_FRAMES
            self._blink_at = self._frame + random.uniform(
                BLINK_MIN, BLINK_MAX
            ) * (1000 / FRAME_MS)

        # Yay: itki verilmediğinde sıfıra dönüyor ve orada duruyor.
        self._vel += -self._squash * SPRING_K
        self._vel *= (1.0 - SPRING_DAMP)
        self._squash = max(-SQUASH_MAX,
                           min(SQUASH_MAX, self._squash + self._vel))
        self.on_change()

    def bump(self) -> None:
        """Bir şey geldi — gövdeye küçük bir itki.

        Boşta salınan bir kafa "bir şey oluyor" derdi; oysa hareket
        yalnızca gerçekten bir şey geldiğinde olmalı. Model bir parça
        yazdığında ya da bir adım bittiğinde buraya geliniyor.
        """
        self._vel = min(self._vel + IMPULSE, IMPULSE * 2)

    # --- çizim ------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.paint(painter, self.width(), QPointF(0, 0))
        painter.end()

    def paint(self, painter: QPainter, size: float, origin: QPointF) -> None:
        """Yüzü verilen boyutta, verilen köşeden boyar.

        Ayrı bir metot çünkü kafa `RunRing`in ortasına da giriyor: halka
        koşunun kaydı, kafa onun içindeki yüz.
        """
        t = self.t
        hata = self._state == "hata"
        govde = QColor(t.critical if hata else t.accent)

        painter.save()
        painter.translate(origin)
        painter.scale(size / GRID, size / GRID)
        painter.translate(12.0, 12.0)

        self._govde(painter, govde)
        self._gozler(painter)
        painter.restore()

    def _govde(self, painter: QPainter, renk: QColor) -> None:
        """Dolu gövde — konturu yok.

        Daire değil squircle: uygulamanın bütün yüzeyleri yuvarlatılmış
        dikdörtgen ve kafa da onlardan biri gibi durmalı. Tam daire
        başka bir yerden gelmiş gibi dururdu.

        Ezilip uzuyor. Bir parça geldiğinde gövdeye küçük bir itki
        biniyor ve yay gibi sönüyor: hareket, gerçekten bir şeyin geldiği
        anlamına geliyor. Boşta hiç kıpırdamıyor.
        """
        yari = BODY / 2
        w = yari * (1.0 + self._squash)
        h = yari * (1.0 - self._squash)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(renk)
        painter.drawRoundedRect(
            QRectF(-w, -h, w * 2, h * 2), CORNER, CORNER
        )

    def _gozler(self, painter: QPainter) -> None:
        """İki eğik yarık. Ağız yok — ifadeyi gözler taşıyor.

        Yarıklar gövdeye oyuluyor: arka planın rengiyle boyanıyorlar, o
        yüzden gövde nereye giderse gözler onunla gidiyor.
        """
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.t.background))

        kapali = self._blink > 0
        dx = self._gaze.x() * GAZE
        dy = self._gaze.y() * GAZE
        # Gövde ezildiğinde gözler de onunla hareket ediyor; sabit kalsalar
        # yüzün içinde kayıyormuş gibi görünürdü.
        dy -= self._squash * 2.2

        if self._state == "bitti" and not kapali:
            self._gulen_gozler(painter, dx, dy)
            return

        h = SLIT_H * (0.12 if kapali else self._slit_scale())
        for taraf in (-1, 1):
            painter.save()
            painter.translate(EYE_X * taraf + dx, EYE_Y + dy)
            painter.rotate(self._slit_angle(taraf))
            painter.drawRoundedRect(
                QRectF(-SLIT_W / 2, -h / 2, SLIT_W, h), SLIT_W / 2, SLIT_W / 2
            )
            painter.restore()

    def _slit_scale(self) -> float:
        """Yarığın boyu. Bakarken açılıyor, yazarken kısılıyor —
        dikkatini nereye verdiği."""
        return {"bakiyor": 1.25, "yaziyor": 0.62, "dusunuyor": 0.85}.get(
            self._state, 1.0
        )

    def _slit_angle(self, taraf: int) -> float:
        """Yarığın eğimi. Hatada ikisi içeri dönüyor: renk tek başına
        yetmiyor, bu temada kırmızı ile vurgu rengi birbirine çok yakın."""
        if self._state == "hata":
            return -34.0 * taraf
        # İki yarık **paralel**. Aynalı eğimle denedim ve yüz sürekli hafif
        # asık duruyordu: içe bakan iki çizgi çatık kaş okunuyor. Paralel
        # eğim nötr kalıyor ve kızgın ifadeyi hataya bırakıyor.
        return SLIT_TILT

    def _gulen_gozler(self, painter: QPainter, dx: float, dy: float) -> None:
        """Bitti: yarıklar yukarı kıvrılıyor."""
        kalem = QPen(QColor(self.t.background), SLIT_W)
        kalem.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(kalem)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for taraf in (-1, 1):
            painter.drawArc(
                QRectF(EYE_X * taraf + dx - 1.5, EYE_Y + dy - 1.0, 3.0, 2.6),
                20 * 16, 140 * 16,
            )
