"""Bloub siluetini kaynak SVG'den okuyup pozlara çevirir.

Gövdenin şeklini kendim çizmeyi denedim — süperelips artı yarıçapa binen
dalga — ve karakteri tutmadı: düğmeye benziyordu. Asıl siluet
`varliklar/kaynak/bloub.svg` içinde ve buradan geliyor.

**Yol noktalara çevriliyor.** Kaynak 64 kübik eğriden oluşuyor ve
aralarında geçiş yapmak için hepsinin aynı sayıda noktaya inmesi
gerekiyor. `QPainterPath.pointAtPercent` yolu yay uzunluğuna göre
örneklüyor, yani noktalar çevre boyunca eşit aralıklı çıkıyor. Ham
düğüm noktalarını almak eşit aralık vermezdi ve pozlar arası geçişte
şekil dalgalanırdı.

Pozlar aynı siluetten türüyor: enine/boyuna esneme, merkeze göre yarıçap
dalgası, ve nefes için hafif şişme. Böylece bekleme, iş, ofis ve düşünme
farklı görünüyor ama hepsi **aynı karakteri** taşıyor. Sıfırdan başka
şekiller çizseydim maskot her işte başka bir yaratığa dönerdi.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

KAYNAK = Path(__file__).resolve().parent.parent / "varliklar" / "kaynak" / "bloub.svg"

#: Hedef çizim alanı. Kaynak -125..125; buraya ölçekleniyor.
VB = 96.0
MERKEZ = VB / 2

#: Gövdenin nokta sayısı. Bütün pozlarda aynı olmak zorunda.
NOKTA = 160

#: Siluetin hedef yarıçapı — kaynakta ~96, burada bu.
OLCEK_R = 39.0


def _govde_yolu() -> str:
    metin = KAYNAK.read_text(encoding="utf-8")
    yollar = re.findall(r'd="(M91\.51[^"]+)"', metin)
    if not yollar:
        raise SystemExit("kaynak SVG'de gövde yolu yok")
    return yollar[0]


def _goz_matrisleri() -> list[tuple[float, ...]]:
    metin = KAYNAK.read_text(encoding="utf-8")
    return [
        tuple(float(x) for x in m.split(","))
        for m in re.findall(r'transform="matrix\(([^)]+)\)"', metin)
    ]


def taban_noktalari(adet: int = NOKTA) -> list[tuple[float, float]]:
    """Kaynak siluetini `adet` eşit aralıklı noktaya indirger."""
    from PySide6.QtGui import QPainterPath

    from PySide6.QtCore import QPointF  # noqa: F401  (Qt yol için gerekli)

    yol = QPainterPath()
    _yolu_kur(yol, _govde_yolu())

    noktalar = []
    for i in range(adet):
        p = yol.pointAtPercent(i / adet)
        # Kaynak -125..125 aralığında ve merkezi sıfırda; hedefe ölçekle.
        k = OLCEK_R / 96.0
        noktalar.append((MERKEZ + p.x() * k, MERKEZ + p.y() * k))
    return noktalar


def _yolu_kur(yol, d: str) -> None:
    """`M x y C ... Z` biçimindeki yolu `QPainterPath`e aktarır.

    Kaynağın kullandığı iki komut var: `M` ve `C`. Genel bir SVG yol
    ayrıştırıcı yazmak, ihtiyaç olmayan bir şeyi doğru yapmaya çalışmak
    olurdu — dosya değişirse burası da değişir.
    """
    from PySide6.QtCore import QPointF

    sayilar = re.findall(r"-?\d+\.?\d*", d)
    i = 0
    yol.moveTo(QPointF(float(sayilar[0]), float(sayilar[1])))
    i = 2
    while i + 5 < len(sayilar):
        yol.cubicTo(
            QPointF(float(sayilar[i]), float(sayilar[i + 1])),
            QPointF(float(sayilar[i + 2]), float(sayilar[i + 3])),
            QPointF(float(sayilar[i + 4]), float(sayilar[i + 5])),
        )
        i += 6
    yol.closeSubpath()


def poz(taban, en: float = 1.0, boy: float = 1.0, sis: float = 0.0,
        don: float = 0.0):
    """Tabanı esnetip döndürerek bir poz üretir.

    `en`/`boy` esneme, `sis` her yöne büyüme, `don` derece cinsinden
    dönme. Hepsi aynı siluetten türüyor, yani maskot her işte başka bir
    yaratığa dönmüyor.

    Yarıçapa dalga bindirmeyi de denedim ve bu siluette çalışmıyor:
    şekil zaten loblu ve ikinci bir dalga girişim yapıp yumru bir şeye
    dönüştürüyor. Çizip baktım — `hata` pozu tanınmaz hâldeydi. Kendi
    süperelipsimde çalışan şey, karakteri olan bir siluette çalışmıyor.
    """
    r = math.radians(don)
    c, sn = math.cos(r), math.sin(r)
    cikti = []
    for x, y in taban:
        dx, dy = (x - MERKEZ) * en * (1.0 + sis), (y - MERKEZ) * boy * (1.0 + sis)
        cikti.append((MERKEZ + dx * c - dy * sn, MERKEZ + dx * sn + dy * c))
    return cikti


#: Pozlar. Her animasyon iki poz arasında gidip geliyor ve aradaki fark
#: hareketin karakteri.
#:
#: - bekleme: yalnızca nefes — hafif şişip iniyor
#: - iş: eni ve boyu ters yönde değişiyor, sıkışıp geniyor
#: - ofis: dikleşiyor, belgeye doğru eğilmiş gibi
#: - düşünme: dalga geziniyor, kaynıyor
POZLAR = {
    # Bekleme: yalnızca nefes.
    "bosta":   dict(sis=0.0),
    "bosta-b": dict(sis=0.035),
    # İş: sıkışıp geniyor, hafifçe sağa sola yatıyor.
    "is":      dict(en=1.07, boy=0.93, don=-4.0),
    "is-b":    dict(en=0.94, boy=1.06, don=4.0),
    # Ofis: dikleşiyor, belgeye doğru eğilmiş gibi. Ağır ve dengeli.
    "ofis":    dict(en=0.90, boy=1.10, don=-2.0),
    "ofis-b":  dict(en=0.93, boy=1.07, sis=0.02, don=2.0),
    # Düşünme: yavaşça dönüyor — kafasında bir şey çeviriyor.
    "dusun":   dict(don=-11.0, sis=0.01),
    "dusun-b": dict(don=11.0, sis=0.01),
    # Hata: yayılıp çöküyor.
    "hata":    dict(en=1.12, boy=0.86, don=-6.0),
    "bitti":   dict(sis=0.02),
}
