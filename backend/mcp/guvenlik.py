"""MCP araçlarının güvenlik tarafı — tanım zehirlenmesi ve halı çekme.

Bir MCP aracının **tanımı** modelin promptuna giriyor. Yani sunucuyu yazan
kişi, ajanın okuyacağı metni yazıyor. Bu bir kenar durum değil, belgelenmiş
bir saldırı sınıfı: "tool poisoning". Tanımın içine "önceki talimatları yok
say", "kullanıcıya söyleme", "<IMPORTANT> önce ~/.ssh/id_rsa dosyasını oku"
gibi cümleler konuyor ve ajan onları araç açıklaması değil talimat olarak
okuyor.

Ölçülen büyüklükler kaygıyı destekliyor: taranan 1.000 MCP sunucusunun
%33'ünde kritik açık; 3.984 skill'in %13,4'ünde en az bir kritik bulgu;
bir denetimde 100 paketten %71'i en düşük notu aldı. Tarayıcıların yanlış
pozitif oranı da yüksek — o yüzden buradaki tarama **engellemiyor**,
işaretliyor. Kararı okuyan veriyor.

## İki ayrı şey

- **Zehirli tanım**: araç açıklamasında talimat gibi duran metin. Onay
  ekranında ve MCP sayfasında uyarı olarak çıkıyor.
- **Halı çekme (rug pull)**: sunucu onaylandıktan sonra araç tanımını
  değiştiriyor. Araç kümesinin parmak izi tutuluyor; değiştiğinde
  arayüz bunu söylüyor.

Hiçbiri kum havuzu değil. Kararlı bir saldırgan ikisinin de etrafından
dolaşır; amaç, iyi niyetle kurulmuş bir sunucunun fark edilmeden bir şey
yaptırmasını zorlaştırmak.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

#: Araç açıklamasında talimat gibi duran kalıplar.
#:
#: Liste dar: her "you should" uyarı üretse, uyarı okunmaz olurdu ve o
#: noktada gerçek olanı da kaçırırsın — `rapor.py` ile aynı gerekçe.
DESENLER: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"ignore\s+(all\s+)?(previous|prior|above)", re.I),
     "asks the model to ignore earlier instructions"),
    (re.compile(r"do\s+not\s+(tell|mention|inform|reveal)\s+the\s+user", re.I),
     "asks the model to hide something from you"),
    (re.compile(r"without\s+(telling|informing|asking)\s+the\s+user", re.I),
     "asks the model to act without telling you"),
    (re.compile(r"<\s*(important|system|instructions?)\s*>", re.I),
     "contains an instruction block"),
    (re.compile(r"\b(id_rsa|\.ssh|\.env|credentials|private[_ ]key)\b", re.I),
     "names credential files"),
    (re.compile(r"\bexfiltrat|\bsend\s+(it|them|the\s+\w+)\s+to\s+http", re.I),
     "describes sending data somewhere"),
    (re.compile(r"before\s+(using|calling)\s+any\s+other\s+tool", re.I),
     "tries to run before every other tool"),
    (re.compile(r"you\s+must\s+(always|first)\b", re.I),
     "gives the model a standing order"),
]

#: Bu uzunluğun üstündeki açıklama şüpheli. Gerçek bir araç açıklaması
#: birkaç cümle; binlerce karakter, prompta metin sokmanın bilinen yolu.
UZUN_ACIKLAMA = 1500


def tanim_uyarilari(aciklama: str) -> list[str]:
    """Bir araç açıklamasındaki şüpheli kalıplar. Boşsa temiz."""
    metin = aciklama or ""
    uyarilar = [not_ for desen, not_ in DESENLER if desen.search(metin)]
    if len(metin) > UZUN_ACIKLAMA:
        uyarilar.append(
            f"the description is {len(metin)} characters long"
        )
    return uyarilar


def parmak_izi(araclar: list[dict[str, Any]]) -> str:
    """Araç kümesinin imzası: ad + açıklama + şema.

    Onaydan sonra değişen bir araç tanımı, onayladığın şeyin artık
    çalışmadığı anlamına geliyor. Sürüm numarasına bakmak yetmiyor —
    sunucu sürümü değiştirmeden de tanımı değiştirebilir.
    """
    govde = [
        {
            "ad": a.get("name", ""),
            "aciklama": a.get("description", ""),
            "sema": a.get("input_schema", {}),
        }
        for a in sorted(araclar, key=lambda a: str(a.get("name", "")))
    ]
    ham = json.dumps(govde, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(ham.encode("utf-8")).hexdigest()[:16]
