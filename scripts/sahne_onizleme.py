"""Maskotun **canlı** sahnelerinin önizlemesi.

    python scripts/sahne_onizleme.py

`svg_onizleme.py` dosyadaki SVG'leri render ediyor; burası uygulamanın
gerçekten çizdiği şeyi alıyor — yüz yuvasına oturmuş, gözler o işe göre
bakıyor, profil açık, hareketli parçalar bir an dondurulmuş hâlde. İkisi
aynı şey değil: sahnenin yarısı SVG'de bile yok.

Tasarım kararı verirken bakılacak kare bu. Sütun ekranda 78 piksel ve o
boyutta hiçbir şey görülmüyor, o yüzden dört kat büyütülüyor.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HEDEF = (Path(__file__).resolve().parent.parent / "varliklar" / "onizleme"
         / "_sahneler.png")

#: Büyütme. Sütun 78 piksel ve o boyutta kolun kalınlığı görülmüyor.
KAT = 4

#: Etiket şeridinin yüksekliği. Beş sahne birbirine benzemiyor ama
#: hangisinin hangi araç olduğu isimsiz bir kareden çıkmıyor.
ETIKET = 22

#: Sahneleri temsil eden araçlar.
SAHNELER = [
    ("büyüteç", "screenshot"),
    ("dizüstü", "office_edit"),
    ("terminal", "run_shell"),
    ("sayfa", "write_file"),
    ("sunucu", "remote_list"),
]

#: Kaç kare ilerletilsin. Yaylar yerine oturmalı, yoksa nesne yarı yolda
#: yakalanıyor ve kare tasarımı değil geçişi gösteriyor.
KARE = 180


def main() -> int:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter
    from PySide6.QtWidgets import QApplication

    from app import fluent
    from app.sahne import GENISLIK, YUKSEKLIK, Sahne
    from app.stream import RunRing

    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    t = fluent.tokens()

    kart = QImage(GENISLIK * KAT * len(SAHNELER), YUKSEKLIK * KAT + ETIKET,
                  QImage.Format.Format_ARGB32)
    kart.fill(QColor(t.background))
    p = QPainter(kart)
    yazi = QFont()
    yazi.setPointSizeF(9.0)
    p.setFont(yazi)

    for i, (ad, arac) in enumerate(SAHNELER):
        halka = RunRing(t, 52)
        sahne = Sahne(t, halka)
        sahne.resize(GENISLIK, YUKSEKLIK)
        sahne._yerlestir()
        sahne.set_tool(arac)
        # Halka yüzü sürüyor: göz türü ve animasyon oradan geliyor.
        halka.begin()
        halka.step(arac)
        for _ in range(KARE):
            sahne._tick(1 / 60)
            adim = getattr(halka, "_tick", None)
            if adim is not None:
                adim(1 / 60)

        im = QImage(GENISLIK, YUKSEKLIK, QImage.Format.Format_ARGB32)
        im.fill(QColor(0, 0, 0, 0))
        sahne.render(im)
        p.drawImage(
            QRectF(i * GENISLIK * KAT, 0, GENISLIK * KAT, YUKSEKLIK * KAT), im
        )
        p.setPen(QColor(t.text_tertiary))
        p.drawText(
            QRectF(i * GENISLIK * KAT, YUKSEKLIK * KAT, GENISLIK * KAT, ETIKET),
            int(Qt.AlignmentFlag.AlignCenter), ad,
        )
    p.end()
    HEDEF.parent.mkdir(parents=True, exist_ok=True)
    kart.save(str(HEDEF))
    print(f"{len(SAHNELER)} sahne -> {HEDEF} ({kart.width()}x{kart.height()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
