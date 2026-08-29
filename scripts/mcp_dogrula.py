"""Gerçek bir MCP sunucusuna bağlanıp ölçer.

Birim testler ağa ve `npx`e dokunmuyor; bu betik dokunuyor. Ölçtüğü
şeyler: bağlanma süresi, kaç araç geldiği, bir çağrının ne kadar
sürdüğü, güvenlik taramasının o sunucuda ne dediği ve kapanışta süreç
kalıp kalmadığı.

    .venv/Scripts/python.exe scripts/mcp_dogrula.py
    .venv/Scripts/python.exe scripts/mcp_dogrula.py playwright

Varsayılan sunucu `@modelcontextprotocol/server-everything`: protokolün
kendi örnek sunucusu, tarayıcı indirmiyor ve `echo` gibi zararsız
araçları var. Ölçüm burada yapılan iş hakkında değil, **borunun
çalıştığı** hakkında.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.mcp import ayar as A  # noqa: E402
from backend.mcp.istemci import McpYonetici  # noqa: E402

SUNUCULAR = {
    "everything": ("npx", ["-y", "@modelcontextprotocol/server-everything"]),
    "playwright": ("npx", ["-y", "@playwright/mcp@latest"]),
    "fetch": ("npx", ["-y", "mcp-server-fetch"]),
}

#: Bağlanmayı bu kadar bekliyoruz. `npx` ilk çalıştırmada paket
#: indiriyor ve bu dakikalar sürebiliyor.
BEKLEME = 180.0


def main() -> int:
    ad = sys.argv[1] if len(sys.argv) > 1 else "everything"
    if ad not in SUNUCULAR:
        print(f"bilinmeyen sunucu: {ad}. Seçenekler: "
              f"{', '.join(SUNUCULAR)}")
        return 2
    komut, argumanlar = SUNUCULAR[ad]

    # Gerçek yapılandırmaya dokunmuyoruz: doğrulama betiği kimsenin
    # ayarını değiştirmemeli.
    yol = Path(tempfile.mkdtemp()) / "mcp.json"
    A.yaz([A.Sunucu(ad=ad, komut=komut, argumanlar=argumanlar, acik=True)],
          yol)

    yonetici = McpYonetici(yol)
    yonetici.basla()

    basla = time.perf_counter()
    while time.perf_counter() - basla < BEKLEME:
        durumlar = yonetici.durumlar()
        if durumlar and durumlar[0].durum in {"hazir", "hata"}:
            break
        time.sleep(0.5)
    gecen = time.perf_counter() - basla
    baglanti = yonetici.durumlar()[0]

    print(f"sunucu     : {ad} ({komut} {' '.join(argumanlar)})")
    print(f"durum      : {baglanti.durum}  ({gecen:.1f} s)")
    if not baglanti.hazir:
        print(f"hata       : {baglanti.hata}")
        yonetici.durdur()
        return 1

    print(f"araç       : {len(baglanti.araclar)}")
    print(f"parmak izi : {baglanti.izler}")
    for tanim in baglanti.araclar[:8]:
        aciklama = (tanim["description"] or "").replace("\n", " ")[:64]
        print(f"  {tanim['name']:<48} {aciklama}")
    if len(baglanti.araclar) > 8:
        print(f"  … {len(baglanti.araclar) - 8} tane daha")

    if baglanti.uyarilar:
        print("\nGÜVENLİK UYARILARI")
        for arac, uyarilar in baglanti.uyarilar.items():
            print(f"  {arac}: {'; '.join(uyarilar)}")
    else:
        print("\ngüvenlik   : tanımlarda şüpheli kalıp yok")

    # Zararsız bir çağrı: gerçekten uçtan uca çalıştığını gösteren şey.
    deneme = next(
        (t["name"] for t in baglanti.araclar if t["name"].endswith("echo")),
        None,
    )
    if deneme:
        basla = time.perf_counter()
        icerik, hatali = yonetici.cagir(deneme, {"message": "yan masa"})
        print(f"\n{deneme}: hata={hatali} "
              f"({(time.perf_counter() - basla) * 1000:.0f} ms)\n  {icerik!r}")

    # Görsel yolu ayrıca ölçülüyor: Playwright'ın ekran görüntüsü aracı
    # görsel döndürüyor ve onu metne çevirmek aracın bütün anlamını
    # ortadan kaldırırdı.
    gorsel = next(
        (t["name"] for t in baglanti.araclar if "image" in t["name"]), None,
    )
    if gorsel:
        icerik, hatali = yonetici.cagir(gorsel, {})
        turler = ([b.get("type") for b in icerik]
                  if isinstance(icerik, list) else ["text"])
        print(f"{gorsel}: hata={hatali} blok türleri={turler}")

    yonetici.durdur()
    print("\nkapatıldı. Arkada süreç kalmadığını görmek için:")
    print('  Get-CimInstance Win32_Process -Filter "Name=\'node.exe\'"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
