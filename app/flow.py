"""Sığdığı kadar yan yana, sonra alt satıra akan düzen.

Qt'de hazır yok. İki yerde gerekiyor — panel ölçüleri ve düğme şeridi —
ve ikisinde de sebep aynı: içerik daraldığında **kesilmemeli**, alt
satıra inmeli.

Elle sarma denendi ve yanlıştı: sarma sınırını içerik kurulurken
hesaplıyordum ama widget o an daha ölçülmemiş oluyor, genişliği
varsayılan kalıyor ve sarma yanlış yerde gerçekleşiyordu. Ölçtüm — 412
piksellik şeritte satır 418'e çıkıyordu. Düzen sarmayı `setGeometry`de
yapıyor, yani gerçek genişlikte.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtWidgets import QLayout


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
