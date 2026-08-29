"""Akışlar sayfası — kaydedilmiş işler ve onları oynatan düğme.

Bir akış, ajanın bir kez yaptığı işin kaydı. Oynatmak modele hiç
uğramıyor: token yok, düşünme yok, ekran görüntüsü yok. Bu sayfanın
varlık sebebi de bu — kaydedilmiş bir akışı çalıştırmak için ajanı
uyandırmak, ücretsiz olanı ücretli yapmak olurdu.

Her kart üç şeyi söylüyor ve üçü de kararı etkiliyor:

- **Kaç adım.** Otuz adımlık bir akış oynatılırken ekranı otuz kez
  değiştiriyor; iki adımlıkla aynı şey değil.
- **Hangi cümleden doğdu.** Aylar sonra `fatura_indir` adına bakıp ne
  yaptığını hatırlamanın tek yolu bu.
- **Kaç adımın imzası var.** İmzası olan adım taşınmış bir düğmeyi
  yeniden buluyor; olmayan kayıtlı koordinata tıklıyor. Pencereyi
  taşımadan çalıştırmak gerektiğini bilmek, akışın ortasında
  öğrenmekten iyi.

Silme geri alınamıyor ve onay soruluyor. Yanlış tıklanan bir çöp
kutusu simgesiyle kaybedilecek şey, tekrar kaydedilmesi bir koşu
sürecek bir iş.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from backend.workflows.depo import Akis
from backend.workflows.oynatici import KOORDINATLI

from .fluent import RADIUS_CARD, Tokens, _blend, sarmali
from .glyphs import WorkGlyph


def _tarih(ts: float) -> str:
    return time.strftime("%d %b %Y", time.localtime(ts)) if ts else "unknown"


def _imzali(akis: Akis) -> int:
    return sum(1 for a in akis.adimlar if a.imza is not None)


def _onarilabilir(akis: Akis) -> int:
    """Kaç adım taşınmış bir denetimi yeniden bulabilir."""
    return sum(
        1 for a in akis.adimlar
        if a.imza is not None and a.arac in KOORDINATLI
    )


class _Kart(QWidget):
    """Tek bir akış."""

    oynat = Signal(str)
    sil = Signal(str)

    def __init__(self, t: Tokens, akis: Akis) -> None:
        super().__init__()
        self.t, self.akis = t, akis
        self.setObjectName("akisKarti")
        self.setStyleSheet(
            f"QWidget#akisKarti {{ background: {t.card};"
            f" border: 1px solid {t.stroke};"
            f" border-radius: {RADIUS_CARD}px; }}"
        )
        duzen = QHBoxLayout(self)
        duzen.setContentsMargins(16, 14, 14, 14)
        duzen.setSpacing(14)

        duzen.addWidget(WorkGlyph(t, "workflow_save", 38), 0,
                        Qt.AlignmentFlag.AlignTop)

        sutun = QVBoxLayout()
        sutun.setContentsMargins(0, 0, 0, 0)
        sutun.setSpacing(3)

        baslik = QLabel(akis.etiket)
        baslik.setStyleSheet(
            f"color: {t.text}; font-size: 14px; font-weight: 600;"
            f" border: none;"
        )
        sutun.addWidget(baslik)

        onarilabilir = _onarilabilir(akis)
        parcalar = [
            akis.ad,
            f"{akis.adim_sayisi} steps",
            _tarih(akis.olusturuldu),
        ]
        if onarilabilir:
            parcalar.append(f"{onarilabilir} can re-find their control")
        alt = QLabel("  ·  ".join(parcalar))
        alt.setStyleSheet(
            f"color: {t.text_tertiary}; font-size: 11.5px; border: none;"
        )
        sutun.addWidget(alt)

        if akis.talimat.strip():
            kaynak = QLabel(f"from: {akis.talimat.strip()}")
            kaynak.setWordWrap(True)
            kaynak.setStyleSheet(
                f"color: {t.text_secondary}; font-size: 12px;"
                f" border: none; padding-top: 3px;"
            )
            sutun.addWidget(kaynak)
        duzen.addLayout(sutun, 1)

        dugmeler = QVBoxLayout()
        dugmeler.setSpacing(6)
        calistir = QPushButton("Run")
        calistir.setFixedSize(74, 30)
        calistir.setCursor(Qt.CursorShape.PointingHandCursor)
        calistir.setToolTip(
            "Replays the recorded steps. No model call, no cost."
        )
        calistir.clicked.connect(lambda: self.oynat.emit(akis.ad))
        dugmeler.addWidget(calistir)

        kaldir = QPushButton("Delete")
        kaldir.setFixedSize(74, 28)
        kaldir.setCursor(Qt.CursorShape.PointingHandCursor)
        kaldir.clicked.connect(self._sor)
        dugmeler.addWidget(kaldir)
        dugmeler.addStretch(1)
        duzen.addLayout(dugmeler)

    def _sor(self) -> None:
        # Geri alınamayan bir şey soruluyor. Tekrar kaydetmek bir koşu
        # sürer ve o koşu para harcar.
        cevap = QMessageBox.question(
            self, "Delete the workflow",
            f"Delete {self.akis.etiket!r}? Its {self.akis.adim_sayisi} "
            f"recorded steps go with it and this cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if cevap == QMessageBox.StandardButton.Yes:
            self.sil.emit(self.akis.ad)


class AkisGorunumu(QWidget):
    """Kayıtlı akışların listesi."""

    oynat = Signal(str)

    def __init__(self, t: Tokens, depo_ver) -> None:
        super().__init__()
        self.t = t
        #: Depo çağrılabilir olarak alınıyor: sayfa uygulama açılırken
        #: kuruluyor, ajan saniyeler sonra. Depo o an alınıp saklansaydı
        #: sayfa ömrü boyunca ajanınkinden farklı bir depoya bakardı.
        self._depo_ver = depo_ver

        dis = QVBoxLayout(self)
        dis.setContentsMargins(0, 0, 0, 0)
        dis.setSpacing(0)
        dis.addWidget(self._baslik_seridi())

        self._kaydirma = QScrollArea()
        self._kaydirma.setWidgetResizable(True)
        self._kaydirma.setFrameShape(QScrollArea.Shape.NoFrame)
        self._kaydirma.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._govde = QWidget()
        self._duzen = QVBoxLayout(self._govde)
        self._duzen.setContentsMargins(20, 18, 20, 24)
        self._duzen.setSpacing(10)
        self._duzen.addStretch(1)
        self._kaydirma.setWidget(self._govde)
        dis.addWidget(self._kaydirma, 1)

        self.yenile()

    def _baslik_seridi(self) -> QWidget:
        t = self.t
        serit = QWidget()
        serit.setObjectName("akisBaslik")
        serit.setFixedHeight(52)
        serit.setStyleSheet(
            f"QWidget#akisBaslik {{ background: {t.background};"
            f" border-bottom: 1px solid {t.divider}; }}"
        )
        duzen = QHBoxLayout(serit)
        duzen.setContentsMargins(20, 0, 16, 0)
        duzen.setSpacing(12)

        baslik = QLabel("Workflows")
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

        tazele = QPushButton("Refresh")
        tazele.setFixedHeight(30)
        tazele.setCursor(Qt.CursorShape.PointingHandCursor)
        tazele.clicked.connect(self.yenile)
        duzen.addWidget(tazele)
        return serit

    # --- veri --------------------------------------------------------------

    def _depo(self):
        return self._depo_ver()

    def yenile(self) -> None:
        while self._duzen.count() > 1:
            oge = self._duzen.takeAt(0)
            if oge.widget() is not None:
                oge.widget().deleteLater()

        akislar = self._depo().hepsi()
        self._sayac.setText(
            f"{len(akislar)} saved" if akislar else "none saved yet"
        )
        if not akislar:
            self._duzen.insertWidget(0, self._bos_durum())
            return
        for sira, akis in enumerate(akislar):
            kart = _Kart(self.t, akis)
            kart.oynat.connect(self.oynat.emit)
            kart.sil.connect(self._sil)
            self._duzen.insertWidget(sira, kart)

    def _sil(self, ad: str) -> None:
        self._depo().sil(ad)
        self.yenile()

    def _bos_durum(self) -> QWidget:
        t = self.t
        kutu = QWidget()
        duzen = QVBoxLayout(kutu)
        duzen.setContentsMargins(20, 40, 20, 20)
        duzen.setSpacing(12)

        baslik = QLabel("No workflows yet")
        baslik.setStyleSheet(
            f"color: {t.text}; font-size: 22px; font-weight: 600;"
            f" font-family: '{t.font_display}', '{t.font_ui}';"
        )
        duzen.addWidget(baslik)

        govde = QLabel(
            "A workflow is a job the agent already did once, recorded as "
            "the exact actions it took. Replaying one calls no model at "
            "all: no thinking, no screenshots, nothing to pay for.\n\n"
            "To make one, give the agent a job and — once it finishes "
            "cleanly — tell it to remember it. It saves the steps that "
            "changed something and drops the looking around.\n\n"
            "Where a click landed on a real button, the button's "
            "accessibility identity is recorded too, so the workflow "
            "still works after the window moves."
        )
        govde.setStyleSheet(
            f"color: {t.text_secondary}; font-size: 13.5px; line-height: 155%;"
        )
        duzen.addWidget(sarmali(govde, 560))

        ipucu = QLabel('Try: "remember this as a workflow"')
        ipucu.setMaximumWidth(560)
        ipucu.setStyleSheet(
            f"color: {t.accent_text};"
            f" background: {_blend(t.accent, 0.10, t.background)};"
            f" border-radius: {RADIUS_CARD}px; padding: 10px 14px;"
            f" font-size: 13px;"
        )
        duzen.addWidget(ipucu)
        duzen.addStretch(1)
        return kutu
