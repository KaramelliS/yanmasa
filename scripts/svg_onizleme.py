"""Bütün SVG varlıklarının PNG önizlemesini üretir.

    python scripts/svg_onizleme.py

`varliklar/svg` altındaki her dosyayı `varliklar/onizleme` altına PNG
olarak yazıyor, üstüne de hepsini tek karede gösteren bir tabaka.

Neden gerekli: bu SVG'ler `scripts/svg_yap.py` tarafından hesaplanarak
üretiliyor ve dosyaya bakarak neye benzediklerini anlamak mümkün değil —
gövde 140 noktalı bir çokgen. Bir sabiti değiştirip yeniden ürettiğinde
sonucu görmenin tek yolu render etmek.

**Zemin koyu.** Varlıkların rengi maskotun teni ve beyaz zeminde 1.2:1
kontrastla kayboluyorlar; uygulamada da koyu yüzeyin üstünde duruyorlar.
Şeffaf PNG yazmak "dosya gezgininde bakınca boş" demek olurdu.

`gozler.svg` tek dosyada bütün göz türlerini taşıyor ve olduğu gibi
render edilirse hepsi üst üste biniyor. O yüzden eleman eleman
ayrılıyor — uygulamanın kendisi de onları `id` ile tek tek çiziyor.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
KAYNAK = KOK / "varliklar" / "svg"
HEDEF = KOK / "varliklar" / "onizleme"

#: Tek varlığın PNG kenarı. Ekranda en büyük kullanım 52 piksel; 256
#: hem eğrileri hem de göz kapsüllerinin uçlarını görünür kılıyor.
BOYUT = 256

#: İki zemin, çünkü varlıkların iki katmanı var. Gövde ve nesneler ten
#: rengiyle çizilip koyu yüzeyin üstünde duruyor; gözler ise **gövdenin
#: içine** koyu renkle oyuluyor. Hepsini koyu zemine koyunca gözler
#: kendi rengiyle aynı zeminde kaybolmuştu — ilk üretimde on iki kare
#: tamamen boş çıktı.
ZEMIN_KOYU = "#1C1C1C"
ZEMIN_TEN = "#E7BABD"

#: Etiket şeridi. On poz birbirine benziyor ve hangisinin hangisi
#: olduğunu isimsiz bir tabakadan çıkarmak mümkün değil.
ETIKET_H = 30
ETIKET_RENK = "#8C8C8C"

#: Tabakadaki sütun sayısı.
SUTUN = 6
PAY = 12


def _elemanlar(yol: Path) -> list[str]:
    """Dosyadaki `id`'ler — yalnızca ayrı çizilmesi gerekenler için."""
    return re.findall(r'<g id="([^"]+)"', yol.read_text(encoding="utf-8"))


def main() -> int:
    from PySide6.QtCore import Qt, QRectF
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import QApplication

    if not KAYNAK.is_dir():
        print(f"no source: {KAYNAK} — run scripts/svg_yap.py first")
        return 1

    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    HEDEF.mkdir(parents=True, exist_ok=True)

    def kare(cizici: QSvgRenderer, eleman: str | None = None,
             ad: str = "") -> QImage:
        im = QImage(BOYUT, BOYUT, QImage.Format.Format_ARGB32)
        im.fill(QColor(ZEMIN_TEN if ad.startswith("goz-") else ZEMIN_KOYU))
        p = QPainter(im)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if eleman is None:
            cizici.render(p)
        else:
            # `render(p, id, hedef)` elemanı hedef dikdörtgene **yayıyor**.
            # Hedefi kare verince 12.2x6.1'lik göz kapsülü kareye
            # geriliyordu ve şekli yanlış görünüyordu. Elemanın kendi
            # kutusunu ölçüp oranını koruyoruz; böylece göz hem doğru
            # biçimde hem de yüzdeki gerçek yerinde çıkıyor.
            kutu = cizici.boundsOnElement(eleman)
            olcek = BOYUT / max(cizici.viewBoxF().width(), 1.0)
            cizici.render(p, eleman, QRectF(
                kutu.x() * olcek, kutu.y() * olcek,
                kutu.width() * olcek, kutu.height() * olcek,
            ))
        p.end()
        return im

    yazilan: list[tuple[str, QImage]] = []
    for yol in sorted(KAYNAK.glob("*.svg")):
        cizici = QSvgRenderer(str(yol))
        if not cizici.isValid():
            print(f"  skipped (invalid): {yol.name}")
            continue
        parcalar = _elemanlar(yol)
        if len(parcalar) > 1:
            for ad in parcalar:
                im = kare(cizici, ad, ad)
                im.save(str(HEDEF / f"{ad}.png"))
                yazilan.append((ad, im))
        else:
            im = kare(cizici, None, yol.stem)
            im.save(str(HEDEF / f"{yol.stem}.png"))
            yazilan.append((yol.stem, im))

    if not yazilan:
        print("render edilecek SVG yok")
        return 1

    satir = (len(yazilan) + SUTUN - 1) // SUTUN
    hucre = BOYUT + ETIKET_H
    tabaka = QImage(
        SUTUN * BOYUT + (SUTUN + 1) * PAY,
        satir * hucre + (satir + 1) * PAY,
        QImage.Format.Format_ARGB32,
    )
    tabaka.fill(QColor(ZEMIN_KOYU))
    p = QPainter(tabaka)
    yazi = p.font()
    yazi.setPointSizeF(11.0)
    p.setFont(yazi)
    for i, (ad, im) in enumerate(yazilan):
        x = PAY + (i % SUTUN) * (BOYUT + PAY)
        y = PAY + (i // SUTUN) * hucre
        p.drawImage(x, y, im)
        p.setPen(QColor(ETIKET_RENK))
        p.drawText(QRectF(x, y + BOYUT, BOYUT, ETIKET_H),
                   int(Qt.AlignmentFlag.AlignCenter), ad)
    p.end()
    tabaka.save(str(HEDEF / "_tabaka.png"))

    print(f"{len(yazilan)} previews -> {HEDEF}")
    for ad, _ in yazilan:
        print(f"  {ad}")
    print(f"  _tabaka.png  ({tabaka.width()}x{tabaka.height()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
