"""Risk sınıflandırıcı — hangi eylem onay ister.

Ajanın kabuk komutu çalıştırma yetkisi olduğu andan itibaren bu modül isteğe
bağlı olmaktan çıkıyor. GUI'de bir dosyayı silmek birkaç tıklama ve geri
dönüşüm kutusuna gider; `Remove-Item -Recurse -Force` bir satır ve gitmez.

Sınıflandırma **desen eşleştirmeyle** yapılıyor, modele sorularak değil.
"Bu tehlikeli mi?" diye modele sormak, aynı modelin komutu üretmiş olması
nedeniyle dairesel; ayrıca bir API çağrısı daha demek.

Kapsam sınırı: bu bir kum havuzu değil, bir hatırlatıcı. Kararlı bir saldırgan
desenlerin etrafından dolaşır. Amaç, iyi niyetli bir ajanın geri alınamaz bir
şeyi fark etmeden yapmasını engellemek.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Risk(str, Enum):
    SAFE = "safe"
    CONFIRM = "confirm"


@dataclass(frozen=True)
class Verdict:
    risk: Risk
    reason: str = ""

    @property
    def needs_confirmation(self) -> bool:
        return self.risk is Risk.CONFIRM


SAFE = Verdict(Risk.SAFE)


def _rule(pattern: str, reason: str) -> tuple[re.Pattern[str], str]:
    return re.compile(pattern, re.IGNORECASE), reason


#: Kabuk komutu desenleri. Sıra önemli değil, ilk eşleşen kazanır.
SHELL_RULES = [
    _rule(r"\brm\b|\bRemove-Item\b|\bdel\b|\berase\b|\brd\b|\brmdir\b",
          "dosya ya da klasör siliyor"),
    # `format` tek başına aranamaz: PowerShell'in en sık kullanılan salt-okunur
    # cmdlet'leri `Format-List`, `Format-Table`, `Format-Wide`. İlk sürüm bunu
    # yapıyordu ve bir dosya listeleme komutuna "diski biçimlendiriyor" dedi.
    # Boş yere uyaran bir kapı görmezden gelinir; o yüzden burada geniş değil
    # dar olmak doğru.
    _rule(r"\bformat(?:\.com)?\s+[A-Za-z]:|\bFormat-Volume\b|\bdiskpart\b|\bmkfs\b",
          "diski biçimlendiriyor"),
    _rule(r"\bStop-Computer\b|\bshutdown\b|\bRestart-Computer\b|\blogoff\b",
          "bilgisayarı kapatıyor ya da yeniden başlatıyor"),
    _rule(r"\bStop-Process\b|\btaskkill\b|\bkill\b", "çalışan bir süreci sonlandırıyor"),
    _rule(r"\breg\b\s+(delete|add)|\bSet-ItemProperty\b.*HK(LM|CU)|\bregedit\b",
          "kayıt defterini değiştiriyor"),
    _rule(r"\bSet-ExecutionPolicy\b|\bDisable-\w+|\bUninstall-\b|\bwinget\s+uninstall\b",
          "sistem ayarı değiştiriyor ya da uygulama kaldırıyor"),
    _rule(r"\bnetsh\b|\bSet-NetFirewall|\bNew-NetFirewall", "ağ ya da güvenlik duvarı ayarı değiştiriyor"),
    _rule(r"\bschtasks\b|\bNew-ScheduledTask\b|\bNew-Service\b|\bsc\.exe\b",
          "kalıcı görev ya da servis oluşturuyor"),
    _rule(r"\bcurl\b.*\|\s*(iex|bash|sh)|\bInvoke-Expression\b|\biex\b|\bInvoke-WebRequest\b.*\|",
          "internetten indirdiğini doğrudan çalıştırıyor"),
    _rule(r"\bgit\b\s+(push|reset\s+--hard|clean\s+-\w*[fd]|checkout\s+--)",
          "geri alınamaz bir git işlemi"),
    # `2>$null` gürültü bastırma, dosyaya yazma değil — onu dışarıda bırak.
    _rule(r"\bSet-Content\b|\bOut-File\b|>>?\s*(?!\$null\b)[A-Za-z0-9_.\\/]",
          "bir dosyanın üzerine yazıyor"),
    _rule(r"\bStart-Process\b.*-Verb\s+RunAs|\brunas\b", "yönetici olarak çalıştırıyor"),
]

#: Tıklama koordinatı yerine pencere başlığına bakan kurallar. Ajan neye
#: tıkladığını bilmez; hangi pencerede olduğunu bilir.
WINDOW_RULES = [
    _rule(r"\bbank|\bhesab[ıi]m|ödeme|payment|checkout|iyzico|paypal|stripe",
          "ödeme ya da bankacılık penceresi"),
    _rule(r"biçimlendir|format|disk yönetimi|disk management",
          "disk aracı"),
    _rule(r"kayıt defteri|registry editor", "kayıt defteri düzenleyicisi"),
]

#: Yazılan metin bunlara benziyorsa dur — ajan kimlik bilgisi girmemeli.
SECRET_HINTS = [
    _rule(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b", "kart numarasına benziyor"),
    _rule(r"\b\d{11}\b", "TC kimlik numarasına benziyor"),
    _rule(r"\bsk-[A-Za-z0-9_-]{16,}|\bghp_[A-Za-z0-9]{20,}", "bir API anahtarı"),
]


def classify_shell(command: str) -> Verdict:
    """Kabuk komutunu sınıflandırır."""
    for pattern, reason in SHELL_RULES:
        if pattern.search(command):
            return Verdict(Risk.CONFIRM, reason)
    return SAFE


def classify_typing(text: str) -> Verdict:
    """Yazılacak metni sınıflandırır."""
    for pattern, reason in SECRET_HINTS:
        if pattern.search(text):
            return Verdict(Risk.CONFIRM, reason)
    return SAFE


def classify_window(title: str) -> Verdict:
    """Ön plandaki pencereyi sınıflandırır — tıklama ve yazma öncesi."""
    for pattern, reason in WINDOW_RULES:
        if pattern.search(title):
            return Verdict(Risk.CONFIRM, reason)
    return SAFE


def classify_write(path: str) -> Verdict:
    """Dosya yazmayı sınıflandırır.

    Yeni bir dosya oluşturmak geri alınabilir — silersin, biter. Var olan bir
    dosyanın üzerine yazmak değil: eski içerik gitmiştir. Kapı bu ayrımı
    yapıyor, yoksa ajanın her `write_file` çağrısı onay isterdi ve onay
    yorgunluğu kapıyı işlevsiz kılardı.
    """
    from ..computer.files import FileError, inspect_write

    try:
        info = inspect_write(path)
    except FileError:
        return SAFE  # yol zaten geçersiz; araç anlamlı bir hata verecek

    if info.sensitive:
        return Verdict(Risk.CONFIRM, "sistem ya da kimlik bilgisi dosyasına yazıyor")
    if info.existed:
        return Verdict(Risk.CONFIRM, f"var olan {info.path.name} dosyasının üzerine yazıyor")
    return SAFE


def classify(name: str, payload: dict, window_title: str = "") -> Verdict:
    """Bir araç çağrısının tamamını sınıflandırır."""
    if name == "run_shell":
        return classify_shell(str(payload.get("command", "")))

    if name == "write_file":
        if payload.get("append"):
            return SAFE  # ekleme veri kaybetmiyor
        return classify_write(str(payload.get("path", "")))

    if name == "edit_file":
        # Düzenleme cerrahi ve eşsiz eşleşme şartı var; hassas dosyada yine sor.
        from ..computer.files import FileError, inspect_write

        try:
            if inspect_write(str(payload.get("path", ""))).sensitive:
                return Verdict(Risk.CONFIRM, "hassas bir dosyayı düzenliyor")
        except FileError:
            pass
        return SAFE

    if name == "terminal_send":
        # Terminale yazılan da bir komut; kabukla aynı kurallara tabi.
        text = payload.get("text")
        if text:
            return classify_shell(str(text))
        return SAFE

    if name == "type":
        verdict = classify_typing(str(payload.get("text", "")))
        if verdict.needs_confirmation:
            return verdict

    if name in {"type", "key", "left_click", "double_click", "left_click_drag"}:
        return classify_window(window_title)

    if name == "side_launch":
        # Yan alanda açılan uygulamayı Berkay göremiyor — masaüstü görünmez.
        # Görünür bir eylemi kaçırırsa fark eder, görünmez olanı fark etmez;
        # o yüzden burada onay, ne açıldığının tek göstergesi.
        return Verdict(Risk.CONFIRM, "görünmeyen çalışma alanında uygulama açıyor")

    if name == "side_act" and payload.get("action") == "type":
        # Yan alanda tıklama sormuyoruz, yoksa paralel çalışma diye bir şey
        # kalmaz. Yazılan metin başka: kimlik bilgisi kalıpları burada da
        # aynı kapıdan geçiyor.
        return classify_typing(str(payload.get("text", "")))

    return SAFE


#: Uzak makinede sorgusuz çalışabilecek komutlar.
#:
#: Yerel kapı bir **yasak listesi**: tehlikeli kalıpları arıyor, gerisine
#: izin veriyor. Uzak makinede bu ters çevrildi ve bunun somut bir sebebi
#: var: yerelde yanlış giden bir komut Berkay'ın kendi dosyası, sunucuda
#: aynı komut çalışan bir servisi düşürüyor ve geri dönüşü yok. Bir yazma
#: işlemini onaylamak ucuz; yanlış bir yazmayı geri almak mümkün değil.
#:
#: Bu yüzden burada **izin listesi**: yalnızca okuyan komutlar sorgusuz
#: geçiyor, tanımadığımız her şey soruluyor.
READ_ONLY_REMOTE = frozenset({
    "ls", "dir", "cat", "head", "tail", "wc", "stat", "file", "find", "locate",
    "grep", "egrep", "fgrep", "rg", "sort", "uniq", "cut", "tr", "column",
    "df", "du", "free", "uptime", "uname", "hostname", "whoami", "id", "groups",
    "date", "pwd", "echo", "printf", "env", "printenv", "which", "type",
    "ps", "pgrep", "lsof", "ss", "netstat", "ip", "ifconfig", "lsblk", "blkid",
    "md5sum", "sha256sum", "sha1sum", "base64", "readlink", "realpath",
    "dpkg", "apt-cache", "pip", "python3", "node", "nproc", "lscpu", "vmstat",
    "true", "false", "test", "sleep", "tee",
})

#: Alt komutu okumaya çeviren durumlar. `systemctl status` zararsız,
#: `systemctl stop` bir servisi düşürüyor.
READ_ONLY_SUB = {
    "systemctl": {"status", "is-active", "is-enabled", "list-units",
                  "list-unit-files", "show", "cat"},
    "journalctl": None,          # None: tüm alt komutlar okuma sayılıyor
    "git": {"status", "log", "diff", "show", "branch", "remote", "config"},
    "docker": {"ps", "logs", "images", "inspect", "stats", "version"},
    "systemd-analyze": None,
}

#: Komutu okuma olmaktan çıkaran işaretler. `>` dosyaya yazıyor, `sed -i`
#: yerinde değiştiriyor, `sudo` yetki yükseltiyor.
_REMOTE_UNSAFE = re.compile(
    r">|\bsudo\b|\bsu\b|\bdd\b|\bmkfs|\bchmod\b|\bchown\b|\bmv\b|\bcp\b|"
    r"\bln\b|\btruncate\b|\bcrontab\b|\bpasswd\b|\buseradd\b|\buserdel\b|"
    r"\bapt\b|\bapt-get\b|\byum\b|\bdnf\b|\bpip\s+install|\bnpm\s+i"
)


def _subcommand(words: list[str]) -> str:
    """Bayrakları atlayıp asıl alt komutu bulur.

    Önce ikinci kelime alınıyordu ve `git -C /srv/app log` salt-okunur bir
    listelemeyken onay istiyordu. Boş yere uyaran bir kapı görmezden
    gelinir; bu dosyada aynı hata `format` kuralında bir kez yapıldı.
    """
    atla = False
    for word in words:
        if atla:
            atla = False
            continue
        if word.startswith("-"):
            # `-C DIZIN` gibi değer alan bayraklar: değeri de atla.
            atla = word in {"-C", "-c", "-f", "-H", "-u", "--git-dir"}
            continue
        return word
    return ""


def classify_remote(command: str) -> Verdict:
    """Uzak komut. Tanımadığımız her şey onay istiyor."""
    text = command.strip()
    if not text:
        return SAFE
    if _REMOTE_UNSAFE.search(text):
        return Verdict(Risk.CONFIRM, "uzak makinede değişiklik yapıyor")

    # Boru ve zincirin her parçası ayrı ayrı bakılıyor: `cat x | sh` içindeki
    # `cat` zararsız, `sh` değil.
    for segment in re.split(r"\|\||&&|\||;", text):
        words = segment.split()
        if not words:
            continue
        head = words[0].rsplit("/", 1)[-1]
        if head in READ_ONLY_SUB:
            allowed = READ_ONLY_SUB[head]
            sub = _subcommand(words[1:])
            if allowed is not None and sub not in allowed:
                return Verdict(
                    Risk.CONFIRM, f"uzak makinede {head} {sub} çalıştırıyor"
                )
            continue
        if head not in READ_ONLY_REMOTE:
            return Verdict(Risk.CONFIRM, f"uzak makinede {head} çalıştırıyor")
    return SAFE
