"""Etkinlik görünümü — ajanın bilgisayarda ne yaptığı.

Ana pencerenin merkezinde bu var, bir ofis paketi değil. Ajan bütün
bilgisayarı kullanıyor: tıklıyor, yazıyor, terminal açıyor, dosya
düzenliyor, uygulama başlatıyor. Sabit dört ofis paneli bu ürünün ne
olduğunu yanlış anlatıyordu.

Her adım bir satır: ne yaptığı, neye yaptığı, neden yaptığı ve — ekran
görüntüsü aldıysa — gerçekten ne gördüğü. Ekran görüntüsü tıklanabilir;
büyütünce ajanın o adımda gördüğü tam kare açılıyor.

Belgeler ve terminaller ayrı panel olarak yalnızca ajan onları açtığında
beliriyor. Boş bir tablo paneli, ajanın tablo üstünde çalıştığını
sanmana yol açardı.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .fluent import RADIUS_CARD, RADIUS_CONTROL, Tokens
from .glyphs import WorkGlyph


#: Boşluksuz uzun parçalardan sonra satır sonu izni verilen karakterler.
#: Bir Windows yolu ya da bir hücre formülü tek bir kelime sayılıyor ve
#: `setWordWrap` onu bölemiyor; bölemeyince de listeyi genişletip pencereyi
#: ekranın dışına itiyor.
BREAK_AFTER = "/\\!:,;)]}$_-"

#: Bir parça bu uzunluğu geçtiyse arasına satır sonu izni serpiliyor.
CHUNK = 14


def _breakable(text: str) -> str:
    """Uzun ve boşluksuz parçalara sıfır genişlikli boşluk serpiştirir."""
    out: list[str] = []
    since = 0
    for ch in text:
        out.append(ch)
        since += 1
        if ch.isspace():
            since = 0
        elif ch in BREAK_AFTER or since >= CHUNK:
            out.append("​")
            since = 0
    return "".join(out)


class FrameDialog(QDialog):
    """Ajanın o adımda gördüğü tam kare."""

    def __init__(self, pixmap: QPixmap, title: str, t: Tokens, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setStyleSheet(f"background: {t.background};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        label = QLabel()
        label.setPixmap(
            pixmap.scaled(
                1280, 800,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        layout.addWidget(label)


class Step(QWidget):
    """Tek bir eylem."""

    frame_clicked = Signal(QPixmap, str)

    def __init__(self, t: Tokens, label: str, target: str, detail: str,
                 tool: str = "") -> None:
        super().__init__()
        self.t = t
        self._pixmap: QPixmap | None = None
        self._label = label

        self.setStyleSheet(f"border-bottom: 1px solid {t.divider};")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(14)

        # İşin çizimi her adımda var; ekran görüntüsü yalnızca bazılarında.
        # Liste bu yüzden çizimle hizalanıyor, kareyle değil.
        self.glyph = WorkGlyph(t, tool or "__sen__", 38)
        self.glyph.setStyleSheet("border: none;")
        layout.addWidget(self.glyph, 0, Qt.AlignmentFlag.AlignTop)

        self.thumb = QLabel()
        self.thumb.setFixedSize(128, 76)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setVisible(False)
        self.thumb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.thumb.setStyleSheet(
            f"border: 1px solid {t.stroke}; border-radius: {RADIUS_CONTROL}px;"
        )
        self.thumb.mousePressEvent = self._open_frame
        layout.addWidget(self.thumb)

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(3)

        head = QLabel(_breakable(f"{label}  ·  {target}" if target else label))
        head.setStyleSheet(
            f"color: {t.text}; font-size: 13px; font-weight: 600; border: none;"
        )
        head.setWordWrap(True)
        column.addWidget(head)

        if detail:
            body = QLabel(_breakable(detail))
            body.setWordWrap(True)
            body.setStyleSheet(
                f"color: {t.text_secondary}; font-size: 12px; border: none;"
            )
            column.addWidget(body)

        self._note = QLabel()
        self._note.setWordWrap(True)
        self._note.setVisible(False)
        column.addWidget(self._note)
        column.addStretch(1)
        layout.addLayout(column, 1)

    def set_frame(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self.thumb.setPixmap(
            pixmap.scaled(
                126, 74,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.thumb.setVisible(True)

    def set_note(self, text: str, error: bool = False) -> None:
        colour = self.t.critical if error else self.t.text_tertiary
        self._note.setText(text)
        self._note.setStyleSheet(f"color: {colour}; font-size: 12px; border: none;")
        self._note.setVisible(bool(text))

    def _open_frame(self, _event) -> None:
        if self._pixmap is not None:
            self.frame_clicked.emit(self._pixmap, self._label)


class ActivityView(QWidget):
    """Adımların akışı. Yeni adım eklendikçe sona kayıyor."""

    def __init__(self, t: Tokens) -> None:
        super().__init__()
        self.t = t
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        # Yatay kaydırma kapalı. Bir hücre formülü ya da uzun bir Windows
        # yolu boşluk içermediği için satır sonu bulamıyor ve listeyi
        # genişletiyordu; pencere de onunla birlikte ekranın dışına taşıyordu.
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        outer.addWidget(self._scroll, 1)

        self._body = QWidget()
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addStretch(1)
        self._scroll.setWidget(self._body)

        self._empty = self._empty_state(t)
        self._layout.insertWidget(0, self._empty)
        self._last: Step | None = None

    def _empty_state(self, t: Tokens) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(48, 64, 48, 48)
        layout.setSpacing(10)

        title = QLabel("Ajan hazır")
        title.setStyleSheet(
            f"color: {t.text}; font-family: '{t.font_display}', '{t.font_ui}';"
            f" font-size: 24px; font-weight: 600;"
        )
        layout.addWidget(title)

        body = QLabel(
            "Köşedeki çubuğa yaz. Ajan bilgisayarı senin adına kullanır: "
            "uygulama açar, tıklar, yazar, terminal çalıştırır, dosya ve "
            "belge düzenler.\n\n"
            "Yaptığı her adım burada görünür — ne yaptığı, neye yaptığı ve "
            "ekran görüntüsü aldıysa tam olarak ne gördüğü. Bir kareye "
            "tıklarsan büyür.\n\n"
            "Belgeler ve terminaller ancak ajan onları açtığında ayrı panel "
            "olarak belirir."
        )
        body.setWordWrap(True)
        body.setMaximumWidth(560)
        body.setStyleSheet(
            f"color: {t.text_secondary}; font-size: 14px; line-height: 150%;"
        )
        layout.addWidget(body)
        layout.addStretch(1)
        return box

    def add_step(self, label: str, target: str, detail: str,
                 tool: str = "") -> Step:
        self._empty.setVisible(False)
        step = Step(self.t, label, target, detail, tool)
        step.frame_clicked.connect(self._show_frame)
        self._layout.insertWidget(self._layout.count() - 1, step)
        self._last = step
        # Yeni adım eklenince sona kaydır: uzun bir koşuda kullanıcının
        # elle takip etmesi gerekmesin.
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        return step

    def annotate_last(self, text: str, error: bool = False) -> None:
        if self._last is not None:
            self._last.set_note(text, error)
            if error:
                self._last.glyph.set_tone("hata")

    def frame_last(self, png: bytes) -> None:
        if self._last is None:
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(png, "PNG"):
            self._last.set_frame(pixmap)

    def clear(self) -> None:
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget() and item.widget() is not self._empty:
                item.widget().deleteLater()
        self._last = None
        self._empty.setVisible(True)
        self._layout.insertWidget(0, self._empty)

    def _show_frame(self, pixmap: QPixmap, title: str) -> None:
        FrameDialog(pixmap, title, self.t, self).exec()
