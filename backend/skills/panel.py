"""Yeteneğin ürettiği panel — ajanın arayüze eklediği özellik.

Bir yetenek metin döndürdüğünde sonuç bir çıktı dökümü oluyor. Oysa
"servisin durumu" ya da "diskin doluluğu" gibi şeyler tablo, ölçü ve günlük
olarak bakılmak isteniyor. Bu modül yeteneğin bunu **anlatmasını** sağlıyor.

Anlatmasını, çizmesini değil. Yetenek Qt kodu yazmıyor; ne göstermek
istediğini düz bir sözlükle söylüyor, çizimi uygulama yapıyor. Bunun üç
sebebi var ve üçü de pratik:

1. **Görsel dil korunuyor.** Ajanın yazdığı bir panel, uygulamanın geri
   kalanıyla aynı Fluent renklerini, aynı yarıçapı, aynı çizimleri
   kullanıyor. Serbest Qt kodu her yetenekte biraz farklı görünen bir
   arayüz üretirdi.
2. **Arayüz thread'i düşmüyor.** Yetenek ajanın thread'inde çalışıyor;
   oradan widget kurmak Qt'de tanımsız davranış. Düz sözlük thread
   sınırını güvenle geçiyor.
3. **Model de aynı şeyi görüyor.** Panel metne de çevriliyor, yani ajan
   kullanıcıya gösterdiği şeyin ne olduğunu biliyor.

Tanınmayan bir bölüm türü sessizce atlanmıyor, hata olarak dönüyor: ajan
yazdığı panelin görünmediğini fark etmeli ki düzeltebilsin.
"""

from __future__ import annotations

from typing import Any

#: Desteklenen bölüm türleri ve zorunlu alanları.
SECTIONS: dict[str, tuple[str, ...]] = {
    "olcu": ("ogeler",),      # büyük sayılar, durum rozetleri
    "tablo": ("satirlar",),   # başlıklı satırlar
    "liste": ("ogeler",),     # çizimli satırlar
    "gunluk": ("satirlar",),  # eşaralıklı çıktı
    "metin": ("icerik",),     # düz paragraf
}

#: Durum tonları. Renk adı değil anlam adı: yetenek "kırmızı" demiyor,
#: "kötü" diyor ve rengi tema belirliyor. Açık temaya geçildiğinde
#: yeteneklerin hiçbiri değişmiyor.
TONES = ("notr", "iyi", "uyari", "kotu")


class PanelError(ValueError):
    """Panel tanımı sözleşmeye uymuyor."""


def normalise(raw: Any) -> dict[str, Any] | None:
    """Yeteneğin döndürdüğünden panel çıkarır. Panel yoksa `None`."""
    if not isinstance(raw, dict):
        return None
    panel = raw.get("panel")
    if panel is None:
        return None
    if not isinstance(panel, dict):
        raise PanelError("'panel' bir sözlük olmalı")

    baslik = str(panel.get("baslik", "")).strip()
    if not baslik:
        raise PanelError("panel['baslik'] gerekli — panelin sekmesinde yazacak")

    bolumler = panel.get("bolumler")
    if not isinstance(bolumler, list) or not bolumler:
        raise PanelError("panel['bolumler'] boş olmayan bir liste olmalı")

    temiz = [_section(index, item) for index, item in enumerate(bolumler)]
    return {
        "baslik": baslik,
        "alt": str(panel.get("alt", "")).strip(),
        "bolumler": temiz,
    }


def _section(index: int, item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise PanelError(f"bölüm {index} bir sözlük olmalı")
    tur = str(item.get("tur", ""))
    if tur not in SECTIONS:
        raise PanelError(
            f"bölüm {index}: {tur!r} diye bir tür yok. "
            f"Olanlar: {', '.join(SECTIONS)}"
        )
    for alan in SECTIONS[tur]:
        if item.get(alan) is None:
            raise PanelError(f"bölüm {index} ({tur}): {alan!r} gerekli")

    out: dict[str, Any] = {"tur": tur, "baslik": str(item.get("baslik", ""))}
    if tur == "olcu":
        out["ogeler"] = [_metric(index, o) for o in _as_list(index, item["ogeler"])]
    elif tur == "tablo":
        out["basliklar"] = [str(h) for h in item.get("basliklar") or []]
        out["satirlar"] = [
            [str(c) for c in _as_list(index, row)]
            for row in _as_list(index, item["satirlar"])
        ]
    elif tur == "liste":
        out["ogeler"] = [_row(index, o) for o in _as_list(index, item["ogeler"])]
    elif tur == "gunluk":
        out["satirlar"] = [str(s) for s in _as_list(index, item["satirlar"])]
    else:
        out["icerik"] = str(item["icerik"])
    return out


def _as_list(index: int, value: Any) -> list:
    if not isinstance(value, list):
        raise PanelError(f"bölüm {index}: liste bekleniyordu, {type(value).__name__} geldi")
    return value


def _metric(index: int, item: Any) -> dict[str, str]:
    if not isinstance(item, dict) or "deger" not in item:
        raise PanelError(f"bölüm {index}: ölçü ögesi {{'etiket', 'deger'}} olmalı")
    return {
        "etiket": str(item.get("etiket", "")),
        "deger": str(item["deger"]),
        "durum": _tone(index, item.get("durum")),
    }


def _row(index: int, item: Any) -> dict[str, str]:
    if not isinstance(item, dict):
        raise PanelError(f"bölüm {index}: liste ögesi sözlük olmalı")
    return {
        "baslik": str(item.get("baslik", "")),
        "alt": str(item.get("alt", "")),
        "sag": str(item.get("sag", "")),
        "cizim": str(item.get("cizim", "sayfa")),
        "durum": _tone(index, item.get("durum")),
    }


def _tone(index: int, value: Any) -> str:
    tone = str(value or "notr")
    if tone not in TONES:
        raise PanelError(
            f"bölüm {index}: {tone!r} diye bir durum yok. Olanlar: {', '.join(TONES)}"
        )
    return tone


def to_text(panel: dict[str, Any]) -> str:
    """Paneli modele gösterilecek metne çevirir.

    Ajan kullanıcıya ne gösterdiğini bilmeli; yoksa panelde yazan bir şeyi
    sonraki cümlesinde çelişerek tekrar ediyor.
    """
    lines = [panel["baslik"]]
    if panel["alt"]:
        lines.append(panel["alt"])
    for bolum in panel["bolumler"]:
        lines.append("")
        if bolum["baslik"]:
            lines.append(f"[{bolum['baslik']}]")
        tur = bolum["tur"]
        if tur == "olcu":
            for o in bolum["ogeler"]:
                lines.append(f"  {o['etiket']}: {o['deger']}")
        elif tur == "tablo":
            if bolum["basliklar"]:
                lines.append("  " + " | ".join(bolum["basliklar"]))
            for row in bolum["satirlar"]:
                lines.append("  " + " | ".join(row))
        elif tur == "liste":
            for o in bolum["ogeler"]:
                sag = f"  ({o['sag']})" if o["sag"] else ""
                lines.append(f"  - {o['baslik']}{sag}")
                if o["alt"]:
                    lines.append(f"      {o['alt']}")
        elif tur == "gunluk":
            lines.extend("  " + s for s in bolum["satirlar"])
        else:
            lines.append("  " + bolum["icerik"])
    return "\n".join(lines)
