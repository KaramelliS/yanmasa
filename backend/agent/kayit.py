"""Denetim kaydı — ajanın ne yaptığının diskteki karşılığı.

Ajan bir turda otuz araç çağırıp sonunda tek paragraf yazıyor. O paragraf
yanlışsa — ya da yapılmamış bir işi yapılmış gösteriyorsa — elde
karşılaştıracak hiçbir şey yoktu. Burası o karşılaştırma zemini.

Kaydın iki tüketicisi var ve ikisi de topluluğun sürekli şikâyet ettiği
bir kusura karşılık geliyor:

- **`rapor.py`** ajanın cümlesini bu kayıtla karşılaştırıyor. 20.574
  gerçek oturumluk analizde görünür çözümlerin %91.49'u kullanıcının elle
  düzeltmesini gerektiriyor ve oransal olarak **artan** kusurlardan biri
  ajanın yapmadığı işi yaptım demesi. Kayıt olmadan bunu yakalamanın yolu
  yok.
- **`tekrar_bul`** aynı işin üçüncü kez sorunsuz yapıldığını görüyor ve
  ajanın bir düğme önermesini tetikliyor. Bu daha önce sistem promptunda
  bir cümleydi — yani modelin hatırlamasına bırakılmıştı. Artık
  sayılıyor.

## Ne yazılmıyor

Girdilerin içeriği kısaltılıyor ve anahtar deseni taşıyan alanlar hiç
yazılmıyor. Kayıt `runs/` altında ve `runs/` `.gitignore`'da — ama bir
denetim kaydının kendisi sızıntı kaynağı olmamalı; dosya yollarını
biliyoruz, dosya içeriklerini tutmuyoruz.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import REPO_ROOT

#: Kayıtların yeri. `.gitignore` içinde.
DIZIN = REPO_ROOT / "runs"

#: Girdi alanlarının kayda giren en uzun hâli. Amaç neyin çağrıldığını
#: bilmek, ne yazıldığını arşivlemek değil.
ALAN_SINIRI = 200

#: Hiç yazılmayan alanlar: dosya gövdeleri ve yetenek kodu. Bunlar zaten
#: diskte duruyor ve kayda kopyalamak aynı veriyi ikinci kez saklamak
#: olurdu.
ATLANAN = frozenset({"code", "content", "contents", "files"})

#: Değeri anahtar gibi görünen alan asla yazılmıyor. Kapı kimlik bilgisi
#: yazmayı zaten engelliyor ama tek katmana güvenmiyoruz.
SIR_DESEN = re.compile(
    r"(sk-[A-Za-z0-9_-]{12,}|AIza[0-9A-Za-z_-]{20,}|ghp_[A-Za-z0-9]{20,}"
    r"|xi-api-key|BEGIN [A-Z ]*PRIVATE KEY)"
)

#: Bir işin "aynı iş" sayılması için gereken araç sayısı. Tek araçlık
#: turlar — bir ekran görüntüsü, bir dosya okuma — sürekli tekrarlanıyor
#: ve onları otomatikleştirmenin bir anlamı yok.
ASGARI_ADIM = 2

#: Kaç kez sorunsuz tekrarlanınca otomasyon önerilsin.
TEKRAR_ESIGI = 3


def _kisalt(deger: Any) -> Any:
    if isinstance(deger, str):
        if SIR_DESEN.search(deger):
            return "[gizlendi]"
        return deger if len(deger) <= ALAN_SINIRI else deger[:ALAN_SINIRI] + "…"
    if isinstance(deger, (int, float, bool)) or deger is None:
        return deger
    return _kisalt(str(deger))


def temiz_girdi(payload: dict[str, Any]) -> dict[str, Any]:
    """Araç girdisinin kayda giren hâli."""
    return {
        ad: _kisalt(deger)
        for ad, deger in payload.items()
        if ad not in ATLANAN
    }


@dataclass
class Tur:
    """Kayıt açısından bir tur: talimat, çağrılan araçlar, sonuç."""

    talimat: str
    baslangic: float
    araclar: list[str] = field(default_factory=list)
    basarili: list[str] = field(default_factory=list)
    hatali: list[str] = field(default_factory=list)

    @property
    def imza(self) -> str:
        """Turun "aynı iş" imzası: ardışık tekrarları sadeleşmiş araç dizisi.

        Talimat metni imzaya **girmiyor**. Aynı işi iki kez birebir aynı
        cümleyle istemiyorsun — "masaüstündeki csv'leri excele çevir" ile
        "şu csv'leri excele çevir" aynı iş. Yapılan işi araç dizisi
        anlatıyor, cümle değil.

        Ardışık tekrarlar sadeleşiyor: dört dosya yazmak ile beş dosya
        yazmak aynı iş, dosya sayısı değişince imza değişmemeli.
        """
        sade: list[str] = []
        for ad in self.basarili:
            if not sade or sade[-1] != ad:
                sade.append(ad)
        return ">".join(sade)


class Kayit:
    """JSONL denetim kaydı. Gün başına bir dosya.

    Yazma hataları yutuluyor: denetim kaydı bir kolaylık ve dolu bir disk
    yüzünden ajanın durması saçma olurdu. Ama sessizce yutulan hata da
    kabul edilemez, o yüzden ilk hata `son_hata`'ya yazılıyor ve arayüz
    isterse gösterebiliyor.
    """

    def __init__(self, dizin: Path | None = None) -> None:
        self.dizin = dizin or DIZIN
        self.son_hata: str | None = None
        self._kilit = threading.Lock()
        self._tur: Tur | None = None

    # -- yazma ------------------------------------------------------

    @property
    def dosya(self) -> Path:
        gun = time.strftime("%Y-%m-%d")
        return self.dizin / f"{gun}.jsonl"

    def _yaz(self, satir: dict[str, Any]) -> None:
        satir["t"] = time.time()
        try:
            self.dizin.mkdir(parents=True, exist_ok=True)
            with self._kilit, open(self.dosya, "a", encoding="utf-8") as f:
                f.write(json.dumps(satir, ensure_ascii=False) + "\n")
        except OSError as hata:
            if self.son_hata is None:
                self.son_hata = f"could not write the audit log: {hata}"

    def tur_basladi(self, talimat: str) -> None:
        self._tur = Tur(talimat=talimat, baslangic=time.time())
        self._yaz({"tur": "tur", "talimat": _kisalt(talimat)})

    def eylem(self, arac: str, girdi: dict[str, Any], hata: bool,
              ozet: str = "") -> None:
        if self._tur is not None:
            self._tur.araclar.append(arac)
            (self._tur.hatali if hata else self._tur.basarili).append(arac)
        self._yaz({
            "tur": "eylem", "arac": arac, "girdi": temiz_girdi(girdi),
            "hata": hata, "ozet": _kisalt(ozet),
        })

    def tur_araclari(self) -> set[str]:
        """Bu turda **başarıyla** çalışmış araçlar."""
        return set(self._tur.basarili) if self._tur else set()

    def tur_bitti(self, metin: str, desteksiz: list[str] | None = None) -> None:
        t = self._tur
        self._yaz({
            "tur": "bitti",
            "imza": t.imza if t else "",
            "adim": len(t.araclar) if t else 0,
            "hata": len(t.hatali) if t else 0,
            "sure": round(time.time() - t.baslangic, 2) if t else 0.0,
            "metin": _kisalt(metin),
            "desteksiz": desteksiz or [],
        })
        self._tur = None

    # -- okuma ------------------------------------------------------

    def satirlar(self, gun_sayisi: int = 14) -> list[dict[str, Any]]:
        """Son `gun_sayisi` günün kayıtları, eskiden yeniye."""
        if not self.dizin.is_dir():
            return []
        dosyalar = sorted(self.dizin.glob("*.jsonl"))[-gun_sayisi:]
        cikti: list[dict[str, Any]] = []
        for yol in dosyalar:
            try:
                metin = yol.read_text(encoding="utf-8")
            except OSError:
                continue
            for satir in metin.splitlines():
                if not satir.strip():
                    continue
                try:
                    cikti.append(json.loads(satir))
                except ValueError:
                    # Yarım yazılmış son satır: süreç kapanırken olur.
                    # Bir bozuk satır yüzünden bütün kaydı atmak, elde
                    # olan bilgiyi de kaybetmek olurdu.
                    continue
        return cikti


def tekrar_bul(satirlar: list[dict[str, Any]], esik: int = TEKRAR_ESIGI,
               asgari_adim: int = ASGARI_ADIM) -> list[tuple[str, int, str]]:
    """Sorunsuz tekrarlanan işler: (imza, kaç kez, örnek talimat).

    Yalnızca **hatasız** biten turlar sayılıyor. Üç kez denenip üç kez
    tökezlemiş bir işi otomatikleştirmek, tökezlemeyi otomatikleştirmek
    olurdu.
    """
    sayac: Counter[str] = Counter()
    ornek: dict[str, str] = {}
    son_talimat = ""
    for satir in satirlar:
        if satir.get("tur") == "tur":
            son_talimat = str(satir.get("talimat") or "")
        elif satir.get("tur") == "bitti":
            imza = str(satir.get("imza") or "")
            if not imza or satir.get("hata"):
                continue
            if imza.count(">") + 1 < asgari_adim:
                continue
            sayac[imza] += 1
            ornek.setdefault(imza, son_talimat)
    return [
        (imza, adet, ornek.get(imza, ""))
        for imza, adet in sayac.most_common()
        if adet >= esik
    ]


def oneri_notu(tekrarlar: list[tuple[str, int, str]]) -> str:
    """Tekrarlanan işleri ajana verilecek nota çevirir.

    Not, kullanıcının mesajının sonuna ekleniyor ve ajandan `button_write`
    ile düğme önermesini istiyor. Öneriyi ajanın kendi hatırlamasına
    bırakmak eskiden sistem promptunda bir cümleydi ve çalışmıyordu —
    model otuz adımlık bir turun sonunda "bunu üçüncü kez yapıyorum"
    demiyor. Şimdi sayan taraf kod.
    """
    if not tekrarlar:
        return ""
    imza, adet, talimat = tekrarlar[0]
    return (
        f"\n\n[You have completed this sequence ({imza}) {adet} times "
        f"without a problem. An example instruction: {talimat!r}. After you "
        f"finish this turn, propose a button for it with `button_write` — "
        f"keep the label short. If the user says no, do not insist and do "
        f"not raise it again.]"
    )


# --- koşuları derleme ---------------------------------------------------
#
# JSONL düz bir olay akışı: `tur`, ardından `eylem`ler, sonunda `bitti`.
# Arayüzün istediği şey ise koşu: bir talimat ve onun adımları. Derleme
# burada, arayüzde değil — kaydın biçimini bilen taraf burası ve aynı
# derlemeye rapor/analiz tarafının da ihtiyacı olacak.


@dataclass
class Adim:
    """Bir araç çağrısı."""

    arac: str
    girdi: dict[str, Any]
    hata: bool
    ozet: str
    t: float


@dataclass
class Kosu:
    """Bir talimat ve onun adımları."""

    talimat: str
    baslangic: float
    adimlar: list[Adim] = field(default_factory=list)
    metin: str = ""
    sure: float = 0.0
    desteksiz: list[str] = field(default_factory=list)
    #: `bitti` satırı hiç gelmedi: uygulama tur ortasında kapandı.
    yarim: bool = True

    @property
    def hata_sayisi(self) -> int:
        return sum(1 for a in self.adimlar if a.hata)

    @property
    def adim_sayisi(self) -> int:
        return len(self.adimlar)


def kosulari_derle(satirlar: list[dict[str, Any]]) -> list[Kosu]:
    """Olay akışını koşulara böler — **yeniden eskiye**.

    Üç bozuk durum kasten tolere ediliyor, çünkü üçü de gerçekten oluyor:

    - **Başlıksız eylem.** Kaydın ilk günü kesilmişse (`satirlar` son on
      dört günü veriyor) turun `tur` satırı okunmayan bir dosyada kalmış
      olabiliyor. O eylemler atılmıyor; talimatı bilinmeyen bir koşuya
      giriyor.
    - **Kapanmamış tur.** Uygulama tur ortasında kapanınca `bitti`
      yazılmıyor. Koşu `yarim` kalıyor ve arayüz bunu söylüyor —
      "0 adımda bitti" demek yalan olurdu.
    - **Bittisi olan ama turu olmayan.** Aynı kesilme, ters yönden.
    """
    kosular: list[Kosu] = []
    acik: Kosu | None = None

    def kapat() -> None:
        nonlocal acik
        if acik is not None:
            kosular.append(acik)
            acik = None

    for satir in satirlar:
        tur = satir.get("tur")
        if tur == "tur":
            kapat()
            acik = Kosu(
                talimat=str(satir.get("talimat") or ""),
                baslangic=float(satir.get("t") or 0.0),
            )
        elif tur == "eylem":
            if acik is None:
                acik = Kosu(talimat="", baslangic=float(satir.get("t") or 0.0))
            acik.adimlar.append(Adim(
                arac=str(satir.get("arac") or ""),
                girdi=dict(satir.get("girdi") or {}),
                hata=bool(satir.get("hata")),
                ozet=str(satir.get("ozet") or ""),
                t=float(satir.get("t") or 0.0),
            ))
        elif tur == "bitti":
            if acik is None:
                continue
            acik.metin = str(satir.get("metin") or "")
            acik.sure = float(satir.get("sure") or 0.0)
            acik.desteksiz = list(satir.get("desteksiz") or [])
            acik.yarim = False
            kapat()
    kapat()
    kosular.reverse()
    return kosular
