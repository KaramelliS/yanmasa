"""Hesap tablosu görünümü — Excel'de ne bekliyorsan o.

Bir hesap tablosunun tanıdık olması süs değil işlevdir: hücre adı kutusu,
formül çubuğu, sütun ve satır başlıkları, dondurulmuş başlık satırı, sayfa
sekmeleri. Bunlar olmadığında ızgara bir tablodan çok bir veri dökümüne
benziyor ve kullanıcı hücrenin gerçek içeriğini — formülü mü değeri mi —
göremiyor.

Formül çubuğu burada ayrıca zorunlu: bu üründe formüller yazılıyor ama
hesaplanmıyor. Hücrede ne göründüğü ile hücrede ne olduğu farklı olabilir
ve tek görebileceğin yer formül çubuğu.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .fluent import RADIUS_CONTROL, Tokens


@dataclass
class Cell:
    value: str
    formula: bool = False
    why: str | None = None
    #: Formülün hesaplanmış sonucu. `None` ise hesaplanamadı.
    result: str | None = None

    @property
    def shown(self) -> str:
        """Hücrede görünen. Excel'de olduğu gibi formülün sonucu görünür,
        formülün kendisi formül çubuğunda kalır.

        Hesaplanamayan formülde formül metni görünüyor — boş bırakmak,
        değeri biliyormuş gibi yapmaktan daha dürüst."""
        if self.formula and self.result is not None:
            return self.result
        return self.value

    @property
    def uncomputed(self) -> bool:
        return self.formula and self.result is None


def column_name(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        name = chr(65 + rest) + name
    return name


class SheetModel(QAbstractTableModel):
    #: Veriden sonra çizilecek boş satır ve sütun. Bir hesap tablosu boş
    #: ızgarasıyla birlikte okunur.
    PAD_ROWS = 40
    PAD_COLS = 6

    def __init__(self, rows: list[list[Cell]], t: Tokens) -> None:
        super().__init__()
        self._rows = rows
        self.t = t
        self._cols = max((len(r) for r in rows), default=1)

    def rowCount(self, _parent=QModelIndex()) -> int:
        return len(self._rows) + self.PAD_ROWS

    def columnCount(self, _parent=QModelIndex()) -> int:
        return self._cols + self.PAD_COLS

    def cell(self, row: int, col: int) -> Cell | None:
        if row < len(self._rows) and col < len(self._rows[row]):
            return self._rows[row][col]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        cell = self.cell(index.row(), index.column())
        if cell is None:
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            return cell.shown
        if role == Qt.ItemDataRole.ToolTipRole:
            return cell.why
        if role == Qt.ItemDataRole.BackgroundRole and cell.why:
            c = QColor(self.t.accent)
            c.setAlpha(38)
            return c
        if role == Qt.ItemDataRole.ForegroundRole and cell.uncomputed:
            return QColor(self.t.critical)
        if role == Qt.ItemDataRole.FontRole and cell.uncomputed:
            font = QFont(self.t.font_mono)
            font.setPointSize(9)
            return font
        if role == Qt.ItemDataRole.TextAlignmentRole:
            numeric = cell.shown.replace(".", "").replace(",", "").isdigit()
            return int(
                (Qt.AlignmentFlag.AlignRight if numeric else Qt.AlignmentFlag.AlignLeft)
                | Qt.AlignmentFlag.AlignVCenter
            )
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        return (
            column_name(section)
            if orientation == Qt.Orientation.Horizontal
            else str(section + 1)
        )


class SheetView(QWidget):
    def __init__(
        self, rows: list[list[Cell]], t: Tokens, sheets: list[str], path: str
    ) -> None:
        super().__init__()
        self.t = t
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._formula_bar(t))

        self.table = QTableView()
        self.model = SheetModel(rows, t)
        self.table.setModel(self.model)
        self.table.setShowGrid(True)
        self.table.setCornerButtonEnabled(True)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.horizontalHeader().setDefaultSectionSize(112)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.verticalHeader().setFixedWidth(40)
        self.table.verticalHeader().setHighlightSections(False)
        self.table.selectionModel().currentChanged.connect(self._on_cell)
        layout.addWidget(self.table, 1)

        layout.addWidget(self._sheet_tabs(t, sheets, path))
        self.table.setCurrentIndex(self.model.index(0, 0))

    def _formula_bar(self, t: Tokens) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(34)
        bar.setStyleSheet(
            f"background: {t.background}; border-bottom: 1px solid {t.divider};"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self.name_box = QLineEdit("A1")
        self.name_box.setReadOnly(True)
        self.name_box.setFixedWidth(76)
        self.name_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_box.setStyleSheet(self._field_style(t))
        layout.addWidget(self.name_box)

        fx = QLabel("fx")
        fx.setStyleSheet(
            f"color: {t.text_secondary}; font-style: italic; font-size: 13px;"
            f" padding: 0 4px;"
        )
        layout.addWidget(fx)

        self.formula = QLineEdit()
        self.formula.setReadOnly(True)
        self.formula.setStyleSheet(self._field_style(t, mono=True))
        layout.addWidget(self.formula, 1)
        return bar

    def _field_style(self, t: Tokens, mono: bool = False) -> str:
        family = f"font-family: '{t.font_mono}';" if mono else ""
        return (
            f"QLineEdit {{ background: {t.control};"
            f" border: 1px solid {t.control_stroke};"
            f" border-radius: {RADIUS_CONTROL}px; padding: 0 8px;"
            f" color: {t.text}; font-size: 13px; {family}"
            f" selection-background-color: {t.accent};"
            f" selection-color: {t.on_accent}; }}"
        )

    def _sheet_tabs(self, t: Tokens, sheets: list[str], path: str) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(30)
        bar.setStyleSheet(
            f"background: {t.background}; border-top: 1px solid {t.divider};"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(6, 0, 10, 0)
        layout.setSpacing(2)

        for index, name in enumerate(sheets):
            tab = QPushButton(name)
            tab.setFixedHeight(24)
            tab.setCursor(Qt.CursorShape.PointingHandCursor)
            active = index == 0
            tab.setStyleSheet(
                f"QPushButton {{ background: {t.card if active else 'transparent'};"
                f" border: none;"
                f" border-bottom: 2px solid {t.accent if active else 'transparent'};"
                f" border-radius: 0; padding: 0 12px;"
                f" color: {t.text if active else t.text_secondary};"
                f" font-size: 12px; font-weight: {600 if active else 400}; }}"
                f"QPushButton:hover {{ background: {t.subtle_hover}; }}"
            )
            layout.addWidget(tab)

        layout.addStretch(1)
        meta = QLabel(path)
        meta.setStyleSheet(f"color: {t.text_tertiary}; font-size: 11px;")
        layout.addWidget(meta)

        stuck = sum(1 for row in self.model._rows for c in row if c.uncomputed)
        if stuck:
            # Hesaplanmamış formülü gizlemek, sonucun bilindiği yanılgısını
            # üretir.
            warn = QLabel(f"{stuck} formulas could not be calculated")
            warn.setStyleSheet(f"color: {t.critical}; font-size: 11px;")
            layout.addWidget(warn)
        return bar

    def _on_cell(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not current.isValid():
            return
        self.name_box.setText(
            f"{column_name(current.column())}{current.row() + 1}"
        )
        cell = self.model.cell(current.row(), current.column())
        self.formula.setText(cell.value if cell else "")
