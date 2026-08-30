"""Sistem promptunun geri dönmemesi gereken yerleri.

Buradaki testler promptun **metnine** bakıyor, ajanın davranışına değil.
Bir cümlenin orada olması modelin ona uyacağını kanıtlamıyor; kanıtladığı
tek şey cümlenin silinmediği. Bu kadarı için bile bir sebep var: aşağıdaki
kural bir kez yanlış yazıldı ve uygulamanın ana işini kapattı.

`prompts.py` "Where to stop" listesi şu satırı koşulsuz içeriyordu:

    - Sending a message, an email or a post.

Sonuç, kullanıcı açıkça "bunu Reddit'te paylaş" dediğinde ajanın durup
soru sorması oldu. Paylaşmak bu programın kaza değil, işi. Kural artık
kullanıcının istemediği gönderimi kapsıyor; istenen gönderim ayrı bir
başlıkta ve orada "post" diyor.

Testin koruduğu şey o ayrım. Listeye koşulsuz bir gönderim yasağı geri
girerse burası kırılır.
"""

from __future__ import annotations

import re

from backend.agent.prompts import SYSTEM, build_system
from backend.computer.displays import Display, DisplayMap


def _harita() -> DisplayMap:
    return DisplayMap([
        Display(index=0, left=0, top=0, width=1920, height=1080, primary=True),
    ])


def _bolum(baslik: str) -> str:
    """Promptun bir başlığından bir sonraki aynı düzeydeki başlığa kadarı."""
    duzey = baslik.split(" ", 1)[0]
    kalan = SYSTEM.split(baslik, 1)
    assert len(kalan) == 2, f"promptta {baslik!r} yok"
    govde = kalan[1]
    sonraki = re.search(rf"^{re.escape(duzey)} ", govde, re.MULTILINE)
    return govde[: sonraki.start()] if sonraki else govde


class TestDurulacakYerler:
    def test_baslik_var(self) -> None:
        assert "## Where to stop" in SYSTEM

    def test_gonderim_yasagi_kosullu(self) -> None:
        """Listedeki gönderim maddesi 'istemediği' ile sınırlı."""
        madde = [
            s for s in _bolum("## Where to stop").splitlines()
            if s.startswith("- ") and " post" in s
        ]
        assert len(madde) == 1, madde
        assert "did not ask for" in madde[0]

    def test_kosulsuz_gonderim_yasagi_yok(self) -> None:
        """Eski satır aynen geri gelirse burası kırılsın."""
        assert "- Sending a message, an email or a post." not in SYSTEM

    def test_geri_alinamayanlar_hala_yasak(self) -> None:
        """Değişiklik listeyi boşaltmadı — asıl korunanlar yerinde."""
        bolum = _bolum("## Where to stop")
        for beklenen in ("administrator (UAC)", "password", "card number",
                         "Sending money", "Deleting files"):
            assert beklenen in bolum, beklenen


class TestIstenenPaylasim:
    def test_baslik_var(self) -> None:
        assert "### When they did ask you to post" in SYSTEM

    def test_yap_diyor(self) -> None:
        assert "Then post." in _bolum("### When they did ask you to post")

    def test_once_haber_veriyor(self) -> None:
        """Gönderme serbest ama sessiz değil: `heads_up` orada."""
        assert "heads_up" in _bolum("### When they did ask you to post")

    def test_reddi_sonuc_gibi_raporlamiyor(self) -> None:
        bolum = _bolum("### When they did ask you to post")
        assert "refusal as if it were a result" in bolum

    def test_durulacak_yerlerin_icinde(self) -> None:
        """İstisna, kuralın hemen altında duruyor — ayrı bir yere kaçmadı."""
        assert (SYSTEM.index("## Where to stop")
                < SYSTEM.index("### When they did ask you to post")
                < SYSTEM.index("## Talking"))


class TestKurulanPrompt:
    def test_bolum_kurulan_promptta_da_var(self) -> None:
        metin = build_system(_harita(), 0)
        assert "### When they did ask you to post" in metin
        assert "- Sending a message, an email or a post." not in metin

    def test_kuru_kosuda_da_var(self) -> None:
        """Kuru koşu eki sonda; gönderim bölümünü yutmuyor."""
        metin = build_system(_harita(), 0, kuru=True)
        assert "### When they did ask you to post" in metin
