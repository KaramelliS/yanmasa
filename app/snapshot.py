"""Belgenin arayüze geçen anlık görüntüsü.

Ajan `openpyxl` ve `python-docx` nesnelerini kendi thread'inde tutuyor. O
nesneleri arayüz thread'inden okumak, ajan bir sonraki hücreyi yazarken
listeyi gezmek demek — sessiz ve tekrar üretilemeyen bir yarış.

Bu yüzden panel canlı nesneyi değil, araç çağrısı biter bitmez ajanın kendi
thread'inde çıkarılan düz bir kopyayı gösteriyor. Kopyada Qt nesnesi yok;
sadece metin, sayı ve gerekçe.

Gerekçeler defterden hücre/paragraf başına eşleştiriliyor: panelde bir hücre
vurguluysa üstüne gelince ajanın onu neden değiştirdiği yazıyor.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Panelde gösterilecek üst sınır. Ajan 50 000 hücrelik bir tablo açarsa
#: arayüz onu çizmeye çalışırken donar; ajan yine de tamamını okuyabiliyor.
MAX_ROWS = 200
MAX_COLS = 40
MAX_PARAS = 400


@dataclass
class DocSnapshot:
    name: str
    kind: str                       # "sheet" | "text"
    path: str
    unsaved: int
    sheets: list[str] = field(default_factory=list)
    #: (hücre metni, formül mü, gerekçe, hesaplanmış sonuç)
    rows: list[list[tuple[str, bool, str | None, str | None]]] = field(
        default_factory=list
    )
    #: (metin, stil, gerekçe)
    paragraphs: list[tuple[str, str, str | None]] = field(default_factory=list)
    truncated: bool = False


def _reasons(document) -> dict[str, str]:
    return {c.target: c.why for c in document.ledger.recent(limit=500)}


def snapshot(name: str, document) -> DocSnapshot | None:
    """Ajanın thread'inde çağrılır. Hata hâlinde panel açılmaz, çökmez."""
    try:
        if document.kind == "sheet":
            return _workbook(name, document)
        return _text(name, document)
    except Exception:
        # Bir belgeyi gösterememek, ajanın işini durdurmayı hak etmiyor.
        return None


def _workbook(name: str, document) -> DocSnapshot:
    ws = document.book.active
    why = _reasons(document)
    max_row = min(ws.max_row or 1, MAX_ROWS)
    max_col = min(ws.max_column or 1, MAX_COLS)

    computed = document.values()
    rows: list[list[tuple[str, bool, str | None, str | None]]] = []
    for r in range(1, max_row + 1):
        row: list[tuple[str, bool, str | None, str | None]] = []
        for c in range(1, max_col + 1):
            cell = ws.cell(row=r, column=c)
            value = "" if cell.value is None else str(cell.value)
            row.append((
                value,
                value.startswith("="),
                why.get(f"{ws.title}!{cell.coordinate}"),
                computed.get(f"{ws.title}!{cell.coordinate}"),
            ))
        rows.append(row)

    return DocSnapshot(
        name=name,
        kind="sheet",
        path=document.path,
        unsaved=document.ledger.unsaved_count,
        sheets=list(document.book.sheetnames),
        rows=rows,
        truncated=(ws.max_row or 0) > MAX_ROWS or (ws.max_column or 0) > MAX_COLS,
    )


def _text(name: str, document) -> DocSnapshot:
    why = _reasons(document)
    paragraphs = document.doc.paragraphs[:MAX_PARAS]
    return DocSnapshot(
        name=name,
        kind="text",
        path=document.path,
        unsaved=document.ledger.unsaved_count,
        paragraphs=[
            (p.text, p.style.name if p.style is not None else "Normal",
             why.get(f"paragraph {i}"))
            for i, p in enumerate(paragraphs)
        ],
        truncated=len(document.doc.paragraphs) > MAX_PARAS,
    )
