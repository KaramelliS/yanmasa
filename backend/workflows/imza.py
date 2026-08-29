"""Tıklanan şeyin kimliği — akışın kendini onarmasını sağlayan parça.

Kaydedilmiş bir tıklama yalnızca koordinat olsaydı, akış pencere iki
piksel kaydığı anda çöperdi. Burada kaydedilen şey koordinat değil,
**neye tıklandığı**: denetimin türü, adı, otomasyon kimliği ve içinde
bulunduğu pencere. Oynatırken aynı denetim yeniden bulunuyor ve o anki
yeri kullanılıyor.

## Neden kırılgan bir eşleşme değil

Üç anahtar var ve güçlüden zayıfa sıralı:

1. `AutomationId` + denetim türü — uygulamanın kendi verdiği kimlik,
   dile ve yere bağlı değil. Varsa bu kullanılıyor.
2. Ad + denetim türü — "Kaydet" düğmesi taşınsa da "Kaydet" kalıyor.
   Uygulamanın dili değişirse kopuyor; kabul edilebilir.
3. Yalnızca ad — son çare, tür değişmişse.

Eşleşme **pencere içinde** aranıyor. Aynı adı taşıyan iki denetim iki
ayrı pencerede sık: iki Explorer penceresinde de "Ad" sütunu var.

## Her yerde çalışmıyor

Oyunlar, yükseltilmiş pencereler ve tuval çizen uygulamalar UIA'ya
kapalı; `ControlFromPoint` orada `E_ACCESSDENIED` veriyor — ölçtüm,
Counter-Strike öndeyken bütün noktalar düştü. O adımlar imzasız
kaydediliyor ve oynatılırken kayıtlı koordinat kullanılıyor. Bu
dürüst olanı: imza uyduramayız, ama imzasız bir adım da bir adım.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

#: Ağaçta gezilirken bakılan en fazla düğüm ve derinlik. `uia.py`
#: ile aynı gerekçe: sınırsız bir gezinti bazı uygulamalarda saniyeler
#: sürüyor ve bir akış adımı saniyelerce donamaz.
MAX_DERINLIK = 14
MAX_DUGUM = 600


@dataclass(frozen=True)
class Imza:
    """Bir denetimin yerden bağımsız kimliği."""

    tur: str = ""
    ad: str = ""
    kimlik: str = ""
    sinif: str = ""
    pencere: str = ""

    @property
    def bos(self) -> bool:
        return not (self.ad or self.kimlik)

    def as_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, ham: Any) -> Imza | None:
        if not isinstance(ham, dict):
            return None
        return cls(
            tur=str(ham.get("tur") or ""),
            ad=str(ham.get("ad") or ""),
            kimlik=str(ham.get("kimlik") or ""),
            sinif=str(ham.get("sinif") or ""),
            pencere=str(ham.get("pencere") or ""),
        )

    def anlat(self) -> str:
        """İnsan için kısa karşılık — hata mesajlarında geçiyor."""
        ad = self.ad or self.kimlik or self.tur or "a control"
        return f"{ad!r} in {self.pencere!r}" if self.pencere else repr(ad)


def _metin(deger: Any) -> str:
    try:
        return str(deger or "")
    except Exception:
        return ""


def _ust_pencere(denetim):
    """Denetimin en üstteki penceresi. Bulunamazsa None."""
    try:
        import uiautomation as auto

        kok = auto.GetRootControl()
        gecerli = denetim
        for _ in range(MAX_DERINLIK):
            if gecerli is None:
                return None
            ust = gecerli.GetParentControl()
            if ust is None or auto.ControlsAreSame(ust, kok):
                return gecerli
            gecerli = ust
    except Exception:
        return None
    return None


def noktada(vx: int, vy: int) -> Imza | None:
    """Sanal masaüstündeki noktadaki denetimin imzası.

    Hiçbir hata dışarı çıkmıyor: imza bir kolaylık ve alınamaması bir
    tıklamayı engellememeli.
    """
    try:
        import uiautomation as auto

        denetim = auto.ControlFromPoint(int(vx), int(vy))
        if denetim is None:
            return None
        pencere = _ust_pencere(denetim)
        imza = Imza(
            tur=_metin(denetim.ControlTypeName),
            ad=_metin(denetim.Name)[:120],
            kimlik=_metin(denetim.AutomationId)[:120],
            sinif=_metin(denetim.ClassName)[:80],
            pencere=_metin(pencere.Name)[:120] if pencere is not None else "",
        )
        return None if imza.bos else imza
    except Exception:
        # COMError (oyun, yükseltilmiş pencere), zaman aşımı, kapanmış
        # pencere. Hepsi normal ve hiçbiri kaydı durdurmamalı.
        return None


def _puan(imza: Imza, denetim) -> int:
    """Adayın imzayla ne kadar örtüştüğü. 0 hiç değil."""
    tur = _metin(denetim.ControlTypeName)
    ad = _metin(denetim.Name)
    kimlik = _metin(denetim.AutomationId)
    if imza.kimlik and kimlik == imza.kimlik:
        return 3 if (not imza.tur or tur == imza.tur) else 2
    if imza.ad and ad == imza.ad:
        return 2 if (not imza.tur or tur == imza.tur) else 1
    return 0


def _pencereyi_bul(baslik: str):
    """Başlığı verilen üst düzey pencere.

    Tam eşleşme önce; sonra önek. Başlıklar değişiyor — "belge.txt -
    Not Defteri" kaydedilince yıldızı gidiyor — ve tam eşleşmede
    ısrar etmek akışı ilk kaydetmede kırardı.
    """
    import uiautomation as auto

    try:
        cocuklar = auto.GetRootControl().GetChildren()
    except Exception:
        return None
    if not baslik:
        return None
    for pencere in cocuklar:
        if _metin(pencere.Name) == baslik:
            return pencere
    kisa = baslik.split(" - ")[0].strip()
    for pencere in cocuklar:
        ad = _metin(pencere.Name)
        if kisa and (ad.startswith(kisa) or kisa in ad):
            return pencere
    return None


def bul(imza: Imza, kok=None) -> tuple[int, int] | None:
    """İmzaya uyan denetimin şu anki merkezi, sanal masaüstü uzayında.

    Bulunamazsa `None`. Uydurma bir koordinat döndürmek, akışı ekranda
    rastgele bir yere tıklatmak olurdu — kaybedilecek en kötü şey.
    """
    if imza is None or imza.bos:
        return None
    try:
        import uiautomation as auto

        baslangic = kok if kok is not None else _pencereyi_bul(imza.pencere)
        if baslangic is None:
            baslangic = auto.GetRootControl()

        en_iyi, en_iyi_puan = None, 0
        yigin = [(baslangic, 0)]
        gorulen = 0
        while yigin and gorulen < MAX_DUGUM:
            denetim, derinlik = yigin.pop()
            gorulen += 1
            puan = _puan(imza, denetim)
            if puan > en_iyi_puan:
                en_iyi, en_iyi_puan = denetim, puan
                if puan == 3:
                    break
            if derinlik < MAX_DERINLIK:
                try:
                    for cocuk in denetim.GetChildren():
                        yigin.append((cocuk, derinlik + 1))
                except Exception:
                    continue
        if en_iyi is None:
            return None
        kutu = en_iyi.BoundingRectangle
        if kutu is None or (kutu.right - kutu.left) <= 0:
            return None
        return ((kutu.left + kutu.right) // 2, (kutu.top + kutu.bottom) // 2)
    except Exception:
        return None
