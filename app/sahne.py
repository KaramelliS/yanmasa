"""Maskot sütunu: gövde, elleri ve elindeki nesne.

Sahne önce çubuğun **üstünde** bir şeritti ve yanlıştı: bir iş
başlayınca cevap alanını aşağı itiyor, okuduğun yer kayıyordu. Artık
solda dar bir sütun — döküm sağında akıyor, hiçbir şey yer değiştirmiyor
ve maskot her zaman orada, boşta da nefes alıyor.

**Elleri var ve nesneyi tutuyor.** Nesne gövdenin önünde, iki el
üstünde. Çalışırken eller sırayla iniyor: ofis belgesinde tuşlara
basıyor, terminalde yazıyor, mercekte tutuyor. Nesneyi yanına koymakla
eline vermek arasındaki fark, izlediğin şeyin bir etiket mi yoksa
çalışan biri mi olduğu.

Eller gövdenin küçültülmüş hâli — aynı siluet. Ayrı bir şekil çizmek
maskotu birbirine yapıştırılmış parçalar gibi gösterirdi.

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

#: Nesne parçalarının çizim sırası. `scripts/nesneler.py` ile aynı.
PARCALAR = {
    "laptop": ["taban", "tus", "ekran", "satir-1", "satir-2", "satir-3"],
    "terminal": ["pencere", "nokta-1", "nokta-2", "istem", "imlec"],
    "mercek": ["sap", "cam", "cam-ic", "parilti"],
    "sunucu": ["raf-ust", "yuva-ust", "isik-ust",
               "raf-alt", "yuva-alt", "isik-alt"],
    "sayfa": ["kagit", "kivrim", "satir-1", "satir-2", "satir-3"],
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

#: Sütunun eni ve içindekilerin ölçüleri. Hepsi sütunun üst kenarına
#: göre, ortalanmış: gövde üstte, nesne onun alt üçte birine biniyor,
#: eller nesnenin üst kenarında.
#: 88'de sütunun sağında boşluk kalıyordu; gövde 52, nesne 36 ve 72
#: ikisini de sığdırıyor.
GENISLIK = 78
#: Nesne gövdeden **dar** olmalı. 42'de gövdeden genişti ve maskot onu
#: tutuyor değil, arkasında duruyor gibi okunuyordu — çizip baktım.
NESNE = 36
EL = 11

#: Nesnenin yüzün alt kenarına **bindirmesi**. Eksi değer boşluk
#: bırakırdı; artı değer nesneyi çenenin altına sokuyor.
#:
#: Nesne eskiden sütunun üstünden sabit 46 pikseldeydi ve yüzün altında
#: 15 piksellik boşluk kalıyordu. Boşluk nesneyi elde tutulan bir şey
#: değil, altta duran bir resim yapıyordu.
NESNE_BINDIRME = 1.5
#: Ellerin nesnenin **üst kenarına** göre inişi. Mutlak değildi ve nesne
#: yer değiştirince eller yerinde kalıyordu.
#:
#: 4'tü ve eller yüzle aynı hizaya düşüyordu: kol görünmüyor, eller kulak
#: gibi duruyordu. 9'da kol ortaya çıkıyor ve el nesnenin üstünde.
EL_Y = 9.0

#: Ellerin merkezden uzaklığı. Nesnenin yarı eninden biraz içeride.
EL_X = 14

#: Kolun kalınlığı ve omzun yüz kutusuna göre yeri.
#:
#: İlk deneme 5 kalınlık ve ±%20 omuzdu: iki kol geniş bir V çiziyor ve
#: pelerin gibi okunuyordu — çizip baktım. Kol ince ve omuz dar olunca
#: çizgi kalıyor, kütle kalmıyor.
KOL = 3.4
OMUZ_X, OMUZ_Y = 0.10, 0.16

#: Nesneye özel el konumu — (merkezden uzaklık, nesnenin üstünden iniş).
#:
#: Varsayılan eller nesnenin iki üst köşesinde: dizüstü, terminal, sayfa
#: ve sunucu birer levha ve köşelerinden tutuluyorlar. Mercek levha
#: değil, halka; aynı köşelerde eller camın dışında kalıyor ve nesne
#: karakterden kopuk okunuyor. Ölçtüm: camın yarıçapı sütun ölçeğinde
#: 11.3 piksel, eller merkeze 19.8 piksel uzaktaydı — arada 8 piksel
#: boşluk. Burada eller camın alt yanaklarına, çemberin üstüne iniyor.
EL_KONUM = {"mercek": (8.0, 23.5)}

#: Nesne ve eller izin sağında kalıyor, üstünde değil.
IZ_PAY = 8

#: Sütunun boyu: yüz + nesne + biraz nefes. 100'dü ve nesne yukarı
#: alınınca altta 37 piksel boş kalıyordu.
YUKSEKLIK = 76


def _renkli(ad: str, t: Tokens) -> QSvgRenderer | None:
    yol = SVG_DIZIN / f"nesne-{ad}.svg"
    if not yol.is_file():
        return None
    metin = yol.read_text(encoding="utf-8")
    metin = metin.replace(YER_GOVDE, t.accent).replace(YER_OYUK, t.background)
    return QSvgRenderer(QByteArray(metin.encode("utf-8")))


def nesneler_var() -> bool:
    return (SVG_DIZIN / "nesne-laptop.svg").is_file()


class Sahne(QWidget):
    """Maskot sütunu: halka, gövde, eller, elindeki nesne."""

    def __init__(self, t: Tokens, halka: QWidget) -> None:
        super().__init__()
        self.t = t
        # Halka sütunun çocuğu. Yüzü ilerleten tek yer halka; sahne de
        # ilerletseydi yüz iki kat hızlı oynardı.
        self.halka = halka
        self.halka.setParent(self)
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
        """Nesne varken maskot ona bakıyor: nesne aşağıda, gözler aşağı.

        Bakmıyorsa nesne elinde değil, önünde duran bir resim gibi
        görünüyor.
        """
        if self._nesne:
            bak = getattr(self.yuz, "look_at", None)
            if bak is not None:
                bak(0.0, 0.85)
        else:
            ileri = getattr(self.yuz, "look_forward", None)
            if ileri is not None:
                ileri()

    def _cizici(self, ad: str) -> QSvgRenderer | None:
        if ad not in self._ciziciler:
            self._ciziciler[ad] = _renkli(ad, self.t)
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

    def _nesneyi_ciz(self, painter: QPainter) -> None:
        ad = self._nesne or self._giden
        if ad is None:
            return
        cizici = self._cizici(ad)
        if cizici is None:
            return
        k = max(0.0, min(1.2, self._gelis.value))
        if k < 0.01:
            return

        boyut = NESNE * (0.78 + 0.22 * k)
        merkez, ust = self._nesne_yeri()
        x = merkez - boyut / 2
        # Aşağıdan gelip ellerine oturuyor.
        y = ust + (NESNE - boyut) / 2 + (1.0 - k) * 12.0

        # Kollar nesnenin **arkasında**: nesne kolun önünde, el nesnenin
        # önünde. Sıra bu olmazsa tutma okunmuyor — el nesnenin arkasında
        # kalırsa maskot ona dokunuyor bile görünmüyor.
        self._kollari_ciz(painter, ad, k)

        painter.save()
        painter.setOpacity(min(1.0, k))
        painter.translate(x, y)
        painter.scale(boyut / 64.0, boyut / 64.0)
        for parca in PARCALAR.get(ad, []):
            self._parcayi_ciz(painter, cizici, ad, parca)
        painter.restore()

        self._elleri_ciz(painter, ad, k)

    def _nesne_yeri(self) -> tuple[float, float]:
        """Nesnenin merkezi ve üst kenarı — **yüzün kutusundan** türüyor.

        Sütunun ortasını kendi başına hesaplamak, yüzün nerede olduğunu
        tahmin etmekti ve tahmin yanlıştı: halka sütundan dar, yüz merkezi
        30'da kalıyordu, nesne 43'e gidiyordu.
        """
        kutu = self.halka.yuz_kutusu()
        return kutu.center().x(), kutu.bottom() - NESNE_BINDIRME

    def _el_yerleri(self, nesne: str, k: float) -> list[tuple[float, float]]:
        """İki elin merkezi. Nesnenin yerine göre, sütuna göre değil."""
        merkez, ust = self._nesne_yeri()
        el_x, el_y = EL_KONUM.get(nesne, (EL_X, EL_Y))
        dusus = (1.0 - k) * 12.0
        return [(merkez + taraf * el_x, ust + el_y + dusus)
                for taraf in (-1, 1)]

    def _kollari_ciz(self, painter: QPainter, nesne: str, k: float) -> None:
        """Yüzün altından ellere inen iki kol.

        Kolsuz eller havada duruyordu: bir el, bağlı olduğu bir şey
        olmadan tutuyor gibi okunmuyor — Berkay da "eliyle tutup
        bakmasını istiyorum" derken tam bunu söyledi. Kollar yüzün alt
        kenarından çıkıyor ve maskotla aynı renkte; ayrı bir parça değil,
        aynı yaratığın uzantısı.
        """
        kutu = self.halka.yuz_kutusu()
        omuz_y = kutu.bottom() - kutu.height() * OMUZ_Y
        painter.save()
        painter.setOpacity(min(1.0, k))
        painter.setPen(QPen(QColor(self._el_rengi()), KOL,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for taraf, (ex, ey) in zip((-1, 1), self._el_yerleri(nesne, k)):
            omuz_x = kutu.center().x() + taraf * kutu.width() * OMUZ_X
            painter.drawLine(QPointF(omuz_x, omuz_y), QPointF(ex, ey))
        painter.restore()

    def _elleri_ciz(self, painter: QPainter, nesne: str, k: float) -> None:
        """İki el, nesnenin iki yanında.

        Tuşlu işlerde sırayla iniyorlar — biri inerken öteki kalkıyor.
        Aynı anda inselerdi yazmak değil, zıplamak olurdu.
        """
        yol = self._el_yolu()
        if yol is None:
            return
        tusa_basiyor = nesne in TUSLU
        yerler = self._el_yerleri(nesne, k)

        painter.save()
        painter.setOpacity(min(1.0, k))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._el_rengi()))
        for i, (ex, ey) in enumerate(yerler):
            vur = 0.0
            if tusa_basiyor:
                vur = max(0.0, math.sin(self._gecen * 7.0 + i * math.pi)) * 2.6
            self._el_ciz(painter, yol, ex - EL / 2, ey - EL / 2 + vur)
        painter.restore()

    def _el_ciz(self, painter: QPainter, yol: QPainterPath,
                x: float, y: float) -> None:
        painter.save()
        painter.translate(x, y)
        painter.scale(EL / 96.0, EL / 96.0)
        painter.drawPath(yol)
        painter.restore()

    def _el_yolu(self) -> QPainterPath | None:
        """El, gövdenin küçültülmüş hâli — aynı siluet.

        Ayrı bir daire çizmek maskotu birbirine yapıştırılmış parçalar
        gibi gösterirdi; el de aynı yaratıktan.
        """
        alici = getattr(self.yuz, "taban_yolu", None)
        return alici() if alici is not None else None

    def _el_rengi(self) -> str:
        renk = getattr(self.yuz, "_govde_rengi", None)
        return renk() if renk is not None else self.t.accent

    def _parcayi_ciz(self, painter: QPainter, cizici: QSvgRenderer,
                     nesne: str, parca: str) -> None:
        """Parçayı çiziyor; hareketli olanlara kendi hareketini veriyor."""
        if not cizici.elementExists(parca):
            return
        kutu = cizici.boundsOnElement(parca)
        opaklik = painter.opacity()

        if nesne == "laptop" and parca.startswith("satir-"):
            # Ekranda satırlar yazılıyor: her biri kendi ritminde uzayıp
            # kısalıyor. Aynı anda değişselerdi yazmak değil, yanıp
            # sönmek olurdu.
            i = int(parca[-1])
            faz = math.sin(self._gecen * 3.2 - i * 1.1) * 0.5 + 0.5
            kutu = QRectF(kutu.x(), kutu.y(),
                          kutu.width() * (0.45 + 0.55 * faz), kutu.height())
        elif nesne == "terminal" and parca == "imlec":
            painter.setOpacity(opaklik if (self._gecen % 1.0) < 0.55 else 0.0)
        elif nesne == "mercek" and parca == "parilti":
            a = self._gecen * 1.6
            kutu = kutu.translated(math.cos(a) * 3.4, math.sin(a) * 3.4)
        elif nesne == "sunucu" and parca.startswith("isik-"):
            ust = parca.endswith("ust")
            acik = (self._gecen % 1.2) < 0.6
            painter.setOpacity(opaklik if acik == ust else opaklik * 0.28)
        elif nesne == "sayfa" and parca.startswith("satir-"):
            i = int(parca[-1])
            gorunur = (self._gecen % 2.4) > i * 0.55
            painter.setOpacity(opaklik if gorunur else 0.0)

        cizici.render(painter, parca, kutu)
        painter.setOpacity(opaklik)
