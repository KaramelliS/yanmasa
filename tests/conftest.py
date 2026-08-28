"""Qt gerektiren testler için tek bir uygulama nesnesi ve temizlik.

`QApplication` süreç başına bir tane olabiliyor ve widget kuran her test
birini istiyor. Test başına kurup yıkmak Qt'yi çökertiyor; oturum boyunca
bir tane yaşıyor.

## Testler kendi çöpünü topluyor

Widget kuran testler onları hiç yok etmiyordu ve süreçte onlarca
`CommandBar` birikiyordu. Hepsi hâlâ animasyon saatine abone ve saat
aralarında hepsini tıklatıyor; bir noktada Qt süreci abort ediyordu.
Ölçtüm: çökme tek başına hiçbir testte olmuyor, 129. testten sonra
birikenlerle ortaya çıkıyor — yani sıraya bağlı, gizlenmesi kolay bir
kusur.

Uygulamada tek bir çubuk var ve hiç yok edilmiyor, yani bu bir test
hijyeni sorunu. Ama gizlenmemesi gerekiyor: sıraya bağlı bir çökme bir
gün gerçek bir hatayı maskeler.
"""

import gc

import pytest


@pytest.fixture(scope="session")
def qt_app():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _qt_temizlik():
    """Her testten sonra sahipsiz pencereleri ve saati boşaltır.

    Sıra önemli: önce pencereler kapatılıp silinir, sonra saat
    boşaltılır. Tersi olsaydı kapatma sırasında tetiklenen `hideEvent`
    aboneliği geri ekleyebilirdi.
    """
    yield
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:  # Qt kurulu değil — saf mantık testleri
        return
    app = QApplication.instance()
    if app is None:
        return
    silinen = 0
    for w in list(app.topLevelWidgets()):
        try:
            w.close()
            w.deleteLater()
            silinen += 1
        except RuntimeError:
            # C++ tarafı zaten silinmiş.
            pass
    if silinen:
        # `gc.collect()` her testte çağrılıyordu ve Qt yığını büyüdükçe
        # test başına 0.3–0.4 saniye tutuyordu: 370 testte iki dakikadan
        # fazla, tamamı hiç widget kurmayan testlerde de ödeniyordu.
        # Ölçtüm — süre 342 saniyeden 48'e indi.
        app.processEvents()
        gc.collect()

    from app.motion import clock

    saat = clock()
    saat._aboneler.clear()
    saat._timer.stop()
