"""Ajanın yazdığı kod.

Bir dosya yazıldığında "yazıldı" demek yetmiyor: ajan senin diskine kod
koyuyor ve o kodu görmeden ona güvenmen gerekiyor. Panel yazılan dosyayı
olduğu gibi gösteriyor.

Renklendirme sözdizimi ağacı kurmuyor, düzenli ifadeyle çalışıyor. Bir
görüntüleyici için doğru olan bu: kodu çalıştırmıyoruz, okunur kılıyoruz.
Tam bir ayrıştırıcı her dil için ayrı bakım demek ve bu panelin kazandırdığı
şeyi kazandırmıyor.

Renkler temadan geliyor. Kod renklendirmesi genelde kendi paletini getirir
ve uygulamanın içinde yabancı durur; buradaki dört ton uygulamanın kendi
tonları — vurgu, ikincil metin, üçüncül metin, uyarı.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from .fluent import RADIUS_CONTROL, Tokens
from .glyphs import glyph_icon

#: Uzantı -> dil. Tanınmayan uzantı düz metin olarak gösteriliyor;
#: yanlış dille renklendirmek renklendirmemekten kötü.
LANGUAGES = {
    ".py": "python", ".pyw": "python",
    ".js": "c", ".ts": "c", ".jsx": "c", ".tsx": "c",
    ".c": "c", ".h": "c", ".cpp": "c", ".cs": "c", ".java": "c",
    ".go": "c", ".rs": "c", ".php": "c", ".swift": "c", ".kt": "c",
    ".sh": "shell", ".bash": "shell", ".ps1": "shell",
    ".json": "data", ".yml": "data", ".yaml": "data", ".toml": "data",
    ".ini": "data", ".cfg": "data", ".env": "data",
    ".html": "markup", ".xml": "markup", ".svg": "markup",
    ".css": "markup", ".md": "markup",
    ".sql": "c",
}

KEYWORDS = {
    "python": (
        "and as assert async await break class continue def del elif else "
        "except finally for from global if import in is lambda nonlocal not "
        "or pass raise return try while with yield None True False self"
    ),
    "c": (
        "async await break case catch class const continue default delete do "
        "else enum export extends false finally for from func function get if "
        "implements import in instanceof interface let new null package "
        "private protected public return set static struct super switch this "
        "throw true try type typeof var void while yield"
    ),
    "shell": (
        "if then else elif fi for while do done case esac function return "
        "export local readonly set unset source echo exit param begin end"
    ),
    "data": "true false null",
    "markup": "",
}


def language_for(path: str) -> str:
    for suffix, language in LANGUAGES.items():
        if path.lower().endswith(suffix):
            return language
    return "duz"


class Highlighter(QSyntaxHighlighter):
    def __init__(self, document, t: Tokens, language: str) -> None:
        super().__init__(document)
        self.rules: list[tuple[QRegularExpression, QTextCharFormat]] = []

        def bicim(colour: str, bold: bool = False, italic: bool = False):
            f = QTextCharFormat()
            f.setForeground(QColor(colour))
            if bold:
                f.setFontWeight(QFont.Weight.DemiBold)
            f.setFontItalic(italic)
            return f

        anahtar = bicim(t.accent, bold=True)
        metin = bicim(t.success)
        sayi = bicim(t.caution)
        yorum = bicim(t.text_tertiary, italic=True)

        kelimeler = KEYWORDS.get(language, "")
        for kelime in kelimeler.split():
            self.rules.append(
                (QRegularExpression(rf"\b{kelime}\b"), anahtar)
            )

        if language == "markup":
            self.rules.append((QRegularExpression(r"</?[\w:-]+"), anahtar))

        # Sayı ve metin her dilde aynı; yorum işareti dile göre değişiyor.
        self.rules.append(
            (QRegularExpression(r"\b\d+(\.\d+)?\b"), sayi)
        )
        self.rules.append(
            (QRegularExpression(r"'[^'\\]*(\\.[^'\\]*)*'"), metin)
        )
        self.rules.append(
            (QRegularExpression(r'"[^"\\]*(\\.[^"\\]*)*"'), metin)
        )
        # Yorumlar en sonda: bir yorumun içindeki tırnak metin sayılmasın.
        yorum_deseni = {
            "python": r"#[^\n]*",
            "shell": r"#[^\n]*",
            "c": r"//[^\n]*",
            "data": r"(#|//)[^\n]*",
            "markup": r"<!--[^>]*-->",
        }.get(language)
        if yorum_deseni:
            self.rules.append((QRegularExpression(yorum_deseni), yorum))

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self.rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


class CodeView(QWidget):
    """Yazılan dosyanın görünümü: başlık, satır sayısı, kod."""

    def __init__(self, t: Tokens, path: str, content: str) -> None:
        super().__init__()
        self.t = t
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        dil = language_for(path)
        layout.addWidget(self._header(t, path, content, dil))

        self.editor = QPlainTextEdit(content)
        self.editor.setReadOnly(True)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont(t.font_mono, 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.editor.setFont(font)
        # Sekme dört boşluk genişliğinde: sekiz, kodun yarısını sağa itiyor.
        self.editor.setTabStopDistance(
            4 * self.editor.fontMetrics().horizontalAdvance(" ")
        )
        self.editor.setStyleSheet(
            f"QPlainTextEdit {{ background: {t.background_secondary};"
            f" border: none; padding: 10px 12px; color: {t.text};"
            f" selection-background-color: {t.accent};"
            f" selection-color: {t.on_accent}; }}"
        )
        if dil != "duz":
            self._highlighter = Highlighter(self.editor.document(), t, dil)
        layout.addWidget(self.editor, 1)

    def _header(self, t: Tokens, path: str, content: str, dil: str) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(38)
        bar.setStyleSheet(
            f"background: {t.background}; border-bottom: 1px solid {t.divider};"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 6, 12, 6)
        row.setSpacing(8)

        icon = QLabel()
        icon.setPixmap(
            glyph_icon("sayfa", 16, t.accent, t.text_tertiary).pixmap(16, 16)
        )
        row.addWidget(icon)

        ad = QLabel(path.replace("\\", "/").rsplit("/", 1)[-1])
        ad.setStyleSheet(
            f"color: {t.text}; font-size: 13px; font-weight: 600;"
        )
        row.addWidget(ad)

        satir = len(content.splitlines())
        meta = QLabel(f"{satir} satır · {dil}" if dil != "duz" else f"{satir} satır")
        meta.setStyleSheet(f"color: {t.text_tertiary}; font-size: 11px;")
        row.addWidget(meta)
        row.addStretch(1)

        yol = QLabel(path)
        yol.setStyleSheet(
            f"color: {t.text_tertiary}; font-size: 11px;"
            f" font-family: '{t.font_mono}';"
        )
        yol.setToolTip(path)
        row.addWidget(yol)
        return bar
