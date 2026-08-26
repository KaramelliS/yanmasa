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
                f"{name!r} adıyla açık bir belge zaten var. Başka bir ad ver ya "
                f"da önce kapat."
            )
        if len(self._documents) >= self.MAX_OPEN:
            raise OfficeError(
                f"En fazla {self.MAX_OPEN} belge açık olabilir. Birini kapat."
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
                    f"{suffix or '(uzantısız)'} desteklenmiyor. "
                    f"Tablo için .xlsx, yazı için .docx kullan."
                )
        except (SheetError, TextError) as exc:
            raise OfficeError(str(exc)) from None

        self._documents[name] = document
        return document

    def get(self, name: str) -> OfficeDocument:
        document = self._documents.get(name)
        if document is None:
            known = ", ".join(sorted(self._documents)) or "yok"
            raise OfficeError(f"{name!r} açık değil. Açık belgeler: {known}")
        return document

    def close(self, name: str) -> str:
        document = self._documents.get(name)
        if document is None:
            raise OfficeError(f"{name!r} açık değil")
        if document.ledger.dirty:
            # Sessizce kapatmak, ajanın kaydettiğini sanmasına yol açar.
            raise OfficeError(
                f"{name!r} belgesinde {document.ledger.unsaved_count} "
                f"kaydedilmemiş değişiklik var. Önce kaydet ya da bilerek "
                f"atıyorsan discard=true ver."
            )
        del self._documents[name]
        return f"{name!r} kapatıldı."

    def discard(self, name: str) -> str:
        document = self._documents.pop(name, None)
        if document is None:
            raise OfficeError(f"{name!r} açık değil")
        lost = document.ledger.unsaved_count
        return f"{name!r} kaydedilmeden kapatıldı ({lost} değişiklik atıldı)."

    def names(self) -> list[str]:
        return sorted(self._documents)

    def dirty_names(self) -> list[str]:
        return sorted(n for n, d in self._documents.items() if d.ledger.dirty)
