"""Ajan — Windows masaüstü uygulaması.

    .venv/Scripts/pythonw.exe ajan.py

Yerel bir Qt uygulaması: web katmanı, tarayıcı motoru ve HTTP köprüsü yok.
Görsel dil Windows 11 Fluent; renkler ve tema sistemden okunuyor.

Ajanla konuşulan yer ana pencere değil, ekranın köşesinde yüzen komut
çubuğu: mikrofon, yazı alanı ve yapılan işin önizleme karesi bir arada.
Ana pencere belgeleri tutuyor.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app import fluent
from app.agent_bridge import AgentBridge
from app.commandbar import CommandBar, Operation
from app.single import InstanceGuard
from app.window import MainWindow

#: Önizleme karesinde hedef olarak gösterilecek alan, araç bazında.
TARGET_KEYS = ("path", "name", "target", "ref", "command", "text", "coordinate")

TOOL_LABEL = {
    "screenshot": "Ekrana bakıyor",
    "zoom": "Yakınlaştırıyor",
    "left_click": "Tıklıyor",
    "double_click": "Çift tıklıyor",
    "type": "Yazıyor",
    "key": "Tuş basıyor",
    "scroll": "Kaydırıyor",
    "read_ui_tree": "Pencereyi okuyor",
    "launch_app": "Uygulama açıyor",
    "run_shell": "Komut çalıştırıyor",
    "write_file": "Dosya yazıyor",
    "read_file": "Dosya okuyor",
    "edit_file": "Dosya düzenliyor",
    "list_dir": "Klasöre bakıyor",
    "terminal_open": "Terminal açıyor",
    "terminal_send": "Terminale yazıyor",
    "terminal_read": "Terminali okuyor",
    "office_open": "Belge açıyor",
    "office_read": "Belgeyi okuyor",
    "office_edit": "Belgeyi düzenliyor",
    "office_save": "Belgeyi kaydediyor",
    "office_history": "Değişikliklere bakıyor",
}


def _describe(tool: str, payload: dict) -> Operation:
    """Araç çağrısını önizleme karesinin anlayacağı hâle getirir."""
    target = ""
    for key in TARGET_KEYS:
        if payload.get(key) is not None:
            target = str(payload[key])
            break
    if len(target) > 46:
        target = target[:43] + "…"

    # `why` zorunlu bir alan olduğu için ofis işlerinde gerekçe hazır;
    # diğerlerinde araç çağrısının kendisi anlatıyor.
    detail = str(payload.get("why") or payload.get("text") or payload.get("command") or "")
    if len(detail) > 140:
        detail = detail[:137] + "…"

    return Operation(
        tool=TOOL_LABEL.get(tool, tool),
        target=target,
        detail=detail or tool,
        key=tool,
    )


def _panel_for(shot, tokens):
    """Anlık görüntüden panel içeriği üretir."""
    if shot.kind == "tablo":
        from app.sheet_view import Cell, SheetView

        rows = [
            [Cell(value=v, formula=f, why=w, result=r) for v, f, w, r in row]
            for row in shot.rows
        ]
        return SheetView(rows, tokens, shot.sheets or ["Sayfa1"], shot.path)

    from app.panels import DocPanel, Para

    return DocPanel([
        Para(text=text, style=style, why=why)
        for text, style, why in shot.paragraphs
    ])


def main() -> int:
    # Süreç DPI farkındalığına alınmalı: ajan aynı süreçten ekran yakalayıp
    # koordinat hesaplıyor ve Qt'nin ölçeklemesi araya girerse tıklama
    # yanlış piksele gider.
    from backend.computer.displays import set_dpi_awareness

    set_dpi_awareness()

    app = QApplication(sys.argv)
    app.setApplicationName("Ajan")
    # Fusion, Windows stilinin yok saydığı QSS kurallarını uyguluyor.
    app.setStyle("Fusion")
    tokens = fluent.apply(app)

    # İki ajan aynı fareyi süremez: ikinci örnek açılmıyor, var olanı
    # öne getiriyor.
    guard = InstanceGuard()
    if not guard.claim():
        return 0
    app.aboutToQuit.connect(guard.release)

    window = MainWindow(tokens)
    window.show()

    bar = CommandBar(tokens)
    window.attach_bar(bar)
    # Ses motoru henüz bağlı değil ve bu gizlenmiyor: mikrofon sönük durur,
    # yazı alanı tek çalışan giriş yolu olarak öne çıkar.
    bar.set_voice_available(False)
    bar.show()

    def on_woken() -> None:
        """Biri uygulamayı tekrar açmaya çalıştı."""
        window.showNormal()
        window.raise_()
        window.activateWindow()
        bar.show()
        bar.raise_()
        bar.set_status("Ajan zaten açık.")

    guard.woken.connect(on_woken)

    bridge = AgentBridge()

    def on_ready(ok: bool, why: str) -> None:
        if ok:
            bar.attach_buttons(bridge.button_store(), bridge.commands)
            bar.set_status("Yazıp Enter'a bas.")
        else:
            bar.set_status(f"Ajan kurulamadı: {why}")
            bar.field.setEnabled(False)

    def on_submit(text: str) -> None:
        # `/ad` bir komutsa hazır talimata açılıyor. Eşleşme yoksa metin
        # olduğu gibi gidiyor: eğik çizgiyle başlayan bir yol yazmak
        # engellenmemeli.
        expanded = bridge.expand_command(text)
        window.activity.add_step("Sen", "", text, "__sen__")
        bar.say("")
        bar.show_operation(None)
        bar.set_busy(True)
        bar.set_status("Çalışıyor…")
        window.run_instruction(text)
        bridge.run(expanded or text)

    steps = {"n": 0}
    unsaved: dict[str, int] = {}

    def open_remote(session, title_suffix: str = "") -> None:
        """Sunucu panelini açar ya da öne getirir."""
        from app.remote_view import RemoteView

        view = RemoteView(tokens, session)
        view.show_path(session.cwd)
        window.open_panel("__uzak__", f"{session.host.label} · sunucu", view)

    def connect_remote() -> None:
        """Berkay 'Sunucu' düğmesine bastı."""
        from PySide6.QtWidgets import QDialog
        from app.remote_view import ConnectDialog
        from backend.remote.ssh import RemoteError, SshSession

        dialog = ConnectDialog(tokens, window)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        session = SshSession(dialog.result_host())
        bar.set_status(f"{session.host.label} bağlanıyor…")
        try:
            banner = session.connect()
        except RemoteError as exc:
            # Bağlanamamak sessizce geçilmiyor; sebebi olduğu gibi yazılıyor.
            bar.set_status(str(exc))
            window.status.set_line(str(exc))
            return
        bridge.adopt_remote(session)
        open_remote(session)
        bar.set_status("")
        window.status.set_line(f"Bağlandı: {banner}")

    window.connect_remote.clicked.connect(connect_remote)

    def on_document(shot) -> None:
        """Ajan bir belge açtığında ya da değiştirdiğinde panel belirir."""
        unsaved[shot.name] = shot.unsaved
        title = f"{shot.name} · {shot.kind}"
        if shot.unsaved:
            title += f"  ({shot.unsaved} kaydedilmemiş)"
        window.open_panel(shot.name, title, _panel_for(shot, tokens))
        window.set_counters(steps["n"], sum(unsaved.values()), 0)

    def on_action(tool: str, payload: dict) -> None:
        op = _describe(tool, payload)
        bar.show_operation(op)
        window.activity.add_step(op.tool, op.target, op.detail, tool)
        steps["n"] += 1
        window.set_counters(steps["n"], 0, 0)

    def on_result(tool: str, text: str, is_error: bool, png: bytes) -> None:
        # Ajan bir düğme kurduysa çubuk hemen göstersin; yeniden başlatmak
        # gerekmesin.
        if tool.startswith("button_") and not is_error:
            bar.buttons.reload()
            bar._grow()
        # Ajan bir sunucuya bağlandıysa ya da orada gezindiyse panel de
        # oraya gitsin: iki ayrı yerde durmaları kafa karıştırıyor.
        if tool in ("remote_connect", "remote_list") and not is_error:
            session = bridge.remote_session()
            if session is not None and session.connected:
                open_remote(session)
        if png:
            window.activity.frame_last(png)
        elif is_error:
            window.activity.annotate_last(text[:200], error=True)
        elif text and text != "OK":
            window.activity.annotate_last(text[:200])
        if is_error:
            bar.set_status(f"{tool}: {text[:120]}")

    def on_finished(text: str) -> None:
        bar.set_busy(False)
        bar.show_operation(None)
        bar.set_status("")
        bar.say(text or "Bitti.")
        window.set_phase("bitti")
        window.status.set_line(text[:120] if text else "Bitti.")

    def on_failed(why: str) -> None:
        bar.set_busy(False)
        bar.show_operation(None)
        bar.set_status("")
        bar.say(why)
        window.set_phase("durduruldu")

    def on_approval(request) -> None:
        bar.ask_approval(request.tool, request.detail, request.reason)
        window.set_phase("onay")

        def answer(approved: bool) -> None:
            request.approved = approved
            request.event.set()
            bar.clear_approval()
            window.set_phase("kosuyor")
            try:
                bar.approval.answered.disconnect(answer)
            except (RuntimeError, TypeError):
                pass

        bar.approval.answered.connect(answer)

    bridge.ready.connect(on_ready)
    bridge.acted.connect(on_action)
    bridge.result.connect(on_result)
    bridge.document.connect(on_document)
    bridge.finished.connect(on_finished)
    bridge.failed.connect(on_failed)
    bridge.approval.connect(on_approval)
    bar.submitted.connect(on_submit)
    bar.set_commands(bridge.commands)
    window.stop_requested.connect(bridge.stop)
    app.aboutToQuit.connect(bridge.shutdown)

    bridge.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
