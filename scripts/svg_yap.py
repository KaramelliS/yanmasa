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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bloub_kaynak import POZLAR as KAYNAK_POZLAR  # noqa: E402
from bloub_kaynak import poz as poz_uret  # noqa: E402
from bloub_kaynak import taban_noktalari  # noqa: E402
from nesneler import NESNELER  # noqa: E402

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

#: Göz ölçüleri kaynak SVG'den geliyor, uydurma değil.
#:
#: Kaynakta göz 30x15'lik yuvarlak uçlu bir kapsül — yani **yatay**,
#: benim ilk yaptığım dikey yarık değil. Merkezleri ve eğimleri de
#: oradan: (+11) ve (-14.6) derece. İkisi birbirinin tam aynası değil ve
#: simetrikleştirmek karakteri öldürüyor; elle çizilmiş olmasının izi bu.
GOZ_KONUM = ((39.18, 37.60, 11.0), (59.03, 37.53, -14.6))
GOZ_W, GOZ_H = 12.2, 6.1

#: Pozlar artık kaynak siluetten türüyor. Kendi süperelipsimi denedim
#: ve karakteri tutmadı — düğmeye benziyordu. `scripts/bloub_kaynak.py`
#: asıl silueti okuyup esnetiyor, yani bütün pozlar aynı yaratık.
POZLAR = KAYNAK_POZLAR


def yol(noktalar) -> str:
    bas = noktalar[0]
    kalan = " ".join(f"L{x:.2f} {y:.2f}" for x, y in noktalar[1:])
    return f"M{bas[0]:.2f} {bas[1]:.2f} {kalan} Z"


def goz(i: int, boy_carpani: float = 1.0, ek_egim: float = 0.0) -> str:
    """Tek bir göz: yuvarlak uçlu kapsül, kaynaktaki yerinde ve eğiminde."""
    x, y, egim = GOZ_KONUM[i]
    h = GOZ_H * boy_carpani
    return (
        f'<rect x="{-GOZ_W / 2:.2f}" y="{-h / 2:.2f}" '
        f'width="{GOZ_W:.2f}" height="{h:.2f}" rx="{min(GOZ_W, h) / 2:.2f}" '
        f'fill="{RENK_OYUK}" '
        f'transform="translate({x:.2f} {y:.2f}) rotate({egim + ek_egim:.1f})"/>'
    )


def gulen(i: int) -> str:
    """Gülen göz: yukarı kıvrılan yay."""
    x, y, egim = GOZ_KONUM[i]
    g = GOZ_W
    return (
        f'<path d="M{-g / 2:.2f} 0 Q0 {-g * 0.52:.2f} {g / 2:.2f} 0" '
        f'fill="none" stroke="{RENK_OYUK}" stroke-width="{GOZ_H * 0.9:.2f}" '
        f'stroke-linecap="round" '
        f'transform="translate({x:.2f} {y + 1.5:.2f}) rotate({egim:.1f})"/>'
    )


#: Göz türleri: boy çarpanı ve ek eğim.
#:
#: Kızgın olanda ek eğim aynalı — iki göz ters yöne dönüyor. Aynı yöne
#: eğik iki göz kızgın değil, sadece eğik duruyor.
GOZLER = {
    "normal": (1.0, 0.0, False),
    "genis": (1.75, 0.0, False),
    "kisik": (0.52, 0.0, False),
    "kapali": (0.26, 0.0, False),
    "kizgin": (0.9, 26.0, True),
}


def _svg(ic: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VB:.0f} {VB:.0f}" '
        f'width="{VB:.0f}" height="{VB:.0f}">\n'
        f'  <!-- Üreten: scripts/svg_yap.py — elle düzenleme, betiği düzenle. -->\n'
        f'  {ic}\n</svg>\n'
    )


_TABAN = None


def _taban():
    global _TABAN
    if _TABAN is None:
        _TABAN = taban_noktalari()
    return _TABAN


def poz_svg(ad: str) -> str:
    d = yol(poz_uret(_taban(), **POZLAR[ad]))
    return _svg(f'<path id="govde" d="{d}" fill="{RENK_GOVDE}"/>')


def gozler_svg() -> str:
    parcalar = []
    for ad, (boy, ek, aynali) in GOZLER.items():
        for i, yon in ((0, "sol"), (1, "sag")):
            e = ek * (1 if i else -1) if aynali else ek
            parcalar.append(f'<g id="goz-{ad}-{yon}">{goz(i, boy, e)}</g>')
    for i, yon in ((0, "sol"), (1, "sag")):
        parcalar.append(f'<g id="goz-gulen-{yon}">{gulen(i)}</g>')
    return _svg("\n  ".join(parcalar))


def main() -> int:
    HEDEF.mkdir(parents=True, exist_ok=True)
    for ad in POZLAR:
        (HEDEF / f"poz-{ad}.svg").write_text(poz_svg(ad), encoding="utf-8")
    (HEDEF / "gozler.svg").write_text(gozler_svg(), encoding="utf-8")
    for ad, yap in NESNELER.items():
        (HEDEF / f"nesne-{ad}.svg").write_text(yap(), encoding="utf-8")
    print(f"{len(POZLAR)} poz + gözler + {len(NESNELER)} nesne -> {HEDEF}")
    print("  poz:   " + ", ".join(POZLAR))
    print("  nesne: " + ", ".join(NESNELER))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
