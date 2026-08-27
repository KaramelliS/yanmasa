"""Ajanın SVG varlıklarını üretir.

    python scripts/svg_yap.py

Neden elle yazılmış `.svg` değil de üreten bir betik: gövde bir eğri ve
onu elle uydurulmuş sayılarla yazmak eğriyi yanlış yapmanın en kolay
yolu. Burada hesaplanıyor; oranı değiştirmek istediğinde tek sabiti
değiştirip yeniden üretiyorsun.

**Bütün pozlar aynı nokta sayısında.** Kritik olan bu: nokta sayıları
aynıysa iki şekil arasında geçiş, noktaları teker teker karıştırmaktan
ibaret. Farklı sayıda olsalardı şekil değiştirmek yol eşleştirme problemi
olurdu ve ara karelerde şekil bozulurdu.

Gövdenin biçimi süperelips tabanı artı yarıçapa binen bir dalga:

    x = |cosθ|^(2/n)·en · R · (1 + genlik·cos(lob·θ + faz))

Süperelips köşeyi verir — `rx` ile yuvarlatılan bir dikdörtgenin köşesi
dairesel yay ve kenara bağlandığı yerde eğrilik sıçrar, süperelipste
süreklidir. Dalga da bulutumsu çıkıntıları verir. Superformula da
denendi ve içbükey yıldızlar üretti; çıkıntıların **dışa** dönmesi
gerekiyordu.

Gözler ayrı parçalar (`goz-<tür>-<taraf>`). Qt tek tek eleman
çizebiliyor, yani gövde şekil değiştirirken gözler kendi başına
kayabiliyor.

Renkler yer tutucu; yükleme anında temadan gelenlerle değişiyor.
"""

from __future__ import annotations

import math
from pathlib import Path

HEDEF = Path(__file__).resolve().parent.parent / "varliklar" / "svg"

#: Çizim alanı.
VB = 96.0
MERKEZ = VB / 2
YARICAP = 36.0

#: Gövdenin nokta sayısı. Bütün pozlarda aynı olmak **zorunda**, yoksa
#: aralarında geçiş yapılamaz. 140 nokta 40 piksele küçültüldüğünde bile
#: pürüzsüz ve poz başına 2 KB.
NOKTA = 140

#: Yer tutucu renkler.
RENK_GOVDE = "#E7BABD"
RENK_OYUK = "#1C1C1C"

#: Gözlerin merkeze uzaklığı ve yarık ölçüleri.
GOZ_X, GOZ_Y = 11.5, -5.5
YARIK_W, YARIK_H, YARIK_EGIM = 7.2, 24.0, 13.0

#: Pozlar. `ustel` köşe sertliği, `en`/`boy` oran, `lob` kaç çıkıntı,
#: `genlik` ne kadar taştıkları, `faz` nereden başladıkları.
#:
#: Her animasyon iki poz arasında gidip geliyor; ikisi arasındaki fark
#: hareketin karakteri. Bekleme pozlarının farkı yalnızca faz — nefes
#: alıyormuş gibi duruyor. İş pozlarının eni ve boyu ters yönde değişiyor
#: — sıkışıp geniyor.
POZLAR = {
    "bosta":   dict(ustel=2.8, lob=4, genlik=0.05),
    "bosta-b": dict(ustel=2.8, lob=4, genlik=0.05, faz=math.pi / 4),
    "is":      dict(ustel=3.4, en=1.07, boy=0.93, lob=6, genlik=0.07),
    "is-b":    dict(ustel=3.4, en=0.93, boy=1.07, lob=6, genlik=0.07,
                    faz=math.pi / 6),
    "ofis":    dict(ustel=5.0, en=0.84, boy=1.12),
    "ofis-b":  dict(ustel=5.0, en=0.88, boy=1.08, lob=4, genlik=0.025),
    "dusun":   dict(ustel=2.1, lob=6, genlik=0.12),
    "dusun-b": dict(ustel=2.1, lob=6, genlik=0.12, faz=math.pi / 6),
    "hata":    dict(ustel=3.0, en=1.12, boy=0.84, lob=8, genlik=0.055),
    "bitti":   dict(ustel=2.0),
}


def govde_noktalari(ustel: float = 2.8, en: float = 1.0, boy: float = 1.0,
                    lob: int = 0, genlik: float = 0.0, faz: float = 0.0,
                    adet: int = NOKTA) -> list[tuple[float, float]]:
    noktalar = []
    for i in range(adet):
        th = 2 * math.pi * i / adet
        c, s = math.cos(th), math.sin(th)
        bx = math.copysign(abs(c) ** (2 / ustel), c) * en
        by = math.copysign(abs(s) ** (2 / ustel), s) * boy
        k = 1.0 + genlik * math.cos(lob * th + faz) if lob else 1.0
        noktalar.append((MERKEZ + bx * YARICAP * k, MERKEZ + by * YARICAP * k))
    return noktalar


def yol(noktalar) -> str:
    bas = noktalar[0]
    kalan = " ".join(f"L{x:.2f} {y:.2f}" for x, y in noktalar[1:])
    return f"M{bas[0]:.2f} {bas[1]:.2f} {kalan} Z"


def yarik(taraf: int, uzunluk: float, egim: float) -> str:
    x = MERKEZ + GOZ_X * taraf
    y = MERKEZ + GOZ_Y
    return (
        f'<rect x="{-YARIK_W / 2:.2f}" y="{-uzunluk / 2:.2f}" '
        f'width="{YARIK_W:.2f}" height="{uzunluk:.2f}" '
        f'rx="{YARIK_W / 2:.2f}" fill="{RENK_OYUK}" '
        f'transform="translate({x:.2f} {y:.2f}) rotate({egim:.1f})"/>'
    )


def gulen(taraf: int) -> str:
    x = MERKEZ + GOZ_X * taraf
    y = MERKEZ + GOZ_Y + 2.0
    g = 13.0
    return (
        f'<path d="M{x - g / 2:.2f} {y:.2f} Q{x:.2f} {y - 11:.2f} '
        f'{x + g / 2:.2f} {y:.2f}" fill="none" stroke="{RENK_OYUK}" '
        f'stroke-width="{YARIK_W:.2f}" stroke-linecap="round"/>'
    )


#: `aynali` olanlarda iki göz ters yöne dönüyor. Kızgın yüz böyle
#: oluyor: aynı yöne eğik iki yarık kızgın değil, sadece eğik duruyor.
GOZLER = {
    "normal": (YARIK_H, YARIK_EGIM, False),
    "genis": (YARIK_H * 1.25, YARIK_EGIM, False),
    "kisik": (YARIK_H * 0.55, YARIK_EGIM, False),
    "kapali": (YARIK_W * 1.05, YARIK_EGIM, False),
    "kizgin": (YARIK_H * 0.92, 32.0, True),
}


def _svg(ic: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VB:.0f} {VB:.0f}" '
        f'width="{VB:.0f}" height="{VB:.0f}">\n'
        f'  <!-- Üreten: scripts/svg_yap.py — elle düzenleme, betiği düzenle. -->\n'
        f'  {ic}\n</svg>\n'
    )


def poz_svg(ad: str) -> str:
    d = yol(govde_noktalari(**POZLAR[ad]))
    return _svg(f'<path id="govde" d="{d}" fill="{RENK_GOVDE}"/>')


def gozler_svg() -> str:
    parcalar = []
    for ad, (uzunluk, egim, aynali) in GOZLER.items():
        for taraf, yon in ((-1, "sol"), (1, "sag")):
            e = egim * taraf if aynali else egim
            parcalar.append(f'<g id="goz-{ad}-{yon}">{yarik(taraf, uzunluk, e)}</g>')
    for taraf, yon in ((-1, "sol"), (1, "sag")):
        parcalar.append(f'<g id="goz-gulen-{yon}">{gulen(taraf)}</g>')
    return _svg("\n  ".join(parcalar))


def main() -> int:
    HEDEF.mkdir(parents=True, exist_ok=True)
    for ad in POZLAR:
        (HEDEF / f"poz-{ad}.svg").write_text(poz_svg(ad), encoding="utf-8")
    (HEDEF / "gozler.svg").write_text(gozler_svg(), encoding="utf-8")
    print(f"{len(POZLAR)} poz + gözler -> {HEDEF}")
    print("  " + ", ".join(POZLAR))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
