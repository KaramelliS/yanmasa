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
                f"{ad} görsel döndürür, yetenek içinden çağrılamaz — "
                f"ekran görüntüsünü ajanın kendisi almalı"
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
