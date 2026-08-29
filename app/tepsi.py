"""Tepsi simgesi — uygulama arkadayken de görünen tek yüzey.

Ajan uzun işlerde dakikalarca çalışıyor ve o sırada bakılan şey ajan
penceresi değil, işin yapıldığı uygulama. Şimdiye kadar "bitti mi" sorusunun
cevabı pencereyi bulup bakmaktı.

Tepsideki simge bunu üç yerden çözüyor:

- **Renk durumu söylüyor.** Çalışırken vurgu rengi, onay beklerken uyarı
  rengi, durdurulduğunda kırmızı, boştayken sönük. Simgeye bakmak
  pencereye bakmakla aynı bilgiyi veriyor.
- **Menü kısa.** Pencere, komut çubuğu, durdur, çık. Bir tepsi menüsü
  ayarlar paneli değil.
- **Bildirim yalnızca bakmıyorken.** Ajan penceresi öndeyken balon
  göstermek, bakılan şeyi ikinci kez söylemek olurdu.

## Simge maskotun kendisi

`varliklar/svg/poz-bosta.svg` içindeki gövde silueti 96'lık ızgarada bir
çokgen; burada 16–48 piksele ölçekleniyor. Ayrı bir tepsi simgesi çizmek
uygulamanın iki farklı yüzü olması demekti. Varlıklar yoksa yuvarlatılmış
bir kare çiziliyor — simgesiz bir tepsi girdisi tıklanamaz bir boşluk.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .fluent import Tokens

#: Simgenin üretildiği boyutlar. Windows tepsiyi ölçek ayarına göre
#: seçiyor; tek boyut verip ona ölçekletmek 125% DPI'da bulanık çıkıyor.
BOYUTLAR = (16, 20, 24, 32, 48)


def _renk(t: Tokens, faz: str) -> str:
    """Gövde rengi. Anahtarlar `window.PHASE_LABEL` ile aynı."""
    if faz in {"kosuyor", "dinleniyor", "diziliyor", "onay"}:
        return t.accent
    if faz == "bitti":
        return t.success
    return t.text_secondary


def _rozet(t: Tokens, faz: str) -> str:
    """Köşe rozetinin rengi; gerekmiyorsa boş.

    Dikkat isteyen iki durumu gövde rengiyle ayırmak **çalışmıyor**:
    sistem vurgu rengi bu makinede pembe ve `critical` da pembeye yakın
    bir kırmızı — 16 pikselde "çalışıyor" ile "durduruldu" aynı simge
    oldu, çizip baktım. Vurgu rengi kullanıcının seçtiği bir şey ve
    hangi renge yakın olacağı önceden bilinemez.

    Rozet buna bağlı değil: sabit renkte, ayrı bir şekil ve gövdeden
    saydam bir boşlukla ayrılıyor.
    """
    if faz == "onay":
        return t.caution
    if faz == "durduruldu":
        return t.critical
    return ""


#: Rozetin çapı ve gövdeyle arasındaki boşluk, 96'lık ızgarada.
ROZET_CAP = 34.0
ROZET_BOSLUK = 7.0


#: Gözler. `varliklar/svg/gozler.svg` içindeki "genis" gözlerin
#: konumları — dar gözler 16 pikselde tek bir gri piksele iniyor ve
#: siluet gözsüz bir lekeye dönüyor. Geniş göz orada iki koyu nokta
#: bırakıyor ve maskot tanınıyor.
GOZLER = ((39.18, 37.60, 11.0), (59.03, 37.53, -14.6))
GOZ_EN, GOZ_BOY = 12.20, 10.67


#: Tepsi ipucunda görünen durum adları. Pencere içindekiyle aynı olmak
#: zorunda değil: orada "Ready" bir başlık, burada bir cümle sonu.
IPUCU = {
    "bos": "Yan Masa — idle",
    "dinleniyor": "Yan Masa — listening",
    "diziliyor": "Yan Masa — transcribing",
    "kosuyor": "Yan Masa — working",
    "onay": "Yan Masa — waiting for your approval",
    "bitti": "Yan Masa — done",
    "durduruldu": "Yan Masa — stopped",
}


def _siluet() -> list[QPointF]:
    """Maskotun nötr gövdesi. Varlık yoksa boş liste."""
    try:
        from .svgyuz import _poz_noktalari, varlik_var

        return _poz_noktalari("bosta") if varlik_var() else []
    except Exception:
        return []


def simge(t: Tokens, faz: str = "bos") -> QIcon:
    """Duruma göre renklenmiş tepsi simgesi."""
    renk = QColor(_renk(t, faz))
    rozet = _rozet(t, faz)
    noktalar = _siluet()
    ikon = QIcon()
    for boyut in BOYUTLAR:
        ikon.addPixmap(_kare(boyut, renk, noktalar,
                             QColor(rozet) if rozet else None))
    return ikon


def _kare(boyut: int, renk: QColor, noktalar: list[QPointF],
          rozet: QColor | None = None) -> QPixmap:
    resim = QPixmap(boyut, boyut)
    resim.fill(Qt.GlobalColor.transparent)
    p = QPainter(resim)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(renk)
    if noktalar:
        # Siluet 96'lık ızgarayı tam doldurmuyor; kenarda pay bırakmadan
        # ölçeklemek 16 pikselde gövdeyi kesiyordu.
        p.scale(boyut / 96.0, boyut / 96.0)
        yol = QPainterPath()
        for i, nokta in enumerate(noktalar):
            yol.moveTo(nokta) if i == 0 else yol.lineTo(nokta)
        yol.closeSubpath()
        p.drawPath(yol)
        # Gözler siluetten **oyuluyor**, üstüne koyu bir şekil
        # çizilmiyor: tepsinin zemini açık da olabilir koyu da ve
        # sabit renkli bir göz açık zeminde kayboluyor.
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        for x, y, aci in GOZLER:
            p.save()
            p.translate(x, y)
            p.rotate(aci)
            p.drawRoundedRect(
                QRectF(-GOZ_EN / 2, -GOZ_BOY / 2, GOZ_EN, GOZ_BOY),
                GOZ_BOY / 2, GOZ_BOY / 2,
            )
            p.restore()
        p.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_SourceOver
        )
    else:
        pay = boyut * 0.12
        p.drawRoundedRect(
            QRectF(pay, pay, boyut - pay * 2, boyut - pay * 2),
            boyut * 0.22, boyut * 0.22,
        )
        p.scale(boyut / 96.0, boyut / 96.0)

    if rozet is not None:
        # Önce saydam bir halka oyuluyor, sonra rozet içine çiziliyor:
        # gövdeyle aynı renkte bir kenar olsaydı rozet gövdeye yapışır ve
        # ayrı bir işaret olmaktan çıkardı. Ölçek zaten 96'lık ızgarada.
        merkez = QPointF(96.0 - ROZET_CAP / 2 - 2, 96.0 - ROZET_CAP / 2 - 2)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.drawEllipse(merkez, ROZET_CAP / 2 + ROZET_BOSLUK,
                      ROZET_CAP / 2 + ROZET_BOSLUK)
        p.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_SourceOver
        )
        p.setBrush(rozet)
        p.drawEllipse(merkez, ROZET_CAP / 2, ROZET_CAP / 2)
    p.end()
    return resim


class Tepsi(QObject):
    """Tepsi simgesi ve menüsü.

    Menüdeki her şey gerçekten bir şey yapıyor. "Ayarlar" diye açılmayan
    bir girdi ya da sönük bir "Güncellemeleri kontrol et", menüyü
    okunmaz yapmaktan başka bir işe yaramaz.
    """

    pencere_istendi = Signal()
    cubuk_istendi = Signal()
    durdur_istendi = Signal()
    cikis_istendi = Signal()

    def __init__(self, t: Tokens, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.t = t
        self._faz = "bos"
        self.icon = QSystemTrayIcon(simge(t), self)
        self.icon.setToolTip(IPUCU["bos"])

        menu = QMenu()
        pencere = menu.addAction("Show the window")
        pencere.triggered.connect(self.pencere_istendi.emit)
        cubuk = menu.addAction("Show the command bar")
        cubuk.triggered.connect(self.cubuk_istendi.emit)
        menu.addSeparator()
        self._durdur = menu.addAction("Stop the agent")
        self._durdur.setToolTip("Esc ×3 does the same from anywhere")
        self._durdur.triggered.connect(self.durdur_istendi.emit)
        menu.addSeparator()
        cik = menu.addAction("Quit Yan Masa")
        cik.triggered.connect(self.cikis_istendi.emit)
        # Menü Python tarafında canlı kalmalı: yerel bir değişken olarak
        # bırakılınca çöp toplayıcı alıyor ve tepsiye sağ tıklamak hiçbir
        # şey açmıyor.
        self._menu = menu
        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self._tiklandi)

    @staticmethod
    def kullanilabilir() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def goster(self) -> None:
        self.icon.show()

    def gizle(self) -> None:
        self.icon.hide()

    def set_phase(self, faz: str) -> None:
        if faz == self._faz:
            return
        self._faz = faz
        self.icon.setIcon(simge(self.t, faz))
        self.icon.setToolTip(IPUCU.get(faz, "Yan Masa"))

    def bildir(self, baslik: str, metin: str, hata: bool = False) -> None:
        """Balon bildirim. Metin kırpılıyor — Windows uzununu kendi kesiyor
        ve ortasından kesilen bir cümle hiçbir şey anlatmıyor."""
        if not self.icon.isVisible():
            return
        tur = (QSystemTrayIcon.MessageIcon.Warning if hata
               else QSystemTrayIcon.MessageIcon.Information)
        kisa = metin.strip().replace("\n", " ")
        if len(kisa) > 180:
            kisa = kisa[:177].rstrip() + "…"
        self.icon.showMessage(baslik, kisa, tur, 6000)

    def _tiklandi(self, sebep) -> None:
        # Tek tık çubuğu getiriyor, çift tık pencereyi. Tepsi simgesinin
        # asıl işi "hemen bir şey söyleyeceğim" ve o çubuk.
        if sebep == QSystemTrayIcon.ActivationReason.Trigger:
            self.cubuk_istendi.emit()
        elif sebep == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.pencere_istendi.emit()
