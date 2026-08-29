"""Koşu geçmişi — kaydın koşuya çevrilmesi ve sayfanın kendisi.

Testlerin ağırlığı **kesik kayıtta**. Denetim kaydı bir olay akışı ve
akış her yerinden kesilebiliyor: uygulama tur ortasında kapanıyor, ilk
gün pencerenin dışında kalıyor, son satır yarım yazılmış oluyor. Bunların
hepsi gerçekten oldu ve hiçbiri kaydı okunamaz yapmamalı — geçmiş
sayfasının bütün değeri "elde ne varsa onu göster"de.
"""

from __future__ import annotations

import json

import pytest

from backend.agent.kayit import Kayit, kosulari_derle


def _tur(talimat, t=100.0):
    return {"tur": "tur", "talimat": talimat, "t": t}


def _eylem(arac, t=101.0, hata=False, girdi=None, ozet="OK"):
    return {"tur": "eylem", "arac": arac, "girdi": girdi or {},
            "hata": hata, "ozet": ozet, "t": t}


def _bitti(metin="tamam", sure=3.0, t=110.0, desteksiz=None):
    return {"tur": "bitti", "metin": metin, "sure": sure, "t": t,
            "imza": "a>b", "adim": 2, "hata": 0,
            "desteksiz": desteksiz or []}


class TestDerleme:
    def test_bir_kosu(self):
        kosular = kosulari_derle([
            _tur("csv'leri çevir"), _eylem("read_file"), _eylem("write_file"),
            _bitti("çevirdim", 4.5),
        ])
        assert len(kosular) == 1
        k = kosular[0]
        assert k.talimat == "csv'leri çevir"
        assert k.adim_sayisi == 2
        assert k.sure == 4.5
        assert not k.yarim

    def test_yeniden_eskiye(self):
        # Listenin başında en son yapılan iş olmalı: geçmişe bakan kişi
        # neredeyse her zaman en sonuncuyu arıyor.
        kosular = kosulari_derle([
            _tur("ilk", 10), _bitti(t=11),
            _tur("ikinci", 20), _bitti(t=21),
        ])
        assert [k.talimat for k in kosular] == ["ikinci", "ilk"]

    def test_kapanmamis_tur_yarim_kaliyor(self):
        # Uygulama tur ortasında kapandı: `bitti` satırı hiç yazılmadı.
        # "0 saniyede bitti" demek kaydın söylemediği bir şey olurdu.
        kosular = kosulari_derle([_tur("yarım iş"), _eylem("screenshot")])
        assert kosular[0].yarim
        assert kosular[0].sure == 0.0

    def test_baslıksiz_eylem_atilmiyor(self):
        # Turun `tur` satırı okunmayan bir günde kalmış olabilir; eylemler
        # yine de elimizde ve atmak elde olan bilgiyi de kaybetmek olurdu.
        kosular = kosulari_derle([_eylem("run_shell"), _bitti()])
        assert len(kosular) == 1
        assert kosular[0].talimat == ""
        assert kosular[0].adim_sayisi == 1

    def test_sahipsiz_bitti_yutuluyor(self):
        assert kosulari_derle([_bitti()]) == []

    def test_yeni_tur_oncekini_kapatiyor(self):
        kosular = kosulari_derle([
            _tur("bir", 10), _eylem("a", 11),
            _tur("iki", 20), _eylem("b", 21), _bitti(t=22),
        ])
        assert len(kosular) == 2
        assert kosular[1].talimat == "bir" and kosular[1].yarim
        assert kosular[0].talimat == "iki" and not kosular[0].yarim

    def test_hata_sayisi(self):
        kosular = kosulari_derle([
            _tur("x"), _eylem("a"), _eylem("b", hata=True), _bitti(),
        ])
        assert kosular[0].hata_sayisi == 1

    def test_desteksiz_iddia_tasiniyor(self):
        kosular = kosulari_derle([
            _tur("x"), _bitti(desteksiz=["dosyayı kaydettim"]),
        ])
        assert kosular[0].desteksiz == ["dosyayı kaydettim"]

    def test_bos_kayit(self):
        assert kosulari_derle([]) == []


@pytest.fixture()
def kayit(tmp_path):
    """Diskte gerçek bir kayıt: okuma yolu da sınanıyor."""
    dizin = tmp_path / "runs"
    dizin.mkdir()
    satirlar = [
        _tur("chrome'u aç", 1000.0),
        _eylem("launch_app", 1001.0, girdi={"name": "chrome"}),
        _eylem("screenshot", 1002.0, ozet="[image]"),
        _bitti("açtım", 5.0, 1005.0),
        _tur("dosyaları sil", 1100.0),
        _eylem("run_shell", 1101.0, hata=True,
               girdi={"command": "rm -rf x"}, ozet="Denied"),
        _bitti("silemedim", 2.0, 1103.0, desteksiz=["sildim"]),
    ]
    yol = dizin / "2026-08-29.jsonl"
    yol.write_text(
        "\n".join(json.dumps(s, ensure_ascii=False) for s in satirlar) + "\n",
        encoding="utf-8",
    )
    return Kayit(dizin)


class TestSayfa:
    def _g(self, qt_app, kayit=None):
        from app import fluent
        from app.gecmis import GecmisGorunumu

        return GecmisGorunumu(fluent.tokens(), kayit)

    def test_kosular_okunuyor(self, qt_app, kayit):
        g = self._g(qt_app, kayit)
        assert [k.talimat for k in g._durum.kosular] == [
            "dosyaları sil", "chrome'u aç",
        ]
        assert g.secili == 0, "en son koşu açılışta seçili olmalı"

    def test_secim_degisiyor(self, qt_app, kayit):
        g = self._g(qt_app, kayit)
        g.sec(1)
        assert g.secili == 1
        assert [s._etkin for s in g._satirlar] == [False, True]

    def test_olmayan_sirayi_secmek_patlamiyor(self, qt_app, kayit):
        g = self._g(qt_app, kayit)
        g.sec(99)
        assert g.secili == 0

    def test_suzgec(self, qt_app, kayit):
        g = self._g(qt_app, kayit)
        g._suz("chrome")
        assert [s.kosu.talimat for s in g._satirlar] == ["chrome'u aç"]
        g._suz("")
        assert len(g._satirlar) == 2

    def test_suzgec_bosa_dusunce_patlamiyor(self, qt_app, kayit):
        # Eşleşme yokken sağ taraf boş bir gövde değil, sebebini söyleyen
        # bir metin gösteriyor.
        g = self._g(qt_app, kayit)
        g._suz("böyle bir şey yok")
        assert g._satirlar == []

    def test_bos_kayit_bos_durum(self, qt_app, tmp_path):
        g = self._g(qt_app, Kayit(tmp_path / "yok"))
        assert g._durum.kosular == []
        assert g.secili == -1

    def test_tekrarla_talimati_gonderiyor(self, qt_app, kayit):
        g = self._g(qt_app, kayit)
        gelenler = []
        g.tekrarla.connect(gelenler.append)
        g._ayrinti.tekrarla.emit(g._durum.kosular[0].talimat)
        assert gelenler == ["dosyaları sil"]

    def test_cizilebiliyor(self, qt_app, kayit):
        from PySide6.QtGui import QImage

        g = self._g(qt_app, kayit)
        g.resize(1000, 600)
        gorsel = QImage(g.size(), QImage.Format.Format_ARGB32)
        g.render(gorsel)  # patlamamalı


class TestBicim:
    def test_sure(self):
        from app.gecmis import _sure

        assert _sure(0) == ""
        assert _sure(45) == "45s"
        assert _sure(125) == "2m 05s"
        assert _sure(3725) == "1h 02m"

    def test_talimat_bossa_uydurmuyor(self):
        from app.gecmis import _baslik
        from backend.agent.kayit import Kosu

        assert "not in the log" in _baslik(Kosu(talimat="", baslangic=0))
