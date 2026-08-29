"""Kuru koşu — ajan planlıyor, hiçbir şeye dokunmuyor.

Riskli bir işi ajana vermeden önce ne yapacağını görmenin bir yolu yoktu.
"Önce anlat, sonra yap" demek işe yaramıyor: model anlatıyor, sonra aynı
turda yapıyor. Kuru koşu bunu kod tarafında kesiyor — anlatı model
üretiyor, ama eylemin çalışmaması modelin iyi niyetine bağlı değil.

## Beyaz liste, kara liste değil

Hangi araçların engelleneceğini saymak yerine hangilerinin **serbest**
olduğu sayılıyor. Sebebi somut: bu depoya araç ekleniyor. Kara liste
olsaydı yeni bir aracın kuru koşuda sessizce çalışması varsayılan davranış
olurdu ve bunu fark etmenin yolu, o aracın bir şeyi bozmasını beklemekten
ibaret kalırdı. Beyaz listede yeni araç varsayılan olarak duruyor; yanlış
tarafa düşen bir araç en fazla "kuru koşu bunu da göstermedi" oluyor.

Aynı gerekçe onay kapısında da var: `Dispatcher.approve` bağlanmadığında
her riskli eylemi reddediyor.

## Neyi okumaya izin veriliyor

Ekran görüntüsü, dosya okuma, dizin listeleme, pencere ağacı. Planın
gerçek duruma bakarak yapılması gerekiyor: kapalı gözle üretilen bir plan,
plan değil tahmin. Bu araçların hiçbiri makinede bir şey değiştirmiyor.

`switch_display` de serbest: yalnızca hangi ekrana bakıldığını değiştiriyor
ve iki ekranlı bir planın ikincisini hiç görmemesi anlamsız olurdu.
"""

from __future__ import annotations

from typing import Any

#: Kuru koşuda çalışmasına izin verilen araçlar. Hepsi salt okunur.
#:
#: Listede olmayan her şey — yerleşik araçlar ve yetenekler dâhil —
#: duruyor. Yetenekler ayrıca hiçbir zaman listeye giremez: içleri
#: ajanın yazdığı Python kodu ve ne yaptıklarını ad üzerinden bilmenin
#: yolu yok.
SALT_OKUNUR = frozenset({
    # Bakmak
    "screenshot", "zoom", "cursor_position", "read_ui_tree",
    "switch_display", "list_apps", "wait",
    # Kullanıcıya not yazmak. Makinede hiçbir şey değiştirmiyor ve kuru
    # koşuda tam da istenen şey: ne yapacağını değil, neye dikkat
    # edeceğini söylüyor.
    "heads_up",
    # Dosya sistemi — okuma tarafı
    "read_file", "list_dir",
    # Belgeler — okuma tarafı
    "office_read", "office_history",
    # Terminal — yalnızca var olan çıktıyı okumak
    "terminal_read",
    # Yetenek ve düğme listesi; yazma tarafı değil
    "skill_list",
    # Uzak makine — okuma tarafı
    "remote_list", "remote_read",
    # Yan masa — bakmak
    "side_windows", "side_capture",
})


def serbest(arac: str) -> bool:
    """Bu araç kuru koşuda çalışabilir mi."""
    return arac in SALT_OKUNUR


def _cagri(arac: str, girdi: dict[str, Any], sinir: int = 160) -> str:
    """Çağrının okunur hâli. Modele geri dönüyor, kullanıcıya değil."""
    parcalar = []
    for ad, deger in girdi.items():
        metin = str(deger)
        if len(metin) > 60:
            metin = metin[:57] + "…"
        parcalar.append(f"{ad}={metin!r}")
    cagri = f"{arac}({', '.join(parcalar)})"
    return cagri if len(cagri) <= sinir else cagri[:sinir - 1] + "…"


def not_metni(arac: str, girdi: dict[str, Any]) -> str:
    """Engellenen çağrının modele dönen karşılığı.

    Hata olarak dönmüyor. Hata dönseydi ajan kendini düzeltmeye çalışır,
    aynı çağrıyı başka bir biçimde dener ve tur "neden çalışmıyor"
    döngüsüne girerdi — kuru koşunun istediği tam tersi: plan kesintisiz
    ilerlesin.
    """
    return (
        f"[dry run] {_cagri(arac, girdi)} was not executed. "
        f"Nothing was clicked, typed, written or launched.\n"
        f"Assume it would have worked and carry on planning. "
        f"When you are done, list every action you would take, in order, "
        f"and say what you are unsure about."
    )


#: Sistem promptuna eklenen bölüm. Modelin "yaptım" demesini engellemek
#: kod tarafında mümkün değil; bunu söyleyen tek yer prompt.
PROMPT = """

## Dry run is on

You are planning this turn, not doing it. Every action that would change
something — clicking, typing, running a command, writing a file, opening
an app — is intercepted before it runs and comes back as `[dry run]`.
Reading the screen, files and windows still works, so plan against what
is really there.

Two things follow:

- Do not say you did anything. You did not. Write in the conditional:
  "I would open X, then …".
- Finish with a numbered list of the actions you would take, in order,
  and name the one you are least sure about.
"""
