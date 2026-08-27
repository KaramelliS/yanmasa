"""Kod görünümü — bir düzenleyicide ne bekliyorsan o.

Ajan diske kod koyuyor ve ona güvenmen için görmen gerekiyor. Düz metin bir
kutu bunu yapmıyor: yüz satırlık bir dosyada nerede olduğunu kaybediyorsun,
bir hatayı satır numarasıyla arayamıyorsun, hangi dosyanın açık olduğunu
göremiyorsun.

Burada olanlar: dosya ağacı, sekmeler, satır numarası cetveli, gerçek
sözdizimi renklendirmesi.

**Renklendirme `pygments` ile, düzenli ifadeyle değil.** Önceki sürüm elle
yazılmış desenler kullanıyordu ve çok satırlı metinlerde (üç tırnaklı
docstring, blok yorum) yanılıyordu: kapanmamış bir tırnak dosyanın geri
kalanını yanlış renklendiriyordu. `pygments` gerçek bir sözcük çözümleyici
ve 500'den fazla dil biliyor, yani ajanın yazabileceği her dil kapsanıyor.

Belge salt okunur olduğu için `QSyntaxHighlighter` kullanılmıyor: dosya bir
kez çözümlenip biçimler doğrudan uygulanıyor. Blok blok çalışan bir
vurgulayıcı, çok satırlı yapıların bağlamını zaten kaybediyor.

**Renkler temadan.** Kod renklendirmesi genelde kendi paletini getirir
(Monokai, Dracula) ve uygulamanın içinde yabancı durur. Buradaki beş ton
uygulamanın kendi tonları.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .fluent import Tokens
from .glyphs import glyph_icon

#: Bu boyutun üstündeki dosya renklendirilmiyor. `pygments` bir megabaytlık
#: dosyada saniyeler harcıyor ve o dosyaya zaten kimse göz atmıyor.
MAX_HIGHLIGHT = 400_000


def _token_colours(t: Tokens) -> dict[str, str]:
    """Pygments belirteç türü -> renk. Beş ton, hepsi temadan."""
    return {
        "Keyword": t.accent,
        "Name.Function": t.text,
        "Name.Class": t.text,
        "Name.Builtin": t.accent_text,
        "Name.Decorator": t.accent_text,
        "String": t.success,
        "Number": t.caution,
        "Comment": t.text_tertiary,
        "Operator": t.text_secondary,
        "Punctuation": t.text_secondary,
        "Error": t.critical,
    }


def _format_for(token, colours: dict[str, str]) -> QTextCharFormat | None:
    """Belirtecin en özgül eşleşmesi. `Name.Function.Magic` önce kendi
    adıyla, sonra `Name.Function`, sonra `Name` diye aranıyor."""
    parts = str(token).split(".")
    # `Token.Keyword.Namespace` -> "Keyword.Namespace" -> "Keyword"
    if parts and parts[0] == "Token":
        parts = parts[1:]
    while parts:
        colour = colours.get(".".join(parts))
        if colour:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(colour))
            if parts[0] == "Keyword":
                fmt.setFontWeight(QFont.Weight.DemiBold)
            if parts[0] == "Comment":
                fmt.setFontItalic(True)
            return fmt
        parts.pop()
    return None


def highlight(editor: QPlainTextEdit, path: str, text: str, t: Tokens) -> str:
    """Belgeyi renklendirir ve kullanılan dilin adını döndürür."""
    if len(text) > MAX_HIGHLIGHT:
        return "renklendirilmedi (çok büyük)"
    try:
        from pygments.lexers import get_lexer_for_filename, guess_lexer
        from pygments.util import ClassNotFound
    except ImportError:
        return "düz metin"

    try:
        lexer = get_lexer_for_filename(path, text)
    except ClassNotFound:
        try:
            lexer = guess_lexer(text)
        except ClassNotFound:
            return "düz metin"

    colours = _token_colours(t)
    document = editor.document()
    cursor = QTextCursor(document)
    cursor.beginEditBlock()
    for index, token, value in lexer.get_tokens_unprocessed(text):
        if not value.strip():
            continue
        fmt = _format_for(token, colours)
        if fmt is None:
            continue
        cursor.setPosition(index)
        cursor.setPosition(index + len(value), QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(fmt)
    cursor.endEditBlock()
    return lexer.name


class Gutter(QWidget):
    """Satır numarası cetveli."""

    def __init__(self, editor: Editor) -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.gutter_width(), 0)

    def paintEvent(self, event) -> None:
        self._editor.paint_gutter(event)


class Editor(QPlainTextEdit):
    """Satır numaralı, o anki satırı vurgulayan salt okunur düzenleyici."""

    def __init__(self, t: Tokens, path: str, text: str) -> None:
        super().__init__()
        self.t = t
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFrameShape(QPlainTextEdit.Shape.NoFrame)

        font = QFont(t.font_mono, 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        # Sekme dört boşluk: sekiz, girintili kodun yarısını sağa itiyor.
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.setStyleSheet(
            f"QPlainTextEdit {{ background: {t.background_secondary};"
            f" border: none; padding: 8px 10px 8px 0; color: {t.text};"
            f" selection-background-color: {t.accent};"
            f" selection-color: {t.on_accent}; }}"
        )
        self.setPlainText(text)
        self.language = highlight(self, path, text, t)

        self._matches: list[int] = []
        self._needle_len = 0
        self._gutter = Gutter(self)
        self.blockCountChanged.connect(lambda _n: self._resize_gutter())
        self.updateRequest.connect(self._scroll_gutter)
        self.cursorPositionChanged.connect(self._mark_line)
        self._resize_gutter()
        self._mark_line()

    # --- cetvel -----------------------------------------------------------

    def gutter_width(self) -> int:
        basamak = max(2, len(str(max(1, self.blockCount()))))
        return 14 + self.fontMetrics().horizontalAdvance("9") * basamak

    def _resize_gutter(self) -> None:
        genislik = self.gutter_width()
        self.setViewportMargins(genislik, 0, 0, 0)
        # Satır sayısı 99'u geçtiğinde cetvel bir basamak genişliyor;
        # sadece kenar boşluğunu büyütmek numaraları kırpardı.
        r = self.contentsRect()
        self._gutter.setGeometry(QRect(r.left(), r.top(), genislik, r.height()))

    def _scroll_gutter(self, rect: QRect, dy: int) -> None:
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._resize_gutter()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        r = self.contentsRect()
        self._gutter.setGeometry(QRect(r.left(), r.top(), self.gutter_width(), r.height()))

    def paint_gutter(self, event) -> None:
        painter = QPainter(self._gutter)
        painter.fillRect(event.rect(), QColor(self.t.background))
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()
        simdiki = self.textCursor().blockNumber()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor(
                    self.t.text_secondary if number == simdiki else self.t.text_disabled
                ))
                painter.drawText(
                    0, int(top), self._gutter.width() - 8,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight, str(number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            number += 1
        painter.end()

    def _mark_line(self) -> None:
        """O anki satırın arkası hafifçe aydınlanıyor. Uzun bir dosyada
        gözün nerede olduğunu kaybetmemesi için."""
        secim = QTextEdit.ExtraSelection()
        renk = QColor(self.t.accent)
        renk.setAlpha(30)
        secim.format.setBackground(renk)
        secim.format.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
        secim.cursor = self.textCursor()
        secim.cursor.clearSelection()
        self.setExtraSelections([secim] + self._match_selections())

    # --- arama ------------------------------------------------------------

    def _match_selections(self) -> list:
        vurgu = QColor(self.t.caution)
        vurgu.setAlpha(70)
        secimler = []
        for start, uzunluk in ((m, self._needle_len) for m in self._matches):
            secim = QTextEdit.ExtraSelection()
            secim.format.setBackground(vurgu)
            cursor = QTextCursor(self.document())
            cursor.setPosition(start)
            cursor.setPosition(start + uzunluk, QTextCursor.MoveMode.KeepAnchor)
            secim.cursor = cursor
            secimler.append(secim)
        return secimler

    def search(self, needle: str) -> int:
        """Eşleşmeleri işaretler ve sayısını döndürür.

        Büyük/küçük harf ayrımı yok: aradığın şeyi tam yazdığın gibi
        hatırlamıyorsun, `Path` mi `path` mi diye düşünmek zorunda kalma.
        """
        self._matches = []
        self._needle_len = len(needle)
        if needle:
            metin = self.toPlainText().casefold()
            aranan = needle.casefold()
            yer = metin.find(aranan)
            while yer != -1 and len(self._matches) < 2000:
                self._matches.append(yer)
                yer = metin.find(aranan, yer + 1)
        self._mark_line()
        return len(self._matches)

    @property
    def match_count(self) -> int:
        return len(self._matches)

    def jump(self, index: int) -> None:
        """Sıradaki eşleşmeye gider."""
        if not self._matches:
            return
        yer = self._matches[index % len(self._matches)]
        cursor = self.textCursor()
        cursor.setPosition(yer)
        cursor.setPosition(yer + self._needle_len, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)
        self.centerCursor()


class CodePane(QWidget):
    """Tek bir dosya: başlık şeridi, arama şeridi ve düzenleyici."""

    def __init__(self, t: Tokens, path: str, text: str) -> None:
        super().__init__()
        self.t = t
        self._hit = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.editor = Editor(t, path, text)
        layout.addWidget(self._header(t, path, text), 0)
        layout.addWidget(self._find_bar(t), 0)
        layout.addWidget(self.editor, 1)

        # Ctrl+F bir düzenleyicide refleks. Ajan "34. satırda hata" dediğinde
        # o satırı gözle aramak, üç yüz satırlık bir dosyada işkence.
        from PySide6.QtGui import QKeySequence, QShortcut

        for tus, hedef, is_ in (
            (QKeySequence.StandardKey.Find, self, self._open_find),
            (QKeySequence(Qt.Key.Key_Escape), self.find, self._close_find),
            (QKeySequence(Qt.Key.Key_Return), self.find, self._next),
            (QKeySequence(Qt.Key.Key_F3), self, self._next),
        ):
            kisayol = QShortcut(tus, hedef, is_)
            # Pencere kapsamı olsaydı bu panel açıkken Esc'i her yerde
            # yutardı; Esc'in başka işleri var.
            kisayol.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)

    def _find_bar(self, t: Tokens) -> QWidget:
        self.find = QWidget()
        self.find.hide()
        self.find.setStyleSheet(
            f"background: {t.background}; border-bottom: 1px solid {t.divider};"
        )
        row = QHBoxLayout(self.find)
        row.setContentsMargins(10, 5, 10, 5)
        row.setSpacing(8)

        self.needle = QLineEdit()
        self.needle.setPlaceholderText("Bu dosyada ara")
        self.needle.setFixedHeight(24)
        self.needle.setStyleSheet(
            f"QLineEdit {{ background: {t.background_secondary};"
            f" border: 1px solid {t.control_stroke}; border-radius: 4px;"
            f" padding: 2px 8px; color: {t.text}; font-size: 12px;"
            f" selection-background-color: {t.accent}; }}"
            f"QLineEdit:focus {{ border-color: {t.accent}; }}"
        )
        self.needle.textChanged.connect(self._search)
        row.addWidget(self.needle, 1)

        self.hits = QLabel("")
        # Sabit genişlik: sayaç "9 / 128"e büyürken arama alanının
        # kenarı oynamasın, ve "2 / 58" kırpılmasın.
        self.hits.setMinimumWidth(64)
        self.hits.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.hits.setStyleSheet(f"color: {t.text_tertiary}; font-size: 11px;")
        row.addWidget(self.hits)
        return self.find

    def _open_find(self) -> None:
        self.find.show()
        self.needle.setFocus()
        self.needle.selectAll()

    def _close_find(self) -> None:
        self.needle.clear()
        self.find.hide()
        self.editor.setFocus()

    def _search(self, needle: str) -> None:
        sayi = self.editor.search(needle)
        self._hit = 0
        if not needle:
            self.hits.setText("")
        elif sayi:
            self.hits.setText(f"1 / {sayi}")
            self.editor.jump(0)
        else:
            self.hits.setText("yok")

    def _next(self) -> None:
        toplam = self.editor.match_count
        if not toplam:
            return
        self._hit = (self._hit + 1) % toplam
        self.editor.jump(self._hit)
        self.hits.setText(f"{self._hit + 1} / {toplam}")

    def _header(self, t: Tokens, path: str, text: str) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(28)
        bar.setStyleSheet(
            f"background: {t.background}; border-bottom: 1px solid {t.divider};"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 4, 10, 4)
        row.setSpacing(8)

        yol = QLabel(path)
        yol.setStyleSheet(
            f"color: {t.text_tertiary}; font-size: 11px;"
            f" font-family: '{t.font_mono}';"
        )
        row.addWidget(yol)
        row.addStretch(1)

        meta = QLabel(f"{len(text.splitlines())} satır · {self.editor.language}")
        meta.setStyleSheet(f"color: {t.text_tertiary}; font-size: 11px;")
        row.addWidget(meta)
        return bar


class IdeView(QWidget):
    """Dosya ağacı ve sekmeler — ajanın kurduğu projeye bakma yeri."""

    opened = Signal(str)

    def __init__(self, t: Tokens, root: str) -> None:
        super().__init__()
        self.t = t
        self.root = Path(root)
        self._open: dict[str, int] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._tree(t))
        split.addWidget(self._tabs(t))
        split.setStretchFactor(1, 1)
        split.setSizes([230, 700])
        layout.addWidget(split)
        self.reload()

    def _tree(self, t: Tokens) -> QWidget:
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setIconSize(QSize(15, 15))
        self.tree.setStyleSheet(
            f"QTreeWidget {{ background: {t.background}; border: none;"
            f" border-right: 1px solid {t.divider};"
            f" color: {t.text_secondary}; font-size: 12px; outline: none; }}"
            f"QTreeWidget::item {{ height: 24px; }}"
            f"QTreeWidget::item:hover {{ background: {t.subtle_hover}; }}"
            f"QTreeWidget::item:selected {{ background: {t.accent};"
            f" color: {t.on_accent}; }}"
        )
        self.tree.itemActivated.connect(self._activate)
        self.tree.itemClicked.connect(self._activate)
        return self.tree

    def _tabs(self, t: Tokens) -> QWidget:
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self._close)
        self.tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: none; }}"
            f"QTabBar::tab {{ background: {t.background};"
            f" border: none; border-bottom: 2px solid transparent;"
            f" padding: 6px 12px; margin: 0; color: {t.text_secondary};"
            f" font-size: 12px; }}"
            f"QTabBar::tab:selected {{ color: {t.text};"
            f" border-bottom-color: {t.accent};"
            f" background: {t.background_secondary}; }}"
            f"QTabBar::tab:hover {{ background: {t.subtle_hover}; }}"
        )
        return self.tabs

    # --- ağaç -------------------------------------------------------------

    def reload(self) -> None:
        self.tree.clear()
        if not self.root.exists():
            return
        self._fill(self.tree.invisibleRootItem(), self.root, depth=0)
        self.tree.expandToDepth(1)

    def _fill(self, parent, folder: Path, depth: int) -> None:
        if depth > 4:
            return
        try:
            girdiler = sorted(
                folder.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
            )
        except OSError:
            return
        for path in girdiler:
            # Derleme çıktısı ve gizli klasörler gürültü; ajanın yazdığı
            # kodu ararken __pycache__ içinde kaybolmak istemiyorsun.
            if path.name.startswith(".") or path.name in {
                "__pycache__", "node_modules", ".git", ".venv"
            }:
                continue
            item = QTreeWidgetItem(parent, [path.name])
            item.setIcon(0, glyph_icon(
                "klasor" if path.is_dir() else "sayfa", 15,
                self.t.accent if path.is_dir() else self.t.text_secondary,
                self.t.text_tertiary,
            ))
            if path.is_dir():
                self._fill(item, path, depth + 1)
            else:
                item.setData(0, Qt.ItemDataRole.UserRole, str(path))

    def set_root(self, root: str) -> None:
        """Ağacı başka bir klasöre taşır.

        Ajan bir işte `C:/proje-a`, sonrakinde `C:/proje-b` altına yazıyor.
        Her seferinde yeni bir panel açmak ekranı sekmelerle doldururdu;
        tek panel kalıyor, kökü değişiyor.
        """
        yeni = Path(root)
        if yeni == self.root:
            return
        self.root = yeni
        self.reload()

    def _activate(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path:
            self.open_file(str(path))

    # --- sekmeler ---------------------------------------------------------

    def open_file(self, path: str) -> None:
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            text = f"Okunamadı: {exc}"

        acik = self._open.get(path)
        if acik is not None:
            # Ajan aynı dosyayı ikinci kez yazdığında sekme tazeleniyor.
            # Sadece öne getirmek, diskteki koddan farklı bir şey
            # gösterirdi — kodu görmenin bütün amacı bu değil.
            eski_pane = self.tabs.widget(acik)
            if eski_pane.editor.toPlainText() != text:
                self.tabs.removeTab(acik)
                self.tabs.insertTab(acik, CodePane(self.t, path, text),
                                    Path(path).name)
                self.tabs.setTabToolTip(acik, path)
            self.tabs.setCurrentIndex(acik)
            return

        index = self.tabs.addTab(CodePane(self.t, path, text), Path(path).name)
        self.tabs.setTabToolTip(index, path)
        self._open[path] = index
        self.tabs.setCurrentIndex(index)
        self.opened.emit(path)

    def _close(self, index: int) -> None:
        for path, i in list(self._open.items()):
            if i == index:
                del self._open[path]
        self.tabs.removeTab(index)
        # Kalan sekmelerin indeksleri kaydı; yeniden eşleştir.
        self._open = {
            self.tabs.tabToolTip(i): i for i in range(self.tabs.count())
        }
