"""Tepsi simgesi ve global kısayol.

İkisi de uygulama **arkadayken** çalışmak zorunda ve arkada olan bir
şeyin bozulduğu fark edilmiyor. Testlerin ağırlığı bu yüzden iki yerde:
durumun simgede gerçekten ayırt edilebilmesi, ve kısayol kaydı tutmadığında
bunun sessizce yutulmaması.
"""

from __future__ import annotations

import pytest

from app import kisayol as kisayol_mod


@pytest.fixture()
def t():
    from app import fluent

    return fluent.tokens()


class TestSimge:
    def test_butun_boyutlar(self, qt_app, t):
        from app.tepsi import BOYUTLAR, simge

        ikon = simge(t, "bos")
        boyutlar = {(s.width(), s.height()) for s in ikon.availableSizes()}
        assert boyutlar == {(b, b) for b in BOYUTLAR}

    def test_simge_bos_degil(self, qt_app, t):
        from app.tepsi import simge

        resim = simge(t, "kosuyor").pixmap(16, 16).toImage()
        dolu = sum(
            1 for y in range(16) for x in range(16)
            if resim.pixelColor(x, y).alpha() > 0
        )
        assert dolu > 40, "16 pikselde siluet neredeyse hiç görünmüyor"

    def test_calisan_ile_duran_ayirt_ediliyor(self, qt_app, t):
        # Sistem vurgu rengi bu makinede pembe ve `critical` da pembeye
        # yakın: yalnızca gövde rengiyle ayırmak iki durumu aynı simge
        # yapıyordu. Rozet bunu renk seçiminden bağımsız çözüyor.
        from app.tepsi import simge

        a = simge(t, "kosuyor").pixmap(16, 16).toImage()
        b = simge(t, "durduruldu").pixmap(16, 16).toImage()
        farkli = sum(
            1 for y in range(16) for x in range(16)
            if a.pixelColor(x, y) != b.pixelColor(x, y)
        )
        assert farkli > 20, f"iki durum neredeyse aynı görünüyor ({farkli} px)"

    def test_rozet_yalnizca_dikkat_isteyende(self, qt_app, t):
        from app.tepsi import _rozet

        assert _rozet(t, "onay") == t.caution
        assert _rozet(t, "durduruldu") == t.critical
        assert _rozet(t, "kosuyor") == ""
        assert _rozet(t, "bos") == ""

    def test_varlik_yoksa_yine_bir_simge_var(self, qt_app, t, monkeypatch):
        # Simgesiz bir tepsi girdisi tıklanamaz bir boşluk.
        from app import tepsi as tepsi_mod

        monkeypatch.setattr(tepsi_mod, "_siluet", lambda: [])
        resim = tepsi_mod.simge(t, "bos").pixmap(16, 16).toImage()
        assert any(
            resim.pixelColor(x, y).alpha() > 0
            for y in range(16) for x in range(16)
        )


class TestTepsi:
    def _tepsi(self, t):
        from app.tepsi import Tepsi

        return Tepsi(t)

    def test_menu_dort_eylem(self, qt_app, t):
        tepsi = self._tepsi(t)
        eylemler = [a for a in tepsi._menu.actions() if not a.isSeparator()]
        assert len(eylemler) == 4
        assert all(a.text() for a in eylemler), "adsız menü girdisi"

    def test_menu_sinyalleri(self, qt_app, t):
        tepsi = self._tepsi(t)
        gelen = []
        tepsi.pencere_istendi.connect(lambda: gelen.append("pencere"))
        tepsi.durdur_istendi.connect(lambda: gelen.append("durdur"))
        tepsi.cikis_istendi.connect(lambda: gelen.append("cikis"))
        for eylem in tepsi._menu.actions():
            if not eylem.isSeparator():
                eylem.trigger()
        assert gelen == ["pencere", "durdur", "cikis"]

    def test_tek_tik_cubuk_cift_tik_pencere(self, qt_app, t):
        from PySide6.QtWidgets import QSystemTrayIcon

        tepsi = self._tepsi(t)
        gelen = []
        tepsi.cubuk_istendi.connect(lambda: gelen.append("cubuk"))
        tepsi.pencere_istendi.connect(lambda: gelen.append("pencere"))
        tepsi._tiklandi(QSystemTrayIcon.ActivationReason.Trigger)
        tepsi._tiklandi(QSystemTrayIcon.ActivationReason.DoubleClick)
        assert gelen == ["cubuk", "pencere"]

    def test_durum_simgeyi_degistiriyor(self, qt_app, t):
        tepsi = self._tepsi(t)
        assert tepsi._faz == "bos"
        tepsi.set_phase("kosuyor")
        assert tepsi._faz == "kosuyor"
        assert "working" in tepsi.icon.toolTip()

    def test_bildirim_gizliyken_gonderilmiyor(self, qt_app, t):
        # Görünmeyen bir tepsi simgesinden balon çıkmıyor; çağrının
        # sessizce patlaması yerine hiç yapılmaması doğru.
        tepsi = self._tepsi(t)
        assert not tepsi.icon.isVisible()
        tepsi.bildir("x", "y")  # patlamamalı


class TestKisayol:
    #: Ctrl+Shift+Alt+F13 — hiçbir yerde kullanılmıyor.
    SERBEST = (
        kisayol_mod.MOD_CONTROL | kisayol_mod.MOD_SHIFT | kisayol_mod.MOD_ALT,
        0x7C,
        "Ctrl+Shift+Alt+F13",
    )

    def test_kayit_ve_birakma(self, qt_app):
        k = kisayol_mod.GlobalKisayol(*self.SERBEST)
        assert k.start(), k.hata
        assert k.kayitli and not k.hata
        k.stop()
        assert not k.kayitli

        # Bırakıldıysa aynı kombinasyon yeniden alınabilmeli. Alınamıyorsa
        # `UnregisterHotKey` çağrılmamış demektir ve uygulama her
        # açılışta bir kısayol daha sızdırıyor demektir.
        ikinci = kisayol_mod.GlobalKisayol(*self.SERBEST)
        assert ikinci.start(), ikinci.hata
        ikinci.stop()

    def test_dolu_kombinasyon_sebebini_soyluyor(self, qt_app):
        tutan = kisayol_mod.GlobalKisayol(*self.SERBEST)
        assert tutan.start(), tutan.hata
        try:
            ikinci = kisayol_mod.GlobalKisayol(*self.SERBEST)
            assert not ikinci.start()
            assert "already taken" in ikinci.hata
            ikinci.stop()
        finally:
            tutan.stop()

    def test_kur_ilk_bosu_aliyor(self, qt_app):
        tutan = kisayol_mod.GlobalKisayol(*self.SERBEST)
        assert tutan.start(), tutan.hata
        try:
            # İlk aday dolu; ikinciye düşmeli.
            yedek = (kisayol_mod.MOD_CONTROL | kisayol_mod.MOD_SHIFT
                     | kisayol_mod.MOD_ALT, 0x7D, "Ctrl+Shift+Alt+F14")
            secilen = kisayol_mod.kur((self.SERBEST, yedek))
            assert secilen.kayitli
            assert secilen.ad == "Ctrl+Shift+Alt+F14"
            secilen.stop()
        finally:
            tutan.stop()

    def test_hicbiri_bos_degilse_hepsini_sayiyor(self, qt_app):
        tutan = kisayol_mod.GlobalKisayol(*self.SERBEST)
        assert tutan.start(), tutan.hata
        try:
            sonuc = kisayol_mod.kur((self.SERBEST,))
            assert not sonuc.kayitli
            assert "Ctrl+Shift+Alt+F13" in sonuc.hata
        finally:
            tutan.stop()

    def test_iki_kez_durdurmak_patlamiyor(self, qt_app):
        k = kisayol_mod.GlobalKisayol(*self.SERBEST)
        k.start()
        k.stop()
        k.stop()
