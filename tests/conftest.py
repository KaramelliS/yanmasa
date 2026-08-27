"""Qt gerektiren testler için tek bir uygulama nesnesi.

`QApplication` süreç başına bir tane olabiliyor ve widget kuran her test
birini istiyor. Test başına kurup yıkmak Qt'yi çökertiyor; oturum boyunca
bir tane yaşıyor.
"""

import pytest


@pytest.fixture(scope="session")
def qt_app():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
