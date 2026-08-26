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
        "Discord'u klavyeyle sürer. islem: ac (aç ve öne getir), git (Ctrl+K "
        "ile sunucu/kanal/kişiye geç), yaz (mesaj kutusuna yaz, GÖNDERMEZ), "
        "gonder (yazılanı gönderir, onay ister), sustur, sagirlastir, "
        "sesten_ayril, kanal_yukari, kanal_asagi, kapat_kutu. "
        "Gezindikten sonra mutlaka ekran görüntüsü al ve doğru yerde "
        "olduğunu doğrula — hızlı geçiş kutusu benzer adları karıştırabilir."
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
            "description": "git için: sunucu, kanal ya da kişi adı",
        },
        "metin": {"type": "string", "description": "yaz için: mesaj metni"},
    },
    "zorunlu": ["islem"],
    "onay": False,
}

KOMUT = {
    "ad": "dc",
    "aciklama": "Discord'u aç ve ekrana bak",
    "talimat": (
        "discord yeteneğiyle Discord'u aç, ekran görüntüsü al ve ne "
        "olduğunu özetle. Hiçbir şey gönderme."
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
        return "Ekran belirlenemedi; ekran görüntüsü almadan önce doğrula."
    ortam.arac("switch_display", index=index)
    return f"Aktif ekran {index} yapıldı (Discord orada)."


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
                return "Discord öne getirildi. " + _ekrana_gec(ortam)
            return (
                "Discord açık ama öne getirilemedi (tam ekran bir uygulama "
                "önde olabilir). Ekran görüntüsü al ve pencereye tıkla."
            )

        # Discord PATH'te değil: Squirrel ile kuruluyor ve gerçek exe sürüm
        # numaralı bir klasörde. Kararlı olan başlatıcı stub'ı.
        import os

        stub = os.path.join(
            os.environ.get("LOCALAPPDATA", ""), "Discord", "Update.exe"
        )
        if not os.path.exists(stub):
            return (
                f"Discord kurulu değil ya da bulunamadı ({stub}). "
                f"Elle açıp tekrar dene."
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
            return "Discord başlatıldı ve öne getirildi. " + _ekrana_gec(ortam)
        return (
            "Discord başlatıldı ama pencere öne gelmedi. Ekran görüntüsü al "
            "ve pencereye tıkla; ön planda olmadan tuşlar başka uygulamaya "
            "gider."
        )

    # Buradan sonraki her şey tuş gönderiyor. Yanlış pencereye tuş
    # göndermek, bir başkasının sohbetine yazmak demek — önce durup bak.
    if not _odakta_mi(ortam):
        # Bir kez öne getirmeyi dene; kullanıcı arada başka pencereye
        # tıklamış olabiliyor ve her seferinde ajana geri dönmek pahalı.
        if not ortam.pencereye_gec(PENCERE):
            return (
                "Discord ön planda değil ve öne getirilemedi; hiçbir tuş "
                "gönderilmedi. Ekran görüntüsü al ve pencereye tıkla."
            )

    if islem == "git":
        hedef = str(girdi.get("hedef", "")).strip()
        if not hedef:
            return "git için hedef gerekli (sunucu, kanal ya da kişi adı)."
        ortam.arac("key", text="ctrl+k")
        ortam.bekle(BEKLE)
        ortam.arac("type", text=hedef)
        # Liste güncellensin diye bekle; erken Enter önceki sonuca gider.
        ortam.bekle(ARAMA_BEKLE)
        ortam.arac("key", text="Return")
        ortam.bekle(BEKLE)
        return (
            f"Hızlı geçişte {hedef!r} arandı ve ilk sonuca gidildi. "
            f"Ekran görüntüsü al ve doğru yerde olduğunu doğrula — benzer "
            f"adlar karışabilir."
        )

    if islem == "yaz":
        metin = str(girdi.get("metin", ""))
        if not metin.strip():
            return "yaz için metin gerekli."
        # Satır sonu Enter'a dönüşüp mesajı erkenden gönderirdi.
        if "\n" in metin:
            return (
                "Metinde satır sonu var; Discord'da Enter mesajı gönderir. "
                "Tek satır yaz ya da satırları ayrı ayrı gönder."
            )
        ortam.arac("type", text=metin)
        ortam.bekle(0.3)
        return (
            f"Mesaj kutusuna yazıldı ({len(metin)} karakter), "
            f"GÖNDERİLMEDİ. Ekran görüntüsüyle doğru kişide olduğunu "
            f"doğrula, sonra islem='gonder' çağır."
        )

    if islem == "gonder":
        # Tek geri alınamaz adım. Kapı burada.
        if not ortam.onay(
            "discord gonder",
            "Mesaj kutusundaki metin Discord'da gönderilecek.",
            "Başka birine senin adına mesaj gidiyor",
        ):
            return "Berkay göndermeyi reddetti. Mesaj kutusunda duruyor."
        ortam.arac("key", text="Return")
        ortam.bekle(0.4)
        return "Gönderildi. Ekran görüntüsüyle gittiğini doğrula."

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
        return f"{islem} yapıldı ({tuslar[islem]})."

    if islem == "sesten_ayril":
        # Ayrılma düğmesinin kısayolu yok; ajanın görüp tıklaması gerekiyor.
        return (
            "Sesli kanaldan ayrılmanın klavye kısayolu yok. Ekran görüntüsü "
            "al, sol altta ses panelindeki ayrılma düğmesini bul ve tıkla."
        )

    return (
        f"{islem!r} diye bir işlem yok. Olanlar: ac, git, yaz, gonder, "
        f"sustur, sagirlastir, sesten_ayril, kanal_yukari, kanal_asagi, "
        f"kapat_kutu."
    )
