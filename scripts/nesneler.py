"""Maskotun yanında beliren nesneler.

Ofiste bir dizüstü, kabukta bir terminal penceresi, ekrana bakarken bir
mercek, uzak makinede bir sunucu, dosya yazarken bir sayfa. Bunlar simge
değil — maskotun **üstünde çalıştığı** nesneler ve yüzle aynı dilde
çizildiler: dolu gövde, arka plan rengiyle oyulmuş ayrıntılar, kontur
yok.

Simge "bu iş bir dosya işi" der ve orada kalır. Nesne, maskotun ona
doğru eğilmesini, ona bakmasını, bir yerinin kıpırdamasını mümkün
kılıyor. İzlediğin şey bir etiket değil, çalışan biri oluyor.

**Bütün parçalar düz, iç içe değil.** Her `id` doğrudan `<svg>` altında
duruyor. Qt bir elemanı `id` ile çizebiliyor ama iç içe olanları tek tek
ayıramıyorsun: laptopun ekran satırları `ekran` grubunun içinde olsaydı
sırayla uzayıp kısalamazlardı. Çizim sırası kodda, `PARCALAR`'da.

Renkler yer tutucu; yükleme anında temadan gelenlerle değişiyor.
"""

from __future__ import annotations

#: Nesnelerin çizim alanı. Yüzden küçük: nesne yanda duruyor, sahneyi
#: paylaşıyorlar.
VB = 64.0

RENK_GOVDE = "#E7BABD"
RENK_OYUK = "#1C1C1C"


def _svg(*parcalar: str) -> str:
    ic = "\n  ".join(parcalar)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {VB:.0f} {VB:.0f}" '
        f'width="{VB:.0f}" height="{VB:.0f}">\n'
        "  <!-- Üreten: scripts/svg_yap.py -->\n"
        f"  {ic}\n"
        "</svg>\n"
    )


def _kutu(id_, x, y, w, h, r, renk, ek="") -> str:
    return (f'<rect id="{id_}" x="{x}" y="{y}" width="{w}" height="{h}" '
            f'rx="{r}" fill="{renk}"{ek}/>')


def laptop() -> str:
    """Açık bir dizüstü. Ekran satırları ayrı: yazarken sırayla uzayıp
    kısalıyorlar ve bu, ekranda bir şeyin yazıldığını anlatan en ucuz
    hareket."""
    return _svg(
        f'<path id="taban" d="M9 45 L55 45 L59 52 Q59 54 57 54 L7 54 '
        f'Q5 54 5 52 Z" fill="{RENK_GOVDE}"/>',
        _kutu("tus", 24, 48, 16, 2.6, 1.3, RENK_OYUK),
        _kutu("ekran", 12, 9, 40, 34, 4, RENK_GOVDE),
        _kutu("satir-1", 17, 15, 24, 3.4, 1.7, RENK_OYUK),
        _kutu("satir-2", 17, 22, 17, 3.4, 1.7, RENK_OYUK),
        _kutu("satir-3", 17, 29, 21, 3.4, 1.7, RENK_OYUK),
    )


def terminal() -> str:
    """Kabuk penceresi: iki düğme, istem işareti, yanıp sönen imleç."""
    return _svg(
        _kutu("pencere", 6, 12, 52, 40, 5, RENK_GOVDE),
        _kutu("nokta-1", 11, 16, 4, 4, 2, RENK_OYUK, ' opacity="0.5"'),
        _kutu("nokta-2", 18, 16, 4, 4, 2, RENK_OYUK, ' opacity="0.5"'),
        f'<path id="istem" d="M14 31 L19 35 L14 39" fill="none" '
        f'stroke="{RENK_OYUK}" stroke-width="3" stroke-linecap="round" '
        f'stroke-linejoin="round"/>',
        _kutu("imlec", 24, 33.4, 13, 3.2, 1.6, RENK_OYUK),
    )


def mercek() -> str:
    """Mercek: halka cam ve sap. Parıltı ayrı, cam üstünde geziniyor."""
    return _svg(
        f'<rect id="sap" x="37" y="37" width="20" height="7.5" rx="3.75" '
        f'fill="{RENK_GOVDE}" transform="rotate(45 37 37)"/>',
        f'<circle id="cam" cx="27" cy="26" r="18.5" fill="{RENK_GOVDE}"/>',
        f'<circle id="cam-ic" cx="27" cy="26" r="12" fill="{RENK_OYUK}"/>',
        f'<circle id="parilti" cx="22" cy="21" r="3.6" fill="{RENK_GOVDE}" '
        f'opacity="0.5"/>',
    )


def sunucu() -> str:
    """Sunucu: üst üste iki raf, sırayla yanan iki ışık."""
    return _svg(
        _kutu("raf-ust", 12, 13, 40, 17, 4.5, RENK_GOVDE),
        _kutu("yuva-ust", 18, 19.5, 14, 3.4, 1.7, RENK_OYUK),
        f'<circle id="isik-ust" cx="45" cy="21.2" r="2.8" fill="{RENK_OYUK}"/>',
        _kutu("raf-alt", 12, 34, 40, 17, 4.5, RENK_GOVDE),
        _kutu("yuva-alt", 18, 40.5, 14, 3.4, 1.7, RENK_OYUK),
        f'<circle id="isik-alt" cx="45" cy="42.2" r="2.8" fill="{RENK_OYUK}"/>',
    )


def sayfa() -> str:
    """Dosya: köşesi kıvrık sayfa, satırlar sırayla beliriyor."""
    return _svg(
        f'<path id="kagit" d="M15 7 L39 7 L50 18 L50 55 Q50 57 48 57 '
        f'L17 57 Q15 57 15 55 Z" fill="{RENK_GOVDE}"/>',
        f'<path id="kivrim" d="M39 7 L39 18 L50 18 Z" fill="{RENK_OYUK}" '
        f'opacity="0.42"/>',
        _kutu("satir-1", 22, 27, 21, 3.2, 1.6, RENK_OYUK),
        _kutu("satir-2", 22, 35, 14, 3.2, 1.6, RENK_OYUK),
        _kutu("satir-3", 22, 43, 18, 3.2, 1.6, RENK_OYUK),
    )


NESNELER = {
    "laptop": laptop,
    "terminal": terminal,
    "mercek": mercek,
    "sunucu": sunucu,
    "sayfa": sayfa,
}

#: Çizim sırası. SVG'de sıra da anlam taşır ama biz elemanları tek tek
#: çizdiğimiz için sırayı burada tutuyoruz.
PARCALAR = {
    "laptop": ["taban", "tus", "ekran", "satir-1", "satir-2", "satir-3"],
    "terminal": ["pencere", "nokta-1", "nokta-2", "istem", "imlec"],
    "mercek": ["sap", "cam", "cam-ic", "parilti"],
    "sunucu": ["raf-ust", "yuva-ust", "isik-ust",
               "raf-alt", "yuva-alt", "isik-alt"],
    "sayfa": ["kagit", "kivrim", "satir-1", "satir-2", "satir-3"],
}
