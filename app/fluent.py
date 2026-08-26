"""Fluent Design — Windows 11'in kendi tasarım dili.

Bu bir yorum değil, uyum. Uygulama Dosya Gezgini ve Ayarlar'ın yanında
durduğunda oradan gelmiş gibi görünmeli: aynı yazı tipi, aynı köşe
yarıçapı, aynı katman renkleri, aynı tip rampası.

Renkler uydurulmuyor, **sistemden okunuyor**. Berkay temasını açığa alırsa
uygulama açılıyor; vurgu rengini değiştirirse uygulama onu alıyor. Sabit
bir palet yazmak, Fluent olduğunu iddia edip Fluent'in tek gerçek kuralını
çiğnemek olurdu.

Token adları WinUI 3'ün kendi adları; başka bir yerden bakan biri
karşılığını bulabilsin diye.
"""

from __future__ import annotations

import winreg
from dataclasses import dataclass

PERSONALIZE = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize"
ACCENT_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Accent"

#: Fluent köşe yarıçapları. Denetim 4, kart ve katman 8.
RADIUS_CONTROL = 4
RADIUS_CARD = 8

#: Fluent boşluk ritmi.
GAP = 4


def _read(root, path: str, name: str):
    try:
        with winreg.OpenKey(root, path) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def system_is_dark() -> bool:
    value = _read(winreg.HKEY_CURRENT_USER, PERSONALIZE, "AppsUseLightTheme")
    return value == 0 if value is not None else True


def _blend(fg: str, alpha: float, bg: str) -> str:
    """Yarı saydam bir Fluent token'ını zemine karıştırıp katı renk üretir.

    Qt stil sayfası rgba()'yı ebeveyn üstüne doğru şekilde bindirmiyor;
    önceden karıştırmak aynı pikseli veriyor ve sürprizi ortadan
    kaldırıyor.
    """
    f = [int(fg[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(bg[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(f[i] * alpha + b[i] * (1 - alpha)):02x}" for i in range(3))


def accent_palette() -> list[str]:
    """Sistemin vurgu paleti: en açıktan en koyuya sekiz renk."""
    blob = _read(winreg.HKEY_CURRENT_USER, ACCENT_KEY, "AccentPalette")
    if not blob or len(blob) < 32:
        # Windows'un varsayılan mavisi. Kayıt okunamadıysa uydurmak yerine
        # bilinen sistem varsayılanına düşmek doğru.
        return [
            "#99EBFF", "#4CC2FF", "#0091F8", "#0078D4",
            "#005EB7", "#003D92", "#001A68", "#68278F",
        ]
    return [
        "#{:02x}{:02x}{:02x}".format(blob[i * 4 + 2], blob[i * 4 + 1], blob[i * 4])
        for i in range(8)
    ]


@dataclass(frozen=True)
class Tokens:
    """WinUI 3 token'larının bu makinedeki karşılıkları."""

    dark: bool

    # Zeminler
    background: str
    background_secondary: str
    layer: str
    card: str
    card_hover: str
    control: str
    control_hover: str
    control_pressed: str
    subtle_hover: str

    # Kenarlar
    stroke: str
    divider: str
    control_stroke: str

    # Metin
    text: str
    text_secondary: str
    text_tertiary: str
    text_disabled: str

    # Vurgu ve durum
    accent: str
    accent_hover: str
    accent_text: str
    on_accent: str
    critical: str
    caution: str
    success: str

    @property
    def font_ui(self) -> str:
        # Segoe UI Variable Windows 11'in metin yüzü; Windows 10'da yok.
        return "Segoe UI Variable Text"

    @property
    def font_display(self) -> str:
        return "Segoe UI Variable Display"

    @property
    def font_mono(self) -> str:
        return "Cascadia Mono"


def tokens() -> Tokens:
    dark = system_is_dark()
    palette = accent_palette()
    light2, light1, base = palette[1], palette[2], palette[3]

    if dark:
        bg = "#202020"
        return Tokens(
            dark=True,
            background=bg,
            background_secondary="#1c1c1c",
            layer=_blend("#3a3a3a", 0.30, bg),
            card=_blend("#ffffff", 0.0512, bg),
            card_hover=_blend("#ffffff", 0.0837, bg),
            control=_blend("#ffffff", 0.0605, bg),
            control_hover=_blend("#ffffff", 0.0837, bg),
            control_pressed=_blend("#ffffff", 0.0326, bg),
            subtle_hover=_blend("#ffffff", 0.0605, bg),
            stroke=_blend("#ffffff", 0.0698, bg),
            divider=_blend("#ffffff", 0.0837, bg),
            control_stroke=_blend("#ffffff", 0.0698, bg),
            text="#ffffff",
            text_secondary=_blend("#ffffff", 0.786, bg),
            text_tertiary=_blend("#ffffff", 0.5442, bg),
            text_disabled=_blend("#ffffff", 0.3628, bg),
            # Koyu temada Fluent taban vurguyu değil açık varyantını
            # kullanıyor; taban renk koyu zeminde okunmuyor.
            accent=light2,
            accent_hover=light1,
            accent_text=light2,
            on_accent="#000000",
            critical="#ff99a4",
            caution="#fce100",
            success="#6ccb5f",
        )

    bg = "#f3f3f3"
    return Tokens(
        dark=False,
        background=bg,
        background_secondary="#eeeeee",
        layer=_blend("#ffffff", 0.50, bg),
        card=_blend("#ffffff", 0.70, bg),
        card_hover=_blend("#ffffff", 0.50, bg),
        control=_blend("#ffffff", 0.70, bg),
        control_hover=_blend("#f9f9f9", 0.50, bg),
        control_pressed=_blend("#f9f9f9", 0.30, bg),
        subtle_hover=_blend("#000000", 0.0373, bg),
        stroke=_blend("#000000", 0.0578, bg),
        divider=_blend("#000000", 0.0803, bg),
        control_stroke=_blend("#000000", 0.0578, bg),
        text=_blend("#000000", 0.8956, bg),
        text_secondary=_blend("#000000", 0.6063, bg),
        text_tertiary=_blend("#000000", 0.4458, bg),
        text_disabled=_blend("#000000", 0.3614, bg),
        accent=base,
        accent_hover=palette[4],
        accent_text=palette[4],
        on_accent="#ffffff",
        critical="#c42b1c",
        caution="#9d5d00",
        success="#0f7b0f",
    )


def apply(app) -> Tokens:
    """Paleti ve stil sayfasını uygular, kullanılan token'ları döndürür."""
    from PySide6.QtGui import QColor, QFont, QPalette

    t = tokens()
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(t.background))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(t.text))
    palette.setColor(QPalette.ColorRole.Base, QColor(t.background_secondary))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(t.card))
    palette.setColor(QPalette.ColorRole.Text, QColor(t.text))
    palette.setColor(QPalette.ColorRole.Button, QColor(t.control))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(t.text))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(t.accent))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(t.on_accent))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(t.card))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(t.text))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(t.text_tertiary))
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(t.text_disabled)
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor(t.text_disabled),
    )
    app.setPalette(palette)

    font = QFont(t.font_ui, 10)  # Fluent gövde ölçüsü 14px ≈ 10.5pt
    font.setHintingPreference(QFont.HintingPreference.PreferDefaultHinting)
    app.setFont(font)
    app.setStyleSheet(stylesheet(t))
    return t


def stylesheet(t: Tokens) -> str:
    return f"""
QWidget {{
    background: transparent;
    color: {t.text};
    font-family: "{t.font_ui}", "Segoe UI", sans-serif;
    font-size: 14px;
}}
QMainWindow, QDialog {{ background: {t.background}; }}

QMainWindow::separator {{ background: {t.divider}; width: 1px; height: 1px; }}
QMainWindow::separator:hover {{ background: {t.accent}; }}

/* Kart: Fluent'in temel yüzeyi. Köşe 8, kenar hairline. */
QDockWidget {{ font-size: 12px; color: {t.text_secondary}; }}
QDockWidget::title {{
    background: {t.background};
    padding: 8px 12px;
    text-align: left;
    border: none;
}}
QDockWidget > QWidget {{
    background: {t.card};
    border: 1px solid {t.stroke};
    border-radius: {RADIUS_CARD}px;
}}

QLabel {{ background: transparent; }}
QLabel[role="caption"] {{ font-size: 12px; color: {t.text_secondary}; }}
QLabel[role="tertiary"] {{ font-size: 12px; color: {t.text_tertiary}; }}
QLabel[role="strong"] {{ font-size: 14px; font-weight: 600; }}
QLabel[role="subtitle"] {{
    font-family: "{t.font_display}", "{t.font_ui}", "Segoe UI";
    font-size: 20px; font-weight: 600;
}}
QLabel[role="critical"] {{ font-size: 12px; color: {t.critical}; }}
QLabel[role="mono"] {{ font-family: "{t.font_mono}", Consolas; font-size: 12px; }}

QPushButton {{
    background: {t.control};
    border: 1px solid {t.control_stroke};
    border-radius: {RADIUS_CONTROL}px;
    padding: 5px 12px;
    color: {t.text};
    font-size: 14px;
}}
QPushButton:hover {{ background: {t.control_hover}; }}
QPushButton:pressed {{ background: {t.control_pressed}; color: {t.text_secondary}; }}
QPushButton:disabled {{ color: {t.text_disabled}; }}

QPushButton[role="accent"] {{
    background: {t.accent};
    border: 1px solid {t.accent};
    color: {t.on_accent};
    font-weight: 600;
}}
QPushButton[role="accent"]:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}

QPushButton[role="subtle"] {{ background: transparent; border-color: transparent; }}
QPushButton[role="subtle"]:hover {{ background: {t.subtle_hover}; }}

QPlainTextEdit, QTextEdit, QTextBrowser {{
    background: {t.background_secondary};
    border: 1px solid {t.stroke};
    border-radius: {RADIUS_CONTROL}px;
    padding: 6px;
    font-family: "{t.font_mono}", Consolas, monospace;
    font-size: 13px;
    selection-background-color: {t.accent};
    selection-color: {t.on_accent};
}}

QTableView {{
    background: {t.background_secondary};
    gridline-color: {t.divider};
    border: none;
    border-radius: {RADIUS_CONTROL}px;
    font-size: 14px;
    selection-background-color: {t.accent};
    selection-color: {t.on_accent};
}}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background: {t.background};
    color: {t.text_secondary};
    border: none;
    border-right: 1px solid {t.divider};
    border-bottom: 1px solid {t.divider};
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 600;
}}
QTableCornerButton::section {{
    background: {t.background};
    border: none;
    border-right: 1px solid {t.divider};
    border-bottom: 1px solid {t.divider};
}}

QScrollBar:vertical, QScrollBar:horizontal {{ background: transparent; border: none; }}
QScrollBar:vertical {{ width: 12px; }}
QScrollBar:horizontal {{ height: 12px; }}
QScrollBar::handle {{
    background: {t.text_tertiary};
    border-radius: 3px;
    margin: 3px;
}}
QScrollBar::handle:hover {{ background: {t.text_secondary}; }}
QScrollBar::handle:vertical {{ min-height: 32px; }}
QScrollBar::handle:horizontal {{ min-width: 32px; }}
QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {{
    background: none; border: none; height: 0; width: 0;
}}

QToolTip {{
    background: {t.card};
    color: {t.text};
    border: 1px solid {t.stroke};
    border-radius: {RADIUS_CONTROL}px;
    padding: 6px 8px;
    font-size: 12px;
}}

QToolBar {{ background: {t.background}; border: none; spacing: 0; padding: 0; }}
QSplitter::handle {{ background: {t.divider}; }}
"""
