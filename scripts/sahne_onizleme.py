"""Maskotun **canlı** sahnelerinin önizlemesi.

    python scripts/sahne_onizleme.py

`svg_onizleme.py` dosyadaki SVG'leri render ediyor; burası uygulamanın
gerçekten çizdiği şeyi alıyor — yüz yuvasına oturmuş, gözler o işe göre
bakıyor, profil açık, hareketli parçalar bir an dondurulmuş hâlde. İkisi
aynı şey değil: sahnenin yarısı SVG'de bile yok.

**İki kare yazılıyor.** Biri gerçek boyutta: ekranda görülecek olan o.
Biri büyütülmüş: ayrıntıya bakmak için. Yalnızca büyütülmüş kareye
bakarak tasarım yapmak, kimsenin görmeyeceği bir şeyi güzelleştirmek
olurdu — bu hatayı bir kez yaptım, sahneler 4× güzeldi ve 1× lapaydı.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ONIZLEME = Path(__file__).resolve().parent.parent / "varliklar" / "onizleme"

#: (dosya soneki, büyütme).
KATLAR = (("gercek", 1), ("buyuk", 3))

#: Etiket şeridinin yüksekliği.
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

    # Sahneler bir kez çiziliyor, iki ölçekte yazılıyor: aynı anı
    # göstersinler diye.
    kareler = []
    for _, arac in SAHNELER:
        halka = RunRing(t, 52)
        sahne = Sahne(t, halka)
        sahne.resize(GENISLIK, YUKSEKLIK)
        sahne._yerlestir()
        sahne.set_tool(arac)
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
        kareler.append(im)

    ONIZLEME.mkdir(parents=True, exist_ok=True)
    for sonek, kat in KATLAR:
        kart = QImage(GENISLIK * kat * len(SAHNELER),
                      YUKSEKLIK * kat + ETIKET,
                      QImage.Format.Format_ARGB32)
        kart.fill(QColor(t.background))
        p = QPainter(kart)
        yazi = QFont()
        yazi.setPointSizeF(9.0)
        p.setFont(yazi)
        for i, ((ad, _), im) in enumerate(zip(SAHNELER, kareler)):
            p.drawImage(
                QRectF(i * GENISLIK * kat, 0, GENISLIK * kat, YUKSEKLIK * kat),
                im,
            )
            p.setPen(QColor(t.text_tertiary))
            p.drawText(
                QRectF(i * GENISLIK * kat, YUKSEKLIK * kat,
                       GENISLIK * kat, ETIKET),
                int(Qt.AlignmentFlag.AlignCenter), ad,
            )
        p.end()
        yol = ONIZLEME / f"_sahneler-{sonek}.png"
        kart.save(str(yol))
        print(f"  {yol.name}  {kart.width()}x{kart.height()}")
    print(f"{len(SAHNELER)} sahne -> {ONIZLEME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
