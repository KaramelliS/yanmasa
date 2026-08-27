"""Ajanın SVG varlıklarını üretir.

    python scripts/svg_yap.py

Neden elle yazılmış bir `.svg` değil de üreten bir betik: gövde bir
süperelips ve köşeleri elle uydurulmuş sayılarla yazmak, eğriyi yanlış
yapmanın en kolay yolu. Burada eğri hesaplanıyor; oranı değiştirmek
istediğinde tek sabiti değiştirip yeniden üretiyorsun.

**Köşeler yuvarlatılmış dikdörtgen değil, süperelips.** `rx` ile
yuvarlatılan bir dikdörtgenin köşesi dairesel bir yay ve kenara
bağlandığı yerde eğrilik birden sıçrıyor — büyük yarıçapta bu göze
çarpıyor. Süperelipste eğrilik sürekli; iOS'un ve modern arayüzlerin
köşesi bu yüzden bu.

Dosyalar parçalara ayrılmış ve her parçanın `id`'si var: `govde`,
`goz-<tür>-<taraf>`. Qt tek tek eleman çizebiliyor, yani gövdeyi ezip
gözleri kaydırmak koda kalıyor. Tek parça bir SVG bunu yapamazdı.

Renkler yer tutucu: `RENK_GOVDE` ve `RENK_OYUK` yükleme anında temadan
gelen değerlerle değiştiriliyor. SVG'ye sabit renk gömmek, temayı
değiştirdiğinde maskotu yabancı bırakırdı.
"""

from __future__ import annotations

import math
from pathlib import Path

HEDEF = Path(__file__).resolve().parent.parent / "varliklar" / "svg"

#: Çizim alanı.
VB = 96.0
MERKEZ = VB / 2

#: Gövdenin yarıçapı ve süperelips üssü.
#:
#: 4.2 ile başladım ve çizip baktığımda gövde yuvarlatılmış bir kare gibi
#: duruyordu — maskot değil, düğme. 2.8 daireye yaklaşıyor ama tam daire
#: olmuyor: köşelerde kalan hafif düzlük karakteri veren şey.
GOVDE_R = 38.0
USTEL = 2.8

#: Süperelipsi kaç noktada örnekleyeceğiz. 96'lık kutuda 120 nokta,
#: 40 piksele küçültüldüğünde bile köşe pürüzsüz kalıyor ve dosya 3 KB.
ORNEK = 120

#: Yer tutucu renkler. Yükleme anında temadan gelenlerle değişiyor.
RENK_GOVDE = "#E7BABD"
RENK_OYUK = "#1C1C1C"
RENK_HATA = "#FF99A4"

#: Gözlerin merkeze uzaklığı ve yarık ölçüleri.
GOZ_X, GOZ_Y = 11.5, -5.5
YARIK_W, YARIK_H, YARIK_EGIM = 7.2, 24.0, 13.0


def superelips(r: float, n: float, adet: int) -> str:
    """Süperelipsi kapalı bir yol olarak döndürür."""
    noktalar = []
    for i in range(adet):
        a = 2 * math.pi * i / adet
        c, s = math.cos(a), math.sin(a)
        # |x/r|^n + |y/r|^n = 1 çözümü, kutupsal biçimde.
        x = r * math.copysign(abs(c) ** (2 / n), c)
        y = r * math.copysign(abs(s) ** (2 / n), s)
        noktalar.append((MERKEZ + x, MERKEZ + y))
    ilk = noktalar[0]
    govde = " ".join(f"L{x:.2f} {y:.2f}" for x, y in noktalar[1:])
    return f"M{ilk[0]:.2f} {ilk[1]:.2f} {govde} Z"


def yarik(taraf: int, uzunluk: float, egim: float) -> str:
    """Tek bir yarık göz: yuvarlatılmış dikdörtgen, eğik."""
    x = MERKEZ + GOZ_X * taraf
    y = MERKEZ + GOZ_Y
    return (
        f'<rect x="{-YARIK_W / 2:.2f}" y="{-uzunluk / 2:.2f}" '
        f'width="{YARIK_W:.2f}" height="{uzunluk:.2f}" '
        f'rx="{YARIK_W / 2:.2f}" fill="{RENK_OYUK}" '
        f'transform="translate({x:.2f} {y:.2f}) rotate({egim:.1f})"/>'
    )


def gulen(taraf: int) -> str:
    """Gülen göz: yukarı kıvrılan yay."""
    x = MERKEZ + GOZ_X * taraf
    y = MERKEZ + GOZ_Y + 2.0
    g = 13.0
    return (
        f'<path d="M{x - g / 2:.2f} {y:.2f} Q{x:.2f} {y - 11:.2f} '
        f'{x + g / 2:.2f} {y:.2f}" fill="none" stroke="{RENK_OYUK}" '
        f'stroke-width="{YARIK_W:.2f}" stroke-linecap="round"/>'
    )


#: Göz türleri. Her tür bir uzunluk ve eğim; kızgın olan ters dönüyor.
#:
#: Kızgınlığı renge bırakmıyoruz: bu temada vurgu rengi #e7babd, hata
#: rengi #ff99a4 ve küçük bir yarıkta ikisi ayırt edilemiyor. Biçim
#: renkten bağımsız okunuyor.
#: `aynali` olanlarda iki göz ters yöne dönüyor. Kızgın yüz böyle
#: oluyor: aynı yöne eğik iki yarık kızgın değil, sadece eğik duruyor —
#: çizip baktım, fark bu.
GOZLER = {
    "normal": (YARIK_H, YARIK_EGIM, False),
    "genis": (YARIK_H * 1.25, YARIK_EGIM, False),
    "kisik": (YARIK_H * 0.55, YARIK_EGIM, False),
    "kapali": (YARIK_W * 1.05, YARIK_EGIM, False),
    "kizgin": (YARIK_H * 0.92, 32.0, True),
}


def yuz_svg() -> str:
    parcalar = [
        f'<path id="govde" d="{superelips(GOVDE_R, USTEL, ORNEK)}" fill="{RENK_GOVDE}"/>'
    ]
    for ad, (uzunluk, egim, aynali) in GOZLER.items():
        for taraf, yon in ((-1, "sol"), (1, "sag")):
            e = egim * taraf if aynali else egim
            parcalar.append(
                f'<g id="goz-{ad}-{yon}">{yarik(taraf, uzunluk, e)}</g>'
            )
    for taraf, yon in ((-1, "sol"), (1, "sag")):
        parcalar.append(f'<g id="goz-gulen-{yon}">{gulen(taraf)}</g>')

    ic = "\n  ".join(parcalar)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VB:.0f} {VB:.0f}" '
        f'width="{VB:.0f}" height="{VB:.0f}">\n'
        f'  <!-- Üreten: scripts/svg_yap.py — elle düzenleme, betiği düzenle. -->\n'
        f'  {ic}\n</svg>\n'
    )


def main() -> int:
    HEDEF.mkdir(parents=True, exist_ok=True)
    yol = HEDEF / "yuz.svg"
    metin = yuz_svg()
    yol.write_text(metin, encoding="utf-8")
    print(f"{yol}  {len(metin)} bayt, {len(GOZLER) * 2 + 3} parça")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
