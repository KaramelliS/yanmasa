"""Masanın içindeki "Code" penceresi — ajan yazarken kodu görmek.

Ajan diske kod koyuyor ve şimdiye kadar onu görmenin yolu, yazma bittikten
sonra açılan ayrı bir sayfaydı. Burada olan başka bir şey: **yazılırken**
görünüyor. Model araç girdisini akıtarak üretiyor (`input_json_delta`) ve
`backend/agent/akankod.py` o yarım JSON'dan içeriği çıkarıyor. Yani
ekrandaki yazılma bir animasyon değil, modelin o anki üretimi.

Dosya diske hâlâ tek seferde yazılıyor. Canlı olan yazma değil üretim ve
durum satırı bunu böyle söylüyor — "writing" derken kastedilen modelin
yazması.

## Neden masanın içinde

Yan masa ajanın kendi çalışma alanı: uygulamalar orada açılıyor, orada
tıklanıyor. Kod da orada yazılıyorsa penceresi de orada olmalı. Ayrı bir
sekmede duran bir düzenleyici, aynı işin iki ayrı yerde olduğunu
söylüyordu.

Yakalanan gerçek pencereler ölçeklenmiş birer fotoğraf; bu pencere
gerçek arayüz, yani 1:1 ve okunaklı. Kodu okunmayacak kadar küçültmek,
onu göstermenin bütün sebebini ortadan kaldırırdı.

## Alt çekmece

Terminal ve değişiklikler aynı yerde, sekmeli. İkisi de "kodun yanında ne
oldu" sorusunu cevaplıyor ve ikisini yan yana koymak, hiçbirine yer
bırakmıyordu. Sekme yalnızca **içeriği olan** için çiziliyor: boş bir
"Changes" sekmesi, bakılacak bir şey varmış gibi duruyor.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from .fluent import Tokens
from .ide import Editor, highlight
from .mint import (
    BASLIK_ETKIN,
    BASLIK_H,
    CERCEVE,
    KOD_KENAR,
    KOD_SERIT,
    KOD_ZEMIN,
    YARICAP,
    YAZI,
    YAZI_SOLUK,
    YESIL,
)

#: Sol dosya listesinin eni. 168'de `discord_bot.py` sığıyor.
AGAC_EN = 168

#: Sekme şeridi ve durum satırı yükseklikleri.
SEKME_H = 30
DURUM_H = 22

#: Alt çekmecenin yüksekliği ve sekme şeridi.
CEKMECE_H = 146
CEKMECE_SEKME_H = 26

#: Renklendirme bu aralıktan sık çalışmıyor, ms. Her parçada `pygments`
#: çağırmak saniyede yüzlerce çözümleme demek; 120 ms'de göz akışı
#: kesintisiz görüyor ve işlemci ajanın kendi işine kalıyor.
RENK_ARASI = 120

#: Çekmecede tutulan en fazla terminal satırı.
TERMINAL_SATIR = 400

#: Değişiklik şeridinde gösterilen en fazla satır, her yön için.
DIFF_SATIR = 40

#: Araçtan durum satırındaki fiile.
FIIL = {
    "write_file": "writing",
    "edit_file": "editing",
    "skill_write": "writing a skill",
}


def _ad(yol: str) -> str:
    return Path(yol).name or yol


def _anahtar(yol: str) -> str:
    """Aynı dosyanın iki yazımını tek sayan anahtar.

    Akan girdideki yol modelin yazdığı hâli (`proje/bot.py` olabiliyor),
    yazma bittiğinde gelen ise çözülmüş mutlak yol. İkisini ayrı sanmak
    dosya listesinde `bot.py`'yi iki kez gösteriyordu — çizip gördüm.
    """
    try:
        return os.path.normcase(os.path.abspath(yol))
    except (OSError, ValueError):
        return yol


def _satir_sayisi(metin: str) -> int:
    return metin.count("\n") + (1 if metin and not metin.endswith("\n") else 0)


# --- parçalar --------------------------------------------------------------


class _Baslik(QWidget):
    """Mint başlık çubuğu. Düğme yok — bu pencere kapatılamaz.

    Masadaki gerçek pencerelerde de yok ve sebebi aynı: çalışmayan bir
    düğme çizmek, çalışıyormuş gibi görünen bir yalan olurdu.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(BASLIK_H)
        self._metin = "Code"

    def set_metin(self, metin: str) -> None:
        if metin != self._metin:
            self._metin = metin
            self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(BASLIK_ETKIN))
        p.setPen(QPen(QColor(CERCEVE), 1))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

        # Mint'in pencere noktaları: süs değil, bu çerçevenin bir pencere
        # olduğunu söyleyen şey. Tıklanmıyorlar ve tıklanır gibi de
        # durmuyorlar — sönük ve küçükler.
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(3):
            p.setBrush(QColor(YAZI_SOLUK if i == 2 else "#4a4a4a"))
            p.drawEllipse(QRectF(11 + i * 13, BASLIK_H / 2 - 3.5, 7, 7))

        f = QFont(self.font())
        f.setPointSizeF(8.5)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor(YAZI))
        p.drawText(self.rect().adjusted(58, 0, -12, 0),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   QFontMetrics(f).elidedText(self._metin,
                                              Qt.TextElideMode.ElideMiddle,
                                              self.width() - 74))
        p.end()


class _Agac(QWidget):
    """Ajanın bu oturumda dokunduğu dosyalar. Yazılan işaretli."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(AGAC_EN)
        self._yollar: list[str] = []
        self._etkin = ""

    def set_dosyalar(self, yollar: list[str], etkin: str = "") -> None:
        self._yollar = yollar
        self._etkin = etkin
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(KOD_KENAR))
        p.setPen(QPen(QColor("#1a1a1a"), 1))
        p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())

        baslik = QFont(self.font())
        baslik.setPointSizeF(7.0)
        baslik.setWeight(QFont.Weight.DemiBold)
        baslik.setCapitalization(QFont.Capitalization.AllUppercase)
        baslik.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        p.setFont(baslik)
        p.setPen(QColor("#7a7a7a"))
        p.drawText(QRectF(12, 8, self.width() - 20, 16),
                   Qt.AlignmentFlag.AlignVCenter, "FILES")

        f = QFont(self.font())
        f.setPointSizeF(8.2)
        olcum = QFontMetrics(f)
        p.setFont(f)
        y = 30.0
        for yol in self._yollar:
            if y > self.height() - 16:
                break
            etkin = yol == self._etkin
            if etkin:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#37373d"))
                p.drawRect(QRectF(0, y - 2, self.width() - 1, 20))
                p.setBrush(QColor(YESIL))
                p.drawRect(QRectF(0, y - 2, 2, 20))
            p.setPen(QColor(YAZI if etkin else "#9d9d9d"))
            p.drawText(QRectF(14, y, self.width() - 22, 18),
                       Qt.AlignmentFlag.AlignVCenter,
                       olcum.elidedText(_ad(yol), Qt.TextElideMode.ElideMiddle,
                                        self.width() - 24))
            y += 20
        p.end()


class _Sekmeler(QWidget):
    """Açık dosyanın sekmesi. Tek sekme var ve o da o an yazılan dosya."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(SEKME_H)
        self._ad = ""
        self._yaziliyor = False

    def set_dosya(self, yol: str, yaziliyor: bool) -> None:
        self._ad = _ad(yol)
        self._yaziliyor = yaziliyor
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(KOD_SERIT))
        if not self._ad:
            p.end()
            return

        f = QFont(self.font())
        f.setPointSizeF(8.2)
        olcum = QFontMetrics(f)
        en = min(self.width() - 4, olcum.horizontalAdvance(self._ad) + 46)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(KOD_ZEMIN))
        p.drawRect(QRectF(0, 0, en, SEKME_H))
        # Üstte ince bir vurgu çizgisi: hangi sekmenin açık olduğunu
        # söyleyen şey, VS Code'da da bu.
        p.setBrush(QColor(YESIL))
        p.drawRect(QRectF(0, 0, en, 1.6))

        p.setFont(f)
        p.setPen(QColor(YAZI))
        p.drawText(QRectF(12, 0, en - 34, SEKME_H),
                   Qt.AlignmentFlag.AlignVCenter, self._ad)
        if self._yaziliyor:
            # Kaydedilmemiş nokta: VS Code'un aynı işareti. Yazma
            # bitince kayboluyor.
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(YAZI_SOLUK))
            p.drawEllipse(QRectF(en - 22, SEKME_H / 2 - 4, 8, 8))
        p.end()


class CanliEditor(Editor):
    """Metni büyüyerek alan salt okunur düzenleyici.

    `setPlainText` her parçada çağrılamaz: belgeyi baştan kurmak
    kaydırmayı başa atıyor ve ekran titriyor. Gelen metin öncekinin
    devamıysa yalnızca **eki** sona ekleniyor.

    Renklendirme kısılıyor. `pygments` her parçada çalıştırılsaydı
    saniyede yüzlerce çözümleme olurdu; 120 ms'de göz akışı kesintisiz
    görüyor.
    """

    def __init__(self, t: Tokens) -> None:
        super().__init__(t, "boş.txt", "")
        self._yol = ""
        self._metin = ""
        self.setStyleSheet(
            f"QPlainTextEdit {{ background: {KOD_ZEMIN}; border: none;"
            f" padding: 6px 10px 6px 0; color: {YAZI};"
            f" selection-background-color: {t.accent};"
            f" selection-color: {t.on_accent}; }}"
        )
        # Salt okunur bir alanda imleç görünmüyor; klavyeyle seçilebilir
        # yapmak onu geri getiriyor. Yazılan yerin nerede olduğunu
        # gösteren tek şey o.
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.setCursorWidth(7)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._renk_zamani = QTimer(self)
        self._renk_zamani.setSingleShot(True)
        self._renk_zamani.timeout.connect(self._renklendir)

    def yaz(self, yol: str, metin: str) -> None:
        if yol != self._yol:
            self._yol, self._metin = yol, ""
            self.setPlainText("")
        if metin == self._metin:
            return
        if metin.startswith(self._metin):
            imlec = self.textCursor()
            imlec.movePosition(imlec.MoveOperation.End)
            imlec.insertText(metin[len(self._metin):])
        else:
            # Model kendini düzeltti ya da baştan başladı.
            self.setPlainText(metin)
        self._metin = metin
        self.moveCursor(self.textCursor().MoveOperation.End)
        self.ensureCursorVisible()
        if not self._renk_zamani.isActive():
            self._renk_zamani.start(RENK_ARASI)

    def bitir(self) -> None:
        """Yazma bitti: son bir kez tam renklendir."""
        self._renk_zamani.stop()
        self._renklendir()

    def _renklendir(self) -> None:
        if not self._metin:
            return
        self.language = highlight(self, self._yol or "boş.txt",
                                  self._metin, self.t)


class _Cekmece(QWidget):
    """Terminal ve değişiklikler, sekmeli.

    Sekme yalnızca içeriği olan için çiziliyor: boş bir "Changes"
    sekmesi, bakılacak bir şey varmış gibi duruyor.
    """

    def __init__(self, t: Tokens) -> None:
        super().__init__()
        self.t = t
        self.setFixedHeight(CEKMECE_H)
        self._terminal: list[str] = []
        self._terminal_ad = ""
        self._diff: tuple[str, str, str] = ("", "", "")
        self._etkin = "terminal"

    @property
    def dolu(self) -> bool:
        return bool(self._terminal or self._diff[1] or self._diff[2])

    def _sekmeler(self) -> list[tuple[str, str]]:
        cikti = []
        if self._terminal:
            cikti.append(("terminal", self._terminal_ad or "Terminal"))
        if self._diff[1] or self._diff[2]:
            cikti.append(("diff", "Changes"))
        return cikti

    def set_terminal(self, ad: str, ekran: str) -> None:
        self._terminal_ad = ad
        self._terminal = ekran.splitlines()[-TERMINAL_SATIR:]
        self._etkin = "terminal"
        self.update()

    def set_diff(self, yol: str, eski: str, yeni: str) -> None:
        self._diff = (yol, eski, yeni)
        self._etkin = "diff"
        self.update()

    def temizle(self) -> None:
        self._terminal, self._terminal_ad = [], ""
        self._diff = ("", "", "")
        self.update()

    def mousePressEvent(self, event) -> None:
        sekmeler = self._sekmeler()
        if not sekmeler:
            return
        f = self._sekme_yazisi()
        x = 10.0
        for anahtar, etiket in sekmeler:
            en = QFontMetrics(f).horizontalAdvance(etiket) + 22
            if x <= event.position().x() < x + en:
                self._etkin = anahtar
                self.update()
                return
            x += en

    def _sekme_yazisi(self) -> QFont:
        f = QFont(self.font())
        f.setPointSizeF(7.6)
        f.setCapitalization(QFont.Capitalization.AllUppercase)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
        return f

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(KOD_ZEMIN))
        p.setPen(QPen(QColor("#1a1a1a"), 1))
        p.drawLine(0, 0, self.width(), 0)

        sekmeler = self._sekmeler()
        f = self._sekme_yazisi()
        p.setFont(f)
        x = 10.0
        for anahtar, etiket in sekmeler:
            en = QFontMetrics(f).horizontalAdvance(etiket) + 22
            etkin = anahtar == self._etkin
            p.setPen(QColor(YAZI if etkin else "#8a8a8a"))
            p.drawText(QRectF(x + 11, 1, en - 22, CEKMECE_SEKME_H),
                       Qt.AlignmentFlag.AlignVCenter, etiket)
            if etkin:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(YESIL))
                p.drawRect(QRectF(x + 8, CEKMECE_SEKME_H - 2, en - 16, 1.6))
            x += en

        # Sekme şeridiyle içerik arasında bir soluk: ilk terminal satırı
        # sekme çizgisine yapışıyordu.
        p.setPen(QPen(QColor("#252526"), 1))
        p.drawLine(0, CEKMECE_SEKME_H, self.width(), CEKMECE_SEKME_H)
        govde = QRectF(0, CEKMECE_SEKME_H + 6, self.width(),
                       self.height() - CEKMECE_SEKME_H - 8)
        if self._etkin == "diff" and (self._diff[1] or self._diff[2]):
            self._diff_ciz(p, govde)
        elif self._terminal:
            self._terminal_ciz(p, govde)
        p.end()

    def _tek_aralikli(self) -> QFont:
        f = QFont(self.t.font_mono, 8)
        f.setStyleHint(QFont.StyleHint.Monospace)
        return f

    def _terminal_ciz(self, p: QPainter, alan: QRectF) -> None:
        f = self._tek_aralikli()
        p.setFont(f)
        satir_h = QFontMetrics(f).height()
        sigan = max(1, int(alan.height() / satir_h))
        p.setPen(QColor("#c8c8c8"))
        # Sondan başa: bir terminalde bakılan şey son çıktı.
        for i, satir in enumerate(self._terminal[-sigan:]):
            p.drawText(QRectF(12, alan.top() + 2 + i * satir_h,
                              alan.width() - 20, satir_h),
                       Qt.AlignmentFlag.AlignVCenter, satir)

    def _diff_ciz(self, p: QPainter, alan: QRectF) -> None:
        f = self._tek_aralikli()
        p.setFont(f)
        satir_h = QFontMetrics(f).height()
        y = alan.top() + 2
        eski = self._diff[1].splitlines()[:DIFF_SATIR]
        yeni = self._diff[2].splitlines()[:DIFF_SATIR]
        for isaret, satirlar, renk, zemin in (
            ("−", eski, "#e08c8c", "#3a2323"),
            ("+", yeni, "#9fd08c", "#233a26"),
        ):
            for satir in satirlar:
                if y > alan.bottom() - satir_h:
                    return
                p.fillRect(QRectF(0, y, alan.width(), satir_h),
                           QColor(zemin))
                p.setPen(QColor(renk))
                p.drawText(QRectF(12, y, 14, satir_h),
                           Qt.AlignmentFlag.AlignVCenter, isaret)
                p.drawText(QRectF(28, y, alan.width() - 36, satir_h),
                           Qt.AlignmentFlag.AlignVCenter, satir)
                y += satir_h


class _Durum(QWidget):
    """Alt durum satırı: ne yapılıyor, kaç satır."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(DURUM_H)
        self._sol = ""
        self._sag = ""

    def set_metin(self, sol: str, sag: str = "") -> None:
        if (sol, sag) != (self._sol, self._sag):
            self._sol, self._sag = sol, sag
            self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#2f4f22"))
        f = QFont(self.font())
        f.setPointSizeF(7.6)
        p.setFont(f)
        p.setPen(QColor("#d8e8cc"))
        p.drawText(self.rect().adjusted(12, 0, -12, 0),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   self._sol)
        if self._sag:
            p.drawText(self.rect().adjusted(12, 0, -12, 0),
                       Qt.AlignmentFlag.AlignVCenter
                       | Qt.AlignmentFlag.AlignRight, self._sag)
        p.end()


# --- pencere ---------------------------------------------------------------


class KodPenceresi(QWidget):
    """Masanın içinde duran düzenleyici penceresi."""

    def __init__(self, t: Tokens) -> None:
        super().__init__()
        self.t = t
        self._yol = ""
        self._yaziliyor = False
        self._dosyalar: list[str] = []
        self._dil = ""
        self._fiil = ""

        dis = QVBoxLayout(self)
        dis.setContentsMargins(1, 1, 1, 1)
        dis.setSpacing(0)

        self.baslik = _Baslik()
        dis.addWidget(self.baslik)

        govde = QWidget()
        yatay = QHBoxLayout(govde)
        yatay.setContentsMargins(0, 0, 0, 0)
        yatay.setSpacing(0)

        self.agac = _Agac()
        yatay.addWidget(self.agac)

        sag = QWidget()
        sagd = QVBoxLayout(sag)
        sagd.setContentsMargins(0, 0, 0, 0)
        sagd.setSpacing(0)
        self.sekmeler = _Sekmeler()
        sagd.addWidget(self.sekmeler)
        self.editor = CanliEditor(t)
        sagd.addWidget(self.editor, 1)
        self.cekmece = _Cekmece(t)
        self.cekmece.setVisible(False)
        sagd.addWidget(self.cekmece)
        yatay.addWidget(sag, 1)
        dis.addWidget(govde, 1)

        self.durum = _Durum()
        dis.addWidget(self.durum)
        self._durumu_tazele()

    # --- dışarıdan gelenler ------------------------------------------------

    @property
    def yaziliyor(self) -> bool:
        """Şu anda bir dosya yazılıyor mu."""
        return self._yaziliyor

    @property
    def aktif(self) -> bool:
        """Gösterilecek bir şey var mı."""
        return bool(self._yol or self._dosyalar or self.cekmece.dolu)

    def kod_akiyor(self, arac: str, yol: str, metin: str, bitti: bool) -> None:
        """Model bir dosya yazıyor. `backend/agent/akankod.py`'den geliyor."""
        if not yol and not metin:
            return
        self._yol = yol or self._yol
        self._yaziliyor = not bitti
        self._dosya_ekle(self._yol)
        self.editor.yaz(self._yol, metin)
        if bitti:
            self.editor.bitir()
        self.baslik.set_metin(f"{_ad(self._yol)} — Code" if self._yol else "Code")
        self.sekmeler.set_dosya(self._yol, self._yaziliyor)
        self.agac.set_dosyalar(self._dosyalar, self._yol)
        self._fiil = FIIL.get(arac, "writing")
        self._durumu_tazele(self._fiil, _satir_sayisi(metin))

    def terminal_ciktisi(self, ad: str, ekran: str) -> None:
        if not ekran.strip():
            return
        self.cekmece.set_terminal(ad, ekran)
        self.cekmece.setVisible(True)

    def degisiklik(self, yol: str, eski: str, yeni: str) -> None:
        if not (eski or yeni):
            return
        self.cekmece.set_diff(yol, eski, yeni)
        self.cekmece.setVisible(True)

    def _dosya_ekle(self, yol: str) -> None:
        if not yol:
            return
        anahtar = _anahtar(yol)
        if any(_anahtar(v) == anahtar for v in self._dosyalar):
            return
        self._dosyalar.append(yol)
        # Liste ağaca sığdığı kadar: on dördü geçen bir listede en
        # eskiler zaten görünmüyor.
        self._dosyalar = self._dosyalar[-14:]

    def dosyalari_ekle(self, yollar: list[str]) -> None:
        """Ajan dosya yazdı — ağaçta görünsün, akmamış olsa bile."""
        for yol in yollar:
            self._dosya_ekle(yol)
        self.agac.set_dosyalar(self._dosyalar, self._yol)
        self._durumu_tazele()

    def temizle(self) -> None:
        self._yol, self._dosyalar, self._dil = "", [], ""
        self._yaziliyor = False
        self._fiil = ""
        self.editor.yaz("", "")
        self.cekmece.temizle()
        self.cekmece.setVisible(False)
        self.agac.set_dosyalar([], "")
        self.sekmeler.set_dosya("", False)
        self.baslik.set_metin("Code")
        self._durumu_tazele()

    # --- çizim -------------------------------------------------------------

    def _durumu_tazele(self, fiil: str = "", satir: int = 0) -> None:
        # Fiil verilmediyse en son kullanılana düşülüyor: ağacın
        # tazelenmesi "writing"i silmemeli, dosya hâlâ yazılıyor.
        fiil = fiil or self._fiil
        satir = satir or _satir_sayisi(self.editor._metin)
        if fiil and self._yaziliyor:
            sol = f"{fiil} {_ad(self._yol)} · {satir} lines"
        elif self._yol:
            sol = f"{_ad(self._yol)} · {_satir_sayisi(self.editor._metin)} lines"
        elif self._dosyalar:
            sol = f"{len(self._dosyalar)} files"
        else:
            sol = "waiting for the agent to write something"
        # Dil renklendirmeden geliyor ve renklendirme kısılmış: ilk
        # çalıştığı ana kadar boş kalıyor, sonra yerinde duruyor.
        self._dil = getattr(self.editor, "language", "") or self._dil
        if self._dil in ("plain text", "not highlighted (too large)"):
            self._dil = ""
        self.durum.set_metin(sol, self._dil)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cerceve = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        yol = QPainterPath()
        yol.addRoundedRect(cerceve, YARICAP, YARICAP)
        p.fillPath(yol, QColor(KOD_ZEMIN))
        p.setPen(QPen(QColor(CERCEVE), 1))
        p.drawPath(yol)
        p.end()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Köşeler yuvarlak; içerik de öyle kırpılmalı, yoksa başlık
        # çubuğunun köşeleri çerçevenin dışına taşıyor.
        yol = QPainterPath()
        yol.addRoundedRect(QRectF(self.rect()), YARICAP, YARICAP)
        from PySide6.QtGui import QRegion

        self.setMask(QRegion(yol.toFillPolygon().toPolygon()))
