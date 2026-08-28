"""İkinci imleç — saf mantık testleri.

Gerçek masaüstü ve gerçek Chromium `scripts/ikinci_imlec_dogrula.py`
içinde ölçülüyor; burası ona ihtiyaç duymayan kısım: koordinat
paketleme, tuş sözlüğü, reddedilen girdi biçimleri ve onay kapısı.

Ölçülen davranışın testi yok çünkü ölçüm Chrome kurulumuna ve ~10
saniyeye bağlı; CI'da yeşil kalan ama hiçbir şey doğrulamayan bir test
yazmak, doğrulanmamış kodu doğrulanmış göstermek olurdu.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.computer.mesaj import (
    TUSLAR,
    DesteklenmiyorHatasi,
    Girdi,
    Imlec,
    _lp,
)
from backend.safety import gate


class TestKoordinat:
    def test_lparam_paketleme(self):
        # y yüksek word, x düşük word.
        assert _lp(0, 0) == 0
        assert _lp(5, 0) == 5
        assert _lp(0, 5) == 5 << 16
        assert _lp(300, 200) == (200 << 16) | 300

    def test_negatif_koordinat_tasmiyor(self):
        # İstemci alanının solundaki nokta negatif gelir ve Win32 bunu
        # 16 bitlik işaretli sayı olarak okur; maskeleme şart.
        assert _lp(-1, -1) == 0xFFFFFFFF
        assert _lp(-3, 2) & 0xFFFF == 0xFFFD


class TestImlec:
    def test_baslangicta_sifirda(self):
        assert (Imlec().x, Imlec().y) == (0, 0)

    def test_tasima_tamsayiya_ceviriyor(self):
        i = Imlec()
        i.tasi(12.7, 30.2)
        assert (i.x, i.y) == (12, 30)
        assert isinstance(i.x, int)

    def test_her_girdinin_kendi_imleci(self):
        a, b = Girdi(), Girdi()
        a.imlec.tasi(100, 100)
        assert (b.imlec.x, b.imlec.y) == (0, 0)


class TestTuslar:
    def test_kombinasyon_reddediliyor(self):
        # Sessizce yanlış iş yapmaktansa hata: değiştirici tuş ileti
        # taklidinde basılı görünmüyor.
        with pytest.raises(DesteklenmiyorHatasi, match="modifier"):
            Girdi().tus("ctrl+s")

    def test_bilinmeyen_tus_reddediliyor(self):
        with pytest.raises(DesteklenmiyorHatasi, match="unknown key"):
            Girdi().tus("hyperspace")

    def test_odak_yokken_yazma_reddediliyor(self):
        with pytest.raises(DesteklenmiyorHatasi, match="focus"):
            Girdi().yaz("merhaba")

    def test_islev_tuslari_dogru_kodda(self):
        assert TUSLAR["f1"] == 0x70
        assert TUSLAR["f12"] == 0x7B

    def test_esanlamlilar_ayni(self):
        assert TUSLAR["esc"] == TUSLAR["escape"] == 0x1B
        assert TUSLAR["enter"] == TUSLAR["return"] == 0x0D


class TestKapi:
    def test_yan_alanda_uygulama_acmak_onay_istiyor(self):
        verdict = gate.classify("side_launch", {"command": "chrome.exe"})
        assert verdict.needs_confirmation

    def test_yan_alanda_tiklama_sormuyor(self):
        # Her tıklamada sorulsaydı paralel çalışma diye bir şey kalmazdı.
        verdict = gate.classify(
            "side_act", {"action": "click", "coordinate": [10, 10]}
        )
        assert not verdict.needs_confirmation

    def test_yan_alanda_kimlik_bilgisi_yazmak_onay_istiyor(self):
        tehlikeli = gate.classify_typing("parola: 12345")
        if not tehlikeli.needs_confirmation:
            pytest.skip("yazma sınıflandırıcısı bu kalıbı riskli saymıyor")
        verdict = gate.classify(
            "side_act", {"action": "type", "text": "parola: 12345"}
        )
        assert verdict.needs_confirmation


class TestDonanimaDokunulmuyor:
    """İkinci imlecin tek gerçek vaadi: fiziksel fareyi oynatmamak.

    Canlı koşuda bunu ölçmek mümkün değil — Berkay o sırada bilgisayarı
    kullanıyor ve imlecin oynaması onun oynatmasından geliyor. O yüzden
    iddia kaynakta doğrulanıyor: bu yolda imleci oynatabilecek bir çağrı
    varsa test kırılır.
    """

    YASAK = ("SendInput", "SetCursorPos", "mouse_event", "keybd_event",
             "SetThreadDesktop", "SwitchDesktop")

    @pytest.mark.parametrize("dosya", ["mesaj.py", "masaustu.py"])
    def test_imleci_oynatan_cagri_yok(self, dosya):
        kaynak = (Path(__file__).resolve().parent.parent
                  / "backend" / "computer" / dosya).read_text(encoding="utf-8")
        # Bu adlar modül başlıklarında geçiyor — neden kullanılmadıkları
        # orada anlatılıyor. Satır başına bakan bir filtre docstring'in
        # gövdesini yakalayamıyor, o yüzden kaynak sözcüklerine ayrılıp
        # dizgi ve açıklama belirteçleri atılıyor.
        import io
        import tokenize

        kod = " ".join(
            t.string
            for t in tokenize.generate_tokens(io.StringIO(kaynak).readline)
            if t.type not in (tokenize.COMMENT, tokenize.STRING)
        )
        bulunan = [ad for ad in self.YASAK if ad in kod]
        assert bulunan == [], bulunan

    def test_girdi_modulu_input_modulunu_ice_aktarmiyor(self):
        # `input.py` donanımı süren modül; buraya sızması sessiz bir
        # gerileme olurdu.
        kaynak = (Path(__file__).resolve().parent.parent
                  / "backend" / "computer" / "mesaj.py").read_text(encoding="utf-8")
        assert "import input" not in kaynak
        assert "from .input" not in kaynak
