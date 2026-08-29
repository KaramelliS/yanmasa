"""Mint'e yakın palet ve ölçüler — masanın ortak dili.

Bu değerler `masa.py` içinde doğmuştu ve orada kalamazlardı: masanın
içindeki "Code" penceresi de aynı çerçeveyi, aynı başlık çubuğunu ve aynı
gri tonları kullanıyor. `kod_penceresi.py` bunları `masa.py`'den alsaydı
iki modül birbirini içe aktarırdı.

Renkler ve ölçüler Mint-Y'ye **yaklaşıyor**, kopyalanmıyor: Mint'in duvar
kâğıtları, logosu ve simgeleri onların ve bu depoya giremez. Panel,
başlık çubuğu ve yeşil vurgu burada sıfırdan seçildi.
"""

from __future__ import annotations

#: Başlık çubuğu yüksekliği — masaüstü ölçeğinden bağımsız, kendi
#: çerçevemiz olduğu için hep okunaklı kalıyor.
BASLIK_H = 26

#: Pencere köşe yarıçapı. Mint-Y üstü yuvarlatıyor; burada tamamı hafif
#: yuvarlak, çünkü pencere bir masaüstünün içinde yüzüyor ve alt köşeleri
#: keskin bırakmak onu kesilmiş gibi gösteriyordu.
YARICAP = 8.0

PANEL = "#2b2b2b"
PANEL_UST = "#1d1d1d"
BASLIK_ETKIN = "#3c3c3c"
BASLIK_PASIF = "#333333"
CERCEVE = "#212121"
YAZI = "#dcdcdc"
YAZI_SOLUK = "#98a09a"
YESIL = "#7fb24a"
DUVAR_UST = "#1a2b1e"
DUVAR_ALT = "#0b110d"

#: Kod penceresinin zeminleri. Mint grilerinden bir tık koyu: bir
#: düzenleyicinin gövdesi kabuktan geride durmalı, yoksa kod pencerenin
#: değil masanın üstünde duruyormuş gibi görünüyor.
KOD_ZEMIN = "#1e1e1e"
KOD_KENAR = "#252526"
KOD_SERIT = "#2d2d2d"
