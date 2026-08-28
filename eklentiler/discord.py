"""Discord — klavye ve fareyle, senin bilgisayarında.

Bot API'si kullanılmıyor. Ajan Discord'u senin gördüğün gibi görüyor ve
senin bastığın tuşlara basıyor; bu, uygulamanın geri kalanıyla aynı yol.

**Neden klavye, neden ekran okuma değil:** ölçüldü. Discord Electron ve
erişilebilirlik ağacı 33 düğüm döndürüyor — hepsi boş grup, tek satır metin
yok. Yani `read_ui_tree` burada işe yaramıyor, gören göz ekran görüntüsü.

Ekran görüntüsü pahalı ve yavaş olduğu için bu eklenti gezinmeyi klavyeye
yıkıyor. `Ctrl+K` hızlı geçiş kutusu bir sunucuya, kanala ya da kişiye adını
yazarak gitmeyi sağlıyor: fareyle beş tıklama gereken iş tek adıma iniyor.
Ajanın gözü yalnızca *doğrulama* için gerekiyor — doğru kişide miyiz, mesaj
gitti mi.

**Mesaj göndermek her zaman onay istiyor.** Gezinmek, okumak, susmak
zararsız; başka birine mesaj göndermek geri alınamaz ve senin adına
konuşmak demek. `yaz` metni kutuya koyuyor ama **göndermiyor**; ajan
ekrandan doğru yerde olduğunu doğruluyor, sonra `gonder` çağırıyor ve o
adımda sana soruluyor.
"""

ARAC = {
    "ad": "discord",
    "aciklama": (
        "Drives Discord from the keyboard. islem: ac (open and bring to "
        "the front), git (jump to a server/channel/person with Ctrl+K), "
        "yaz (type into the message box, DOES NOT SEND), gonder (sends "
        "what was typed, asks for approval), sustur, sagirlastir, "
        "sesten_ayril, kanal_yukari, kanal_asagi, kapat_kutu. "
        "After navigating, always take a screenshot and verify you are in "
        "the right place — the quick switcher confuses similar names."
    ),
    "girdi": {
        "islem": {
            "type": "string",
            "description": (
                "ac, git, yaz, gonder, sustur, sagirlastir, sesten_ayril, "
                "kanal_yukari, kanal_asagi, kapat_kutu"
            ),
        },
        "hedef": {
            "type": "string",
            "description": "for git: a server, channel or person name",
        },
        "metin": {"type": "string", "description": "for yaz: the message text"},
    },
    "zorunlu": ["islem"],
    "onay": False,
}

KOMUT = {
    "ad": "dc",
    "aciklama": "Open Discord and look at the screen",
    "talimat": (
        "Open Discord with the discord skill, take a screenshot and "
        "summarise what is there. Do not send anything."
    ),
}

#: Discord açılırken ve pencere değişirken beklenecek süre. Ölçülerek
#: bulundu: 0.4 saniyede hızlı geçiş kutusu bazen henüz açılmamış oluyor
#: ve tuşlar arkadaki kanala düşüyor.
BEKLE = 0.8

#: Hızlı geçiş kutusunun arama sonucunu getirmesi. Yazdıktan hemen sonra
#: Enter'a basmak, liste henüz güncellenmediği için **önceki** sonuca
#: gidiyor — bu, yanlış kişiye mesaj yazmanın en kolay yolu.
ARAMA_BEKLE = 1.2

PENCERE = "Discord"


def _odakta_mi(ortam) -> bool:
    """Discord ön planda mı. Değilse tuşlar başka bir uygulamaya gider."""
    return PENCERE.lower() in (ortam.on_pencere() or "").lower()


def _ekrana_gec(ortam) -> str:
    """Ajanı Discord'un bulunduğu monitöre geçirir.

    Ekran görüntüsü aktif ekrandan alınıyor. Discord ikinci monitördeyken
    ajan birinciye bakıyor, Discord'u hiç göremiyor ve olmayan bir şeyi
    aramaya başlıyor. Bu gerçekten oldu — pencere sol kenarı 1912'de
    başladığı için birinci ekranda sanıldı.
    """
    index = ortam.pencerenin_ekrani(PENCERE)
    if index is None:
        return "Could not tell which display; verify before taking a screenshot."
    ortam.arac("switch_display", index=index)
    return f"The active display is now {index} (that is where Discord is)."


def calistir(girdi, ortam):
    islem = str(girdi.get("islem", "")).strip()

    if islem == "ac":
        # Pencere varsa **asla başlatma**. Ölçüldü: zaten açık Discord için
        # başlatma yolu 25 saniye sürüyordu — `launch_app` yeni bir pencere
        # bekleyip 10 saniye zaman aşımına düşüyor, üstüne eklentinin kendi
        # beklemeleri biniyordu. Açık bir uygulamayı öne getirmek 50 ms.
        acik = ortam.pencerenin_ekrani(PENCERE) is not None
        if acik:
            if ortam.pencereye_gec(PENCERE, timeout=2.0):
                return "Discord was brought to the front. " + _ekrana_gec(ortam)
            return (
                "Discord is open but could not be brought to the front (a "
                "full-screen app may be in front). Take a screenshot and click the window."
            )

        # Discord PATH'te değil: Squirrel ile kuruluyor ve gerçek exe sürüm
        # numaralı bir klasörde. Kararlı olan başlatıcı stub'ı.
        import os

        stub = os.path.join(
            os.environ.get("LOCALAPPDATA", ""), "Discord", "Update.exe"
        )
        if not os.path.exists(stub):
            return (
                f"Discord is not installed or was not found ({stub}). "
                f"Open it by hand and try again."
            )
        ortam.arac("launch_app", target=stub,
                   arguments="--processStart Discord.exe")
        # Sabit bekleme yerine yokla: Discord soğuk açılışta 8 saniye,
        # sıcakta 2 saniye sürüyor ve ikisine de aynı süreyi harcamak
        # ya erken davranmak ya da boşuna beklemek demek.
        for _ in range(20):
            if ortam.pencerenin_ekrani(PENCERE) is not None:
                break
            ortam.bekle(0.5)
        if ortam.pencereye_gec(PENCERE, timeout=3.0):
            return "Discord was launched and brought to the front. " + _ekrana_gec(ortam)
        return (
            "Discord was launched but its window did not come forward. Take a "
            "screenshot and click the window; without focus the keys go to "
            "gider."
        )

    # Buradan sonraki her şey tuş gönderiyor. Yanlış pencereye tuş
    # göndermek, bir başkasının sohbetine yazmak demek — önce durup bak.
    if not _odakta_mi(ortam):
        # Bir kez öne getirmeyi dene; kullanıcı arada başka pencereye
        # tıklamış olabiliyor ve her seferinde ajana geri dönmek pahalı.
        if not ortam.pencereye_gec(PENCERE):
            return (
                "Discord is not in the foreground and could not be brought there; "
                "no key was sent. Take a screenshot and click the window."
            )

    if islem == "git":
        hedef = str(girdi.get("hedef", "")).strip()
        if not hedef:
            return "git needs a target (a server, channel or person name)."
        ortam.arac("key", text="ctrl+k")
        ortam.bekle(BEKLE)
        ortam.arac("type", text=hedef)
        # Liste güncellensin diye bekle; erken Enter önceki sonuca gider.
        ortam.bekle(ARAMA_BEKLE)
        ortam.arac("key", text="Return")
        ortam.bekle(BEKLE)
        return (
            f"Searched the quick switcher for {hedef!r} and went to the first "
            f"result. Take a screenshot and verify you are in the right place — "
            f"similar names get confused."
        )

    if islem == "yaz":
        metin = str(girdi.get("metin", ""))
        if not metin.strip():
            return "yaz needs text."
        # Satır sonu Enter'a dönüşüp mesajı erkenden gönderirdi.
        if "\n" in metin:
            return (
                "The text contains a line break, and Enter sends the message in "
                "Discord. Write a single line, or send the lines one by one."
            )
        ortam.arac("type", text=metin)
        ortam.bekle(0.3)
        return (
            f"Typed into the message box ({len(metin)} characters), "
            f"NOT SENT. Verify with a screenshot that you are on the right "
            f"conversation, then call islem='gonder'."
        )

    if islem == "gonder":
        # Tek geri alınamaz adım. Kapı burada.
        if not ortam.onay(
            "discord gonder",
            "The text in the message box will be sent in Discord.",
            "a message goes to someone else in your name",
        ):
            return "The user declined sending it. It is still in the message box."
        ortam.arac("key", text="Return")
        ortam.bekle(0.4)
        return "Sent. Verify with a screenshot that it went."

    tuslar = {
        "sustur": "ctrl+shift+m",
        "sagirlastir": "ctrl+shift+d",
        "kanal_yukari": "alt+Up",
        "kanal_asagi": "alt+Down",
        "kapat_kutu": "Escape",
    }
    if islem in tuslar:
        ortam.arac("key", text=tuslar[islem])
        ortam.bekle(0.3)
        return f"{islem} done ({tuslar[islem]})."

    if islem == "sesten_ayril":
        # Ayrılma düğmesinin kısayolu yok; ajanın görüp tıklaması gerekiyor.
        return (
            "There is no keyboard shortcut for leaving a voice channel. Take a "
            "screenshot, find the disconnect button in the voice panel at the bottom left and click it."
        )

    return (
        f"There is no operation called {islem!r}. The valid ones are: ac, git, yaz, gonder, "
        f"sustur, sagirlastir, sesten_ayril, kanal_yukari, kanal_asagi, "
        f"kapat_kutu."
    )
