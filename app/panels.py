"""Kasa gözleri — tablo, yazı, kod, terminal ve tashih marjı.

Hepsi gerçek Qt görünümleri. Tablo bir `QTableView`: yüz bin satırı da
akıcı çizer, hücreye tıklanır, kopyalanır. Bir web ızgarasını taklit etmek
yerine platformun kendi tablosunu kullanmak, bu ürünün her katmanda
tekrarladığı seçim — piksel taklidi değil, yerel API.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal


def _accent_wash(alpha: int = 38) -> tuple[int, int, int, int]:
    """Ajanın dokunduğu yerin işareti: sistem vurgu rengi, yıkama olarak."""
    c = T.accent.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), alpha
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableView,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .fluent import Tokens

T: Tokens | None = None


def set_tokens(tokens: Tokens) -> None:
    global T
    T = tokens


def kicker(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "caption")
    return label


def meta(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "tertiary")
    return label


def footer(*widgets: QWidget) -> QWidget:
    """Panel altı ölçü şeridi: her gözde aynı yerde, aynı ritimde."""
    bar = QWidget()
    bar.setStyleSheet(f"border-top: 1px solid {T.divider};")
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(4 * 2, 4, 4 * 2, 4)
    layout.setSpacing(4 * 4)
    for widget in widgets:
        layout.addWidget(widget)
    layout.addStretch(1)
    return bar


# --- Tablo -----------------------------------------------------------------


@dataclass
class Cell:
    value: str
    formula: bool = False
    why: str | None = None


class SheetModel(QAbstractTableModel):
    """Ajanın dokunduğu hücre işaretli; gerekçesi araç ipucunda.

    Değişikliği yalnızca marjda listelemek, "hangi hücreydi" sorusunu
    kullanıcıya bıraktırırdı. İşaret hücrenin kendisinde duruyor.
    """

    def __init__(self, rows: list[list[Cell]], columns: list[str]) -> None:
        super().__init__()
        self._rows = rows
        self._columns = columns

    #: Veriden sonra çizilecek boş satır. Bir hesap tablosu boş ızgarasıyla
    #: birlikte okunur; veri bitince yüzeyin boşluğa dönmesi onu tablo
    #: olmaktan çıkarıyor.
    PADDING_ROWS = 24

    def rowCount(self, _parent=QModelIndex()) -> int:
        return len(self._rows) + self.PADDING_ROWS

    def columnCount(self, _parent=QModelIndex()) -> int:
        return len(self._columns)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if index.row() >= len(self._rows):
            return None  # boş ızgara satırı
        cell = self._rows[index.row()][index.column()]

        if role == Qt.ItemDataRole.DisplayRole:
            return cell.value
        if role == Qt.ItemDataRole.ToolTipRole:
            return cell.why
        if role == Qt.ItemDataRole.BackgroundRole and cell.why:
            return QColor(*_accent_wash())
        if role == Qt.ItemDataRole.ForegroundRole and cell.formula:
            return QColor(T.text_secondary)
        if role == Qt.ItemDataRole.FontRole and cell.formula:
            font = QFont(T.font_mono)
            font.setPointSize(9)
            return font
        if role == Qt.ItemDataRole.TextAlignmentRole and cell.value.isdigit():
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self._columns[section]
        return str(section + 1)


class SheetPanel(QWidget):
    def __init__(self, rows: list[list[Cell]], columns: list[str], sheet: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        view = QTableView()
        view.setModel(SheetModel(rows, columns))
        view.setShowGrid(True)
        view.setAlternatingRowColors(False)
        view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        view.verticalHeader().setDefaultSectionSize(26)
        view.verticalHeader().setFixedWidth(34)
        view.setSelectionBehavior(QTableView.SelectionBehavior.SelectItems)
        layout.addWidget(view, 1)

        formulas = sum(1 for row in rows for c in row if c.formula)
        bits = [meta(sheet)]
        if formulas:
            # Hesaplanmamış formülü gizlemek, sonucun bilindiği yanılgısını
            # üretir. Açıkça söyleniyor.
            warn = QLabel(f"{formulas} formül hesaplanmadı")
            warn.setProperty("role", "critical")
            
            bits.append(warn)
        layout.addWidget(footer(*bits))


# --- Yazı belgesi ----------------------------------------------------------


@dataclass
class Para:
    text: str
    style: str = "Normal"
    why: str | None = None


class DocPanel(QTextBrowser):
    """Word sayfası: gri tezgâh üstünde beyaz bir kâğıt.

    Belge arayüzün bir paneli değil, üstünde duran bir kâğıt. Word koyu
    temada bile sayfayı beyaz gösteriyor ve bunun sebebi doğru: bastığında
    ya da birine yolladığında göreceğin şey bu. Sayfayı temaya boyamak,
    belgenin gerçek halini gizler.

    Ajanın yazdığı paragraflar solda ince bir vurgu kuralıyla işaretli —
    Word'ün değişiklik izleme çubuğu gibi.
    """

    def __init__(self, paragraphs: list[Para]) -> None:
        super().__init__()
        self.setOpenExternalLinks(False)
        self.setStyleSheet(
            f"""
            QTextBrowser {{
                background: {T.background_secondary};
                border: none;
                padding: 0;
                selection-background-color: {T.accent};
                selection-color: {T.on_accent};
            }}
            """
        )
        sizes = {"Title": 26, "Heading 1": 18, "Heading 2": 15, "Normal": 13}
        colours = {
            "Title": "#1a1a1a",
            "Heading 1": "#2b579a",  # Word'ün kendi başlık mavisi
            "Heading 2": "#2b579a",
            "Normal": "#1a1a1a",
        }
        face = "font-family: Calibri, 'Segoe UI', sans-serif;"

        # Değişiklik çubuğu tabloyla çiziliyor, `border-left` ile değil:
        # Qt'nin zengin metin motoru blok kenarlıklarını sessizce yok
        # sayıyor. İlk sürüm border-left kullanıyordu ve ajanın hangi
        # paragrafı değiştirdiği hiç görünmüyordu — bu ürünün ayırt edici
        # özelliğinin görünmez olması demekti.
        blocks = []
        for para in paragraphs:
            weight = "600" if para.style != "Normal" else "400"
            space = "18px" if para.style in ("Heading 1", "Heading 2") else "10px"
            body = (
                f'<p style="{face} font-size:{sizes[para.style]}px;'
                f' font-weight:{weight}; color:{colours[para.style]};'
                f' line-height:160%; margin:0;">{para.text}</p>'
            )
            bar = T.accent if para.why else "#ffffff"
            blocks.append(
                f'<table width="100%" cellpadding="0" cellspacing="0"'
                f' title="{para.why or ""}" style="margin-bottom:{space};">'
                f'<tr><td width="3" bgcolor="{bar}"></td>'
                f'<td width="13"></td><td>{body}</td></tr></table>'
            )

        # Sayfa: beyaz kâğıt, geniş kenar boşluğu, tezgâhın üstünde.
        self.setHtml(
            '<table width="100%" cellpadding="0" cellspacing="0"><tr>'
            '<td align="center" style="padding: 24px 0;">'
            '<table width="720" bgcolor="#ffffff" cellpadding="0" cellspacing="0">'
            f'<tr><td style="padding: 56px 64px; {face}">'
            + "".join(blocks)
            + "</td></tr></table></td></tr></table>"
        )


# --- Kod -------------------------------------------------------------------


class CodePanel(QPlainTextEdit):
    """Sözdizimi renklendirmesi yok.

    Dört mürekkeple bir renklendirme şeması kurulamaz ve beşinci mürekkebi
    kod vurgusu için harcamak dünyayı kırar. Ajanın dokunduğu satırlar
    yine de işaretli — ayrım renkle değil, mürekkep örtüsüyle.
    """

    def __init__(self, lines: list[str], touched: set[int], path: str) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setPlainText("\n".join(lines))
        self._path = path

        highlight = QTextCharFormat()
        highlight.setBackground(QColor(*_accent_wash(26)))
        cursor = QTextCursor(self.document())
        for index in touched:
            block = self.document().findBlockByNumber(index)
            if not block.isValid():
                continue
            cursor.setPosition(block.position())
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.mergeCharFormat(highlight)


# --- Terminal --------------------------------------------------------------


class TerminalPanel(QWidget):
    """PTY ekranının metin hali.

    Backend ANSI akışını terminal emülatöründen geçirip ekranın son halini
    veriyor; burada olduğu gibi gösteriliyor. Monospace burada kostüm
    değil — gerçekten sabit genişlikli bir karakter ızgarası.
    """

    def __init__(self, screen: str, cursor: tuple[int, int], settled: bool) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        view.setPlainText(screen)
        layout.addWidget(view, 1)

        bits = [meta(f"imleç {cursor[0]}:{cursor[1]}")]
        if not settled:
            warn = QLabel("hâlâ çıktı geliyor")
            
            bits.append(warn)
        layout.addWidget(footer(*bits))


# --- Tashih marjı ----------------------------------------------------------


@dataclass
class Correction:
    target: str
    before: str | None
    after: str
    why: str
    at: str
    saved: bool


class TashihMargin(QWidget):
    """Ajanın değiştirdiği her şey, gerekçesiyle.

    Gerekçe ikincil bir açıklama değil, kaydın kendisi — backend'de `why`
    zorunlu alan olduğu için burada boş bir hücre hiç oluşamaz.
    """

    undo_requested = Signal(int)

    def __init__(self, corrections: list[Correction]) -> None:
        super().__init__()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.set_corrections(corrections)

    def set_corrections(self, corrections: list[Correction]) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        head = QWidget()
        head.setStyleSheet(f"border-bottom: 1px solid {T.divider};")
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(4 * 3, 4 * 2, 4 * 3, 4 * 2)
        head_layout.setSpacing(4 * 3)
        head_layout.addWidget(meta(f"{len(corrections)} değişiklik"))
        head_layout.addStretch(1)
        self._layout.addWidget(head)

        if not corrections:
            empty = QLabel(
                "Henüz düzeltme yok. Ajan bir belgede bir şey değiştirdiğinde,\n"
                "ne değiştirdiği ve neden değiştirdiği buraya düşer."
            )
            empty.setProperty("role", "tertiary")
            empty.setStyleSheet(f"color: {T.text_secondary}; padding: 20px 14px;")
            self._layout.addWidget(empty)
            self._layout.addStretch(1)
            return

        for index, correction in enumerate(corrections):
            self._layout.addWidget(self._row(index, correction))
        self._layout.addStretch(1)

    def _row(self, index: int, c: Correction) -> QWidget:
        row = QWidget()
        row.setStyleSheet(f"border-bottom: 1px solid {T.divider};")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(4 * 3, 4 * 2, 4 * 3, 4 * 2)
        layout.setSpacing(4 * 4)

        # Segoe Fluent Icons: Windows'un kendi ikon kütüphanesi. E710 ekleme,
        # E70F düzenleme. Unicode sembolü değil, platformun ikon sistemi.
        mark = QLabel("" if c.before is None else "")
        mark.setStyleSheet(
            f"font-family: 'Segoe Fluent Icons'; font-size: 13px;"
            f" color: {T.accent_text};"
        )
        mark.setFixedWidth(18)
        layout.addWidget(mark)

        where = QWidget()
        where_layout = QVBoxLayout(where)
        where_layout.setContentsMargins(0, 0, 0, 0)
        where_layout.setSpacing(2)
        where_layout.addWidget(meta(c.target))
        text = c.after if c.before is None else f"{c.before}  →  {c.after}"
        change = QLabel()
        change.setText(
            QFontMetrics(change.font()).elidedText(
                text, Qt.TextElideMode.ElideRight, 210
            )
        )
        change.setToolTip(text)
        change.setStyleSheet(
            f"font-family: '{T.font_mono}'; font-size: 10px;"
            f" color: {T.text};"
        )
        where_layout.addWidget(change)
        where.setFixedWidth(230)
        layout.addWidget(where)

        why = QLabel(c.why)
        why.setWordWrap(True)
        layout.addWidget(why, 1)

        if not c.saved:
            tag = QLabel("Kaydedilmedi")
            tag.setStyleSheet(
                f"color: {T.critical}; border: 1px solid {T.critical};"
                f" border-radius: 4px; padding: 1px 7px; font-size: 12px;"
            )
            layout.addWidget(tag)

        undo = QPushButton("Geri al")
        undo.setFixedHeight(28)
        undo.setProperty("role", "subtle")
        undo.setCursor(Qt.CursorShape.PointingHandCursor)
        undo.clicked.connect(lambda: self.undo_requested.emit(index))
        layout.addWidget(undo)

        return row
