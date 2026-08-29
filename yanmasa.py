"""Yan Masa — Windows masaüstü uygulaması.

    .venv/Scripts/pythonw.exe yanmasa.py

Yerel bir Qt uygulaması: web katmanı, tarayıcı motoru ve HTTP köprüsü yok.
Görsel dil Windows 11 Fluent; renkler ve tema sistemden okunuyor.

Ajanla konuşulan yer ana pencere değil, ekranın köşesinde yüzen komut
çubuğu: mikrofon, yazı alanı ve yapılan işin önizleme karesi bir arada.
Ana pencere belgeleri tutuyor.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app import fluent
from app.agent_bridge import AgentBridge
from app.commandbar import CommandBar, Operation
from app.single import InstanceGuard
from app.window import MainWindow

#: Önizleme karesinde hedef olarak gösterilecek alan, araç bazında.
TARGET_KEYS = ("path", "name", "target", "ref", "command", "text", "coordinate")

TOOL_LABEL = {
    "screenshot": "Looking at the screen",
    "zoom": "Zooming in",
    "left_click": "Clicking",
    "double_click": "Double-clicking",
    "type": "Typing",
    "key": "Pressing a key",
    "scroll": "Scrolling",
    "read_ui_tree": "Reading the window",
    "launch_app": "Launching an app",
    "run_shell": "Running a command",
    "write_file": "Writing a file",
    "read_file": "Reading a file",
    "edit_file": "Editing a file",
    "list_dir": "Listing a folder",
    "terminal_open": "Opening a terminal",
    "terminal_send": "Typing in the terminal",
    "terminal_read": "Reading the terminal",
    "office_open": "Opening a document",
    "office_read": "Reading the document",
    "office_edit": "Editing the document",
    "office_save": "Saving the document",
    "office_history": "Reviewing the changes",
    "office_close": "Closing the document",
    "cursor_position": "Locating the cursor",
    "right_click": "Right-clicking",
    "middle_click": "Middle-clicking",
    "triple_click": "Triple-clicking",
    "mouse_move": "Moving the cursor",
    "left_mouse_down": "Holding the button",
    "left_mouse_up": "Releasing",
    "left_click_drag": "Dragging",
    "hold_key": "Holding a key",
    "wait": "Waiting",
    "switch_display": "Switching display",
    "list_apps": "Listing apps",
    "write_files": "Writing files",
    "terminal_close": "Closing the terminal",
    "skill_list": "Listing skills",
    "skill_write": "Writing a skill",
    "skill_remove": "Removing a skill",
    "button_write": "Adding a button",
    "button_remove": "Removing a button",
    "remote_connect": "Connecting to the server",
    "remote_list": "Listing the server",
    "remote_read": "Reading from the server",
    "remote_write": "Writing to the server",
    "remote_run": "Running on the server",
    "side_launch": "Launching in the side desk",
    "side_windows": "Listing the side desk",
    "side_capture": "Looking at the side desk",
    "side_act": "Working in the side desk",
    "side_close": "Closing the side desk",
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

    # Detay boşsa boş kalıyor. Eskiden araç adına düşüyordu ve satır
    # "Bekliyor  wait" gibi kendini tekrar ediyordu; çizim zaten hangi
    # iş olduğunu söylüyor.
    return Operation(
        tool=TOOL_LABEL.get(tool, tool),
        target=target,
        detail=detail,
        key=tool,
    )


def _ortak_klasor(paths: list[str]) -> str:
    """Yazılan dosyaların ortak üst klasörü — kod ağacının kökü.

    Tek dosya yazıldıysa onun klasörü. Farklı sürücülere yazıldıysa
    (`commonpath` orada hata veriyor) ilk dosyanın klasörü.
    """
    klasorler = [str(Path(p).resolve().parent) for p in paths]
    if len(set(klasorler)) == 1:
        return klasorler[0]
    try:
        return os.path.commonpath(klasorler)
    except ValueError:
        return klasorler[0]


def _panel_for(shot, tokens):
    """Anlık görüntüden panel içeriği üretir."""
    if shot.kind == "sheet":
        from app.sheet_view import Cell, SheetView

        rows = [
            [Cell(value=v, formula=f, why=w, result=r) for v, f, w, r in row]
            for row in shot.rows
        ]
        return SheetView(rows, tokens, shot.sheets or ["Sheet1"], shot.path)

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
    app.setApplicationName("Yan Masa")
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
        bar.set_status("Yan Masa is already open.")

    guard.woken.connect(on_woken)

    bridge = AgentBridge()

    def on_ready(ok: bool, why: str) -> None:
        if ok:
            bar.attach_buttons(bridge.button_store(), bridge.commands)
            bar.set_status("Type something and press Enter.")
        else:
            bar.set_status(f"Agent could not start: {why}")
            bar.field.setEnabled(False)

    def on_submit(text: str) -> None:
        # `/ad` bir komutsa hazır talimata açılıyor. Eşleşme yoksa metin
        # olduğu gibi gidiyor: eğik çizgiyle başlayan bir yol yazmak
        # engellenmemeli.
        expanded = bridge.expand_command(text)
        window.activity.add_step("You", "", text, "__sen__")
        # Araya cümle sıkıştırırken cevabı silme: süren turun anlatımı
        # ekranda kalmalı, yeni bir tur başlıyorsa temizlenmeli.
        if not bar.busy:
            bar.clear_run()
            bar.show_operation(None)
        bar.add_user(text)
        bar.set_busy(True)
        bar.set_status("Working…")
        window.run_instruction(text)
        bridge.run(expanded or text)

    steps = {"n": 0}
    unsaved: dict[str, int] = {}
    ide: dict = {"view": None}

    def open_remote(session, title_suffix: str = "") -> None:
        """Sunucu panelini açar ya da öne getirir."""
        from app.remote_view import RemoteView

        view = RemoteView(tokens, session)
        view.show_path(session.cwd)
        window.open_panel("__uzak__", f"{session.host.label} · server", view,
                          glyph="sunucu", label=session.host.label)

    def connect_remote() -> None:
        """Berkay 'Sunucu' düğmesine bastı."""
        from PySide6.QtWidgets import QDialog
        from app.remote_view import ConnectDialog
        from backend.remote.ssh import RemoteError, SshSession

        dialog = ConnectDialog(tokens, window)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        session = SshSession(dialog.result_host())
        bar.set_status(f"connecting to {session.host.label}…")
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
        window.status.set_line(f"Connected: {banner}")

    window.status.connect_remote.clicked.connect(connect_remote)

    # Masa sabit bir sayfa: ajan yan alanı hiç kullanmasa da rayda duruyor
    # ve boş masayı gösteriyor. Yakalama yalnızca sayfa görünürken dönüyor,
    # yani bakılmayan bir masa hiç işlemci yemiyor.
    from app.masa import MasaPenceresi, masa_kaynagi

    masa_gorunumu = MasaPenceresi(masa_kaynagi(bridge.dispatcher))
    # Masa başlıksız: kendi paneli zaten bir başlık şeridi ve ikisini üst
    # üste koymak aynı işi yapan iki çubuk demekti.
    window.add_fixed_page("masa", "Desk", "pencere", masa_gorunumu,
                          basliksiz=True)

    def show_desk() -> None:
        window.show_page("masa")

    def on_panel(skill: str, panel: dict) -> None:
        """Bir yetenek panel üretti — arayüzde yeni bir özellik."""
        from app.panel_view import SkillPanel

        window.open_panel(f"__yetenek__{skill}", panel["baslik"],
                          SkillPanel(tokens, panel),
                          glyph="yetenek", label=skill)

    def on_wrote(paths: list) -> None:
        """Ajan dosya yazdı — kodu göster.

        "yazıldı" demek yetmiyor: ajan diske kod koyuyor ve görmeden ona
        güvenmen gerekiyor.

        Dosya başına bir panel açmak eskiden ekranı sekmelerle dolduruyordu
        ve dosyalar arasındaki ilişkiyi göstermiyordu. Tek bir kod paneli
        var: solda projenin ağacı, sağda sekmeler.
        """
        gecerli = [p for p in paths if Path(p).is_file()]
        if not gecerli:
            return
        kok = _ortak_klasor(gecerli)
        if ide["view"] is None:
            from app.ide import IdeView

            ide["view"] = IdeView(tokens, kok)
        else:
            ide["view"].set_root(kok)
            ide["view"].reload()
        window.open_panel("__kod__", f"Code · {Path(kok).name}", ide["view"],
                          glyph="sayfa", label="Code")
        for path in gecerli[-3:]:
            ide["view"].open_file(path)

    def on_document(shot) -> None:
        """Ajan bir belge açtığında ya da değiştirdiğinde panel belirir."""
        unsaved[shot.name] = shot.unsaved
        title = f"{shot.name} · {shot.kind}"
        if shot.unsaved:
            title += f"  ({shot.unsaved} unsaved)"
        window.open_panel(shot.name, title, _panel_for(shot, tokens),
                          glyph="tablo" if shot.kind == "sheet" else "yazi",
                          label=shot.name)
        window.set_counters(steps["n"], sum(unsaved.values()), 0)

    def _bakis(payload: dict) -> None:
        """Gözler gerçekten tıklanacak yere bakıyor.

        Koordinat zaten elimizde ve yakalanan ekran 1920x1080; merkeze
        göre -1..1 aralığına çeviriyoruz. Rastgele kıpırdayan bir maskot
        süs olurdu — buradaki her hareket gibi bu da bir veriyi taşıyor.
        """
        nokta = payload.get("coordinate")
        if isinstance(nokta, (list, tuple)) and len(nokta) == 2:
            try:
                x, y = float(nokta[0]), float(nokta[1])
            except (TypeError, ValueError):
                return
            bar.ring.face.look_at(x / 960.0 - 1.0, y / 540.0 - 1.0)
        else:
            # Koordinat yoksa bakış baloncuğa dönüyor: maskot kendi
            # söylediğine bakıyor. Körü körüne öne çevirmek, konuşurken
            # başka yere bakmak olurdu.
            bar.bakisi_tazele()

    def on_said(parca: str) -> None:
        """Model yazarken harfler düşüyor.

        Akış zaten çekirdekte vardı ama arayüz onu hiç dinlemiyordu: cevap
        yalnızca tur bitince, tek seferde beliriyordu.
        """
        bar.stream(parca)

    def on_action(tool: str, payload: dict) -> None:
        # Ajan yan masaüstüne dokundu: orada olan bitenin görünmesi bu
        # aracın bütün gerekçesi. Pencereyi elle açmayı beklemek, ilk
        # koşuda kimsenin bakmadığı bir çalışma alanı demek.
        if tool.startswith("side_"):
            show_desk()
            if tool == "side_launch":
                masa_gorunumu.masa_acildi()
        op = _describe(tool, payload)
        bar.ring.step(tool)
        bar.set_tool(op.tool, op.target or op.detail)
        _bakis(payload)
        bar.add_step(tool, op.tool, op.target or op.detail)
        bar.show_operation(op)
        window.activity.add_step(op.tool, op.target, op.detail, tool)
        steps["n"] += 1
        window.set_counters(steps["n"], 0, 0)

    def on_result(tool: str, text: str, is_error: bool, png: bytes) -> None:
        # Adım bitti: halkada kalıcı bir dilim bırakıyor, hata kırmızı.
        bar.ring.settle(is_error)
        bar.settle_step(is_error)
        # Ajan bir düğme kurduysa çubuk hemen göstersin; yeniden başlatmak
        # gerekmesin.
        if tool == "side_close" and not is_error:
            masa_gorunumu.masa_kapandi()
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
            window.activity.annotate_last(text[:600], error=True, tool=tool)
        elif text and text != "OK":
            window.activity.annotate_last(text[:900], tool=tool)
        if is_error:
            bar.set_status(f"{tool}: {text[:120]}")

    def on_finished(text: str) -> None:
        bar.set_busy(False)
        bar.show_operation(None)
        bar.set_status("")
        # Metin akarken zaten yazıldı; burada tekrar koymak turun ilk
        # adımlarındaki anlatımı silerdi. Yalnızca hiç akmadıysa yazılıyor.
        if bar.reply.text().strip():
            bar.end_stream()
        else:
            bar.say(text or "Bitti.")
        bar._fit_reply()
        window.set_phase("bitti")
        window.status.set_line(text[:120] if text else "Bitti.")

    def on_rapor(satir: str) -> None:
        """Ajan bir iş yaptığını söyledi ama denetim kaydında yok.

        Durum satırına yazılıyor, cevabın içine değil: cevap ajanın
        sözü, bu ise ona dair bir gözlem. İkisini aynı baloncuğa koymak,
        ajanı kendi hakkında konuşuyor gibi gösterirdi.
        """
        window.status.set_line(satir)

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
    bridge.said.connect(on_said)
    bridge.pulse.connect(bar.ring.pulse)
    bridge.acted.connect(on_action)
    bridge.result.connect(on_result)
    bridge.document.connect(on_document)
    bridge.panel.connect(on_panel)
    bridge.wrote.connect(on_wrote)
    bridge.rapor.connect(on_rapor)
    bridge.finished.connect(on_finished)
    bridge.failed.connect(on_failed)
    bridge.approval.connect(on_approval)
    bar.submitted.connect(on_submit)
    bar.set_commands(bridge.commands)
    window.stop_requested.connect(bridge.stop)
    bar.stop_requested.connect(bridge.stop)
    app.aboutToQuit.connect(bridge.shutdown)

    bridge.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
