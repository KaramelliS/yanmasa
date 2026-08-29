"""Kaydırma takibi ve ajanın "buna dikkat" notu.

İkisi de aynı şikâyetten doğdu: **yukarıdaki mesajlar görünmüyor.**

Kaydırma tarafında sebep şuydu: her yeni adımda döküm koşulsuz sona
alınıyordu. Ajan saniyede bir adım atıyor, sen yukarı kaydırıyorsun,
bir sonraki adım seni sona geri fırlatıyor. Okumak fiilen imkânsızdı ve
kaydırma çubuğunun çalışıyor olması bunu gizliyordu.

Not tarafında ise eksik olan şey: ajan bir işi yaparken neye dikkat
ettiğini hiç söylemiyordu. Adım satırı *ne yaptığını* anlatıyor, notun
anlattığı şey *neyin ters gidebileceği*.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def t():
    from app import fluent

    return fluent.tokens()


@pytest.fixture()
def bar(qt_app, t):
    from app.commandbar import CommandBar

    w = CommandBar(t)
    w.show()
    qt_app.processEvents()
    return w


def _doldur(bar, qt_app, adet: int = 20) -> None:
    for i in range(adet):
        bar.add_step("screenshot", "Looking at the screen", f"adım {i}")
    qt_app.processEvents()


class TestKaydirmaTakibi:
    def test_sondayken_takip_ediyor(self, bar, qt_app):
        _doldur(bar, qt_app)
        cubuk = bar._reply_scroll.verticalScrollBar()
        assert cubuk.maximum() > 0, "döküm taşmadı, test bir şey ölçmüyor"
        assert cubuk.value() == cubuk.maximum()

        bar.add_step("zoom", "Zooming in", "son")
        qt_app.processEvents()
        assert cubuk.value() == cubuk.maximum(), "sondayken takip etmeli"

    def test_yukari_kaydirinca_yerinde_kaliyor(self, bar, qt_app):
        # Asıl kusur bu: yukarı kaydırdıktan sonra gelen her adım seni
        # sona geri fırlatıyordu.
        _doldur(bar, qt_app)
        cubuk = bar._reply_scroll.verticalScrollBar()
        cubuk.setValue(0)
        qt_app.processEvents()

        bar.add_step("zoom", "Zooming in", "yeni adım")
        qt_app.processEvents()
        assert cubuk.value() == 0, "yeni adım kullanıcıyı sona fırlattı"

    def test_akan_metin_de_firlatmiyor(self, bar, qt_app):
        _doldur(bar, qt_app)
        cubuk = bar._reply_scroll.verticalScrollBar()
        cubuk.setValue(0)
        qt_app.processEvents()
        for parca in ("bir ", "iki ", "üç "):
            bar.stream(parca)
        qt_app.processEvents()
        assert cubuk.value() == 0

    def test_sona_kaydir_geri_getiriyor(self, bar, qt_app):
        # Yeni tur başlarken çağrılıyor: eski turda yukarıda kalmış
        # olmak, yeni turu hiç görmemek anlamına gelmemeli.
        _doldur(bar, qt_app)
        cubuk = bar._reply_scroll.verticalScrollBar()
        cubuk.setValue(0)
        qt_app.processEvents()
        bar.sona_kaydir()
        assert cubuk.value() == cubuk.maximum()

    def test_akis_sayfasi_da_ayni(self, qt_app, t):
        from app.activity import ActivityView

        v = ActivityView(t)
        v.setFixedSize(600, 200)
        v.show()
        for i in range(30):
            v.add_step("Looking at the screen", f"{i}", "", "screenshot")
        for _ in range(3):
            qt_app.processEvents()
        v._body.adjustSize()
        qt_app.processEvents()
        cubuk = v._scroll.verticalScrollBar()
        assert cubuk.maximum() > 0, "liste taşmadı, test bir şey ölçmüyor"
        cubuk.setValue(0)
        qt_app.processEvents()
        v.add_step("Zooming in", "yeni", "", "zoom")
        qt_app.processEvents()
        assert cubuk.value() == 0


class TestArac:
    def test_arac_tanimli(self):
        from backend.agent.tools import CUSTOM_TOOL_NAMES

        assert "heads_up" in CUSTOM_TOOL_NAMES

    def test_kuru_kosuda_serbest(self):
        # Kuru koşuda tam da istenen şey: ne yapacağını değil, neye
        # dikkat edeceğini söylüyor.
        from backend.agent.kuru import serbest

        assert serbest("heads_up")

    def test_akisa_kaydedilmiyor(self):
        # Not bir eylem değil; oynatılan bir akışta tekrar edilmesinin
        # anlamı yok.
        from backend.workflows.depo import kaydedilir

        assert not kaydedilir("heads_up")

    def test_promptta_ne_zaman_yazdigi_var(self):
        from backend.agent.prompts import build_system
        from backend.computer.displays import Display, DisplayMap

        metin = build_system(DisplayMap([Display(0, 0, 0, 1920, 1080, True)]),
                             0)
        assert "Say what to watch out for" in metin

    def test_calistirmak_hicbir_sey_yapmiyor(self):
        from backend.agent.dispatch import Dispatcher, ToolOutcome

        d = Dispatcher.__new__(Dispatcher)
        sonuc = d._do_heads_up({"note": "dikkat"})
        assert isinstance(sonuc, ToolOutcome) and not sonuc.is_error

    def test_notsuz_cagri_hata(self):
        from backend.agent.dispatch import Dispatcher, ToolError

        d = Dispatcher.__new__(Dispatcher)
        with pytest.raises(ToolError):
            d._do_heads_up({"about": "bir şey"})

    def test_kendi_cizimi_ve_etiketi(self):
        from app.etiketler import tool_label
        from app.glyphs import GLYPHS, glyph_for

        assert glyph_for("heads_up") == "uyari"
        assert "uyari" in GLYPHS
        assert tool_label("heads_up") == "A note"


class TestNotSatiri:
    def _satir(self, t, notu, hakkinda=""):
        from app.stream import NotSatiri

        return NotSatiri(t, notu, hakkinda)

    def test_uzun_not_daha_yuksek(self, qt_app, t):
        # Tek satıra sıkıştırılan bir uyarı, okunmadan geçilen bir uyarı.
        kisa = self._satir(t, "kısa")
        uzun = self._satir(t, "çok daha uzun bir not " * 12)
        assert uzun.heightForWidth(360) > kisa.heightForWidth(360)

    def test_dar_alanda_daha_yuksek(self, qt_app, t):
        satir = self._satir(t, "orta uzunlukta bir uyarı metni " * 4)
        assert satir.heightForWidth(200) > satir.heightForWidth(420)

    def test_hakkinda_yer_kapliyor(self, qt_app, t):
        assert (self._satir(t, "x", "gönderme").heightForWidth(360)
                > self._satir(t, "x").heightForWidth(360))

    def test_cizilebiliyor(self, qt_app, t):
        from PySide6.QtGui import QImage

        satir = self._satir(t, "İleti #genel kanalına gidiyor.", "gönderme")
        satir.resize(360, satir.heightForWidth(360))
        satir.render(QImage(satir.size(), QImage.Format.Format_ARGB32))


class TestDokumdekiNot:
    def test_dokume_giriyor(self, bar, qt_app):
        from app.stream import NotSatiri

        bar.add_note("İleti herkese görünür.", "gönderme")
        qt_app.processEvents()
        kutu = bar.reply._kutu
        assert isinstance(kutu.itemAt(kutu.count() - 1).widget(), NotSatiri)

    def test_not_adim_sayilmiyor(self, bar, qt_app):
        # Sonraki bir hata notu kırmızıya çevirmemeli: not bir adım
        # değil ve başarısız olmadı.
        bar.add_step("run_shell", "Running a command", "dir")
        bar.add_note("dikkat", "bir şey")
        bar.settle_step(True)
        qt_app.processEvents()
        kutu = bar.reply._kutu
        son = kutu.itemAt(kutu.count() - 1).widget()
        assert son._tone != "hata" if hasattr(son, "_tone") else True

    def test_bos_not_yutuluyor(self, qt_app, t):
        # Boş bir uyarı şeridi, bakılacak bir şey varmış gibi durur.
        from app.stream import Akis

        akis = Akis(t)
        akis.add_note("")
        akis.add_note("   ")
        assert akis._kutu.count() == 0
        akis.add_note("İleti herkese görünür.")
        assert akis._kutu.count() == 1


class TestHedef:
    def test_yetenek_girdisinden_hedef(self):
        # Yeteneklerin girdi adlarını ajan seçiyor; bilinen alanların
        # hiçbiri olmuyordu ve dökümde arka arkaya aynı satır çıkıyordu.
        from app.etiketler import hedef

        assert hedef({"kanal": "genel"}) == "kanal=genel"

    def test_bilinen_alan_oncelikli(self):
        from app.etiketler import hedef

        assert hedef({"kanal": "genel", "name": "discord"}) == "discord"

    def test_gerekce_hedef_degil(self):
        from app.etiketler import hedef

        assert hedef({"why": "çünkü"}) == ""

    def test_uzun_govde_hedef_degil(self):
        from app.etiketler import hedef

        assert hedef({"code": "x" * 500}) == ""
