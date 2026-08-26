"""Dosya işlemleri.

`run_shell` ile de dosya yazılabilir ama kötü yazılır: metni PowerShell
here-string'ine gömmek kaçış cehennemi, Türkçe karakterler kod sayfasına
takılıyor ve her yazma güvenlik kapısını tetikliyor. Ayrı araçlar hem
güvenilir hem de kapının yalnızca *gerçekten* riskli olanı ayıklamasına izin
veriyor — üzerine yazma riskli, yeni dosya değil.

Kodlama her yerde açıkça UTF-8. Windows'un varsayılan kod sayfası cp1254 ve
Türkçe metni sessizce bozuyor.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

#: Bir okumada modele gidecek en fazla karakter. Bir dosyayı bağlama komple
#: doldurmak, ajanın geri kalan işi için yer bırakmıyor.
MAX_READ_CHARS = 60_000

#: Kazara yazmanın en pahalı olduğu yerler. Buralara yazmak onay ister.
SENSITIVE_PARTS = {
    "windows", "system32", "program files", "program files (x86)",
    ".ssh", ".gnupg", "appdata\\roaming\\npm",
}

SENSITIVE_NAMES = {".env", "id_rsa", "id_ed25519", "credentials", "settings.json"}


class FileError(RuntimeError):
    """Dosya işlemi yapılamadı."""


@dataclass(frozen=True)
class WriteInfo:
    path: Path
    existed: bool
    sensitive: bool


def resolve(path: str) -> Path:
    """Kullanıcı yolunu mutlak yola çevirir. `~` ve ortam değişkenleri açılır."""
    if not path or not path.strip():
        raise FileError("Yol boş olamaz")
    expanded = os.path.expandvars(os.path.expanduser(path.strip()))
    try:
        return Path(expanded).resolve()
    except (OSError, ValueError) as exc:
        raise FileError(f"Geçersiz yol {path!r}: {exc}") from None


def is_sensitive(path: Path) -> bool:
    lowered = str(path).lower()
    if path.name.lower() in SENSITIVE_NAMES:
        return True
    return any(part in lowered for part in SENSITIVE_PARTS)


def inspect_write(path: str) -> WriteInfo:
    """Yazmadan önce kapının ihtiyaç duyduğu bilgi."""
    resolved = resolve(path)
    return WriteInfo(
        path=resolved, existed=resolved.exists(), sensitive=is_sensitive(resolved)
    )


def write(path: str, content: str, append: bool = False) -> str:
    resolved = resolve(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    try:
        with open(resolved, mode, encoding="utf-8", newline="") as handle:
            handle.write(content)
    except OSError as exc:
        raise FileError(f"{resolved} yazılamadı: {exc}") from None

    verb = "eklendi" if append else "yazıldı"
    return f"{resolved} ({len(content)} karakter {verb})"


def read(path: str, max_chars: int = MAX_READ_CHARS) -> str:
    resolved = resolve(path)
    if not resolved.exists():
        raise FileError(f"{resolved} yok")
    if resolved.is_dir():
        raise FileError(f"{resolved} bir klasör; list_dir kullan")

    try:
        text = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise FileError(f"{resolved} okunamadı: {exc}") from None

    if len(text) > max_chars:
        return (
            text[:max_chars]
            + f"\n\n[... {len(text)} karakterin ilk {max_chars} tanesi gösterildi]"
        )
    return text


def edit(path: str, old: str, new: str) -> str:
    """Birebir metin değişimi. Eşsiz eşleşme yoksa hiçbir şey yazılmaz."""
    resolved = resolve(path)
    if not resolved.exists():
        raise FileError(f"{resolved} yok")
    if not old:
        raise FileError("Aranan metin boş olamaz; yeni dosya için write_file kullan")

    text = resolved.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0:
        raise FileError(f"Aranan metin {resolved} içinde bulunamadı; dosyayı önce oku")
    if count > 1:
        # Kısmi bir düzenleme, düzenleme yapmamaktan kötü: model dosyanın
        # değiştiğini sanıp devam eder.
        raise FileError(
            f"Aranan metin {count} kez geçiyor; hangisi olduğu belirsiz. "
            f"Daha fazla çevre satırı ekleyerek eşsiz hale getir."
        )

    resolved.write_text(text.replace(old, new), encoding="utf-8", newline="")
    return f"{resolved} güncellendi ({len(old)} karakter -> {len(new)} karakter)"


def list_dir(path: str, limit: int = 200) -> str:
    resolved = resolve(path)
    if not resolved.exists():
        raise FileError(f"{resolved} yok")
    if not resolved.is_dir():
        raise FileError(f"{resolved} bir klasör değil")

    entries = []
    for index, item in enumerate(sorted(resolved.iterdir(),
                                        key=lambda p: (p.is_file(), p.name.lower()))):
        if index >= limit:
            entries.append(f"... {limit} ögede kesildi")
            break
        if item.is_dir():
            entries.append(f"{item.name}/")
        else:
            try:
                size = item.stat().st_size
            except OSError:
                size = 0
            entries.append(f"{item.name}  ({size} bayt)")

    return f"{resolved}\n" + ("\n".join(entries) if entries else "(boş)")
