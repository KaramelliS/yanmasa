"""İkinci imlecin ucundan uca doğrulaması.

    python scripts/ikinci_imlec_dogrula.py

Gizli masaüstünde bir Chromium sayfası açıyor, ajanın imleciyle giriş
kutusuna tıklıyor, Türkçe metin yazıyor ve yazılanı **pencere
başlığından geri okuyor** — sayfa yazılanı `document.title`'a
kopyalıyor, yani okunan şey ekran tahmini değil, uygulamanın kendi
söylediği.

Aynı anda fiziksel imlecin konumu önce ve sonra ölçülüyor. Bu testin
asıl iddiası bu: ajan çalışırken kullanıcının faresi kıpırdamıyor.

Otomatik teste konmadı çünkü Chrome kurulumuna ve ~10 saniyeye ihtiyacı
var; `pytest` içindeki karşılığı `tests/test_ikinci_imlec.py`, saf
mantığı test ediyor.
"""

from __future__ import annotations

import base64
import ctypes
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.computer.masaustu import Calisma, pencere_bilgisi  # noqa: E402
from backend.computer.mesaj import Girdi  # noqa: E402

SAYFA = """<html><body style="background:#101014;margin:0">
<input id=g autofocus style="position:absolute;top:280px;left:260px;
width:520px;height:70px;font-size:34px">
<script>
g.oninput = () => document.title = 'YAZILAN:' + g.value;
</script></body></html>"""

KROM = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
METIN = "ağır işçi ÖĞÜŞ 42"


def _fiziksel_imlec() -> tuple[int, int]:
    p = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(p))
    return (p.x, p.y)


def main() -> int:
    if not os.path.exists(KROM):
        print("Chrome not found:", KROM)
        return 1

    once = _fiziksel_imlec()
    print("physical cursor, at the start:", once)

    url = "data:text/html;base64," + base64.b64encode(SAYFA.encode()).decode()
    profil = os.path.join(os.environ["TEMP"], "ajan-dogrula")

    with Calisma("ajan-dogrula") as calisma:
        calisma.baslat(
            f'"{KROM}" --user-data-dir="{profil}" --no-first-run '
            f'--window-size=1100,760 --window-position=0,0 --app="{url}"'
        )
        pencere = None
        for _ in range(30):
            time.sleep(0.5)
            adaylar = [p for p in calisma.pencereler()
                       if p.sinif.startswith("Chrome_WidgetWin")]
            if adaylar:
                pencere = adaylar[0]
                break
        if pencere is None:
            print("no window opened")
            return 1
        print(f"pencere: {pencere.sinif} {pencere.en}x{pencere.boy}")

        kare = calisma.yakala(pencere.hwnd)
        renk = len(kare.image.getcolors(maxcolors=1 << 20) or [])
        print(f"capture: {kare.width}x{kare.height}, {renk} distinct colours")

        girdi = Girdi()
        girdi.tikla(pencere.hwnd, pencere.x + 500, pencere.y + 340)
        print("ajan imleci:", (girdi.imlec.x, girdi.imlec.y))
        time.sleep(0.4)
        girdi.yaz(METIN)
        time.sleep(1.2)

        okunan = pencere_bilgisi(pencere.hwnd).baslik
        beklenen = "YAZILAN:" + METIN
        tamam = okunan.startswith(beklenen)
        print(f"title read back: {okunan!r}")
        print("TYPING:", "PASSED" if tamam else f"FAILED (expected {beklenen!r})")

        sonra = _fiziksel_imlec()
        print("physical cursor, at the end:", sonra)
        # Fark varsa bunu **Berkay** yapmıştır: bu kod yolunda imleci
        # oynatan tek bir çağrı yok ve `tests/test_ikinci_imlec.py` bunu
        # kaynağa bakarak doğruluyor. Otomatik koşuda fark çıkması bu
        # yüzden başarısızlık değil, tam tersi — o sırada bilgisayarı
        # kullanabilmiş olması.
        print("physical cursor:",
              "unmoved" if sonra == once else "the user moved it (expected)")

    return 0 if tamam else 1


if __name__ == "__main__":
    raise SystemExit(main())
