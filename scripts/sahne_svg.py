"""Maskotun her işi için ayrı bir sahne, tek SVG.

Parçaları çalışma anında yan yana koymayı bıraktık: gövdeyi bir yer,
kolları bir formül, elleri başka bir sabit yerleştiriyordu ve sonuç monte
edilmiş görünüyordu. Kollar bir turda pelerine, bir turda kulağa döndü;
her düzeltme bir sonrakini doğurdu. Sebep şuydu: kimse sahneyi bir bütün
olarak **çizmiyordu**.

Daha önemlisi tek bir düzen beş işe yetmiyor. Berkay'ın tarifi şuydu ve
haklıydı: büyüteci gözünde tutar, dizüstünde iki eliyle klavyeye
dokunur, terminalde eli görünmez ve bize dönüktür, dosya yazarken
kalemle yazar ve sayfayı bize göstermez, sunucuda sarhoş gibi bakar.
Beş ayrı kompozisyon; beşini tek formülden çıkarmaya çalışmak beşini de
yanlış yapmaktı.

## Yüz neden bu dosyada değil

Yüz canlı: nefes alıyor, göz kırpıyor, yana dönüyor, hata olunca
sıçrıyor. Statik bir SVG'ye gömmek hepsini kaybetmek olurdu. Sahne bir
**yuva** bırakıyor — çizilmeyen bir dikdörtgen, "gövde buraya oturuyor"
diyor. Kolların uçları yuvanın içinde başlıyor ve gövde üstlerine
çiziliyor; ek yeri görünmüyor, tek silüet.

## Hareketli parçalar

Bazı parçalar uygulamada oynuyor ve konumlarını buradan alıyorlar.
Kablonun üstünde koşan kıvılcım bunun en zoru: eğrinin denklemi iki
yerde olsaydı bir gün ayrı düşerlerdi, o yüzden kontrol noktaları
`kablo-p0/p1/p2` kimlikleriyle dosyaya yazılıyor ve uygulama eğriyi
onlardan hesaplıyor.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bloub_kaynak import taban_noktalari  # noqa: E402

HEDEF = Path(__file__).resolve().parent.parent / "varliklar" / "svg"

#: Bütün sahneler aynı çizim alanında: sütun tek bir orana göre
#: ölçekleniyor ve sahne değişince maskot zıplamamalı.
VB_EN, VB_BOY = 96.0, 62.0

#: Nesnenin rengi.
RENK_GOVDE = "#E7BABD"
#: Nesnenin içine oyulan ayrıntılar — arka plan rengi.
RENK_OYUK = "#1C1C1C"
#: Yaratığın kendi parçaları: kol, el. Gövdenin rengi. Üçü de vurgu
#: rengi olduğunda kol, el ve nesne tek bir pembe kütleye dönüşüyordu.
RENK_TEN = "#C9A0A3"
#: Uzaktaki kol ve el. Aynı renk olsalardı iki kol tek kalın kol olurdu.
RENK_UZAK = "#9E7C7F"
#: Sunucunun yanıp sönen ışığı ve kablodaki veri kıvılcımı.
RENK_ISIK = "#6CCB5F"

#: Kolun omuzdaki ve bilekteki yarı kalınlığı. Uca doğru inceliyor;
#: sabit kalınlıkta bir kol boru gibi duruyor.
#: 4.2 ve 3.4 denendi: kol gövdeyle aynı renkte ve kalın olunca ikisi
#: tek bir amip oluyor, silüet okunmuyor. İnce kol hem bağlı kalıyor hem
#: kol olduğu görülüyor.
OMUZ_KALIN, BILEK_KALIN = 2.8, 2.0

#: Elin yarıçapı. El gövdenin küçültülmüş silüeti — ayrı bir daire
#: çizmek maskotu yapıştırılmış parçalar gibi gösterirdi.
EL_R = 4.4


def _egri(p0, p1, p2, u):
    """İkinci dereceden Bézier üstünde nokta ve teğet."""
    x = (1 - u) ** 2 * p0[0] + 2 * (1 - u) * u * p1[0] + u * u * p2[0]
    y = (1 - u) ** 2 * p0[1] + 2 * (1 - u) * u * p1[1] + u * u * p2[1]
    tx = 2 * (1 - u) * (p1[0] - p0[0]) + 2 * u * (p2[0] - p1[0])
    ty = 2 * (1 - u) * (p1[1] - p0[1]) + 2 * u * (p2[1] - p1[1])
    return (x, y), (tx, ty)


def _yol(noktalar) -> str:
    bas = noktalar[0]
    kalan = " ".join(f"L{x:.2f} {y:.2f}" for x, y in noktalar[1:])
    return f"M{bas[0]:.2f} {bas[1]:.2f} {kalan} Z"


def _serit(p0, p2, bas_kalin, son_kalin, egim=0.5, adet=18) -> str:
    """Eğri boyunca kalınlığı değişen dolu bir şerit.

    Kalem yerine dolu çokgen: maskotun bütün dili kontursuz dolu
    şekiller ve değişken kalınlık ancak böyle oluyor.
    """
    p1 = (p0[0] + (p2[0] - p0[0]) * egim, p0[1] + (p2[1] - p0[1]) * 0.85)
    sol, sag = [], []
    for i in range(adet + 1):
        u = i / adet
        (x, y), (tx, ty) = _egri(p0, p1, p2, u)
        boy = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / boy, tx / boy
        k = bas_kalin + (son_kalin - bas_kalin) * u
        sol.append((x + nx * k, y + ny * k))
        sag.append((x - nx * k, y - ny * k))
    return _yol(sol + sag[::-1])


def _duz_serit(p0, p1, p2, bas_kalin, son_kalin, adet=20) -> str:
    """Kontrol noktası verilen şerit — kablo için."""
    sol, sag = [], []
    for i in range(adet + 1):
        u = i / adet
        (x, y), (tx, ty) = _egri(p0, p1, p2, u)
        boy = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / boy, tx / boy
        k = bas_kalin + (son_kalin - bas_kalin) * u
        sol.append((x + nx * k, y + ny * k))
        sag.append((x - nx * k, y - ny * k))
    return _yol(sol + sag[::-1])


def _kol(omuz, el, dirsek=0.5) -> str:
    return _serit(omuz, el, OMUZ_KALIN, BILEK_KALIN, dirsek)


_TABAN = None


def _el(merkez, r=EL_R) -> str:
    global _TABAN
    if _TABAN is None:
        _TABAN = taban_noktalari(48)
    cx, cy = merkez
    k = r / 39.0
    return _yol([(cx + (x - 48.0) * k, cy + (y - 48.0) * k) for x, y in _TABAN])


def _kutu(id_, x, y, w, h, r, renk, ek="") -> str:
    return (f'<rect id="{id_}" x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" '
            f'height="{h:.2f}" rx="{r:.2f}" fill="{renk}"{ek}/>')


def _isaret(id_, x, y) -> str:
    """Çizilmeyen konum işareti. Uygulama koordinatı buradan okuyor."""
    return (f'<rect id="{id_}" x="{x - 0.5:.2f}" y="{y - 0.5:.2f}" '
            f'width="1" height="1" fill="none"/>')


def _yuva(x, y, en) -> str:
    return (f'<rect id="yuva" x="{x:.2f}" y="{y:.2f}" width="{en:.2f}" '
            f'height="{en:.2f}" fill="none"/>')


# --- sahneler --------------------------------------------------------


def mercek():
    """Büyüteci **gözünde** tutuyor.

    Cam gözün üstünde; maskot ona bakmıyor, onun **içinden** bakıyor.
    Camın içi tam oyulmuyor — altında göz var ve dolu bir oyuk onu
    silerdi. Yarı saydam bir daire hem cam olduğunu söylüyor hem gözü
    bırakıyor.
    """
    # Camın yeri hesaplandı, uydurulmadı: yuva (2, 4, 46) ve yakın göz
    # yüz uzayında (59.0, 37.5), profil kayması +16 ile (75.0, 37.5).
    # 46/96 ölçeğinde sahnede (37.9, 22.0) ediyor.
    cam = (38.0, 22.0)
    # Sap camın hemen altında bitiyor ve el orada. Uç 56'daydı: el
    # gövdeden 25 birim uzağa düşüyor ve kol geriliyordu. Bir merceği
    # kolunu uzatarak değil, sapından tutarsın.
    sap_ucu = (51.0, 39.0)
    el = (47.0, 34.0)
    omuz = (30.0, 32.0)
    return [
        ("--yuz--", None),
        ("sap", f'<path id="sap" d="{_serit(cam, sap_ucu, 3.2, 2.4, 0.5)}" '
                f'fill="{RENK_GOVDE}"/>'),
        # Çerçeve dolu daire değil **halka**: dolu olduğunda camın
        # altındaki gözü siliyordu ve maskot merceğin içinden bakmıyor,
        # arkasına saklanıyor gibi duruyordu.
        ("cam-halka", f'<circle id="cam-halka" cx="{cam[0]}" cy="{cam[1]}" '
                      f'r="12" fill="none" stroke="{RENK_GOVDE}" '
                      f'stroke-width="4"/>'),
        ("cam", f'<circle id="cam" cx="{cam[0]}" cy="{cam[1]}" r="10" '
                f'fill="{RENK_GOVDE}" opacity="0.16"/>'),
        ("parilti", f'<circle id="parilti" cx="{cam[0] - 4.5:.1f}" '
                    f'cy="{cam[1] - 4.5:.1f}" r="2.8" fill="{RENK_GOVDE}" '
                    f'opacity="0.7"/>'),
        ("kol-yakin", f'<path id="kol-yakin" d="{_kol(omuz, el, 0.3)}" '
                      f'fill="{RENK_TEN}"/>'),
        ("el-yakin", f'<path id="el-yakin" d="{_el(el)}" fill="{RENK_TEN}"/>'),
        ("yuva", _yuva(2.0, 4.0, 46.0)),
    ], True


def laptop():
    """Dizüstü **ona dönük**, iki eli klavyede.

    Ekran maskota bakıyor, yani bize arkasını dönüyor. İçeriğini bize
    göstermiyor ve göstermemeli: ne yazdığı onun işi, bizim gördüğümüz
    şey çalıştığı.
    """
    # Dizüstü gövdenin **önünde**, uzağında değil. 46..90 idi ve eller
    # gövdeden 30 birim ötede kalıyordu: kollar uzayıp çubuğa dönüyordu.
    # Yazan biri bilgisayarı kucağına çeker.
    taban_sol, taban_sag, taban_y = 32.0, 78.0, 44.0
    # Menteşe sağ uçta ve ekranın tepesi **sola**, maskota doğru
    # yatıyor. Önceki hâlde sağa yatıyordu: ekran bize dönüktü ve
    # maskot arkasına bakıyordu.
    ekran = [(76.0, 44.5), (52.0, 19.0), (58.0, 15.0), (81.0, 41.0)]
    eller = [(40.0, 41.0), (51.0, 41.0)]
    omuzlar = [(28.0, 28.0), (30.0, 34.0)]
    return [
        ("kol-uzak", f'<path id="kol-uzak" d="{_kol(omuzlar[0], eller[0], 0.6)}" '
                     f'fill="{RENK_UZAK}"/>'),
        ("el-uzak", f'<path id="el-uzak" d="{_el(eller[0])}" '
                    f'fill="{RENK_UZAK}"/>'),
        ("--yuz--", None),
        ("ekran", f'<path id="ekran" d="{_yol(ekran)}" fill="{RENK_GOVDE}"/>'),
        ("taban", f'<path id="taban" d="{_yol([(taban_sol, taban_y), (taban_sag, taban_y), (taban_sag - 3, taban_y + 5), (taban_sol + 2, taban_y + 5)])}" '
                  f'fill="{RENK_GOVDE}"/>'),
        ("tus-1", _kutu("tus-1", 38, taban_y + 1.5, 9, 1.8, 0.9, RENK_OYUK)),
        ("tus-2", _kutu("tus-2", 50, taban_y + 1.5, 13, 1.8, 0.9, RENK_OYUK)),
        ("kol-yakin", f'<path id="kol-yakin" d="{_kol(omuzlar[1], eller[1], 0.6)}" '
                      f'fill="{RENK_TEN}"/>'),
        ("el-yakin", f'<path id="el-yakin" d="{_el(eller[1])}" '
                     f'fill="{RENK_TEN}"/>'),
        ("yuva", _yuva(0.0, 6.0, 44.0)),
    ], True


def terminal():
    """Bize dönük, eli yok, gözü terminale bakıyor.

    Berkay'ın tarifi: "eli olmasın, bize dönük olcak". El çizmemek burada
    eksiklik değil tercih — klavyede eli görünmeyen biri yine de yazıyor
    demektir ve bunu anlatan şey bakış.
    """
    px, py, pen, pboy = 27.0, 38.0, 42.0, 22.0
    return [
        ("--yuz--", None),
        ("pencere", _kutu("pencere", px, py, pen, pboy, 4, RENK_GOVDE)),
        ("nokta-1", _kutu("nokta-1", px + 4.5, py + 4, 3, 3, 1.5, RENK_OYUK,
                          ' opacity="0.5"')),
        ("nokta-2", _kutu("nokta-2", px + 10, py + 4, 3, 3, 1.5, RENK_OYUK,
                          ' opacity="0.5"')),
        ("istem", f'<path id="istem" d="M{px + 6} {py + 11.5} '
                  f'L{px + 10} {py + 14.8} L{px + 6} {py + 18}" fill="none" '
                  f'stroke="{RENK_OYUK}" stroke-width="2.6" '
                  f'stroke-linecap="round" stroke-linejoin="round"/>'),
        ("imlec", _kutu("imlec", px + 15, py + 13.5, 12, 2.6, 1.3, RENK_OYUK)),
        # Yuva sahnenin dışına taşamaz: taşarsa yüzün üstü kırpılıyor.
        # -2'ye çekmiştim ve bir test yakaladı.
        ("yuva", _yuva(27.0, 0.0, 42.0)),
    ], False


def sayfa():
    """Kalemle yazıyor; sayfa bize arkasını dönük.

    "Bize bir şey göstermesin" — sayfanın yüzü maskota bakıyor, biz
    arkasını görüyoruz. Satır çizmiyoruz: arkadan bakılan bir kâğıtta
    satır görünmez, göstermek sayfayı camdan yapmak olurdu.
    """
    # Sayfa küçüldü ve gövdeye yanaştı. 54..92 arasında koca bir levha
    # olarak duruyordu: sahnenin yarısı kâğıttı ve el ona yetişmek için
    # geriliyordu.
    kagit = [(38.0, 46.0), (42.0, 20.0), (70.0, 23.0), (66.0, 49.0)]
    sirt = [(38.0, 46.0), (42.0, 20.0), (45.0, 20.3), (41.0, 46.3)]
    kalem_ust, kalem_uc = (62.0, 15.0), (52.0, 33.0)
    el = (58.0, 20.0)
    omuz = (32.0, 32.0)
    return [
        # Kol sayfanın **arkasında**, el ve kalem önünde. Kol önde
        # olduğunda sayfanın üstünden geçip kompozisyonu karıştırıyordu:
        # neyin kâğıt neyin kol olduğu okunmuyordu.
        ("kol-yakin", f'<path id="kol-yakin" d="{_kol(omuz, el, 0.5)}" '
                      f'fill="{RENK_TEN}"/>'),
        ("--yuz--", None),
        ("kagit", f'<path id="kagit" d="{_yol(kagit)}" fill="{RENK_GOVDE}"/>'),
        ("sirt", f'<path id="sirt" d="{_yol(sirt)}" fill="{RENK_OYUK}" '
                 f'opacity="0.2"/>'),
        ("kalem", f'<path id="kalem" d="'
                  f'{_serit(kalem_ust, kalem_uc, 2.6, 0.6, 0.5)}" '
                  f'fill="{RENK_UZAK}"/>'),
        ("el-yakin", f'<path id="el-yakin" d="{_el(el, 4.0)}" '
                     f'fill="{RENK_TEN}"/>'),
        ("yuva", _yuva(2.0, 4.0, 44.0)),
    ], True


def sunucu():
    """Sarhoş bakış, kablo, yanıp sönen yeşil ışık, koşan veri.

    Kablonun kontrol noktaları `kablo-p0/p1/p2` olarak dosyada duruyor ve
    kıvılcımın yolunu uygulama onlardan hesaplıyor. Eğrinin denklemini
    iki yere yazmak, bir gün ayrı düşmelerinin garantisiydi.
    """
    raf_x, raf_en = 62.0, 30.0
    p0, p1, p2 = (34.0, 40.0), (50.0, 58.0), (raf_x + 1.0, 34.0)
    return [
        ("kablo", f'<path id="kablo" d="{_duz_serit(p0, p1, p2, 1.9, 1.9)}" '
                  f'fill="{RENK_TEN}" opacity="0.8"/>'),
        ("--yuz--", None),
        ("raf-ust", _kutu("raf-ust", raf_x, 10, raf_en, 13, 3.5, RENK_GOVDE)),
        ("yuva-ust", _kutu("yuva-ust", raf_x + 4, 14.7, 11, 2.6, 1.3,
                           RENK_OYUK)),
        ("isik-ust", f'<circle id="isik-ust" cx="{raf_x + raf_en - 6:.1f}" '
                     f'cy="16" r="2.3" fill="{RENK_ISIK}"/>'),
        ("raf-alt", _kutu("raf-alt", raf_x, 27, raf_en, 13, 3.5, RENK_GOVDE)),
        ("yuva-alt", _kutu("yuva-alt", raf_x + 4, 31.7, 11, 2.6, 1.3,
                           RENK_OYUK)),
        ("isik-alt", f'<circle id="isik-alt" cx="{raf_x + raf_en - 6:.1f}" '
                     f'cy="33" r="2.3" fill="{RENK_ISIK}"/>'),
        ("kivilcim", f'<circle id="kivilcim" cx="{p0[0]:.1f}" '
                     f'cy="{p0[1]:.1f}" r="2.6" fill="{RENK_ISIK}"/>'),
        ("kablo-p0", _isaret("kablo-p0", *p0)),
        ("kablo-p1", _isaret("kablo-p1", *p1)),
        ("kablo-p2", _isaret("kablo-p2", *p2)),
        ("yuva", _yuva(0.0, 6.0, 42.0)),
    ], False


SAHNELER = {
    "mercek": mercek,
    "laptop": laptop,
    "terminal": terminal,
    "sayfa": sayfa,
    "sunucu": sunucu,
}

#: Çizilmeyen kimlikler: yuva ve kablonun kontrol noktaları.
GIZLI = ("yuva", "kablo-p0", "kablo-p1", "kablo-p2")


def sahne(ad: str) -> tuple[str, list[str], bool]:
    """SVG metni, çizim sırası ve profil bayrağı."""
    parcalar, profil = SAHNELER[ad]()
    ic = "\n  ".join(m for _, m in parcalar if m is not None)
    metin = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {VB_EN:.0f} {VB_BOY:.0f}" '
        f'width="{VB_EN:.0f}" height="{VB_BOY:.0f}">\n'
        f"  <!-- Üreten: scripts/sahne_svg.py — elle düzenleme, betiği düzenle. -->\n"
        f"  {ic}\n</svg>\n"
    )
    sira = [pid for pid, _ in parcalar if pid not in GIZLI]
    return metin, sira, profil


def main() -> int:
    HEDEF.mkdir(parents=True, exist_ok=True)
    for ad in SAHNELER:
        metin, sira, profil = sahne(ad)
        (HEDEF / f"sahne-{ad}.svg").write_text(metin, encoding="utf-8")
        print(f"  sahne-{ad} ({'yandan' if profil else 'önden'}): "
              + " ".join(sira))
    print(f"{len(SAHNELER)} sahne -> {HEDEF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
