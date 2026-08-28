"""Açık belgeler.

Terminal oturumlarıyla aynı desen: ajan belgelere isimle erişiyor, belge
açık kaldığı sürece değişiklik defteri de yaşıyor. Her araç çağrısında
dosyayı diskten yeniden açmak defteri sıfırlardı ve gerekçe zinciri
kopardı.
"""

from __future__ import annotations

from pathlib import Path

from .model import OfficeDocument
from .sheet import SheetError, Workbook
from .text import TextDocument, TextError

SHEET_SUFFIXES = {".xlsx", ".xlsm"}
TEXT_SUFFIXES = {".docx"}


class OfficeError(RuntimeError):
    """Belge açılamadı ya da bulunamadı."""


class OfficeStore:
    MAX_OPEN = 8

    def __init__(self) -> None:
        self._documents: dict[str, OfficeDocument] = {}

    def open(self, name: str, path: str, create: bool = False) -> OfficeDocument:
        if name in self._documents:
            raise OfficeError(
                f"A document named {name!r} is already open. Give another name or "
                f"close that one first."
            )
        if len(self._documents) >= self.MAX_OPEN:
            raise OfficeError(
                f"At most {self.MAX_OPEN} documents can be open. Close one."
            )

        target = Path(path).expanduser()
        suffix = target.suffix.lower()
        try:
            if suffix in SHEET_SUFFIXES:
                document = (
                    Workbook.create(str(target))
                    if create or not target.exists()
                    else Workbook.open(str(target))
                )
            elif suffix in TEXT_SUFFIXES:
                document = (
                    TextDocument.create(str(target))
                    if create or not target.exists()
                    else TextDocument.open(str(target))
                )
            else:
                raise OfficeError(
                    f"{suffix or '(no extension)'} is not supported. "
                    f"Use .xlsx for a sheet and .docx for a text document."
                )
        except (SheetError, TextError) as exc:
            raise OfficeError(str(exc)) from None

        self._documents[name] = document
        return document

    def get(self, name: str) -> OfficeDocument:
        document = self._documents.get(name)
        if document is None:
            known = ", ".join(sorted(self._documents)) or "none"
            raise OfficeError(f"{name!r} is not open. Open documents: {known}")
        return document

    def close(self, name: str) -> str:
        document = self._documents.get(name)
        if document is None:
            raise OfficeError(f"{name!r} is not open")
        if document.ledger.dirty:
            # Sessizce kapatmak, ajanın kaydettiğini sanmasına yol açar.
            raise OfficeError(
                f"The document {name!r} has {document.ledger.unsaved_count} "
                f"unsaved changes. Save it first, or pass discard=true if you "
                f"are deliberately throwing them away."
            )
        del self._documents[name]
        return f"{name!r} was closed."

    def discard(self, name: str) -> str:
        document = self._documents.pop(name, None)
        if document is None:
            raise OfficeError(f"{name!r} is not open")
        lost = document.ledger.unsaved_count
        return f"{name!r} was closed without saving ({lost} changes discarded)."

    def names(self) -> list[str]:
        return sorted(self._documents)

    def dirty_names(self) -> list[str]:
        return sorted(n for n, d in self._documents.items() if d.ledger.dirty)
