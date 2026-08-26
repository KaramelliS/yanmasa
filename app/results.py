"""Araç sonuçlarının görünümü.

Bir adımın sonucu ham metin olarak basıldığında her sonuç birbirine
benziyor: dizin listesi, komut çıktısı ve yığın izi aynı gri paragraf. Bir
koşuya bakarken aranan şey ise hep aynı — nerede bozuldu, ne buldu.

Bu yüzden sonuç türüne göre görünüm değişiyor:

- **Hata** kırmızı bir şeritle ve tek satırlık özetle. Yığın izinin tamamı
  değil, hangi çağrının neden düştüğü.
- **Dizin listesi** klasör ve dosya çizimleriyle, ilk birkaç girdi. Sunucuda
  bir klasöre bakmak, o klasörün neye benzediğini görmek demek.
- **Komut çıktısı** eşaralıklı ve çerçeveli, terminalde nasıl görünüyorsa.
- **Kısa onay** olduğu gibi, tek satır.

Bir sonuç tanınmıyorsa metin olarak gösteriliyor — tanımadığını gizlemek,
gösterecek bir şey olmadığında boş bir kutu bırakmak olurdu.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .fluent import RADIUS_CONTROL, Tokens
from .glyphs import glyph_icon

#: Sonuç kutusunda gösterilecek en fazla satır. Fazlası listeyi bir çıktı
#: dökümüne çeviriyor ve adımlar arasında gezinmeyi imkânsız kılıyor.
MAX_LINES = 6

#: `remote_list` çıktısındaki satır: `  d drwxr-xr-x   3.2 KB 2026-08-14 ad`
_ENTRY = re.compile(
    r"^\s{2}(?P<kind>[d-])\s(?P<mode>[drwxst!@\-]{10})\s+"
    r"(?P<size>[\d.]* ?[KMGT]?B?)\s+"
    r"(?P<date>\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s+(?P<name>.+)$"
)


#: `TypeError: ...` gibi bir hata satırı. Yığın izindeki kaynak
#: satırlarından ayırt etmek için.
_EXCEPTION = re.compile(r"^[A-Za-z_][\w.]*(Error|Exception|Warning)?: \S")


def _short_error(text: str) -> str:
    """Yığın izinden okunabilir tek satır.

    `TypeError: Dispatcher._session() missing 1 required positional
    argument: 'payload'` gibi bir satır zaten yeterli; onu bir paragrafın
    içine gömmek okunmasını engelliyor.
    """
    lines = [line for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return ""
    # Python yığın izinde asıl hata **son** satırda. İlk uygun satırı almak
    # `return handler(payload)` gibi bir kaynak satırını hata sanıyordu —
    # bir testte yakalandı.
    for line in reversed(lines):
        if _EXCEPTION.match(line.strip()):
            return line.strip()
    return lines[-1].strip()


class ResultBox(QWidget):
    """Bir adımın sonucu."""

    def __init__(self, t: Tokens) -> None:
        super().__init__()
        self.t = t
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 4, 0, 0)
        self._layout.setSpacing(2)
        self.setVisible(False)

    def clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def show_result(self, tool: str, text: str, error: bool) -> None:
        self.clear()
        text = (text or "").strip()
        if not text:
            self.setVisible(False)
            return

        if error:
            self._error(text)
        elif tool == "remote_list" or _ENTRY.match(text.splitlines()[-1] if text else ""):
            self._listing(text)
        elif tool in ("remote_run", "run_shell", "terminal_read", "remote_read"):
            self._output(text)
        else:
            self._plain(text)
        self.setVisible(True)

    # --- görünümler -------------------------------------------------------

    def _error(self, text: str) -> None:
        row = QWidget()
        row.setStyleSheet(
            f"background: transparent;"
            f" border-left: 2px solid {self.t.critical};"
        )
        inner = QHBoxLayout(row)
        inner.setContentsMargins(8, 2, 0, 2)
        label = QLabel(_short_error(text))
        label.setWordWrap(True)
        label.setStyleSheet(
            f"color: {self.t.critical}; font-size: 12px; border: none;"
            f" font-family: '{self.t.font_mono}';"
        )
        inner.addWidget(label)
        self._layout.addWidget(row)

    def _listing(self, text: str) -> None:
        satirlar = [s for s in text.splitlines() if _ENTRY.match(s)]
        if not satirlar:
            return self._plain(text)

        grid = QWidget()
        grid.setStyleSheet("background: transparent;")
        box = QVBoxLayout(grid)
        box.setContentsMargins(0, 2, 0, 2)
        box.setSpacing(1)

        for satir in satirlar[:MAX_LINES]:
            parts = _ENTRY.match(satir).groupdict()
            klasor = parts["kind"] == "d"
            row = QHBoxLayout()
            row.setSpacing(8)

            icon = QLabel()
            icon.setPixmap(
                glyph_icon(
                    "klasor" if klasor else "sayfa", 14,
                    self.t.accent if klasor else self.t.text_secondary,
                    self.t.text_tertiary,
                ).pixmap(QSize(14, 14))
            )
            icon.setStyleSheet("border: none;")
            row.addWidget(icon)

            name = QLabel(parts["name"])
            name.setStyleSheet(
                f"color: {self.t.text if klasor else self.t.text_secondary};"
                f" font-size: 12px; border: none;"
                f" font-weight: {600 if klasor else 400};"
            )
            row.addWidget(name)
            row.addStretch(1)

            meta = QLabel(parts["size"].strip() or ("klasör" if klasor else ""))
            meta.setStyleSheet(
                f"color: {self.t.text_tertiary}; font-size: 11px; border: none;"
            )
            row.addWidget(meta)
            box.addLayout(row)

        if len(satirlar) > MAX_LINES:
            # Kaç tanesini görmediğin yazıyor; sessizce kesmek "hepsi bu"
            # diye okunurdu.
            more = QLabel(f"+{len(satirlar) - MAX_LINES} tane daha")
            more.setStyleSheet(
                f"color: {self.t.text_tertiary}; font-size: 11px; border: none;"
            )
            box.addWidget(more)
        self._layout.addWidget(grid)

    def _output(self, text: str) -> None:
        satirlar = text.splitlines()
        gosterilen = "\n".join(satirlar[:MAX_LINES])
        if len(satirlar) > MAX_LINES:
            gosterilen += f"\n… +{len(satirlar) - MAX_LINES} satır"

        label = QLabel(gosterilen)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setStyleSheet(
            f"color: {self.t.text_secondary}; font-size: 11px;"
            f" font-family: '{self.t.font_mono}';"
            f" background: {self.t.background_secondary};"
            f" border: 1px solid {self.t.stroke};"
            f" border-radius: {RADIUS_CONTROL}px; padding: 6px 8px;"
        )
        self._layout.addWidget(label)

    def _plain(self, text: str) -> None:
        satirlar = text.splitlines()
        gosterilen = "\n".join(satirlar[:MAX_LINES])
        if len(satirlar) > MAX_LINES:
            gosterilen += f"\n… +{len(satirlar) - MAX_LINES} satır"
        label = QLabel(gosterilen)
        label.setWordWrap(True)
        label.setStyleSheet(
            f"color: {self.t.text_tertiary}; font-size: 12px; border: none;"
        )
        self._layout.addWidget(label)
