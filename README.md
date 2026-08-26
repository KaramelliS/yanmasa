# Ajan

Windows'u yöneten bir bilgisayar kontrol ajanı. Ekranı Claude Opus 5'in
`computer_toolset_20260801` araç setiyle görüyor, fareyi ve klavyeyi ham Win32
`SendInput` ile sürüyor.

Yerel bir Qt (PySide6) masaüstü uygulaması — web katmanı, tarayıcı motoru ya
da HTTP köprüsü yok. Görsel dil Windows 11 Fluent; renkler ve tema kayıt
defterinden okunuyor, sabit palet yok.

Ayakta olanlar: yakalama, girdi, ajan döngüsü, UIA yan kanalı, dosya araçları,
kalıcı terminal oturumları, güvenlik kapısı, acil durdurma. Ses ve arayüz yok — "Ne eksik" bölümüne bak.

## Neden bu mimari

Ekranı okuyan modeli biz yazmıyoruz. Claude'un computer araç seti GA ve
`claude-opus-5` destekliyor; `screenshot`, `zoom`, `left_click`, `type`, `key`
gibi 17 üye aracı var ve koordinatları ekran görüntüsü piksel uzayında,
**1:1**. Bize düşen Windows tarafındaki el: kareyi yakalamak ve modelin
söylediği piksele gerçekten tıklamak.

Bu makinede iki adet 1920×1080 monitör var, yani sanal masaüstü 3840×1080.
Uzun kenar modelin 2576 px sınırını aştığı için **monitör başına** yakalıyoruz;
her kare 1920×1080, küçültme yok, koordinat matematiği yok.

Yerel bir görüntü modeli seçenek değil: bu makinedeki RX 560 (4 GB) üzerinde
OmniParser/Qwen-VL sınıfı bir model çalışmıyor.

## Arayüz

```
.venv/Scripts/pythonw.exe ajan.py
```

İki pencere açılır:

- **Ajan penceresi** — panelleri barındırır: tablo, yazı belgesi, kod,
  terminal ve değişiklik listesi. Her panel bir `QDockWidget`; başlığına çift
  tıklayınca gerçek, ayrı bir Windows penceresine çıkar ve ikinci ekrana
  atılabilir. Bu Qt'nin kendi davranışı, taklit edilmiş bir sürükleme değil.
- **Komut çubuğu** — ajanla konuşulan yer burası, ana pencere değil.
  Çerçevesiz, hep üstte, ekranın köşesinde yüzen bir çubuk. Üç parçası var:
  mikrofon, **yazı alanı** (ses kullanılamıyorsa tek çalışan giriş yolu) ve
  ajanın o an yaptığı işi gösteren **önizleme karesi** — eylem, hedef,
  gerekçe ve gerçek bir küçük resim. Sürüklenip taşınır, konumu
  `~/.ajan/bar.json` içinde kalır.

Fluent'e uymanın pratikteki anlamı `app/fluent.py`'de: renkler sistemden
okunuyor. Temayı açığa alırsan uygulama açılır, vurgu rengini değiştirirsen
uygulama onu alır. Sabit bir palet yazmak, Fluent olduğunu iddia edip tek
gerçek kuralını çiğnemek olurdu.

## Kurulum

Proje kendi başına duruyor: dizini nereye kopyalarsan orada çalışıyor,
hiçbir çalışma alanı yöneticisine ya da dış depoya bağlı değil.

```
py -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Anahtarlar `.env` dosyasına girer. `.env` `.gitignore`'da — repoya asla
girmemeli. `ANTHROPIC_API_KEY` yoksa uygulama açılıyor ama çubukta
"Ajan kurulamadı" yazıyor; sessizce yarım çalışmıyor.

Ajanın kendine yazdığı yetenekler ve düğmeler depoda değil,
`~/.ajan/` altında: kendi yazdığı kod uygulamanın kaynağına karışmamalı ve
bir güncelleme onları silmemeli. `AJAN_STATE_DIR` ile taşınabiliyor.

## Çalıştırma ve doğrulama

```
.venv/Scripts/pythonw.exe ajan.py                          # uygulama
.venv/Scripts/python.exe -m pytest tests -q                # saf mantık, 110 test
.venv/Scripts/python.exe scripts/check_phase1.py           # yakalama, ekrana dokunmaz
.venv/Scripts/python.exe scripts/check_phase1.py --input   # Notepad'e Türkçe yazar
.venv/Scripts/python.exe scripts/ajan.py                   # ajan, etkileşimli
.venv/Scripts/python.exe scripts/ajan.py "Not Defteri'ni aç"
```

`--input` ve `ajan.py` gerçekten fareyi ve klavyeyi sürüyor. Her an **Esc'ye
üç kez** basarak durdurabilirsin.

## Ajanın araçları

Computer araç seti fare ve klavyeyi veriyor. Üstüne on iki özel araç var:

| Araç | Ne için |
| --- | --- |
| `read_ui_tree` | Pencerenin denetimlerini tıklama noktalarıyla metin olarak verir. Ekran görüntüsünden çok daha ucuz ve koordinatları tahmin değil ölçüm. |
| `launch_app` | Uygulamayı doğrudan başlatır. Başlat menüsünde tıklatmak dört-beş tur sürüyordu. |
| `run_shell` | Tek atışlık PowerShell. Toplu dosya işleri ve sorgular. |
| `write_file` `read_file` `edit_file` `list_dir` | Dosya işleri. Her yerde UTF-8 — Windows'un cp1254 varsayılanı Türkçe metni sessizce bozuyor. |
| `terminal_open` `terminal_send` `terminal_read` `terminal_close` | Kalıcı terminal oturumları. |
| `office_open` `office_read` `office_edit` `office_save` `office_history` `office_close` | Kendi ofisimiz — gerçek .xlsx/.docx, Office kurulu olmadan. |
| `switch_display` | Hangi ekranda çalışılacağı. |

Sistem promptu ajana bir **araç merdiveni** veriyor: dosya işi için dosya
araçları, toplu iş için kabuk, etkileşimli program için terminal, uygulama
açmak için `launch_app`, bir şey bulmak için `read_ui_tree`, geriye kalan
her şey için ekran görüntüsü ve fare. Bir dosyayı Not Defteri'nde açıp
yazmak teknik olarak mümkün ama en pahalı yol.

Düşünme bütçesi adıma göre değişiyor: ilk adım `high` — yaklaşım orada
seçiliyor ve yanlış yaklaşım sonraki on adımı çöpe atar. Sonrası `medium`.
Bir eylem hata verdiyse ajan tıkanmış demektir, orada tekrar `high`.

## Kendi ofisimiz

Bu makinede Microsoft Office kurulu değil ve gerekmiyor. `office_*` araçları
gerçek `.xlsx` ve `.docx` üretiyor — Berkay dosyayı birine yolladığında karşı
taraf Excel'de açıyor. Fark dosya biçiminde değil, ajanın belgeye nasıl
eriştiğinde: bir arayüzü sürmek yerine hücre ve paragraf modeline doğrudan
yazıyor.

**Her düzenleme gerekçe taşır ve bu zorunlu bir alan.** `office_edit`
çağrısında `why` verilmezse değişiklik yapılmaz. İsteğe bağlı olsaydı model
çoğu zaman atlardı ve defter yarı dolu kalırdı; yarı dolu bir gerekçe defteri
hiç olmamasından kötüdür, çünkü güvenilir sanılır. `office_history` defteri
gösteriyor ve son N değişikliği geri alabiliyor — her kayıt önceki değeri de
tuttuğu için geri alma veri kaybetmiyor.

### Formüller

Formüller hesaplanıyor. Bu bir hata yüzünden yazıldı: ajan bir bütçe
tablosuna toplam formülü yazdı, sonra sonucun **21.290** olacağını söyledi.
Doğrusu 20.990'dı. Dosya doğruydu; yanlış olan ajanın kafadan yaptığı
toplama.

Şimdi `office_read` formül hücresini `=SUM(B1:B5) → 20990` diye gösteriyor
ve sistem promptu "ok işaretinden sonrakini kullan, kendin hesaplama" diyor.
Panelde de Excel'deki gibi: hücrede sonuç, formül çubuğunda formül.
Hesaplanamayan formül kırmızı kalıyor ve "N formül hesaplanamadı" yazıyor —
sıfır gösterip sonucu biliyormuş gibi yapmıyor.

Motor `formulas` 1.3.4. Pahalı olduğu için tabloda hiç formül yoksa hiç
çağrılmıyor, varsa defterdeki değişiklik sayısına göre önbelleğe alınıyor.

## Kendine yetenek yazmak

Ajan kendi araçlarını yazabiliyor. Bir işi ikinci kez aynı adımlarla
yaparken `skill_write` ile o işi bir araca çeviriyor; yazıldığı anda
yükleniyor ve bir sonraki adımda çağırıyor. Başka bir programın eklenti
sistemine bağlı değil — dosyalar `~/.ajan/yetenekler/`, sözleşme bir
`ARAC` sözlüğü ile `calistir(girdi, ortam)` fonksiyonu.

```python
ARAC = {
    "ad": "gun_farki",
    "aciklama": "Iki tarih arasindaki gun sayisi.",
    "girdi": {"bas": {"type": "string"}, "son": {"type": "string"}},
}

KOMUT = {"ad": "gun", "aciklama": "Gun farki", "talimat": "Su iki tarih arasini hesapla:"}

def calistir(girdi, ortam):
    from datetime import date
    return f"{(date.fromisoformat(girdi['son']) - date.fromisoformat(girdi['bas'])).days} gun"
```

`KOMUT` isteğe bağlı: çubuğa `/gun` yazınca o talimat gönderiliyor. `/`
yazdığın anda eldeki komutlar çubukta listeleniyor.

Sözleşmenin sert tarafları:

- **Bozuk yetenek gizlenmiyor.** Yüklenemeyen dosya sessizce atlanmıyor;
  hatasıyla listede duruyor. Sessizce atlamak, "yazdım" deyip hiç
  çalışmayan bir yetenek bırakmanın en kolay yolu.
- **Yarım kurulum yok.** Yükleme başarısızsa dosya eski hâline dönüyor.
- **Yerleşik araç adı ele geçirilemiyor.** Bir yetenek `run_shell` adını
  alıp kabuk çağrılarını üstlenemiyor.
- **Kapı yeteneğin içinde de devrede.** `ortam.kabuk("del /f /s /q ...")`
  yine Berkay'a soruluyor; yetenek yazmak kapıyı atlamanın yolu değil.
- **`.pyc` önbelleği devre dışı.** Kaynak doğrudan derleniyor. `importlib`
  bayt kodunu boyut ve zaman damgasıyla doğruluyor; tek karakterlik bir
  düzeltme (`+` yerine `*`) ikisini de değiştirmiyor ve düzeltilmiş dosya
  eski hâliyle çalışmaya devam ediyordu. Bir testte yakalandı.

## Ajan arayüze özellik ekleyebiliyor

Bir yetenek metin yerine **panel** döndürebiliyor: ana pencerede açılan,
ölçü/tablo/liste/günlük bölümlerinden oluşan gerçek bir arayüz.

Yetenek Qt kodu yazmıyor. Ne göstermek istediğini düz bir sözlükle
söylüyor, çizimi uygulama yapıyor:

```python
def calistir(girdi, ortam):
    return {"panel": {
        "baslik": "brky sunucu durumu",
        "bolumler": [
            {"tur": "olcu", "ogeler": [
                {"etiket": "Disk", "deger": "%68 dolu", "durum": "uyari"}]},
            {"tur": "tablo", "basliklar": ["Klasor", "Boyut"],
             "satirlar": [["/var/log", "4.4 GB"]]},
        ],
    }}
```

Ayrım kasıtlı ve üç somut sebebi var:

1. **Görsel dil korunuyor.** Ajanın eklediği panel uygulamanın geri
   kalanından ayırt edilemiyor: aynı Fluent renkleri, aynı yarıçap, aynı
   çizimler. Serbest Qt kodu her yetenekte biraz farklı görünen bir arayüz
   üretirdi.
2. **Arayüz thread'i düşmüyor.** Yetenek ajanın thread'inde çalışıyor;
   oradan widget kurmak Qt'de tanımsız davranış.
3. **Model de aynı şeyi görüyor.** Panel metne çevrilip ajana veriliyor;
   yoksa gösterdiği panelle çelişen bir cümle kurabilir.

Renkleri yetenek seçmiyor. `durum` alanına `iyi`, `uyari`, `kotu` ya da
`notr` yazıyor, rengi tema veriyor — açık temaya geçildiğinde ajanın
yazdığı hiçbir panelin düzeltilmesi gerekmiyor.

Tanınmayan bir bölüm türü sessizce atlanmıyor, hata olarak dönüyor: ajan
panelinin görünmediğini fark etmeli ki düzeltebilsin.

**Yapamadığı:** kendi sistem promptunu, güvenlik kapısını, modelini ve
pencere düzenini değiştiremiyor. Bunlar kodda ve bir kısmı kasıtlı — ajanın
kendi kapısını gevşetebilmesi, kapının olmaması demek.

## Discord eklentisi

`eklentiler/discord.py` — yetenek sisteminin gerçek bir işte kullanımı.
Bot API'si yok: ajan Discord'u senin gördüğün gibi görüyor ve senin
bastığın tuşlara basıyor, uygulamanın geri kalanıyla aynı yol.

**Neden klavye, neden erişilebilirlik ağacı değil:** ölçüldü. Discord
Electron ve UIA ağacı 33 düğüm döndürüyor — hepsi boş grup, tek satır metin
yok. `read_ui_tree` burada işe yaramıyor.

Ekran görüntüsü pahalı olduğu için eklenti gezinmeyi klavyeye yıkıyor.
`Ctrl+K` hızlı geçiş kutusu bir sunucuya, kanala ya da kişiye adını yazarak
gitmeyi sağlıyor; ajanın gözü yalnızca doğrulama için gerekiyor.

Korumalar, hepsi testli:

- **Discord ön planda değilse hiçbir tuş gönderilmiyor.** Bir kez öne
  getirmeyi deniyor, olmazsa duruyor. Yanlış pencereye giden tuş,
  başkasının sohbetine yazmak demek — bu projede bir kez oldu.
- **`yaz` göndermiyor.** Metni kutuya koyuyor; ajan ekrandan doğru kişide
  olduğunu doğruluyor, sonra `gonder` çağırıyor ve o adımda Berkay'a
  soruluyor.
- **Satır sonu içeren metin reddediliyor.** Discord'da Enter mesajı
  gönderir; çok satırlı bir metin yarısını erkenden yollardı.
- **Arama sonrası bekleniyor.** Yazdıktan hemen sonra Enter, liste henüz
  güncellenmediği için **önceki** sonuca gidiyor — yanlış kişiye mesaj
  yazmanın en kolay yolu.
- **Açılışta doğru monitöre geçiliyor.** Discord ikinci ekrandayken ajan
  birinciye bakıp onu hiç göremiyordu.

Sesli kanaldan ayrılmanın klavye kısayolu yok; eklenti bunu uyduracağına
söylüyor ve ajanın görüp tıklamasını istiyor.

## Düğmeler

Yetenek ajanın kullandığı araç; düğme Berkay'ın kullandığı kısayol. Düğme
çubukta duruyor, tıklanınca hazır bir talimat gidiyor.

İkisi de kurabiliyor. Ajan tekrar eden bir iş fark ettiğinde `button_write`
ile öneriyor — onaysız kurulmuyor, çünkü düğme Berkay'ın arayüzünü
değiştiriyor. Berkay artıya basıp Python yazmadan kendisi ekliyor: etiket,
talimat, çizim. Ajanın kurduğu düğme Berkay'ın düzenleyemediği bir şey
değil; ikisi de aynı `~/.ajan/dugmeler.json` dosyasına yazıyor.

Düğmeler yeteneklerden ayrı dosyada tutuluyor çünkü ömürleri farklı:
yetenek kod, düğme tercih. Bir yeteneği silmek onu çağıran düğmeyi
silmiyor.

Bozuk bir `dugmeler.json` uygulamayı açılmaktan alıkoymuyor — okuma hiçbir
durumda istisna fırlatmıyor, eksik alanlı kayıt atlanıyor, gerisi kalıyor.

## Uzak makine

Sunucu, uygulamanın bir paneli olarak açılıyor: klasörler bir listede, yol
tıklanabilir kırıntılarda, dosyalar boyutu ve tarihiyle. Terminalde `ls`
yazıp nerede olduğunu aklında tutmak yerine, Dosya Gezgini'nde ne
bekliyorsan o.

Bağlantı Windows'un kendi `ssh.exe`'siyle, bir Python SSH kütüphanesiyle
değil: `~/.ssh/config` içindeki takma adlar ve anahtarlar zaten orada.
`brky` diye bir takma adın varsa burada da `brky` yazıyorsun.

Dizin listesi `ls -l` ayrıştırılarak değil `find -printf` ile alınıyor.
`ls -l` çıktısı yerel dile göre değişiyor, boşluklu dosya adlarında
sütunları kaydırıyor ve tarih biçimi dosyanın yaşına göre farklılaşıyor.

Ajan da aynı oturumu kullanıyor — sen bağlanırsan o da bağlı oluyor. İki
ayrı bağlantı tutmak, panelde bir yeri gezerken ajana başka bir yerden
bahsetmek demekti.

**Uzak güvenlik kapısı yereldekinin tersi.** Yerelde yasak listesi:
tehlikeli kalıplar aranıyor, gerisi geçiyor. Uzakta izin listesi: yalnızca
okuyan komutlar sorgusuz geçiyor, tanımadığımız her şey soruluyor. Sebebi
somut — yerelde yanlış giden bir komut Berkay'ın kendi dosyası, sunucuda
aynı komut çalışan bir servisi düşürüyor.

Parola ile giriş yok ve arayüzde bu yazıyor: parolayı programdan beslemek
için onu bir yerde tutmak gerekirdi.

Panelden silme ve taşıma yapılamıyor. Yanlış klasörde yapılan bir
sağ tık > sil, sunucuda geri alınamaz.

## Hız

Bir iş 38 saniye sürüyordu, aynı iş şimdi 14 saniye. Tahmin edilmedi,
ölçüldü — ve tahminlerin ikisi de yanlış çıktı.

| | önce | sonra |
|---|---|---|
| toplam | 38.4 sn | 13.9 sn |
| araçlar | 17.2 sn | 0.2 sn |
| model | 21.2 sn | 13.7 sn |

Dört değişiklik:

**Açık uygulamayı yeniden başlatma.**  **25 saniye** sürüyordu.
Pencere zaten açıkken öne getirme başarısız olunca başlatma yoluna
düşüyordu;  yeni bir pencere bekleyip 10 saniye zaman aşımına
giriyor, üstüne eklentinin kendi beklemeleri biniyordu. Pencere varsa artık
hiç başlatılmıyor: **4 ms**.

**Ön plana getirme gerçekten çalışsın.** Windows ön plan hırsızlığını
engelliyor;  çağrıların çoğunda sessizce yok
sayılıyordu ve ajan pencereyi açamayıp turlarca deniyordu.
 ile ön plandaki thread'e geçici bağlanınca 5/5 başarı,
her biri ~20 ms.

**Kare biçimi WebP kayıpsız.** Ölçüm iki monitörde:

| biçim | base64 | kodlama |
|---|---|---|
| PNG compress=1 | 632–1843 KB | 40–94 ms |
| WebP kayıpsız m=0 | 315–795 KB | 71–241 ms |
| WebP kalite 90 | 264–308 KB | 87–89 ms |

Kayıpsız seçildi. Kayıplı biçim daha küçük ama ajanın okuduğu şey küçük
yazı; yanlış okunan bir etiket yanlış tıklama demek ve bunun maliyeti
birkaç yüz kilobayttan yüksek.  daha da küçültüyor ama aynı
karede 910 ms sürüyor — her adıma binen 700 ms buna değmiyor.

**Önbellek noktası doğru yere.** Nokta computer araç setinin üstündeydi ve
bir nokta yalnızca kendisine kadar olanı kapsıyor: arkasındaki 28 özel araç
(~3700 token) ile sistem promptu (~2450 token) her istekte yeniden
işleniyordu. Nokta son statik aracın üstüne alındı ve sistem promptu
önbelleklenebilir blok yapıldı — her adımda **16.100 token önbellekten**
geliyor. Yetenekler noktadan sonra kaldığı için yeni yetenek yazmak
önbelleği bozmuyor.

Ayrıca sistem promptuna hız bölümü eklendi: birbirini izleyen eylemleri tek
turda gönder, metin sonucu yeten yerde ekran görüntüsü alma, bitirirken tek
cümle yaz.

## Güvenlik

Üç katman, üçü de bağımsız:

1. **Sistem promptu** ajana nerede duracağını söyler (UAC, şifre, ödeme,
   silme, mesaj gönderme).
2. **`safety/gate.py`** komutu desen eşleştirmeyle sınıflandırır ve riskliyse
   onay ister. Prompt'a değil koda gömülü, çünkü prompt bir öneri, kapı bir
   mekanizma. Onay kancası bağlanmamışsa varsayılan **red**.
3. **`safety/killswitch.py`** Esc ×3 ile döngüyü keser. Ayrı thread'de
   yoklama yapıyor, ajan ne yaparsa yapsın cevap verir.

Kapsam sınırı: bu bir kum havuzu değil. Kararlı bir saldırgan desenlerin
etrafından dolaşır. Amaç, iyi niyetli bir ajanın geri alınamaz bir şeyi fark
etmeden yapmasını engellemek.

## Ne eksik, ne kırık

Bir README'de en işe yarayan bölüm bu.

- **Ses yok.** Gemini kullanılacak, API anahtarı henüz yok. Mikrofon
  düğmesi ve üç durumu hazır ama arkasındaki motor bağlı değil; arayüz bunu
  gizlemiyor, durum satırında yazıyor.
- **Yetenek kodu için kum havuzu yok.** `skill_write` ile kurulan kod bu
  süreçte, tam yetkiyle çalışıyor: `import os` yazıp güvenlik kapısını
  dolaşabilir. Koruma tek katman — her kurulum Berkay'ın onayını istiyor ve
  kodun tamamı onay ekranında gösteriliyor. Gerçek bir kum havuzu (ayrı
  süreç, kısıtlı içe aktarma) yazılmadı.
- **Açık tema denenmedi.** `fluent.py` iki temayı da üretiyor ama yalnızca
  koyu tema render edilip ölçüldü.
- **Belgeler salt okunur.** Tabloya ve yazı belgesine bakabiliyorsun, hücre
  seçebiliyorsun, formül çubuğu gerçek içeriği gösteriyor — ama
  düzenleyemiyorsun. Düzenlemeyi şu an sadece ajan yapıyor.
- **Sistem tepsisi ve global kısayol yok.** Uygulama açılışta başlamıyor.
- **Workflow yok.** Kayıt/oynatma Faz 6. Yetenekler bunun bir kısmını
  karşılıyor ama tekrar eden bir GUI dizisini otomatik kaydetmiyorlar;
  yeteneği ajan elle yazıyor.
- **Kuru çalıştırma modu yok.** Seçilmiş ama başlanmadı.
- **Uygulamanın kendi penceresi ekran görüntüsünden çıkarılmıyor.** Ajan
  kendi arayüzünü görebiliyor.
- **Ofisin arayüzü yok.** Ajan belgeyi yazıyor, sen Excel'de açıp bakıyorsun.
  Canlı ortak düzenleme ve canlı veri kaynağı arayüze bağlı, Faz 5'ten sonra.
- **Sunum (.pptx) yok.** Kütüphane çalışıyor, araç yazılmadı.
- **Yazı belgesinde ekleme geri alınamıyor.** python-docx'te paragraf silmek
  XML ağacına inmeyi gerektiriyor; yarım çalışan bir geri alma tehlikeli
  olacağı için hiç yapılmadı ve bu açıkça söyleniyor.
- **Terminal ekranı 120x40 sabit.** Daha geniş bir TUI kırpılır; ekran
  boyutu henüz araçtan ayarlanamıyor.
- **Terminalde kaydırma geçmişi yok.** Ajan yalnızca o anki ekranı görüyor;
  yukarı kayan çıktı kaybolur.
- **Uzun metin yazmak yavaş.** Karakter başına ~12 ms; 500 karakter 6 saniye.
  Panoya yazıp `Ctrl+V` daha hızlı ama kullanıcının panosunu eziyor.
- **Yakalama kendi penceremizi dışlamıyor.** Arayüz gelince ajan kendi
  ekranını okuyup geri besleme döngüsüne girer. Faz 5'te çözülecek.
- **`run_shell` çıktısı 8000 karakterde kesiliyor.** Kesildiği söyleniyor ama
  sayfalama yok; uzun çıktılı bir komut eksik okunur.
- **UAC diyaloğu erişilemez.** Güvenli masaüstünde çıktığı için ne
  yakalanabilir ne tıklanabilir. Ajan orada durup insandan istiyor.
- **Anti-cheat.** `SendInput` DirectInput yakalayan oyunlarda çalışmaz.
- **UIA her yerde çalışmaz.** Tuval, oyun, video, bazı web sayfaları boş ağaç
  verir. `read_ui_tree` bunu bildiriyor ve model ekran görüntüsüne dönüyor.

## Geliştirirken öğrenilenler

Beşi de gerçek koşuda çıktı, hepsi koda gömülü:

**Girdinin hedefi yoktur.** `type_text` ve `press` nereye yazdıklarını
bilmezler — o an odakta ne varsa oraya giderler. İlk doğrulama koşusunda
Notepad öne gelmedi ve test metni ikinci ekrandaki bir tarayıcı sekmesine
düştü, ardından gelen `Return` mesajı gönderdi. `computer/windows.py` bu
yüzden var: her klavye eyleminden önce `assert_foreground`.

**Toplu gönderim karakter yer.** İlk `type_text` 24 karakteri tek `SendInput`
çağrısında topluyordu. Kısa dizelerde kusursuz görünüyordu; 55 karakterlik
gerçek bir metin hedefe **39 karakter** olarak düştü, arada kalanlar `…` oldu.
Olaylar hedefin mesaj kuyruğunun tükettiğinden hızlı geliyordu. Şimdi karakter
başına bir çağrı, arada 12 ms.

**Boş yere uyaran bir kapı, kapı değildir.** Güvenlik kapısının ilk sürümü
`format` deseni arıyordu ve PowerShell'in en sık kullanılan salt-okunur
cmdlet'i **`Format-List`** ile eşleşiyordu. Bir dosya listeleme komutuna
"diski biçimlendiriyor" diye onay istedi. Sürekli yanlış alarm veren bir kapı
görmezden gelinir ve o noktada hiç kapı olmamasından kötüdür. Desen artık dar:
`format C:` ve `Format-Volume` yakalanıyor, `Format-List` geçiyor.

**Sessizce takılan bir el sıkışma.** Terminal oturumları ConPTY ile açılıyor.
ConPTY açılışta `ESC[c` (cihaz öznitelikleri) gönderip **cevap bekliyor**;
cevaplamazsan prompt hiç yazılmıyor. Oturum canlı, süreç çalışıyor, hata yok
— ekran sonsuza kadar boş. İlk düzeltme fazla cevap verdi: `ESC[1t` bir sorgu
değil terminale verilen bir komut ve ona cevap yazmak `[8;40;120t` dizisini
kabuğa yazılmış bir tuş dizisi olarak gönderdi, komut satırına düştü.
Yalnızca gerçek sorgular cevaplanmalı.

**Katı şema bir bütçedir.** Her araca `strict: True` koymuştum. Tek tek
hepsi geçiyordu, on sekizi birden "Schema is too complex" ile 400 dönüyordu:
katı şemalar kısıtlı bir gramere derleniyor ve toplam gramer boyutunun sınırı
var. Ölçüldü — 12 katı + 6 gevşek geçiyor, 18 katı geçmiyor. Katılık
kaldırıldı; doğrulama zaten dispatch tarafında ve modele düzeltmesi kolay
hata dönüyor. Bu sınır araç sayısıyla değil şema boyutuyla ilgili, yani yeni
araç eklerken sessizce geri gelebilir.

Beşi de yalnızca uçtan uca, gerçek bir hedefe karşı çalıştırınca ortaya çıktı.
Birim testler hiçbirini yakalayamazdı — ama hepsinin regresyon testi ya da
kodda gerekçesi artık yerinde.

## Yapı

```
backend/
  config.py             .env okuma; anahtarlara dokunan tek yer
  computer/
    displays.py         monitör envanteri, sanal masaüstü <-> ekran çevirisi
    capture.py          mss ile monitör başına PNG, zoom için kırpma
    input.py            SendInput: mutlak fare, unicode klavye
    windows.py          ön plan penceresi sorgusu ve odak kilidi
    uia.py              erişilebilirlik ağacı -> tıklama noktalı metin
    files.py            dosya okuma/yazma/düzenleme, her yerde UTF-8
    terminal.py         ConPTY + pyte: TUI'yi metin ekran olarak gösterir
  office/
    model.py            gerekçe defteri; her değişiklik neden yapıldığını taşır
    sheet.py            .xlsx okuma/yazma
    text.py             .docx okuma/yazma
    store.py            açık belgeler
  agent/
    loop.py             ajan döngüsü, akış, bağlam budama, değişken effort
    dispatch.py         araç çağrısı -> gerçek eylem, onay kapısı
    tools.py            özel araç tanımları
    prompts.py          sistem promptu
  safety/
    gate.py             risk sınıflandırıcı
    killswitch.py       Esc x3 acil durdurma
app/
  fluent.py             Fluent token'ları; tema ve vurgu sistemden okunuyor
  window.py             ana pencere, dock panelleri, durum şeridi
  commandbar.py         yüzen komut çubuğu: mikrofon, yazı alanı, önizleme
  sheet_view.py         Excel benzeri tablo: formül çubuğu, sayfa sekmeleri
  panels.py             tablo, yazı, kod, terminal, değişiklik listesi
  fixtures.py           ajanın gerçekten ürettiği örnek içerik
ajan.py                 masaüstü uygulaması girişi
scripts/
  check_phase1.py       yakalama ve girdi elle doğrulama
  ajan.py               terminal arayüzü (ajan çekirdeği)
tests/test_computer.py  saf mantık: koordinat, tuş, kapı, dosya, effort
```

## Sırlar

`.env` içine giren hiçbir şey repoya girmez. `config.py` `os.environ`'a
dokunan tek modül — bir anahtarın nereden geldiği tek yerden görülebilsin
diye.
