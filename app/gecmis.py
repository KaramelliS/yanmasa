"""Koşu geçmişi — ajanın daha önce ne yaptığı.

Akış sayfası **şu anki** turu gösteriyor ve tur bitince orada kalıyor;
uygulama kapanınca da gidiyor. Oysa diskte gün gün bir denetim kaydı
birikiyor (`runs/*.jsonl`) ve bugüne kadar ona bakmanın tek yolu dosyayı
elle açmaktı.

Sayfanın cevapladığı üç soru var ve üçü de gerçek:

- **"Dün şu işi nasıl yaptırmıştım?"** Talimat metni kayıtta duruyor.
  Sağdaki "Run again" onu komut çubuğuna geri koyuyor.
- **"Bu iş neden tutmadı?"** Hatalı adımlar kırmızı; hata metni satırın
  altında.
- **"Yaptım dedi, gerçekten yaptı mı?"** `rapor.py` her turda ajanın
  cümlesini kayıtla karşılaştırıyor ve desteksiz iddiaları `bitti`
  satırına yazıyor. O satır burada görünüyor — daha önce yalnızca o an
  durum çubuğunda bir kez parlayıp kayboluyordu.

## Neden kendi çizimimiz

Sol liste ve adım satırları `QListWidget` değil, elle boyanan pencereler.
Sebep süs değil: bir satırda üç ayrı tipografik seviye var (talimat, saat,
sayaçlar) ve `QListWidget` bunu ancak her satır için bir widget kurarak
veriyor — yani zaten elle çizmekle aynı iş, üstüne stil sayfası kavgası.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from backend.agent.kayit import Kayit, Kosu, kosulari_derle

from .etiketler import hedef, tool_label
from .fluent import RADIUS_CARD, RADIUS_CONTROL, Tokens, _blend, sarmali
from .glyphs import WorkGlyph
from .stream import bicimle

#: Listeye alınan en fazla koşu. Ondört günlük kayıt yüzlerce tur
#: tutabiliyor ve hepsini birden pencere olarak kurmak sayfayı açılışta
#: yarım saniye dondururdu. Sınıra dayanıldığında liste bunu söylüyor.
EN_COK_KOSU = 200

#: Ayrıntıda gösterilen en fazla adım. Altmış adımlık bir tur normal;
#: üç yüzü geçen bir liste okunmuyor zaten.
EN_COK_ADIM = 300

#: Sol listenin eni. 320'de iki satırlık bir talimat okunuyor.
LISTE_EN = 320

SATIR_H = 60
GUN_H = 32


def _saat(ts: float) -> str:
    return time.strftime("%H:%M", time.localtime(ts)) if ts else "--:--"


def _gun_adi(ts: float) -> str:
    """Gün başlığı. Bugün ve dün adlarıyla, gerisi tarihiyle."""
    if not ts:
        return "Unknown day"
    gun = time.strftime("%Y-%m-%d", time.localtime(ts))
    bugun = time.strftime("%Y-%m-%d")
    dun = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
    if gun == bugun:
        return "Today"
    if gun == dun:
        return "Yesterday"
    return time.strftime("%a %d %B", time.localtime(ts))


def _sure(saniye: float) -> str:
    if saniye <= 0:
        return ""
    if saniye < 60:
        return f"{saniye:.0f}s"
    dakika, kalan = divmod(int(saniye), 60)
    if dakika < 60:
        return f"{dakika}m {kalan:02d}s"
    saat, dakika = divmod(dakika, 60)
    return f"{saat}h {dakika:02d}m"


def _ozet_satiri(kosu: Kosu) -> str:
    """Listedeki ikinci satır: saat, adım, süre, hata."""
    parcalar = [_saat(kosu.baslangic)]
    if kosu.kuru:
        parcalar.append("dry run")
    parcalar.append(f"{kosu.adim_sayisi} steps")
    sure = _sure(kosu.sure)
    if sure:
        parcalar.append(sure)
    if kosu.yarim:
        parcalar.append("unfinished")
    return "  ·  ".join(parcalar)


def _baslik(kosu: Kosu) -> str:
    """Talimat boşsa uydurmuyoruz — kaydın kesildiğini söylüyoruz."""
    metin = kosu.talimat.strip()
    return metin or "(the instruction is not in the log)"


# --- sol liste ------------------------------------------------------------


class _GunSatiri(QWidget):
    """Gün ayracı."""

    def __init__(self, t: Tokens, ad: str) -> None:
        super().__init__()
        self.t, self._ad = t, ad
        self.setFixedHeight(GUN_H)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        f = QFont(self.font())
        f.setPointSizeF(8.0)
        f.setBold(True)
        f.setCapitalization(QFont.Capitalization.AllUppercase)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        p.setFont(f)
        p.setPen(QColor(self.t.text_tertiary))
        p.drawText(QRectF(16, 0, self.width() - 32, GUN_H),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   self._ad)
        p.end()


class _Satir(QWidget):
    """Listedeki bir koşu."""

    secildi = Signal(int)

    def __init__(self, t: Tokens, kosu: Kosu, sira: int) -> None:
        super().__init__()
        self.t, self.kosu, self.sira = t, kosu, sira
        self.setFixedHeight(SATIR_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._uzerinde = False
        self._etkin = False

    def set_etkin(self, etkin: bool) -> None:
        if etkin != self._etkin:
            self._etkin = etkin
            self.update()

    def enterEvent(self, event) -> None:
        self._uzerinde = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._uzerinde = False
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.secildi.emit(self.sira)

    def paintEvent(self, _event) -> None:
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        zemin = t.background_secondary

        if self._etkin:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(_blend(t.accent, 0.12, zemin)))
            p.drawRect(self.rect())
            p.setBrush(QColor(t.accent))
            p.drawRoundedRect(QRectF(0, 10, 3, SATIR_H - 20), 1.5, 1.5)
        elif self._uzerinde:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.control))
            p.drawRect(self.rect())

        sag = self.width() - 16
        # Hata varsa satırın sağında bir nokta: listeyi okumadan taramak
        # için tek işaret bu.
        if self.kosu.hata_sayisi:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.critical))
            p.drawEllipse(QPointF(sag - 3, SATIR_H / 2), 3.0, 3.0)
            sag -= 14

        f = QFont(self.font())
        f.setPointSizeF(9.5)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor(t.text if (self._etkin or self._uzerinde)
                        else t.text_secondary))
        en = sag - 16
        p.drawText(
            QRectF(16, 10, en, 18), Qt.AlignmentFlag.AlignVCenter,
            QFontMetrics(f).elidedText(_baslik(self.kosu),
                                       Qt.TextElideMode.ElideRight, int(en)),
        )

        f2 = QFont(self.font())
        f2.setPointSizeF(8.0)
        p.setFont(f2)
        p.setPen(QColor(t.text_tertiary))
        p.drawText(
            QRectF(16, 30, en, 16), Qt.AlignmentFlag.AlignVCenter,
            QFontMetrics(f2).elidedText(_ozet_satiri(self.kosu),
                                        Qt.TextElideMode.ElideRight, int(en)),
        )

        p.setPen(QPen(QColor(t.divider), 1))
        p.drawLine(16, SATIR_H - 1, self.width() - 16, SATIR_H - 1)
        p.end()


# --- ayrıntı --------------------------------------------------------------


def _rozet(t: Tokens, metin: str, renk: str = "") -> QLabel:
    """Ayrıntı başlığındaki küçük sayaç."""
    etiket = QLabel(metin)
    ton = renk or t.text_secondary
    etiket.setStyleSheet(
        f"color: {ton}; background: {_blend(ton, 0.12, t.background)};"
        f" border-radius: {RADIUS_CONTROL}px; padding: 3px 9px;"
        f" font-size: 11px; font-weight: 600;"
    )
    return etiket


class _AdimSatiri(QWidget):
    """Ayrıntıdaki bir adım. Canlı akıştaki satırla aynı dili konuşuyor."""

    def __init__(self, t: Tokens, adim, sira: int) -> None:
        super().__init__()
        self.t = t
        duzen = QHBoxLayout(self)
        duzen.setContentsMargins(20, 8, 20, 8)
        duzen.setSpacing(12)

        sayi = QLabel(f"{sira}")
        sayi.setFixedWidth(22)
        sayi.setAlignment(Qt.AlignmentFlag.AlignRight
                          | Qt.AlignmentFlag.AlignTop)
        sayi.setStyleSheet(
            f"color: {t.text_disabled}; font-size: 11px;"
            f" font-family: '{t.font_mono}'; padding-top: 6px;"
        )
        duzen.addWidget(sayi)

        cizim = WorkGlyph(t, adim.arac, 30)
        if adim.hata:
            cizim.set_tone("hata")
        duzen.addWidget(cizim, 0, Qt.AlignmentFlag.AlignTop)

        sutun = QVBoxLayout()
        sutun.setContentsMargins(0, 0, 0, 0)
        sutun.setSpacing(2)

        hedef_metni = hedef(adim.girdi)
        bas = tool_label(adim.arac)
        ust = QLabel(f"{bas}  ·  {hedef_metni}" if hedef_metni else bas)
        ust.setWordWrap(True)
        ust.setStyleSheet(
            f"color: {t.critical if adim.hata else t.text};"
            f" font-size: 12.5px; font-weight: 600;"
        )
        sutun.addWidget(ust)

        # Özet yalnızca bir şey söylüyorsa yazılıyor. "OK" bir bilgi
        # değil ve altmış satır "OK" listeyi okunmaz yapıyordu.
        ozet = adim.ozet.strip()
        if ozet == "[image]":
            alt = QLabel("took a screenshot")
            alt.setStyleSheet(f"color: {t.text_tertiary}; font-size: 11.5px;")
            sutun.addWidget(alt)
        elif ozet and ozet != "OK":
            alt = QLabel(ozet[:400])
            alt.setWordWrap(True)
            alt.setStyleSheet(
                f"color: {t.critical if adim.hata else t.text_secondary};"
                f" font-size: 11.5px;"
                + (f" font-family: '{t.font_mono}';" if adim.hata else "")
            )
            sutun.addWidget(alt)

        duzen.addLayout(sutun, 1)

        saat = QLabel(_saat(adim.t))
        saat.setStyleSheet(
            f"color: {t.text_disabled}; font-size: 11px;"
            f" font-family: '{t.font_mono}';"
        )
        duzen.addWidget(saat, 0, Qt.AlignmentFlag.AlignTop)


class _Ayrinti(QWidget):
    """Seçili koşunun tamamı."""

    tekrarla = Signal(str)

    def __init__(self, t: Tokens) -> None:
        super().__init__()
        self.t = t
        dis = QVBoxLayout(self)
        dis.setContentsMargins(0, 0, 0, 0)
        dis.setSpacing(0)

        self._kaydirma = QScrollArea()
        self._kaydirma.setWidgetResizable(True)
        self._kaydirma.setFrameShape(QScrollArea.Shape.NoFrame)
        self._kaydirma.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        dis.addWidget(self._kaydirma, 1)

        self._govde = QWidget()
        self._duzen = QVBoxLayout(self._govde)
        self._duzen.setContentsMargins(0, 0, 0, 24)
        self._duzen.setSpacing(0)
        self._duzen.addStretch(1)
        self._kaydirma.setWidget(self._govde)

    def _temizle(self) -> None:
        while self._duzen.count() > 1:
            oge = self._duzen.takeAt(0)
            if oge.widget() is not None:
                oge.widget().deleteLater()

    def _ekle(self, w: QWidget) -> None:
        self._duzen.insertWidget(self._duzen.count() - 1, w)

    def bos_goster(self, metin: str, alt: str = "") -> None:
        self._temizle()
        kutu = QWidget()
        duzen = QVBoxLayout(kutu)
        duzen.setContentsMargins(40, 56, 40, 24)
        duzen.setSpacing(10)
        baslik = QLabel(metin)
        baslik.setStyleSheet(
            f"color: {self.t.text}; font-size: 20px; font-weight: 600;"
            f" font-family: '{self.t.font_display}', '{self.t.font_ui}';"
        )
        duzen.addWidget(baslik)
        if alt:
            govde = QLabel(alt)
            govde.setStyleSheet(
                f"color: {self.t.text_secondary}; font-size: 13px;"
                f" line-height: 150%;"
            )
            duzen.addWidget(sarmali(govde, 520))
        self._ekle(kutu)

    def goster(self, kosu: Kosu) -> None:
        t = self.t
        self._temizle()

        bas = QWidget()
        bd = QVBoxLayout(bas)
        bd.setContentsMargins(20, 22, 24, 18)
        bd.setSpacing(10)

        talimat = QLabel(_baslik(kosu))
        talimat.setWordWrap(True)
        talimat.setStyleSheet(
            f"color: {t.text}; font-size: 19px; font-weight: 600;"
            f" font-family: '{t.font_display}', '{t.font_ui}';"
        )
        bd.addWidget(talimat)

        rozetler = QHBoxLayout()
        rozetler.setSpacing(6)
        rozetler.addWidget(_rozet(
            t, f"{_gun_adi(kosu.baslangic)} {_saat(kosu.baslangic)}"))
        if kosu.kuru:
            # Bir kuru koşuyu gerçek bir koşu sanmak, yapılmamış bir işi
            # yapılmış hatırlamak demek.
            rozetler.addWidget(_rozet(t, "dry run — nothing was done",
                                      t.caution))
        rozetler.addWidget(_rozet(t, f"{kosu.adim_sayisi} steps"))
        if _sure(kosu.sure):
            rozetler.addWidget(_rozet(t, _sure(kosu.sure)))
        if kosu.hata_sayisi:
            rozetler.addWidget(_rozet(
                t, f"{kosu.hata_sayisi} failed", t.critical))
        if kosu.yarim:
            # "Yarım" gerçekten yarım demek: `bitti` satırı yok, yani
            # uygulama tur ortasında kapanmış. Bunu gizleyip 0 saniye
            # yazmak kaydın söylemediği bir şeyi söylemek olurdu.
            rozetler.addWidget(_rozet(t, "unfinished", t.caution))
        rozetler.addStretch(1)

        if kosu.talimat.strip():
            yeniden = QPushButton("Run again")
            yeniden.setCursor(Qt.CursorShape.PointingHandCursor)
            yeniden.setFixedHeight(30)
            yeniden.clicked.connect(
                lambda _=False, m=kosu.talimat: self.tekrarla.emit(m)
            )
            rozetler.addWidget(yeniden)
        bd.addLayout(rozetler)
        self._ekle(bas)

        if kosu.metin.strip():
            # Ajanın cevabı ham markdown olarak kaydediliyor. Canlı
            # akışta `bicimle` işaretleri temizliyor ve geçmişte de
            # temizlenmeli: `**dosya.md**` diye bir dosya yok.
            duz, _kalin, _kod = bicimle(kosu.metin.strip())
            self._ekle(self._kart("What it said", duz, t.text))
        if kosu.desteksiz:
            self._ekle(self._kart(
                "Not backed by the log",
                "It claimed: " + ", ".join(kosu.desteksiz)
                + ".\nThe audit log has no matching tool call for this turn.",
                t.caution,
            ))

        ayrac = QWidget()
        ayrac.setFixedHeight(1)
        ayrac.setStyleSheet(f"background: {t.divider};")
        self._ekle(ayrac)

        for i, adim in enumerate(kosu.adimlar[:EN_COK_ADIM], start=1):
            self._ekle(_AdimSatiri(t, adim, i))
        if kosu.adim_sayisi > EN_COK_ADIM:
            kalan = QLabel(
                f"  {kosu.adim_sayisi - EN_COK_ADIM} more steps are in "
                f"the log but not shown here."
            )
            kalan.setStyleSheet(
                f"color: {t.text_tertiary}; font-size: 12px;"
                f" padding: 14px 20px;"
            )
            self._ekle(kalan)
        if not kosu.adimlar:
            bos = QLabel("  It did not call a single tool in this run.")
            bos.setStyleSheet(
                f"color: {t.text_tertiary}; font-size: 12px;"
                f" padding: 18px 20px;"
            )
            self._ekle(bos)

        self._kaydirma.verticalScrollBar().setValue(0)

    def _kart(self, baslik: str, govde: str, renk: str) -> QWidget:
        t = self.t
        kutu = QWidget()
        duzen = QVBoxLayout(kutu)
        duzen.setContentsMargins(20, 0, 24, 14)
        duzen.setSpacing(0)

        ic = QWidget()
        ic.setStyleSheet(
            f"background: {t.card}; border-radius: {RADIUS_CARD}px;"
            f" border-left: 3px solid {renk};"
        )
        icd = QVBoxLayout(ic)
        icd.setContentsMargins(14, 11, 14, 12)
        icd.setSpacing(4)

        ust = QLabel(baslik)
        ust.setStyleSheet(
            f"color: {renk}; font-size: 10.5px; font-weight: 700;"
            f" border: none; letter-spacing: 0.5px;"
        )
        icd.addWidget(ust)

        alt = QLabel(govde)
        alt.setWordWrap(True)
        alt.setStyleSheet(
            f"color: {t.text_secondary}; font-size: 12.5px; border: none;"
        )
        icd.addWidget(alt)
        duzen.addWidget(ic)
        return kutu


# --- sayfa ----------------------------------------------------------------


@dataclass
class _Durum:
    kosular: list[Kosu]
    secili: int = -1


class GecmisGorunumu(QWidget):
    """Geçmiş sayfası: solda koşular, sağda seçilenin tamamı."""

    tekrarla = Signal(str)

    def __init__(self, t: Tokens, kayit: Kayit | None = None,
                 gun_sayisi: int = 14) -> None:
        super().__init__()
        self.t = t
        self._kayit = kayit or Kayit()
        self._gun_sayisi = gun_sayisi
        self._durum = _Durum(kosular=[])
        self._satirlar: list[_Satir] = []
        self._suzgec = ""

        dis = QVBoxLayout(self)
        dis.setContentsMargins(0, 0, 0, 0)
        dis.setSpacing(0)
        dis.addWidget(self._baslik_seridi())

        govde = QWidget()
        yatay = QHBoxLayout(govde)
        yatay.setContentsMargins(0, 0, 0, 0)
        yatay.setSpacing(0)

        sol = QWidget()
        sol.setObjectName("gecmisListe")
        sol.setFixedWidth(LISTE_EN)
        sol.setStyleSheet(
            f"QWidget#gecmisListe, QWidget#gecmisListe QScrollArea,"
            f" QWidget#gecmisListe QWidget {{"
            f" background: {t.background_secondary}; }}"
        )
        sold = QVBoxLayout(sol)
        sold.setContentsMargins(0, 0, 0, 0)
        sold.setSpacing(0)

        self._liste_kaydirma = QScrollArea()
        self._liste_kaydirma.setWidgetResizable(True)
        self._liste_kaydirma.setFrameShape(QScrollArea.Shape.NoFrame)
        self._liste_kaydirma.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._liste = QWidget()
        self._liste_duzen = QVBoxLayout(self._liste)
        self._liste_duzen.setContentsMargins(0, 4, 0, 16)
        self._liste_duzen.setSpacing(0)
        self._liste_duzen.addStretch(1)
        self._liste_kaydirma.setWidget(self._liste)
        sold.addWidget(self._liste_kaydirma, 1)
        yatay.addWidget(sol)

        cizgi = QWidget()
        cizgi.setFixedWidth(1)
        cizgi.setStyleSheet(f"background: {t.divider};")
        yatay.addWidget(cizgi)

        self._ayrinti = _Ayrinti(t)
        self._ayrinti.tekrarla.connect(self.tekrarla.emit)
        yatay.addWidget(self._ayrinti, 1)
        dis.addWidget(govde, 1)

        self.yenile()

    # --- başlık ------------------------------------------------------------

    def _baslik_seridi(self) -> QWidget:
        t = self.t
        serit = QWidget()
        serit.setObjectName("gecmisBaslik")
        serit.setFixedHeight(52)
        # Seçici nesne adına bağlı: kapsamsız bir kural şeridin
        # `border-bottom`'ını içindeki etiketlere de uyguluyor ve
        # başlığın altında açık bir bant bırakıyordu.
        serit.setStyleSheet(
            f"QWidget#gecmisBaslik {{ background: {t.background};"
            f" border-bottom: 1px solid {t.divider}; }}"
        )
        duzen = QHBoxLayout(serit)
        duzen.setContentsMargins(20, 0, 16, 0)
        duzen.setSpacing(12)

        baslik = QLabel("History")
        baslik.setStyleSheet(
            f"color: {t.text}; font-size: 15px; font-weight: 600;"
            f" font-family: '{t.font_display}', '{t.font_ui}'; border: none;"
        )
        duzen.addWidget(baslik)

        self._sayac = QLabel()
        self._sayac.setStyleSheet(
            f"color: {t.text_tertiary}; font-size: 12px; border: none;"
        )
        duzen.addWidget(self._sayac)
        duzen.addStretch(1)

        self._arama = QLineEdit()
        self._arama.setPlaceholderText("Filter by instruction")
        self._arama.setFixedWidth(220)
        self._arama.setFixedHeight(30)
        self._arama.setClearButtonEnabled(True)
        self._arama.textChanged.connect(self._suz)
        duzen.addWidget(self._arama)

        tazele = QPushButton("Refresh")
        tazele.setFixedHeight(30)
        tazele.setCursor(Qt.CursorShape.PointingHandCursor)
        tazele.clicked.connect(self.yenile)
        duzen.addWidget(tazele)
        return serit

    # --- veri --------------------------------------------------------------

    def yenile(self) -> None:
        """Kaydı diskten yeniden okur.

        Elle tazeleniyor, dosyayı izleyerek değil. Ajan çalışırken kayda
        saniyede birkaç satır düşüyor ve her satırda listeyi yeniden
        kurmak, bakılmayan bir sayfa için sürekli iş demekti.
        """
        try:
            satirlar = self._kayit.satirlar(self._gun_sayisi)
        except OSError:
            satirlar = []
        self._durum = _Durum(kosular=kosulari_derle(satirlar)[:EN_COK_KOSU])
        self._kur()

    def _suz(self, metin: str) -> None:
        self._suzgec = metin.strip().lower()
        self._kur()

    def _gorunenler(self) -> list[tuple[int, Kosu]]:
        if not self._suzgec:
            return list(enumerate(self._durum.kosular))
        return [
            (i, k) for i, k in enumerate(self._durum.kosular)
            if self._suzgec in k.talimat.lower()
        ]

    def _kur(self) -> None:
        while self._liste_duzen.count() > 1:
            oge = self._liste_duzen.takeAt(0)
            if oge.widget() is not None:
                oge.widget().deleteLater()
        self._satirlar = []

        gorunen = self._gorunenler()
        toplam = len(self._durum.kosular)
        self._sayac.setText(
            f"{toplam} runs · last {self._gun_sayisi} days"
            + (f" · {len(gorunen)} shown" if self._suzgec else "")
        )

        son_gun = ""
        for sira, kosu in gorunen:
            gun = _gun_adi(kosu.baslangic)
            if gun != son_gun:
                son_gun = gun
                self._liste_duzen.insertWidget(
                    self._liste_duzen.count() - 1, _GunSatiri(self.t, gun)
                )
            satir = _Satir(self.t, kosu, sira)
            satir.secildi.connect(self.sec)
            self._liste_duzen.insertWidget(
                self._liste_duzen.count() - 1, satir
            )
            self._satirlar.append(satir)

        if not self._durum.kosular:
            self._ayrinti.bos_goster(
                "Nothing has run yet",
                "Every turn the agent takes is written to runs/ as it "
                "happens — the instruction, each tool call and how it "
                "ended. Once you have given it a job, it shows up here "
                "and stays there after the app closes."
            )
        elif not gorunen:
            self._ayrinti.bos_goster(
                "No match",
                f"No run in the last {self._gun_sayisi} days has "
                f"{self._suzgec!r} in its instruction."
            )
        else:
            self.sec(gorunen[0][0])

    def sec(self, sira: int) -> None:
        if not (0 <= sira < len(self._durum.kosular)):
            return
        self._durum.secili = sira
        for satir in self._satirlar:
            satir.set_etkin(satir.sira == sira)
        self._ayrinti.goster(self._durum.kosular[sira])

    @property
    def secili(self) -> int:
        return self._durum.secili
