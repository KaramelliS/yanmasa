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
        raise FileError("The path cannot be empty")
    expanded = os.path.expandvars(os.path.expanduser(path.strip()))
    try:
        return Path(expanded).resolve()
    except (OSError, ValueError) as exc:
        raise FileError(f"Invalid path {path!r}: {exc}") from None


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
        raise FileError(f"Could not write {resolved}: {exc}") from None

    verb = "appended" if append else "written"
    return f"{resolved} ({len(content)} characters {verb})"


def read(path: str, max_chars: int = MAX_READ_CHARS) -> str:
    resolved = resolve(path)
    if not resolved.exists():
        raise FileError(f"{resolved} does not exist")
    if resolved.is_dir():
        raise FileError(f"{resolved} is a folder; use list_dir")

    try:
        text = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise FileError(f"Could not read {resolved}: {exc}") from None

    if len(text) > max_chars:
        return (
            text[:max_chars]
            + f"\n\n[... showing the first {max_chars} of {len(text)} characters]"
        )
    return text


def edit(path: str, old: str, new: str) -> str:
    """Birebir metin değişimi. Eşsiz eşleşme yoksa hiçbir şey yazılmaz."""
    resolved = resolve(path)
    if not resolved.exists():
        raise FileError(f"{resolved} does not exist")
    if not old:
        raise FileError("The search text cannot be empty; use write_file for a new file")

    text = resolved.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0:
        raise FileError(f"The search text was not found in {resolved}; read the file first")
    if count > 1:
        # Kısmi bir düzenleme, düzenleme yapmamaktan kötü: model dosyanın
        # değiştiğini sanıp devam eder.
        raise FileError(
            f"The search text appears {count} times, so which one is unclear. "
            f"Add more surrounding lines to make it unique."
        )

    resolved.write_text(text.replace(old, new), encoding="utf-8", newline="")
    return f"{resolved} updated ({len(old)} characters -> {len(new)} characters)"


def list_dir(path: str, limit: int = 200) -> str:
    resolved = resolve(path)
    if not resolved.exists():
        raise FileError(f"{resolved} does not exist")
    if not resolved.is_dir():
        raise FileError(f"{resolved} is not a folder")

    entries = []
    for index, item in enumerate(sorted(resolved.iterdir(),
                                        key=lambda p: (p.is_file(), p.name.lower()))):
        if index >= limit:
            entries.append(f"... truncated at {limit} entries")
            break
        if item.is_dir():
            entries.append(f"{item.name}/")
        else:
            try:
                size = item.stat().st_size
            except OSError:
                size = 0
            entries.append(f"{item.name}  ({size} bytes)")

    return f"{resolved}\n" + ("\n".join(entries) if entries else "(empty)")
