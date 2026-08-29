"""Model bir dosya yazarken içeriği parça parça çıkarmak.

Ajan `write_file` çağırdığında dosya bir anda beliriyordu: arayüz olayı
ancak araç çalıştıktan sonra görüyor. Oysa model o içeriği **akıtarak**
üretiyor — `input_json_delta` olayları araç girdisinin JSON'unu harf harf
getiriyor. Buradaki iş o yarım JSON'dan yazılmakta olan metni çıkarmak.

Yani ekranda gördüğün yazılma bir animasyon değil: model o an ne
yazıyorsa o. Dosya diske hâlâ tek seferde yazılıyor; canlı olan modelin
üretimi.

## Neden elle bir tarayıcı

`json.loads` yarım bir metni reddediyor ve elimizdeki her zaman yarım.
Kapanmamış tırnağı tahmin edip tamamlamak da çalışmıyor: içerik kendi
içinde tırnak ve ters eğik çizgi taşıyor, kaçış dizisinin ortasında
kesilebiliyor (`\\u00e7`'nin ilk üç karakteri gelmiş olabiliyor).

Tarayıcı üst düzey nesneyi anahtar anahtar geziyor ve dizeleri kaçış
kaçış çözüyor. Bir dize yarım kalırsa çözülen kadarı veriliyor —
gösterilecek olan da tam o.

## Neyi taşımıyor

`write_files` bir dizi taşıyor (`files: [{path, content}, ...]`) ve
canlı gösterime girmiyor: dizinin içinde hangi dosyanın yazıldığını
anlamak, tarayıcıyı iki kat karmaşık yapardı ve o araç tek seferde
küçük dosyalar yazmak için kullanılıyor. Yazıldıktan sonra kod sayfası
zaten hepsini gösteriyor.
"""

from __future__ import annotations

#: Araçtan, canlı gösterilecek metni taşıyan alana.
KOD_ALANI = {
    "write_file": "content",
    "edit_file": "new",
    "skill_write": "code",
}

#: Dosya yolunu taşıyan alan adayları, sırayla.
YOL_ALANLARI = ("path", "name")

_KACIS = {
    '"': '"', "\\": "\\", "/": "/", "b": "\b",
    "f": "\f", "n": "\n", "r": "\r", "t": "\t",
}


def _bosluk_atla(s: str, i: int) -> int:
    while i < len(s) and s[i] in " \t\r\n":
        i += 1
    return i


def _dize_oku(s: str, i: int) -> tuple[str, int, bool]:
    """`s[i]` açılış tırnağı. `(çözülen, sonraki_indeks, tamam_mı)`.

    Yarım kalırsa çözülebilen kadarı dönüyor ve `tamam` `False`.
    """
    i += 1
    parcalar: list[str] = []
    while i < len(s):
        ch = s[i]
        if ch == '"':
            return "".join(parcalar), i + 1, True
        if ch != "\\":
            parcalar.append(ch)
            i += 1
            continue
        # Kaçış dizisi. Yarım gelmiş olabilir; o zaman burada duruyoruz.
        if i + 1 >= len(s):
            break
        nxt = s[i + 1]
        if nxt == "u":
            if i + 6 > len(s):
                break
            try:
                parcalar.append(chr(int(s[i + 2:i + 6], 16)))
            except ValueError:
                # Bozuk bir kaçış: olduğu gibi bırakmak, yanlış bir
                # karakter uydurmaktan iyi.
                parcalar.append(s[i:i + 6])
            i += 6
            continue
        parcalar.append(_KACIS.get(nxt, nxt))
        i += 2
    return "".join(parcalar), len(s), False


def _deger_atla(s: str, i: int) -> int | None:
    """Değeri atlar. Değer yarımsa `None`."""
    i = _bosluk_atla(s, i)
    if i >= len(s):
        return None
    ch = s[i]
    if ch == '"':
        _metin, son, tamam = _dize_oku(s, i)
        return son if tamam else None
    if ch in "[{":
        kapanis = {"[": "]", "{": "}"}[ch]
        derinlik = 0
        while i < len(s):
            c = s[i]
            if c == '"':
                _m, i, tamam = _dize_oku(s, i)
                if not tamam:
                    return None
                continue
            if c in "[{":
                derinlik += 1
            elif c in "]}":
                derinlik -= 1
                if derinlik == 0:
                    return i + 1
                if derinlik < 0:
                    return None
            i += 1
        return None
    # Sayı, true, false, null: bir ayraca kadar.
    son = i
    while son < len(s) and s[son] not in ",}] \t\r\n":
        son += 1
    # Tamponun sonuna dayandıysak değer daha uzayabilir.
    return son if son < len(s) else None


def coz(ham: str) -> tuple[dict[str, str], str, str]:
    """Yarım JSON nesnesini çözer.

    Döner: tamamlanmış dize alanları, yarım kalan alanın adı, o alanın
    şu ana kadar çözülen değeri. Yarım kalan yoksa ikisi de boş.
    """
    tam: dict[str, str] = {}
    i = _bosluk_atla(ham, 0)
    if i >= len(ham) or ham[i] != "{":
        return tam, "", ""
    i += 1
    while True:
        i = _bosluk_atla(ham, i)
        if i >= len(ham) or ham[i] == "}":
            return tam, "", ""
        if ham[i] != '"':
            return tam, "", ""
        anahtar, i, tamam = _dize_oku(ham, i)
        if not tamam:
            return tam, "", ""
        i = _bosluk_atla(ham, i)
        if i >= len(ham) or ham[i] != ":":
            return tam, "", ""
        i = _bosluk_atla(ham, i + 1)
        if i >= len(ham):
            return tam, "", ""
        if ham[i] == '"':
            deger, son, bitti = _dize_oku(ham, i)
            if not bitti:
                return tam, anahtar, deger
            tam[anahtar] = deger
            i = son
        else:
            son = _deger_atla(ham, i)
            if son is None:
                return tam, "", ""
            i = son
        i = _bosluk_atla(ham, i)
        if i < len(ham) and ham[i] == ",":
            i += 1


class AkanKod:
    """Bir araç çağrısının girdisi akarken yazılmakta olan metni verir.

    Kullanımı: araç bloğu başlayınca `basla(ad)`, her parçada `besle()`,
    blok bitince `dur()`. `besle` gösterilecek bir şey değiştiyse `True`
    dönüyor — her parçada arayüze sinyal göndermek, saniyede yüzlerce
    çizim demek olurdu.
    """

    def __init__(self) -> None:
        self.arac = ""
        self._ham = ""
        self.yol = ""
        self.metin = ""

    @property
    def etkin(self) -> bool:
        """Bu araç canlı gösterime giriyor mu."""
        return self.arac in KOD_ALANI

    def basla(self, arac: str) -> None:
        self.arac = arac or ""
        self._ham = ""
        self.yol = ""
        self.metin = ""

    def dur(self) -> None:
        self.basla("")

    def besle(self, parca: str) -> bool:
        if not self.etkin or not parca:
            return False
        self._ham += parca
        tam, yarim_ad, yarim_deger = coz(self._ham)

        yol = ""
        for ad in YOL_ALANLARI:
            if tam.get(ad):
                yol = tam[ad]
                break
        alan = KOD_ALANI[self.arac]
        metin = tam.get(alan, "")
        if yarim_ad == alan:
            metin = yarim_deger
        elif not metin and yarim_ad in YOL_ALANLARI and not yol:
            # Yol daha yazılıyor; adı yarım göstermek yanıp sönen bir
            # başlık demek olurdu.
            yol = ""

        if yol == self.yol and metin == self.metin:
            return False
        self.yol, self.metin = yol, metin
        return True
