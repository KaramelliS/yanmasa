"""Sahne: maskot solda, üstünde çalıştığı nesne sağda.

Ajan ofis belgesi düzenliyorsa yanında bir dizüstü beliriyor ve ekranında
satırlar yazılıyor; kabuk komutu çalıştırıyorsa bir terminal ve imleci
yanıp sönüyor; ekrana bakıyorsa bir mercek, parıltısı camda geziniyor;
sunucudaysa bir sunucu ve ışıkları sırayla yanıyor; dosya yazıyorsa bir
sayfa ve satırları sırayla beliriyor.

**Neden simge değil nesne.** Simge "bu bir dosya işi" der ve orada
kalır. Nesne maskotun ona doğru eğilmesini, ona bakmasını, bir yerinin
kıpırdamasını mümkün kılıyor. Aradaki fark, bir etiket izlemekle çalışan
birini izlemek arasındaki fark.

**Nesne halkanın içine sığmıyordu.** 52 pikselde laptop okunmuyor;
sahne 96 piksel yüksekliğinde ayrı bir şerit ve yalnızca bir tur
sürerken görünüyor. Boşta yer kaplamıyor.

Nesnenin gelişi ve gidişi yay: aşağıdan gelip yerine oturuyor, iş
bitince küçülüp kayboluyor. Birden belirip birden kaybolan bir şey,
gözün onu fark etmesine fırsat bırakmıyor.
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget

from .fluent import RADIUS_CARD, Tokens
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

#: Sahnenin yüksekliği ve içindekilerin ölçüleri.
YUKSEKLIK = 96
YUZ_BOYUT = 62
NESNE_BOYUT = 60

#: Maskot nesneye doğru bu kadar eğiliyor.
EGILME = 0.55


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
    """Maskot ve o an üstünde çalıştığı nesne."""

    def __init__(self, t: Tokens, halka: QWidget) -> None:
        super().__init__()
        self.t = t
        # Halka sahnenin **çocuğu**. Yüzü ilerleten tek yer halka; sahne
        # de ilerletseydi yüz iki kat hızlı oynardı. Sahibi tek olsun.
        self.halka = halka
        self.halka.setParent(self)
        self.yuz = getattr(halka, "face", halka)
        self.setFixedHeight(YUKSEKLIK)
        self._egim = Spring(0.0, stiffness=140.0, damping=16.0)
        self._ciziciler: dict[str, QSvgRenderer] = {}
        self._nesne: str | None = None
        self._giden: str | None = None
        self._gelis = Spring(0.0, stiffness=170.0, damping=15.0)
        self._gecen = 0.0
        self._abone = False

    # --- durum ------------------------------------------------------------

    def set_tool(self, tool: str) -> None:
        """Araç değişti: nesne de değişiyor.

        Aynı nesne devam ediyorsa sahne bozulmuyor — her adımda nesneyi
        yeniden getirmek, dosya yazan bir turda sayfanın sürekli gidip
        gelmesi olurdu.
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
        self.bakisi_ayarla()
        self.update()

    def clear(self) -> None:
        self._nesne = None
        self._giden = None
        self._gelis.jump(0.0)
        self.update()

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
        self._egim.step(dt)
        self._yerlestir()
        self.update()

    # --- çizim ------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.t.background))
        painter.drawRoundedRect(
            QRectF(0.5, 0.5, self.width() - 1, self.height() - 1),
            RADIUS_CARD, RADIUS_CARD,
        )

        self._nesneyi_ciz(painter)
        painter.end()

    def _yerlestir(self) -> None:
        """Halkayı yerine koyuyor; nesne varken ona doğru eğiliyor.

        Yalnızca bakış yetmiyordu: nesne sağda, maskot yerinde duruyor ve
        ikisi aynı sahnede değil, yan yana iki resim gibi görünüyordu.
        Gövdenin de o yöne kayması ikisini bir arada tutuyor.
        """
        b = self.halka.width()
        x = self.width() * 0.21 - b / 2 + self._egim.value * 7.0
        self.halka.move(int(x), int((self.height() - b) / 2))

    def _nesneyi_ciz(self, painter: QPainter) -> None:
        ad = self._nesne or self._giden
        if ad is None:
            return
        cizici = self._cizici(ad)
        if cizici is None:
            return

        k = max(0.0, self._gelis.value)
        if k < 0.01:
            return
        boyut = NESNE_BOYUT * (0.7 + 0.3 * k)
        x = self.width() * 0.62 - boyut / 2
        # Aşağıdan gelip yerine oturuyor.
        y = (self.height() - boyut) / 2 + (1.0 - k) * 14.0

        painter.save()
        painter.setOpacity(min(1.0, k))
        painter.translate(x, y)
        painter.scale(boyut / 64.0, boyut / 64.0)
        for parca in PARCALAR.get(ad, []):
            self._parcayi_ciz(painter, cizici, ad, parca)
        painter.restore()

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
            # Parıltı camın içinde küçük bir daire çiziyor.
            a = self._gecen * 1.6
            kutu = kutu.translated(math.cos(a) * 3.4, math.sin(a) * 3.4)
        elif nesne == "sunucu" and parca.startswith("isik-"):
            ust = parca.endswith("ust")
            acik = (self._gecen % 1.2) < 0.6
            painter.setOpacity(opaklik if acik == ust else opaklik * 0.28)
        elif nesne == "sayfa" and parca.startswith("satir-"):
            # Satırlar sırayla beliriyor: yazılıyormuş gibi.
            i = int(parca[-1])
            gorunur = (self._gecen % 2.4) > i * 0.55
            painter.setOpacity(opaklik if gorunur else 0.0)

        cizici.render(painter, parca, kutu)
        painter.setOpacity(opaklik)

    # --- yüzün nesneye bakması --------------------------------------------

    def bakisi_ayarla(self) -> None:
        """Maskot nesneye doğru bakıyor.

        Nesne sağda duruyor ve maskot ona bakmıyorsa ikisi aynı sahnede
        değil, yan yana iki resim oluyor.
        """
        bak = getattr(self.yuz, "look_at", None)
        if bak is None:
            return
        if self._nesne:
            bak(EGILME, 0.18)
            self._egim.to(1.0)
        else:
            self._egim.to(0.0)
            ileri = getattr(self.yuz, "look_forward", None)
            if ileri is not None:
                ileri()
