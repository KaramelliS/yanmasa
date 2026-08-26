"""Arayüz geliştirirken kullanılan içerik.

Uydurma değil: bu satırlar ajanın gerçekten ürettiği dosyalardan alındı
(`~/Desktop/ajan_ofis/butce.xlsx`, `ozet.docx`, `~/Desktop/ajan_demo/`).
Ajan döngüsü arayüze bağlandığında bu modül düşecek; o zamana kadar
arayüz gerçek biçim ve gerçek uzunluklarla ölçülüyor.
"""

from __future__ import annotations

from .panels import Correction, Para
from .sheet_view import Cell

SHEET_COLUMNS = ["A", "B"]

SHEET_ROWS: list[list[Cell]] = [
    [Cell("Kalem"), Cell("Tutar")],
    [Cell("Kira"), Cell("12000", why="Ocak kira faturasından")],
    [Cell("Elektrik"), Cell("1850", why="Ocak elektrik faturasından")],
    [Cell("Internet"), Cell("640", why="Aylık sabit abonelik")],
    [Cell("Market"), Cell("4200", why="Kart ekstresi toplamı")],
    [
        Cell("Toplam"),
        Cell("=SUM(B2:B5)", formula=True, why="B2:B5 aralığının toplamı"),
    ],
]

DOC_PARAGRAPHS = [
    Para("Ağustos Gider Özeti", "Title", why="Belgenin başlığı"),
    Para(
        "Ağustos ayında toplam gider 18.690 TL oldu. En büyük kalem 12.000 TL "
        "ile kira; bunu 4.200 TL ile market harcamaları izliyor. Elektrik ve "
        "internet birlikte toplamın yüzde on üçünü buluyor.",
        "Normal",
        why="Tablodaki dört kalemin yorumu",
    ),
    Para("Kalemler", "Heading 1"),
    Para(
        "Aşağıdaki tablo aynı verinin belge içindeki kopyasıdır. Word "
        "tablosunda formül işlemediği için toplam elle hesaplandı; Excel'de "
        "açtığında bu sayıyla eşleştiğini doğrula.",
        "Normal",
        why="Formül hesaplanamadığı için uyarı eklendi",
    ),
]

CODE_LINES = [
    '"""Ilk N Fibonacci sayisini ureten kucuk bir modul ve CLI."""',
    "",
    "import argparse",
    "from typing import List",
    "",
    "",
    "def fibonacci(n: int) -> List[int]:",
    '    """Ilk n Fibonacci sayisini bir liste olarak dondurur."""',
    "    if n < 0:",
    '        raise ValueError("n negatif olamaz")',
    "",
    "    result: List[int] = []",
    "    a, b = 0, 1",
    "    for _ in range(n):",
    "        result.append(a)",
    "        a, b = b, a + b",
    "    return result",
]

#: Ajanın bu koşuda dokunduğu satırlar. Her satırı işaretlemek işaretlemeyi
#: anlamsız kılar — her şey vurguluysa hiçbir şey vurgulu değildir.
CODE_TOUCHED = {8, 9, 12, 13, 14, 15}

TERMINAL_SCREEN = """PS C:\\Users\\berkaycik\\Desktop\\ajan_demo> python -m pytest -v
========================= test session starts =========================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
collected 8 items

test_fibonacci.py::test_sifir_eleman PASSED                     [ 12%]
test_fibonacci.py::test_tek_eleman PASSED                       [ 25%]
test_fibonacci.py::test_ilk_bes PASSED                          [ 37%]
test_fibonacci.py::test_ilk_on PASSED                           [ 50%]
test_fibonacci.py::test_negatif_hata PASSED                     [ 62%]
test_fibonacci.py::test_buyuk_n PASSED                          [ 75%]
test_fibonacci.py::test_cli_varsayilan PASSED                   [ 87%]
test_fibonacci.py::test_cli_ayirici PASSED                      [100%]

========================== 8 passed in 0.13s ==========================
PS C:\\Users\\berkaycik\\Desktop\\ajan_demo>"""

CORRECTIONS = [
    Correction(
        target="butce.xlsx · Sayfa1!B2",
        before=None,
        after="12000",
        why="Ocak kira faturasından alındı",
        at="14:41:08",
        saved=True,
    ),
    Correction(
        target="butce.xlsx · Sayfa1!B6",
        before=None,
        after="=SUM(B2:B5)",
        why="Dört kalemin toplamı; değeri hesaplanmadı, Excel'de açılınca hesaplanacak",
        at="14:41:09",
        saved=True,
    ),
    Correction(
        target="ozet.docx · paragraf 1",
        before="Ağustos ayında toplam gider hesaplanacak.",
        after="Ağustos ayında toplam gider 18.690 TL oldu…",
        why="Toplam elle hesaplandı (12000+1850+640+4200); Word tablosunda formül işlemiyor",
        at="14:42:31",
        saved=False,
    ),
]
