"""Renders the README hero shot offscreen.

Deliberately **not** a screen capture. Grabbing the real screen would put
whatever happens to be open behind the window into a public image, and it
has: an earlier capture in this project caught private messages. Here the
widgets are constructed and rendered into a `QImage` — nothing outside the
app can leak into the file.

The sample content lives in this file rather than in `app/`. It used to sit
in `app/fixtures.py`, which nothing imported: a module kept alive only by
the README mentioning it. Content that exists for a screenshot belongs to
the script that takes the screenshot.

    .venv/Scripts/python.exe scripts/tanitim.py

Writes `varliklar/onizleme/hero.png`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import fluent  # noqa: E402
from app.commandbar import CommandBar  # noqa: E402
from app.panels import Correction, Para, TashihMargin  # noqa: E402
from app.panels import DocPanel  # noqa: E402
from app.sheet_view import Cell, SheetView  # noqa: E402
from app.window import MainWindow  # noqa: E402

#: The run the hero shot shows. Not invented: the agent really did this
#: (`~/Desktop/ajan_ofis/`), in Turkish; the strings are translated.
TALIMAT = "Read the CSVs on my desktop into a sheet and summarise August"

SATIRLAR = [
    [Cell("Item"), Cell("Amount")],
    [Cell("Rent"), Cell("12000", why="From the January rent invoice")],
    [Cell("Electricity"), Cell("1850", why="From the January power bill")],
    [Cell("Internet"), Cell("640", why="Fixed monthly subscription")],
    [Cell("Groceries"), Cell("4200", why="Card statement total")],
    [Cell("Total"), Cell("=SUM(B2:B5)", formula=True,
                         why="Sum of the range B2:B5")],
]

PARAGRAFLAR = [
    Para("August Expense Summary", "Title", why="Title of the document"),
    Para(
        "August spending came to 18,690 TL. The largest item is rent at "
        "12,000 TL, followed by groceries at 4,200 TL. Electricity and "
        "internet together account for thirteen percent of the total.",
        "Normal",
        why="Reading of the four items in the sheet",
    ),
]

DUZELTMELER = [
    Correction(
        target="budget.xlsx · Sheet1!B6",
        before=None,
        after="=SUM(B2:B5)",
        why="Sum of the four items; the sheet app will evaluate it",
        at="14:41:09",
        saved=True,
    ),
    Correction(
        target="summary.docx · paragraph 1",
        before="August spending will be calculated.",
        after="August spending came to 18,690 TL…",
        why="Total computed by hand; Word tables do not evaluate formulas",
        at="14:42:31",
        saved=False,
    ),
]

ADIMLAR = [
    ("list_dir", "Listing a folder", "Desktop",
     "4 files, 4 of them .csv"),
    ("read_file", "Reading a file", "august.csv",
     "Rent;12000 / Electricity;1850 / Internet;640 / Groceries;4200"),
    ("office_open", "Opening a document", "budget.xlsx",
     "New workbook, sheet Sheet1"),
    ("office_edit", "Editing the document", "Sheet1!B6",
     "Sheet1!B6 = =SUM(B2:B5)"),
]


def _kur(t):
    pencere = MainWindow(t)
    pencere.resize(1500, 940)
    pencere.open_panel("sheet", "budget.xlsx",
                       SheetView(SATIRLAR, t, ["Sheet1"], "budget.xlsx"))
    pencere.open_panel("fix", "Corrections", TashihMargin(DUZELTMELER))
    pencere.open_panel("doc", "summary.docx", DocPanel(PARAGRAFLAR))
    # Panels tabify by design; the hero shows that, with the sheet on top.
    pencere._panels["sheet"].raise_()
    # The activity view is the run's own record; leaving it on its empty
    # state while the status bar says "Working" would be a lie about the
    # app, not just a worse picture.
    pencere.activity.add_step("You", "", TALIMAT, "__sen__")
    for arac, etiket, hedef, sonuc in ADIMLAR:
        pencere.activity.add_step(etiket, hedef, "", arac)
        pencere.activity.annotate_last(sonuc, tool=arac)
    pencere.set_counters(len(ADIMLAR), 1, 0)
    pencere.set_phase("kosuyor")
    pencere.status.set_line(TALIMAT)

    cubuk = CommandBar(t)
    cubuk.set_voice_available(False)
    cubuk.show()
    cubuk.clear_run()
    cubuk.add_user(TALIMAT)
    cubuk.set_busy(True)
    cubuk.stream("Four CSVs on the desktop. Reading them into one sheet.")
    for arac, etiket, hedef, _ in ADIMLAR:
        cubuk.ring.step(arac)
        cubuk.set_tool(etiket, hedef)
        cubuk.add_step(arac, etiket, hedef)
    cubuk.settle_step(False)
    # The bubble types at 42 chars/sec; the hero wants it mid-sentence, not
    # finished. A finished line says "was", a typing line says "is".
    for _ in range(52):
        cubuk.baloncuk._tick(1 / 60)
        cubuk.ring._tick(1 / 60)
    cubuk._fit_reply()
    return pencere, cubuk


def main() -> int:
    app = QApplication(sys.argv)
    t = fluent.apply(app)
    pencere, cubuk = _kur(t)
    pencere.show()
    app.processEvents()

    pay = 40
    en, boy = pencere.width() + pay * 2, pencere.height() + pay * 2
    kare = QImage(en, boy, QImage.Format_ARGB32)
    kare.fill(QColor(t.background))

    p = QPainter(kare)
    pencere.render(p, QPoint(pay, pay))
    p.end()

    # The bar floats over the corner in the real app; the hero shows the
    # same relationship instead of two disconnected pictures.
    bar_kare = QImage(cubuk.size(), QImage.Format_ARGB32)
    bar_kare.fill(QColor(t.background))
    cubuk.render(bar_kare)
    p = QPainter(kare)
    p.drawImage(en - cubuk.width() - pay - 24, boy - cubuk.height() - pay - 62,
                bar_kare)
    p.end()

    hedef = Path("varliklar/onizleme/hero.png")
    hedef.parent.mkdir(parents=True, exist_ok=True)
    kare.save(str(hedef))
    print(f"{hedef}  {kare.width()}x{kare.height()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
