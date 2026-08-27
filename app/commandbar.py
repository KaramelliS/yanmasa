"""Komut çubuğu — ekranın köşesinde yüzen, her şeyden bağımsız pencere.

Ajanla konuşulan yer burası, ana pencere değil. Ana pencere belgeleri
tutuyor; bu çubuk ajan penceresi kapalıyken, başka bir uygulamadayken, tam
ekran bir oyundayken bile orada.

Üç parçası var ve üçü de aynı yerde olmak zorunda:

- **Mikrofon.** Bas ve konuş.
- **Yazı alanı.** Mikrofon kullanılamıyorsa — sessiz olman gereken bir yer,
  bozuk bir mikrofon, ya da yazmanın daha kolay olduğu bir komut — aynı
  çubuktan yazarsın. Ses bir kolaylık, tek yol değil.
- **Önizleme karesi.** Ajan bir şey yaptığında ne yaptığı burada küçük bir
  kare olarak görünüyor: eylemin adı, hedefi, gerekçesi ve gerçek bir
  görüntüsü. Ajan penceresine bakmadan takip edebilmek için.

Sürüklenebilir; köşeyi Berkay seçer. Konum kaydediliyor.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QPushButton,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .buttons import ButtonStrip
from .sahne import Sahne
from .stream import Akis, RunRing
from .glyphs import PreviewFrame

#: Onay kartındaki ayrıntı alanının tavanı. Onaylanan şey yüz satırlık bir
#: dosya olabiliyor.
DETAIL_MAX_HEIGHT = 190

#: Cevap alanının tavanı. Bunun üstünde çubuk büyümüyor, içerik kayıyor.
REPLY_MAX_HEIGHT = 170

#: Sürüklerken çubuğun ekranda kalması gereken en küçük payı. Tamamen
#: dışarı çıkarılamamalı: geri getirmenin tek yolu ayar dosyasını elle
#: silmek olurdu.
KEEP_ON_SCREEN = 90
from .fluent import RADIUS_CARD, RADIUS_CONTROL, Tokens

#: Çubuğun bıraktığın yeri. `AJAN_STATE_DIR` ile taşınabiliyor: test
#: çalıştırmak Berkay'ın çubuğunu yerinden oynatmamalı.
STATE_FILE = (
    Path(os.environ.get("AJAN_STATE_DIR") or (Path.home() / ".ajan")) / "bar.json"
)

BAR_WIDTH = 440
MARGIN = 24
#: Adim anlatimlari arasindaki paragraf arasi.
BREAK = "\n\n"

MIC_SIZE = 40

#: Koşu halkası. Mikrofondan büyük: içinde bir yüz var ve 40 pikselde
#: ifade okunmuyor — ölçtüm.
RING_SIZE = 52


@dataclass
class Operation:
    """Önizleme karesinde gösterilen tek bir işlem."""

    tool: str
    target: str
    detail: str
    thumbnail: QPixmap | None = None
    #: Ham araç adı — çizimi bu seçiyor. `tool` Türkçe etiket olduğu için
    #: ondan çıkarılamıyor.
    key: str = ""


class MicDot(QWidget):
    """Bas ve konuş. Halka gerçek ses şiddetini gösteriyor.

    Nabız atan bir küre değil: kategorinin her ajanında var ve hiçbir sinyal
    taşımıyor — sen konuşsan da sussan da aynı hızda atıyor. Buradaki halka
    sustuğunda duruyor, ses motoru bağlı değilken de hiç hareket etmiyor.
    """

    pressed = Signal()
    released = Signal()

    def __init__(self, t: Tokens) -> None:
        super().__init__()
        self.t = t
        self.setFixedSize(MIC_SIZE, MIC_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Bas ve konuş")
        self._level = 0.0
        self._live = False
        self._enabled = True

    def set_level(self, level: float) -> None:
        level = max(0.0, min(1.0, level))
        if abs(level - self._level) > 0.01:
            self._level = level
            self.update()

    def set_live(self, live: bool) -> None:
        if self._live != live:
            self._live = live
            if not live:
                self._level = 0.0
            self.update()

    def set_available(self, available: bool) -> None:
        """Ses motoru yoksa mikrofon sönük durur ve bunu söyler."""
        self._enabled = available
        self.setToolTip(
            "Bas ve konuş" if available else "Ses motoru bağlı değil — yazarak komut ver"
        )
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if available else Qt.CursorShape.ArrowCursor
        )
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._enabled:
            self.pressed.emit()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._enabled:
            self.released.emit()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        t = self.t
        centre = QPointF(self.width() / 2, self.height() / 2)
        radius = MIC_SIZE / 2 - 3

        if not self._enabled:
            ring, fill, ink = t.text_disabled, t.control, t.text_disabled
        elif self._live:
            ring, fill, ink = t.accent, t.accent, t.on_accent
        else:
            ring, fill, ink = t.accent_text, t.control, t.accent_text

        painter.setPen(QPen(QColor(ring), 1.4))
        painter.setBrush(QColor(fill))
        painter.drawEllipse(centre, radius, radius)

        if self._live and self._level > 0.02:
            pen = QPen(QColor(t.on_accent), 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(
                QRectF(centre.x() - radius - 3, centre.y() - radius - 3,
                       (radius + 3) * 2, (radius + 3) * 2),
                90 * 16, int(-340 * self._level * 16),
            )

        pen = QPen(QColor(ink), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = centre.x(), centre.y() - 1
        painter.drawRoundedRect(QRectF(cx - 3.2, cy - 7.5, 6.4, 10.5), 3.2, 3.2)
        painter.drawArc(QRectF(cx - 6.5, cy - 4, 13, 11.5), 200 * 16, 140 * 16)
        painter.drawLine(QPointF(cx, cy + 5.5), QPointF(cx, cy + 8.5))
        painter.end()


class DragGrip(QWidget):
    """Çubuğun tutamağı.

    Kart yazıyla dolduğunda nereden tutulacağı belirsizdi: metnin üstüne
    basmak seçim yapıyor, düğmeye basmak düğmeyi çalıştırıyor. Üstteki bu
    şerit her zaman boş ve her zaman sürüklenebilir.

    Ayrıca çubuğun taşınabilir olduğunu söylüyor. Taşınabilir ama görünürde
    hiçbir işareti olmayan bir pencere, taşınamaz bir pencereden farksız.
    """

    def __init__(self, t: Tokens) -> None:
        super().__init__()
        self.t = t
        self.setFixedHeight(14)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setToolTip("Sürükleyerek taşı")

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        colour = QColor(self.t.text_tertiary)
        colour.setAlpha(120)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        width = 34.0
        painter.drawRoundedRect(
            QRectF((self.width() - width) / 2, 6.0, width, 3.0), 1.5, 1.5
        )
        painter.end()


class PreviewCard(QWidget):
    """Ajanın o an yaptığı işin küçük karesi.

    Küçük resim gerçek: GUI eylemlerinde ekranın ilgili yerinden kırpılmış
    bir kare, belge işlerinde değişen bölgenin küçük çizimi. Yer tutucu bir
    simge koymak, bakıp bir şey anlamayı imkânsız kılardı.
    """

    def __init__(self, t: Tokens) -> None:
        super().__init__()
        self.t = t
        self.setFixedHeight(72)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        self._thumb = PreviewFrame(t, 84, 52)
        layout.addWidget(self._thumb)

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)

        self._title = QLabel()
        self._title.setStyleSheet(
            f"color: {t.text}; font-size: 13px; font-weight: 600;"
        )
        column.addWidget(self._title)

        self._detail = QLabel()
        self._detail.setWordWrap(True)
        self._detail.setStyleSheet(f"color: {t.text_secondary}; font-size: 12px;")
        column.addWidget(self._detail)
        column.addStretch(1)
        layout.addLayout(column, 1)

    def show_operation(self, op: Operation) -> None:
        self._title.setText(f"{op.tool} · {op.target}" if op.target else op.tool)
        self._detail.setText(op.detail)
        # Ekran görüntüsü yoksa işin kendi çizimi geçiyor; boş bir kutu
        # değil.
        self._thumb.show_tool(op.key or op.tool, op.thumbnail)


class ApprovalRow(QWidget):
    """Riskli eylem onayı — çubuğun içinde, modal olarak değil.

    Modal, ajanı durdurup ekranı karartır ve arkasındaki bağlamı tam da
    karar için gereken anda gizler. Burada komutun kendisi okunuyor ve
    ekranda hiçbir şey kaybolmuyor.
    """

    answered = Signal(bool)

    def __init__(self, t: Tokens) -> None:
        super().__init__()
        self.t = t
        self.setStyleSheet(
            f"background: {t.background_secondary};"
            f" border-top: 1px solid {t.critical};"
            f" border-bottom: 1px solid {t.divider};"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        self._reason = QLabel()
        self._reason.setWordWrap(True)
        self._reason.setStyleSheet(
            f"color: {t.critical}; font-size: 12px; font-weight: 600; border: none;"
        )
        layout.addWidget(self._reason)

        self._detail = QLabel()
        self._detail.setWordWrap(True)
        self._detail.setStyleSheet(
            f"color: {t.text}; font-size: 12px; font-family: '{t.font_mono}';"
            f" background: transparent; border: none; padding: 6px 8px;"
        )

        # Onaylanacak şey yüz satırlık bir Python dosyası olabiliyor ve
        # düz bir etiket olarak çubuğu ekran boyunun kat kat üstüne
        # çıkarıyordu: Reddet ve Çalıştır düğmeleri ekranın dışında kalıyor,
        # yani onay kutusu onaylanamaz hâle geliyordu.
        self._detail_scroll = QScrollArea()
        self._detail_scroll.setWidget(self._detail)
        self._detail_scroll.setWidgetResizable(True)
        self._detail_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._detail_scroll.setMaximumHeight(DETAIL_MAX_HEIGHT)
        self._detail_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._detail_scroll.setStyleSheet(
            f"QScrollArea {{ background: {t.control};"
            f" border: 1px solid {t.stroke};"
            f" border-radius: {RADIUS_CONTROL}px; }}"
            f"QScrollArea > QWidget > QWidget {{ background: transparent; }}"
            f"QScrollBar:vertical {{ background: transparent; width: 8px;"
            f" margin: 4px 2px; }}"
            f"QScrollBar::handle:vertical {{ background: {t.text_tertiary};"
            f" border-radius: 3px; min-height: 20px; }}"
            f"QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}"
            f"QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}"
        )
        layout.addWidget(self._detail_scroll)

        self._more = QLabel()
        self._more.setStyleSheet(f"color: {t.text_tertiary}; font-size: 11px; border: none;")
        self._more.setVisible(False)
        layout.addWidget(self._more)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(1)
        deny = QPushButton("Reddet")
        deny.setFixedHeight(30)
        deny.setCursor(Qt.CursorShape.PointingHandCursor)
        deny.clicked.connect(lambda: self.answered.emit(False))
        row.addWidget(deny)
        allow = QPushButton("Çalıştır")
        allow.setProperty("role", "accent")
        allow.setFixedHeight(30)
        allow.setCursor(Qt.CursorShape.PointingHandCursor)
        allow.clicked.connect(lambda: self.answered.emit(True))
        row.addWidget(allow)
        layout.addLayout(row)

    def ask(self, tool: str, detail: str, reason: str) -> None:
        self._reason.setText(f"{tool} — {reason}")
        self._detail.setText(detail)
        lines = detail.count("\n") + 1
        width = BAR_WIDTH - 28 - 16
        needed = self._detail.heightForWidth(width)
        self._detail_scroll.setFixedHeight(
            min(DETAIL_MAX_HEIGHT, max(40, needed) + 14)
        )
        # Kaydırma çubuğu tek başına "burada daha var" demeye yetmiyor;
        # onaylanan şeyin ne kadarını görmediğin yazıyor.
        kesik = needed + 14 > DETAIL_MAX_HEIGHT
        self._more.setText(f"{lines} satır — kaydırarak tamamını oku" if kesik else "")
        self._more.setVisible(kesik)


class CommandBar(QWidget):
    """Yüzen komut çubuğu: mikrofon, yazı alanı, işlem önizlemesi."""

    hold_started = Signal()
    hold_ended = Signal()
    submitted = Signal(str)

    def __init__(self, t: Tokens) -> None:
        super().__init__()
        self.t = t
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(BAR_WIDTH)

        self._drag_from: QPoint | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(0)

        self._card = QWidget()
        self._card.setObjectName("bar")
        self._card.setStyleSheet(
            f"#bar {{ background: {t.card}; border: 1px solid {t.stroke};"
            f" border-radius: {RADIUS_CARD}px; }}"
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 130))
        self._card.setGraphicsEffect(shadow)
        outer.addWidget(self._card)

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        self._grip = DragGrip(t)
        card_layout.addWidget(self._grip)

        # Konuşma: ajanın son söylediği. Sohbet geçmişi değil, son cevap —
        # köşede yüzen bir çubuk uzun bir dökümü taşıyamaz ve taşımaya
        # kalkarsa ekranın yarısını kaplar.
        # Kendi düzenini kuran bir widget: imlecin son harfin yanında
        # durabilmesi için satır kırılımlarının nerede olduğunu bilmek
        # gerekiyor ve `QLabel` bunu söylemiyor.
        self.reply = Akis(t)
        self.reply.setVisible(True)

        # Cevap kaydırılabilir bir alanda ve tavanı var. Önceden düz bir
        # etiketti: uzun bir cevap çubuğu ekran boyunun üstüne çıkaracak
        # kadar büyütüyor, yazı alanı da ekranın dışına düşüp kayboluyordu.
        # Artık cevap uzadıkça çubuk değil içerik kayıyor.
        self._reply_scroll = QScrollArea()
        self._reply_scroll.setWidget(self.reply)
        self._reply_scroll.setWidgetResizable(True)
        self._reply_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._reply_scroll.setMaximumHeight(REPLY_MAX_HEIGHT)
        self._reply_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._reply_scroll.setStyleSheet(
            f"QScrollArea, QScrollArea > QWidget > QWidget {{"
            f" background: transparent; border: none; }}"
            f"QScrollBar:vertical {{ background: transparent; width: 8px;"
            f" margin: 6px 2px 2px 0; }}"
            f"QScrollBar::handle:vertical {{ background: {t.text_tertiary};"
            f" border-radius: 3px; min-height: 24px; }}"
            f"QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}"
            f"QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}"
        )
        self._reply_scroll.setVisible(False)
        # Maskot solda dar bir sütunda, döküm sağında. Önce üstte bir
        # şeritti ve yanlıştı: bir iş başlayınca cevabı aşağı itiyor,
        # okuduğun yer kayıyordu. Sütunda hiçbir şey yer değiştirmiyor.
        self.ring = RunRing(t, RING_SIZE)
        self.sahne = Sahne(t, self.ring)
        self.sahne.setToolTip(
            "Ajan. Halkadaki her dilim bir adım, kırmızı olan düştü"
        )
        self.sahne.setVisible(False)

        self._govde = QWidget()
        govde = self._govde
        govde_yatay = QHBoxLayout(govde)
        govde_yatay.setContentsMargins(0, 0, 0, 0)
        govde_yatay.setSpacing(0)
        govde_yatay.addWidget(self.sahne, 0, Qt.AlignmentFlag.AlignTop)
        govde_yatay.addWidget(self._reply_scroll, 1)
        card_layout.addWidget(govde)

        self.preview = PreviewCard(t)
        self.preview.setVisible(False)
        card_layout.addWidget(self.preview)

        self.approval = ApprovalRow(t)
        self.approval.setVisible(False)
        card_layout.addWidget(self.approval)

        self._divider = QWidget()
        self._divider.setFixedHeight(1)
        self._divider.setStyleSheet(f"background: {t.divider};")
        self._divider.setVisible(False)
        card_layout.addWidget(self._divider)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(10, 8, 10, 8)
        row_layout.setSpacing(8)

        self.mic = MicDot(t)
        self.mic.pressed.connect(self.hold_started.emit)
        self.mic.released.connect(self.hold_ended.emit)
        row_layout.addWidget(self.mic)

        self._busy = False
        self.field = QLineEdit()
        self.field.setPlaceholderText("Yaz ya da konuş…")
        self.field.setFixedHeight(34)
        self.field.setStyleSheet(self._field_style(t))
        self.field.returnPressed.connect(self._submit)
        # Alana doğrudan yapılan tıklama `mousePressEvent`e ulaşmıyor —
        # QLineEdit onu yiyor. Süzgeç o tıklamayı da yakalıyor.
        self.field.installEventFilter(self)
        self.field.textChanged.connect(self._on_typing)
        row_layout.addWidget(self.field, 1)


        card_layout.addWidget(row)

        # Düğmeler yazı alanının hemen altında: elin oradayken tıklanacak
        # yer de orada olsun. Çubuk yukarı doğru büyüdüğü için satır
        # eklendiğinde yazı alanı yerinden kıpırdamıyor.
        self.buttons = ButtonStrip(t)
        self.buttons.triggered.connect(self._run_shortcut)
        self.buttons.changed.connect(self._grow)
        card_layout.addWidget(self.buttons)

        self._status = QLabel()
        self._status.setStyleSheet(
            f"color: {t.text_tertiary}; font-size: 11px; padding: 0 12px 8px 12px;"
        )
        self._status.setVisible(False)
        card_layout.addWidget(self._status)

        self._restore_position()

    # --- giriş ------------------------------------------------------------

    def _submit(self) -> None:
        text = self.field.text().strip()
        if text:
            self.field.clear()
            self.submitted.emit(text)

    def set_voice_available(self, available: bool) -> None:
        self.mic.set_available(available)
        if not available:
            self.set_status("Ses motoru bağlı değil — yazarak komut verebilirsin.")

    def _field_style(self, t: Tokens, live: bool = False) -> str:
        """Yazı alanının biçimi. `live` ajan çalışırken: alt kenar vurgu
        rengine dönüyor, yazdığın şeyin yeni bir iş değil süren işe
        eklendiği görünür olsun."""
        alt = t.accent if live else t.text_tertiary
        return (
            f"QLineEdit {{ background: {t.control};"
            f" border: 1px solid {t.control_stroke};"
            f" border-bottom: 2px solid {alt};"
            f" border-radius: {RADIUS_CONTROL}px; padding: 0 10px;"
            f" color: {t.text}; font-size: 14px;"
            f" selection-background-color: {t.accent};"
            f" selection-color: {t.on_accent}; }}"
            f"QLineEdit:focus {{ border-bottom-color: {t.accent}; }}"
        )

    def _run_shortcut(self, instruction: str) -> None:
        """Düğmeye basıldı. Metni alana yazıp göndermek yerine doğrudan
        gönderiyoruz; alanda yazılı bir şey varsa o kaybolmamalı."""
        if self.field.isEnabled():
            self.submitted.emit(instruction)

    def attach_buttons(self, store, extra_source=None) -> None:
        self.buttons.attach(store, extra_source)
        self._grow()

    def set_status(self, text: str) -> None:
        self._status.setText(text)
        self._status.setVisible(bool(text))

    def set_commands(self, source) -> None:
        """Komut listesini veren çağrılabilir. Liste değişebildiği için
        anlık sorulur; ajan az önce yeni bir komut yazmış olabilir."""
        self._command_source = source

    def _on_typing(self, text: str) -> None:
        """`/` yazınca eldeki komutlar görünüyor.

        Ayrı bir tamamlama penceresi açmıyoruz: çubuk zaten küçük ve yüzen
        bir pencere; üstüne ikinci bir açılır liste koymak onu ekranın
        dışına iten bir yığın yapardı.
        """
        source = getattr(self, "_command_source", None)
        if source is None or not text.startswith("/"):
            if getattr(self, "_showing_commands", False):
                self._showing_commands = False
                self.set_status("")
            return
        prefix = text[1:].split(" ")[0].lower()
        matches = [
            f"/{name} — {desc}"
            for name, desc in source()
            if name.startswith(prefix)
        ]
        self._showing_commands = True
        if matches:
            self.set_status("   ".join(matches[:4]))
        else:
            self.set_status(
                "Komut yok. Ajandan yazmasını isteyebilirsin."
                if prefix else "Henüz komut yok."
            )
        self._grow()

    def say(self, text: str) -> None:
        """Akış olmadan tek parça cevap — hata mesajları böyle geliyor."""
        self.reply.end_stream()
        if text:
            self.reply.say(text)
        self._fit_reply()

    def add_user(self, text: str) -> None:
        """Senin cümlen de aynı akışta duruyor: neye cevap verdiğini
        görmeden cevabı okumak eksik kalıyordu."""
        self.reply.add_user(text)
        self._fit_reply()

    def add_step(self, tool: str, baslik: str, detay: str) -> None:
        self.reply.add_step(tool, baslik, detay)
        self._fit_reply()

    def settle_step(self, is_error: bool) -> None:
        self.reply.mark_last(is_error)

    def set_tool(self, tool: str) -> None:
        """Sahnedeki nesne o anki işe göre değişiyor."""
        self.sahne.set_tool(tool)

    def clear_run(self) -> None:
        """Yeni talimat: önceki turun şekli ve dökümü gidiyor."""
        self.sahne.setVisible(False)
        self.sahne.clear()
        self.reply.clear()
        self._fit_reply()

    def stream(self, parca: str) -> None:
        """Modelden düşen parçayı akışa ekler.

        Model zaten parça parça yazıyordu; arayüz bunu çöpe atıp yalnızca
        tur bitince tek seferde gösteriyordu. Uzun bir turda dakikalarca
        boş bir kutuya bakıyordun.
        """
        self.reply.stream(parca)
        self._fit_reply()

    def end_stream(self) -> None:
        """Akış bitti — imleç sönüyor, metin kalıyor."""
        self.reply.end_stream()

    def _fit_reply(self) -> None:
        dolu = not self.reply.is_empty()
        self._reply_scroll.setVisible(dolu)
        # Kaydırma alanının yüksekliğini metne göre elle veriyoruz.
        # `QScrollArea` kendi boyut ipucunu içeriğinden almıyor; layout ona
        # küçük bir varsayılan veriyor ve kısa bir cevap bile üç satıra
        # sıkışıp kayıyordu — tavanın altında kalan cevap hiç kaymamalı.
        # Sütun genişliği düşülüyor: döküm artık bütün çubuğu değil,
        # maskotun sağında kalanı kaplıyor.
        width = BAR_WIDTH - 28 - 14 - self.sahne.width()
        needed = self.reply.heightForWidth(width) if dolu else 0
        yukseklik = min(REPLY_MAX_HEIGHT, max(0, needed) + 18)
        self._reply_scroll.setFixedHeight(yukseklik)
        # Sütun dökümle aynı boyda: maskot metnin yanında duruyor, altına
        # ya da üstüne taşmıyor.
        self.sahne.setFixedHeight(max(96, yukseklik))
        self._grow()
        bar = self._reply_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def ask_approval(self, tool: str, detail: str, reason: str) -> None:
        self.approval.ask(tool, detail, reason)
        self.approval.setVisible(True)
        self._grow()

    def clear_approval(self) -> None:
        self.approval.setVisible(False)
        self._grow()

    @property
    def busy(self) -> bool:
        return self._busy

    def set_busy(self, busy: bool) -> None:
        """Çalışırken yazı alanı **açık kalıyor**.

        Kapalıydı: ajan çalışırken yazamıyordun, yazdıysan da mesaj
        sessizce düşüyordu. Oysa bir işi izlerken araya bir cümle
        sıkıştırmak en çok istenen şey — "şunu da ekle", "orayı atla",
        "yanlış klasör". Artık kuyruğa giriyor ve ajan bir sonraki adımda
        görüyor.
        """
        self._busy = busy
        # Halka tur bitince **kalıyor**. Turun şekli — kaç adım sürdü,
        # hangisi düştü — cevabı okurken hâlâ orada. Bitince silmek, tam
        # da bakmak isteyeceğin anda veriyi çöpe atmak olurdu. Yeni bir
        # talimat verildiğinde `clear_run` siliyor.
        if busy:
            self.sahne.setVisible(True)
            self.ring.begin()
        else:
            self.ring.finish()
        self.field.setPlaceholderText(
            "Araya yaz — ajan sıradaki adımda görür" if busy
            else "Yaz ya da konuş…"
        )
        # Çalışırken alanın kenarı vurgu rengine dönüyor: yazdığın şeyin
        # yeni bir iş değil, süren işe eklendiği görünür olsun.
        self.field.setStyleSheet(
            self._field_style(self.t, live=busy)
        )

    def show_operation(self, op: Operation | None) -> None:
        visible = op is not None
        if op is not None:
            self.preview.show_operation(op)
        self.preview.setVisible(visible)
        self._divider.setVisible(visible)
        self._grow()

    def _grow(self) -> None:
        """Çubuk büyürken ekranın dışına taşmasın.

        Ekranın altına yakın duran bir pencere içerik eklendikçe aşağı
        doğru büyüyor ve alt kenarı ekranın dışına çıkıyor — cevap uzadıkça
        daha da kayboluyor. Alta yapışıksa yukarı doğru büyümeli: yazı
        alanı her zaman aynı yerde kalıyor, üstüne eklenen içerik yukarı
        açılıyor.
        """
        bottom_before = self.y() + self.height()
        # Yerleşimi önce zorla hesaplat. `adjustSize` bayat bir boyut
        # ipucuna bakıyordu ve çubuk bir tur geriden geliyordu: uzun cevap
        # geldiğinde eski yükseklikte kalıp metni kırpıyordu.
        self.layout().activate()
        # Sarmalayıcının düzeni de etkinleşmeli. Etkinleşmeyince kart
        # bayat bir boyut ipucuna bakıyor ve döküm kırpılıyordu —
        # ölçtüm: kaydırma alanı 147 pikseldi, kart 110'da kalıyordu.
        self._govde.layout().activate()
        self._card.layout().activate()
        self.adjustSize()

        area = None
        for screen in QApplication.screens():
            if screen.availableGeometry().contains(self.pos()):
                area = screen.availableGeometry()
                break
        if area is None:
            area = QApplication.primaryScreen().availableGeometry()

        # Yön boşluğa göre seçiliyor. Alt kenarı sabit tutup yukarı açılmak
        # çubuk ekranın altındayken doğru; tepedeyken yukarıda yer olmadığı
        # için o kural çubuğu ekranın altından taşırıyordu ve onay
        # düğmeleri görünmüyordu.
        top_room = bottom_before - self.height() - area.top()
        if top_room >= 0:
            y = bottom_before - self.height()      # alt kenar sabit, yukarı aç
        else:
            y = self.y()                            # yukarıda yer yok, aşağı aç

        # Ne olursa olsun tamamı ekranda: bu son satır çubuğun bir kenarının
        # dışarıda kalmasını imkânsız kılıyor.
        y = max(area.top(), min(y, area.bottom() - self.height() + 14))
        x = max(area.left() - 14, min(self.x(), area.right() - self.width() + 14))
        self.move(x, y)

    # --- konum ------------------------------------------------------------

    def _restore_position(self) -> None:
        """Çubuğu bıraktığın yere geri koyar.

        Kaydedilen üst kenar değil **alt kenar**. Çubuk uzun bir cevapta
        yukarı doğru büyüyor; üst kenarı kaydetmek her uzun cevaptan sonra
        çubuğu kalıcı olarak biraz yukarı taşıyordu ve birkaç turda ekranın
        ortasına tırmanıyordu. Alt kenar büyürken sabit kalan taraf.
        """
        self.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        default_bottom = screen.bottom() - MARGIN + 14
        default_x = screen.right() - BAR_WIDTH - MARGIN + 14
        try:
            saved = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            x, bottom = int(saved["x"]), int(saved["bottom"])
        except (OSError, ValueError, KeyError, TypeError):
            x, bottom = default_x, default_bottom

        # Ekran düzeni değişmiş olabilir; kaybolan pencereyi geri getir.
        # Çubuğun tamamı bakılıyor, tek bir köşesi değil: yarısı ikinci
        # ekranda kalmış bir çubuk da kaybolmuş sayılır.
        rect = QRect(x, bottom - self.height(), self.width(), self.height())
        if not any(
            s.availableGeometry().intersects(rect)
            and s.availableGeometry().contains(rect.center())
            for s in QApplication.screens()
        ):
            x, bottom = default_x, default_bottom
        self.move(x, bottom - self.height())

    def _save_position(self) -> None:
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(
                json.dumps({"x": self.x(), "bottom": self.y() + self.height()}),
                encoding="utf-8",
            )
        except OSError:
            pass  # konumu kaydedememek kullanıcıyı durduracak bir şey değil

    def eventFilter(self, watched, event) -> bool:
        if (watched is self.field
                and event.type() == QEvent.Type.MouseButtonPress):
            self.claim_focus()
        return super().eventFilter(watched, event)

    def showEvent(self, event) -> None:
        """Çubuk göründüğünde odak hazır olsun — tıklamak gerekmesin."""
        super().showEvent(event)
        QTimer.singleShot(0, self.claim_focus)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_from = event.globalPosition().toPoint() - self.pos()
            self.claim_focus()

    def claim_focus(self) -> None:
        """Çubuğu ön plana alıp yazı alanına odaklanır.

        Çubuk sahipsiz bir `Qt.Tool` penceresi: görev çubuğunda yeri yok ve
        ana pencereye bağlı değil, çünkü pencere kapansa da yaşamaya devam
        etmeli. Bedeli şu: uygulama hiç ön plana gelmediyse Windows ona
        klavye odağı vermiyor ve alana tıklasan da yazamıyorsun.

        `activateWindow()` tek başına yetmiyor — Windows ön plan hırsızlığı
        korumasına takılıyor ve çağrı sessizce yok sayılıyor. Ajanın başka
        pencereleri öne getirmek için kullandığı `force_foreground` burada
        da işi görüyor: ön plandaki thread'e bağlanıp izni alıyor.
        """
        self.raise_()
        self.activateWindow()
        try:
            from backend.computer.windows import force_foreground

            force_foreground(int(self.winId()))
        except Exception:
            pass  # odak alamamak yazmayı engelliyor, çökmeyi değil
        self.field.setFocus(Qt.FocusReason.MouseFocusReason)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_from is None:
            return
        point = event.globalPosition().toPoint() - self._drag_from
        self.move(self._clamp(point))

    def _clamp(self, point: QPoint) -> QPoint:
        """Çubuğu ekranın dışına kaçırmayı engeller.

        Sınırsız sürüklerken çubuk ekranın altından çıkıp kayboluyordu ve
        geri getirmenin yolu yoktu — pencere görünmediği için tutamayacağın
        bir şeyi geri sürükleyemiyorsun.
        """
        screens = [s.availableGeometry() for s in QApplication.screens()]
        if not screens:
            return point
        # Hangi ekrana en yakınsa ona göre sınırla: iki ekranlı kurulumda
        # birincil ekrana zorlamak çubuğu ikinciden koparırdı.
        centre = QPoint(point.x() + self.width() // 2, point.y() + self.height() // 2)
        area = min(
            screens,
            key=lambda a: (a.center() - centre).manhattanLength()
            if not a.contains(centre) else -1,
        )
        x = max(
            area.left() - self.width() + KEEP_ON_SCREEN,
            min(point.x(), area.right() - KEEP_ON_SCREEN),
        )
        y = max(
            area.top() - 14,
            min(point.y(), area.bottom() - KEEP_ON_SCREEN),
        )
        return QPoint(x, y)

    def mouseReleaseEvent(self, _event) -> None:
        if self._drag_from is not None:
            self._save_position()
            self._drag_from = None

    def paintEvent(self, _event) -> None:
        # Şeffaf pencere: gövdeyi kart widget'ı çiziyor, burada iş yok.
        pass
