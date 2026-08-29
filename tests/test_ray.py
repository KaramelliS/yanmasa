"""Ray ve sayfalar — dock'ların yerine geçen gezinme.

Testlerin ağırlığı **kapanmada**. Bir sayfa kapandığında yığında hangi
sayfanın kaldığı, hiç düşünülmediğinde boş bir gövde bırakan türden bir
ayrıntı: ekranda hiçbir şey yok, uygulama çalışıyor, kimse sebebini
anlamıyor.
"""

from __future__ import annotations

import pytest

from app.ray import Oge, Ray


@pytest.fixture()
def t():
    from app import fluent

    return fluent.tokens()


class TestRay:
    def test_ayni_anahtar_iki_kez_eklenmiyor(self, qt_app, t):
        r = Ray(t)
        r.ekle(Oge("a", "A", "sayfa"))
        r.ekle(Oge("a", "A", "sayfa"))
        assert r.anahtarlar() == ["a"]

    def test_secim_ve_cikarma(self, qt_app, t):
        r = Ray(t)
        r.ekle(Oge("a", "A", "sayfa"))
        r.ekle(Oge("b", "B", "sayfa"))
        r.sec("b")
        assert r.etkin == "b"
        r.cikar("b")
        assert r.anahtarlar() == ["a"]

    def test_sabitler_sayiliyor(self, qt_app, t):
        # Ayraç sabitlerle ajanın açtıkları arasına çiziliyor; sayı yanlışsa
        # ayraç listenin ortasına düşer.
        r = Ray(t)
        r.ekle(Oge("akis", "Activity", "defter", kapatilabilir=False))
        r.ekle(Oge("masa", "Desk", "pencere", kapatilabilir=False))
        r.ekle(Oge("x.xlsx", "x.xlsx", "tablo"))
        assert r._sabit_sayisi == 2

    def test_etiket_degistirilebiliyor(self, qt_app, t):
        r = Ray(t)
        r.ekle(Oge("a", "A", "sayfa"))
        r.etiketle("a", "B")
        assert r._ogeler[0].etiket == "B"

    def test_bos_alana_tiklamak_sinyal_yollamiyor(self, qt_app, t):
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        r = Ray(t)
        r.ekle(Oge("a", "A", "sayfa"))
        r.resize(76, 600)
        gelenler = []
        r.secildi.connect(gelenler.append)
        olay = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress, QPointF(30, 500),
            QPointF(30, 500), Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        )
        r.mousePressEvent(olay)
        assert gelenler == []


class TestSayfalar:
    def _pencere(self, qt_app):
        from app import fluent
        from app.window import MainWindow

        return MainWindow(fluent.tokens())

    def _govde(self, t):
        from PySide6.QtWidgets import QLabel

        return QLabel("x")

    def test_akis_hep_ilk_sayfa(self, qt_app, t):
        w = self._pencere(qt_app)
        assert w.ray.anahtarlar() == ["akis"]
        assert w.ray.etkin == "akis"

    def test_panel_acinca_sayfa_ve_ray_ogesi(self, qt_app, t):
        w = self._pencere(qt_app)
        w.open_panel("a.xlsx", "a.xlsx · sheet", self._govde(t))
        assert w.ray.anahtarlar() == ["akis", "a.xlsx"]
        assert w.ray.etkin == "a.xlsx", "yeni sayfa öne gelmeli"

    def test_ray_etiketi_baslikin_ilk_parcasi(self, qt_app, t):
        # `butce.xlsx · sheet (1 unsaved)` 76 piksellik raya sığmıyor.
        w = self._pencere(qt_app)
        w.open_panel("a.xlsx", "a.xlsx · sheet  (1 unsaved)", self._govde(t))
        assert w.ray._ogeler[-1].etiket == "a.xlsx"

    def test_ayni_anahtar_govdeyi_degistiriyor(self, qt_app, t):
        w = self._pencere(qt_app)
        ilk, ikinci = self._govde(t), self._govde(t)
        w.open_panel("a", "A", ilk)
        w.open_panel("a", "A2", ikinci)
        assert w.ray.anahtarlar() == ["akis", "a"]
        assert w._pages["a"].govde is ikinci
        assert w._pages["a"].baslik._etiket.text() == "A2"

    def test_kapanan_sayfadan_sonra_bos_kalmiyor(self, qt_app, t):
        # Kapanan sayfa etkinken hiçbir yere düşülmezse yığın boş bir
        # gövde gösteriyor ve ekranda hiçbir şey kalmıyor.
        w = self._pencere(qt_app)
        w.open_panel("a", "A", self._govde(t))
        w.open_panel("b", "B", self._govde(t))
        w.close_panel("b")
        assert w.ray.etkin == "a"
        assert w.stack.currentWidget() is w._pages["a"]

    def test_son_sayfa_kapaninca_akisa_donuyor(self, qt_app, t):
        w = self._pencere(qt_app)
        w.open_panel("a", "A", self._govde(t))
        w.close_panel("a")
        assert w.ray.etkin == "akis"

    def test_sabit_sayfa_kapatilamiyor(self, qt_app, t):
        w = self._pencere(qt_app)
        assert w._pages["akis"].baslik is not None
        # Akış sayfasında kapat düğmesi yok.
        assert not hasattr(w._pages["akis"].baslik, "_kapat")

    def test_basliksiz_sayfa_ustune_serit_koymuyor(self, qt_app, t):
        # Masanın kendi paneli zaten bir başlık şeridi.
        w = self._pencere(qt_app)
        w.add_fixed_page("masa", "Desk", "pencere", self._govde(t),
                         basliksiz=True)
        assert w._pages["masa"].baslik is None

    def test_olmayan_sayfaya_gecmek_patlamiyor(self, qt_app, t):
        w = self._pencere(qt_app)
        w.show_page("yok-boyle-bir-sey")
        assert w.ray.etkin == "akis"
