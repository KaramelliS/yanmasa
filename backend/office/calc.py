"""Formül hesaplama.

Bu modül bir hata yüzünden var. Ajan bir bütçe tablosuna toplam formülü
yazdı, sonra kullanıcıya sonucun 21.290 olacağını söyledi. Doğrusu 20.990.
Dosya doğruydu; yanlış olan, ajanın formülün sonucunu kafadan toplaması.

`openpyxl` formülü metin olarak saklar, hesaplamaz — ve Excel kurulu
olmadığı için dosyayı açıp değeri okuyacak kimse yok. `formulas` paketi
formül grafiğini kurup çözüyor; ajan artık kendi aritmetiğine değil bu
sonuca bakıyor.

Hesaplama pahalı (grafiği kurmak saniyeler sürüyor), bu yüzden defterdeki
değişiklik sayısına göre önbelleğe alınıyor: tablo değişmediyse yeniden
hesaplanmıyor.
"""

from __future__ import annotations

import contextlib
import io
import logging
import re
import tempfile
import warnings
from pathlib import Path
from typing import Any

#: `'[dosya.xlsx]SAYFA1'!B6` — motorun döndürdüğü anahtar biçimi.
_KEY = re.compile(r"^'\[[^\]]+\]([^']+)'!([A-Z]+\d+)$")


class CalcError(RuntimeError):
    pass


def _load():
    # `formulas` içe aktarılırken ve çalışırken bol uyarı basıyor; bunlar
    # ajanın çıktısına karışıyor.
    warnings.filterwarnings("ignore")
    logging.getLogger("formulas").setLevel(logging.CRITICAL)
    logging.getLogger("schedula").setLevel(logging.CRITICAL)
    import formulas

    return formulas


def _scalar(value: Any) -> str:
    """Motorun `Ranges` nesnesinden tek bir hücre değeri çıkarır."""
    raw = getattr(value, "value", value)
    while hasattr(raw, "__len__") and not isinstance(raw, str) and len(raw):
        raw = raw[0]
    if raw is None:
        return ""
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    return str(raw)


def evaluate(book, sheet_names: list[str]) -> dict[str, str]:
    """`{"Sayfa1!B6": "20990"}`. Hesaplanamayan hücre sözlükte yok."""
    formulas_mod = _load()

    # Motor dosya istiyor; çalışma kitabı bellekte olduğu için geçici bir
    # kopya yazılıyor. Kullanıcının dosyasına dokunulmuyor.
    target = Path(tempfile.gettempdir()) / "ajan_hesap.xlsx"
    try:
        book.save(target)
        # Motor stderr'e ilerleme çubuğu basıyor; ajanın kendi çıktısıyla
        # karışıyor. Gerçek hatalar zaten istisna olarak geliyor.
        with contextlib.redirect_stderr(io.StringIO()):
            model = formulas_mod.ExcelModel().loads(str(target)).finish()
            solution = model.calculate()
    except Exception as exc:
        raise CalcError(str(exc)) from None
    finally:
        target.unlink(missing_ok=True)

    # Motor sayfa adını büyük harfe çeviriyor; gerçek adlara geri eşleniyor.
    by_upper = {name.upper(): name for name in sheet_names}
    out: dict[str, str] = {}
    for key, value in solution.items():
        match = _KEY.match(str(key))
        if not match:
            continue
        sheet, ref = match.groups()
        out[f"{by_upper.get(sheet, sheet)}!{ref}"] = _scalar(value)
    return out
