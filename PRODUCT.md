# Product

<!-- impeccable:product-schema 1 -->

## Platform

desktop

(Impeccable şemasının dört değeri — web, ios, android, adaptive — bu ürüne
uymuyor: yerel bir Windows masaüstü uygulaması. Değer olduğu gibi yazıldı.)

## Stack

Python + PySide6 (Qt). Tek süreç, yerel pencereler, web katmanı yok.

Bu bilinçli bir geri dönüş: ilk yığın React + Vite + pywebview'di ve
kısmen yazılmıştı. Berkay web tabanlı bir şey istemediğini söyleyince
atıldı. Gerekçe teknik olarak da doğru — backend'in tamamı zaten Python
(UIA, ekran yakalama, PTY, ofis belgeleri), araya HTTP/WebSocket köprüsü
ve bir tarayıcı motoru koymak fazladan katman demekti. Ayrıca Qt'nin
`QDockWidget`'ı panelleri yerel olarak ayrı pencereye koparıyor; web
tarafında bu taklit edilmesi gereken bir davranıştı.

## Users

Tek birincil kullanıcı: Berkay, kendi Windows 11 makinesinde. Geliştirici;
aynı anda kod yazıyor, belge hazırlıyor ve sistem işleri yapıyor. Arayüz
Türkçe.

Çalışma ortamı: iki adet 1920×1080 monitör (sanal masaüstü 3840×1080),
%100 DPI, 16 GB RAM, Radeon RX 560 (4 GB).

## Product Purpose

Sesle yönetilen bir Windows bilgisayar kontrol ajanı. Berkay mikrofona basıp
konuşuyor; ajan işi yapıyor ve ne yaptığını gösteriyor.

Başarı: Berkay'ın elle yapacağı çok adımlı bir işi (tablo hazırlama, dosya
düzenleme, test çalıştırma, uygulama sürme) tek bir sözlü talimatla
bitirmesi — ve sonucu doğrulayabilmesi.

## Positioning

Piksel değil, Windows'un kendi API'leri. Yaygın bilgisayar ajanları ekran
görüntüsü alıp koordinat tahmin ederek tıklıyor. Bu ajanda ekran görüntüsü
son çare:

- **UIA erişilebilirlik ağacı** denetimleri tıklama noktalarıyla veriyor —
  ölçüm, tahmin değil. Ölçüldü: yerel Windows uygulamalarında denetimlerin
  %100'ü faresiz erişilebilir.
- **Kalıcı PTY oturumları** TUI'leri metin ekran olarak gösteriyor, ekran
  görüntüsü almadan.
- **Kendi ofisi** gerçek `.xlsx`/`.docx` üretiyor; Microsoft Office
  gerekmiyor ve kurulu değil.

İkinci ayırt edici nokta: **ajanın belgede yaptığı her değişiklik neden
yapıldığını taşıyor.** `why` zorunlu bir alan; gerekçesiz düzenleme hiç
çalışmıyor. Değişiklik defteri önceki değeri de tuttuğu için geri alma veri
kaybetmiyor.

## Operating Context

Uygulama açılışta başlar ve sistem tepsisinde durur. İş yokken kenarda ince
bir mikrofon şeridine küçülür; iş varken açılır. Global bir kısayol her
yerden konuşmayı başlatır.

Etkileşim döngüsü: basılı tut → konuş → bırak → bekle → ajan çalışır →
sonuç. Bekleme süresi gerçek ve değişken (basit iş ~10 sn, çok adımlı iş
dakikalar), yani bekleme durumu tasarımın birinci sınıf parçası.

Ajan çalışırken iş bağlamını panel olarak diziyor: düzenlediği tablo,
açtığı terminal, değişiklik defteri. Paneller uygulama içinde duruyor ama
ayrı bir pencereye koparılabiliyor — tabloyu ikinci ekrana atıp ajanı
birincide izlemek gibi.

## Capabilities and Constraints

Çalışan yetenekler (hepsi uçtan uca doğrulandı):

- Ekran yakalama (monitör başına), fare ve klavye (Türkçe karakterler dahil)
- UIA ağacı okuma; dosya okuma/yazma/düzenleme; PowerShell; uygulama başlatma
- Kalıcı terminal oturumları (Claude Code, opencode, REPL'ler erişilebilir)
- `.xlsx` ve `.docx` oluşturma, okuma, düzenleme, gerekçeli değişiklik defteri

Editör kapsamı: tablo, yazı belgesi, kod/düz metin, terminal görünümü.

Kesin kısıtlar:

- **Ses henüz yok.** Gemini API anahtarı bekleniyor. Mikrofon arayüzü
  tasarlanacak ama arkasındaki motor bağlanmadı.
- **Formül hesaplanmıyor.** Formüller dosyaya doğru yazılıyor, değerleri
  hesaplanmıyor. Motor (`formulas` 1.3.4) doğrulandı, bağlanmadı.
- **Chromium/Electron pencerelerinde UIA ağacı boş.** Tarayıcı için ayrı
  kanal gerekiyor.
- **UAC diyaloğu erişilemez** — güvenli masaüstünde çıkıyor.
- Uygulamanın kendi penceresi ekran yakalamadan dışlanmalı, yoksa ajan
  kendini okuyup geri besleme döngüsüne girer.

Güvenlik mekanizmaları arayüzde görünür olmalı: riskli eylemde onay istemi,
ve her an çalışan Esc ×3 acil durdurma.

## Brand Commitments

Ürün adı: **Ajan**. Arayüz dili Türkçe.

**Görsel dil: Windows 11 Fluent Design — kalıcı ve bağlayıcı.** Berkay bunu
açıkça seçti. Kendi görsel dünyamızı kurmuyoruz; uygulama Dosya Gezgini ve
Ayarlar'ın yanında durduğunda oradan gelmiş gibi görünmeli. Kalite çıtası
Windows 11'in kendi uygulamalarıdır.

Bunun pratikteki anlamı, `app/fluent.py` içinde uygulanıyor:

- Renkler **sistemden okunuyor**, sabit palet yok. Tema açığa alınırsa
  uygulama açılıyor, vurgu rengi değişirse uygulama onu alıyor. Sabit bir
  palet yazmak, Fluent olduğunu iddia edip tek gerçek kuralını çiğnemek
  olurdu.
- Segoe UI Variable (Text/Display), Cascadia Mono, Segoe Fluent Icons.
- Köşe yarıçapı: denetim 4, kart 8. WinUI 3 token adları korunuyor.

**Mikrofon her şeyden bağımsız.** Ana pencerenin parçası değil: çerçevesiz,
hep üstte, ekranın köşesinde kendi küçük penceresi. Sürüklenip taşınabiliyor
ve konumu kaydediliyor. Ajan penceresi kapalıyken de basıp konuşulabilmeli.

Daha önce "Mürettip Kasası" adlı özgün bir görsel dünya kurulmuş ve
uygulanmıştı; Berkay renklerini beğenmediğini söyleyince tümüyle atıldı.
Geri getirilmemeli.

## Evidence on Hand

Gerçek, çalışan çıktılar mevcut ve arayüz tasarımında örnek veri olarak
kullanılabilir:

- `~/Desktop/ajan_ofis/butce.xlsx` — ajanın ürettiği bütçe tablosu,
  `=SUM(B2:B5)` formülüyle; bağımsız motorla 18690.0 doğrulandı
- `~/Desktop/ajan_ofis/ozet.docx` — başlık, paragraf, 6×2 tablo
- `~/Desktop/ajan_demo/` — ajanın yazdığı Python projesi, 8 testi geçiyor

Uydurulmaması gerekenler: kullanıcı sayısı, müşteri, fiyat, karşılaştırmalı
kıyaslama. Ürünün tek kullanıcısı var.

## Product Principles

1. **Gösterilmeyen iş yapılmamış sayılır.** Ajan bir şey değiştirdiyse
   arayüz neyi ve neden değiştirdiğini göstermek zorunda.
2. **Bilinmeyen bilinmiyor diye söylenir.** Hesaplanmamış formül, okunamayan
   simge, yarım çizilmiş terminal — hepsi açıkça bildirilir. Sessiz boşluk,
   yanlış güven üretir.
3. **Durdurmak her zaman bir tuş uzakta.** Acil durdurma ve onay istemi
   arayüzün gizlenebilir parçaları değil.
4. **Bekleme gerçek, gizlenmez.** Sahte ilerleme çubuğu yok; ajanın o an ne
   yaptığı görünür.
5. **Berkay'ın makinesi Berkay'ın.** Ajan çalışırken kullanıcının işine
   mümkün olduğunca az müdahale eder.

## Accessibility & Inclusion

Türkçe metin desteği her katmanda zorunlu — sistem cp1254 varsayılanı
nedeniyle bu daha önce iki kez sessizce bozuldu. Klavyeyle tam kullanım
gerekli: ajan fareyi ele geçirdiğinde kullanıcının klavyeden müdahale
edebilmesi lazım.
