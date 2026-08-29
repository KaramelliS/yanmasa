"""Akışlar — kayıt, depo, oynatma ve kendini onarma.

Testlerin ağırlığı **oynatmada**. Bir akış oynatılırken model yok, yani
yanlış bir adımı fark edip düzeltecek kimse de yok: kod ne derse o
tıklanıyor. Bu yüzden en çok sınanan şey, kodun *tıklamamayı* seçtiği
durumlar — denetim bulunamadığında kayıtlı koordinata düşmemesi bu
özelliğin en önemli davranışı.
"""

from __future__ import annotations

import json

import pytest

from backend.workflows.depo import Adim, Akis, AkisDeposu, AkisHatasi
from backend.workflows.imza import Imza
from backend.workflows.oynatici import oynat


class _Sonuc:
    def __init__(self, content="OK", is_error=False):
        self.content, self.is_error = content, is_error


class _Ekran:
    left = top = 0
    width, height = 1920, 1080
    index = 0

    def from_virtual(self, vx, vy):
        return vx - self.left, vy - self.top


class _Ekranlar:
    def __init__(self):
        self._e = _Ekran()

    def __getitem__(self, i):
        return self._e

    def locate_virtual(self, vx, vy):
        return self._e


class _SahteDispatcher:
    """Oynatıcının gördüğü kadarıyla dispatcher."""

    def __init__(self, patlayan=None):
        self.displays = _Ekranlar()
        self.active_index = 0
        self.cagrilar: list[tuple[str, dict]] = []
        self._patlayan = patlayan or {}

    def run(self, ad, girdi):
        self.cagrilar.append((ad, dict(girdi)))
        if ad in self._patlayan:
            return _Sonuc(self._patlayan[ad], is_error=True)
        return _Sonuc()


@pytest.fixture()
def depo(tmp_path):
    return AkisDeposu(tmp_path / "akislar")


def _akis(**kwargs):
    varsayilan = dict(
        ad="test_akis", etiket="Test", talimat="şunu yap",
        adimlar=[Adim("launch_app", {"name": "notepad"})],
    )
    varsayilan.update(kwargs)
    return Akis(**varsayilan)


class TestDepo:
    def test_kaydet_ve_oku(self, depo):
        depo.kaydet(_akis())
        geri = depo.al("test_akis")
        assert geri is not None
        assert geri.etiket == "Test"
        assert geri.adimlar[0].girdi == {"name": "notepad"}

    def test_imza_gidip_geliyor(self, depo):
        imza = Imza("ButtonControl", "Kaydet", "saveBtn", "", "Not Defteri")
        depo.kaydet(_akis(adimlar=[
            Adim("left_click", {"coordinate": [10, 20]}, imza)
        ]))
        geri = depo.al("test_akis")
        assert geri.adimlar[0].imza == imza

    def test_bos_akis_kaydedilmiyor(self, depo):
        # "Kaydettim" deyip boş bir dosya bırakmak, sonra oynatınca
        # hiçbir şey olmaması demekti.
        with pytest.raises(AkisHatasi):
            depo.kaydet(_akis(adimlar=[]))

    def test_kotu_ad_reddediliyor(self, depo):
        for ad in ("", "A", "iki kelime", "1baslangic", "x" * 60):
            with pytest.raises(AkisHatasi):
                depo.kaydet(_akis(ad=ad))

    def test_cok_uzun_akis_reddediliyor(self, depo):
        adimlar = [Adim("left_click", {"coordinate": [1, 1]})] * 500
        with pytest.raises(AkisHatasi):
            depo.kaydet(_akis(adimlar=adimlar))

    def test_bozuk_dosya_listeyi_dusurmuyor(self, depo):
        depo.kaydet(_akis())
        depo.dizin.joinpath("bozuk.json").write_text("{ bu json değil",
                                                     encoding="utf-8")
        assert [a.ad for a in depo.hepsi()] == ["test_akis"]

    def test_olmayan_akis_none(self, depo):
        assert depo.al("yok") is None

    def test_silme(self, depo):
        depo.kaydet(_akis())
        assert depo.sil("test_akis")
        assert not depo.sil("test_akis")

    def test_yeniden_eskiye(self, depo):
        depo.kaydet(_akis(ad="eski", olusturuldu=100.0))
        depo.kaydet(_akis(ad="yeni", olusturuldu=200.0))
        assert [a.ad for a in depo.hepsi()] == ["yeni", "eski"]

    def test_dizin_yoksa_bos_liste(self, tmp_path):
        assert AkisDeposu(tmp_path / "hic-yok").hepsi() == []

    def test_adim_olmayan_kayit_atlaniyor(self, depo):
        depo.dizin.mkdir(parents=True, exist_ok=True)
        depo.dizin.joinpath("yarim.json").write_text(
            json.dumps({"ad": "yarim", "adimlar": [{"girdi": {}}, None, 3]}),
            encoding="utf-8",
        )
        akis = depo.al("yarim")
        assert akis is not None and akis.adimlar == []


class TestOynatma:
    def test_adimlar_sirayla(self):
        d = _SahteDispatcher()
        akis = _akis(adimlar=[
            Adim("launch_app", {"name": "notepad"}),
            Adim("type", {"text": "merhaba"}),
        ])
        sonuc = oynat(akis, d)
        assert sonuc.basarili and sonuc.calisan == 2
        assert [ad for ad, _ in d.cagrilar] == ["launch_app", "type"]

    def test_ilk_hatada_duruyor(self):
        # Adımlar birbirini varsayıyor: tıklama tutmadıysa yazma yanlış
        # yere gider.
        d = _SahteDispatcher(patlayan={"type": "alan bulunamadı"})
        akis = _akis(adimlar=[
            Adim("launch_app", {"name": "notepad"}),
            Adim("type", {"text": "x"}),
            Adim("key", {"text": "ctrl+s"}),
        ])
        sonuc = oynat(akis, d)
        assert not sonuc.basarili
        assert sonuc.duran_adim == 2
        assert "alan bulunamadı" in sonuc.hata
        assert [ad for ad, _ in d.cagrilar] == ["launch_app", "type"]

    def test_istisna_akisi_dusurmuyor(self):
        class Patlak(_SahteDispatcher):
            def run(self, ad, girdi):
                raise RuntimeError("acil durdurma")

        sonuc = oynat(_akis(), Patlak())
        assert not sonuc.basarili and "acil durdurma" in sonuc.hata

    def test_imzasiz_adim_kayitli_koordinati_kullaniyor(self):
        # Oyun, yükseltilmiş pencere, tuval: imza alınamıyor ve
        # karşılaştırılacak bir şey de yok.
        d = _SahteDispatcher()
        akis = _akis(adimlar=[Adim("left_click", {"coordinate": [700, 400]})])
        sonuc = oynat(akis, d)
        assert sonuc.basarili and sonuc.onarilan == 0
        assert d.cagrilar[0][1]["coordinate"] == [700, 400]

    def test_denetim_tasinmissa_yeni_yeri_kullaniliyor(self, monkeypatch):
        from backend.workflows import oynatici

        monkeypatch.setattr(oynatici, "imzayi_bul", lambda _i: (900, 620))
        d = _SahteDispatcher()
        akis = _akis(adimlar=[Adim(
            "left_click", {"coordinate": [700, 400]},
            Imza("ButtonControl", "Kaydet", "", "", "Not Defteri"),
        )])
        sonuc = oynat(akis, d)
        assert sonuc.basarili and sonuc.onarilan == 1
        assert d.cagrilar[0][1]["coordinate"] == [900, 620]
        assert sonuc.notlar and "had moved" in sonuc.notlar[0]

    def test_kucuk_kayma_onarim_sayilmiyor(self, monkeypatch):
        # Bir-iki piksellik fark ölçüm gürültüsü; onu "düzeltildi" diye
        # saymak hiçbir şey değişmemişken düzeltme raporlamak olurdu.
        from backend.workflows import oynatici

        monkeypatch.setattr(oynatici, "imzayi_bul", lambda _i: (701, 400))
        akis = _akis(adimlar=[Adim(
            "left_click", {"coordinate": [700, 400]},
            Imza("ButtonControl", "Kaydet", "", "", "x"),
        )])
        assert oynat(akis, _SahteDispatcher()).onarilan == 0

    def test_denetim_bulunamazsa_tiklanmiyor(self, monkeypatch):
        # Kayıtlı koordinata düşmek cazip ama yanlış: denetim
        # bulunamıyorsa ekran kaydedildiği andaki ekran değil demektir ve
        # orada artık bambaşka bir şey olabilir.
        from backend.workflows import oynatici

        monkeypatch.setattr(oynatici, "imzayi_bul", lambda _i: None)
        d = _SahteDispatcher()
        akis = _akis(adimlar=[Adim(
            "left_click", {"coordinate": [700, 400]},
            Imza("ButtonControl", "Kaydet", "", "", "Not Defteri"),
        )])
        sonuc = oynat(akis, d)
        assert not sonuc.basarili and sonuc.duran_adim == 1
        assert d.cagrilar == [], "bulunamayan denetime tıklandı"
        assert "Kaydet" in sonuc.hata

    def test_koordinatsiz_arac_onarilmiyor(self, monkeypatch):
        from backend.workflows import oynatici

        monkeypatch.setattr(
            oynatici, "imzayi_bul",
            lambda _i: pytest.fail("koordinatsız araçta imza aranmamalı"),
        )
        akis = _akis(adimlar=[Adim(
            "run_shell", {"command": "dir"},
            Imza("ButtonControl", "x", "", "", "y"),
        )])
        assert oynat(akis, _SahteDispatcher()).basarili

    def test_anlatim_onarimi_soyluyor(self):
        from backend.workflows.oynatici import Sonuc

        assert "3/3" in Sonuc("x", 3, 3).anlat()
        assert "re-located" in Sonuc("x", 3, 3, onarilan=1).anlat()
        assert "step 2" in Sonuc("x", 1, 3, hata="patladı", duran_adim=2).anlat()


class TestImza:
    def test_bos_imza_aranmiyor(self):
        from backend.workflows.imza import bul

        assert bul(Imza()) is None
        assert bul(None) is None

    def test_sozluge_gidip_geliyor(self):
        imza = Imza("ButtonControl", "Kaydet", "saveBtn", "Btn", "Pencere")
        assert Imza.from_dict(imza.as_dict()) == imza

    def test_bozuk_sozluk_none(self):
        assert Imza.from_dict("bu bir sözlük değil") is None
        assert Imza.from_dict(None) is None

    def test_eksik_alanlar_bos_string(self):
        imza = Imza.from_dict({"ad": "Kaydet"})
        assert imza.ad == "Kaydet" and imza.tur == "" and imza.pencere == ""

    def test_anlatim_okunur(self):
        assert "Kaydet" in Imza(ad="Kaydet", pencere="Not Defteri").anlat()


class TestKayit:
    """Turun adımlarını tampona alan taraf."""

    def _d(self, tmp_path):
        from backend.agent.dispatch import Dispatcher, ToolOutcome

        class SahteKill:
            def check(self):
                pass

        d = Dispatcher.__new__(Dispatcher)
        d.kill = SahteKill()
        d.kuru = False
        d._oynatiyor = False
        d._tur_adimlari = []
        d._tur_talimati = ""
        d.akislar = AkisDeposu(tmp_path / "akislar")
        d._do_wait = lambda payload: ToolOutcome(content="OK")
        d._do_launch_app = lambda payload: ToolOutcome(content="OK")
        d._gate = lambda n, p: None
        d._imza = lambda n, p: None
        return d

    def test_bakan_araclar_kaydedilmiyor(self, tmp_path):
        # Oynatmada karar veren yok; yirmi ekran görüntüsü almak hem
        # yavaş hem anlamsız olurdu.
        d = self._d(tmp_path)
        d._do_screenshot = lambda payload: type(
            "S", (), {"content": "x", "is_error": False}
        )()
        d.run("screenshot", {})
        assert d.son_adimlar == []

    def test_degistiren_arac_kaydediliyor(self, tmp_path):
        d = self._d(tmp_path)
        d.run("launch_app", {"name": "notepad"})
        assert [a.arac for a in d.son_adimlar] == ["launch_app"]

    def test_bekleme_kaydediliyor(self, tmp_path):
        # `wait` hiçbir şeyi değiştirmiyor ve kuru koşuda serbest — ama
        # oynatmada anlamlı: ajan bir diyaloğun açılmasını beklemek için
        # koyduysa, atlamak tıklamayı diyalog gelmeden yapmak demek.
        d = self._d(tmp_path)
        d.run("wait", {"duration": 1})
        assert [a.arac for a in d.son_adimlar] == ["wait"]

    def test_hatali_adim_kaydedilmiyor(self, tmp_path):
        from backend.agent.dispatch import ToolOutcome

        d = self._d(tmp_path)
        d._do_launch_app = lambda payload: ToolOutcome(content="olmadı",
                                                       is_error=True)
        d.run("launch_app", {})
        assert d.son_adimlar == []

    def test_tur_basi_tamponu_bosaltiyor(self, tmp_path):
        d = self._d(tmp_path)
        d.run("launch_app", {})
        d.tur_basladi("yeni iş")
        assert d.son_adimlar == []
        assert d._tur_talimati == "yeni iş"

    def test_kuru_kosuda_kaydedilmiyor(self, tmp_path):
        d = self._d(tmp_path)
        d.kuru = True
        d.run("launch_app", {})
        assert d.son_adimlar == []

    def test_oynatirken_kaydedilmiyor(self, tmp_path):
        # Yoksa oynatılan her akış kendini yeniden kaydederdi.
        d = self._d(tmp_path)
        d._oynatiyor = True
        d.run("launch_app", {})
        assert d.son_adimlar == []

    def test_workflow_araclari_kaydedilmiyor(self, tmp_path):
        d = self._d(tmp_path)
        d.run("launch_app", {})
        d.run("workflow_list", {})
        assert [a.arac for a in d.son_adimlar] == ["launch_app"]

    def test_kaydetme_talimati_tasiyor(self, tmp_path):
        d = self._d(tmp_path)
        d.tur_basladi("notepad aç")
        d.run("launch_app", {"name": "notepad"})
        d.run("workflow_save", {"name": "acilis", "label": "Açılış"})
        akis = d.akislar.al("acilis")
        assert akis is not None
        assert akis.talimat == "notepad aç"
        assert [a.arac for a in akis.adimlar] == ["launch_app"]

    def test_bos_turu_kaydetmek_hata(self, tmp_path):
        from backend.agent.dispatch import ToolError

        d = self._d(tmp_path)
        d.tur_basladi("hiçbir şey yapmadım")
        with pytest.raises(ToolError):
            d.run("workflow_save", {"name": "bos", "label": "Boş"})


class TestSayfa:
    def _g(self, qt_app, depo):
        from app import fluent
        from app.akislar import AkisGorunumu

        return AkisGorunumu(fluent.tokens(), lambda: depo)

    def test_bos_durum(self, qt_app, depo):
        g = self._g(qt_app, depo)
        assert "none saved" in g._sayac.text()

    def test_kartlar_ve_oynatma(self, qt_app, depo):
        depo.kaydet(_akis())
        g = self._g(qt_app, depo)
        assert "1 saved" in g._sayac.text()
        gelenler = []
        g.oynat.connect(gelenler.append)
        kartlar = [g._duzen.itemAt(i).widget()
                   for i in range(g._duzen.count() - 1)]
        kartlar[0].oynat.emit("test_akis")
        assert gelenler == ["test_akis"]

    def test_silme_listeden_dusuruyor(self, qt_app, depo):
        depo.kaydet(_akis())
        g = self._g(qt_app, depo)
        g._sil("test_akis")
        assert depo.hepsi() == []
        assert "none saved" in g._sayac.text()

    def test_cizilebiliyor(self, qt_app, depo):
        from PySide6.QtGui import QImage

        depo.kaydet(_akis(adimlar=[Adim(
            "left_click", {"coordinate": [1, 2]},
            Imza("ButtonControl", "Kaydet", "", "", "x"),
        )]))
        g = self._g(qt_app, depo)
        g.resize(900, 500)
        g.render(QImage(g.size(), QImage.Format.Format_ARGB32))
