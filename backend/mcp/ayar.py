"""MCP sunucu ayarları — `~/.ajan/mcp.json`.

Biçim kasten **standart olan**: `{"mcpServers": {"ad": {"command": ...}}}`.
Kendi biçimimizi uydurmak, insanların elindeki Claude Desktop ya da VS Code
yapılandırmasını kopyalayamaması demekti; bu dosyalar internette hazır
dolaşıyor ve yeniden yazdırmanın kimseye faydası yok.

## Hiçbir sunucu kendiliğinden açılmıyor

`enabled` alanı bizim eklediğimiz tek alan ve varsayılanı **kapalı**.
Dosyaya bir sunucu yazmak onu çalıştırmaya izin vermek değil: MCP
sunucusu senin makinende senin haklarınla çalışan bir süreç ve
taranan sunucuların üçte birinde kritik açık bulundu. Açma kararı ayrı
bir hareket olmalı.

## Sırlar

`env` alanı anahtar taşıyabiliyor (`GITHUB_TOKEN` gibi). Bu dosya
`~/.ajan` altında, depoda değil, ve arayüz `env` değerlerini **hiç**
göstermiyor — yalnızca hangi anahtarların tanımlı olduğunu. `${VAR}`
yazarsan süreç ortamından okunuyor, yani anahtarı burada tutmak zorunda
da değilsin.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..skills.shortcuts import STATE_DIR

DOSYA = STATE_DIR / "mcp.json"

#: Claude Desktop'ın yapılandırması. "İçe aktar" bunu okuyor.
CLAUDE_DESKTOP = (
    Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    / "Claude" / "claude_desktop_config.json"
)

AD_KURALI = re.compile(r"^[a-zA-Z0-9_-]{1,48}$")

#: `${VAR}` yer tutucusu: anahtarı dosyaya yazmak zorunda kalmamak için.
_YER_TUTUCU = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class AyarHatasi(RuntimeError):
    pass


@dataclass
class Sunucu:
    """Bir MCP sunucusunun tanımı."""

    ad: str
    #: stdio için çalıştırılacak komut. HTTP sunucularında boş.
    komut: str = ""
    argumanlar: list[str] = field(default_factory=list)
    ortam: dict[str, str] = field(default_factory=dict)
    calisma_dizini: str = ""
    #: HTTP sunucusu ise adresi. Komutla birlikte verilemez.
    adres: str = ""
    #: Varsayılan **kapalı**. Dosyaya yazmak çalıştırmaya izin vermek değil.
    acik: bool = False

    @property
    def http(self) -> bool:
        return bool(self.adres)

    @property
    def anlat(self) -> str:
        """Arayüzde görünen kısa tanım. Sır taşımıyor."""
        if self.http:
            return self.adres
        return " ".join([self.komut, *self.argumanlar]).strip()

    def cozulmus_ortam(self) -> dict[str, str]:
        """`${VAR}` yer tutucuları süreç ortamından dolduruluyor.

        Bulunamayan bir değişken **boş dize değil**, hata: sessizce boş
        bir anahtarla bağlanmak, sunucunun anlaşılmaz bir yetki hatası
        vermesi ve sebebin görünmemesi demek.
        """
        cikti: dict[str, str] = {}
        for anahtar, deger in self.ortam.items():
            def _degistir(m: re.Match[str]) -> str:
                bulunan = os.environ.get(m.group(1))
                if bulunan is None:
                    raise AyarHatasi(
                        f"{self.ad}: {m.group(0)} is not set in the "
                        f"environment"
                    )
                return bulunan

            cikti[anahtar] = _YER_TUTUCU.sub(_degistir, str(deger))
        return cikti

    def as_dict(self) -> dict[str, Any]:
        cikti: dict[str, Any] = {"enabled": self.acik}
        if self.http:
            cikti["url"] = self.adres
        else:
            cikti["command"] = self.komut
            if self.argumanlar:
                cikti["args"] = list(self.argumanlar)
            if self.calisma_dizini:
                cikti["cwd"] = self.calisma_dizini
        if self.ortam:
            cikti["env"] = dict(self.ortam)
        return cikti

    @classmethod
    def from_dict(cls, ad: str, ham: Any) -> Sunucu | None:
        if not isinstance(ham, dict) or not AD_KURALI.match(ad):
            return None
        komut = str(ham.get("command") or "")
        adres = str(ham.get("url") or ham.get("serverUrl") or "")
        if not (komut or adres):
            return None
        argumanlar = ham.get("args")
        ortam = ham.get("env")
        return cls(
            ad=ad,
            komut=komut,
            argumanlar=[str(a) for a in argumanlar]
            if isinstance(argumanlar, list) else [],
            ortam={str(k): str(v) for k, v in ortam.items()}
            if isinstance(ortam, dict) else {},
            calisma_dizini=str(ham.get("cwd") or ""),
            adres=adres,
            # Başka bir uygulamadan kopyalanan bir dosyada `enabled`
            # olmuyor ve olmaması "açık" demek değil.
            acik=bool(ham.get("enabled", False)),
        )


def oku(yol: Path | None = None) -> list[Sunucu]:
    """Tanımlı sunucular. Dosya yoksa ya da bozuksa boş liste.

    Bozuk bir yapılandırma yüzünden uygulamanın açılmaması kabul
    edilemez; MCP bir kolaylık, önkoşul değil.
    """
    yol = yol or DOSYA
    try:
        ham = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    kok = ham.get("mcpServers") if isinstance(ham, dict) else None
    if not isinstance(kok, dict):
        return []
    cikti = []
    for ad, tanim in kok.items():
        sunucu = Sunucu.from_dict(str(ad), tanim)
        if sunucu is not None:
            cikti.append(sunucu)
    cikti.sort(key=lambda s: s.ad)
    return cikti


def yaz(sunucular: list[Sunucu], yol: Path | None = None) -> None:
    yol = yol or DOSYA
    govde = {"mcpServers": {s.ad: s.as_dict() for s in sunucular}}
    try:
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(json.dumps(govde, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    except OSError as hata:
        raise AyarHatasi(f"could not write {yol}: {hata}") from None


def ac_kapa(ad: str, acik: bool, yol: Path | None = None) -> bool:
    sunucular = oku(yol)
    for sunucu in sunucular:
        if sunucu.ad == ad:
            sunucu.acik = acik
            yaz(sunucular, yol)
            return True
    return False


def ekle(sunucu: Sunucu, yol: Path | None = None) -> None:
    if not AD_KURALI.match(sunucu.ad):
        raise AyarHatasi(
            f"{sunucu.ad!r} is not a usable name. Letters, digits, "
            f"underscore and hyphen, up to 48 characters."
        )
    if sunucu.komut and sunucu.adres:
        raise AyarHatasi(
            f"{sunucu.ad}: give either a command or a url, not both."
        )
    sunucular = [s for s in oku(yol) if s.ad != sunucu.ad]
    sunucular.append(sunucu)
    sunucular.sort(key=lambda s: s.ad)
    yaz(sunucular, yol)


def sil(ad: str, yol: Path | None = None) -> bool:
    sunucular = oku(yol)
    kalan = [s for s in sunucular if s.ad != ad]
    if len(kalan) == len(sunucular):
        return False
    yaz(kalan, yol)
    return True


def claude_desktop_aktar(kaynak: Path | None = None,
                         yol: Path | None = None) -> list[str]:
    """Claude Desktop'ın sunucularını içe aktarır — hepsi **kapalı**.

    Var olan bir tanımın üstüne yazılmıyor: elle düzenlediğin bir
    sunucuyu içe aktarma sessizce geri almamalı.
    """
    kaynak = kaynak or CLAUDE_DESKTOP
    try:
        ham = json.loads(kaynak.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    kok = ham.get("mcpServers") if isinstance(ham, dict) else None
    if not isinstance(kok, dict):
        return []
    var_olan = {s.ad for s in oku(yol)}
    eklenen: list[str] = []
    for ad, tanim in kok.items():
        if str(ad) in var_olan:
            continue
        sunucu = Sunucu.from_dict(str(ad), tanim)
        if sunucu is None:
            continue
        sunucu.acik = False
        try:
            ekle(sunucu, yol)
        except AyarHatasi:
            continue
        eklenen.append(sunucu.ad)
    return eklenen


#: Örnek dosya. Hiçbiri açık değil ve hepsi npx ile çalışıyor.
ORNEK = {
    "mcpServers": {
        "playwright": {
            "command": "npx",
            "args": ["-y", "@playwright/mcp@latest"],
            "enabled": False,
        },
        "fetch": {
            "command": "npx",
            "args": ["-y", "mcp-server-fetch"],
            "enabled": False,
        },
        "github": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"},
            "enabled": False,
        },
    }
}


def ornek_yaz(yol: Path | None = None) -> Path:
    """Örnek yapılandırmayı yazar. Var olan dosyanın üstüne yazmıyor."""
    yol = yol or DOSYA
    if yol.exists():
        return yol
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(ORNEK, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    return yol
