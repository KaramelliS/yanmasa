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
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

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

#: Akıştaki bir adım satırının yüksekliği.
ROW_H = 26

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
    PAD_TOP = 3
    PAD_BOTTOM = 3
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
        # Düzen yüksekliği `sizeHint`ten alıyor ve genişliğe bağlı
        # yükseklik ancak politika söylerse dikkate alınıyor. Bu satır
        # olmadan metin satırları 0 yükseklik alıp adımların üstüne
        # biniyordu — ölçtüm, ekranda üst üste çıktılar.
        politika = QSizePolicy(QSizePolicy.Policy.Preferred,
                               QSizePolicy.Policy.Minimum)
        politika.setHeightForWidth(True)
        self.setSizePolicy(politika)

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

    def sizeHint(self) -> QSize:
        genislik = self.width() or 320
        return QSize(genislik, self.heightForWidth(genislik))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def _resize_to_text(self) -> None:
        if self.width() > 0:
            self.setMinimumHeight(self.heightForWidth(self.width()))
        self.updateGeometry()

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


class AdimSatiri(QWidget):
    """Akıştaki tek bir adım: işin çizimi, ne yaptığı, nerede yaptığı.

    Çizim araca göre değişiyor — bakmak, okumak, tıklamak, yazmak, kabuk,
    dosya, sunucu, yetenek. Aynı simgeyi her adıma koymak, akışı okunmaz
    bir liste yapardı: hangi adımın ne olduğunu ancak metni okuyarak
    anlardın.
    """

    def __init__(self, t: Tokens, tool: str, baslik: str, detay: str) -> None:
        super().__init__()
        self.t = t
        self._tone = "normal"
        self._key = glyph_for(tool)
        self._baslik = baslik
        self._detay = detay
        self.setFixedHeight(ROW_H)

    def sizeHint(self) -> QSize:
        # `setFixedHeight` en/boy sınırlarını koyuyor ama `sizeHint`i
        # değiştirmiyor: düz bir `QWidget` geçersiz (-1) ipucu veriyor ve
        # düzen satırı hiç saymıyordu. Ölçtüm — dört adım toplamda sıfır
        # yükseklik sayılıyor, son satır kırpılıyordu.
        return QSize(160, ROW_H)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def set_tone(self, tone: str) -> None:
        """`normal` ya da `hata`. Düşen adım kırmızıya dönüyor."""
        self._tone = tone
        self.update()

    def paintEvent(self, _event) -> None:
        t = self.t
        hata = self._tone == "hata"
        ana = t.critical if hata else t.accent
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        paint_glyph(painter, self._key, 16, ana,
                    t.critical if hata else t.text_tertiary, QPointF(14, 5))

        font = QFont(t.font_ui)
        font.setPixelSize(12)
        painter.setFont(font)
        olcu = painter.fontMetrics()
        x = 38
        painter.setPen(QColor(t.critical if hata else t.text_secondary))
        painter.drawText(x, 0, olcu.horizontalAdvance(self._baslik), self.height(),
                         int(Qt.AlignmentFlag.AlignVCenter), self._baslik)

        if self._detay:
            x += olcu.horizontalAdvance(self._baslik) + 8
            kalan = self.width() - x - 14
            if kalan > 24:
                painter.setPen(QColor(t.text_tertiary))
                painter.drawText(
                    x, 0, kalan, self.height(),
                    int(Qt.AlignmentFlag.AlignVCenter),
                    olcu.elidedText(self._detay, Qt.TextElideMode.ElideRight, kalan),
                )
        painter.end()


class Akis(QWidget):
    """Turun dökümü: senin cümlen, ajanın anlattıkları, attığı adımlar.

    Önceden burada yalnızca son cevap duruyordu; ne yaptığını görmek için
    ana pencereye bakman gerekiyordu. Oysa çubuk zaten gözünün olduğu yer.
    Adımlar buraya, her biri kendi çizimiyle düşüyor.
    """

    def __init__(self, t: Tokens) -> None:
        super().__init__()
        self.t = t
        self._son_metin: AkanMetin | None = None
        self._son_adim: AdimSatiri | None = None
        self._kutu = QVBoxLayout(self)
        self._kutu.setContentsMargins(0, 10, 0, 6)
        self._kutu.setSpacing(2)

    # --- içerik -----------------------------------------------------------

    def clear(self) -> None:
        while self._kutu.count():
            oge = self._kutu.takeAt(0).widget()
            if oge is not None:
                oge.setParent(None)
                oge.deleteLater()
        self._son_metin = None
        self._son_adim = None
        self.updateGeometry()

    def is_empty(self) -> bool:
        return self._kutu.count() == 0

    def add_user(self, metin: str) -> None:
        # Önceki anlatımın imleci sönüyor: iki yerde birden yanıp
        # sönen imleç, ikisinin de yazıldığını söylerdi.
        self.end_stream()
        self._son_metin = None
        self._ekle(AdimSatiri(self.t, "__sen__", "Sen", metin))

    def add_step(self, tool: str, baslik: str, detay: str) -> None:
        # Önceki anlatımın imleci sönüyor: iki yerde birden yanıp
        # sönen imleç, ikisinin de yazıldığını söylerdi.
        self.end_stream()
        self._son_metin = None
        self._son_adim = AdimSatiri(self.t, tool, baslik, detay)
        self._ekle(self._son_adim)

    def mark_last(self, is_error: bool) -> None:
        if self._son_adim is not None and is_error:
            self._son_adim.set_tone("hata")

    def stream(self, parca: str) -> None:
        if self._son_metin is None:
            self._son_metin = AkanMetin(self.t)
            self._son_metin.set_live(True)
            self._ekle(self._son_metin)
        self._son_metin.append(parca)
        self.updateGeometry()

    def say(self, metin: str) -> None:
        """Akış olmadan tek parça cevap — hata mesajları böyle geliyor."""
        # Önceki anlatımın imleci sönüyor: iki yerde birden yanıp
        # sönen imleç, ikisinin de yazıldığını söylerdi.
        self.end_stream()
        self._son_metin = None
        w = AkanMetin(self.t)
        w.set_text(metin)
        self._ekle(w)

    def end_stream(self) -> None:
        if self._son_metin is not None:
            self._son_metin.set_live(False)

    def text(self) -> str:
        return self._son_metin.text() if self._son_metin else ""

    def _ekle(self, w: QWidget) -> None:
        self._kutu.addWidget(w)
        self.updateGeometry()

    def heightForWidth(self, width: int) -> int:
        if self.is_empty():
            return 0
        toplam = self._kutu.contentsMargins().top() + self._kutu.contentsMargins().bottom()
        for i in range(self._kutu.count()):
            w = self._kutu.itemAt(i).widget()
            if w is None:
                continue
            h = (w.heightForWidth(width) if w.hasHeightForWidth()
                 else w.sizeHint().height())
            toplam += max(h, w.minimumHeight())
            if i:
                toplam += self._kutu.spacing()
        return toplam

    def hasHeightForWidth(self) -> bool:
        return True
