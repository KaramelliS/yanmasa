"""Ajanın iddiası ile denetim kaydının karşılaştırılması.

Bu modülün tek gerçek riski **yanlış alarm** ve kendi belgesi de bunu
söylüyor: her cevabın altında haksız bir uyarı çıkarsa insan uyarıyı
okumayı bırakır, ve o noktada gerçek olanı da kaçırır. Testlerin ağırlığı
bu yüzden "iddia sayılmaması gereken cümlelerde".

İki dil birden sınanıyor. Arayüz İngilizce ve ajan İngilizce cevap
veriyor; İngilizce tarafın yarım kalması bu özelliğin sessizce
kapanması ya da sürekli yanlış alarm vermesi demek — ikisi de ölçüldü ve
ikisi de olmuştu.
"""

from __future__ import annotations

import pytest

from backend.agent import rapor

DOSYA = {"write_file"}
KABUK = {"run_shell"}


def _eksik(metin: str, tur=frozenset(), oturum=frozenset()) -> list[str]:
    return rapor.desteksiz(metin, set(tur), set(oturum))


class TestIddia:
    @pytest.mark.parametrize("metin", [
        "Dosyayı kaydettim.",
        "I saved the file.",
        "I wrote it to your Desktop.",
        "The file was created.",
    ])
    def test_dosya_iddiasi_yakalaniyor(self, metin):
        assert _eksik(metin) == ["dosya"]

    @pytest.mark.parametrize("metin", [
        "Komutu çalıştırdım.",
        "I ran the tests.",
        "I installed the package.",
    ])
    def test_kabuk_iddiasi_yakalaniyor(self, metin):
        assert _eksik(metin) == ["kabuk"]

    def test_destekleniyorsa_isaretlenmiyor(self):
        assert _eksik("I saved the file.", tur=DOSYA) == []

    def test_oturumdan_destek_de_sayiliyor(self):
        # "Az önce yazdığım dosya" meşru bir cümle: bu turda yazma
        # olmasa da oturumda olmuş olabilir.
        assert _eksik("I saved the file.", oturum=DOSYA) == []

    def test_yanlis_aile_destek_saymiyor(self):
        assert _eksik("I saved the file.", tur=KABUK) == ["dosya"]


class TestOlumsuzluk:
    @pytest.mark.parametrize("metin", [
        "kaydetmedim.",
        "Dosyayı yazamadım.",
        "I have not saved the file yet.",
        "I did not run the tests.",
        "I could not run the installer.",
        "I was unable to open it.",
        "Nothing was created because the folder is missing.",
        "I never saved it.",
    ])
    def test_olumsuz_cumle_iddia_degil(self, metin):
        # Ölçüldü: İngilizce olumsuzlama ayrı bir kelime, Türkçedeki gibi
        # ek değil. Yalnızca Türkçe eki arayan ilk sürüm "I have not
        # saved the file yet" cümlesini desteksiz iddia sayıyordu.
        assert _eksik(metin) == []

    def test_yalin_no_olumsuz_saymiyor(self):
        # "no problem, I saved it" gerçek bir iddia; yalın `no`yu
        # olumsuzlama saymak özelliği başka bir yönden köreltirdi.
        assert _eksik("No problem - I saved it.") == ["dosya"]


class TestYanCumle:
    def test_turkce_yan_cumle(self):
        # Olumsuzluk yalnızca ilk yarıya ait; cümlenin tamamına bakmak
        # ikinci iddiayı da elerdi.
        assert _eksik("Dosyayı yazamadım ama komutu çalıştırdım.") == ["kabuk"]

    @pytest.mark.parametrize("metin", [
        "I wrote the file but could not run it.",
        "I saved it, however the tests did not run.",
        "I created it although the install failed.",
    ])
    def test_ingilizce_yan_cumle(self, metin):
        # Aynı kusurun İngilizce yarısı: bağlaçlar eksikken ikinci
        # yarıdaki olumsuzluk birinci yarıdaki gerçek iddiayı götürüyordu.
        assert _eksik(metin) == ["dosya"]


class TestSoru:
    @pytest.mark.parametrize("metin", [
        "Dosyayı yazdım mı?",
        "Did I save the file?",
        "Should I have run it?",
    ])
    def test_soru_iddia_degil(self, metin):
        assert _eksik(metin) == []


class TestKiplik:
    @pytest.mark.parametrize("metin", [
        "Dosyayı kaydedebilirim.",
        "İstersen çalıştırırım.",
    ])
    def test_gelecek_ve_yeterlilik_iddia_degil(self, metin):
        assert _eksik(metin) == []

    def test_ran_into_calistirma_iddiasi_degil(self):
        # Yalın `ran` alınmadı: "I ran into an issue" komut çalıştırmak
        # değil.
        assert _eksik("I ran into an issue with the parser.") == []

    def test_started_by_uygulama_acmak_degil(self):
        assert _eksik("I started by reading the folder.") == []


class TestNot:
    def test_bos_liste_bos_metin(self):
        assert rapor.not_metni([]) == ""

    def test_not_suclamiyor(self):
        # "Ajan yalan söyledi" demek, kalıp eşleşmesinin taşıyabileceğinden
        # fazla iddia olurdu; söylenen şey kanıtın nerede olmadığı.
        metin = rapor.not_metni(["dosya"])
        assert "No record of" in metin
        assert "writing a file" in metin
        assert "lie" not in metin.lower()

    def test_bos_metin_iddia_uretmiyor(self):
        assert _eksik("") == []
        assert _eksik("Bitti.") == []
