"""Ajanın kendi raporunu denetim kaydıyla karşılaştırır.

20.574 gerçek kodlama oturumluk analizde ajan–kullanıcı uyumsuzluğunun
oransal olarak **artan** biçimlerinden biri ajanın yapmadığı işi yaptım
demesi. Kötü tarafı hata olması değil — hatayı görürsün — sessiz olması:
"dosyayı kaydettim" cümlesi doğru görünüyor ve kimse gidip bakmıyor.

Burada yapılan şey basit: ajanın son cümlesinde bir **iddia** varsa, o
iddiayı destekleyecek bir araç sonucu gerçekten olmuş mu diye bakılıyor.

## Neden yanlış alarm vermiyor

Dört kademe var ve hepsi yanlış alarmı kısmak için:

1. İddia **kalıpla** aranıyor, anlamla değil. "kaydettim" iddia,
   "kaydedebilirim" değil.
2. Bir iddia yalnızca bu turda desteklenmiyorsa hemen işaretlenmiyor;
   oturumun tamamına bakılıyor. "Az önce yazdığım dosya" meşru bir cümle.
3. Soru ve olumsuz cümleler eleniyor: "kaydetmedim" bir iddia değil.
4. Kalıplar kelimeden üretiliyor, elle yazılmıyor — ilk denemede
   `çalıştırdım` yazıp `calistirdim`i kaçırmıştım. İnsan klavye düzenine
   göre ikisini de yazıyor ve yazıma takılan bir denetim aracı işe
   yaramaz.

## İki dil

Arayüz İngilizce, ajan İngilizce cevap veriyor; ama Türkçe kalıplar
duruyor, çünkü Türkçe bir talimata Türkçe cevap vermesi hâlâ olabilir ve
o cevabın denetimsiz kalması bu özelliğin sessizce kapanması olurdu.

İngilizce kelime seçimi Türkçeden dikkatli: bare `ran` alınmadı, çünkü
"I ran into an issue" bir komut çalıştırma iddiası değil. Onun yerine
`ran the`, `ran it` gibi ifadeler var. Aynı sebeple `started` yok — "I
started by reading the folder" bir uygulama açma iddiası değil.

Yanlış alarm bu özelliğin tek gerçek riski. Her cevabın altında haksız
bir uyarı çıksaydı insan uyarıyı okumayı bırakırdı — ve o noktada gerçek
olanı da kaçırırdı.
"""

from __future__ import annotations

import re

#: Türkçe harfleri ikizleriyle eşleyen tablo.
_IKIZ = {
    "ç": "[çc]", "c": "[cç]", "ş": "[şs]", "s": "[sş]",
    "ı": "[ıi]", "i": "[iı]", "ö": "[öo]", "o": "[oö]",
    "ü": "[üu]", "u": "[uü]", "ğ": "[ğg]", "g": "[gğ]",
}


def _esnek(kelime: str) -> str:
    """Kelimeyi Türkçe harf farklarını yok sayan bir kalıba çevirir."""
    return "".join(_IKIZ.get(h, re.escape(h)) for h in kelime.lower())


def _kalip(*kelimeler: str) -> re.Pattern[str]:
    govde = "|".join(_esnek(k) for k in kelimeler)
    return re.compile(r"\b(" + govde + r")\b", re.IGNORECASE)


#: İddia ailesi -> (cümle kalıbı, iddiayı destekleyen araçlar).
#:
#: Kelimeler görülen geçmiş zamanda. Gelecek ve yeterlilik kipleri iddia
#: değil, o yüzden kelime sınırı iki yandan kapalı: "kaydedebilirim"
#: eşleşmiyor.
AILELER: dict[str, tuple[re.Pattern[str], frozenset[str]]] = {
    "dosya": (
        _kalip("yazdım", "kaydettim", "oluşturdum", "güncelledim",
               "kaydedildi", "oluşturuldu", "yazıldı", "sildim",
               "wrote", "saved", "created", "updated", "deleted",
               "was written", "was saved", "was created"),
        frozenset({
            "write_file", "write_files", "edit_file",
            "office_save", "office_edit", "remote_write",
        }),
    ),
    "kabuk": (
        _kalip("çalıştırdım", "kurdum", "derledim", "çalıştırıldı",
               "executed", "installed", "compiled",
               "ran the", "ran it", "ran a", "ran that"),
        frozenset({"run_shell", "terminal_send", "remote_run",
                   "terminal_open"}),
    ),
    "uygulama": (
        _kalip("açtım", "başlattım", "tıkladım", "açıldı", "tıklandı",
               "opened", "launched", "clicked"),
        frozenset({
            "launch_app", "left_click", "double_click", "right_click",
            "side_launch", "side_act", "terminal_open", "office_open",
        }),
    ),
    "sunucu": (
        _kalip("sunucuya", "sunucuda", "sunucudan",
               "on the server", "to the server", "from the server",
               "on the remote"),
        frozenset({"remote_connect", "remote_run", "remote_write",
                   "remote_read", "remote_list"}),
    ),
}

#: İddiayı iptal eden ekler: "kaydetmedim", "yazamadım", "açamadım".
OLUMSUZ = re.compile(
    r"\w*(med[iı]m|mad[ıi]m|emedim|amad[ıi]m|eyemedim|ayamad[ıi]m)\b",
    re.IGNORECASE,
)

#: Soru: ya işaret ya da ayrı yazılan soru eki. Ek ayrı bir kelime
#: olduğu için sınırlar şart — "yazdım" içindeki harfler eşleşmemeli.
SORU = re.compile(r"\?|\bm[ıiuü]\b", re.IGNORECASE)

#: İnsana gösterilen ad.
ETIKET = {
    "dosya": "writing a file",
    "kabuk": "running a command",
    "uygulama": "opening an app or clicking",
    "sunucu": "a server operation",
}


def _cumleler(metin: str) -> list[str]:
    """Cümleler, noktalama **korunarak**.

    Ayırıcıyı atan bir bölme soru işaretini de atıyordu ve "yazdım mı?"
    iddia sayılıyordu.
    """
    parcalar = re.split(r"([.!?\n]+)", metin)
    cikti = []
    for i in range(0, len(parcalar), 2):
        govde = parcalar[i]
        ek = parcalar[i + 1] if i + 1 < len(parcalar) else ""
        if govde.strip():
            cikti.append((govde + ek).strip())
    return cikti


#: Cümle içi sınırlar. Olumsuzluk bunların ötesine geçmiyor.
YAN_CUMLE = re.compile(r",|\b(ama|fakat|ancak|l[âa]kin|yaln[ıi]z)\b",
                       re.IGNORECASE)


def iddialar(metin: str) -> set[str]:
    """Metindeki iddia aileleri.

    Yan cümle cümle bakılıyor, cümle cümle değil. "Dosyayı yazamadım ama
    komutu çalıştırdım" tek cümle ve olumsuzluk yalnızca ilk yarıya ait;
    cümlenin tamamına baksaydım ikinci iddia da elenirdi. İlk hâli tam
    olarak bunu yapıyordu.

    Soru ise cümlenin tamamını eliyor: "Dosyayı yazdım, doğru mu?" soru
    işaretini sonda taşıyor ama baştaki iddiayı da soruya çeviriyor.
    """
    bulunan: set[str] = set()
    for cumle in _cumleler(metin):
        if SORU.search(cumle):
            continue
        for parca in YAN_CUMLE.split(cumle):
            if not parca or OLUMSUZ.search(parca):
                continue
            for ad, (desen, _) in AILELER.items():
                if desen.search(parca):
                    bulunan.add(ad)
    return bulunan


def desteksiz(metin: str, tur_araclari: set[str],
              oturum_araclari: set[str] | None = None) -> list[str]:
    """Kayıtta karşılığı olmayan iddialar.

    `tur_araclari` bu turda **başarıyla** çalışmış araçlar. Turda karşılık
    yoksa oturumun tamamına bakılıyor; oradan da destek gelmiyorsa iddia
    desteksiz sayılıyor.
    """
    oturum = oturum_araclari if oturum_araclari is not None else set()
    eksik: list[str] = []
    for ad in sorted(iddialar(metin)):
        _, kabul = AILELER[ad]
        if tur_araclari & kabul or oturum & kabul:
            continue
        eksik.append(ad)
    return eksik


def not_metni(eksik: list[str]) -> str:
    """Arayüzde cevabın altına düşen satır.

    Suçlama değil, kayıt: kanıtın nerede olmadığını söylüyor ve kararı
    okuyana bırakıyor. "Ajan yalan söyledi" demek, kalıp eşleşmesinin
    taşıyabileceğinden fazla iddia olurdu.
    """
    if not eksik:
        return ""
    adlar = ", ".join(ETIKET.get(ad, ad) for ad in eksik)
    return f"No record of {adlar} in this session."
