"""Yeteneğin elindeki ortam.

`calistir(girdi, ortam)` ikinci parametresi bu. Ajanın kendi araçlarını
yeteneğin içinden çağırmayı sağlıyor: bir yetenek "Not Defteri'ni aç, şunu
yaz, kaydet" dizisini tek çağrıya indirebiliyor.

En önemli tarafı `arac()`: yerleşik araçlar buradan çağrıldığında **güvenlik
kapısı yine devrede**. Yeteneğin `run_shell` çağırması ile ajanın doğrudan
çağırması arasında fark yok; riskli komut yine Berkay'a soruluyor. Aksi
hâlde yetenek yazmak kapıyı atlamanın en kolay yolu olurdu.

Bu bir kum havuzu değil. Yetenek düz Python; `import os` yazıp kapıyı
tamamen dolaşabilir. Ortam kolaylık sağlıyor, hapsetmiyor — asıl koruma
yeteneğin yazılırken onaylanması ve kodunun okunması.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class Ortam:
    """Yeteneğe verilen yardımcılar."""

    def __init__(self, dispatcher: Any) -> None:
        self._dispatcher = dispatcher

    # --- ajanın araçları --------------------------------------------------

    def arac(self, ad: str, **girdi: Any) -> str:
        """Yerleşik bir aracı çağırır: `ortam.arac("launch_app", name="notepad")`.

        Sonucu metin olarak döndürür. Ekran görüntüsü döndüren araçlar
        (`screenshot`, `zoom`) buradan çağrılamaz; görsel modele gider,
        yeteneğin işine yaramaz.
        """
        from ..agent.dispatch import VISUAL_MEMBERS

        if ad in VISUAL_MEMBERS:
            raise RuntimeError(
                f"{ad} returns an image and cannot be called from a skill — "
                f"the agent itself has to take the screenshot"
            )
        outcome = self._dispatcher.run(ad, dict(girdi))
        content = outcome.content
        return content if isinstance(content, str) else str(content)

    def kabuk(self, komut: str) -> str:
        """Kabuk komutu. Riskliyse Berkay'a sorulur."""
        return self.arac("run_shell", command=komut)

    def oku(self, yol: str) -> str:
        return self.arac("read_file", path=yol)

    def yaz(self, yol: str, icerik: str) -> str:
        return self.arac("write_file", path=yol, content=icerik)

    def on_pencere(self) -> str:
        """Şu an ön planda olan pencerenin başlığı.

        Tuş gönderen her yetenek buna bakmalı: yanlış pencereye giden bir
        tuş dizisi başkasının sohbetine yazmak demek. Bu projede bir kez
        oldu — test metni bir sohbet penceresine düştü ve Enter onu
        gönderdi.
        """
        from ..computer import windows as win

        return win.foreground_title()

    def pencereye_gec(self, baslik_parcasi: str, timeout: float = 3.0) -> bool:
        """Başlığında bu metin geçen pencereyi öne getirir.

        Getiremezse `False` döndürüyor, varsaymıyor: Windows
        `SetForegroundWindow` çağrısını sessizce yok sayabiliyor ve
        "geçtim" varsaymak tuşların başka bir uygulamaya gitmesi demek.
        """
        from ..computer import windows as win

        return win.activate(baslik_parcasi, timeout)

    def pencerenin_ekrani(self, baslik_parcasi: str) -> int | None:
        """Pencerenin bulunduğu ekranın indeksi. Pencere yoksa `None`.

        Ekran görüntüsü almadan önce buna geçmek gerekiyor: ajan yanlış
        monitöre bakarsa pencereyi hiç göremiyor ve olmayan bir şeyi
        aramaya başlıyor.
        """
        from ..computer import windows as win

        rect = win.window_rect(baslik_parcasi)
        if rect is None:
            return None
        return self._dispatcher.displays.locate_rect(*rect).index

    def onay(self, baslik: str, ayrinti: str, sebep: str) -> bool:
        """Yeteneğin kendi riskli adımı için Berkay'a sorar.

        Yetenek sözleşmesindeki `"onay": True` bütün yeteneği kapsıyor ve
        çoğu zaman fazla geniş: Discord yeteneğinin gezinmesi zararsız ama
        mesaj **göndermesi** geri alınamaz. Bu çağrı yeteneğin yalnızca o
        adımı sormasını sağlıyor.

        Kapıyı yeteneğin kendisi kuramaz; bu çağrı arayüzün onay yoluna
        gidiyor, yani reddedildiğinde gerçekten durdurulabiliyor.
        """
        return bool(self._dispatcher.approve(baslik, ayrinti[:1500], sebep))

    def bekle(self, saniye: float) -> None:
        """Acil durdurmayı dinleyen bekleme. `time.sleep` Esc×3'ü sağır
        bırakıyor; uzun bekleyen bir yetenek durdurulamaz oluyor."""
        from ..agent.dispatch import _interruptible_sleep

        _interruptible_sleep(max(0.0, min(float(saniye), 60.0)),
                             self._dispatcher.kill)

    # --- yeteneğin kendi alanı --------------------------------------------

    @property
    def klasor(self) -> Path:
        """Yeteneklerin kendi verilerini koyabileceği yer.

        Kullanıcının Belgeler klasörüne dosya saçmasınlar diye ayrı.
        """
        from .registry import SKILL_DIR

        target = SKILL_DIR / "veri"
        target.mkdir(parents=True, exist_ok=True)
        return target
