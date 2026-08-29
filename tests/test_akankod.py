"""Akan araç girdisinden yazılmakta olan kodu çıkarmak.

Testlerin ağırlığı **yarım kalan yerlerde**. Elimizdeki JSON her zaman
yarım ve her yerinden yarım olabiliyor: anahtarın ortasında, iki nokta
üst üstenin öncesinde, bir kaçış dizisinin tam ortasında. `json.loads`
bunların hepsini reddediyor; buradaki tarayıcının hepsini elde olanla
cevaplaması gerekiyor.
"""

from __future__ import annotations

import json

from backend.agent.akankod import AkanKod, coz


def _akit(ham: str, adim: int = 7):
    """Metni parça parça verir — gerçek akışın yaptığı da bu."""
    for i in range(0, len(ham), adim):
        yield ham[i:i + adim]


class TestCozme:
    def test_tam_nesne(self):
        tam, yarim, deger = coz('{"path": "a.py", "content": "x"}')
        assert tam == {"path": "a.py", "content": "x"}
        assert yarim == "" and deger == ""

    def test_yarim_dize(self):
        tam, yarim, deger = coz('{"path": "a.py", "content": "import di')
        assert tam == {"path": "a.py"}
        assert yarim == "content" and deger == "import di"

    def test_kacislar_cozuluyor(self):
        tam, _y, _d = coz(r'{"content": "bir\nikı\t\"uc\" \\son"}')
        assert tam["content"] == 'bir\nikı\t"uc" \\son'

    def test_unicode_kacisi(self):
        tam, _y, _d = coz(r'{"content": "çıktı"}')
        assert tam["content"] == "çıktı"

    def test_yarim_unicode_kacisi_bekliyor(self):
        # `\u00e` gelmiş, son basamak gelmemiş: uydurulmuş bir karakter
        # yazmak yerine o kadarı gösterilmiyor.
        _t, yarim, deger = coz(r'{"content": "ab\u00e')
        assert yarim == "content" and deger == "ab"

    def test_ters_egik_cizginin_ortasinda_kesilmis(self):
        _t, yarim, deger = coz('{"content": "satir\\')
        assert yarim == "content" and deger == "satir"

    def test_icerikteki_anahtar_benzeri_metin_yaniltmiyor(self):
        # İçerik `"path":` yazıyor olabilir; tarayıcı dizenin içindeyken
        # anahtar aramıyor.
        ham = json.dumps({"content": '{"path": "sahte.py"}', "path": "asil.py"})
        tam, _y, _d = coz(ham)
        assert tam["path"] == "asil.py"
        assert tam["content"] == '{"path": "sahte.py"}'

    def test_dizi_ve_sayi_atlaniyor(self):
        tam, _y, _d = coz('{"n": 12, "ok": true, "xs": [1, 2], "p": "a"}')
        assert tam["p"] == "a"

    def test_yarim_dizi_durduruyor(self):
        tam, yarim, _d = coz('{"xs": [1, 2')
        assert tam == {} and yarim == ""

    def test_bos_ve_bozuk_girdi(self):
        assert coz("") == ({}, "", "")
        assert coz("bu json değil") == ({}, "", "")
        assert coz("{") == ({}, "", "")
        assert coz('{"a"') == ({}, "", "")
        assert coz('{"a":') == ({}, "", "")

    def test_bosluklu_bicim(self):
        tam, _y, _d = coz('{\n  "path"  :  "a.py" ,\n  "content" : "x"\n}')
        assert tam == {"path": "a.py", "content": "x"}


class TestAkanKod:
    def test_yazma_akiyor(self):
        akan = AkanKod()
        akan.basla("write_file")
        ham = json.dumps({"path": "bot.py", "content": "import discord\nx = 1\n"})
        goruntuler = []
        for parca in _akit(ham):
            if akan.besle(parca):
                goruntuler.append((akan.yol, akan.metin))
        assert akan.yol == "bot.py"
        assert akan.metin == "import discord\nx = 1\n"
        # Metin **büyüyerek** geliyor: her görüntü bir öncekiyle başlıyor.
        metinler = [m for _y, m in goruntuler]
        assert len(metinler) > 3, "tek seferde belirmiş"
        assert all(b.startswith(a) for a, b in zip(metinler, metinler[1:]))

    def test_edit_file_yeni_metni_gosteriyor(self):
        akan = AkanKod()
        akan.basla("edit_file")
        ham = json.dumps({"path": "a.py", "old": "eski satır",
                          "new": "yeni satır"})
        for parca in _akit(ham):
            akan.besle(parca)
        assert akan.metin == "yeni satır"

    def test_ilgisiz_arac_akmiyor(self):
        akan = AkanKod()
        akan.basla("left_click")
        assert not akan.etkin
        assert not akan.besle('{"coordinate": [1, 2]}')
        assert akan.metin == ""

    def test_degismeyen_parca_sinyal_yollamiyor(self):
        # Her parçada arayüze haber vermek saniyede yüzlerce çizim
        # demek olurdu.
        akan = AkanKod()
        akan.basla("write_file")
        akan.besle('{"path": "a.py", "content": "x"')
        assert not akan.besle("")
        assert not akan.besle("  ")

    def test_yol_yarimken_gosterilmiyor(self):
        # Yanıp sönen bir başlık: "b", "bo", "bot", "bot.p"...
        akan = AkanKod()
        akan.basla("write_file")
        akan.besle('{"path": "bo')
        assert akan.yol == ""

    def test_durdurmak_temizliyor(self):
        akan = AkanKod()
        akan.basla("write_file")
        akan.besle('{"path": "a.py", "content": "x"}')
        akan.dur()
        assert not akan.etkin and akan.metin == "" and akan.yol == ""

    def test_yeni_arac_oncekini_siliyor(self):
        akan = AkanKod()
        akan.basla("write_file")
        akan.besle('{"path": "a.py", "content": "eski"}')
        akan.basla("write_file")
        assert akan.metin == ""

    def test_yetenek_kodu_da_akiyor(self):
        akan = AkanKod()
        akan.basla("skill_write")
        ham = json.dumps({"name": "hava", "code": "ARAC = {}\n"})
        for parca in _akit(ham):
            akan.besle(parca)
        assert akan.yol == "hava"
        assert akan.metin == "ARAC = {}\n"
