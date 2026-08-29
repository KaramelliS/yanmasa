"""MCP istemcisi — dış sunucuların araçlarını ajana bağlamak.

Bir MCP sunucusu ya yerel bir süreç (stdio) ya da bir adres (HTTP). İkisi
de araç listesi veriyor ve o araçlar modelin araç listesine ekleniyor;
çağrıldıklarında `Dispatcher` üzerinden buraya dönüyorlar. Yani MCP
araçları yeteneklerle aynı yolu izliyor: onay kapısı, denetim kaydı, kuru
koşu ve akış kaydı hepsi bedavaya geliyor.

## Neden ayrı bir thread

`mcp` paketi asyncio üstüne kurulu; ajan döngüsü senkron ve kendi
thread'inde dönüyor. Ajanın içine bir olay döngüsü sokmak yerine burada
kendi thread'inde dönen tek bir döngü var ve senkron taraf
`run_coroutine_threadsafe` ile ona sesleniyor. Tek döngü olması şart:
oturum nesnesi yaratıldığı döngüye ait ve başka bir döngüden çağrılamaz.

Her sunucu kendi görevinde yaşıyor. `stdio_client` ve `ClientSession`
birer async bağlam yöneticisi; bağlantıyı canlı tutmanın yolu görevin
kapanma olayını beklemesi. Görev bittiğinde iki bağlam da düzgün
kapanıyor, yani süreç arkada kalmıyor.

## Zaman aşımı her yerde

Bir MCP sunucusu `npx` ile paket indirebiliyor ve ilk açılış dakikalar
sürebiliyor; buna izin var. İzin olmayan şey **süresiz** beklemek:
yanıt vermeyen bir sunucu ajanı kilitlerse, kilitlenen şey bütün
uygulama olur.

## Hiçbir sunucu kendiliğinden açılmıyor

`ayar.py` varsayılanı kapalı tutuyor. Burada da yalnızca `acik` olanlar
bağlanıyor: yapılandırmaya bir sunucu yazmak, onu çalıştırmaya izin
vermek değil.
"""

from __future__ import annotations

import asyncio
import base64
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import ayar as ayar_mod
from . import guvenlik
from .ayar import AyarHatasi, Sunucu

#: Araç adı öneki. Ajanın kendi araçlarıyla çakışmayı imkânsız kılıyor
#: ve hangi aracın nereden geldiğini kayıtta okunur yapıyor.
ONEK = "mcp"

#: Anthropic araç adı sınırı.
AD_SINIRI = 128

_TEMIZ = re.compile(r"[^A-Za-z0-9_-]")

#: Bağlanma ve çağrı için üst sınırlar, saniye. Bağlanma uzun: `npx`
#: ilk çalıştırmada paket indiriyor.
BAGLANMA_SURESI = 120.0
CAGRI_SURESI = 120.0

#: Bir aracın sonucundan modele giden en uzun metin. MCP sunucuları
#: bütün bir sayfayı döndürebiliyor ve bağlamı tek çağrıda doldurmak
#: turun geri kalanını yiyor.
SONUC_SINIRI = 20_000


class McpHatasi(RuntimeError):
    pass


def arac_adi(sunucu: str, arac: str) -> str:
    """`mcp__playwright__browser_click` gibi."""
    ham = f"{ONEK}__{_TEMIZ.sub('_', sunucu)}__{_TEMIZ.sub('_', arac)}"
    return ham[:AD_SINIRI]


@dataclass
class Baglanti:
    """Bir sunucunun o anki hâli."""

    sunucu: Sunucu
    durum: str = "kapali"  # kapali | baglaniyor | hazir | hata
    hata: str = ""
    #: Modele giden araç tanımları (adları önekli).
    araclar: list[dict[str, Any]] = field(default_factory=list)
    #: Araç adı -> güvenlik uyarıları.
    uyarilar: dict[str, list[str]] = field(default_factory=dict)
    #: Araç kümesinin parmak izi; değişmesi "halı çekme" demek.
    izler: str = ""
    #: Önceki parmak izi. Doluysa tanımlar bağlantı sırasında değişti.
    onceki_izler: str = ""

    @property
    def hazir(self) -> bool:
        return self.durum == "hazir"

    @property
    def degisti(self) -> bool:
        return bool(self.onceki_izler and self.onceki_izler != self.izler)


class _Dongu:
    """Kendi thread'inde dönen tek asyncio döngüsü."""

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._hazir = threading.Event()

    def basla(self) -> None:
        if self._thread is not None:
            return
        self._hazir.clear()
        self._thread = threading.Thread(target=self._sur, daemon=True,
                                        name="mcp-dongu")
        self._thread.start()
        self._hazir.wait(timeout=5.0)

    def _sur(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self._hazir.set()
        self.loop.run_forever()

    def durdur(self) -> None:
        if self.loop is None or self._thread is None:
            return
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=3.0)
        self._thread = None
        self.loop = None

    def calistir(self, coro, timeout: float):
        """Coroutine'i döngüde çalıştırır, sonucu bekler."""
        if self.loop is None:
            raise McpHatasi("the MCP loop is not running")
        gelecek = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return gelecek.result(timeout=timeout)

    def gonder(self, coro) -> None:
        """Sonucu beklenmeyen görev. Bağlantılar böyle kuruluyor."""
        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(coro, self.loop)


def _metne(icerik: Any) -> tuple[Any, bool]:
    """MCP sonucunu modelin anlayacağı içeriğe çevirir.

    Görseller **korunuyor**: Playwright'ın ekran görüntüsü aracı bir
    görsel döndürüyor ve onu metne çevirmek, aracın bütün anlamını
    ortadan kaldırırdı. Ajanın kendi `screenshot` sonucuyla aynı blok
    biçimi kullanılıyor.
    """
    if isinstance(icerik, str):
        return icerik[:SONUC_SINIRI], False
    bloklar: list[dict[str, Any]] = []
    metinler: list[str] = []
    for parca in icerik or []:
        tur = getattr(parca, "type", "")
        if tur == "text":
            metinler.append(str(getattr(parca, "text", "")))
        elif tur == "image":
            veri = getattr(parca, "data", "")
            if veri:
                bloklar.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": getattr(parca, "mime_type", "image/png"),
                        "data": veri if isinstance(veri, str)
                        else base64.standard_b64encode(veri).decode("ascii"),
                    },
                })
        else:
            metinler.append(str(parca))
    metin = "\n".join(m for m in metinler if m)[:SONUC_SINIRI]
    if bloklar:
        if metin:
            bloklar.insert(0, {"type": "text", "text": metin})
        return bloklar, False
    return metin or "OK", False


class McpYonetici:
    """Açık sunucuları bağlar, araçlarını verir, çağrıları iletir."""

    def __init__(self, yol: Path | None = None) -> None:
        self._yol = yol
        self._dongu = _Dongu()
        self._kilit = threading.Lock()
        self._baglantilar: dict[str, Baglanti] = {}
        self._oturumlar: dict[str, Any] = {}
        self._durdur: dict[str, asyncio.Event] = {}
        #: Önekli ad -> (sunucu adı, sunucudaki gerçek ad).
        self._eslesme: dict[str, tuple[str, str]] = {}
        self._calisiyor = False

    # --- yaşam döngüsü ----------------------------------------------------

    def basla(self) -> None:
        """Açık sunucuları arka planda bağlar. **Beklemiyor** — bir
        `npx` indirmesi dakikalar sürebilir ve o süre boyunca uygulamanın
        açılmaması kabul edilemez."""
        if self._calisiyor:
            return
        self._calisiyor = True
        # Olay döngüsü **tembel**: MCP kullanmayan bir kurulumda boşta
        # duran bir thread taşımanın anlamı yok ve bu kurulumların
        # çoğunluğu.
        self.yenile()

    def durdur(self) -> None:
        if not self._calisiyor:
            return
        for ad in list(self._durdur):
            self._kapat(ad)
        self._dongu.durdur()
        self._calisiyor = False

    def yenile(self) -> None:
        """Ayarı yeniden okur: açılanları bağlar, kapananları kapatır."""
        if not self._calisiyor:
            return
        istenen = {s.ad: s for s in ayar_mod.oku(self._yol)}
        if any(s.acik for s in istenen.values()):
            self._dongu.basla()
        with self._kilit:
            var_olan = dict(self._baglantilar)

        for ad in var_olan:
            sunucu = istenen.get(ad)
            if sunucu is None or not sunucu.acik:
                self._kapat(ad)

        for ad, sunucu in istenen.items():
            if not sunucu.acik:
                with self._kilit:
                    if ad not in self._baglantilar:
                        self._baglantilar[ad] = Baglanti(sunucu=sunucu)
                continue
            with self._kilit:
                mevcut = self._baglantilar.get(ad)
                if mevcut is not None and mevcut.durum in {"baglaniyor",
                                                           "hazir"}:
                    continue
                onceki = mevcut.izler if mevcut is not None else ""
                self._baglantilar[ad] = Baglanti(
                    sunucu=sunucu, durum="baglaniyor", onceki_izler=onceki,
                )
            self._dongu.gonder(self._sur(sunucu))

    def _kapat(self, ad: str) -> None:
        olay = self._durdur.pop(ad, None)
        if olay is not None and self._dongu.loop is not None:
            self._dongu.loop.call_soon_threadsafe(olay.set)
        with self._kilit:
            self._oturumlar.pop(ad, None)
            baglanti = self._baglantilar.get(ad)
            if baglanti is not None:
                baglanti.durum = "kapali"
                baglanti.araclar = []
            self._eslesme = {
                k: v for k, v in self._eslesme.items() if v[0] != ad
            }

    # --- bağlantı ---------------------------------------------------------

    async def _sur(self, sunucu: Sunucu) -> None:
        """Bir sunucuyu bağlar ve kapatılana kadar canlı tutar."""
        ad = sunucu.ad
        olay = asyncio.Event()
        self._durdur[ad] = olay
        try:
            async with self._tasima(sunucu) as (oku, yaz):
                from mcp import ClientSession

                async with ClientSession(oku, yaz) as oturum:
                    await asyncio.wait_for(oturum.initialize(),
                                           BAGLANMA_SURESI)
                    liste = await asyncio.wait_for(oturum.list_tools(),
                                                   BAGLANMA_SURESI)
                    self._araclari_al(sunucu, oturum, liste)
                    await olay.wait()
        except asyncio.TimeoutError:
            self._dustu(ad, f"{ad} did not answer in "
                            f"{int(BAGLANMA_SURESI)} seconds")
        except AyarHatasi as hata:
            self._dustu(ad, str(hata))
        except Exception as hata:  # sunucu çöktü, komut yok, protokol hatası
            self._dustu(ad, f"{type(hata).__name__}: {hata}")
        finally:
            self._durdur.pop(ad, None)

    def _tasima(self, sunucu: Sunucu):
        if sunucu.http:
            from mcp.client.streamable_http import streamable_http_client

            return streamable_http_client(sunucu.adres)

        import os

        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client

        # Sunucunun ortamı: sürecin ortamı + tanımdakiler. Boş bir
        # ortamla başlatmak `npx`'i PATH'siz bırakıyor ve hiçbir sunucu
        # açılmıyor.
        ortam = dict(os.environ)
        ortam.update(sunucu.cozulmus_ortam())
        return stdio_client(StdioServerParameters(
            command=sunucu.komut,
            args=list(sunucu.argumanlar),
            env=ortam,
            cwd=sunucu.calisma_dizini or None,
        ))

    def _araclari_al(self, sunucu: Sunucu, oturum, liste) -> None:
        araclar: list[dict[str, Any]] = []
        uyarilar: dict[str, list[str]] = {}
        eslesme: dict[str, tuple[str, str]] = {}
        ham: list[dict[str, Any]] = []

        for arac in getattr(liste, "tools", []) or []:
            gercek = str(getattr(arac, "name", "") or "")
            if not gercek:
                continue
            aciklama = str(getattr(arac, "description", "") or "")
            sema = getattr(arac, "input_schema", None) or {
                "type": "object", "properties": {},
            }
            onekli = arac_adi(sunucu.ad, gercek)
            araclar.append({
                "name": onekli,
                "description": aciklama[:2000],
                "input_schema": sema,
            })
            ham.append({"name": gercek, "description": aciklama,
                        "input_schema": sema})
            bulgu = guvenlik.tanim_uyarilari(aciklama)
            if bulgu:
                uyarilar[onekli] = bulgu
            eslesme[onekli] = (sunucu.ad, gercek)

        with self._kilit:
            self._oturumlar[sunucu.ad] = oturum
            baglanti = self._baglantilar.get(sunucu.ad) or Baglanti(
                sunucu=sunucu
            )
            baglanti.sunucu = sunucu
            baglanti.durum = "hazir"
            baglanti.hata = ""
            baglanti.araclar = araclar
            baglanti.uyarilar = uyarilar
            baglanti.izler = guvenlik.parmak_izi(ham)
            self._baglantilar[sunucu.ad] = baglanti
            self._eslesme = {
                k: v for k, v in self._eslesme.items()
                if v[0] != sunucu.ad
            }
            self._eslesme.update(eslesme)

    def _dustu(self, ad: str, sebep: str) -> None:
        with self._kilit:
            baglanti = self._baglantilar.get(ad)
            if baglanti is not None:
                baglanti.durum = "hata"
                baglanti.hata = sebep
                baglanti.araclar = []
            self._oturumlar.pop(ad, None)
            self._eslesme = {
                k: v for k, v in self._eslesme.items() if v[0] != ad
            }

    # --- okuma ------------------------------------------------------------

    def tools(self) -> list[dict[str, Any]]:
        """Modele giden araç tanımları. Hazır olmayan sunucu boş veriyor."""
        with self._kilit:
            return [
                dict(arac)
                for baglanti in self._baglantilar.values()
                if baglanti.hazir
                for arac in baglanti.araclar
            ]

    def adlar(self) -> set[str]:
        with self._kilit:
            return set(self._eslesme)

    def bilir(self, arac: str) -> bool:
        with self._kilit:
            return arac in self._eslesme

    def durumlar(self) -> list[Baglanti]:
        with self._kilit:
            return sorted(self._baglantilar.values(),
                          key=lambda b: b.sunucu.ad)

    def uyarilar(self, arac: str) -> list[str]:
        with self._kilit:
            for baglanti in self._baglantilar.values():
                if arac in baglanti.uyarilar:
                    return list(baglanti.uyarilar[arac])
        return []

    def anlat(self, arac: str) -> str:
        """Onay ekranında görünen tanım."""
        with self._kilit:
            eslesme = self._eslesme.get(arac)
            if eslesme is None:
                return arac
            sunucu, gercek = eslesme
            for baglanti in self._baglantilar.values():
                if baglanti.sunucu.ad != sunucu:
                    continue
                for tanim in baglanti.araclar:
                    if tanim["name"] == arac:
                        return (f"{gercek} on the {sunucu} server — "
                                f"{tanim['description'][:200]}")
        return arac

    # --- çağrı ------------------------------------------------------------

    def cagir(self, arac: str, girdi: dict[str, Any]) -> tuple[Any, bool]:
        """Aracı çalıştırır. `(içerik, hata_mı)`."""
        with self._kilit:
            eslesme = self._eslesme.get(arac)
            oturum = self._oturumlar.get(eslesme[0]) if eslesme else None
        if eslesme is None or oturum is None:
            raise McpHatasi(
                f"{arac} is not available — its server is not connected."
            )
        _sunucu, gercek = eslesme
        try:
            sonuc = self._dongu.calistir(
                oturum.call_tool(gercek, dict(girdi),
                                 read_timeout_seconds=CAGRI_SURESI),
                timeout=CAGRI_SURESI + 10,
            )
        except TimeoutError:
            return (f"{arac} did not answer in "
                    f"{int(CAGRI_SURESI)} seconds."), True
        except Exception as hata:
            return f"{type(hata).__name__}: {hata}", True

        icerik, _ = _metne(getattr(sonuc, "content", None))
        return icerik, bool(getattr(sonuc, "is_error", False))
