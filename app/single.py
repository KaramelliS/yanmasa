"""Tek örnek koruması.

Uygulama iki kez açıldığında iki ajan penceresi ve iki komut çubuğu oluyor.
Bu yalnızca dağınık değil, tehlikeli: iki ajan aynı fareyi ve klavyeyi
sürüyor, birinin tıklaması diğerinin ekran görüntüsünü geçersizleştiriyor
ve Esc×3 acil durdurma yalnızca birini kesiyor.

Kilit `QLocalServer` ile: ilk örnek adlandırılmış bir yuva açıyor, ikincisi
o yuvaya bağlanabiliyorsa zaten bir örnek var demektir. İkinci örnek sessizce
kapanmıyor — çift tıklayan kişi bir şey olmasını bekliyor, o yüzden var olan
pencereyi öne getirmesini söyleyip çıkıyor.

Windows'ta süreç çökerse yuva ortada kalabiliyor; `removeServer` bu ölü
kilidi temizliyor. Aksi hâlde bir çökmeden sonra uygulama bir daha hiç
açılmazdı.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

#: Kullanıcıya özel: aynı makinede başka bir hesap kendi örneğini açabilmeli.
SOCKET = "ajan-tek-ornek"

#: Var olan örneğe "kendini göster" demek için gönderilen işaret.
WAKE = b"uyan\n"


class InstanceGuard(QObject):
    """İkinci bir örnek başlatıldığında yayılır."""

    woken = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._server: QLocalServer | None = None

    def claim(self, timeout_ms: int = 400) -> bool:
        """İlk örnek isek `True`. Değilsek var olanı uyandırıp `False`."""
        probe = QLocalSocket()
        probe.connectToServer(SOCKET)
        if probe.waitForConnected(timeout_ms):
            probe.write(WAKE)
            probe.waitForBytesWritten(timeout_ms)
            probe.disconnectFromServer()
            return False

        # Bağlanamadık: ya gerçekten ilk örneğiz ya da önceki örnek çöküp
        # yuvayı ardında bırakmış. İkisi de aynı davranışı gerektiriyor.
        QLocalServer.removeServer(SOCKET)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)
        self._server.listen(SOCKET)
        return True

    def release(self) -> None:
        if self._server is not None:
            self._server.close()
            QLocalServer.removeServer(SOCKET)

    def _on_connection(self) -> None:
        connection = self._server.nextPendingConnection()
        if connection is None:
            return
        connection.disconnected.connect(connection.deleteLater)
        self.woken.emit()
