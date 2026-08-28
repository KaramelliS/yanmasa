"""Maskotun konuşma baloncuğu: o an ne yaptığını yazıyor.

Bundan önce maskotun elinde nesneler vardı — dizüstü, mercek, sayfa,
sunucu — ve her biri çalışma anında kol, el, tutuş noktası hesaplayan bir
kompozisyondu. Altı tur uğraştım ve hiçbiri iyi olmadı: 78 pikselde bir
kol iki piksel, bir kalem bir piksel ediyor. Berkay'ın çözümü doğru
olandı: nesneyi çizmeye çalışmayı bırak, **yazıyla söyle**.

Bir baloncuk, iki nedenden ötürü çizilen nesneden iyi:

- **Belirsizlik yok.** Bir dizüstü çizimi "ofis işi" diyebilir; "notlar.md
  yazıyor" tam olarak ne yaptığını söylüyor. Simge yaklaşıklıktır, yazı
  değildir.
- **Ölçekten bağımsız.** Yazı 11 puntoda okunuyor; iki piksellik bir kol
  hiçbir puntoda okunmuyor.

## Yazı akıyor

Harfler tek tek düşüyor ve sonunda bir imleç yanıp sönüyor. Metnin
tamamını bir anda basmak da olurdu ve bir şey kaybederdi: akan yazı
"şu an oluyor" der, duran yazı "oldu" der. Ajan çalışırken doğru olan
birincisi.

Yeni bir iş geldiğinde eski yazı silinmiyor, **üstüne yazılıyor**: ortak
ön ek korunup gerisi değişiyor. "Dosya yazıyor: a.md" ile "Dosya yazıyor:
b.md" arasında baloncuk tamamen boşalıp yeniden dolsaydı, gözün takip
ettiği şey iş değil animasyon olurdu.

Baloncuğun **yüksekliği tam metinden**, çizimi görünen harflerden
hesaplanıyor. İkisini de görünen harflerden alsaydım satır kırılımı harf
sayısıyla oynardı: kelime bir satır aşağı atlayıp geri gelirdi ve
baloncuk yazarken titrerdi.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QTextLayout,
    QTextOption,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from shiboken6 import isValid

from .fluent import Tokens, _blend
from .motion import Spring, clock

#: Baloncuğun iç boşluğu ve köşe yarıçapı.
PAY_X, PAY_Y, YARICAP = 11.0, 8.0, 11.0

#: Kuyruğun boyu ve yüksekliği. Sola, maskota doğru bakıyor.
KUYRUK_EN, KUYRUK_BOY = 7.0, 12.0

#: Kuyruğun üstten uzaklığı. Maskotun yüzü sütunun üstünde duruyor ve
#: kuyruk ona bakmalı; ortadan çıkan bir kuyruk boşluğu işaret ediyor.
KUYRUK_Y = 17.0

#: Saniyede düşen harf. 42'de yazı okunacak hızda akıyor; 90'da göz
#: takip etmeye çalışmayı bırakıp bekliyor ve akıntının anlamı kalmıyor.
HARF_HIZ = 42.0

#: İmlecin yanıp sönme dönemi.
IMLEC_DONEM = 1.0

#: En fazla iki satır. Üçüncü satır çubuğu büyütüyor ve baloncuk
#: cevabın yerini yemeye başlıyor.
SATIR_SINIR = 2

#: Giriş yayı: baloncuk maskottan doğuyor.
GIRIS_K, GIRIS_D = 210.0, 17.0


class Baloncuk(QWidget):
    """Maskotun yanında beliren, yazısı akan baloncuk."""

    def __init__(self, t: Tokens) -> None:
        super().__init__()
        self.t = t
        self._tam = ""
        self._kirpik = ""
        self._kirp_anahtar = (None, None)
        self._gorunen = 0.0
        self._gecen = 0.0
        # Giriş: 0 kapalı, 1 açık. Yay, çünkü baloncuk maskottan doğuyor
        # ve doğan bir şey yerine oturur, belirip durmaz.
        self._giris = Spring(0.0, stiffness=GIRIS_K, damping=GIRIS_D)
        self._abone = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    # --- durum ------------------------------------------------------------

    def soyle(self, metin: str) -> None:
        """Yeni bir iş: baloncuk bunu yazmaya başlıyor.

        Ortak ön ek korunuyor. "Dosya yazıyor: a.md" ile "Dosya yazıyor:
        b.md" arasında baloncuk tamamen boşalıp yeniden dolsaydı, gözün
        takip ettiği şey iş değil animasyon olurdu.
        """
        metin = (metin or "").strip()
        if not metin:
            self.sakla()
            return
        if metin == self._tam:
            return
        ortak = 0
        for a, b in zip(self._tam, metin):
            if a != b:
                break
            ortak += 1
        self._tam = metin
        self._gorunen = min(self._gorunen, float(ortak))
        self._giris.to(1.0)
        self._dinle(True)
        self.updateGeometry()
        self.update()

    def sakla(self) -> None:
        """İş bitti: baloncuk kapanıyor ve yerini dökümene geri veriyor."""
        self._giris.to(0.0)
        self.updateGeometry()
        self.update()

    def temizle(self) -> None:
        self._tam = ""
        self._kirpik = ""
        self._kirp_anahtar = (None, None)
        self._gorunen = 0.0
        self._giris.jump(0.0)
        self._dinle(False)
        self.updateGeometry()

    @property
    def akiyor(self) -> bool:
        return self._gorunen < len(self._gosterim())

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
        if self._tam and self._giris.target > 0.0:
            self._dinle(True)

    def _tick(self, dt: float) -> None:
        if not isValid(self):
            # Qt C++ tarafını sildi ama Python sarmalayıcı yaşıyor. İkinci
            # katman: abonelik yine de sızarsa ölü nesneye dokunmuyoruz.
            clock().unsubscribe(self._tick)
            return
        self._gecen += dt
        self._giris.step(dt)
        if self.akiyor:
            self._gorunen = min(float(len(self._gosterim())),
                                self._gorunen + HARF_HIZ * dt)
        if self._giris.value < 0.01 and self._giris.target == 0.0:
            # Kapandı: kareyi boşuna ilerletmiyoruz. Görünürlük ya da
            # geometri **burada** değiştirilmiyor.
            self._dinle(False)
            return
        self.update()

    # --- ölçü -------------------------------------------------------------

    def _yazi(self) -> QFont:
        f = QFont(self.font())
        f.setPointSizeF(11.0)
        return f

    def _duzen(self, en: float, metin: str | None = None) -> QTextLayout:
        duzen = QTextLayout(self._tam if metin is None else metin, self._yazi())
        secenek = QTextOption()
        secenek.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        duzen.setTextOption(secenek)
        duzen.beginLayout()
        y = 0.0
        while True:
            satir = duzen.createLine()
            if not satir.isValid():
                break
            satir.setLineWidth(en)
            satir.setPosition(QPointF(0.0, y))
            y += satir.height()
            if duzen.lineCount() >= SATIR_SINIR:
                break
        duzen.endLayout()
        return duzen

    def _kirp(self, en: float) -> str:
        """İki satıra sığmayanı üç noktayla kesiyor.

        Kesmezsem `QTextLayout` fazlasını sessizce düşürüyor ve imleç
        ikinci satırın sonunda yanıp sönüyor: baloncuk yazının bittiğini
        söylüyor, oysa yolun ortasında kesilmiş. Uzun bir dosya yolunda
        tam olarak bu oluyor. Üç nokta "devamı var" diyor.
        """
        duzen = self._duzen(en, self._tam)
        if not duzen.lineCount():
            return self._tam
        son = duzen.lineAt(duzen.lineCount() - 1)
        sinir = son.textStart() + son.textLength()
        if sinir >= len(self._tam):
            return self._tam
        return self._tam[:max(1, sinir - 1)].rstrip() + "…"

    def _gosterim(self) -> str:
        """Kırpılmış metin. Ölçü her karede yeniden yapılmıyor."""
        anahtar = (self._tam, round(self._ic_en()))
        if anahtar != self._kirp_anahtar:
            self._kirp_anahtar = anahtar
            self._kirpik = self._kirp(anahtar[1])
        return self._kirpik

    def _ic_en(self) -> float:
        return max(40.0, self.width() - PAY_X * 2 - KUYRUK_EN)

    def _govde(self, duzen: QTextLayout) -> QRectF:
        """Gövde dikdörtgeni: **eni yazıdan**, boyu satırlardan.

        Baloncuk sütunun tamamını kaplarsa konuşma gibi durmuyor, devre
        dışı bir metin alanı gibi duruyor: "Klasöre bakıyor" 340 pikselin
        solunda tek başına kalıyor. Bir baloncuk yazısına yapışır.

        Ölçü **tam metinden** alınıyor, görünenden değil. Görünenden
        alsaydım harfler düşerken baloncuk sağa doğru büyürdü; kuyruk
        sabit dururken sağ kenarın sürüklenmesi yazıyı okunmaz yapıyor.
        """
        en = 0.0
        for i in range(duzen.lineCount()):
            en = max(en, duzen.lineAt(i).naturalTextWidth())
        en = min(en + PAY_X * 2, max(1.0, self.width() - KUYRUK_EN))
        return QRectF(KUYRUK_EN, 0.0, max(2 * YARICAP, en),
                      duzen.boundingRect().height() + PAY_Y * 2)

    def sizeHint(self):
        """Konuşmuyorken **sıfır** yükseklik.

        Görünürlüğü açıp kapatmak yerine yükseklik sıfıra iniyor.
        `setVisible`i saat geri çağrısından çağırmak Qt'yi özyinelemeli
        boyamaya sokuyor ve süreci düşürüyor; ertelenmiş bir çağrı da ölü
        nesnede patlıyor. İkisini de yaşadım. Yer kaplamayan bir widget
        aynı sonucu veriyor ve hiçbir yaşam döngüsü sorunu doğurmuyor.
        """
        if not self._tam or self._giris.target == 0.0:
            return QSize(0, 0)
        duzen = self._duzen(self._ic_en(), self._gosterim())
        boy = duzen.boundingRect().height() + PAY_Y * 2
        return QSize(self.width() or 200, int(boy + 4))

    def minimumSizeHint(self):
        return self.sizeHint()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.updateGeometry()

    # --- çizim ------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        if not self._tam:
            return
        k = max(0.0, min(1.0, self._giris.value))
        if k < 0.01:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Yükseklik tam metinden: yazarken baloncuk büyümüyor.
        yazi = self._gosterim()
        tam = self._duzen(self._ic_en(), yazi)
        gorunen = self._duzen(self._ic_en(), yazi[:int(self._gorunen)])
        govde = self._govde(tam)

        # Baloncuk maskottan doğuyor: kuyruğun dibinden büyüyor, ortadan
        # değil. Ortadan büyüyen bir baloncuk maskotla ilgisiz görünüyor.
        p.save()
        p.translate(0.0, KUYRUK_Y)
        p.scale(k, k)
        p.translate(0.0, -KUYRUK_Y)
        p.setOpacity(k)

        yol = QPainterPath()
        yol.addRoundedRect(govde, YARICAP, YARICAP)
        kuyruk = QPainterPath()
        kuyruk.moveTo(QPointF(govde.left(), KUYRUK_Y - KUYRUK_BOY / 2))
        kuyruk.lineTo(QPointF(0.0, KUYRUK_Y))
        kuyruk.lineTo(QPointF(govde.left(), KUYRUK_Y + KUYRUK_BOY / 2))
        kuyruk.closeSubpath()
        yol = yol.united(kuyruk)

        p.setPen(Qt.PenStyle.NoPen)
        # Vurgunun kısılmış hâli: baloncuk kartın üstünde ayrı bir yüzey
        # olmalı ama cevabın önüne geçmemeli.
        p.setBrush(QColor(_blend(self.t.accent, 0.16, self.t.layer)))
        p.drawPath(yol)

        p.setPen(QColor(self.t.text))
        p.translate(govde.left() + PAY_X, PAY_Y)
        gorunen.draw(p, QPointF(0.0, 0.0))
        self._imleci_ciz(p, gorunen)
        p.restore()
        p.end()

    def _imleci_ciz(self, p: QPainter, duzen: QTextLayout) -> None:
        """Yazının ucunda yanıp sönen imleç.

        Akış bitince yanıp sönmeye başlıyor; akarken sabit duruyor. Ters
        olsaydı yanıp sönen imleç "devam ediyor" derdi ve yazı durmuşken
        yanlış söylerdi.
        """
        if not self.akiyor and (self._gecen % IMLEC_DONEM) > 0.55:
            return
        if not duzen.lineCount():
            return
        satir = duzen.lineAt(duzen.lineCount() - 1)
        x = satir.naturalTextWidth()
        p.setBrush(QColor(self.t.accent))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(x + 1.5, satir.y() + 2.0, 1.6,
                          satir.height() - 4.0))
