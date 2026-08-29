"""Sol ray ve sayfa başlığı — uygulamanın gezinme iskeleti.

Önce her şey `QDockWidget`'tı: belge, terminal, kod, sunucu, yetenek
panelleri ana pencerenin kenarlarına yapışıyor, birbirleriyle sekmeleniyor
ve büyüdükçe ortada ne olduğu belirsizleşiyordu. Bir dock'un iki hâli var
— yapışık ve yüzen — ve ikisi arasında pencere kendi kendine yeniden
düzenleniyor; ajan üç belge açtığında ekranda ne olduğunu kimse
söyleyemiyordu.

Şimdi tek bir şey var: **sayfalar**. Solda dar bir ray, her sayfa bir
çizim ve bir etiket. Etkin olanın yanında vurgu çubuğu. İçerik hep aynı
yerde, hep tam genişlikte.

## Neyi kaybettik

Dock'ların bir özelliği gerçekten iyiydi: başlığa çift tıklayınca panel
ayrı bir Windows penceresine çıkıyor ve ikinci ekrana atılabiliyordu. O
Qt'nin bedava verdiği bir davranıştı ve sayfalarla gitti. Berkay bunu
bilerek seçti; yerine bir gün "ayrı pencereye çıkar" düğmesi elle
yazılabilir.

## Ray etiketi kısa, başlık uzun

Raydaki etiket 76 pikselde okunmak zorunda, yani `butce.xlsx · sheet
(1 unsaved)` oraya sığmıyor. Sayfanın kendi başlığı tam metni taşıyor.
İkisini de raya sığdırmaya çalışmak, ikisini de okunmaz yapardı.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .fluent import Tokens, _blend as _yikama
from .glyphs import paint_glyph

#: Rayın eni. 76'da çizim ve iki kelimelik bir etiket birlikte duruyor;
#: 64'te etiket kırpılmaya başlıyor, 88'de içerikten boşuna yer alıyor.
RAY_EN = 76

#: Bir ray ögesinin yüksekliği.
OGE_H = 66

#: Çizimin oturduğu karo ve çizimin kendisi.
#:
#: Çizim doğrudan zemine konunca 22 pikselde dolu bir lekeye dönüşüyordu —
#: ölçtüm, rayda pembe kutular çıktı. Karo hem kontrast veriyor hem de
#: akıştaki adım satırlarıyla aynı dili konuşuyor: orada da çizim küçük
#: yuvarlak bir karonun içinde duruyor.
KARO = 34
CIZIM = 18

#: Etkin sayfanın yanındaki vurgu çubuğu.
VURGU_EN, VURGU_BOY = 3.0, 26.0


@dataclass
class Oge:
    anahtar: str
    etiket: str
    cizim: str
    #: Sabit sayfalar kapanmıyor: akış ve masa her zaman orada.
    kapatilabilir: bool = True


class Ray(QWidget):
    """Soldaki dikey sayfa rayı."""

    secildi = Signal(str)

    def __init__(self, t: Tokens) -> None:
        super().__init__()
        self.t = t
        self.setFixedWidth(RAY_EN)
        self.setMouseTracking(True)
        self._ogeler: list[Oge] = []
        self._etkin = ""
        self._uzerinde = -1
        #: Sabitlerle dinamikler arasındaki ayraç bu sayıda ögeden sonra.
        self._sabit_sayisi = 0

    # --- içerik -----------------------------------------------------------

    def ekle(self, oge: Oge) -> None:
        if any(o.anahtar == oge.anahtar for o in self._ogeler):
            return
        self._ogeler.append(oge)
        if not oge.kapatilabilir:
            self._sabit_sayisi = sum(
                1 for o in self._ogeler if not o.kapatilabilir
            )
        self.update()

    def cikar(self, anahtar: str) -> None:
        self._ogeler = [o for o in self._ogeler if o.anahtar != anahtar]
        self.update()

    def etiketle(self, anahtar: str, etiket: str) -> None:
        for o in self._ogeler:
            if o.anahtar == anahtar:
                o.etiket = etiket
                self.update()
                return

    def sec(self, anahtar: str) -> None:
        if anahtar != self._etkin:
            self._etkin = anahtar
            self.update()

    @property
    def etkin(self) -> str:
        return self._etkin

    def anahtarlar(self) -> list[str]:
        return [o.anahtar for o in self._ogeler]

    # --- fare -------------------------------------------------------------

    def _indeks(self, y: float) -> int:
        i = int(y // OGE_H)
        return i if 0 <= i < len(self._ogeler) else -1

    def mouseMoveEvent(self, event) -> None:
        i = self._indeks(event.position().y())
        if i != self._uzerinde:
            self._uzerinde = i
            self.setCursor(Qt.CursorShape.PointingHandCursor if i >= 0
                           else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, event) -> None:
        self._uzerinde = -1
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        i = self._indeks(event.position().y())
        if i >= 0 and event.button() == Qt.MouseButton.LeftButton:
            self.secildi.emit(self._ogeler[i].anahtar)

    # --- çizim ------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        t = self.t
        p.fillRect(self.rect(), QColor(t.background_secondary))
        p.setPen(QPen(QColor(t.divider), 1))
        p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())

        f = QFont(self.font())
        f.setPointSizeF(8.5)
        olcum = QFontMetrics(f)

        for i, oge in enumerate(self._ogeler):
            ust = i * OGE_H
            kutu = QRectF(0, ust, self.width() - 1, OGE_H)
            etkin = oge.anahtar == self._etkin
            uzerinde = i == self._uzerinde

            if etkin:
                # `subtle_hover` ile `control` bu temada aynı değer
                # (#2d2d2d): seçili satırı onunla boyamak, üstüne gelinen
                # satırdan ayırt edilemez yapıyordu. Vurgunun kısılmış
                # hâli seçimi tek bakışta söylüyor.
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(
                    _yikama(t.accent, 0.10, t.background_secondary)
                ))
                p.drawRect(kutu)
            elif uzerinde:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(t.control))
                p.drawRect(kutu)

            if etkin:
                p.setBrush(QColor(t.accent))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(
                    QRectF(0, kutu.center().y() - VURGU_BOY / 2,
                           VURGU_EN, VURGU_BOY),
                    1.5, 1.5,
                )

            # Çizimin iki rengi var — gövde ve sap — ve ikisini aynı
            # vermek onu dolu bir lekeye çeviriyor. Ölçtüm: rayda pembe
            # kutular çıktı, simge okunmuyordu.
            renk = t.text if etkin else (
                t.text_secondary if uzerinde else t.text_tertiary
            )
            ana = t.accent if etkin else (
                t.accent_text if uzerinde else t.text_secondary
            )
            karo = QRectF(kutu.center().x() - KARO / 2, ust + 8, KARO, KARO)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(_yikama(t.accent, 0.20, t.background_secondary)
                              if etkin else t.control))
            p.drawRoundedRect(karo, 9, 9)
            paint_glyph(
                p, oge.cizim, CIZIM, ana, renk,
                QPointF(karo.center().x() - CIZIM / 2,
                        karo.center().y() - CIZIM / 2),
            )

            p.setFont(f)
            p.setPen(QColor(renk))
            p.drawText(
                QRectF(2, ust + 44, self.width() - 5, 14),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                olcum.elidedText(oge.etiket, Qt.TextElideMode.ElideRight,
                                 self.width() - 10),
            )

            # Sabit sayfalarla ajanın açtıkları arasında bir ayraç: ilk
            # ikisi hep orada, altındakiler gelip gidiyor ve bu iki farklı
            # şey olduğunu göstermek listeyi okunur yapıyor.
            if (i + 1) == self._sabit_sayisi and i + 1 < len(self._ogeler):
                p.setPen(QPen(QColor(
                    _yikama(t.text, 0.16, t.background_secondary)), 1))
                p.drawLine(QPointF(14, ust + OGE_H),
                           QPointF(self.width() - 15, ust + OGE_H))
        p.end()

    def sizeHint(self):
        from PySide6.QtCore import QSize

        return QSize(RAY_EN, max(1, len(self._ogeler)) * OGE_H)


class SayfaBasligi(QWidget):
    """Sayfanın üstündeki ince başlık şeridi.

    Dock'ların başlık çubuğu gitti ve tam başlık onunla birlikte gidiyordu:
    raydaki etiket 76 piksellik ve `butce.xlsx · sheet (1 unsaved)` oraya
    sığmıyor. Buradaki şerit tam metni taşıyor.
    """

    kapatildi = Signal()

    def __init__(self, t: Tokens, baslik: str,
                 kapatilabilir: bool = True) -> None:
        super().__init__()
        self.t = t
        self.setFixedHeight(34)
        duzen = QHBoxLayout(self)
        duzen.setContentsMargins(16, 0, 8, 0)
        duzen.setSpacing(8)

        self._etiket = QLabel(baslik)
        self._etiket.setStyleSheet(
            f"color: {t.text_secondary}; font-size: 12px;"
        )
        duzen.addWidget(self._etiket, 1)

        if kapatilabilir:
            self._kapat = _KapatDugmesi(t)
            self._kapat.clicked.connect(self.kapatildi.emit)
            duzen.addWidget(self._kapat)

    def set_baslik(self, baslik: str) -> None:
        self._etiket.setText(baslik)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(self.t.background))
        p.setPen(QPen(QColor(self.t.divider), 1))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.end()


class _KapatDugmesi(QWidget):
    """Sayfayı kapatan çarpı. Gerçekten kapatıyor."""

    clicked = Signal()

    def __init__(self, t: Tokens) -> None:
        super().__init__()
        self.t = t
        self.setFixedSize(24, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._uzerinde = False

    def enterEvent(self, event) -> None:
        self._uzerinde = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._uzerinde = False
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._uzerinde:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(self.t.control_hover))
            p.drawRoundedRect(QRectF(0, 0, 24, 24), 5, 5)
        renk = self.t.text if self._uzerinde else self.t.text_tertiary
        kalem = QPen(QColor(renk), 1.4)
        kalem.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(kalem)
        p.drawLine(QPointF(8.5, 8.5), QPointF(15.5, 15.5))
        p.drawLine(QPointF(15.5, 8.5), QPointF(8.5, 15.5))
        p.end()


class Sayfa(QWidget):
    """Başlık şeridi + gövde.

    Bir sayfa başlıksız da olabiliyor ve bunun tek kullanıcısı masa: onun
    kendi paneli zaten bir başlık şeridi. İkisini üst üste koymak, aynı
    işi yapan iki çubuk demekti.
    """

    def __init__(self, t: Tokens, baslik: str, govde: QWidget,
                 kapatilabilir: bool = True, basliksiz: bool = False) -> None:
        super().__init__()
        duzen = QVBoxLayout(self)
        duzen.setContentsMargins(0, 0, 0, 0)
        duzen.setSpacing(0)
        self.baslik = None if basliksiz else SayfaBasligi(
            t, baslik, kapatilabilir
        )
        if self.baslik is not None:
            duzen.addWidget(self.baslik)
        self.govde = govde
        duzen.addWidget(govde, 1)

    def set_govde(self, govde: QWidget) -> None:
        if govde is self.govde:
            return
        duzen = self.layout()
        duzen.removeWidget(self.govde)
        self.govde.setParent(None)
        self.govde = govde
        duzen.addWidget(govde, 1)
