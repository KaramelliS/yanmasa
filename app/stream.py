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
from .motion import (
    Ripple, Shake, Spring, Tween, clock, ease_out_back, ease_out_expo,
)
from .kafa import AjanKafasi


def _yuz(t: Tokens, size: int):
    """Halkanın içindeki yüz.

    Sıra: kendi SVG'miz, sonra kodla çizilen yüz. İkisi de aynı arayüzü
    sunuyor.

    Arada bir üçüncü katman vardı — hazır GIF karelerinden oynayan bir
    maskot. Kaldırıldı: 1180 kare 8.8 MB tutuyordu, tema bilmiyordu,
    gözbebeğini oynatamıyordu, ve kareler başkasının çizimlerinden
    ayrılmıştı. SVG varlıkları depoda duruyor; yoksa `svg_yap.py` onları
    yeniden üretiyor.
    """
    yuz = _svg_yuz(t, size)
    return yuz if yuz is not None else AjanKafasi(t, size)


def _svg_yuz(t: Tokens, size: int):
    try:
        from .svgyuz import SvgYuz, varlik_var

        return SvgYuz(t, size) if varlik_var() else None
    except Exception:
        return None


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

#: İzin kalınlığı, sol kenardan uzaklığı ve uçlardaki pay.
TRACK_W, TRACK_X, TRACK_PAD = 3.0, 5.0, 6.0

#: Yüzün üstten uzaklığı.
FACE_Y = 2.0

#: Bu kadar süre hiçbir şey gelmezse yayın ucu soluyor.
STALL_AFTER = 0.9

#: Akıştaki bir adım satırının yüksekliği. 26'ydı; yedi satırlık bir
#: dökümde 28 piksel fazladan yer kaplıyordu ve satırlar zaten 12 punto.
ROW_H = 22

#: Düşen adımın işareti bu kadar kalınlaşıyor.
#:
#: Renk tek başına yetmiyor: bu temada `accent` #e7babd ve `critical`
#: #ff99a4 — ikisi de soluk pembe ve ince bir işarette aynı görünüyor.
#: Ölçtüm. Biçim renge bağlı değil: düşen adım kalınlaşıyor ve temayı
#: değiştirsen de görünür kalıyor.
FAIL_WIDTH = 2.0


class RunRing(QWidget):
    """Turun şeklini biriktiren iz, üstünde ajanın yüzü.

    Önce bir daireydi ve yüz ortasındaydı. Maskotun eline nesne verince
    çalışmaz oldu: nesne çemberi kesiyor, koşu kaydı okunmaz hâle
    geliyordu. Daireyi büyütmek de olmazdı — figür küçülür, ifade
    kaybolurdu.

    Şimdi **dikey bir iz**, sütunun sol kenarında. Adımlar yukarıdan
    aşağı diziliyor, yani dökümle aynı yönde okunuyor ve figürün üstünden
    hiç geçmiyor. Çember hiç kırılmıyor çünkü çember yok.
    """

    def __init__(self, t: Tokens, size: int = 52) -> None:
        super().__init__()
        self.t = t
        self.setFixedSize(size, size)
        self._done: list[bool] = []      # her biten adım: hata mı?
        # Halkanın içindeki yüz. Ayrı bir widget olarak üst üste koymak
        # iki ortayı hizalamak demekti; yüz kendi çizimini buraya boyuyor.
        #
        # Hazır kareler varsa maskot, yoksa çizilen yüz. İkisi aynı
        # arayüzü sunuyor; halka hangisi olduğunu bilmiyor. Varlıksız bir
        # kopyada uygulama yüzsüz kalmamalı.
        self.face = _yuz(t, size)
        self.face.setParent(self)
        #: Yüzü halka çiziyor. Bir dönem sahne çiziyordu — maskotun
        #: elinde nesne varken sıra önemliydi — ama nesneler kalktı.
        self.yuzu_ciz = True
        self.face.hide()
        self.face.on_change = self.update
        self._glyph = "goz"
        self._prev_glyph = ""
        self._fade = 1.0
        self._arc_target = 0.0
        # Yay: yolun ortasında hedef değişirse hız korunuyor. Süreli bir
        # geçiş orada sıfırlanıp zıplardı ve akış sırasında hedef saniyede
        # yirmi kez değişiyor.
        self._arc_spring = Spring(0.0, stiffness=150.0)
        # İniş: yeni biten dilim yerine oturarak geliyor, birden
        # belirmiyor. Turun tek yazılı anı bu.
        self._land = Spring(1.0, stiffness=210.0, damping=17.0)
        self._ripple = Ripple(0.5)
        self._shake = Shake()
        self._live = False
        self._last = 0.0
        self._abone = False

    # --- olaylar ----------------------------------------------------------

    def begin(self) -> None:
        """Yeni tur. Önceki turun şekli siliniyor."""
        self._done.clear()
        self._arc_target = 0.0
        self._arc_spring.jump(0.0)
        self._land.jump(1.0)
        self._live = True
        self.face.set_live(True)
        self.face.set_state("dusunuyor")
        self._mark()
        self._dinle(True)
        self.update()

    def step(self, tool: str) -> None:
        """Yeni bir araç çağrısı başladı."""
        self.face.set_tool(tool)
        self.face.bump()
        yeni = glyph_for(tool)
        if yeni != self._glyph:
            self._prev_glyph = self._glyph
            self._glyph = yeni
            self._fade = 0.0
        self._arc_spring.jump(0.0)
        self._arc_target = 0.08
        self._mark()
        self._dinle(True)

    def settle(self, is_error: bool) -> None:
        """Adım bitti — halkada kalıcı bir dilim bırakıyor."""
        self._done.append(bool(is_error))
        self.face.bump()
        # İniş: dilim sıfırdan tam boyuna yayla açılıyor ve halkadan bir
        # dalga çıkıyor. Adımın **bittiği** an, adımın sürdüğü andan
        # başka görünmeli.
        self._land.jump(0.0)
        self._land.to(1.0)
        self._ripple.hit()
        if is_error:
            self.face.set_state("hata")
            self._shake.hit(1.0)
        self._arc_target = 0.0
        self._arc_spring.jump(0.0)
        self._mark()
        self._dinle(True)

    def pulse(self) -> None:
        """Modelden bir parça düştü."""
        self._arc_target = min(ARC_CEILING, self._arc_target + ARC_STEP)
        self.face.bump()
        self._mark()

    def finish(self) -> None:
        """Tur bitti. Şekil ekranda kalıyor, hareket duruyor."""
        self._live = False
        self.face.set_state("bitti")
        self.face.look_forward()
        self.face.set_live(False)
        self._arc_target = 0.0
        self._arc_spring.to(0.0)
        self.update()

    def _mark(self) -> None:
        self._last = time.monotonic()

    def _dinle(self, ac: bool) -> None:
        if ac and not self._abone:
            clock().subscribe(self._tick)
            self._abone = True
        elif not ac and self._abone:
            clock().unsubscribe(self._tick)
            self._abone = False

    def hideEvent(self, event) -> None:
        # Görünmeyen bir şeyi canlandırmak boşa iş.
        self._dinle(False)
        super().hideEvent(event)

    def showEvent(self, event) -> None:
        # Yüz görünür olduğu sürece nefes alıyor: bekleme animasyonu tur
        # bitince de sürüyor.
        super().showEvent(event)
        self._dinle(True)

    # --- kare -------------------------------------------------------------

    def _tick(self, dt: float) -> None:
        # Yüz gizli bir çocuk widget: kendi saatine abone olamıyor,
        # halka onu buradan sürüyor.
        adim = getattr(self.face, "step", None)
        if adim is not None:
            adim(dt)
        self._arc_spring.to(self._arc_target)
        self._arc_spring.step(dt)
        self._land.step(dt)
        self._ripple.step(dt)
        self._shake.step(dt)
        if self._fade < 1.0:
            self._fade = min(1.0, self._fade + dt / 0.22)
        self.update()
        # Yüz görünür olduğu sürece devam: bekleme animasyonu duruyorsa
        # halka ölü bir rozete dönüyor.

    @property
    def _arc(self) -> float:
        return max(0.0, self._arc_spring.value)

    # --- çizim ------------------------------------------------------------

    def _slots(self) -> int:
        return max(MIN_SLOTS, len(self._done) + 1)

    def paintEvent(self, _event) -> None:
        t = self.t
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Hata titremesi izi sarsıyor: kırmızı bir dilim okunmayı bekler,
        # kımıldayan bir şey gözü kendine çeker.
        sars = self._shake.amount and self._shake.step(0.0) or 0.0
        self._izi_ciz(painter, sars)
        self._paint_glyph(painter)
        painter.end()

    def _izi_ciz(self, painter: QPainter, sars: float) -> None:
        t = self.t
        x = TRACK_X + sars * 2.0
        ust, alt = TRACK_PAD, self.height() - TRACK_PAD
        boy = max(1.0, alt - ust)

        # Ray: bütün iz, sönük. Nereye kadar gidileceğini gösteriyor.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(t.divider))
        painter.drawRoundedRect(
            QRectF(x - TRACK_W / 2, ust, TRACK_W, boy), TRACK_W / 2, TRACK_W / 2
        )

        yuva = max(MIN_SLOTS, len(self._done) + 1)
        dilim = boy / yuva
        bosluk = min(3.0, dilim * 0.22)

        # Biten adımlar. Düşen adım hem kırmızı hem de sıradan dışarı
        # taşıyor: bu temada iki renk küçük bir işarette ayırt edilmiyor.
        son = len(self._done) - 1
        for i, hata in enumerate(self._done):
            oran = (ease_out_back(min(1.0, max(0.0, self._land.value)))
                    if i == son else 1.0)
            uzunluk = max(0.0, (dilim - bosluk) * oran)
            en = TRACK_W * (FAIL_WIDTH if hata else 1.0)
            painter.setBrush(QColor(t.critical if hata else t.accent))
            painter.drawRoundedRect(
                QRectF(x - en / 2, ust + i * dilim, en, uzunluk),
                en / 2, en / 2,
            )

        # Süren adım: dilimin içinde büyüyen parça, sonuna varmıyor.
        if self._arc > 0.004:
            durdu = self._live and (time.monotonic() - self._last) > STALL_AFTER
            renk = QColor(t.text_tertiary if durdu else t.text_secondary)
            painter.setBrush(renk)
            uzunluk = (dilim - bosluk) * self._arc
            bas_y = ust + len(self._done) * dilim
            painter.drawRoundedRect(
                QRectF(x - TRACK_W / 2, bas_y, TRACK_W, max(0.0, uzunluk)),
                TRACK_W / 2, TRACK_W / 2,
            )
            self._paint_head(painter, x, bas_y + uzunluk, renk)

        # Biten adımın dalgası: izin ucundan dışarı yayılıp sönüyor.
        if self._ripple.alive:
            hale = QColor(t.accent)
            hale.setAlphaF(0.30 * self._ripple.alpha)
            painter.setPen(QPen(hale, 1.4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r = 4.0 + self._ripple.radius * 9.0
            merkez_y = ust + min(len(self._done), yuva) * dilim
            painter.drawEllipse(QPointF(x, merkez_y), r, r)
            painter.setPen(Qt.PenStyle.NoPen)

    def _paint_head(self, painter: QPainter, x: float, y: float,
                    renk: QColor) -> None:
        """İzin ucundaki nokta: "buradayız".

        Çizgi tek başına nerede bittiğini yeterince söylemiyor — bitmiş
        dilimlerle aynı kalınlıkta ve durağan bir karede ikisi birbirine
        karışıyor.
        """
        painter.setBrush(renk)
        painter.drawEllipse(QPointF(x, y), 2.4, 2.4)

    def _paint_glyph(self, painter: QPainter) -> None:
        """Ortadaki yüz.

        Eskiden burada aracın çizimi vardı; o çizimler artık dökümde, her
        adımın kendi satırında. Burada tek bir şey olmalı ve o da ajanın
        kendisi: hangi araçta olduğunu satırdan okuyorsun, ne durumda
        olduğunu yüzden.
        """
        if not self.yuzu_ciz:
            return
        kutu = self.yuz_kutusu()
        self.face.paint(painter, kutu.width(), kutu.topLeft())

    def yuz_kutusu(self) -> QRectF:
        """Yüzün gerçekten çizildiği kare.

        Dışarıya açık, çünkü maskotun elindeki nesneyi yerleştiren
        `sahne.py` yüzün nerede olduğunu bilmek zorunda. Eskiden bilmiyordu
        ve kendi hesabını yapıyordu: sütunun ortası. Halka sütundan dar
        olduğu için yüz merkezi 30'da, nesne merkezi 43'te kalıyordu —
        ölçtüm. Ekranda maskot bir yana, elindeki nesne öbür yana
        düşüyordu ve hiçbir şeyi tuttuğu okunmuyordu.

        Aynı sayıyı iki yerde hesaplamanın bedeli buydu. Artık tek yer
        burası.

        Yüz izin sağında ve üstte; ortalanmıyor çünkü altta nesne var.
        """
        alan = self.width() - TRACK_X - TRACK_W
        boyut = alan * getattr(self.face, "fill", 0.56)
        return QRectF(
            TRACK_X + TRACK_W + (alan - boyut) / 2, FACE_Y, boyut, boyut
        )


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
        """Genişlikte alt sınır **yok**.

        `sizeHint`i olduğu gibi döndürüyordum ve o genişliği en küçük
        genişlik sayılıyordu: kaydırma alanı içeriği viewport'a
        sığdıramıyor, döküm 640 piksele şişip metin sağdan kırpılıyordu.
        Ölçtüm — viewport 340, içerik 640.
        """
        return QSize(0, self.heightForWidth(self.width() or 320))

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
        self._giris: Giris | None = None
        self._shake = Shake()
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
        """`normal` ya da `hata`. Düşen adım kırmızıya dönüyor ve bir kez
        titriyor: kırmızı bir yazı okunmayı bekler, kımıldayan bir şey
        gözü kendine çeker."""
        self._tone = tone
        if tone == "hata":
            self._shake.hit(1.0)
            clock().subscribe(self._tick)
        self.update()

    def anime_et(self) -> None:
        """Satır aşağıdan kayarak geliyor. Birden beliren bir satır,
        akış hâlindeki bir dökümde gözün yerini kaybettiriyor."""
        self._giris = Giris()
        clock().subscribe(self._tick)

    def _tick(self, dt: float) -> None:
        if self._giris is not None:
            self._giris.step(dt)
            if self._giris.done:
                self._giris = None
        self._shake.step(dt)
        self.update()
        if self._giris is None and self._shake.resting:
            clock().unsubscribe(self._tick)

    def hideEvent(self, event) -> None:
        clock().unsubscribe(self._tick)
        super().hideEvent(event)

    def paintEvent(self, _event) -> None:
        t = self.t
        hata = self._tone == "hata"
        ana = t.critical if hata else t.accent
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._giris is not None:
            painter.setOpacity(self._giris.opacity)
            painter.translate(0, self._giris.offset)
        sars = self._shake.amount
        if sars:
            painter.translate(self._shake.step(0.0) * 3.0, 0)

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


class Giris:
    """Bir satırın geliş animasyonu.

    Satır aşağıdan hafifçe kayıp beliriyor. Amaç süs değil: dökümde
    satırlar akış hâlinde ekleniyor ve birden beliren bir satır, gözün
    yerini kaybetmesine yol açıyor. Kayarak gelen satır nereden geldiğini
    söylüyor.

    Gecikme yok: satırlar teker teker geliyor, kademelendirilecek bir
    grup yok. Olmayan bir gruba gecikme uydurmak, her satırı boşuna
    bekletmek olurdu.
    """

    SURE = 0.28
    KAYMA = 9.0

    def __init__(self) -> None:
        self._t = Tween(self.SURE, ease_out_expo)

    def step(self, dt: float) -> None:
        self._t.step(dt)

    @property
    def done(self) -> bool:
        return self._t.done

    @property
    def opacity(self) -> float:
        return self._t.value

    @property
    def offset(self) -> float:
        return (1.0 - self._t.value) * self.KAYMA


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
        if hasattr(w, "anime_et"):
            w.anime_et()
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
