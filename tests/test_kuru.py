"""Kuru koşu — ajan planlıyor, hiçbir şeye dokunmuyor.

Testlerin ağırlığı **beyaz listede**. Bu özelliğin tek vaadi "hiçbir şey
olmayacak" ve o vaadin kırılma biçimi tek: listeye girmemesi gereken bir
aracın orada olması. Bu yüzden liste hem tek tek hem de toplu olarak
sınanıyor — depoya araç eklendiğinde yeni aracın varsayılan olarak
engellendiği de dâhil.
"""

from __future__ import annotations

import pytest

from backend.agent import kuru as kuru_mod


class TestListe:
    def test_bakan_araclar_serbest(self):
        for arac in ("screenshot", "zoom", "read_file", "list_dir",
                     "read_ui_tree", "office_read", "terminal_read",
                     "remote_read", "side_capture"):
            assert kuru_mod.serbest(arac), arac

    def test_degistiren_araclar_duruyor(self):
        for arac in ("left_click", "double_click", "type", "key", "scroll",
                     "left_click_drag", "run_shell", "launch_app",
                     "write_file", "write_files", "edit_file",
                     "terminal_send", "terminal_open", "office_edit",
                     "office_save", "skill_write", "button_write",
                     "remote_write", "remote_run", "side_launch",
                     "side_act"):
            assert not kuru_mod.serbest(arac), arac

    def test_bilinmeyen_arac_duruyor(self):
        # Beyaz liste olmasının bütün sebebi bu: depoya araç ekleniyor ve
        # yeni bir aracın kuru koşuda sessizce çalışması, fark edilmesi
        # ancak bir şeyi bozmasıyla mümkün bir kusur olurdu.
        assert not kuru_mod.serbest("bir_gun_eklenecek_arac")
        assert not kuru_mod.serbest("")

    def test_yetenekler_listede_degil(self):
        # Yeteneklerin içi ajanın yazdığı Python kodu; adına bakarak ne
        # yaptığını bilmenin yolu yok.
        assert not (kuru_mod.SALT_OKUNUR & {"yetenek", "skill_write"})


class TestNot:
    def test_hata_degil(self):
        # Hata dönseydi ajan kendini düzeltmeye çalışır, aynı çağrıyı
        # başka biçimde dener ve tur "neden çalışmıyor" döngüsüne girerdi.
        metin = kuru_mod.not_metni("run_shell", {"command": "ls"})
        assert metin.startswith("[dry run]")
        assert "carry on planning" in metin

    def test_cagri_gorunuyor(self):
        metin = kuru_mod.not_metni("write_file", {"path": "C:/a.txt"})
        assert "write_file(" in metin and "C:/a.txt" in metin

    def test_uzun_girdi_kirpiliyor(self):
        metin = kuru_mod.not_metni("type", {"text": "x" * 500})
        assert len(metin.splitlines()[0]) < 220


class TestDispatcher:
    def _d(self):
        from backend.agent.dispatch import Dispatcher

        class SahteKill:
            def check(self):
                pass

        d = Dispatcher.__new__(Dispatcher)
        d.kill = SahteKill()
        d.kuru = True
        return d

    def test_degistiren_arac_calismiyor(self):
        d = self._d()
        # `_do_left_click` var ama çağrılmıyor: kesme noktası `run`'ın
        # başında, her aracın içinde değil.
        sonuc = d.run("left_click", {"coordinate": [10, 20]})
        assert not sonuc.is_error
        assert "[dry run]" in sonuc.content

    def test_kuru_kapaliyken_normal_yol(self, monkeypatch):
        d = self._d()
        d.kuru = False
        cagrildi = {}
        monkeypatch.setattr(
            type(d), "_do_wait",
            lambda self, payload: cagrildi.setdefault("evet", True), raising=False,
        )
        monkeypatch.setattr(type(d), "_gate",
                            lambda self, n, p: None, raising=False)
        d.run("wait", {})
        assert cagrildi == {"evet": True}

    def test_onay_kapisi_hic_calismiyor(self, monkeypatch):
        # Kuru koşuda onay sorulmamalı: yapılmayacak bir şey için izin
        # istemek, kullanıcıyı hiçbir şeye karar vermeye zorlamak olurdu.
        d = self._d()
        monkeypatch.setattr(
            type(d), "_gate",
            lambda self, n, p: pytest.fail("kapı çalıştı"), raising=False,
        )
        d.run("run_shell", {"command": "Remove-Item x"})


class TestPrompt:
    def test_kuruyken_bolum_ekleniyor(self):
        from backend.agent.prompts import build_system
        from backend.computer.displays import Display, DisplayMap

        ekranlar = DisplayMap([Display(0, 0, 0, 1920, 1080, True)])
        acik = build_system(ekranlar, 0, kuru=True)
        kapali = build_system(ekranlar, 0, kuru=False)
        assert "Dry run is on" in acik
        assert "Dry run is on" not in kapali
        # Bölüm **sona** ekleniyor: prompt önbelleğe alınıyor ve ortasına
        # blok sokmak, anahtar her çevrildiğinde önbelleği baştan bozardı.
        assert acik.startswith(kapali)


class TestKayit:
    def test_kuru_tur_isaretleniyor(self, tmp_path):
        from backend.agent.kayit import Kayit, kosulari_derle

        kayit = Kayit(tmp_path)
        kayit.tur_basladi("planla", kuru=True)
        kayit.eylem("screenshot", {}, False, "[image]")
        kayit.tur_bitti("şunu yapardım")
        kosular = kosulari_derle(kayit.satirlar())
        assert len(kosular) == 1 and kosular[0].kuru

    def test_normal_tur_isaretlenmiyor(self, tmp_path):
        from backend.agent.kayit import Kayit, kosulari_derle

        kayit = Kayit(tmp_path)
        kayit.tur_basladi("yap")
        kayit.tur_bitti("yaptım")
        assert not kosulari_derle(kayit.satirlar())[0].kuru

    def test_kuru_kosu_tekrar_onerisine_girmiyor(self, tmp_path):
        # Üç kez planlanmış ama hiç yapılmamış bir işi otomatikleştirmeyi
        # önermek, yapılmamış bir işe düğme koymak olurdu.
        from backend.agent.kayit import Kayit, tekrar_bul

        kayit = Kayit(tmp_path)
        for _ in range(4):
            kayit.tur_basladi("aynı iş", kuru=True)
            kayit.eylem("read_file", {}, False)
            kayit.eylem("list_dir", {}, False)
            kayit.tur_bitti("yapardım")
        assert tekrar_bul(kayit.satirlar()) == []


class TestCubuk:
    def test_anahtar_kalici_ve_gorunur(self, qt_app):
        from app import fluent
        from app.commandbar import CommandBar

        bar = CommandBar(fluent.tokens())
        assert not bar.kuru
        gelenler = []
        bar.kuru_degisti.connect(gelenler.append)

        bar.kuru_dugmesi.set_kuru(True)
        assert bar.kuru and gelenler == [True]
        # Küçük bir düğmenin açık olduğunu fark etmemek kolay; alan da
        # değişiyor.
        assert "Dry run" in bar.field.placeholderText()

        bar.kuru_dugmesi.set_kuru(False)
        assert not bar.kuru and gelenler == [True, False]
        assert "Dry run" not in bar.field.placeholderText()

    def test_ayni_degeri_yeniden_vermek_sinyal_yollamiyor(self, qt_app):
        from app import fluent
        from app.commandbar import CommandBar

        bar = CommandBar(fluent.tokens())
        gelenler = []
        bar.kuru_degisti.connect(gelenler.append)
        bar.kuru_dugmesi.set_kuru(False)
        assert gelenler == []


class TestKopru:
    def test_ajan_gelmeden_cevrilen_anahtar_kaybolmuyor(self, qt_app):
        # Anahtar açılışta çevrilebiliyor ve ajan saniyeler sonra
        # kuruluyor. Değer beklemeseydi sessizce yok sayılırdı.
        from app.agent_bridge import AgentBridge

        kopru = AgentBridge()
        kopru.set_kuru(True)
        assert kopru.kuru

        class SahteDispatcher:
            kuru = False

        class SahteAjan:
            dispatcher = SahteDispatcher()

        kopru._agent = SahteAjan()
        kopru.set_kuru(True)
        assert kopru._agent.dispatcher.kuru
