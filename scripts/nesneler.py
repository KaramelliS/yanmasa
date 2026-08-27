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

import re

#: Nesnelerin çizim alanı. Yüzden küçük: nesne yanda duruyor, sahneyi
#: paylaşıyorlar.
VB = 64.0

RENK_GOVDE = "#E7BABD"
RENK_OYUK = "#1C1C1C"


def _parcala(*parcalar: str) -> list[tuple[str, str]]:
    """Şekilleri `(id, markup)` çiftlerine ayırır.

    Nesneler iki yerde kullanılıyor: kendi başına duran önizleme
    dosyasında ve maskotun elinde durduğu sahne dosyasında. İkincisinde
    her parça bir dönüşümün içine sarılıyor, o yüzden markup'ın kendisi
    değil parçaları gerekiyor. Kimlikleri elle ikinci kez yazmak yerine
    şeklin içinden okunuyor — iki liste böylece ayrı düşemiyor.
    """
    return [(re.search(r'id="([^"]+)"', m).group(1), m) for m in parcalar]


def svg(ad: str) -> str:
    """Tek nesnenin kendi başına duran SVG'si — önizleme için."""
    return _svg(*(m for _, m in NESNELER[ad]()))


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


def laptop() -> list[tuple[str, str]]:
    """Açık bir dizüstü. Ekran satırları ayrı: yazarken sırayla uzayıp
    kısalıyorlar ve bu, ekranda bir şeyin yazıldığını anlatan en ucuz
    hareket."""
    return _parcala(
        f'<path id="taban" d="M9 45 L55 45 L59 52 Q59 54 57 54 L7 54 '
        f'Q5 54 5 52 Z" fill="{RENK_GOVDE}"/>',
        _kutu("tus", 24, 48, 16, 2.6, 1.3, RENK_OYUK),
        _kutu("ekran", 12, 9, 40, 34, 4, RENK_GOVDE),
        _kutu("satir-1", 17, 15, 24, 3.4, 1.7, RENK_OYUK),
        _kutu("satir-2", 17, 22, 17, 3.4, 1.7, RENK_OYUK),
        _kutu("satir-3", 17, 29, 21, 3.4, 1.7, RENK_OYUK),
    )


def terminal() -> list[tuple[str, str]]:
    """Kabuk penceresi: iki düğme, istem işareti, yanıp sönen imleç."""
    return _parcala(
        _kutu("pencere", 6, 12, 52, 40, 5, RENK_GOVDE),
        _kutu("nokta-1", 11, 16, 4, 4, 2, RENK_OYUK, ' opacity="0.5"'),
        _kutu("nokta-2", 18, 16, 4, 4, 2, RENK_OYUK, ' opacity="0.5"'),
        f'<path id="istem" d="M14 31 L19 35 L14 39" fill="none" '
        f'stroke="{RENK_OYUK}" stroke-width="3" stroke-linecap="round" '
        f'stroke-linejoin="round"/>',
        _kutu("imlec", 24, 33.4, 13, 3.2, 1.6, RENK_OYUK),
    )


def mercek() -> list[tuple[str, str]]:
    """Mercek: halka cam ve sap. Parıltı ayrı, cam üstünde geziniyor.

    **Cam kutunun ortasında.** Önce (27, 26)'daydı ve maskotun sağ eli
    boşlukta kalıyordu: öteki dört nesne ellerin arasını dolduran birer
    levha, mercek ise ince bir halka ve kütlesi sola kaçmıştı. Ekranda
    nesne karakterden kopuk duruyordu — Berkay da bunu söyledi.

    Cam merkeze alındı ve büyütüldü; eller de bu nesnede camın alt
    yanaklarına iniyor (`EL_KONUM`), çünkü bir merceği köşelerinden değil
    kenarından tutarsın. Halkayı levhaya çevirmek de olurdu ve o zaman
    mercek olmaktan çıkardı.

    Sap da yer değiştirdi. Klasik yeri sağ alt köşedeydi ve orada sağ
    elin tam altına düşüyordu: çizip baktım, sap görünmüyordu ve nesne
    merceğe değil çembere benziyordu. Şimdi camdan aşağı, iki elin
    arasındaki boşluğa iniyor.
    """
    return _parcala(
        f'<rect id="sap" x="28" y="44" width="8" height="16" rx="4" '
        f'fill="{RENK_GOVDE}"/>',
        f'<circle id="cam" cx="32" cy="28" r="20" fill="{RENK_GOVDE}"/>',
        f'<circle id="cam-ic" cx="32" cy="28" r="12.5" fill="{RENK_OYUK}"/>',
        f'<circle id="parilti" cx="26" cy="22" r="4" fill="{RENK_GOVDE}" '
        f'opacity="0.5"/>',
    )


def sunucu() -> list[tuple[str, str]]:
    """Sunucu: üst üste iki raf, sırayla yanan iki ışık."""
    return _parcala(
        _kutu("raf-ust", 12, 13, 40, 17, 4.5, RENK_GOVDE),
        _kutu("yuva-ust", 18, 19.5, 14, 3.4, 1.7, RENK_OYUK),
        f'<circle id="isik-ust" cx="45" cy="21.2" r="2.8" fill="{RENK_OYUK}"/>',
        _kutu("raf-alt", 12, 34, 40, 17, 4.5, RENK_GOVDE),
        _kutu("yuva-alt", 18, 40.5, 14, 3.4, 1.7, RENK_OYUK),
        f'<circle id="isik-alt" cx="45" cy="42.2" r="2.8" fill="{RENK_OYUK}"/>',
    )


def sayfa() -> list[tuple[str, str]]:
    """Dosya: köşesi kıvrık sayfa, satırlar sırayla beliriyor."""
    return _parcala(
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
