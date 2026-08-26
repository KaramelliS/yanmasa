"""Ajanın kurduğu panelin çizimi.

Yetenek ne göstereceğini söylüyor, buradaki kod nasıl görüneceğine karar
veriyor. Ayrım kasıtlı: ajanın eklediği bir özellik uygulamanın geri
kalanından ayırt edilemesin. Aynı Fluent renkleri, aynı 8 piksel yarıçap,
aynı çizimler, aynı tipografi.

Durum renkleri yeteneğin elinde değil. Yetenek "kötü" diyor, rengi tema
veriyor — açık temaya geçildiğinde ajanın yazdığı hiçbir panelin
düzeltilmesi gerekmiyor.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .fluent import GAP, RADIUS_CARD, RADIUS_CONTROL, Tokens
from .glyphs import GLYPHS, glyph_icon


#: Bir ölçü değerinde gösterilecek en fazla karakter.
MAX_METRIC = 18

#: Tablo ölçüleri. Stil sayfasındaki değerlerle aynı olmalı.
ROW_HEIGHT = 24
HEADER_HEIGHT = 28


def _elide(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def tone_colour(t: Tokens, tone: str) -> str:
    return {
        "iyi": t.success,
        "uyari": t.caution,
        "kotu": t.critical,
    }.get(tone, t.text)


class FlowLayout(QLayout):
    """Sığdığı kadar yan yana, sonra alt satıra.

    Qt'de hazır yok. Ölçü rozetleri için doğru davranış bu: pencere
    daraldığında kesilmiyorlar, alt satıra iniyorlar.
    """

    def __init__(self, hgap: int, vgap: int) -> None:
        super().__init__()
        self._items: list = []
        self._hgap, self._vgap = hgap, vgap
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientations:
        return Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._lay(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._lay(rect, apply=True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _lay(self, rect: QRect, apply: bool) -> int:
        x, y, satir = rect.x(), rect.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            if x > rect.x() and x + hint.width() > rect.right():
                x = rect.x()
                y += satir + self._vgap
                satir = 0
            if apply:
                item.setGeometry(QRect(x, y, hint.width(), hint.height()))
            x += hint.width() + self._hgap
            satir = max(satir, hint.height())
        return y + satir - rect.y()


class Card(QWidget):
    """Bölümlerin oturduğu kart."""

    #: Her kartın kendi nesne adı var ve biçim ona bağlanıyor. Seçicisiz
    #: bir stil sayfası çocuklara da uygulanıyor: her ölçünün, her satırın
    #: etrafında kartın çerçevesi beliriyordu.
    _serial = 0

    def __init__(self, t: Tokens, title: str) -> None:
        super().__init__()
        Card._serial += 1
        name = f"kart{Card._serial}"
        self.setObjectName(name)
        # Qt tuzağı: `QWidget` türevi bir sınıf, bu bayrak olmadan stil
        # sayfasındaki zemini ve çerçeveyi hiç boyamıyor. Seçicisiz stil
        # çalışıyor gibi görünüyordu çünkü boyanan kartın kendisi değil,
        # çerçeveyi miras alan çocuklarıydı.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#{name} {{ background: {t.card};"
            f" border: 1px solid {t.stroke};"
            f" border-radius: {RADIUS_CARD}px; }}"
        )
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(GAP * 3, GAP * 2, GAP * 3, GAP * 2)
        self.box.setSpacing(GAP)
        if title:
            head = QLabel(title)
            head.setStyleSheet(
                f"color: {t.text_secondary}; font-size: 11px; font-weight: 600;"
                f" letter-spacing: 0.4px; border: none;"
            )
            self.box.addWidget(head)


class Metric(QWidget):
    """Tek bir ölçü: büyük değer, altında etiket."""

    def __init__(self, t: Tokens, item: dict) -> None:
        super().__init__()
        self.setStyleSheet("border: none;")
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, GAP * 4, 0)
        box.setSpacing(1)

        # Değer sarmıyor. Uzun bir değer dört satıra yayılıp ölçü satırının
        # ritmini bozuyordu; artık kısaltılıyor ve tamamı ipucunda.
        deger = item["deger"]
        value = QLabel(_elide(deger, MAX_METRIC))
        value.setToolTip(deger if len(deger) > MAX_METRIC else "")
        value.setStyleSheet(
            f"color: {tone_colour(t, item['durum'])}; border: none;"
            f" font-family: '{t.font_display}', '{t.font_ui}';"
            f" font-size: 19px; font-weight: 600;"
        )
        box.addWidget(value)

        label = QLabel(item["etiket"])
        label.setStyleSheet(
            f"color: {t.text_tertiary}; font-size: 11px; border: none;"
        )
        box.addWidget(label)


class SkillPanel(QWidget):
    """Bir yeteneğin ürettiği panel."""

    def __init__(self, t: Tokens, panel: dict) -> None:
        super().__init__()
        self.t = t
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll, 1)

        body = QWidget()
        body.setStyleSheet(f"background: {t.background};")
        column = QVBoxLayout(body)
        column.setContentsMargins(GAP * 3, GAP * 3, GAP * 3, GAP * 3)
        column.setSpacing(GAP * 2)

        title = QLabel(panel["baslik"])
        title.setWordWrap(True)
        title.setStyleSheet(
            f"color: {t.text}; font-family: '{t.font_display}', '{t.font_ui}';"
            f" font-size: 20px; font-weight: 600;"
        )
        column.addWidget(title)

        if panel.get("alt"):
            sub = QLabel(panel["alt"])
            sub.setWordWrap(True)
            sub.setStyleSheet(f"color: {t.text_secondary}; font-size: 13px;")
            column.addWidget(sub)

        for bolum in panel["bolumler"]:
            column.addWidget(self._section(bolum))
        column.addStretch(1)
        scroll.setWidget(body)

    def _section(self, bolum: dict) -> QWidget:
        card = Card(self.t, bolum.get("baslik", ""))
        tur = bolum["tur"]
        if tur == "olcu":
            # Akan yerleşim: ölçüler sığdığı kadar yan yana, sonra alt
            # satıra. Tek satırlık bir düzen altı ölçüyü panelin sağından
            # taşırıp kesiyordu.
            flow = FlowLayout(GAP * 4, GAP * 2)
            for item in bolum["ogeler"]:
                flow.addWidget(Metric(self.t, item))
            card.box.addLayout(flow)
        elif tur == "tablo":
            card.box.addWidget(self._table(bolum))
        elif tur == "liste":
            for item in bolum["ogeler"]:
                card.box.addWidget(self._row(item))
        elif tur == "gunluk":
            card.box.addWidget(self._log(bolum["satirlar"]))
        else:
            text = QLabel(bolum["icerik"])
            text.setWordWrap(True)
            text.setStyleSheet(
                f"color: {self.t.text_secondary}; font-size: 13px;"
                f" line-height: 150%; border: none;"
            )
            card.box.addWidget(text)
        return card

    def _table(self, bolum: dict) -> QWidget:
        t = self.t
        headers = bolum["basliklar"]
        rows = bolum["satirlar"]
        width = max([len(headers)] + [len(r) for r in rows] or [1])

        tree = QTreeWidget()
        tree.setColumnCount(width)
        tree.setHeaderLabels(headers or [""] * width)
        tree.setHeaderHidden(not headers)
        tree.setRootIsDecorated(False)
        tree.setUniformRowHeights(True)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tree.setStyleSheet(
            f"QTreeWidget {{ background: transparent; border: none;"
            f" color: {t.text}; font-size: 12px; }}"
            f"QTreeWidget::item {{ height: 24px; border: none; }}"
            f"QHeaderView::section {{ background: transparent; border: none;"
            f" border-bottom: 1px solid {t.divider}; padding: 4px 6px;"
            f" color: {t.text_secondary}; font-size: 11px; font-weight: 600; }}"
        )
        for row in rows:
            tree.addTopLevelItem(QTreeWidgetItem(row + [""] * (width - len(row))))
        header = tree.header()
        for column in range(width):
            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.Stretch if column == 0
                else QHeaderView.ResizeMode.ResizeToContents,
            )
        # Yükseklik satır sayısına göre: kaydırma çubuklu küçük bir kutu,
        # altı satırlık bir tabloyu okunmaz hâle getiriyor. Başlık ve kenar
        # payı eklenmezse son satır kırpılıyor ve tabloda daha çok şey
        # varmış gibi görünüyor.
        gorunen = min(len(rows), 14)
        tree.setFixedHeight(gorunen * ROW_HEIGHT + (HEADER_HEIGHT if headers else 0) + 6)
        if gorunen == len(rows):
            tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return tree

    def _row(self, item: dict) -> QWidget:
        t = self.t
        box = QWidget()
        box.setStyleSheet("border: none;")
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(10)

        icon = QLabel()
        cizim = item["cizim"] if item["cizim"] in GLYPHS else "sayfa"
        icon.setPixmap(
            glyph_icon(cizim, 16, tone_colour(t, item["durum"])
                       if item["durum"] != "notr" else t.accent,
                       t.text_tertiary).pixmap(QSize(16, 16))
        )
        icon.setStyleSheet("border: none;")
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        column = QVBoxLayout()
        column.setSpacing(1)
        head = QLabel(item["baslik"])
        head.setWordWrap(True)
        head.setStyleSheet(
            f"color: {t.text}; font-size: 13px; font-weight: 600; border: none;"
        )
        column.addWidget(head)
        if item["alt"]:
            sub = QLabel(item["alt"])
            sub.setWordWrap(True)
            sub.setStyleSheet(
                f"color: {t.text_secondary}; font-size: 12px; border: none;"
            )
            column.addWidget(sub)
        row.addLayout(column, 1)

        if item["sag"]:
            right = QLabel(item["sag"])
            right.setStyleSheet(
                f"color: {tone_colour(t, item['durum'])}; font-size: 12px;"
                f" border: none;"
            )
            row.addWidget(right, 0, Qt.AlignmentFlag.AlignTop)
        return box

    def _log(self, satirlar: list[str]) -> QWidget:
        t = self.t
        label = QLabel("\n".join(satirlar))
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setStyleSheet(
            f"color: {t.text_secondary}; font-family: '{t.font_mono}';"
            f" font-size: 11px; background: {t.background_secondary};"
            f" border: 1px solid {t.stroke};"
            f" border-radius: {RADIUS_CONTROL}px; padding: 8px 10px;"
        )
        return label
