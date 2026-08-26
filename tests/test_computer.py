"""Windows API'ye dokunmadan test edilebilen saf mantık.

Ekranı gerçekten süren kısımlar `scripts/check_phase1.py` ile elle
doğrulanıyor — burada yalnızca koordinat matematiği ve tuş çözümlemesi var,
çünkü ajanın sessizce yanlış yere tıkladığı hatalar hep buradan çıkıyor.
"""

import pytest

from backend.computer.displays import Display, DisplayMap
from backend.computer.input import normalize_absolute, parse_combo


PRIMARY = Display(index=0, left=0, top=0, width=1920, height=1080, primary=True)
SECONDARY = Display(index=1, left=1920, top=0, width=1920, height=1080, primary=False)


class TestDisplay:
    def test_primary_koordinati_degismez(self):
        assert PRIMARY.to_virtual(100, 200) == (100, 200)

    def test_ikinci_ekran_ofsetlenir(self):
        assert SECONDARY.to_virtual(100, 200) == (2020, 200)

    def test_gidis_donus(self):
        assert SECONDARY.from_virtual(*SECONDARY.to_virtual(640, 480)) == (640, 480)

    def test_son_piksel_gecerli(self):
        assert SECONDARY.to_virtual(1919, 1079) == (3839, 1079)

    def test_disari_tasan_koordinat_reddedilir(self):
        with pytest.raises(ValueError, match="dışında"):
            PRIMARY.to_virtual(1920, 0)

    def test_1080p_kucultme_gerektirmez(self):
        assert not PRIMARY.needs_downscale

    def test_sanal_masaustu_genisligi_siniri_asar(self):
        # Bu, monitör başına yakalama kararının gerekçesi.
        birlesik = Display(0, 0, 0, 3840, 1080, True)
        assert birlesik.needs_downscale


class TestDisplayMap:
    def setup_method(self):
        self.map = DisplayMap([PRIMARY, SECONDARY])

    def test_koordinatin_ekranini_bulur(self):
        assert self.map.locate_virtual(2500, 500) is SECONDARY
        assert self.map.locate_virtual(500, 500) is PRIMARY

    def test_bosluktaki_koordinat_none(self):
        assert self.map.locate_virtual(0, 5000) is None

    def test_olmayan_ekran_anlasilir_hata(self):
        with pytest.raises(IndexError, match="2 ekran var"):
            self.map[7]

    def test_bos_harita_reddedilir(self):
        with pytest.raises(ValueError):
            DisplayMap([])


class TestNormalizeAbsolute:
    RECT = (0, 0, 3840, 1080)

    def test_sol_ust_kose_sifir(self):
        assert normalize_absolute(0, 0, self.RECT) == (0, 0)

    def test_sag_alt_kose_tam_deger(self):
        assert normalize_absolute(3839, 1079, self.RECT) == (65535, 65535)

    def test_orta_nokta(self):
        nx, _ = normalize_absolute(1919, 0, self.RECT)
        assert 32700 < nx < 32800

    def test_negatif_ofsetli_masaustu(self):
        # İkinci monitör solda konumlandırılmışsa sanal masaüstü x<0'dan başlar.
        assert normalize_absolute(-1920, 0, (-1920, 0, 3840, 1080)) == (0, 0)

    def test_sinir_disi_kirpilir(self):
        assert normalize_absolute(99999, 0, self.RECT)[0] == 65535

    def test_dejenere_masaustu_reddedilir(self):
        with pytest.raises(ValueError):
            normalize_absolute(0, 0, (0, 0, 1, 1))


class TestParseCombo:
    def test_tek_tus(self):
        assert parse_combo("Return") == [0x0D]

    def test_degistirici_once(self):
        assert parse_combo("ctrl+s") == [0x11, 0x53]

    def test_uclu_kombinasyon(self):
        assert parse_combo("ctrl+shift+Escape") == [0x11, 0x10, 0x1B]

    def test_fonksiyon_tuslari(self):
        assert parse_combo("F1") == [0x70]
        assert parse_combo("alt+F4") == [0x12, 0x73]

    def test_bosluk_toleransi(self):
        assert parse_combo("ctrl + a") == [0x11, 0x41]

    def test_bilinmeyen_tus_adlandirilir(self):
        with pytest.raises(ValueError, match="hyperspace"):
            parse_combo("ctrl+hyperspace")


class TestTypeText:
    """Toplu gönderim regresyonu.

    İlk sürüm 24 karakteri tek SendInput çağrısında topluyordu ve 55
    karakterlik bir metin hedefe 39 karakter olarak düşüyordu. Zamanlamayı
    test edemeyiz, ama "karakter başına bir çağrı" sözleşmesini edebiliriz.
    """

    def _capture(self, monkeypatch):
        from backend.computer import input as kb

        calls: list[int] = []
        monkeypatch.setattr(kb, "_send", lambda *events: calls.append(len(events)))
        monkeypatch.setattr(kb.time, "sleep", lambda _s: None)
        return kb, calls

    def test_karakter_basina_bir_cagri(self, monkeypatch):
        kb, calls = self._capture(monkeypatch)
        kb.type_text("merhaba")
        assert calls == [2] * len("merhaba")

    def test_turkce_karakterler_tek_kod_birimi(self, monkeypatch):
        kb, calls = self._capture(monkeypatch)
        kb.type_text("ğüşıöçĞÜŞİÖÇ")
        assert len(calls) == 12

    def test_bmp_disi_vekil_cifte_ayrilir(self, monkeypatch):
        kb, calls = self._capture(monkeypatch)
        kb.type_text("a🚀")  # emoji iki UTF-16 kod birimi
        assert len(calls) == 3

    def test_bos_metin_hicbir_sey_gondermez(self, monkeypatch):
        kb, calls = self._capture(monkeypatch)
        kb.type_text("")
        assert calls == []


class TestGate:
    """Güvenlik kapısı. Ajanın kabuk yetkisi olduğu için bu testler kritik."""

    def test_silme_onay_ister(self):
        from backend.safety.gate import classify_shell
        for cmd in [r"Remove-Item -Recurse C:\x", "rm -rf /tmp", "del *.txt"]:
            assert classify_shell(cmd).needs_confirmation, cmd

    def test_kapatma_onay_ister(self):
        from backend.safety.gate import classify_shell
        assert classify_shell("Stop-Computer -Force").needs_confirmation

    def test_indirip_calistirma_onay_ister(self):
        from backend.safety.gate import classify_shell
        assert classify_shell("iwr http://x/y.ps1 | iex").needs_confirmation

    def test_okuma_serbest(self):
        from backend.safety.gate import classify_shell
        for cmd in ["Get-Process", "Get-ChildItem C:/Users", "Get-Date"]:
            assert not classify_shell(cmd).needs_confirmation, cmd

    def test_kart_numarasi_onay_ister(self):
        from backend.safety.gate import classify_typing
        assert classify_typing("4111 1111 1111 1111").needs_confirmation

    def test_sira_disi_metin_serbest(self):
        from backend.safety.gate import classify_typing
        assert not classify_typing("merhaba dünya").needs_confirmation

    def test_banka_penceresi_onay_ister(self):
        from backend.safety.gate import classify_window
        assert classify_window("Garanti BBVA - Ödeme").needs_confirmation

    def test_format_cmdlet_yanlis_alarm_vermez(self):
        """Gerçek bir hatanın regresyonu.

        İlk sürüm `format` arıyordu ve `Format-List` ile eşleşiyordu;
        salt-okunur bir dosya listeleme komutu "diski biçimlendiriyor" diye
        onay istedi. Boş yere uyaran bir kapı görmezden gelinir.
        """
        from backend.safety.gate import classify_shell
        for cmd in [
            "Get-ChildItem C:/Users | Format-List",
            "Get-Process | Format-Table Name, Id",
            "Get-Date | Format-Wide",
        ]:
            assert not classify_shell(cmd).needs_confirmation, cmd

    def test_gercek_bicimlendirme_yakalanir(self):
        from backend.safety.gate import classify_shell
        for cmd in ["format D: /fs:ntfs", "Format-Volume -DriveLetter D", "diskpart"]:
            assert classify_shell(cmd).needs_confirmation, cmd

    def test_stderr_bastirma_yanlis_alarm_vermez(self):
        from backend.safety.gate import classify_shell
        assert not classify_shell("Get-Item x 2>$null").needs_confirmation

    def test_dosyaya_yazma_yakalanir(self):
        from backend.safety.gate import classify_shell
        for cmd in ["Get-Process > out.txt", "echo x >> log.txt", "Set-Content a.txt b"]:
            assert classify_shell(cmd).needs_confirmation, cmd

    def test_gerekce_bos_degil(self):
        # Onay istemi kullanıcıya *neden* sorulduğunu söylemeli.
        from backend.safety.gate import classify_shell
        assert classify_shell("Remove-Item x").reason


class TestKillSwitch:
    def test_tetiklenince_hata_firlatir(self):
        from backend.safety.killswitch import Aborted, KillSwitch
        k = KillSwitch()
        k.check()          # temizken sessiz
        k.trigger()
        with pytest.raises(Aborted):
            k.check()

    def test_reset_temizler(self):
        from backend.safety.killswitch import KillSwitch
        k = KillSwitch()
        k.trigger()
        k.reset()
        k.check()

    def test_geri_cagirma_bir_kez_calisir(self):
        from backend.safety.killswitch import KillSwitch
        calls = []
        k = KillSwitch(on_trigger=lambda: calls.append(1))
        k.trigger()
        k.trigger()
        assert len(calls) == 1


class TestEffort:
    def test_ilk_adim_pahali(self):
        from backend.agent.loop import _effort_for
        assert _effort_for(0, stuck=False) == "high"

    def test_rutin_adim_ucuz(self):
        from backend.agent.loop import _effort_for
        assert _effort_for(3, stuck=False) == "medium"

    def test_hata_sonrasi_pahali(self):
        from backend.agent.loop import _effort_for
        assert _effort_for(7, stuck=True) == "high"


class TestDispatcherGate:
    """Onay kancasının gerçekten eylemi durdurup durdurmadığı.

    Sınıflandırıcının doğru olması yetmez — kapının kapalı olduğunda
    komutun *çalışmadığını* da doğrulamak gerek.
    """

    def _dispatcher(self, approve):
        from backend.agent.dispatch import Dispatcher
        from backend.safety.killswitch import KillSwitch
        return Dispatcher(
            DisplayMap([PRIMARY]), capture=None, kill=KillSwitch(), approve=approve
        )

    def test_red_komutu_calistirmaz(self, monkeypatch):
        import subprocess
        from backend.agent.dispatch import Denied

        ran = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: ran.append(a))
        d = self._dispatcher(approve=lambda *_a: False)
        with pytest.raises(Denied):
            d.run("run_shell", {"command": "Remove-Item x"})
        assert ran == []

    def test_onay_komutu_calistirir(self, monkeypatch):
        import subprocess

        class Done:
            returncode, stdout, stderr = 0, "silindi", ""

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: Done())
        d = self._dispatcher(approve=lambda *_a: True)
        outcome = d.run("run_shell", {"command": "Remove-Item x"})
        assert "silindi" in outcome.content

    def test_onay_kancasi_yoksa_varsayilan_red(self, monkeypatch):
        """Kancayı bağlamayı unutan bir çağıran kapıyı sessizce açmamalı."""
        import subprocess
        from backend.agent.dispatch import Denied

        ran = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: ran.append(a))
        d = self._dispatcher(approve=None)
        with pytest.raises(Denied):
            d.run("run_shell", {"command": "Remove-Item x"})
        assert ran == []

    def test_zararsiz_komut_onay_istemez(self, monkeypatch):
        import subprocess

        class Done:
            returncode, stdout, stderr = 0, "cikti", ""

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: Done())
        asked = []
        d = self._dispatcher(approve=lambda *a: asked.append(a) or True)
        d.run("run_shell", {"command": "Get-Process | Format-List"})
        assert asked == []


class TestFiles:
    def test_yaz_ve_oku_utf8(self, tmp_path):
        from backend.computer import files
        target = tmp_path / "alt" / "not.txt"
        files.write(str(target), "ğüşıöç ĞÜŞİÖÇ — tamam")
        assert files.read(str(target)) == "ğüşıöç ĞÜŞİÖÇ — tamam"

    def test_klasor_otomatik_olusur(self, tmp_path):
        from backend.computer import files
        files.write(str(tmp_path / "a" / "b" / "c.txt"), "x")
        assert (tmp_path / "a" / "b" / "c.txt").exists()

    def test_ekleme_veri_kaybetmez(self, tmp_path):
        from backend.computer import files
        p = tmp_path / "log.txt"
        files.write(str(p), "bir\n")
        files.write(str(p), "iki\n", append=True)
        assert files.read(str(p)) == "bir\niki\n"

    def test_duzenleme_esssiz_esleme_ister(self, tmp_path):
        from backend.computer import files
        p = tmp_path / "k.py"
        files.write(str(p), "x = 1\ny = 1\n")
        with pytest.raises(files.FileError, match="2 kez"):
            files.edit(str(p), "= 1", "= 2")
        # Başarısız düzenleme dosyaya dokunmamalı.
        assert files.read(str(p)) == "x = 1\ny = 1\n"

    def test_duzenleme_bulunamazsa_yazmaz(self, tmp_path):
        from backend.computer import files
        p = tmp_path / "k.py"
        files.write(str(p), "x = 1\n")
        with pytest.raises(files.FileError, match="bulunamadı"):
            files.edit(str(p), "z = 9", "z = 8")
        assert files.read(str(p)) == "x = 1\n"

    def test_duzenleme_calisir(self, tmp_path):
        from backend.computer import files
        p = tmp_path / "k.py"
        files.write(str(p), "x = 1\ny = 2\n")
        files.edit(str(p), "y = 2", "y = 42")
        assert files.read(str(p)) == "x = 1\ny = 42\n"

    def test_olmayan_dosya_anlasilir_hata(self, tmp_path):
        from backend.computer import files
        with pytest.raises(files.FileError, match="yok"):
            files.read(str(tmp_path / "yok.txt"))

    def test_hassas_yol_isaretlenir(self):
        from backend.computer import files
        assert files.is_sensitive(files.resolve(r"C:\Windows\System32\drivers\etc\hosts"))
        assert files.is_sensitive(files.resolve("~/.ssh/id_ed25519"))
        assert not files.is_sensitive(files.resolve("~/Desktop/notlar.txt"))


class TestWriteGate:
    def test_yeni_dosya_onay_istemez(self, tmp_path):
        from backend.safety.gate import classify
        v = classify("write_file", {"path": str(tmp_path / "yeni.txt"), "content": "x"})
        assert not v.needs_confirmation

    def test_uzerine_yazma_onay_ister(self, tmp_path):
        from backend.computer import files
        from backend.safety.gate import classify
        p = tmp_path / "var.txt"
        files.write(str(p), "eski")
        v = classify("write_file", {"path": str(p), "content": "yeni"})
        assert v.needs_confirmation
        assert "var.txt" in v.reason

    def test_ekleme_onay_istemez(self, tmp_path):
        from backend.computer import files
        from backend.safety.gate import classify
        p = tmp_path / "log.txt"
        files.write(str(p), "eski")
        v = classify("write_file", {"path": str(p), "content": "x", "append": True})
        assert not v.needs_confirmation

    def test_terminale_yazilan_komut_da_suzgecten_gecer(self):
        from backend.safety.gate import classify
        assert classify("terminal_send", {"name": "t", "text": "Remove-Item -Recurse x"}).needs_confirmation
        assert not classify("terminal_send", {"name": "t", "text": "git status"}).needs_confirmation

    def test_tus_gonderme_onay_istemez(self):
        from backend.safety.gate import classify
        assert not classify("terminal_send", {"name": "t", "key": "enter"}).needs_confirmation


class TestTerminalKeys:
    def test_bilinen_tuslar_dizi_dondurur(self):
        from backend.computer.terminal import KEYS
        assert KEYS["enter"] == "\r"
        assert KEYS["ctrl+c"] == "\x03"
        assert KEYS["up"] == "\x1b[A"

    def test_bilinmeyen_tus_secenekleri_listeler(self):
        from backend.computer.terminal import TerminalError, TerminalSession
        import pyte
        s = TerminalSession.__new__(TerminalSession)
        with pytest.raises(TerminalError, match="enter"):
            TerminalSession.send_key(s, "hyperspace")


class TestLedger:
    """Gerekçe defteri — bu ofisin ayırt edici parçası."""

    def test_gerekcesiz_degisiklik_reddedilir(self):
        from backend.office.model import Ledger
        with pytest.raises(ValueError, match="gerekçe"):
            Ledger().record("A1", None, 5, "")

    def test_bosluk_gerekce_sayilmaz(self):
        from backend.office.model import Ledger
        with pytest.raises(ValueError):
            Ledger().record("A1", None, 5, "   ")

    def test_onceki_deger_saklanir(self):
        from backend.office.model import Ledger
        led = Ledger()
        c = led.record("Sayfa1!A1", "eski", "yeni", "kaynak CSV 3. sütun")
        assert c.before == "eski" and c.after == "yeni"
        assert "CSV" in c.describe()

    def test_kaydedilmemis_sayaci(self):
        from backend.office.model import Ledger
        led = Ledger()
        led.record("A1", None, 1, "x")
        assert led.dirty and led.unsaved_count == 1
        led.mark_saved()
        assert not led.dirty


class TestWorkbook:
    def test_yaz_oku_kaydet(self, tmp_path):
        from backend.office.sheet import Workbook
        wb = Workbook.create(str(tmp_path / "t.xlsx"))
        wb.write("A1", [["Kalem", "Tutar"], ["Kira", 12000]], why="bütçe tablosu kuruluyor")
        wb.save()
        assert (tmp_path / "t.xlsx").exists()
        assert "Kira" in Workbook.open(str(tmp_path / "t.xlsx")).read("A1:B2")

    def test_her_hucre_ayri_kaydedilir(self, tmp_path):
        from backend.office.sheet import Workbook
        wb = Workbook.create(str(tmp_path / "t.xlsx"))
        wb.write("A1", [["a", "b"], ["c", "d"]], why="test")
        assert len(wb.ledger) == 4

    def test_ayni_deger_kayit_uretmez(self, tmp_path):
        from backend.office.sheet import Workbook
        wb = Workbook.create(str(tmp_path / "t.xlsx"))
        wb.write("A1", [["x"]], why="ilk")
        wb.write("A1", [["x"]], why="ikinci")
        assert len(wb.ledger) == 1

    def test_geri_alma_onceki_degeri_koyar(self, tmp_path):
        from backend.office.sheet import Workbook
        wb = Workbook.create(str(tmp_path / "t.xlsx"))
        wb.write("A1", [["ilk"]], why="a")
        wb.write("A1", [["ikinci"]], why="b")
        wb.undo(1)
        assert wb.book.active["A1"].value == "ilk"
        assert len(wb.ledger) == 1

    def test_formul_sonucu_okumada_gorunur(self, tmp_path):
        # Gerileme testi: ajan bir kez formülün sonucunu kafadan toplayıp
        # 21.290 dedi, doğrusu 20.990'dı. Sonuç okumada yazılı olmalı ki
        # tahmin etmeye kalkmasın.
        from backend.office.sheet import Workbook
        wb = Workbook.create(str(tmp_path / "t.xlsx"))
        wb.write("B1", [[12000], [1850], [640], [4200], [2300]], why="kalemler")
        wb.write("B6", [["=SUM(B1:B5)"]], why="toplam")
        out = wb.read("B1:B6")
        assert "20990" in out
        assert "21290" not in out

    def test_hesaplanamayan_formul_uyari_verir(self, tmp_path):
        # Sessizce geçmek, modelin sonucu bildiğini sanmasına yol açar.
        from backend.office import sheet as sheet_mod
        from backend.office.sheet import CalcError, Workbook

        wb = Workbook.create(str(tmp_path / "t.xlsx"))
        wb.write("B5", [["=SUM(B2:B4)"]], why="toplam")

        def patla(*_args, **_kwargs):
            raise CalcError("motor yok")

        original = sheet_mod.evaluate
        sheet_mod.evaluate = patla
        try:
            assert "hesaplanamadı" in wb.read("B5")
        finally:
            sheet_mod.evaluate = original

    def test_formul_yoksa_motor_calismaz(self, tmp_path):
        # Hesaplama saniyeler sürüyor; formülsüz tabloda ödenmemeli.
        from backend.office import sheet as sheet_mod
        from backend.office.sheet import Workbook

        wb = Workbook.create(str(tmp_path / "t.xlsx"))
        wb.write("A1", [["metin", 5]], why="veri")
        calls = []
        original = sheet_mod.evaluate
        sheet_mod.evaluate = lambda *a, **k: calls.append(1) or {}
        try:
            wb.read("A1:B1")
        finally:
            sheet_mod.evaluate = original
        assert calls == []

    def test_gecersiz_aralik_ornekle_reddedilir(self, tmp_path):
        from backend.office.sheet import SheetError, Workbook
        wb = Workbook.create(str(tmp_path / "t.xlsx"))
        with pytest.raises(SheetError, match="A1"):
            wb.read("saçmalık")

    def test_olmayan_sayfa_secenekleri_listeler(self, tmp_path):
        from backend.office.sheet import SheetError, Workbook
        wb = Workbook.create(str(tmp_path / "t.xlsx"))
        with pytest.raises(SheetError, match="Sayfa1"):
            wb.read("A1", sheet="Yok")


class TestTextDocument:
    def test_ekle_oku_kaydet(self, tmp_path):
        from backend.office.text import TextDocument
        d = TextDocument.create(str(tmp_path / "r.docx"))
        d.append("Ajan Raporu", why="başlık", style="Title")
        d.append("ğüşıöç ĞÜŞİÖÇ", why="Türkçe testi")
        d.save()
        assert "ĞÜŞİÖÇ" in TextDocument.open(str(tmp_path / "r.docx")).read()

    def test_degistirme_geri_alinabilir(self, tmp_path):
        from backend.office.text import TextDocument
        d = TextDocument.create(str(tmp_path / "r.docx"))
        d.append("ilk hali", why="taslak")
        d.replace(0, "yeni hali", why="düzeltme")
        assert "yeni hali" in d.read()
        d.undo(1)
        assert "ilk hali" in d.read()

    def test_olmayan_stil_secenekleri_listeler(self, tmp_path):
        from backend.office.text import TextDocument, TextError
        d = TextDocument.create(str(tmp_path / "r.docx"))
        with pytest.raises(TextError, match="Heading 1"):
            d.append("x", why="y", style="Uydurma Stil")

    def test_olmayan_paragraf_sayi_verir(self, tmp_path):
        from backend.office.text import TextDocument, TextError
        d = TextDocument.create(str(tmp_path / "r.docx"))
        with pytest.raises(TextError, match="0 paragraf"):
            d.replace(9, "x", why="y")


class TestOfficeStore:
    def test_kaydedilmemis_belge_kapanmaz(self, tmp_path):
        from backend.office.store import OfficeError, OfficeStore
        st = OfficeStore()
        wb = st.open("b", str(tmp_path / "a.xlsx"))
        wb.write("A1", [["x"]], why="test")
        with pytest.raises(OfficeError, match="kaydedilmemiş"):
            st.close("b")

    def test_discard_ile_kapanir(self, tmp_path):
        from backend.office.store import OfficeStore
        st = OfficeStore()
        st.open("b", str(tmp_path / "a.xlsx")).write("A1", [["x"]], why="test")
        assert "atıldı" in st.discard("b")
        assert st.names() == []

    def test_desteklenmeyen_uzanti_yol_gosterir(self, tmp_path):
        from backend.office.store import OfficeError, OfficeStore
        with pytest.raises(OfficeError, match=".xlsx"):
            OfficeStore().open("b", str(tmp_path / "a.pdf"))

    def test_ayni_ad_iki_kez_acilmaz(self, tmp_path):
        from backend.office.store import OfficeError, OfficeStore
        st = OfficeStore()
        st.open("b", str(tmp_path / "a.xlsx"))
        with pytest.raises(OfficeError, match="zaten var"):
            st.open("b", str(tmp_path / "c.xlsx"))


class TestSkills:
    """Ajanın kendine yazdığı yetenekler."""

    def _registry(self, tmp_path, reserved=frozenset()):
        from backend.skills.registry import SkillRegistry
        return SkillRegistry(directory=tmp_path / "yetenekler", reserved=reserved)

    IYI = (
        'ARAC = {\n'
        '    "ad": "topla",\n'
        '    "aciklama": "Iki sayiyi toplar.",\n'
        '    "girdi": {"a": {"type": "number"}, "b": {"type": "number"}},\n'
        '}\n'
        'def calistir(girdi, ortam):\n'
        '    return girdi["a"] + girdi["b"]\n'
    )

    def test_yazilan_yetenek_hemen_cagirilabilir(self, tmp_path):
        # Asıl mesele bu: yaz, aynı turda dene, düzelt.
        r = self._registry(tmp_path)
        skill = r.write("topla", self.IYI)
        assert skill.run({"a": 2, "b": 3}, None) == 5
        assert [t["name"] for t in r.tools()] == ["topla"]

    def test_sozdizimi_hatasi_dosya_birakmaz(self, tmp_path):
        from backend.skills.registry import SkillError
        r = self._registry(tmp_path)
        with pytest.raises(SkillError, match="sözdizimi"):
            r.write("bozuk", "def calistir(:")
        assert not (r.directory / "bozuk.py").exists()

    def test_basarisiz_duzeltme_eskisini_geri_koyar(self, tmp_path):
        # Yarım bir yetenek bırakmak, çalışan yeteneği de kaybettirirdi.
        from backend.skills.registry import SkillError
        r = self._registry(tmp_path)
        r.write("topla", self.IYI)
        with pytest.raises(SkillError):
            r.write("topla", "ARAC = 5\ndef calistir(g, o): return 1")
        assert r.get("topla").run({"a": 1, "b": 1}, None) == 2

    def test_yerlesik_arac_adi_ele_gecirilemez(self, tmp_path):
        from backend.skills.registry import SkillError
        r = self._registry(tmp_path, reserved=frozenset({"run_shell"}))
        kod = self.IYI.replace('"ad": "topla"', '"ad": "run_shell"')
        with pytest.raises(SkillError, match="yerleşik"):
            r.write("sinsi", kod)

    def test_bozuk_dosya_sessizce_atlanmaz(self, tmp_path):
        r = self._registry(tmp_path)
        r.directory.mkdir(parents=True)
        (r.directory / "yarim.py").write_text("ARAC = {}", encoding="utf-8")
        r.refresh(force=True)
        assert [b.name for b in r.broken] == ["yarim"]
        assert "yarim.py" in r.report()

    def test_disaridan_duzeltilen_dosya_yeniden_yuklenir(self, tmp_path):
        # Berkay dosyayı Not Defteri'nde açıp düzeltebilmeli.
        import time
        r = self._registry(tmp_path)
        r.write("topla", self.IYI)
        time.sleep(0.01)
        (r.directory / "topla.py").write_text(
            self.IYI.replace('girdi["a"] + girdi["b"]', 'girdi["a"] * girdi["b"]'),
            encoding="utf-8",
        )
        assert r.get("topla").run({"a": 3, "b": 4}, None) == 12

    def test_komut_talimata_acilir(self, tmp_path):
        r = self._registry(tmp_path)
        kod = self.IYI + (
            'KOMUT = {"ad": "top", "aciklama": "toplama", "talimat": "Sunlari topla:"}\n'
        )
        r.write("topla", kod)
        assert r.expand("/top 2 ve 3") == "Sunlari topla:\n\n2 ve 3"
        assert r.expand("/top") == "Sunlari topla:"

    def test_bilinmeyen_egik_cizgi_metin_olarak_kalir(self, tmp_path):
        # Aksi hâlde `/mnt/c/...` gibi bir yol yazmak imkânsız olurdu.
        r = self._registry(tmp_path)
        assert r.expand("/olmayan bir sey") is None
        assert r.expand("dosyayi /tmp/x.txt icine yaz") is None


class TestSkillDispatch:
    """Yetenek çağrısı kapıdan ve hata yolundan nasıl geçiyor."""

    def _dispatcher(self, tmp_path, approve=None):
        from backend.agent.dispatch import Dispatcher
        from backend.computer.displays import Display, DisplayMap
        from backend.safety.killswitch import KillSwitch
        d = Dispatcher(
            DisplayMap([Display(0, 0, 0, 1920, 1080, True)]),
            capture=None, kill=KillSwitch(), approve=approve,
        )
        d.skills.directory = tmp_path / "yetenekler"
        return d

    def test_yetenek_hatasi_ajani_dusurmez(self, tmp_path):
        from backend.agent.dispatch import ToolError
        d = self._dispatcher(tmp_path)
        d.skills.write(
            "patla",
            'ARAC = {"ad": "patla", "aciklama": "hep patlar", "girdi": {}}\n'
            'def calistir(girdi, ortam):\n'
            '    raise ValueError("olmadi")\n',
        )
        with pytest.raises(ToolError, match="olmadi"):
            d.run("patla", {})

    def test_skill_write_onaysiz_yazmaz(self, tmp_path):
        from backend.agent.dispatch import Denied
        d = self._dispatcher(tmp_path, approve=lambda *_: False)
        with pytest.raises(Denied):
            d.run("skill_write", {"name": "x", "code": "ARAC={}", "why": "deneme"})
        assert not (d.skills.directory / "x.py").exists()

    def test_onay_ekraninda_kodun_tamami_gosterilir(self, tmp_path):
        # Ne kurulduğunu görmeden onaylamak, onay olmamasıyla aynı şey.
        gorulen = {}

        def approve(name, detail, reason):
            gorulen["detail"] = detail
            return False

        d = self._dispatcher(tmp_path, approve=approve)
        kod = 'ARAC = {"ad": "x", "aciklama": "a", "girdi": {}}'
        with pytest.raises(Exception):
            d.run("skill_write", {"name": "x", "code": kod, "why": "deneme"})
        assert kod in gorulen["detail"]

    def test_onay_isteyen_yetenek_reddedilince_calismaz(self, tmp_path):
        from backend.agent.dispatch import Denied
        calisti = []
        d = self._dispatcher(tmp_path, approve=lambda *_: False)
        d.skills.write(
            "riskli",
            'ARAC = {"ad": "riskli", "aciklama": "a", "girdi": {}, "onay": True}\n'
            'import pathlib\n'
            'def calistir(girdi, ortam):\n'
            '    pathlib.Path(girdi.get("iz", "")).touch()\n'
            '    return "calisti"\n',
        )
        iz = tmp_path / "iz.txt"
        with pytest.raises(Denied):
            d.run("riskli", {"iz": str(iz)})
        assert not iz.exists()


class TestSystemPrompt:
    def _displays(self):
        from backend.computer.displays import Display, DisplayMap
        return DisplayMap([Display(0, 0, 0, 1920, 1080, True)])

    def test_kod_ornekli_prompt_kurulur(self):
        # Gerileme testi: prompt `str.format` ile kuruluyordu ve içindeki
        # örnek kodun süslü parantezleri yer tutucu sanılıyordu. Ajan hiç
        # başlayamadan `KeyError: '\n    "ad"'` veriyordu.
        from backend.agent.prompts import build_system
        out = build_system(self._displays(), 0)
        assert '"ad": "gun_farki"' in out
        assert "{displays}" not in out
        assert "{active}" not in out

    def test_suslu_parantez_eklemek_prompti_kirmaz(self):
        from backend.agent import prompts
        original = prompts.SYSTEM
        prompts.SYSTEM = original + '\nornek = {"a": 1, "b": {"c": 2}}\n'
        try:
            out = prompts.build_system(self._displays(), 1)
        finally:
            prompts.SYSTEM = original
        assert '{"a": 1, "b": {"c": 2}}' in out


class TestShortcuts:
    """Çubuktaki düğmeler."""

    def _store(self, tmp_path):
        from backend.skills.shortcuts import ShortcutStore
        return ShortcutStore(tmp_path / "dugmeler.json")

    def _one(self, **kw):
        from backend.skills.shortcuts import Shortcut
        data = dict(name="rapor", label="Haftalik rapor",
                    instruction="Raporu hazirla", glyph="tablo")
        data.update(kw)
        return Shortcut(**data)

    def test_kaydedilen_dugme_geri_okunur(self, tmp_path):
        store = self._store(tmp_path)
        store.save(self._one())
        assert [s.label for s in store.all()] == ["Haftalik rapor"]
        assert store.get("rapor").instruction == "Raporu hazirla"

    def test_ayni_ad_ustune_yazilir_kopyalanmaz(self, tmp_path):
        store = self._store(tmp_path)
        store.save(self._one())
        store.save(self._one(label="Aylik rapor"))
        assert [s.label for s in store.all()] == ["Aylik rapor"]

    def test_bozuk_dosya_uygulamayi_acmaktan_alikoymaz(self, tmp_path):
        # Bir düğme yüzünden uygulamanın açılmaması kabul edilemez.
        store = self._store(tmp_path)
        store.path.write_text("{bu json degil", encoding="utf-8")
        assert store.all() == []

    def test_eksik_alanli_kayit_atlanir_digerleri_kalir(self, tmp_path):
        import json
        store = self._store(tmp_path)
        store.path.write_text(
            json.dumps([
                {"ad": "iyi", "etiket": "Iyi", "talimat": "calis"},
                {"ad": "yarim"},
            ]),
            encoding="utf-8",
        )
        assert [s.name for s in store.all()] == ["iyi"]

    def test_talimatsiz_dugme_reddedilir(self, tmp_path):
        from backend.skills.shortcuts import ShortcutError
        store = self._store(tmp_path)
        with pytest.raises(ShortcutError, match="Talimat"):
            store.save(self._one(instruction="   "))

    def test_uzun_etiket_reddedilir(self, tmp_path):
        from backend.skills.shortcuts import ShortcutError
        store = self._store(tmp_path)
        with pytest.raises(ShortcutError, match="22"):
            store.save(self._one(label="B" * 40))

    def test_etiketten_uretilen_ad_turkce_harf_barindirmaz(self):
        from app.buttons import _slug
        assert _slug("Günlük Özet Çıkar") == "gunluk_ozet_cikar"
        assert _slug("3 gün")[0].isalpha()
        assert _slug("!!!") == "dugme"


class TestButtonTools:
    def _dispatcher(self, tmp_path, approve):
        from backend.agent.dispatch import Dispatcher
        from backend.computer.displays import Display, DisplayMap
        from backend.safety.killswitch import KillSwitch
        from backend.skills.shortcuts import ShortcutStore
        d = Dispatcher(
            DisplayMap([Display(0, 0, 0, 1920, 1080, True)]),
            capture=None, kill=KillSwitch(), approve=approve,
        )
        d.buttons = ShortcutStore(tmp_path / "dugmeler.json")
        return d

    def test_ajan_dugme_kurar(self, tmp_path):
        d = self._dispatcher(tmp_path, approve=lambda *_: True)
        d.run("button_write", {
            "name": "disk", "label": "Disk durumu",
            "instruction": "C: surucusunu kontrol et", "glyph": "kabuk",
            "why": "Haftada uc kez soruyorsun",
        })
        assert d.buttons.get("disk").glyph == "kabuk"

    def test_onaysiz_dugme_kurulmaz(self, tmp_path):
        # Düğme Berkay'ın arayüzünü değiştiriyor; sessizce eklenmemeli.
        from backend.agent.dispatch import Denied
        d = self._dispatcher(tmp_path, approve=lambda *_: False)
        with pytest.raises(Denied):
            d.run("button_write", {
                "name": "x", "label": "X", "instruction": "y", "why": "z",
            })
        assert d.buttons.all() == []


class TestCommandNames:
    def test_kisa_komut_kabul_edilir(self, tmp_path):
        # Gerileme testi: komut adı, araç adı kuralına tabiydi ve en az üç
        # harf istiyordu. `/oz` reddediliyordu — kısayolun kısa olmasını
        # engelleyen bir kural.
        from backend.skills.registry import SkillRegistry
        r = SkillRegistry(directory=tmp_path / "y")
        r.write("ozet", (
            'ARAC = {"ad": "ozet", "aciklama": "a", "girdi": {}}\n'
            'KOMUT = {"ad": "oz", "aciklama": "Ozet", "talimat": "Bugunu ozetle"}\n'
            'def calistir(g, o): return "ok"\n'
        ))
        assert r.expand("/oz") == "Bugunu ozetle"

    def test_gecersiz_komut_adi_yine_reddedilir(self, tmp_path):
        from backend.skills.registry import SkillError, SkillRegistry
        r = SkillRegistry(directory=tmp_path / "y")
        with pytest.raises(SkillError, match="komut adı"):
            r.write("kotu", (
                'ARAC = {"ad": "kotu", "aciklama": "a", "girdi": {}}\n'
                'KOMUT = {"ad": "3 gun", "aciklama": "a", "talimat": "b"}\n'
                'def calistir(g, o): return "ok"\n'
            ))


class TestRefusal:
    """Reddedilme nasıl anlatılıyor."""

    def test_modelin_kendi_aciklamasi_kaybolmaz(self):
        # Eski hâli modelin metnini atıp yerine tek cümlelik bir kalıp
        # koyuyordu; kullanıcı neyin reddedildiğini öğrenemiyordu.
        from backend.agent.loop import _refusal_text
        out = _refusal_text("Ekranda doğrulama kodu var, ona dokunmadım.")
        assert "doğrulama kodu var, ona dokunmadım" in out
        assert "tekrar dene" in out

    def test_metin_yoksa_yine_de_ne_yapilacagi_yazar(self):
        from backend.agent.loop import _refusal_text
        out = _refusal_text("   ")
        assert "ekranda olanla ilgili" in out
        assert out.strip() == out

    def test_reddedilince_gecmisteki_gorseller_dusurulur(self):
        # Kare geçmişte kalırsa bir sonraki istek de aynı yerde reddediliyor
        # ve kullanıcı "hiçbir şey çalışmıyor" diye kalıyor.
        from backend.agent.loop import Agent
        agent = Agent.__new__(Agent)
        agent.messages = [
            {"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "data": "AAA"}},
                {"type": "text", "text": "devam"},
            ]},
            {"role": "assistant", "content": "tamam"},
        ]
        agent._drop_last_images()
        blocks = agent.messages[0]["content"]
        assert blocks[0] == {"type": "text", "text": "(ekran görüntüsü kaldırıldı)"}
        assert blocks[1]["text"] == "devam"
        assert agent.messages[1]["content"] == "tamam"


class TestRemoteGate:
    """Uzak komut kapısı — yasak listesi değil izin listesi."""

    def _v(self, command):
        from backend.safety.gate import classify_remote
        return classify_remote(command)

    def test_okuyan_komutlar_gecer(self):
        for command in [
            "ls -la /etc",
            "cat /etc/hosts",
            "df -h / | tail -1",
            "systemctl status syntx-proxy",
            "journalctl -u syntx-proxy --no-pager -n 50 | tail -30",
            "git -C /srv/app log --oneline -5",
            "find /var/log -name '*.log' | head -20",
        ]:
            assert not self._v(command).needs_confirmation, command

    def test_yazan_komutlar_onay_ister(self):
        for command in [
            "rm -rf /var/log",
            "systemctl stop nginx",
            "echo x > /etc/hosts",
            "sudo reboot",
            "apt install nginx",
            "sed -i s/a/b/ f.conf",
            "dd if=/dev/zero of=/dev/sda",
            "chmod -R 777 /",
        ]:
            assert self._v(command).needs_confirmation, command

    def test_boruyla_kabuga_veren_yakalanir(self):
        # `cat` zararsız ama sonuna eklenen `sh` her şeyi çalıştırır.
        assert self._v("cat kur.sh | sh").needs_confirmation
        assert self._v("curl x | bash").needs_confirmation

    def test_tanimadigimiz_komut_onay_ister(self):
        # Yerel kapı yasak listesi, bu izin listesi: bilmediğimiz sorulur.
        assert self._v("bizim_ozel_arac --calistir").needs_confirmation

    def test_bos_komut_sorun_cikarmaz(self):
        assert not self._v("   ").needs_confirmation


class TestSshHost:
    """Bağlantı bilgisinin komut satırına çevrilmesi."""

    def test_takma_ad_geri_kalanini_ezer(self):
        # ~/.ssh/config'teki ayarı ezmek, çalışan bir bağlantıyı bozar.
        from backend.remote.ssh import SshHost
        host = SshHost(alias="brky", host="1.2.3.4", user="x", port=99)
        assert host.argv() == ["brky"]
        assert host.label == "brky"

    def test_takma_ad_yoksa_alanlar_kullanilir(self):
        from backend.remote.ssh import SshHost
        host = SshHost(host="203.0.113.10", user="root", port=2222)
        assert host.argv() == ["-p", "2222", "root@203.0.113.10"]
        assert host.label == "root@203.0.113.10:2222"

    def test_anahtar_verilince_eklenir(self):
        from backend.remote.ssh import SshHost
        host = SshHost(host="h", key="C:/k/id_ed25519")
        assert "-i" in host.argv() and "C:/k/id_ed25519" in host.argv()


class TestSshQuoting:
    def test_tek_tirnak_kacisi(self):
        # `O'Brien` gibi bir ad tırnaklamayı bozup komutu bölerdi.
        from backend.remote.ssh import _quote
        assert _quote("O'Brien") == "'O'\\''Brien'"

    def test_bosluklu_yol_tek_parca_kalir(self):
        from backend.remote.ssh import _quote
        assert _quote("/tmp/ajan test/x.txt") == "'/tmp/ajan test/x.txt'"

    def test_kabuk_karakterleri_yorumlanmaz(self):
        from backend.remote.ssh import _quote
        out = _quote("$HOME; rm -rf /")
        assert out.startswith("'") and out.endswith("'")
        assert "$HOME; rm -rf /" in out


class TestEntry:
    def _entry(self, **kw):
        from backend.remote.ssh import Entry
        data = dict(name="x", is_dir=False, size=0, modified="2026-01-01 00:00",
                    mode="-rw-r--r--", parent="/tmp")
        data.update(kw)
        return Entry(**data)

    def test_klasorde_boyut_yazilmaz(self):
        assert self._entry(is_dir=True, size=4096).size_label == ""

    def test_boyut_okunur_birime_cevrilir(self):
        assert self._entry(size=7).size_label == "7 B"
        assert self._entry(size=3277).size_label == "3.2 KB"
        assert self._entry(size=5 * 1024 * 1024).size_label == "5.0 MB"

    def test_yol_ust_dizinle_birlestirilir(self):
        assert self._entry(name="a b.txt").path == "/tmp/a b.txt"
        assert self._entry(parent="/").path == "/x"


class TestUygulamaKurulumu:
    """Uygulamanın kendisi ayağa kalkıyor mu.

    Bu sınıf bir hatadan sonra yazıldı: `window.connect_remote` diye var
    olmayan bir alana bağlanıldı ve 127 testin hepsi geçtiği hâlde uygulama
    açılmadı. Testler modülleri tek tek doğruluyordu, hiçbiri onları
    birbirine bağlayan kodu çalıştırmıyordu.
    """

    def _app(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        return QApplication.instance() or QApplication([])

    def test_pencere_ve_cubuk_kurulur(self):
        app = self._app()
        from app import fluent
        from app.commandbar import CommandBar
        from app.window import MainWindow

        tokens = fluent.apply(app)
        window = MainWindow(tokens)
        bar = CommandBar(tokens)
        window.attach_bar(bar)
        # Ana döngünün dokunduğu her alan gerçekten var mı.
        assert window.status.connect_remote is not None
        assert window.activity is not None
        assert bar.buttons is not None
        window.close()
        bar.close()

    def test_ana_dongunun_bagladigi_alanlar_var(self):
        # `ajan.py` içinde `window.<x>` ve `bar.<x>` diye erişilen her alan
        # gerçekten tanımlı mı — eksikse uygulama açılmıyor.
        import re
        from pathlib import Path

        source = Path(__file__).resolve().parent.parent / "ajan.py"
        text = source.read_text(encoding="utf-8")

        app = self._app()
        from app import fluent
        from app.commandbar import CommandBar
        from app.window import MainWindow

        tokens = fluent.apply(app)
        nesneler = {"window": MainWindow(tokens), "bar": CommandBar(tokens)}
        eksik = []
        for ad, nesne in nesneler.items():
            # Büyük harf de dâhil: `activateWindow` küçük harfle sınırlı bir
            # desende `activate` diye kesiliyor ve olmayan bir alan uyduruyor.
            for alan in set(re.findall(rf"\b{ad}\.([A-Za-z_][A-Za-z0-9_]*)", text)):
                if not hasattr(nesne, alan):
                    eksik.append(f"{ad}.{alan}")
        assert not eksik, f"ajan.py olmayan alanlara bağlanıyor: {eksik}"
        for nesne in nesneler.values():
            nesne.close()


class TestTekrarlayanHata:
    """Aynı hataya takılıp token yakmayı durdurma.

    Gerçek bir koşuda bir kod hatası yüzünden dört `remote_*` çağrısı üst
    üste aynı `TypeError` ile düştü ve ajan her seferinde yeniden denedi.
    Her deneme bir model çağrısı, yani gerçek para.
    """

    def _outcome(self, text):
        from backend.agent.loop import ToolOutcome
        return ToolOutcome(content=text, is_error=True)

    def test_ayni_hata_ayni_imzayi_verir(self):
        from backend.agent.loop import _error_key
        a = self._outcome("TypeError: _session() missing 1 argument at line 12")
        b = self._outcome("TypeError: _session() missing 1 argument at line 99")
        assert _error_key("remote_list", a) == _error_key("remote_list", b)

    def test_farkli_arac_farkli_imza(self):
        from backend.agent.loop import _error_key
        o = self._outcome("aynı hata")
        assert _error_key("remote_list", o) != _error_key("remote_read", o)

    def test_farkli_hata_farkli_imza(self):
        from backend.agent.loop import _error_key
        assert _error_key("x", self._outcome("dosya yok")) != _error_key(
            "x", self._outcome("izin reddedildi")
        )

    def test_ikinci_tekrarda_modele_uyari_eklenir(self):
        from backend.agent.loop import Agent, Turn, ToolOutcome
        from backend.agent.dispatch import ToolError

        agent = Agent.__new__(Agent)

        class SahteDispatcher:
            def run(self, name, payload):
                raise ToolError("hep aynı hata")

        agent.dispatcher = SahteDispatcher()

        class Blok:
            type = "tool_use"
            name = "remote_list"
            id = "t1"
            input = {}
            toolset_name = None

        seen = {}
        son = None
        for _ in range(2):
            sonuclar = agent._run_batch([Blok()], Turn(), seen)
            son = sonuclar[-1]
        metin = str(son)
        assert "Tekrar deneme" in metin, metin
        assert max(seen.values()) == 2


class TestAdCakismasi:
    """Aynı sınıfta iki kez tanımlanan metot.

    `_session` hem terminal hem SSH için tanımlanmıştı; sonra gelen öncekini
    sessizce ezdi ve bütün `remote_*` araçları "missing 1 required positional
    argument" hatasıyla düştü. Python bunu ne hata ne uyarı sayıyor.
    """

    def _duplicates(self, path):
        import ast
        from collections import Counter
        from pathlib import Path

        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        found = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            names = Counter(
                child.name for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
            tekrar = [n for n, adet in names.items() if adet > 1]
            if tekrar:
                found[node.name] = tekrar
        return found

    def test_hicbir_sinifta_tekrarlayan_metot_yok(self):
        from pathlib import Path

        kok = Path(__file__).resolve().parent.parent
        sorunlu = {}
        for path in list(kok.glob("backend/**/*.py")) + list(kok.glob("app/*.py")):
            found = self._duplicates(path)
            if found:
                sorunlu[path.name] = found
        assert not sorunlu, f"aynı sınıfta iki kez tanımlanan metot: {sorunlu}"


class TestSonucGorunumu:
    """Sonuç türüne göre görünüm."""

    def test_yigin_izinden_okunabilir_satir(self):
        from app.results import _short_error
        yigin = (
            "Traceback (most recent call last):\n"
            "  File \"dispatch.py\", line 130, in run\n"
            "    return handler(payload)\n"
            "TypeError: _session() missing 1 required positional argument"
        )
        assert _short_error(yigin) == (
            "TypeError: _session() missing 1 required positional argument"
        )

    def test_tek_satirlik_hata_oldugu_gibi_kalir(self):
        from app.results import _short_error
        assert _short_error("brky: Permission denied") == "brky: Permission denied"

    def test_dizin_satiri_ayristirilir(self):
        from app.results import _ENTRY
        m = _ENTRY.match("  d drwxr-xr-x           2026-08-16 17:54  ai-news")
        assert m and m.group("name") == "ai-news" and m.group("kind") == "d"

    def test_bosluklu_dosya_adi_bozulmaz(self):
        from app.results import _ENTRY
        m = _ENTRY.match("  - -rw-r--r--     3.2 KB 2026-08-14 19:03  bir dosya.txt")
        assert m and m.group("name") == "bir dosya.txt"
        assert m.group("size").strip() == "3.2 KB"

    def test_dizin_olmayan_cikti_eslesmez(self):
        from app.results import _ENTRY
        assert _ENTRY.match(" 15:36:19 up 12 days,  2 users") is None
