"""Ajanın masası — canlı görüntünün saf mantığı.

Gerçek gizli masaüstü ve gerçek pencereler `scripts/masa_dogrula.py`
içinde ölçülüyor; burası ona ihtiyaç duymayan kısım: hataların yutulması,
çizim sırası, ölçek matematiği ve salt okunurluk sözü.

Testlerin ağırlığı **hata yutmada**. Bu döngü saniyede sekiz kez dönüyor
ve ajan tam o sırada masaüstünü kapatabiliyor; o yarışta kaybeden bir
karenin uygulamayı düşürmesi, canlı görüntünün var olmamasından kötü
olurdu.
"""

from __future__ import annotations

import io
import tokenize
from pathlib import Path

import pytest

from backend.computer.canli import MasaKaresi, masayi_oku


class _SahtePencere:
    def __init__(self, hwnd, en=200, boy=150, x=0, y=0, baslik="p"):
        self.hwnd, self.en, self.boy = hwnd, en, boy
        self.x, self.y, self.baslik, self.sinif = x, y, baslik, "S"


class _SahteKare:
    def __init__(self, gorsel):
        self.image = gorsel


class _SahteCalisma:
    """Gizli masaüstünün yerine geçen en küçük şey."""

    def __init__(self, pencereler, patlayan=(), liste_patlar=False):
        self._pencereler = pencereler
        self._patlayan = set(patlayan)
        self._liste_patlar = liste_patlar

    def pencereler(self):
        if self._liste_patlar:
            raise OSError("masaüstü kapandı")
        return list(self._pencereler)

    def yakala(self, hwnd, **_):
        if hwnd in self._patlayan:
            raise OSError("pencere gitti")
        from PIL import Image
        p = next(x for x in self._pencereler if x.hwnd == hwnd)
        return _SahteKare(Image.new("RGB", (p.en, p.boy), (10, 20, 30)))


@pytest.fixture()
def kutu(monkeypatch):
    """`istemci_kutusu` ve `pencere_bilgisi` gerçek HWND istiyor."""
    from backend.computer import canli

    monkeypatch.setattr(canli, "istemci_kutusu",
                        lambda hwnd: (0, 0, 200, 150))
    monkeypatch.setattr(
        canli, "pencere_bilgisi",
        lambda hwnd: _SahtePencere(hwnd, baslik=f"pencere-{hwnd}"),
    )


class TestOkuma:
    def test_calisma_yoksa_bos_kare(self):
        # Ajan kurulamamış olabilir; pencere yine açılıyor.
        kare = masayi_oku(None)
        assert kare.bos and kare.pencereler == []

    def test_liste_patlarsa_bos_kare(self):
        # `side_close` tam bu sırada çağrılmış olabilir.
        kare = masayi_oku(_SahteCalisma([], liste_patlar=True))
        assert kare.bos

    def test_bir_pencere_patlarsa_digerleri_kaliyor(self, kutu):
        calisma = _SahteCalisma(
            [_SahtePencere(1), _SahtePencere(2)], patlayan={1},
        )
        kare = masayi_oku(calisma)
        assert [p.hwnd for p in kare.pencereler] == [2]

    def test_cizim_sirasi_alttan_uste(self, kutu):
        # `EnumDesktopWindows` üstten alta veriyor; çizim ters sırada
        # olmalı, yoksa en üstteki pencere en alta çiziliyor.
        calisma = _SahteCalisma([_SahtePencere(1), _SahtePencere(2),
                                 _SahtePencere(3)])
        kare = masayi_oku(calisma)
        assert [p.hwnd for p in kare.pencereler] == [3, 2, 1]

    def test_ust_sinir_uygulaniyor(self, kutu):
        calisma = _SahteCalisma([_SahtePencere(i) for i in range(10)])
        assert len(masayi_oku(calisma, sinir=3).pencereler) == 3

    def test_ham_bayt_boyutu_tutuyor(self, kutu):
        calisma = _SahteCalisma([_SahtePencere(1)])
        p = masayi_oku(calisma).pencereler[0]
        assert len(p.ham) == p.en * p.boy * 3

    def test_imlec_ve_iz_geciyor(self, kutu):
        from backend.computer.mesaj import Girdi

        girdi = Girdi()
        girdi.imlec.tasi(400, 300)
        girdi.iz.append((390, 290))
        girdi.son_tik = True
        kare = masayi_oku(_SahteCalisma([_SahtePencere(1)]), girdi)
        assert kare.imlec == (400, 300)
        assert kare.iz == [(390, 290)]
        assert kare.tik


class TestPencere:
    def _p(self, qt_app, kare=None):
        from app.masa import MasaPenceresi

        w = MasaPenceresi(lambda: kare or MasaKaresi())
        w.resize(900, 600)
        if kare is not None:
            w._kare = kare
        return w

    def test_bos_masa_cizilebiliyor(self, qt_app):
        from PySide6.QtGui import QImage

        w = self._p(qt_app)
        gorsel = QImage(w.size(), QImage.Format.Format_ARGB32)
        w.render(gorsel)  # patlamamalı
        assert not w._akis._calis, "gösterilmeden yakalama başlamamalı"

    def test_kapali_masa_baska_sey_soyluyor(self, qt_app):
        # "Bağlantı koptu" ile "ajan henüz bir şey açmadı" çok farklı iki
        # durum ve boş bir duvar kâğıdı ikisini de aynı gösteriyordu.
        w = self._p(qt_app)
        assert not w._kapali
        w.masa_kapandi()
        assert w._kapali
        w.masa_acildi()
        assert not w._kapali

    def test_olcek_ortaliyor(self, qt_app):
        from PySide6.QtCore import QRect

        w = self._p(qt_app, MasaKaresi(alan=(1000, 1000)))
        olcek, ofset = w._olcek(QRect(0, 0, 400, 200))
        assert olcek == pytest.approx(0.2)
        # Kare alan geniş bir kutuya sığınca yanlarda eşit pay kalıyor.
        assert ofset.x() == pytest.approx(100.0)
        assert ofset.y() == pytest.approx(0.0)

    def test_duraklatma_akisi_durduruyor(self, qt_app):
        w = self._p(qt_app)
        assert not w._akis._duraklat
        w._duraklat = True
        w._akis.duraklat(True)
        assert w._akis._duraklat


class TestSaltOkunur:
    """Masa penceresi hiçbir şey göndermiyor — söz bu.

    Salt okunurluk bir niyet değil, bir sözleşme: bu pencere ajanın
    masaüstüne bir tek ileti gönderirse, bakan kişinin farkında olmadığı
    bir tıklama olur. Kaynağa bakarak doğrulanıyor, `mesaj.py`'nin
    fiziksel imleci hiç oynatmadığının aynı şekilde doğrulanması gibi.
    """

    YASAK = {"tikla", "kaydir", "tus", "yaz", "tasi",
             "PostMessage", "SendInput", "SendMessage"}

    def test_masa_penceresi_girdi_gondermiyor(self):
        # Ad **tam** eşleşiyor, alt dize olarak değil: ilk hâli alt dize
        # arıyordu ve `_duraklat_kutusu` içindeki "tus" yüzünden bağırdı.
        # Yanlış alarm veren bir güvenlik testi, bir süre sonra
        # susturuluyor ve o noktada hiç yok demektir.
        kaynak = (Path(__file__).resolve().parent.parent
                  / "app" / "masa.py").read_text(encoding="utf-8")
        adlar = {
            t.string
            for t in tokenize.generate_tokens(io.StringIO(kaynak).readline)
            if t.type == tokenize.NAME
        }
        assert sorted(adlar & self.YASAK) == []

    def test_okuyucu_girdiyi_degistirmiyor(self, kutu):
        from backend.computer.mesaj import Girdi

        girdi = Girdi()
        girdi.imlec.tasi(11, 22)
        masayi_oku(_SahteCalisma([_SahtePencere(1)]), girdi)
        assert (girdi.imlec.x, girdi.imlec.y) == (11, 22)
        assert list(girdi.iz) == []
