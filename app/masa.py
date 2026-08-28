"""Ajanın masası — kendi masaüstünü canlı gösteren pencere.

Ajanın zaten kendi masaüstü var: `CreateDesktopW` ile açılmış, kendi
pencere listesi, kendi odak zinciri, kendi imleci olan gerçek bir Windows
masaüstü nesnesi. Sorun onu göremememizdi. `side_capture` yalnızca ajan
bir eylem yaptığında tek bir pencerenin karesini veriyordu; arada ekran
donuyordu ve "şu anda ne oluyor" sorusunun cevabı yoktu.

Bu pencere o boşluğu kapatıyor: saniyede sekiz kez bütün pencereleri
yakalayıp yerlerine koyuyor, üstünde ajanın imlecini geziyor.

## Neden Linux Mint gibi görünüyor

Berkay'ın istediği buydu ve isteğin altında bir sebep var: o masaüstü
Windows'un masaüstü **değil**. Aynı görünseydi bakan kişi hangi ekrana
baktığını karıştırırdı — kendi masaüstü mü, ajanınki mi. Başka bir
işletim sisteminin kabuğu, tek bakışta "burası başka bir yer" diyor.

Renkler ve ölçüler Mint-Y'ye **yaklaşıyor**, kopyalanmıyor: Mint'in duvar
kâğıtları, logosu ve simgeleri onların ve bu depoya giremez. Panel,
başlık çubuğu, yeşil vurgu ve duvar kâğıdı burada sıfırdan çiziliyor.
Yazı tipi de sistemin: Mint'in Ubuntu/Noto'su kurulu olmayan bir makinede
zorlanamaz.

## Neyi gösteriyor, neyi göstermiyor

Salt okunur. Pencerelerin üstüne tıklayamazsın, yazamazsın — kasıtlı,
Berkay öyle seçti. Bu yüzden başlık çubuklarında kapat/küçült düğmeleri
**yok**: çalışmayan bir düğme çizmek, çalışıyormuş gibi görünen bir yalan
olurdu. Yerine başlıkta ajanın o an hangi pencerede olduğu yazıyor —
bakan kişinin gerçekten sorduğu şey bu.

Paneldeki tek gerçek düğme duraklatma ve o gerçekten bir iş yapıyor:
yakalama saniyede 54 ms tutuyor ve bakmadığın sürece o payı ajanın kendi
işine bırakmak doğru.
"""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from backend.computer.canli import MasaKaresi, masayi_oku
from backend.computer.masaustu import IMLEC_BOY, IMLEC_OYUK, IMLEC_RENK

#: Panel yüksekliği. Mint'in Cinnamon paneli varsayılan 40; burada 38,
#: çünkü bizim pencere bir ekran değil ve panel oranı büyük görünüyor.
PANEL_H = 38

#: Başlık çubuğu yüksekliği — masaüstü ölçeğinden bağımsız, kendi
#: çerçevemiz olduğu için hep okunaklı kalıyor.
BASLIK_H = 26

#: Saniyede kaç kare. Ölçüm: tek pencere yakalaması 54 ms, yani tavan
#: ~18. Sekizde kalmak bilinçli — bu döngü ajanın kendi işiyle aynı
#: makinede dönüyor ve öncelik onun.
FPS = 8

# --- Mint'e yakın palet ----------------------------------------------------
#
# Kendi değerlerimiz. Mint-Y karanlık temasının izlenimini veriyor:
# nötr griler, tek bir yeşil vurgu, kontrastı düşük tutulmuş kenarlar.
PANEL = "#2b2b2b"
PANEL_UST = "#1d1d1d"
BASLIK_ETKIN = "#3c3c3c"
BASLIK_PASIF = "#333333"
CERCEVE = "#212121"
YAZI = "#dcdcdc"
YAZI_SOLUK = "#98a09a"
YESIL = "#7fb24a"
DUVAR_UST = "#1a2b1e"
DUVAR_ALT = "#0b110d"


class _Akis(QObject):
    """Yakalamayı kendi thread'inde döndürür.

    Arayüz thread'inde olamaz: bir kare 54 ms ve saniyede sekiz kare, yani
    arayüzün yarım saniyesi. Çubuk ve maskot o sırada donardı.

    Ajanın thread'inde de olamaz: orada ajanın kendi işi var ve canlı
    görüntü onu bekletemez.
    """

    kare = Signal(object)

    def __init__(self, kaynak) -> None:
        super().__init__()
        self._kaynak = kaynak
        self._calis = False
        self._thread: threading.Thread | None = None
        self._duraklat = False
        self.son_sure = 0.0

    def basla(self) -> None:
        if self._calis:
            return
        self._calis = True
        self._thread = threading.Thread(target=self._don, daemon=True,
                                        name="masa-canli")
        self._thread.start()

    def dur(self) -> None:
        self._calis = False

    def duraklat(self, deger: bool) -> None:
        self._duraklat = deger

    def _don(self) -> None:
        butce = 1.0 / FPS
        while self._calis:
            if self._duraklat:
                time.sleep(0.15)
                continue
            bas = time.perf_counter()
            try:
                kare = self._kaynak()
            except Exception:
                # Canlı görüntü uygulamayı düşüremez: ajan tam bu sırada
                # masaüstünü kapatmış olabilir.
                kare = None
            self.son_sure = time.perf_counter() - bas
            if kare is not None and self._calis:
                self.kare.emit(kare)
            time.sleep(max(0.0, butce - self.son_sure))


class MasaPenceresi(QWidget):
    """Ajanın masaüstü — Mint görünümlü kabuk, içinde gerçek pencereler."""

    def __init__(self, kaynak) -> None:
        super().__init__()
        self.setWindowTitle("Yan Masa — the agent's desk")
        self.resize(1180, 740)
        self.setMinimumSize(720, 460)
        self.setAutoFillBackground(False)

        self._kare = MasaKaresi()
        self._akis = _Akis(kaynak)
        self._akis.kare.connect(self._kare_geldi)
        self._duraklat = False
        self._duraklat_kutusu = QRect()
        self._kapali = False

        # Saat panelde gerçek saati gösteriyor. Duran bir saat, canlı
        # olduğunu iddia eden bir ekranda ilk fark edilen yalan olurdu.
        self._saat = QTimer(self)
        self._saat.timeout.connect(self.update)
        self._saat.start(1000)

    # --- yaşam döngüsü ----------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._akis.basla()

    def hideEvent(self, event) -> None:
        # Görünmeyen bir pencere için yakalama yapmak, ajanın işlemcisini
        # kimsenin bakmadığı bir görüntüye harcamak olurdu.
        self._akis.dur()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self._akis.dur()
        super().closeEvent(event)

    def _kare_geldi(self, kare: MasaKaresi) -> None:
        self._kare = kare
        self.update()

    def masa_kapandi(self) -> None:
        """Ajan yan alanı kapattı — pencere kalıyor ama bunu söylüyor."""
        self._kapali = True
        self._akis.dur()
        self.update()

    def masa_acildi(self) -> None:
        self._kapali = False
        if self.isVisible():
            self._akis.basla()

    # --- etkileşim --------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if self._duraklat_kutusu.contains(event.position().toPoint()):
            self._duraklat = not self._duraklat
            self._akis.duraklat(self._duraklat)
            self.update()

    # --- çizim ------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        masa = QRect(0, 0, self.width(), self.height() - PANEL_H)
        self._duvar(p, masa)

        olcek, ofset = self._olcek(masa)
        if self._kare.bos:
            self._bos_masa(p, masa)
        else:
            for pencere in self._kare.pencereler:
                self._pencere_ciz(p, pencere, olcek, ofset)
            self._imlec_ciz(p, olcek, ofset)

        self._panel(p)
        p.end()

    def _olcek(self, masa: QRect) -> tuple[float, QPointF]:
        """Masaüstünü pencereye sığdıran ölçek ve ortalama kayması."""
        en, boy = self._kare.alan
        if en <= 0 or boy <= 0:
            return 1.0, QPointF(0, 0)
        olcek = min(masa.width() / en, masa.height() / boy)
        return olcek, QPointF(
            (masa.width() - en * olcek) / 2,
            (masa.height() - boy * olcek) / 2,
        )

    def _duvar(self, p: QPainter, masa: QRect) -> None:
        """Duvar kâğıdı. Mint'in fotoğrafı değil, kendi çizimimiz.

        Mint'in duvar kâğıtları onların ve açık bir depoya konamaz. Buradaki
        yeşile çalan karanlık geçiş aynı izlenimi veriyor ve kimseye ait
        değil.
        """
        gecis = QLinearGradient(QPointF(0, masa.top()),
                                QPointF(masa.width() * 0.4, masa.bottom()))
        gecis.setColorAt(0.0, QColor(DUVAR_UST))
        gecis.setColorAt(1.0, QColor(DUVAR_ALT))
        p.fillRect(masa, gecis)

        # Sol üstten gelen yumuşak bir ışık: düz bir zemin ekranı ölü
        # gösteriyor, bir kaynak varmış gibi olması yeterli.
        isik = QRadialGradient(
            QPointF(masa.width() * 0.22, masa.height() * 0.18),
            max(masa.width(), masa.height()) * 0.75,
        )
        yesil = QColor(YESIL)
        yesil.setAlpha(26)
        isik.setColorAt(0.0, yesil)
        sonuk = QColor(YESIL)
        sonuk.setAlpha(0)
        isik.setColorAt(1.0, sonuk)
        p.fillRect(masa, isik)

    def _bos_masa(self, p: QPainter, masa: QRect) -> None:
        """Hiç pencere yokken ne olduğunu yazıyor.

        Boş bir duvar kâğıdı "bağlantı koptu" ile "ajan henüz bir şey
        açmadı"yı ayırt ettirmiyor. İkisi çok farklı ve ikisi de burada
        yazılı.
        """
        if self._kapali:
            baslik = "The desk is closed"
            alt = "The agent closed its workspace. It opens again on the next side_launch."
        else:
            baslik = "The desk is empty"
            alt = "Nothing has been launched here yet."
        f = QFont(self.font())
        f.setPointSizeF(15.0)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor(YAZI))
        kutu = QRect(masa.left(), masa.center().y() - 26, masa.width(), 30)
        p.drawText(kutu, Qt.AlignmentFlag.AlignCenter, baslik)
        f.setPointSizeF(10.5)
        f.setWeight(QFont.Weight.Normal)
        p.setFont(f)
        p.setPen(QColor(YAZI_SOLUK))
        p.drawText(QRect(masa.left(), kutu.bottom() + 2, masa.width(), 22),
                   Qt.AlignmentFlag.AlignCenter, alt)

    def _pencere_ciz(self, p: QPainter, pencere, olcek: float,
                     ofset: QPointF) -> None:
        en = max(1.0, pencere.en * olcek)
        boy = max(1.0, pencere.boy * olcek)
        x = ofset.x() + pencere.x * olcek
        y = ofset.y() + pencere.y * olcek
        govde = QRectF(x, y, en, boy)
        baslik = QRectF(x, y - BASLIK_H, en, BASLIK_H)
        etkin = pencere.hwnd == self._kare.etkin

        # Gölge: pencerelerin duvardan ayrılması gerekiyor, yoksa kare
        # duvar kâğıdının üstüne yapıştırılmış bir resim gibi duruyor.
        golge = QColor(0, 0, 0, 90)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(golge)
        p.drawRoundedRect(baslik.united(govde).adjusted(-1, 2, 3, 4), 7, 7)

        # Başlık çubuğu: üst köşeleri yuvarlak, altı düz.
        yol = QPainterPath()
        yol.moveTo(baslik.left(), baslik.bottom())
        yol.lineTo(baslik.left(), baslik.top() + 6)
        yol.quadTo(baslik.left(), baslik.top(), baslik.left() + 6, baslik.top())
        yol.lineTo(baslik.right() - 6, baslik.top())
        yol.quadTo(baslik.right(), baslik.top(), baslik.right(), baslik.top() + 6)
        yol.lineTo(baslik.right(), baslik.bottom())
        yol.closeSubpath()
        p.setBrush(QColor(BASLIK_ETKIN if etkin else BASLIK_PASIF))
        p.drawPath(yol)

        # İçerik. `QImage` ham baytı kopyalamıyor; `ham` kare nesnesinde
        # yaşadığı sürece geçerli ve kare `self._kare` içinde duruyor.
        gorsel = QImage(pencere.ham, pencere.en, pencere.boy,
                        pencere.en * 3, QImage.Format.Format_RGB888)
        p.drawImage(govde, gorsel)

        p.setPen(QPen(QColor(CERCEVE), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(govde)

        # Başlık yazısı ortada — Mint-Y'nin yaptığı bu. Rozet varken
        # yazının alanı ondan **önce** daraltılıyor: eliding tek başına
        # yetmiyor, ortalanmış bir yazı kısalsa da rozetin altına giriyor.
        # Ölçmeden önce öyleydi, "…Q6l2Y0here" diye üst üste bindi.
        rozet = self._rozet_eni() if etkin else 0.0
        alan = baslik.adjusted(8, 0, -(rozet + 8), 0)
        f = QFont(self.font())
        f.setPointSizeF(9.0)
        f.setWeight(QFont.Weight.DemiBold if etkin else QFont.Weight.Normal)
        p.setFont(f)
        p.setPen(QColor(YAZI if etkin else YAZI_SOLUK))
        yazi = QFontMetrics(f).elidedText(
            pencere.baslik or pencere.sinif, Qt.TextElideMode.ElideRight,
            max(20, int(alan.width())),
        )
        p.drawText(alan, Qt.AlignmentFlag.AlignCenter, yazi)

        if etkin:
            # Kapat/küçült düğmesi yok — salt okunur bir pencerede
            # çalışmayan bir düğme çizmek yalan olurdu. Yerine ajanın
            # burada olduğunu söyleyen bir işaret var.
            self._etkin_isareti(p, baslik)

    ROZET = "agent here"

    def _rozet_eni(self) -> float:
        f = QFont(self.font())
        f.setPointSizeF(8.0)
        return QFontMetrics(f).horizontalAdvance(self.ROZET) + 26

    def _etkin_isareti(self, p: QPainter, baslik: QRectF) -> None:
        f = QFont(self.font())
        f.setPointSizeF(8.0)
        p.setFont(f)
        metin = self.ROZET
        w = QFontMetrics(f).horizontalAdvance(metin)
        kutu = QRectF(baslik.right() - w - 26, baslik.center().y() - 8,
                      w + 18, 16)
        p.setPen(Qt.PenStyle.NoPen)
        yesil = QColor(YESIL)
        yesil.setAlpha(46)
        p.setBrush(yesil)
        p.drawRoundedRect(kutu, 8, 8)
        p.setBrush(QColor(YESIL))
        p.drawEllipse(QPointF(kutu.left() + 8, kutu.center().y()), 3.0, 3.0)
        p.setPen(QColor(YESIL))
        p.drawText(kutu.adjusted(14, 0, -4, 0),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   metin)

    def _imlec_ciz(self, p: QPainter, olcek: float, ofset: QPointF) -> None:
        """Ajanın imleci ve geldiği yol.

        İz kasıtlı ve `masaustu.py` ile aynı gerekçeyle: yalnızca ok "şu an
        neredeyim" der, iz "nereden geldim" der. Bir ajan yanlış yere
        tıkladığında ikincisi soruyu cevaplıyor.

        Ok **ölçeklenmiyor**: masaüstü küçültülerek gösteriliyor ve okla
        birlikte küçülen bir imleç üçte bir ölçekte kayboluyor. Gerçek bir
        imleç de ekran çözünürlüğüyle küçülmüyor.
        """
        def yerel(nokta: tuple[int, int]) -> QPointF:
            return QPointF(ofset.x() + nokta[0] * olcek,
                           ofset.y() + nokta[1] * olcek)

        iz = [yerel(n) for n in self._kare.iz]
        if len(iz) > 1:
            kalem = QPen(QColor(*IMLEC_RENK, 110), 2.0)
            kalem.setCapStyle(Qt.PenCapStyle.RoundCap)
            kalem.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(kalem)
            p.setBrush(Qt.BrushStyle.NoBrush)
            yol = QPainterPath(iz[0])
            for nokta in iz[1:]:
                yol.lineTo(nokta)
            p.drawPath(yol)

        uc = yerel(self._kare.imlec)
        if self._kare.tik:
            p.setPen(QPen(QColor(*IMLEC_RENK, 150), 2.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(uc, 11.0, 11.0)

        # Aynı siluet `masaustu.py`'deki oku izliyor: modele giden karede ve
        # burada iki farklı imleç görünmesi, ikisinin aynı şey olduğunu
        # gizlerdi.
        boy = float(IMLEC_BOY)
        silüet = [
            QPointF(uc.x(), uc.y()),
            QPointF(uc.x(), uc.y() + boy),
            QPointF(uc.x() + boy * 0.26, uc.y() + boy * 0.72),
            QPointF(uc.x() + boy * 0.42, uc.y() + boy * 1.04),
            QPointF(uc.x() + boy * 0.60, uc.y() + boy * 0.96),
            QPointF(uc.x() + boy * 0.44, uc.y() + boy * 0.66),
            QPointF(uc.x() + boy * 0.70, uc.y() + boy * 0.64),
        ]
        yol = QPainterPath(silüet[0])
        for nokta in silüet[1:]:
            yol.lineTo(nokta)
        yol.closeSubpath()
        p.setPen(QPen(QColor(*IMLEC_OYUK), 2.4))
        p.setBrush(QColor(*IMLEC_RENK))
        p.drawPath(yol)

    # --- panel ------------------------------------------------------------

    def _panel(self, p: QPainter) -> None:
        kutu = QRect(0, self.height() - PANEL_H, self.width(), PANEL_H)
        p.fillRect(kutu, QColor(PANEL))
        p.setPen(QPen(QColor(PANEL_UST), 1))
        p.drawLine(kutu.topLeft(), kutu.topRight())

        x = self._panel_mark(p, kutu)
        sag = self._panel_sag(p, kutu)
        self._panel_pencereler(p, kutu, x, sag)

    def _panel_mark(self, p: QPainter, kutu: QRect) -> int:
        """Panelin sol ucu: menü değil, kimlik.

        Mint'te burada menü düğmesi var. Bizde menü yok ve olmayan bir
        menünün düğmesini çizmek yalan olurdu; yerine masaüstü nesnesinin
        adı duruyor — o gerçekten var, `CreateDesktopW` ona verildi.
        """
        isaret = QRectF(10, kutu.center().y() - 9, 18, 18)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(YESIL))
        p.drawRoundedRect(isaret, 5, 5)
        p.setPen(QPen(QColor(PANEL), 1.6))
        for i in range(3):
            y = isaret.top() + 5.5 + i * 3.6
            p.drawLine(QPointF(isaret.left() + 4.5, y),
                       QPointF(isaret.right() - 4.5, y))

        f = QFont(self.font())
        f.setPointSizeF(9.5)
        p.setFont(f)
        p.setPen(QColor(YAZI))
        metin = "ajan-calisma"
        w = QFontMetrics(f).horizontalAdvance(metin)
        p.drawText(QRectF(isaret.right() + 8, kutu.top(), w + 4, PANEL_H),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   metin)
        return int(isaret.right() + 8 + w + 14)

    def _panel_sag(self, p: QPainter, kutu: QRect) -> int:
        """Saat, kare hızı ve duraklatma. Üçü de gerçek."""
        f = QFont(self.font())
        f.setPointSizeF(9.5)
        p.setFont(f)
        olcum = QFontMetrics(f)

        saat = time.strftime("%H:%M")
        w = olcum.horizontalAdvance(saat)
        p.setPen(QColor(YAZI))
        p.drawText(QRectF(self.width() - w - 14, kutu.top(), w, PANEL_H),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                   saat)
        x = self.width() - w - 24

        sure = self._akis.son_sure
        hiz = f"{min(FPS, 1 / sure):.0f} fps" if sure > 0.001 else "— fps"
        if self._duraklat:
            hiz = "paused"
        w2 = olcum.horizontalAdvance(hiz)
        p.setPen(QColor(YAZI_SOLUK))
        p.drawText(QRectF(x - w2, kutu.top(), w2, PANEL_H),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                   hiz)
        x -= w2 + 12

        dugme = QRectF(x - 26, kutu.center().y() - 11, 22, 22)
        self._duraklat_kutusu = dugme.toRect()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#383838"))
        p.drawRoundedRect(dugme, 5, 5)
        p.setBrush(QColor(YAZI))
        if self._duraklat:
            ucgen = QPainterPath(QPointF(dugme.center().x() - 3.5,
                                         dugme.center().y() - 5))
            ucgen.lineTo(dugme.center().x() + 5, dugme.center().y())
            ucgen.lineTo(dugme.center().x() - 3.5, dugme.center().y() + 5)
            ucgen.closeSubpath()
            p.drawPath(ucgen)
        else:
            for dx in (-3.5, 1.5):
                p.drawRect(QRectF(dugme.center().x() + dx,
                                  dugme.center().y() - 5, 2.6, 10))
        return int(dugme.left() - 12)

    def _panel_pencereler(self, p: QPainter, kutu: QRect, sol: int,
                          sag: int) -> None:
        """Pencere listesi. Mint'te bunlar düğme; burada etiket.

        Salt okunur bir görüntüde bir pencereyi öne getirmek gerçek
        z-sırasını yalanlamak olurdu — ekranda gördüğün sıra ajanın
        masaüstündeki sıra.
        """
        pencereler = list(reversed(self._kare.pencereler))
        if not pencereler or sag - sol < 80:
            return
        f = QFont(self.font())
        f.setPointSizeF(9.0)
        p.setFont(f)
        olcum = QFontMetrics(f)
        genislik = min(190, (sag - sol - 8) // len(pencereler))
        if genislik < 60:
            return
        x = sol
        for pencere in pencereler:
            etkin = pencere.hwnd == self._kare.etkin
            alan = QRectF(x, kutu.top() + 5, genislik - 6, PANEL_H - 10)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#343434" if etkin else "#2f2f2f"))
            p.drawRoundedRect(alan, 4, 4)
            if etkin:
                p.setBrush(QColor(YESIL))
                p.drawRoundedRect(
                    QRectF(alan.left(), alan.top(), 2.5, alan.height()), 1, 1
                )
            p.setPen(QColor(YAZI if etkin else YAZI_SOLUK))
            p.drawText(
                alan.adjusted(10, 0, -6, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                olcum.elidedText(pencere.baslik or pencere.sinif,
                                 Qt.TextElideMode.ElideRight,
                                 int(alan.width()) - 18),
            )
            x += genislik


def masa_kaynagi(dispatcher):
    """Arayüzün her karede çağıracağı okuyucu.

    Dispatcher'a doğrudan bağlanmak yerine bir kapanış veriliyor: ajan
    kurulamamışsa da pencere açılabiliyor ve boş masayı gösteriyor.
    """
    def oku() -> MasaKaresi:
        alan = (1920, 1080)
        try:
            ekran = dispatcher.active
            alan = (ekran.width, ekran.height)
        except Exception:
            # Ajan kurulamamışsa masaüstü ölçüsü de yok; varsayılan kalıyor
            # ve pencere boş masayı gösteriyor.
            pass
        return masayi_oku(
            getattr(dispatcher, "side", None),
            getattr(dispatcher, "side_input", None),
            alan=alan,
            etkin=getattr(dispatcher, "last_side_hwnd", 0),
        )
    return oku
