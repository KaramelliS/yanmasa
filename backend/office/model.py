"""Belge modeli ve gerekçe defteri.

Bu ofisin diğerlerinden farkı burada başlıyor: ajanın yaptığı **her**
değişiklik neden yapıldığını taşıyor. Bir hücreye 12.000 yazıldıysa, o
değerin nereden geldiği kayıtlı.

Gerekçe isteğe bağlı bir alan değil, `apply` çağrısının zorunlu parametresi.
İsteğe bağlı olsaydı model çoğu zaman atlardı ve defter yarı boş kalırdı;
yarı dolu bir gerekçe defteri, hiç olmamasından kötüdür çünkü güvenilir
sanılır.

Defter aynı zamanda geri almanın temeli: her kayıt önceki değeri de
tutuyor, yani "son üç değişikliği geri al" veri kaybı olmadan mümkün.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Change:
    """Tek bir değişiklik: nerede, ne, neden."""

    target: str          # "Sayfa1!B5" ya da "paragraf 3"
    before: Any
    after: Any
    why: str
    at: datetime
    author: str = "ajan"

    def describe(self) -> str:
        before = "(boş)" if self.before in (None, "") else repr(self.before)
        after = "(boş)" if self.after in (None, "") else repr(self.after)
        return f"{self.at:%H:%M:%S} {self.target}: {before} -> {after}  — {self.why}"


class Ledger:
    """Değişiklik defteri. Kaydedilmemiş değişiklikleri de tutar."""

    def __init__(self) -> None:
        self._changes: list[Change] = []
        self._saved_at: int = 0

    def record(self, target: str, before: Any, after: Any, why: str,
               author: str = "ajan") -> Change:
        if not why or not why.strip():
            raise ValueError(
                f"{target} değiştiriliyor ama gerekçe yok. Her değişiklik "
                f"neden yapıldığını taşımak zorunda."
            )
        change = Change(
            target=target, before=before, after=after,
            why=why.strip(), at=datetime.now(), author=author,
        )
        self._changes.append(change)
        return change

    def mark_saved(self) -> None:
        self._saved_at = len(self._changes)

    @property
    def dirty(self) -> bool:
        return len(self._changes) > self._saved_at

    @property
    def unsaved_count(self) -> int:
        return len(self._changes) - self._saved_at

    def __len__(self) -> int:
        return len(self._changes)

    def recent(self, limit: int = 30) -> list[Change]:
        return self._changes[-limit:]

    def last(self, count: int = 1) -> list[Change]:
        """Geri alma için en son değişiklikler, yeniden eskiye."""
        return list(reversed(self._changes[-count:]))

    def drop_last(self, count: int) -> None:
        """Geri alınan kayıtları defterden düşürür."""
        if count <= 0:
            return
        del self._changes[-count:]
        self._saved_at = min(self._saved_at, len(self._changes))

    def report(self, limit: int = 30) -> str:
        if not self._changes:
            return "Henüz değişiklik yok."
        lines = [c.describe() for c in self.recent(limit)]
        header = f"{len(self._changes)} değişiklik"
        if self.dirty:
            header += f", {self.unsaved_count} tanesi kaydedilmemiş"
        if len(self._changes) > limit:
            lines.insert(0, f"(son {limit} tanesi)")
        return f"{header}\n" + "\n".join(lines)


@dataclass
class OfficeDocument:
    """Açık bir belgenin ortak yüzü. Tablo ve yazı bunu paylaşıyor."""

    path: str
    ledger: Ledger = field(default_factory=Ledger)

    @property
    def kind(self) -> str:
        raise NotImplementedError

    def summary(self) -> str:
        raise NotImplementedError

    def save(self, path: str | None = None) -> str:
        raise NotImplementedError

    def undo(self, count: int = 1) -> str:
        raise NotImplementedError
