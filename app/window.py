"""Ajan penceresi — Windows 11 Fluent.

Uygulama Dosya Gezgini ve Ayarlar'ın yanında durduğunda oradan gelmiş gibi
görünmeli. Kendi tasarım dilimizi uydurmuyoruz; Fluent'in kendi kurallarına
uyuyoruz: Segoe UI Variable, 8 piksel kart yarıçapı, sistem vurgu rengi,
sistem teması.

Mikrofon burada değil. O her şeyden bağımsız, kendi penceresinde, ekranın
köşesinde duruyor (`mic.py`) — Berkay ajan penceresine bakmadan da basıp
konuşabilsin diye.

Paneller `QDockWidget`. Başlığına çift tıklayınca panel gerçek, ayrı bir
Windows penceresine çıkıyor ve ikinci ekrana atılabiliyor — Qt'nin kendi
davranışı, taklit edilmiş bir sürükleme değil.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import panels
from .fluent import GAP, RADIUS_CARD, RADIUS_CONTROL, Tokens
from .activity import ActivityView

PHASE_LABEL = {
    "bos": "Hazır",
    "dinleniyor": "Dinliyor",
    "diziliyor": "Yazıya çeviriyor",
    "kosuyor": "Çalışıyor",
    "onay": "Onay bekliyor",
    "bitti": "Bitti",
    "durduruldu": "Durduruldu",
}


class StatusDot(QWidget):
    """Durum ışığı. Unicode karakteri değil, çizilmiş bir daire —
    bir glifin ağırlığı yazı tipine bağlıdır ve hiçbir zaman hizalanmaz."""

    def __init__(self, t: Tokens) -> None:
        super().__init__()
        self.setFixedSize(10, 10)
        self._colour = t.text_tertiary

    def set_colour(self, colour: str) -> None:
        self._colour = colour
        self.update()

    def paintEvent(self, _event) -> None:
        from PySide6.QtGui import QColor, QPainter

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._colour))
        painter.drawEllipse(1, 1, 8, 8)
        painter.end()


class Counter(QWidget):
    """Durum şeridindeki canlı sayaç."""

    def __init__(self, t: Tokens, label: str, warn: bool = False) -> None:
        super().__init__()
        self.t, self._warn = t, warn
        layout = QVBoxLayout(self)
        layout.setContentsMargins(GAP * 3, GAP * 2, GAP * 3, GAP * 2)
        layout.setSpacing(0)

        self._value = QLabel("0")
        self._value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._value)

        caption = QLabel(label)
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setProperty("role", "tertiary")
        layout.addWidget(caption)
        self.set_value(0)

    def set_value(self, value: int) -> None:
        colour = self.t.critical if (self._warn and value > 0) else self.t.text
        self._value.setText(str(value))
        self._value.setStyleSheet(
            f"font-family: '{self.t.font_display}', '{self.t.font_ui}';"
            f" font-size: 20px; font-weight: 600; color: {colour};"
        )


class StatusBar(QWidget):
    """Durum ve sayaçlar. Durdurma her zaman burada, hep etkin."""

    stop_requested = Signal()

    def __init__(self, t: Tokens) -> None:
        super().__init__()
        self.t = t
        self.setFixedHeight(56)
        self.setStyleSheet(
            f"background: {t.background}; border-top: 1px solid {t.divider};"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(GAP * 4, 0, GAP * 3, 0)
        layout.setSpacing(GAP * 2)

        self._dot = StatusDot(t)
        layout.addWidget(self._dot)

        self._phase = QLabel()
        self._phase.setProperty("role", "strong")
        layout.addWidget(self._phase)

        self._line = QLabel()
        self._line.setProperty("role", "caption")
        layout.addWidget(self._line, 1)

        self.steps = Counter(t, "adım")
        self.unsaved = Counter(t, "kaydedilmedi", warn=True)
        self.terminals = Counter(t, "terminal")
        for counter in (self.steps, self.unsaved, self.terminals):
            layout.addWidget(counter)

        self.connect_remote = QPushButton("Sunucu")
        self.connect_remote.setToolTip("SSH ile bir sunucuya bağlan")
        self.connect_remote.setFixedHeight(32)
        self.connect_remote.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.connect_remote)

        stop = QPushButton("Durdur")
        stop.setToolTip("Ajanı durdur — Esc ×3 her yerden çalışır")
        stop.setFixedHeight(32)
        stop.setCursor(Qt.CursorShape.PointingHandCursor)
        stop.clicked.connect(self.stop_requested.emit)
        layout.addWidget(stop)

        self.set_phase("bos")
        self.set_line("Köşedeki çubuktan yaz ya da konuş.")

    def set_phase(self, phase: str) -> None:
        active = phase in {"dinleniyor", "diziliyor", "kosuyor"}
        alert = phase in {"onay", "durduruldu"}
        colour = self.t.critical if alert else (self.t.accent if active else self.t.text_tertiary)
        self._dot.set_colour(colour)
        self._phase.setText(PHASE_LABEL.get(phase, phase))

    def set_line(self, text: str) -> None:
        self._line.setText(text)


class MainWindow(QMainWindow):
    stop_requested = Signal()

    def __init__(self, t: Tokens) -> None:
        super().__init__()
        self.t = t
        panels.set_tokens(t)

        self.setWindowTitle("Ajan")
        self.resize(1500, 940)
        self.setDockNestingEnabled(True)
        self.setDockOptions(
            QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.AllowNestedDocks
        )

        self._phase = "bos"
        self._bar = None
        self._esc_hits: list[float] = []

        # Merkezde etkinlik görünümü: ajanın bilgisayarda ne yaptığı.
        # Qt artan alanı merkeze verdiği için asıl içerik burada olmalı;
        # belgeler ve terminaller ancak açıldıklarında dock olarak gelir.
        self.activity = ActivityView(t)
        self.setCentralWidget(self.activity)
        self._panels: dict[str, QDockWidget] = {}

        self.status = StatusBar(t)
        self.status.stop_requested.connect(self.stop)
        self.setStatusBar(self._status_host())

        self._wire_shortcuts()
        self.set_counters(0, 0, 0)

    # --- komut çubuğu bağlantısı -----------------------------------------

    def attach_bar(self, bar) -> None:
        """Köşedeki komut çubuğunu bağlar.

        Çubuk ana pencereye ait değil; pencere kapansa da yaşamaya devam
        etmeli. Bu yüzden pencere çubuğu sahiplenmiyor, yalnızca ona
        yazıyor.
        """
        self._bar = bar

    def run_instruction(self, text: str) -> None:
        """Çubuktan gelen yazılı komut."""
        self.set_phase("kosuyor")
        self.status.set_line(text)
        if self._bar is not None:
            self._bar.set_status(f"Çalışıyor: {text}")

    def show_operation(self, op) -> None:
        """Ajanın o an yaptığı iş çubuktaki önizleme karesine düşer."""
        if self._bar is not None:
            self._bar.show_operation(op)

    def _status_host(self):
        from PySide6.QtWidgets import QStatusBar

        bar = QStatusBar()
        bar.setSizeGripEnabled(False)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setStyleSheet("QStatusBar::item { border: none; }")
        bar.addPermanentWidget(self.status, 1)
        return bar

    # --- paneller ---------------------------------------------------------

    def open_panel(self, key: str, title: str, body: QWidget) -> None:
        """Ajan bir belge ya da terminal açtığında panel belirir.

        Uygulama açılışta boş: ortada hiç dosya yokken bir tablo paneli
        göstermek, ajanın tablo üstünde çalıştığını sanmana yol açardı.
        """
        existing = self._panels.get(key)
        if existing is not None:
            # Aynı gövde tekrar geliyorsa dokunma: `setWidget` onu bir an
            # için düzenden çıkarıyor ve kod panelinde kaydırma konumu
            # başa dönüyordu.
            if existing.widget() is not body:
                existing.setWidget(body)
            existing.setWindowTitle(title)
            existing.show()
            existing.raise_()
            return

        dock = QDockWidget(title, self)
        dock.setWidget(body)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)

        # İlk panel sağa, sonrakiler onunla sekmeleniyor: her yeni panel
        # ekranı bölmesin.
        if self._panels:
            self.tabifyDockWidget(next(iter(self._panels.values())), dock)
        else:
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
            self.resizeDocks([dock], [720], Qt.Orientation.Horizontal)
        self._panels[key] = dock
        dock.raise_()
        self._fit_to_screen()

    def _fit_to_screen(self) -> None:
        """Pencereyi ekranın içinde tutar.

        720 piksellik bir panel eklendiğinde Qt pencereyi büyütüyor ve
        pencere ekranın soluna taşıp içeriğini kırpıyordu: etkinlik
        listesinin sol kenarı ekranın dışında kalıyor, adımlar yarım
        okunuyordu.
        """
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        size = self.size().boundedTo(area.size())
        if size != self.size():
            self.resize(size)
        x = max(area.left(), min(self.x(), area.right() - self.width() + 1))
        y = max(area.top(), min(self.y(), area.bottom() - self.height() + 1))
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)

    def close_panel(self, key: str) -> None:
        dock = self._panels.pop(key, None)
        if dock is not None:
            dock.close()
            dock.deleteLater()

    # --- kısayollar -------------------------------------------------------

    def _wire_shortcuts(self) -> None:
        stop = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        stop.setAutoRepeat(False)
        stop.activated.connect(self._escape_hit)

    def _escape_hit(self) -> None:
        now = time.monotonic()
        self._esc_hits = [t for t in self._esc_hits if now - t < 0.8] + [now]
        if len(self._esc_hits) >= 3:
            self._esc_hits.clear()
            self.stop()

    # --- ajan durumu ------------------------------------------------------

    def set_phase(self, phase: str) -> None:
        self._phase = phase
        self.status.set_phase(phase)

    def start_listening(self) -> None:
        self.set_phase("dinleniyor")
        self.status.set_line("Dinliyorum — bırakınca çalışmaya başlar.")

    def stop_listening(self) -> None:
        if self._phase != "dinleniyor":
            return
        self.set_phase("bos")
        # Ses motoru bağlı değil ve bu gizlenmiyor.
        self.status.set_line(
            "Ses motoru bağlı değil — köşedeki çubuğa yazarak komut ver."
        )

    def stop(self) -> None:
        self.set_phase("durduruldu")
        self.status.set_line("Durduruldu. Bekleyen eylemler iptal edildi.")
        self.stop_requested.emit()
        if self._bar is not None:
            self._bar.set_busy(False)
            self._bar.clear_approval()

    # --- değişiklikler ----------------------------------------------------

    def set_counters(self, steps: int, unsaved: int, terminals: int) -> None:
        self.status.steps.set_value(steps)
        self.status.unsaved.set_value(unsaved)
        self.status.terminals.set_value(terminals)
