"""Akış göstergeleri: koşu halkası ve akan metin.

**Halka bir bekleme çarkı değil, turun şekli.** Biten her adım halkada
kalıcı bir dilim bırakıyor; başarısız olan kırmızı. Tur bitince halkaya
bakıp "dokuz adım sürdü, biri patladı" diyebiliyorsun. Klasik bekleme
çarkı bunu yapmıyor: sabit hızda döner, sen bekliyor musun yoksa iş mi
yapıyor ayırt edemezsin, ve bittiğinde ardında hiçbir şey bırakmaz.

**Yalnızca gerçekten bir şey geldiğinde ilerliyor.** Modelden bir parça
düştüğünde ya da bir araç sonuç verdiğinde. Model takılırsa halka da
takılıyor — bu bilgi, arıza değil: "neden bekliyor" sorusunun cevabı.
`MicDot` da aynı görüşte, halkası sen sustuğunda duruyor.

**Yay dilimin sonuna asla varmıyor.** Bir adımın bittiğini, bitmeden önce
iddia edemez. Yüzde 92'de durup gerçek sonucu bekliyor.

Metin tarafında `AkanMetin` var: model yazarken harfler geldikçe düşüyor
ve sonunda bir imleç yanıp sönüyor. İmleçsiz akan metin, bitmiş bir cevap
gibi okunuyordu.
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QKeySequence,
    QPainter,
    QPen,
    QTextLayout,
    QTextOption,
)
from PySide6.QtWidgets import QWidget

from .fluent import Tokens
from .glyphs import glyph_for, paint_glyph

#: Kare aralığı. 30 fps: 44 pikselik bir çizimde 60 fps'in farkı
#: görünmüyor, işlemci farkı görünüyor.
FRAME_MS = 33

#: Yayın dilim sonuna yaklaşırken durduğu yer. 1.0 olsaydı adım bitmeden
#: bittiğini söylerdi.
ARC_CEILING = 0.92

#: Bir parça geldiğinde yayın ilerlediği miktar.
ARC_STEP = 0.035

#: Halka en az bu kadar dilime bölünüyor. Tek adımlık bir turda tam
#: çember çizmek, turun bittiğini söylerdi.
MIN_SLOTS = 6

#: Dilimler arasındaki boşluk, derece.
SLOT_GAP = 7.0

#: Bu kadar süre hiçbir şey gelmezse yayın ucu soluyor.
STALL_AFTER = 0.9

#: Düşen adımın yayı bu kadar içeri kaçıyor.
#:
#: Renk tek başına yetmiyor: bu temada `accent` #e7babd ve `critical`
#: #ff99a4 — ikisi de soluk pembe ve 2.4 piksellik bir yayda aynı görünüyor.
#: Ölçtüm. Biçim renge bağlı değil: düşen adım sıradan içeri kayıyor ve
#: temayı değiştirsen de görünür kalıyor.
FAIL_INSET = 3.5


class RunRing(QWidget):
    """Turun şeklini biriktiren halka, ortasında o anki işin çizimi."""

    def __init__(self, t: Tokens, size: int = 44) -> None:
        super().__init__()
        self.t = t
        self.setFixedSize(size, size)
        self._done: list[bool] = []      # her biten adım: hata mı?
        self._glyph = "goz"
        self._prev_glyph = ""
        self._fade = 1.0
        self._arc_target = 0.0
        self._arc = 0.0
        self._live = False
        self._last = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # --- olaylar ----------------------------------------------------------

    def begin(self) -> None:
        """Yeni tur. Önceki turun şekli siliniyor."""
        self._done.clear()
        self._arc = self._arc_target = 0.0
        self._live = True
        self._mark()
        if not self._timer.isActive():
            self._timer.start(FRAME_MS)
        self.update()

    def step(self, tool: str) -> None:
        """Yeni bir araç çağrısı başladı."""
        yeni = glyph_for(tool)
        if yeni != self._glyph:
            self._prev_glyph = self._glyph
            self._glyph = yeni
            self._fade = 0.0
        self._arc = 0.0
        self._arc_target = 0.08
        self._mark()

    def settle(self, is_error: bool) -> None:
        """Adım bitti — halkada kalıcı bir dilim bırakıyor."""
        self._done.append(bool(is_error))
        self._arc = self._arc_target = 0.0
        self._mark()

    def pulse(self) -> None:
        """Modelden bir parça düştü."""
        self._arc_target = min(ARC_CEILING, self._arc_target + ARC_STEP)
        self._mark()

    def finish(self) -> None:
        """Tur bitti. Şekil ekranda kalıyor, hareket duruyor."""
        self._live = False
        self._arc_target = 0.0
        self._timer.stop()
        self.update()

    def _mark(self) -> None:
        self._last = time.monotonic()

    # --- kare -------------------------------------------------------------

    def _tick(self) -> None:
        # Üstel yaklaşma: hızlı başlayıp yumuşak duruyor. Sabit adım
        # olsaydı her kare aynı mesafeyi katedip mekanik görünürdü.
        self._arc += (self._arc_target - self._arc) * 0.18
        if self._fade < 1.0:
            self._fade = min(1.0, self._fade + FRAME_MS / 220)
        self.update()

    # --- çizim ------------------------------------------------------------

    def _slots(self) -> int:
        return max(MIN_SLOTS, len(self._done) + 1)

    def paintEvent(self, _event) -> None:
        t = self.t
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        pay = 3.0
        kutu = QRectF(pay, pay, self.width() - pay * 2, self.height() - pay * 2)
        dilim = 360.0 / self._slots()

        # Ray: halkanın tamamı, sönük. Nereye kadar gidileceğini gösteriyor.
        iz = QPen(QColor(t.divider), 1.0)
        painter.setPen(iz)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(kutu)

        kalem = QPen()
        kalem.setWidthF(2.4)
        kalem.setCapStyle(Qt.PenCapStyle.RoundCap)

        # Biten adımlar. Düşen adım hem kırmızı hem de sıradan içeri kaçık.
        ic = kutu.adjusted(FAIL_INSET, FAIL_INSET, -FAIL_INSET, -FAIL_INSET)
        for i, hata in enumerate(self._done):
            kalem.setColor(QColor(t.critical if hata else t.accent))
            painter.setPen(kalem)
            painter.drawArc(
                ic if hata else kutu,
                int((90 - i * dilim) * 16),
                int(-(dilim - SLOT_GAP) * 16),
            )

        # Süren adım: dilimin içinde büyüyen yay, sonuna varmıyor.
        #
        # Rengi bitmiş dilimlerden farklı olmak zorunda, yoksa nerede
        # olduğunu göremiyorsun — ve bu temada `accent_text`, `accent`in
        # ta kendisi. Beyaza yakın olan "şimdi", pembe olan "oldu".
        if self._arc > 0.004:
            durdu = self._live and (time.monotonic() - self._last) > STALL_AFTER
            onculuk = QColor(t.text_tertiary if durdu else t.text_secondary)
            kalem.setColor(onculuk)
            painter.setPen(kalem)
            uzunluk = (dilim - SLOT_GAP) * self._arc
            basla = 90 - len(self._done) * dilim
            painter.drawArc(kutu, int(basla * 16), int(-uzunluk * 16))
            self._paint_head(painter, kutu, basla - uzunluk, onculuk)

        self._paint_glyph(painter)
        painter.end()

    def _paint_head(self, painter: QPainter, kutu: QRectF,
                    aci: float, renk: QColor) -> None:
        """Yayın ucundaki nokta: "buradayız".

        Yay tek başına nerede bittiğini yeterince söylemiyor — bitmiş
        dilimlerle aynı kalınlıkta ve durağan bir karede ikisi birbirine
        karışıyor.
        """
        r = kutu.width() / 2
        merkez = kutu.center()
        radyan = math.radians(aci)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(renk)
        painter.drawEllipse(
            QPointF(merkez.x() + r * math.cos(radyan),
                    merkez.y() - r * math.sin(radyan)),
            2.1, 2.1,
        )

    def _paint_glyph(self, painter: QPainter) -> None:
        """Ortadaki çizim. Araç değişince eskisi sönerken yenisi geliyor —
        bir anda takas etmek, neyin neye dönüştüğünü göstermiyordu."""
        boyut = self.width() * 0.46
        koken = QPointF((self.width() - boyut) / 2, (self.height() - boyut) / 2)
        t = self.t
        if self._prev_glyph and self._fade < 1.0:
            painter.setOpacity(1.0 - self._fade)
            paint_glyph(painter, self._prev_glyph, boyut,
                        t.accent, t.text_tertiary, koken)
        painter.setOpacity(self._fade if self._prev_glyph else 1.0)
        paint_glyph(painter, self._glyph, boyut, t.accent, t.text_secondary, koken)
        painter.setOpacity(1.0)


class AkanMetin(QWidget):
    """Model yazarken harflerin düştüğü alan, sonunda yanıp sönen imleç.

    `QLabel` yerine kendi düzenini kuruyor çünkü imlecin **son harfin tam
    yanında** durması gerekiyor ve `QLabel` satır kırılımlarını nereye
    koyduğunu söylemiyor. `QTextLayout` bunu söylüyor.

    Fare ile seçme de burada: ajanın cevabını kopyalayabilmek gerekiyor ve
    kendi düzenini kuran bir widget bunu kendi eklemezse kaybediyor.
    """

    PAD_X = 14
    PAD_TOP = 12
    PAD_BOTTOM = 4
    #: Satır yüksekliği çarpanı. 13 piksel gövdede 1.0 sıkışık okunuyor.
    LEADING = 1.34

    def __init__(self, t: Tokens, font_px: int = 13) -> None:
        super().__init__()
        self.t = t
        self._text = ""
        self._live = False
        self._caret_on = True
        self._layout: QTextLayout | None = None
        self._width = 0
        self._sel = (0, 0)
        self._anchor: int | None = None

        self._font = QFont(t.font_ui)
        self._font.setPixelSize(font_px)

        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        # İmleç yanıp sönmesi Windows'un kendi hızında: sistemle uyumsuz
        # bir imleç, ekrandaki tek yanlış ritim olurdu.
        self._blink = QTimer(self)
        self._blink.timeout.connect(self._flip)
        self._interval = max(400, QGuiApplication.styleHints().cursorFlashTime() // 2)

    # --- içerik -----------------------------------------------------------

    def text(self) -> str:
        return self._text

    def set_text(self, text: str) -> None:
        if text == self._text:
            return
        self._text = text
        self._sel = (0, 0)
        self._layout = None
        self._resize_to_text()
        self.update()

    def append(self, parca: str) -> None:
        if not parca:
            return
        self._text += parca
        self._layout = None
        self._resize_to_text()
        self.update()

    def set_live(self, live: bool) -> None:
        """Akış sürüyor mu — imleç yalnızca sürerken yanıp sönüyor."""
        if self._live == live:
            return
        self._live = live
        self._caret_on = True
        if live:
            self._blink.start(self._interval)
        else:
            self._blink.stop()
        self.update()

    def _flip(self) -> None:
        self._caret_on = not self._caret_on
        self.update()

    # --- düzen ------------------------------------------------------------

    def _build(self, width: int) -> QTextLayout:
        if self._layout is not None and self._width == width:
            return self._layout
        secenek = QTextOption()
        secenek.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        duzen = QTextLayout(self._text, self._font)
        duzen.setTextOption(secenek)
        kullanilir = max(1, width - self.PAD_X * 2)
        duzen.beginLayout()
        y = 0.0
        while True:
            satir = duzen.createLine()
            if not satir.isValid():
                break
            satir.setLineWidth(kullanilir)
            satir.setPosition(QPointF(0, y))
            y += satir.height() * self.LEADING
        duzen.endLayout()
        self._layout = duzen
        self._width = width
        self._text_height = y
        return duzen

    def heightForWidth(self, width: int) -> int:
        if not self._text:
            return 0
        self._build(width)
        return int(math.ceil(self._text_height)) + self.PAD_TOP + self.PAD_BOTTOM

    def hasHeightForWidth(self) -> bool:
        return True

    def _resize_to_text(self) -> None:
        if self.width() > 0:
            self.setMinimumHeight(self.heightForWidth(self.width()))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout = None
        self._resize_to_text()

    # --- seçim ------------------------------------------------------------

    def _cursor_at(self, point) -> int:
        duzen = self._build(self.width())
        yerel = QPointF(point.x() - self.PAD_X, point.y() - self.PAD_TOP)
        for i in range(duzen.lineCount()):
            satir = duzen.lineAt(i)
            alt = satir.y() + satir.height() * self.LEADING
            if yerel.y() < alt or i == duzen.lineCount() - 1:
                return satir.xToCursor(yerel.x())
        return len(self._text)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._text:
            self._anchor = self._cursor_at(event.position())
            self._sel = (self._anchor, self._anchor)
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._anchor is not None:
            simdi = self._cursor_at(event.position())
            self._sel = (min(self._anchor, simdi), max(self._anchor, simdi))
            self.update()

    def mouseReleaseEvent(self, _event) -> None:
        self._anchor = None

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.Copy):
            bas, son = self._sel
            if son > bas:
                QGuiApplication.clipboard().setText(self._text[bas:son])
            return
        if event.matches(QKeySequence.StandardKey.SelectAll):
            self._sel = (0, len(self._text))
            self.update()
            return
        super().keyPressEvent(event)

    # --- çizim ------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        if not self._text:
            return
        duzen = self._build(self.width())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QColor(self.t.text))

        secimler = []
        bas, son = self._sel
        if son > bas:
            aralik = QTextLayout.FormatRange()
            aralik.start = bas
            aralik.length = son - bas
            aralik.format.setBackground(QColor(self.t.accent))
            aralik.format.setForeground(QColor(self.t.on_accent))
            secimler.append(aralik)

        koken = QPointF(self.PAD_X, self.PAD_TOP)
        duzen.draw(painter, koken, secimler)

        if self._live and self._caret_on and duzen.lineCount():
            self._paint_caret(painter, duzen, koken)
        painter.end()

    def _paint_caret(self, painter: QPainter, duzen: QTextLayout,
                     koken: QPointF) -> None:
        """Son harfin yanındaki imleç. Blok değil ince bir çubuk: metnin
        altını kapatan bir blok, gelen son kelimeyi okunmaz yapıyordu."""
        satir = duzen.lineAt(duzen.lineCount() - 1)
        x = satir.cursorToX(len(self._text))[0]
        yukseklik = satir.height() * 0.82
        ust = satir.y() + (satir.height() - yukseklik) / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.t.accent))
        painter.drawRoundedRect(
            QRectF(koken.x() + x + 1, koken.y() + ust, 2.0, yukseklik), 1.0, 1.0
        )
