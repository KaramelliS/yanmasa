"""SSH oturumu — uzak makineyi kendi bilgisayarın gibi gezmek.

Windows'un kendi `ssh.exe`'si kullanılıyor, bir Python SSH kütüphanesi değil.
Sebebi tek bir cümlede: `~/.ssh/config` içindeki takma adlar ve anahtarlar
zaten orada. `brky` diye bir takma adın varsa burada da `brky` yazıyorsun;
aynı anahtarı ikinci bir yere kopyalamak, ikinci bir parola sorusu ve
kaçınılmaz olarak ikinci bir ayar dosyası demekti.

Dizin listesi `ls` çıktısını ayrıştırarak değil, `find -maxdepth 1 -printf`
ile alınıyor: `ls -l` çıktısı yerel dile göre değişiyor, boşluklu dosya
adlarında sütunları kaydırıyor ve tarih biçimi dosyanın yaşına göre
farklılaşıyor. `printf` biçimi bizim belirlediğimiz sabit alanlar veriyor.

**Parola desteklenmiyor ve bu bilinçli.** `ssh` parolayı terminalden
istiyor; onu programdan beslemek için parolayı bir yerde tutmak gerekir.
Anahtar tabanlı bağlantı hem daha güvenli hem zaten kurulu.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import PurePosixPath

#: Bağlantı ve komut için üst sınır. Ağ takılırsa arayüz donmamalı.
CONNECT_TIMEOUT = 10
COMMAND_TIMEOUT = 60

#: Listeleme çıktısındaki alan ayracı. Dosya adında geçme ihtimali yok:
#: POSIX dosya adında yalnızca `/` ve NUL yasak, ama bu diziyi ad olarak
#: kullanan bir dosya pratikte yok ve varsa satır atlanıyor.
SEP = "\x1f"

#: `find -printf` biçimi: tür, boyut, değiştirilme zamanı, izinler, ad.
LIST_FORMAT = f"%y{SEP}%s{SEP}%TY-%Tm-%Td %TH:%TM{SEP}%M{SEP}%f\\n"


class RemoteError(RuntimeError):
    """Bağlanılamadı ya da komut çalışmadı."""


@dataclass(frozen=True)
class SshHost:
    """Bağlantı bilgisi.

    `alias` doluysa geri kalanı yok sayılıyor: `~/.ssh/config` orada ne
    yazıyorsa o geçerli. Kullanıcının kendi ayarını ezmek, çalışan bir
    bağlantıyı bozmanın en hızlı yolu.
    """

    alias: str = ""
    host: str = ""
    user: str = "root"
    port: int = 22
    key: str = ""

    @property
    def label(self) -> str:
        if self.alias:
            return self.alias
        return f"{self.user}@{self.host}:{self.port}"

    def argv(self) -> list[str]:
        if self.alias:
            return [self.alias]
        args = ["-p", str(self.port)]
        if self.key:
            args += ["-i", self.key]
        return args + [f"{self.user}@{self.host}"]


@dataclass
class Entry:
    """Uzak dizindeki tek bir girdi."""

    name: str
    is_dir: bool
    size: int
    modified: str
    mode: str
    parent: str

    @property
    def path(self) -> str:
        return str(PurePosixPath(self.parent) / self.name)

    @property
    def size_label(self) -> str:
        if self.is_dir:
            return ""
        value = float(self.size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
            value /= 1024
        return f"{self.size} B"


@dataclass
class SshSession:
    """Açık bir uzak makine.

    Kalıcı bir kanal tutmuyor; her çağrı kendi `ssh` sürecini açıyor.
    Basit ve dayanıklı: ağ koptuğunda yeniden bağlanma mantığı yazmak
    gerekmiyor, bir sonraki çağrı zaten yeniden bağlanıyor. Bedeli her
    çağrıda el sıkışma gecikmesi; dosya gezmek için kabul edilebilir.
    """

    host: SshHost
    cwd: str = "/"
    connected: bool = False
    banner: str = ""
    _cache: dict[str, list[Entry]] = field(default_factory=dict, repr=False)

    # --- bağlantı ---------------------------------------------------------

    @staticmethod
    def ssh_path() -> str:
        found = shutil.which("ssh")
        if not found:
            raise RemoteError(
                "ssh was not found. On Windows, install the OpenSSH Client from "
                "Settings > Apps > Optional features."
            )
        return found

    def connect(self) -> str:
        """Bağlanır ve makinenin kim olduğunu döndürür."""
        out = self.run("echo \"$(hostname) | $(uname -sr) | $(whoami)\"")
        self.connected = True
        self.banner = out.strip()
        # Ev dizininden başla: `/` içinde gezinmeye başlamak, sunucuda
        # aradığın hiçbir şeyin orada olmamasıyla sonuçlanıyor.
        try:
            self.cwd = self.run("echo $HOME").strip() or "/"
        except RemoteError:
            self.cwd = "/"
        return self.banner

    def close(self) -> None:
        self.connected = False
        self._cache.clear()

    # --- komut ------------------------------------------------------------

    def run(self, command: str, timeout: int = COMMAND_TIMEOUT) -> str:
        argv = [
            self.ssh_path(),
            "-o", "BatchMode=yes",
            "-o", f"ConnectTimeout={CONNECT_TIMEOUT}",
            "-o", "StrictHostKeyChecking=accept-new",
            *self.host.argv(),
            command,
        ]
        try:
            done = subprocess.run(
                argv,
                capture_output=True,
                timeout=timeout,
                # Sunucular UTF-8; bozuk bayt tüm çıktıyı düşürmemeli.
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            raise RemoteError(
                f"{self.host.label}: no answer within {timeout} seconds"
            ) from None
        except OSError as exc:
            raise RemoteError(f"could not run ssh: {exc}") from None

        if done.returncode != 0:
            detail = (done.stderr or done.stdout or "").strip().splitlines()
            first = detail[0] if detail else f"exit code {done.returncode}"
            if "Permission denied" in first or "publickey" in first:
                first += (
                    " — the key was rejected. Password login is not "
                    "supported; add your public key to the server."
                )
            raise RemoteError(f"{self.host.label}: {first}")
        return done.stdout

    # --- dosya sistemi ----------------------------------------------------

    def listdir(self, path: str | None = None, refresh: bool = False) -> list[Entry]:
        target = _clean(path or self.cwd)
        if not refresh and target in self._cache:
            return self._cache[target]

        quoted = _quote(target)
        # `-mindepth 1` dizinin kendisini listelemiyor; `2>/dev/null` izin
        # verilmeyen alt yollar için, ama dizinin kendisi okunamıyorsa
        # `find` yine hata döndürüyor ve onu gizlemiyoruz.
        out = self.run(
            f"find {quoted} -mindepth 1 -maxdepth 1 -printf '{LIST_FORMAT}'"
        )
        entries: list[Entry] = []
        for line in out.splitlines():
            parts = line.split(SEP)
            if len(parts) != 5:
                continue
            kind, size, modified, mode, name = parts
            entries.append(
                Entry(
                    name=name,
                    is_dir=kind == "d",
                    size=int(size) if size.isdigit() else 0,
                    modified=modified,
                    mode=mode,
                    parent=target,
                )
            )
        # Klasörler önce, sonra ad sırası — Dosya Gezgini'nin sıralaması.
        entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))
        self._cache[target] = entries
        return entries

    def enter(self, path: str) -> list[Entry]:
        entries = self.listdir(path)
        self.cwd = _clean(path)
        return entries

    def up(self) -> list[Entry]:
        return self.enter(str(PurePosixPath(self.cwd).parent))

    def read(self, path: str, max_bytes: int = 200_000) -> str:
        size = self.run(f"stat -c %s {_quote(path)}").strip()
        if size.isdigit() and int(size) > max_bytes:
            raise RemoteError(
                f"{path} is {int(size) // 1024} KB — we do not open files over "
                f"{max_bytes // 1024} KB here. Take a section with `remote_run`."
            )
        return self.run(f"cat {_quote(path)}")

    def write(self, path: str, content: str) -> str:
        """Dosyayı yazar. İçerik stdin'den değil, base64 olarak gidiyor:
        tırnak, satır sonu ve Türkçe karakter kabuk tarafından yorumlanmasın."""
        import base64

        blob = base64.b64encode(content.encode("utf-8")).decode("ascii")
        self.run(f"printf %s {_quote(blob)} | base64 -d > {_quote(path)}")
        self._cache.pop(str(PurePosixPath(path).parent), None)
        return f"{path} written ({len(content)} characters)"

    def disk(self) -> str:
        return self.run("df -h / | tail -1").strip()


def _clean(path: str) -> str:
    path = (path or "/").strip() or "/"
    return str(PurePosixPath(path)) if path.startswith("/") else path


def _quote(value: str) -> str:
    """POSIX kabuk için tek tırnaklama.

    `shlex.quote` doğru olanı yapıyor ama Windows'ta `os.name` kontrolü
    yok; yine de POSIX kuralı gerekiyor çünkü komut karşı tarafta
    çalışıyor. Bu yüzden elle.
    """
    return "'" + value.replace("'", "'\\''") + "'"
