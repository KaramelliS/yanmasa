"""Masanın içindeki Code penceresi.

Testlerin ağırlığı **büyüyen metinde ve alan paylaşımında**. Kod parça
parça geliyor ve her parçada belgeyi baştan kurmak ekranı titretiyor;
masa da tek bir alan ve kod penceresi açılınca yakalanan pencerelerin
oradan pay alması gerekiyor. İkisi de gözle görülür kusur üretir ve
ikisi de saf mantıkla sınanabilir.
"""

from __future__ import annotations

import pytest

from app.kod_penceresi import _anahtar, _satir_sayisi


@pytest.fixture()
def t():
    from app import fluent

    return fluent.tokens()


@pytest.fixture()
def kod(qt_app, t):
    from app.kod_penceresi import KodPenceresi

    w = KodPenceresi(t)
    w.resize(700, 480)
    return w


class TestYardimcilar:
    def test_satir_sayisi(self):
        assert _satir_sayisi("") == 0
        assert _satir_sayisi("bir") == 1
        assert _satir_sayisi("bir\n") == 1
        assert _satir_sayisi("bir\niki") == 2
        assert _satir_sayisi("bir\niki\n") == 2

    def test_ayni_dosyanin_iki_yazimi_tek_anahtar(self):
        # Akan girdideki yol modelin yazdığı hâli, yazma bitince gelen
        # ise çözülmüş mutlak yol; ikisini ayrı sanmak listede `bot.py`yi
        # iki kez gösteriyordu.
        import os

        assert _anahtar("bot.py") == _anahtar(os.path.abspath("bot.py"))


class TestAkis:
    def test_baslangicta_bos(self, kod):
        assert not kod.aktif

    def test_kod_gelince_aktif(self, kod):
        kod.kod_akiyor("write_file", "C:/p/bot.py", "import x\n", False)
        assert kod.aktif
        assert kod.editor._metin == "import x\n"
        assert "bot.py" in kod.baslik._metin

    def test_metin_ek_olarak_buyuyor(self, kod):
        # Her parçada `setPlainText` çağırmak kaydırmayı başa atıyor ve
        # ekran titriyor; devam eden metin yalnızca sona ekleniyor.
        kod.kod_akiyor("write_file", "C:/p/a.py", "bir", False)
        kod.kod_akiyor("write_file", "C:/p/a.py", "bir iki", False)
        kod.kod_akiyor("write_file", "C:/p/a.py", "bir iki üç", False)
        assert kod.editor.toPlainText() == "bir iki üç"

    def test_metin_geri_giderse_bastan_kuruluyor(self, kod):
        kod.kod_akiyor("write_file", "C:/p/a.py", "yanlış başlangıç", False)
        kod.kod_akiyor("write_file", "C:/p/a.py", "başka", False)
        assert kod.editor.toPlainText() == "başka"

    def test_dosya_degisince_editor_siniyor(self, kod):
        kod.kod_akiyor("write_file", "C:/p/a.py", "aaa", False)
        kod.kod_akiyor("write_file", "C:/p/b.py", "bbb", False)
        assert kod.editor.toPlainText() == "bbb"

    def test_agac_biriktiriyor_ama_tekrarlamiyor(self, kod):
        kod.kod_akiyor("write_file", "C:/p/a.py", "x", True)
        kod.kod_akiyor("write_file", "C:/p/b.py", "y", True)
        kod.dosyalari_ekle(["C:/p/a.py"])
        assert len(kod._dosyalar) == 2

    def test_agac_ondorde_kirpiliyor(self, kod):
        for i in range(20):
            kod.dosyalari_ekle([f"C:/p/d{i}.py"])
        assert len(kod._dosyalar) == 14

    def test_durum_yazarken_fiil_gosteriyor(self, kod):
        kod.kod_akiyor("write_file", "C:/p/a.py", "bir\niki\n", False)
        assert kod.durum._sol.startswith("writing a.py")
        kod.kod_akiyor("edit_file", "C:/p/a.py", "bir\niki\n", False)
        assert kod.durum._sol.startswith("editing a.py")

    def test_agac_tazelemesi_fiili_silmiyor(self, kod):
        # `dosyalari_ekle` durumu da tazeliyor ve fiili sıfırlarsa
        # "writing" yazma ortasında kayboluyordu.
        kod.kod_akiyor("write_file", "C:/p/a.py", "bir\n", False)
        kod.dosyalari_ekle(["C:/p/z.py"])
        assert kod.durum._sol.startswith("writing a.py")

    def test_bitince_yaziliyor_sonuyor(self, kod):
        kod.kod_akiyor("write_file", "C:/p/a.py", "bir\n", True)
        assert not kod._yaziliyor
        assert kod.durum._sol.startswith("a.py")

    def test_bos_cagri_yutuluyor(self, kod):
        kod.kod_akiyor("write_file", "", "", False)
        assert not kod.aktif

    def test_temizleme(self, kod):
        kod.kod_akiyor("write_file", "C:/p/a.py", "x", True)
        kod.terminal_ciktisi("t", "çıktı")
        kod.temizle()
        assert not kod.aktif
        assert kod.editor.toPlainText() == ""


class TestCekmece:
    def test_bos_cekmece_gizli(self, kod):
        assert not kod.cekmece.isVisible()
        assert not kod.cekmece.dolu

    def test_terminal_cikinca_aciliyor(self, kod):
        kod.terminal_ciktisi("kurulum", "pip install x\nok\n")
        assert kod.cekmece.dolu
        assert [a for a, _e in kod.cekmece._sekmeler()] == ["terminal"]

    def test_bos_cikti_cekmeceyi_acmiyor(self, kod):
        kod.terminal_ciktisi("t", "   \n  ")
        assert not kod.cekmece.dolu

    def test_degisiklik_sekmesi_yalnizca_iceriginde(self, kod):
        # Boş bir "Changes" sekmesi, bakılacak bir şey varmış gibi durur.
        kod.terminal_ciktisi("t", "satır")
        assert [a for a, _e in kod.cekmece._sekmeler()] == ["terminal"]
        kod.degisiklik("a.py", "eski", "yeni")
        assert [a for a, _e in kod.cekmece._sekmeler()] == ["terminal", "diff"]
        assert kod.cekmece._etkin == "diff"

    def test_bos_degisiklik_yutuluyor(self, kod):
        kod.degisiklik("a.py", "", "")
        assert not kod.cekmece.dolu

    def test_terminal_satirlari_kirpiliyor(self, kod):
        from app.kod_penceresi import TERMINAL_SATIR

        kod.terminal_ciktisi("t", "\n".join(str(i) for i in range(2000)))
        assert len(kod.cekmece._terminal) == TERMINAL_SATIR
        assert kod.cekmece._terminal[-1] == "1999", "son çıktı tutulmalı"

    def test_cizilebiliyor(self, kod):
        from PySide6.QtGui import QImage

        kod.kod_akiyor("write_file", "C:/p/a.py", "def f():\n    return 1\n",
                       True)
        kod.terminal_ciktisi("t", "ok")
        kod.degisiklik("a.py", "eski satır", "yeni satır")
        kod.cekmece.setVisible(True)
        kod.render(QImage(kod.size(), QImage.Format.Format_ARGB32))


class TestMasaBolusumu:
    def _masa(self, qt_app, t, kare=None):
        from app.masa import MasaPenceresi
        from backend.computer.canli import MasaKaresi

        w = MasaPenceresi(lambda: kare or MasaKaresi(), t)
        if kare is not None:
            w._kare = kare
        w.resize(1200, 760)
        return w

    def _kare_pencereli(self):
        from backend.computer.canli import MasaKaresi, PencereKaresi

        pencere = PencereKaresi(hwnd=1, baslik="p", sinif="S",
                                x=100, y=100, en=800, boy=600, ham=b"")
        return MasaKaresi(pencereler=[pencere], alan=(1920, 1080))

    def test_kod_yokken_masa_tamami_pencerelerin(self, qt_app, t):
        w = self._masa(qt_app, t, self._kare_pencereli())
        kod, alan = w._bolgeler()
        assert not kod.isValid()
        assert alan.width() == w.width()

    def test_kod_varken_ve_pencere_yokken_masayi_kapliyor(self, qt_app, t):
        w = self._masa(qt_app, t)
        w.kod_akiyor("write_file", "C:/p/a.py", "x", False)
        kod, alan = w._bolgeler()
        assert kod.width() > w.width() * 0.9
        assert not alan.isValid()

    def test_ikisi_de_varsa_bolunuyor(self, qt_app, t):
        # Ajan hem kod yazarken hem tarayıcıya bakarken ikisi de
        # görünmeli; üst üste bindirmek birini gizlerdi.
        w = self._masa(qt_app, t, self._kare_pencereli())
        w.kod_akiyor("write_file", "C:/p/a.py", "x", False)
        kod, alan = w._bolgeler()
        assert kod.isValid() and alan.isValid()
        assert not kod.intersects(alan)
        assert kod.width() > alan.width(), "kod okunacak kadar geniş olmalı"

    def test_kod_penceresi_gorunurlugu(self, qt_app, t):
        # `isHidden` soruluyor: ebeveyn ekranda değilken `isVisible`
        # her zaman `False` ve niyeti söylemiyor.
        w = self._masa(qt_app, t)
        assert w.kod.isHidden()
        w.kod_akiyor("write_file", "C:/p/a.py", "x", False)
        assert not w.kod.isHidden()

    def test_dar_masada_bolunmuyor(self, qt_app, t):
        # İki okunmaz bölme, bir okunur bölmeden kötü. Pencerenin en
        # küçük hâli 480 ve orada bölüşüm 260 veriyor — yani bu gerçekten
        # oluyor.
        w = self._masa(qt_app, t, self._kare_pencereli())
        w.kod_akiyor("write_file", "C:/p/a.py", "x", False)
        w.resize(480, 400)
        kod, alan = w._bolgeler()
        assert kod.isValid() and not alan.isValid(), "yazarken kod önde"

    def test_dar_masada_yazma_bitince_pencereler_geri_geliyor(self, qt_app, t):
        # Yoksa küçük bir pencerede kod ekranı kalıcı olarak kaplardı.
        w = self._masa(qt_app, t, self._kare_pencereli())
        w.kod_akiyor("write_file", "C:/p/a.py", "x", True)
        w.resize(480, 400)
        kod, alan = w._bolgeler()
        assert not kod.isValid() and alan.isValid()
        w._yerlestir()
        assert w.kod.isHidden()

    def test_kod_varken_bos_masa_metni_yazilmiyor(self, qt_app, t):
        # "Ajan henüz bir şey açmadı" derken tam o sırada kod yazıyor.
        from PySide6.QtGui import QImage

        w = self._masa(qt_app, t)
        w.kod_akiyor("write_file", "C:/p/a.py", "x", False)
        assert w._kare.bos and w.kod.aktif
        w.render(QImage(w.size(), QImage.Format.Format_ARGB32))
