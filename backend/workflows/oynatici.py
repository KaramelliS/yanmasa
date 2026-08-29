"""Akış oynatma — modele hiç uğramadan.

Bir akış oynatılırken model çağrısı yok, ekran görüntüsü yok, token yok.
Adımlar sırayla `Dispatcher`'a veriliyor; o zaten koordinat çevirisini,
onay kapısını ve acil durdurmayı yapıyor. Oynatmayı ayrı bir yoldan
geçirmek, bu üçünü ikinci kez yazmak ve birini unutmak olurdu.

## Kendini onarma

Tıklama adımlarının kayıtlı koordinatı **son çare**. Önce adımın imzası
aranıyor: aynı denetim şu anda neredeyse orası kullanılıyor. Pencere
taşınmış, ekran çözünürlüğü değişmiş ya da araç çubuğu kaymışsa akış
buna rağmen çalışıyor.

## Bulunamayınca duruyor

İmza kayıtlı ama denetim bulunamıyorsa adım **çalıştırılmıyor** ve akış
orada duruyor. Kayıtlı koordinata düşmek cazip ama yanlış: denetim
bulunamıyorsa ekran kaydedildiği andaki ekran değil demektir ve o
koordinatta artık bambaşka bir şey olabilir. Ekranda rastgele bir yere
tıklamak, kaybedilebilecek en kötü şey.

İmza hiç yoksa (oyun, yükseltilmiş pencere, tuval) kayıtlı koordinat
kullanılıyor — orada karşılaştırılacak bir şey de yok.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .depo import Adim, Akis
from .imza import bul as imzayi_bul

#: Koordinat taşıyan araçlar. Onarım yalnızca bunlarda anlamlı.
KOORDINATLI = frozenset({
    "left_click", "right_click", "middle_click", "double_click",
    "triple_click", "mouse_move", "left_mouse_down", "left_mouse_up",
    "scroll", "zoom",
})

#: Onarımın "kaydı" sayılması için gereken kayma, piksel. Bir-iki
#: piksellik fark ölçüm gürültüsü; onu onarım diye saymak, hiçbir şey
#: değişmemişken "düzeltildi" demek olurdu.
KAYMA_ESIGI = 3


@dataclass
class Sonuc:
    """Bir oynatmanın sonucu."""

    akis: str
    calisan: int = 0
    toplam: int = 0
    onarilan: int = 0
    hata: str = ""
    #: Kaçıncı adımda durdu (1'den). Sorun yoksa 0.
    duran_adim: int = 0
    notlar: list[str] = field(default_factory=list)

    @property
    def basarili(self) -> bool:
        return not self.hata

    def anlat(self) -> str:
        if self.basarili:
            metin = f"Replayed {self.akis}: {self.calisan}/{self.toplam} steps"
            if self.onarilan:
                metin += (
                    f", {self.onarilan} of them re-located because the "
                    f"control had moved"
                )
            return metin + "."
        return (
            f"{self.akis} stopped at step {self.duran_adim} of "
            f"{self.toplam}: {self.hata}"
        )


def _hedef(adim: Adim, displays, aktif_index: int) -> tuple[dict[str, Any], bool]:
    """Adımın girdisini onarır. `(girdi, onarildi_mi)`.

    Onarım bulunamazsa `KeyError` yerine istisna: çağıran bunu adımı
    çalıştırmama gerekçesi yapıyor.
    """
    girdi = dict(adim.girdi)
    if adim.imza is None or adim.arac not in KOORDINATLI:
        return girdi, False
    if not isinstance(girdi.get("coordinate"), (list, tuple)):
        return girdi, False

    nokta = imzayi_bul(adim.imza)
    if nokta is None:
        raise LookupError(
            f"could not find {adim.imza.anlat()} on screen any more"
        )
    ekran = displays.locate_virtual(*nokta) or displays[aktif_index]
    x, y = ekran.from_virtual(*nokta)
    eski = [int(girdi["coordinate"][0]), int(girdi["coordinate"][1])]
    girdi["coordinate"] = [int(x), int(y)]
    onarildi = (abs(eski[0] - x) > KAYMA_ESIGI
                or abs(eski[1] - y) > KAYMA_ESIGI)
    return girdi, onarildi


def oynat(akis: Akis, dispatcher,
          on_step: Callable[[str, dict[str, Any]], None] | None = None,
          on_result: Callable[[str, Any], None] | None = None) -> Sonuc:
    """Akışı sırayla çalıştırır. İlk hatada duruyor.

    İlk hatada durmanın gerekçesi ajan döngüsündekiyle aynı: adımlar
    birbirini varsayıyor. Tıklama tutmadıysa yazma yanlış yere gider.
    """
    sonuc = Sonuc(akis=akis.etiket or akis.ad, toplam=len(akis.adimlar))
    for sira, adim in enumerate(akis.adimlar, start=1):
        try:
            girdi, onarildi = _hedef(
                adim, dispatcher.displays, dispatcher.active_index
            )
        except LookupError as eksik:
            sonuc.hata = str(eksik)
            sonuc.duran_adim = sira
            return sonuc
        if onarildi:
            sonuc.onarilan += 1
            sonuc.notlar.append(
                f"step {sira}: {adim.imza.anlat()} had moved; used its "
                f"current position"
            )

        if on_step is not None:
            on_step(adim.arac, dict(girdi))
        try:
            cikti = dispatcher.run(adim.arac, girdi)
        except Exception as hata:
            # `Aborted` da buradan geçiyor: acil durdurma bir hata değil
            # ama akış yine de durmalı ve sebebi görünmeli.
            sonuc.hata = f"{type(hata).__name__}: {hata}"
            sonuc.duran_adim = sira
            return sonuc
        if on_result is not None:
            on_result(adim.arac, cikti)
        if getattr(cikti, "is_error", False):
            sonuc.hata = str(getattr(cikti, "content", "the step failed"))
            sonuc.duran_adim = sira
            return sonuc
        sonuc.calisan += 1
    return sonuc
