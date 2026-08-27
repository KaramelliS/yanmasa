"""Ajanın yüzü.

Karikatür bir kafa: yuvarlatılmış bir gövde, iki göz, bir ağız ve yanlarda
iki kulak. Uygulamanın geri kalanıyla aynı geometriden çizilmiş —
yuvarlatılmış dikdörtgen, tek kalınlıkta çizgi, aynı palet. Başka bir
yerden alınmış bir maskot burada yabancı dururdu.

**Gözler gerçekten baktığı yere bakıyor.** Ajan ekranın sağ altına
tıklayacaksa gözbebekleri oraya kayıyor; koordinat zaten elimizde. Bu
projedeki bütün hareket aynı kuralda: `MicDot`un halkası gerçek ses
şiddetini, `RunRing`in dilimleri gerçek adımları gösteriyor. Rastgele
kıpırdayan bir maskot bu kuralı bozardı ve süs olurdu.

Yüz ifadesi de uydurma değil, ajanın o an ne yaptığı:

- **bakiyor** — gözler iri, ağız nötr (bakmak bir duygu değil)
- **tikliyor** — gözbebekleri hedefe kayıyor
- **yaziyor** — gözler aşağıda, ağız yazarken açık
- **dusunuyor** — bakış yukarı sola, ağız düz
- **hata** — kaşlar çatık, çizgi kırmızı
- **bitti** — gözler gülümseme yayına dönüyor

Göz kırpma tek rastgele şey ve sebebi var: hiç kırpmayan bir yüz ölü
görünüyor. Kırpma tur sürerken oluyor, boştayken durmuyor.
"""

from __future__ import annotations

import random

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .fluent import Tokens

#: Çizim 24 birimlik ızgarada, glyph'lerle aynı.
GRID = 24.0

#: Kare aralığı.
FRAME_MS = 33

#: Göz kırpma arası, saniye. Sabit aralık mekanik görünüyor.
BLINK_MIN, BLINK_MAX = 2.2, 5.5

#: Kırpmanın süresi, kare sayısı.
BLINK_FRAMES = 4

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

    def __init__(self, t: Tokens, size: int = 44) -> None:
        super().__init__()
        self.t = t
        self.setFixedSize(size, size)
        self._state = "bosta"
        self._gaze = QPointF(0.0, 0.0)
        self._gaze_hedef = QPointF(0.0, 0.0)
        self._blink = 0
        self._blink_at = 0.0
        self._live = False
        self._mouth = 0.0          # yazarken açılıp kapanan ağız
        self._frame = 0
        #: Yüz değiştiğinde çağrılıyor. Kafa `RunRing`in içine boyandığında
        #: kendi widget'ı görünmez oluyor; yeniden çizmesi gereken halka.
        self.on_change = self.update
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # --- durum ------------------------------------------------------------

    def set_live(self, live: bool) -> None:
        """Tur sürüyor mu. Boştayken kırpma da durur — hareket, bir şeyin
        olduğu anlamına gelmeli."""
        if self._live == live:
            return
        self._live = live
        if live:
            self._timer.start(FRAME_MS)
        else:
            self._timer.stop()
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

    def _tick(self) -> None:
        self._frame += 1
        # Bakış hedefe yumuşak kayıyor: göz ışınlanmıyor.
        self._gaze += (self._gaze_hedef - self._gaze) * 0.22

        if self._blink > 0:
            self._blink -= 1
        elif self._frame >= self._blink_at:
            self._blink = BLINK_FRAMES
            self._blink_at = self._frame + random.uniform(
                BLINK_MIN, BLINK_MAX
            ) * (1000 / FRAME_MS)

        if self._state == "yaziyor":
            self._mouth = (self._frame % 12) / 12.0
        self.on_change()

    # --- çizim ------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.paint(painter, self.width(), QPointF(0, 0))
        painter.end()

    def paint(self, painter: QPainter, size: float, origin: QPointF) -> None:
        """Yüzü verilen boyutta, verilen köşeden boyar.

        Ayrı bir metot çünkü kafa `RunRing`in ortasına da giriyor: halka
        koşunun kaydı, kafa onun içindeki yüz. İki ayrı widget üst üste
        koymak, ikisinin ortasını hizalamak demekti.
        """
        t = self.t
        hata = self._state == "hata"
        cizgi = QColor(t.critical if hata else t.text_secondary)
        ic = QColor(t.critical if hata else t.accent)

        painter.save()
        painter.translate(origin)
        olcek = size / GRID
        painter.scale(olcek, olcek)

        kalem = QPen(cizgi, 1.5 / max(olcek, 0.001) * olcek)
        kalem.setWidthF(1.5)
        kalem.setCapStyle(Qt.PenCapStyle.RoundCap)
        kalem.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(kalem)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        self._kulaklar(painter, kalem)
        painter.drawRoundedRect(QRectF(4.5, 5.0, 15.0, 13.0), 5.0, 5.0)
        self._gozler(painter, kalem, ic)
        self._agiz(painter, kalem)
        painter.restore()

    def _kulaklar(self, painter: QPainter, kalem: QPen) -> None:
        """Yanlardaki iki çentik. Yüzü insan değil makine yapan şey bu:
        çentiksiz hâli kaşsız bir surat gibi duruyordu."""
        painter.drawLine(QPointF(3.2, 10.0), QPointF(3.2, 13.0))
        painter.drawLine(QPointF(20.8, 10.0), QPointF(20.8, 13.0))

    def _gozler(self, painter: QPainter, kalem: QPen, ic: QColor) -> None:
        kapali = self._blink > 0
        sol = QPointF(9.4 + self._gaze.x() * GAZE, 10.6 + self._gaze.y() * GAZE)
        sag = QPointF(14.6 + self._gaze.x() * GAZE, 10.6 + self._gaze.y() * GAZE)

        if self._state == "bitti" and not kapali:
            # Gülümseyen göz: iki yay. Nokta göz + gülen ağız, ikisi birden
            # fazla neşe oluyordu; sevinç tek yerde.
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(kalem)
            for merkez in (sol, sag):
                painter.drawArc(
                    QRectF(merkez.x() - 1.9, merkez.y() - 1.4, 3.8, 2.8),
                    20 * 16, 140 * 16,
                )
            return

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ic)
        if kapali:
            for merkez in (sol, sag):
                painter.drawRoundedRect(
                    QRectF(merkez.x() - 1.8, merkez.y() - 0.4, 3.6, 0.8), 0.4, 0.4
                )
            return

        # "bakiyor" gözü büyütüyor: ekrana bakmak, dikkatin dışarıda olması.
        r = 2.0 if self._state == "bakiyor" else 1.6
        for merkez in (sol, sag):
            painter.drawEllipse(merkez, r, r)

        if self._state == "hata":
            # Çatık kaş. Kırmızı tek başına yetmiyor, biçim de söylemeli.
            painter.setPen(kalem)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(QPointF(7.6, 7.9), QPointF(11.0, 8.9))
            painter.drawLine(QPointF(16.4, 7.9), QPointF(13.0, 8.9))

    def _agiz(self, painter: QPainter, kalem: QPen) -> None:
        painter.setPen(kalem)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        y = 14.6
        if self._state == "yaziyor":
            # Yazarken açılıp kapanan ağız — tuşa basma ritmi.
            h = 0.6 + self._mouth * 1.6
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.t.text_secondary))
            painter.drawRoundedRect(
                QRectF(10.6, y - h / 2, 2.8, h), 0.6, 0.6
            )
        elif self._state == "bitti":
            painter.drawLine(QPointF(10.4, y), QPointF(13.6, y))
        elif self._state == "hata":
            painter.drawArc(QRectF(10.0, y - 0.2, 4.0, 2.6), 20 * 16, 140 * 16)
        else:
            painter.drawLine(QPointF(10.6, y), QPointF(13.4, y))
