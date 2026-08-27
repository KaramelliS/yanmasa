"""Maskot sütunu: gövde, elleri ve elindeki nesne.

Sahne önce çubuğun **üstünde** bir şeritti ve yanlıştı: bir iş
başlayınca cevap alanını aşağı itiyor, okuduğun yer kayıyordu. Artık
solda dar bir sütun — döküm sağında akıyor, hiçbir şey yer değiştirmiyor
ve maskot her zaman orada, boşta da nefes alıyor.

**Sahnenin tamamı tek çizim.** Kol, el ve nesne `varliklar/svg/sahne-*.svg`
içinde aynı koordinat sisteminde duruyor ve `scripts/sahne_svg.py`
üretiyor. Önceki hâl parçaları çalışma anında yan yana koyuyordu —
gövdeyi bir yer, kolları bir formül, elleri başka bir sabit — ve monte
edilmiş görünüyordu. Kollar bir turda pelerine, bir turda kulağa döndü;
her düzeltme bir sonrakini doğurdu. Sebep şuydu: kimse sahneyi bir bütün
olarak çizmiyordu.

Yüz bu dosyaya gömülü **değil**: canlı, nefes alıyor ve nesneye bakıyor.
SVG bir `yuva` bırakıyor, yüz oraya çiziliyor, kolların üst uçları
yuvanın içinde başlıyor. Gövde onların üstüne geldiği için ek yeri
görünmüyor — tek silüet.

Nesnenin gelişi yay: aşağıdan gelip ellerine oturuyor. Birden belirip
birden kaybolan bir şey, gözün onu fark etmesine fırsat bırakmıyor.
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget

from .fluent import Tokens
from .motion import Spring, clock

SVG_DIZIN = Path(__file__).resolve().parent.parent / "varliklar" / "svg"

YER_GOVDE = "#E7BABD"
YER_OYUK = "#1C1C1C"
#: Kol ve elin yer tutucusu — yükleme anında gövdenin rengiyle değişiyor.
YER_TEN = "#C9A0A3"

#: Sahnelerin çizim sırası. `scripts/sahne_svg.py` ile birebir aynı ve
#: bir test bunu doğruluyor — iki liste ayrı düşerse maskotun bir parçası
#: sessizce kaybolur.
#:
#: `--yuz--` yüzün araya girdiği yer. Yüz SVG'de değil çünkü canlı;
#: sıradaki yeri burada.
PARCALAR = {
    "mercek": ["--yuz--", "sap", "cam-halka", "cam", "parilti",
               "kol-yakin", "el-yakin"],
    "laptop": ["kol-uzak", "el-uzak", "--yuz--", "ekran", "taban",
               "tus-1", "tus-2", "kol-yakin", "el-yakin"],
    "terminal": ["--yuz--", "pencere", "nokta-1", "nokta-2", "istem",
                 "imlec"],
    "sayfa": ["kol-yakin", "--yuz--", "kagit", "sirt", "kalem",
              "el-yakin"],
    "sunucu": ["kablo", "--yuz--", "raf-ust", "yuva-ust", "isik-ust",
               "raf-alt", "yuva-alt", "isik-alt", "kivilcim"],
}

#: Yüzün yerini tutan kimlik.
YUZ = "--yuz--"

#: Hangi sahnede yandan bakılıyor. Terminalde bize dönük duruyor —
#: Berkay'ın isteği ve doğrusu: eli görünmeyen biri yazıyorsa bunu
#: anlatan tek şey yüzü.
PROFIL = {"mercek": True, "laptop": True, "terminal": False,
          "sayfa": True, "sunucu": False}

#: Sahne başına bakış. Büyüteçte bakış ileri: maskot merceğe bakmıyor,
#: onun **içinden** bakıyor.
BAKIS = {
    "mercek": (0.0, -0.05),
    "laptop": (0.45, 0.35),
    "terminal": (0.0, 0.7),
    "sayfa": (0.5, 0.3),
    "sunucu": (0.35, 0.15),
}

#: Araçtan nesneye. Karşılığı olmayan araçta nesne çıkmıyor — her işe
#: bir nesne uydurmak, nesnelerin anlamını yok ederdi.
ARAC_NESNE = {
    "office_open": "laptop", "office_read": "laptop", "office_edit": "laptop",
    "office_write": "laptop", "office_save": "laptop", "office_close": "laptop",
    "office_history": "laptop",
    "run_shell": "terminal", "terminal_open": "terminal",
    "terminal_send": "terminal", "terminal_read": "terminal",
    "terminal_close": "terminal", "remote_run": "terminal",
    "screenshot": "mercek", "zoom": "mercek", "read_ui_tree": "mercek",
    "switch_display": "mercek",
    "remote_connect": "sunucu", "remote_list": "sunucu",
    "remote_read": "sunucu", "remote_write": "sunucu",
    "write_file": "sayfa", "write_files": "sayfa", "read_file": "sayfa",
    "edit_file": "sayfa", "list_dir": "sayfa", "skill_write": "sayfa",
}

#: Tuşlara basılan işler. Mercek tutuluyor, tuşa basılmıyor.
TUSLU = {"laptop", "terminal", "sayfa"}

#: Sahne SVG'sinin çizim alanı. `scripts/sahne_svg.py` ile aynı.
VB_EN, VB_BOY = 96.0, 62.0

#: Sahne izin sağında kalıyor, üstünde değil.
IZ_PAY = 8

#: Sütunun eni. 88'de sağda boşluk kalıyordu.
GENISLIK = 78

#: Sütunun boyu: sahnenin oranı 96x92 ve en 70 kalıyor.
YUKSEKLIK = 48

#: Nesne gelirken bu kadar yukarı çıkıyor. 12'ydi ve kolların gövdeye
#: girdiği yer açılıyordu — ek yeri görünen bir kol, kol değil yapıştırma.
GELIS_YOL = 6.0

#: Yüzün oturduğu yuvanın kimliği ve kolların kimlikleri.
YUVA = "yuva"


def _renkli(ad: str, t: Tokens, ten: str) -> QSvgRenderer | None:
    yol = SVG_DIZIN / f"sahne-{ad}.svg"
    if not yol.is_file():
        return None
    metin = yol.read_text(encoding="utf-8")
    metin = (metin.replace(YER_TEN, ten)
                  .replace(YER_GOVDE, t.accent)
                  .replace(YER_OYUK, t.background))
    return QSvgRenderer(QByteArray(metin.encode("utf-8")))


def nesneler_var() -> bool:
    return (SVG_DIZIN / "sahne-laptop.svg").is_file()


class Sahne(QWidget):
    """Maskot sütunu: halka, gövde, eller, elindeki nesne."""

    def __init__(self, t: Tokens, halka: QWidget) -> None:
        super().__init__()
        self.t = t
        # Halka sütunun çocuğu. Yüzü ilerleten tek yer halka; sahne de
        # ilerletseydi yüz iki kat hızlı oynardı.
        self.halka = halka
        self.halka.setParent(self)
        # Yüzü halka değil sahne çiziyor. Halka bir çocuk pencere ve
        # çocuklar ebeveynden **sonra** boyanıyor; yüzü orada bıraksaydık
        # her zaman nesnenin önünde kalırdı ve maskot nesneyi tutmuyor,
        # önüne geçmiş görünürdü.
        self.halka.yuzu_ciz = False
        self.yuz = getattr(halka, "face", halka)
        # Sütun yalnızca maskotun boyu kadar. Dökümle aynı boya
        # zorlandığında altında doksan piksellik boşluk kalıyordu —
        # ölçtüm: 88x170'in yarısı boştu.
        self.setFixedSize(GENISLIK, YUKSEKLIK)

        self._ciziciler: dict[str, QSvgRenderer] = {}
        self._nesne: str | None = None
        self._giden: str | None = None
        self._gelis = Spring(0.0, stiffness=170.0, damping=15.0)
        self._gecen = 0.0
        self._abone = False

    # --- durum ------------------------------------------------------------

    def set_tool(self, tool: str) -> None:
        """Araç değişti: elindeki nesne de değişiyor.

        Aynı nesne devam ediyorsa sahne bozulmuyor — her adımda nesneyi
        yeniden getirmek, dosya yazan bir turda sayfanın sürekli elinden
        düşüp geri gelmesi olurdu.
        """
        yeni = ARAC_NESNE.get(tool)
        if yeni == self._nesne:
            return
        if yeni is None:
            self._giden, self._nesne = self._nesne, None
            self._gelis.to(0.0)
        else:
            self._giden = None
            self._nesne = yeni
            self._gelis.jump(0.0)
            self._gelis.to(1.0)
        self.bakisi_tazele()
        self.update()

    def clear(self) -> None:
        self._nesne = None
        self._giden = None
        self._gelis.jump(0.0)
        self.bakisi_tazele()
        self.update()

    def bakisi_tazele(self) -> None:
        """Nesne varken maskot yana dönüp ona bakıyor.

        Profil ayrı bir çizim değil: gözler bakılan yöne kayıyor,
        uzaktaki küçülüyor, gövde biraz daralıyor. Geçiş yay ile — ani
        dönen bir kafa dönmüyor, takılıyor gibi görünüyor.

        Bakmıyorsa nesne elinde değil, önünde duran bir resim gibi
        görünüyor.
        """
        yandan = getattr(self.yuz, "set_profil", None)
        if yandan is not None:
            yandan(PROFIL.get(self._nesne or "", False))
        if self._nesne:
            bak = getattr(self.yuz, "look_at", None)
            if bak is not None:
                bak(*BAKIS.get(self._nesne, (0.0, 0.6)))
        else:
            ileri = getattr(self.yuz, "look_forward", None)
            if ileri is not None:
                ileri()

    def _ten_rengi(self) -> str:
        """Kol ve elin rengi — yüzün gövdesiyle aynı.

        Yaratığın parçaları nesneden ayrı okunmalı. Üçü de vurgu rengi
        olduğunda kol, el ve nesne tek bir pembe kütleye dönüşüyordu.
        """
        renk = getattr(self.yuz, "_govde_rengi", None)
        return renk() if renk is not None else self.t.accent

    def _cizici(self, ad: str) -> QSvgRenderer | None:
        if ad not in self._ciziciler:
            self._ciziciler[ad] = _renkli(ad, self.t, self._ten_rengi())
        return self._ciziciler[ad]

    # --- kare -------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._yerlestir()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.halka.show()
        self._yerlestir()
        if not self._abone:
            clock().subscribe(self._tick)
            self._abone = True

    def hideEvent(self, event) -> None:
        if self._abone:
            clock().unsubscribe(self._tick)
            self._abone = False
        super().hideEvent(event)

    def _tick(self, dt: float) -> None:
        self._gecen += dt
        # Yüz beklemeye döndüyse nesne de elinden bırakılıyor. Yoksa
        # maskot bitmiş bir işin nesnesiyle sonsuza kadar duruyor —
        # canlı bir şey değil, bir ekran görüntüsü.
        if self._nesne and getattr(self.yuz, "bosta", False):
            self.clear()
        self._gelis.step(dt)
        self.update()

    def _yerlestir(self) -> None:
        """İz artık bütün sütun boyunca: adımlar yukarıdan aşağı diziliyor
        ve figürün üstünden geçmiyor."""
        self.halka.setGeometry(0, 0, self.width(), self.height())

    # --- çizim ------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._nesneyi_ciz(painter)
        painter.end()

    def _sahne_kutusu(self) -> QRectF:
        """Sahnenin çizileceği dikdörtgen — izin sağında, oranı korunmuş."""
        alan_x = IZ_PAY
        alan_en = max(1.0, self.width() - IZ_PAY)
        olcek = min(alan_en / VB_EN, self.height() / VB_BOY)
        en, boy = VB_EN * olcek, VB_BOY * olcek
        return QRectF(alan_x + (alan_en - en) / 2, 0.0, en, boy)

    def yuz_kutusu(self) -> QRectF:
        """Yüzün oturduğu yuva, pencere koordinatında.

        Yer SVG'den geliyor, koddan değil. Aynı sayıyı iki yerde
        hesaplamak bu sahnenin en pahalı hatasıydı: halka sütundan dar ve
        yüz merkezi 30'da kalıyordu, nesne 43'e gidiyordu — maskot bir
        yana, elindeki nesne öbür yana düşüyordu.
        """
        kutu = self._sahne_kutusu()
        cizici = self._cizici(self._nesne or self._giden or "laptop")
        if cizici is None or not cizici.elementExists(YUVA):
            # Sahne yoksa yüz sütunun üstünde ortalanıyor.
            kenar = min(kutu.width(), kutu.height()) * 0.48
            return QRectF(kutu.center().x() - kenar / 2, 0.0, kenar, kenar)
        yuva = cizici.boundsOnElement(YUVA)
        o = kutu.width() / VB_EN
        return QRectF(kutu.x() + yuva.x() * o, kutu.y() + yuva.y() * o,
                      yuva.width() * o, yuva.height() * o)

    def _nesneyi_ciz(self, painter: QPainter) -> None:
        """Sahneyi sırayla çiziyor; yüz sıranın içinde.

        Yüzün yeri `PARCALAR` listesinde: büyüteçte camın **altında**,
        dizüstünde uzak kolun **üstünde**. Yüzü hep en öne ya da hep en
        arkaya koymak, sahnenin yarısını yanlış yapardı.
        """
        ad = self._nesne or self._giden
        cizici = self._cizici(ad) if ad else None
        kutu = self._sahne_kutusu()
        olcek = kutu.width() / VB_EN
        k = max(0.0, min(1.2, self._gelis.value)) if ad else 0.0

        painter.save()
        painter.translate(kutu.topLeft())
        painter.scale(olcek, olcek)
        if cizici is None or k < 0.01:
            self._yuzu_ciz(painter, cizici)
            painter.restore()
            return

        opaklik = min(1.0, k)
        for parca in PARCALAR.get(ad, ()):
            if parca == YUZ:
                self._yuzu_ciz(painter, cizici)
                continue
            painter.save()
            # Sahne aşağıdan gelip yerine oturuyor. Yüz bu kaymaya
            # katılmıyor: gövde yerinde durup elleri geliyor.
            painter.translate(0.0, (1.0 - k) * GELIS_YOL)
            painter.setOpacity(opaklik)
            self._parcayi_ciz(painter, cizici, ad, parca)
            painter.restore()
        painter.restore()

    def _yuzu_ciz(self, painter: QPainter, cizici: QSvgRenderer | None) -> None:
        """Yüzü yuvasına çizer. Ölçek zaten painter'da."""
        if cizici is not None and cizici.elementExists(YUVA):
            yuva = cizici.boundsOnElement(YUVA)
        else:
            kenar = VB_EN * 0.46
            yuva = QRectF((VB_EN - kenar) / 2, 0.0, kenar, kenar)
        boya = getattr(self.yuz, "paint", None)
        if boya is not None:
            boya(painter, yuva.width(), yuva.topLeft())

    def _kablo_noktasi(self, cizici: QSvgRenderer, u: float):
        """Kablonun üstünde `u` oranındaki nokta.

        Eğrinin kontrol noktaları SVG'de `kablo-p0/p1/p2` işaretleriyle
        duruyor ve buradan okunuyor. Denklemi iki yere yazmak — biri
        çizim betiğinde, biri burada — bir gün ayrı düşmelerinin
        garantisiydi; kıvılcım kablonun yanından geçerdi ve kimse nedenini
        bulamazdı.
        """
        noktalar = []
        for ad in ("kablo-p0", "kablo-p1", "kablo-p2"):
            if not cizici.elementExists(ad):
                return None
            noktalar.append(cizici.boundsOnElement(ad).center())
        p0, p1, p2 = noktalar
        t = 1.0 - u
        return QPointF(
            t * t * p0.x() + 2 * t * u * p1.x() + u * u * p2.x(),
            t * t * p0.y() + 2 * t * u * p1.y() + u * u * p2.y(),
        )

    def _parcayi_ciz(self, painter: QPainter, cizici: QSvgRenderer,
                     nesne: str, parca: str) -> None:
        """Parçayı çiziyor; hareketli olanlara kendi hareketini veriyor.

        Hedef dikdörtgen `transformForElement` ile hesaplanıyor.
        `boundsOnElement` elemanın **yerel** kutusunu veriyor: nesne
        parçaları sahnenin içinde bir dönüşümün altında duruyor ve yerel
        kutuya çizmek onları 64 birimlik kendi uzaylarında, sahnenin
        yanlış yerine koyuyor. Ölçtüm: `ekran` yerelde (12, 9), belgede
        (34.2, 48.2). Fark sessiz — bir şey çizilir, ama yanlış yere.
        """
        if not cizici.elementExists(parca):
            return
        donusum = cizici.transformForElement(parca)
        kutu = donusum.mapRect(cizici.boundsOnElement(parca))
        #: Nesne kendi 64 birimlik uzayından sahneye küçülüyor; hareket
        #: mesafeleri de aynı oranda küçülmeli, yoksa parıltı camdan
        #: taşar.
        o = donusum.m11() or 1.0
        opaklik = painter.opacity()

        if nesne == "laptop" and parca.startswith("tus-"):
            # İki eli klavyede: tuşlar sırayla basılıyor. Aynı anda
            # inselerdi yazmak değil, tuşa yaslanmak olurdu.
            i = int(parca[-1])
            vur = max(0.0, math.sin(self._gecen * 6.4 + i * math.pi))
            kutu = kutu.translated(0.0, vur * 0.9 * o)
        elif nesne == "terminal" and parca == "imlec":
            painter.setOpacity(opaklik if (self._gecen % 1.0) < 0.55 else 0.0)
        elif nesne == "mercek" and parca == "parilti":
            a = self._gecen * 1.6
            kutu = kutu.translated(math.cos(a) * 3.0 * o, math.sin(a) * 3.0 * o)
        elif nesne == "sayfa" and parca in ("kalem", "el-yakin"):
            # Kalem yazıyor: uç küçük bir yay çiziyor, el onunla gidiyor.
            a = self._gecen * 5.2
            kutu = kutu.translated(math.sin(a) * 1.6 * o,
                                   math.cos(a * 0.5) * 0.7 * o)
        elif nesne == "sunucu" and parca.startswith("isik-"):
            ust = parca.endswith("ust")
            acik = (self._gecen % 1.2) < 0.6
            painter.setOpacity(opaklik if acik == ust else opaklik * 0.22)
        elif nesne == "sunucu" and parca == "kivilcim":
            yer = self._kablo_noktasi(cizici, (self._gecen * 0.55) % 1.0)
            if yer is None:
                return
            kutu.moveCenter(yer)

        cizici.render(painter, parca, kutu)
        painter.setOpacity(opaklik)
