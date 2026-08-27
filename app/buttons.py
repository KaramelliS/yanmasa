"""Çubuktaki düğmeler.

Tekrar eden bir iş her seferinde baştan yazılmamalı. Düğme o işi tek tıka
indiriyor: çizimi, etiketi ve arkasındaki talimatı var.

İki taraf da kurabiliyor. Ajan tekrar fark ettiğinde `button_write` ile
teklif ediyor; Berkay artı düğmesine basıp Python yazmadan kendisi
ekleyebiliyor. Ajanın kurduğu bir düğme Berkay'ın düzenleyemediği bir şey
değil — ikisi de aynı dosyaya yazıyor, ikisi de aynı listede.

Düğmeler çubukta, ana pencerede değil. Konuşulan yer orası; kısayolun da
orada olması gerekiyor.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .fluent import RADIUS_CONTROL, Tokens
from .flow import FlowLayout
from .glyphs import GLYPHS, glyph_icon, paint_glyph

#: Çubuk 440 piksel; bundan fazla düğme sığmıyor ve sığdırmaya çalışmak
#: etiketleri okunmaz hâle getiriyor.
MAX_VISIBLE = 8

#: Bir düğmenin en fazla eni. Uzun etiketli bir düğme satırın dışına
#: taşıp kırpılıyordu: "Butce ozetini goster y" diye kesiliyor ve ne
#: yaptığı okunmuyordu. Kırpmak yerine kısaltıyoruz — üç nokta hiç
#: olmazsa kesildiğini söylüyor.
CHIP_MAX = 168

#: Çizim, kenar boşlukları ve iç dolgu. Etiketin kullanabileceği yer
#: `CHIP_MAX - CHIP_PAD`.
CHIP_PAD = 46


class ShortcutChip(QPushButton):
    """Tek düğme: çizim ve etiket."""

    edit_requested = Signal(str)
    remove_requested = Signal(str)

    def __init__(self, t: Tokens, name: str, label: str, glyph: str,
                 editable: bool = True) -> None:
        super().__init__()
        self.t = t
        self.name = name
        self._label = label
        # Tam etiket ipucunda kalıyor: kısaltılan bir şeyi okumanın yolu
        # olmalı.
        self.setToolTip(label)
        self._glyph = glyph if glyph in GLYPHS else "yetenek"
        self._editable = editable
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(30)
        # Çizim solda elle çizildiği için metne yer açılıyor.
        self.setStyleSheet(
            f"QPushButton {{ background: {t.control};"
            f" border: 1px solid {t.control_stroke};"
            f" border-radius: {RADIUS_CONTROL + 2}px;"
            f" padding: 0 10px 0 28px; text-align: left;"
            f" color: {t.text}; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {t.control_hover}; }}"
            f"QPushButton:pressed {{ background: {t.control_pressed}; }}"
        )
        # Etiket **bir kez** kısaltılıyor, kurulurken.
        #
        # Önce `resizeEvent`te yapıyordum ve kararsızdı: metni
        # değiştirmek `sizeHint`i değiştiriyor, o da yeniden boyutlanmayı
        # tetikliyor. Sonuç, üç noktası olmayan kırpılmış bir yazıydı —
        # "Bütçe özetini göster v" diye kesiliyordu ve kesildiği belli
        # olmuyordu.
        self.setText(
            self.fontMetrics().elidedText(
                label, Qt.TextElideMode.ElideRight, CHIP_MAX - CHIP_PAD
            )
        )
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    def sizeHint(self) -> QSize:
        genislik = self.fontMetrics().horizontalAdvance(self.text()) + CHIP_PAD
        return QSize(min(genislik, CHIP_MAX), 30)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        paint_glyph(painter, self._glyph, 16, self.t.accent, self.t.text_secondary,
                    _origin(self))
        painter.end()

    def _menu(self, point) -> None:
        menu = QMenu(self)
        if self._editable:
            menu.addAction("Düzenle").triggered.connect(
                lambda: self.edit_requested.emit(self.name)
            )
            menu.addAction("Kaldır").triggered.connect(
                lambda: self.remove_requested.emit(self.name)
            )
        else:
            # Yetenek dosyasından gelen düğme burada düzenlenemiyor; kaynağı
            # kod. Menüyü boş açmak yerine sebebi yazıyoruz.
            action = menu.addAction("Yetenek dosyasında tanımlı")
            action.setEnabled(False)
        menu.exec(self.mapToGlobal(point))


def _origin(widget):
    return QPointF(8, (widget.height() - 16) / 2)


def _glyph_icon(t: Tokens, key: str, size: int = 18) -> QIcon:
    return glyph_icon(key, size, t.accent, t.text_secondary)


class ShortcutEditor(QDialog):
    """Berkay'ın kendi düğmesini kurduğu yer. Python gerekmiyor."""

    def __init__(self, t: Tokens, shortcut=None, parent=None) -> None:
        super().__init__(parent)
        self.t = t
        self.setWindowTitle("Düğmeyi düzenle" if shortcut else "Yeni düğme")
        self.setMinimumWidth(420)
        self.setStyleSheet(
            f"QDialog {{ background: {t.background}; }}"
            f"QLabel {{ color: {t.text_secondary}; font-size: 12px; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        self.label = QLineEdit(shortcut.label if shortcut else "")
        self.label.setMaxLength(22)
        self.label.setPlaceholderText("Günlük özet")
        self.label.setStyleSheet(self._field(t))
        form.addRow("Üstünde yazan", self.label)

        self.instruction = QPlainTextEdit(shortcut.instruction if shortcut else "")
        self.instruction.setPlaceholderText(
            "Tıklayınca ajana gidecek talimat. Ne yapmasını istiyorsan onu yaz."
        )
        self.instruction.setFixedHeight(92)
        # `QPlainTextEdit` varsayılan olarak eşaralıklı yazı kullanıyor;
        # burada kod değil cümle yazılıyor.
        self.instruction.setFont(QFont(t.font_ui, 10))
        self.instruction.setStyleSheet(self._field(t))
        form.addRow("Talimat", self.instruction)

        # Çizimler adlarıyla listeleniyordu ve "agac" ile "defter" arasında
        # seçim yapmak tahmin işiydi. Her satırın yanında çizimin kendisi var.
        self.glyph = QComboBox()
        self.glyph.setIconSize(QSize(18, 18))
        for key in sorted(GLYPHS):
            self.glyph.addItem(_glyph_icon(t, key), key)
        self.glyph.setStyleSheet(self._field(t))
        if shortcut:
            index = self.glyph.findText(shortcut.glyph)
            if index >= 0:
                self.glyph.setCurrentIndex(index)
        form.addRow("Çizim", self.glyph)
        layout.addLayout(form)

        self._error = QLabel()
        self._error.setWordWrap(True)
        self._error.setStyleSheet(f"color: {t.critical}; font-size: 12px;")
        self._error.setVisible(False)
        layout.addWidget(self._error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Kaydet")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Vazgeç")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._name = shortcut.name if shortcut else ""

    def _field(self, t: Tokens) -> str:
        return (
            f"QLineEdit, QPlainTextEdit, QComboBox {{ background: {t.control};"
            f" border: 1px solid {t.control_stroke};"
            f" border-radius: {RADIUS_CONTROL}px; padding: 6px 8px;"
            f" color: {t.text}; font-size: 13px;"
            f" selection-background-color: {t.accent};"
            f" selection-color: {t.on_accent}; }}"
            # Açılır listenin kendisi ayrı bir pencere ve kutunun biçimini
            # miras almıyor: biçimlendirilmeyince koyu temada beyaz zeminde
            # beyaz yazı çıkıyor ve seçenekler görünmüyordu.
            f"QComboBox QAbstractItemView {{ background: {t.card};"
            f" border: 1px solid {t.stroke};"
            f" border-radius: {RADIUS_CONTROL}px; padding: 4px;"
            f" color: {t.text}; outline: none;"
            f" selection-background-color: {t.accent};"
            f" selection-color: {t.on_accent}; }}"
            f"QComboBox QAbstractItemView::item {{ min-height: 24px;"
            f" padding: 2px 6px; border-radius: {RADIUS_CONTROL}px; }}"
        )

    def _accept(self) -> None:
        if not self.label.text().strip():
            return self._fail("Üstünde ne yazacak?")
        if not self.instruction.toPlainText().strip():
            return self._fail("Talimat boş — tıklanınca ne gitsin?")
        self.accept()

    def _fail(self, message: str) -> None:
        self._error.setText(message)
        self._error.setVisible(True)

    def result_shortcut(self):
        """Diyalogdan çıkan düğme. Ad etiketten türetiliyor."""
        from backend.skills.shortcuts import Shortcut

        label = self.label.text().strip()
        return Shortcut(
            name=self._name or _slug(label),
            label=label,
            instruction=self.instruction.toPlainText().strip(),
            glyph=self.glyph.currentText(),
        )


def _slug(label: str) -> str:
    """Etiketten kimlik. Türkçe harfler karşılıklarına çevriliyor."""
    table = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    out = "".join(
        ch if ch.isalnum() else "_" for ch in label.translate(table).lower()
    ).strip("_")
    out = out[:30] or "dugme"
    if not out[0].isalpha():
        out = "d" + out
    return out


class ButtonStrip(QWidget):
    """Çubuktaki düğme satırı."""

    triggered = Signal(str)      # talimat
    changed = Signal()

    def __init__(self, t: Tokens) -> None:
        super().__init__()
        self.t = t
        self._store = None
        self._extra = []
        # Akan düzen: sarmayı yerleşim anında, gerçek genişlikte yapıyor.
        # Elle sarıyordum ve sınırı içerik kurulurken hesaplıyordum —
        # widget o an ölçülmemiş oluyor ve satır taşıyordu.
        self._rows = FlowLayout(6, 6)
        self.setLayout(self._rows)

    def attach(self, store, extra_source=None) -> None:
        """`store` düzenlenebilir düğmeler, `extra_source` yeteneklerden
        gelen salt-okunur komutlar."""
        self._store = store
        self._extra = extra_source
        self.reload()

    def reload(self) -> None:
        while self._rows.count():
            item = self._rows.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        items = []
        if self._store is not None:
            items.extend((s, True) for s in self._store.all())
        if self._extra is not None:
            try:
                for name, description in self._extra():
                    items.append((_from_command(name, description), False))
            except Exception:
                pass

        for shortcut, editable in items[:MAX_VISIBLE]:
            chip = ShortcutChip(
                self.t, shortcut.name, shortcut.label, shortcut.glyph, editable
            )
            chip.clicked.connect(
                lambda _=False, s=shortcut: self.triggered.emit(s.instruction)
            )
            chip.edit_requested.connect(self._edit)
            chip.remove_requested.connect(self._remove)
            self._rows.addWidget(chip)

        plus = QPushButton("+")
        plus.setFixedSize(30, 30)
        plus.setCursor(Qt.CursorShape.PointingHandCursor)
        plus.setToolTip("Kendi düğmeni ekle")
        plus.setStyleSheet(
            f"QPushButton {{ background: transparent;"
            f" border: 1px dashed {t_stroke(self.t)};"
            f" border-radius: {RADIUS_CONTROL + 2}px;"
            f" color: {self.t.text_secondary}; font-size: 15px; }}"
            f"QPushButton:hover {{ background: {self.t.subtle_hover};"
            f" color: {self.t.text}; }}"
        )
        plus.clicked.connect(self._add)
        self._rows.addWidget(plus)
        self.updateGeometry()

    # --- düzenleme --------------------------------------------------------

    def _add(self) -> None:
        dialog = ShortcutEditor(self.t, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._save(dialog.result_shortcut())

    def _edit(self, name: str) -> None:
        if self._store is None:
            return
        shortcut = self._store.get(name)
        if shortcut is None:
            return
        dialog = ShortcutEditor(self.t, shortcut, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._save(dialog.result_shortcut())

    def _remove(self, name: str) -> None:
        if self._store is None:
            return
        try:
            self._store.remove(name)
        except Exception:
            return
        self.reload()
        self.changed.emit()

    def _save(self, shortcut) -> None:
        if self._store is None:
            return
        try:
            self._store.save(shortcut)
        except Exception:
            return
        self.reload()
        self.changed.emit()


def t_stroke(t: Tokens) -> str:
    return t.control_stroke


def _from_command(name: str, description: str):
    from backend.skills.shortcuts import Shortcut

    return Shortcut(
        name=name,
        label=description[:22] or name,
        instruction=f"/{name}",
        glyph="yetenek",
        from_skill=True,
    )
