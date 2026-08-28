"""Denetim kaydı, doğrulanmış rapor ve tekrar tespiti.

Bu üçü topluluğun ölçülmüş üç kusuruna karşılık geliyor: gözlemlenebilirlik
boşluğu, ajanın yapmadığı işi yaptım demesi, ve aynı işin elle tekrar
tekrar yapılması.

Testlerin ağırlığı **yanlış alarmda**. Bir denetim aracının asıl riski bir
şeyi kaçırması değil, haksız yere bağırması: her cevabın altında sebepsiz
bir uyarı çıkarsa insan uyarıyı okumayı bırakır ve o noktada gerçek olanı
da kaçırır.
"""

from __future__ import annotations

import json

import pytest

from backend.agent import rapor
from backend.agent.kayit import (
    ASGARI_ADIM,
    Kayit,
    oneri_notu,
    tekrar_bul,
    temiz_girdi,
)


class TestIddiaBulma:
    @pytest.mark.parametrize("metin,beklenen", [
        ("Dosyayı yazdım.", {"dosya"}),
        # Türkçe harfsiz yazım da tutmalı: insan iki türlü de yazıyor.
        ("Dosyayi yazdim ve testleri calistirdim.", {"dosya", "kabuk"}),
        ("Notepad açtım ve içine yazdım.", {"dosya", "uygulama"}),
        ("Sunucuda çalıştırdım.", {"kabuk", "sunucu"}),
    ])
    def test_iddia_yakalaniyor(self, metin, beklenen):
        assert rapor.iddialar(metin) == beklenen

    @pytest.mark.parametrize("metin", [
        "Dosyayı yazamadım.",
        "Dosyayı yazdım mı?",
        "Kaydedebilirim.",
        "Bunu yapmamı ister misin?",
        "Dosyayı yazmadım, önce sana sormak istedim.",
    ])
    def test_iddia_olmayan_cumle_isaretlenmiyor(self, metin):
        # Yanlış alarm bu özelliğin tek gerçek riski.
        assert rapor.iddialar(metin) == set()

    def test_olumsuzluk_yan_cumlenin_disina_tasmiyor(self):
        # İlk hâli bunu kaçırıyordu: tek cümlede olumsuzluk ikinci
        # yarıdaki iddiayı da eliyordu.
        assert rapor.iddialar(
            "Dosyayı yazamadım ama komutu çalıştırdım."
        ) == {"kabuk"}


class TestDesteksizIddia:
    def test_bu_turda_destek_varsa_susuyor(self):
        assert rapor.desteksiz("Dosyayı yazdım.", {"write_file"}) == []

    def test_onceki_turda_destek_varsa_susuyor(self):
        # "Az önce yazdığım dosya" meşru bir cümle; oturuma bakılıyor.
        assert rapor.desteksiz("Dosyayı yazdım.", set(), {"edit_file"}) == []

    def test_hicbir_yerde_destek_yoksa_isaretliyor(self):
        assert rapor.desteksiz("Dosyayı yazdım.", set(), set()) == ["dosya"]

    def test_yanlis_aile_destek_saymiyor(self):
        # Ekran görüntüsü almak dosya yazmayı desteklemiyor.
        assert rapor.desteksiz("Dosyayı yazdım.", {"screenshot"}) == ["dosya"]

    def test_not_suclamiyor(self):
        # Kalıp eşleşmesi "yalan söyledi" demeyi taşımaz; söylediği şey
        # kanıtın nerede olmadığı.
        metin = rapor.not_metni(["dosya"])
        assert "kaydı yok" in metin
        assert "yalan" not in metin.lower()

    def test_bos_liste_bos_metin(self):
        assert rapor.not_metni([]) == ""


class TestKayitYazma:
    def test_tur_ve_eylem_yaziliyor(self, tmp_path):
        k = Kayit(tmp_path)
        k.tur_basladi("bir şey yap")
        k.eylem("write_file", {"path": "a.txt"}, False, "OK")
        k.tur_bitti("Dosyayı yazdım.", [])
        satirlar = k.satirlar()
        assert [s["tur"] for s in satirlar] == ["tur", "eylem", "bitti"]
        assert satirlar[1]["arac"] == "write_file"
        assert satirlar[2]["imza"] == "write_file"

    def test_dosya_govdesi_yazilmiyor(self, tmp_path):
        # Aynı veriyi ikinci kez saklamak; dosya zaten diskte.
        k = Kayit(tmp_path)
        k.tur_basladi("yaz")
        k.eylem("write_file", {"path": "a.py", "content": "gizli" * 500},
                False)
        assert "content" not in k.satirlar()[1]["girdi"]

    def test_anahtar_deseni_gizleniyor(self, tmp_path):
        # Kapı kimlik bilgisi yazmayı engelliyor ama tek katmana
        # güvenmiyoruz: denetim kaydının kendisi sızıntı olmamalı.
        k = Kayit(tmp_path)
        k.tur_basladi("x")
        k.eylem("type", {"text": "sk-ant-api03-" + "A" * 40}, False)
        assert k.satirlar()[1]["girdi"]["text"] == "[gizlendi]"

    def test_uzun_alan_kisaliyor(self, tmp_path):
        k = Kayit(tmp_path)
        k.tur_basladi("x")
        k.eylem("run_shell", {"command": "x" * 5000}, False)
        assert len(k.satirlar()[1]["girdi"]["command"]) < 260

    def test_bozuk_satir_butun_kaydi_dusurmuyor(self, tmp_path):
        k = Kayit(tmp_path)
        k.tur_basladi("x")
        with open(k.dosya, "a", encoding="utf-8") as f:
            f.write('{"tur": "eylem", yarim\n')
        k.eylem("screenshot", {}, False)
        # Süreç kapanırken yarım satır oluşabiliyor; bir bozuk satır
        # yüzünden elde olan bilgiyi de atmak yanlış olurdu.
        assert len(k.satirlar()) == 2

    def test_yazilamayan_kayit_ajani_durdurmuyor(self, tmp_path):
        # Denetim kaydı bir kolaylık; dolu disk yüzünden ajanın durması
        # saçma olurdu. Ama sessizce yutulmuyor.
        k = Kayit(tmp_path / "dosya")
        (tmp_path / "dosya").write_text("ben bir dosyayım", encoding="utf-8")
        k.tur_basladi("x")
        assert k.son_hata is not None

    def test_gizlenen_alan_adi_temiz_girdide(self):
        assert temiz_girdi({"code": "x", "path": "a"}) == {"path": "a"}


class TestTekrarTespiti:
    def _bitti(self, imza: str, hata: int = 0):
        return {"tur": "bitti", "imza": imza, "hata": hata}

    def test_uc_kez_tekrarlanan_is_bulunuyor(self):
        satirlar = [{"tur": "tur", "talimat": "csv'leri excele çevir"}]
        satirlar += [self._bitti("list_dir>office_open>office_save")] * 3
        bulunan = tekrar_bul(satirlar)
        assert bulunan and bulunan[0][1] == 3
        assert bulunan[0][2] == "csv'leri excele çevir"

    def test_iki_kez_yeterli_degil(self):
        satirlar = [self._bitti("list_dir>office_open")] * 2
        assert tekrar_bul(satirlar) == []

    def test_hatali_turlar_sayilmiyor(self):
        # Üç kez tökezleyen bir işi otomatikleştirmek, tökezlemeyi
        # otomatikleştirmek olurdu.
        satirlar = [self._bitti("list_dir>office_open", hata=1)] * 5
        assert tekrar_bul(satirlar) == []

    def test_tek_araclik_turlar_sayilmiyor(self):
        # Ekran görüntüsü almak sürekli tekrarlanıyor ve
        # otomatikleştirmenin anlamı yok.
        satirlar = [self._bitti("screenshot")] * 9
        assert tekrar_bul(satirlar) == []
        assert ASGARI_ADIM == 2

    def test_ardisik_tekrarlar_imzada_sadelesiyor(self):
        from backend.agent.kayit import Tur

        dort = Tur("x", 0.0, basarili=["write_file"] * 4 + ["run_shell"])
        bes = Tur("x", 0.0, basarili=["write_file"] * 5 + ["run_shell"])
        # Dört dosya yazmak ile beş dosya yazmak aynı iş.
        assert dort.imza == bes.imza == "write_file>run_shell"

    def test_oneri_notu_button_write_istiyor(self):
        notu = oneri_notu([("a>b", 3, "şunu yap")])
        assert "button_write" in notu and "3 kez" in notu

    def test_tekrar_yoksa_not_bos(self):
        # Boş not talimatın sonuna eklenmemeli; her mesaja gereksiz bir
        # paragraf takmak bağlamı kirletirdi.
        assert oneri_notu([]) == ""


class TestKayitOkuma:
    def test_bos_dizin_bos_liste(self, tmp_path):
        assert Kayit(tmp_path / "yok").satirlar() == []

    def test_gunler_eskiden_yeniye(self, tmp_path):
        for gun, ad in (("2026-01-01", "eski"), ("2026-06-01", "yeni")):
            (tmp_path / f"{gun}.jsonl").write_text(
                json.dumps({"tur": "tur", "talimat": ad}) + "\n",
                encoding="utf-8",
            )
        assert [s["talimat"] for s in Kayit(tmp_path).satirlar()] == [
            "eski", "yeni",
        ]


class TestBeklemeyeDonus:
    """Tur bitince maskot beklemeye dönmeli.

    Dönmüyordu: son pozunda donuyor, gözünü kırpmayı bırakıyor ve
    elindeki nesneyle öylece kalıyordu. Bitmiş bir işin pozunda sonsuza
    kadar durmak canlı bir şey değil, ekran görüntüsü.
    """

    def _kur(self, qt_app):
        from app import fluent
        from app.stream import RunRing

        halka = RunRing(fluent.tokens(), 52)
        return halka.face, halka

    def _ilerle(self, yuz, halka, saniye):
        for _ in range(int(saniye * 60)):
            halka._tick(1 / 60)

    def test_bitince_beklemeye_donuyor(self, qt_app):
        from app.svgyuz import BITTI_SURESI

        yuz, halka = self._kur(qt_app)
        halka.begin()
        halka.step("office_edit")
        self._ilerle(yuz, halka, 0.5)
        assert yuz._anim != "bosta", "çalışırken beklemede olmamalı"

        halka.settle(False)
        halka.finish()
        self._ilerle(yuz, halka, BITTI_SURESI * 0.4)
        # Bitiş pozu bir süre duruyor: hemen sıfırlamak "bitti"yi
        # görünmez yapardı.
        assert yuz._anim == "bitti"

        self._ilerle(yuz, halka, BITTI_SURESI + 0.5)
        assert yuz._anim == "bosta"
        assert yuz._live, "göz kırpması geri gelmeli"

    def test_bosta_ozelligi_durumu_yansitiyor(self, qt_app):
        yuz, _ = self._kur(qt_app)
        assert yuz.bosta
        yuz.set_state("yaziyor")
        assert not yuz.bosta
