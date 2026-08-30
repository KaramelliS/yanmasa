"""Windows açılışında kendiliğinden başlama — tek bir kayıt defteri değeri.

Uygulamanın açılışta başlaması için Windows'ta üç yol var ve ikisi
**yönetici hakkı istiyor**: `HKLM\\...\\Run` altına yazmak da, Zamanlanmış
Görev oluşturmak da UAC penceresi açtırıyor. Bir kutucuğu işaretlemenin
bedeli yükseltme istemi olamaz; kalan tek yol `HKEY_CURRENT_USER`:

    HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run

Kullanıcıya özel, yükseltme istemiyor, oturum açıldığında çalışıyor.
Yazılan tek bir değer var; uygulamanın kayıt defterinde başka izi yok.

## Komut satırı tırnaklanıyor

Yazılan şey `"...\\pythonw.exe" "...\\yanmasa.py"`. Tırnak süs değil:
kullanıcı adında boşluk olabiliyor (`C:\\Users\\Ada Lovelace\\...`) ve
tırnaksız bir komutu Windows ilk boşluktan bölüp `C:\\Users\\Ada.exe`
aramaya çıkıyor. Sessizce başlamayan bir uygulamanın sebebi de görünmüyor.

`python.exe` değil `pythonw.exe`: her açılışta bir konsol penceresinin
açılıp kalması, açılışta başlamanın bütün anlamını götürürdü.

## "Açık" ne demek

`acik()` yalnızca değerin var olmasına bakmıyor, komutun **bu** kurulumun
`yanmasa.py`'sini gösterdiğine bakıyor. Depo taşındıysa kayıt defterindeki
satır hâlâ duruyor ama hiçbir şey başlatmıyor; orada işaretli bir kutu
göstermek yalan olurdu. İşaretsiz görünüyor, işaretlenince doğru yol
üzerine yazılıyor.

Tek bağımlılık `winreg` — standart kütüphanede ve yalnızca Windows'ta var,
uygulamanın geri kalanı gibi.
"""

from __future__ import annotations

import sys
import winreg
from pathlib import Path

#: Windows'un oturum açılışında çalıştırdığı, kullanıcıya özel anahtar.
#: `HKEY_LOCAL_MACHINE` altındaki eşi yönetici hakkı istiyor.
ANAHTAR = r"Software\Microsoft\Windows\CurrentVersion\Run"

#: Değerin adı. Kayıt defterini elle açan biri bunu görüp ne olduğunu
#: anlayabilmeli; `yanmasa` değil, uygulamanın adı.
DEGER = "Yan Masa"


def _pythonw() -> Path:
    """Uygulamayı çalıştıracak yorumlayıcı.

    `sys.executable` geliştirirken `python.exe` oluyor; açılışta konsol
    istemediğimiz için yanındaki `pythonw.exe` tercih ediliyor. Yoksa
    (gömülü ya da alışılmadık bir kurulum) çalışan yorumlayıcı yazılıyor:
    konsollu başlamak, hiç başlamamaktan iyi.
    """
    calisan = Path(sys.executable)
    yanindaki = calisan.with_name("pythonw.exe")
    return yanindaki if yanindaki.exists() else calisan


def _betik() -> Path:
    """`yanmasa.py`'nin mutlak yolu — bu modülün bir üst klasöründe."""
    return Path(__file__).resolve().parent.parent / "yanmasa.py"


def komut() -> str:
    """Kayıt defterine yazılan komut satırı, iki parçası da tırnaklı."""
    return f'"{_pythonw()}" "{_betik()}"'


def _yazili() -> str:
    """Kayıtlı değer; yoksa boş dize.

    Anahtar ya da değer yoksa bu bir hata değil, "kapalı" demek.
    """
    try:
        anahtar = winreg.OpenKey(winreg.HKEY_CURRENT_USER, ANAHTAR, 0,
                                 winreg.KEY_READ)
    except OSError:
        return ""
    try:
        deger, _tur = winreg.QueryValueEx(anahtar, DEGER)
    except OSError:
        return ""
    finally:
        winreg.CloseKey(anahtar)
    return str(deger)


def acik() -> bool:
    """Açılışta **bu** kurulum başlıyor mu.

    Karşılaştırma betik yoluyla yapılıyor, komutun tamamıyla değil:
    sanal ortam `python.exe`'den `pythonw.exe`'ye geçmiş olabilir ve o
    fark kutuyu işaretsiz göstermeyi hak etmiyor. Yollar Windows'ta
    büyük/küçük harfe duyarsız.
    """
    yazili = _yazili()
    return bool(yazili) and str(_betik()).casefold() in yazili.casefold()


def ac() -> None:
    """Değeri yazar. Zaten varsa üzerine yazılıyor — eski yol bayatsa
    düzeltmenin yolu bu."""
    anahtar = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, ANAHTAR, 0,
                                 winreg.KEY_SET_VALUE)
    try:
        winreg.SetValueEx(anahtar, DEGER, 0, winreg.REG_SZ, komut())
    finally:
        winreg.CloseKey(anahtar)


def kapat() -> None:
    """Değeri siler. Yoksa sessizce çıkıyor: istenen sonuç zaten bu."""
    try:
        anahtar = winreg.OpenKey(winreg.HKEY_CURRENT_USER, ANAHTAR, 0,
                                 winreg.KEY_SET_VALUE)
    except OSError:
        return
    try:
        winreg.DeleteValue(anahtar, DEGER)
    except OSError:
        pass
    finally:
        winreg.CloseKey(anahtar)
