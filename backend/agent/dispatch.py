"""Araç çağrısı -> gerçek eylem.

`computer_toolset_20260801` üye araçlarını Windows eylemlerine çeviriyor.
Koordinatlar modelden ekran görüntüsü uzayında gelir; buradan çıkarken aktif
ekranın ofsetiyle sanal masaüstü uzayına dönüşürler. Çeviri tek noktada
kalsın diye başka hiçbir modül `to_virtual` çağırmıyor.
"""

from __future__ import annotations

import base64
import io
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..computer import files
from ..computer import input as kb
from ..computer import uia
from ..computer import windows as win
from ..computer.capture import ScreenCapture
from ..computer.displays import DisplayMap
from ..computer.terminal import TerminalError, TerminalRegistry
from ..office.sheet import SheetError, Workbook
from ..office.store import OfficeError, OfficeStore
from ..office.text import TextError
from ..safety import gate
from ..safety.killswitch import KillSwitch
from ..remote.ssh import RemoteError, SshHost, SshSession
from ..skills.api import Ortam
from ..skills.panel import PanelError, normalise, to_text
from ..skills.registry import SkillError, SkillRegistry
from ..skills.shortcuts import Shortcut, ShortcutError, ShortcutStore

#: Ekran görüntüsü döndüren üyeler — sonuçları metin değil görsel bloktur.
VISUAL_MEMBERS = {"screenshot", "zoom"}

_CLICK_COUNTS = {"left_click": 1, "double_click": 2, "triple_click": 3}
_CLICK_BUTTONS = {"left_click": "left", "right_click": "right", "middle_click": "middle"}


class ToolError(RuntimeError):
    """Araç çalıştırılamadı — modele `is_error` olarak döner."""


class Denied(ToolError):
    """Berkay eylemi reddetti. Modele hata olarak döner ki başka yol denesin."""


@dataclass
class ToolOutcome:
    """Bir araç çağrısının sonucu."""

    content: str | list[dict[str, Any]]
    is_error: bool = False


def _png_block(png: bytes) -> list[dict[str, Any]]:
    return [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.standard_b64encode(png).decode("ascii"),
            },
        }
    ]


class Dispatcher:
    """Aktif ekranı ve yakalayıcıyı tutan araç çalıştırıcısı."""

    def __init__(
        self,
        displays: DisplayMap,
        capture: ScreenCapture,
        kill: KillSwitch,
        approve: Callable[[str, str, str], bool] | None = None,
        active_index: int = 0,
    ) -> None:
        self.displays = displays
        self.capture = capture
        self.kill = kill
        # Onay isteyici verilmezse her riskli eylem reddedilir. Varsayılan
        # "izin ver" olsaydı, onay kancasını bağlamayı unutan bir çağıran
        # kapıyı sessizce kapatmış olurdu.
        self.approve = approve or (lambda _n, _d, _r: False)
        self.active_index = active_index
        self.terminals = TerminalRegistry()
        self.office = OfficeStore()
        # Yerleşik araç adları rezerve: bir yetenek `run_shell` adını alıp
        # kabuk çağrılarını sessizce ele geçiremesin.
        from .tools import CUSTOM_TOOL_NAMES

        builtin = {m[4:] for m in dir(self) if m.startswith("_do_")}
        self.skills = SkillRegistry(reserved=frozenset(builtin | CUSTOM_TOOL_NAMES))
        self.buttons = ShortcutStore()
        self.remote: SshSession | None = None
        #: (yetenek adı, panel) — arayüzün alıp çizeceği son panel.
        self.last_panel: tuple[str, dict] | None = None

    def shutdown(self) -> None:
        """Açık PTY'leri kapatır. Yoksa süreçler ajan bittikten sonra yaşar."""
        self.terminals.close_all()

    @property
    def active(self):
        return self.displays[self.active_index]

    def _virtual(self, coordinate: Any) -> tuple[int, int]:
        if not (isinstance(coordinate, (list, tuple)) and len(coordinate) == 2):
            raise ToolError(f"Koordinat [x, y] olmalı, gelen: {coordinate!r}")
        x, y = int(coordinate[0]), int(coordinate[1])
        try:
            return self.active.to_virtual(x, y)
        except ValueError as exc:
            raise ToolError(str(exc)) from None

    def run(self, name: str, payload: dict[str, Any]) -> ToolOutcome:
        """Tek bir araç çağrısını çalıştırır."""
        self.kill.check()
        handler = getattr(self, f"_do_{name}", None)
        if handler is None:
            skill = self.skills.get(name)
            if skill is None:
                raise ToolError(f"Bilinmeyen araç: {name}")
            return self._run_skill(skill, payload)

        self._gate(name, payload)
        return handler(payload)

    def _run_skill(self, skill, payload: dict[str, Any]) -> ToolOutcome:
        """Yeteneği çalıştırır.

        Yeteneğin fırlattığı istisna ajanı düşürmüyor; modele hata olarak
        dönüyor ki ajan kendi yazdığı kodu düzeltebilsin. Bu, yeteneklerin
        yararlı olmasının asıl yolu: ilk deneme tutmaz, ikinci tutar.
        """
        if skill.needs_approval and not self.approve(
            skill.name, str(payload)[:400], f"{skill.name} yeteneği onay istiyor"
        ):
            raise Denied(f"Berkay {skill.name} yeteneğini reddetti.")
        try:
            result = skill.run(dict(payload), Ortam(self))
        except Denied:
            raise
        except Exception as exc:
            raise ToolError(
                f"{skill.name} çalışırken hata — {type(exc).__name__}: {exc}. "
                f"Kod {skill.path}. skill_write ile düzeltebilirsin."
            ) from None
        # Yetenek panel döndürebiliyor: `{"panel": {...}}`. Panel arayüze
        # gidiyor, metin karşılığı modele. İkisi ayrılmazsa ajan kullanıcıya
        # gösterdiği şeyi bilmiyor ve bir sonraki cümlesinde çelişiyor.
        try:
            panel = normalise(result)
        except PanelError as exc:
            raise ToolError(
                f"{skill.name} geçersiz bir panel döndürdü: {exc}. "
                f"skill_write ile düzelt."
            ) from None
        if panel is not None:
            self.last_panel = (skill.name, panel)
            metin = str(result.get("metin") or "").strip()
            return ToolOutcome(content=metin or to_text(panel))
        return ToolOutcome(content=str(result) if result is not None else "OK")

    def _gate(self, name: str, payload: dict[str, Any]) -> None:
        """Riskli eylemde onay ister. Onay yoksa eylem hiç çalışmaz."""
        verdict = gate.classify(name, payload, window_title=win.foreground_title())
        if not verdict.needs_confirmation:
            return

        detail = payload.get("command") or payload.get("text") or str(payload)
        if not self.approve(name, str(detail)[:400], verdict.reason):
            raise Denied(f"Berkay reddetti ({verdict.reason}). Bu eylem çalıştırılmadı.")

    # --- yetenekler -------------------------------------------------------

    def _do_skill_list(self, payload: dict[str, Any]) -> ToolOutcome:
        name = payload.get("name")
        if name:
            try:
                return ToolOutcome(content=self.skills.read(str(name)))
            except SkillError as exc:
                raise ToolError(str(exc)) from None
        return ToolOutcome(content=self.skills.report())

    def _do_skill_write(self, payload: dict[str, Any]) -> ToolOutcome:
        _require(payload, "name", "code", "why")
        name, code = str(payload["name"]), str(payload["code"])
        # Onay ekranında kodun tamamı görünüyor: neyin kurulduğunu görmeden
        # onaylamak, onay olmamasıyla aynı şey.
        detail = f"{name}.py\n\n{code}"
        if not self.approve("skill_write", detail, str(payload["why"])):
            raise Denied(f"Berkay {name} yeteneğini onaylamadı.")
        try:
            skill = self.skills.write(name, code)
        except SkillError as exc:
            raise ToolError(f"Yetenek kurulamadı: {exc}") from None
        return ToolOutcome(
            content=f"{skill.name} kuruldu ve yüklendi — {skill.path}. "
            f"Bir sonraki adımda çağırabilirsin."
        )

    def _do_skill_remove(self, payload: dict[str, Any]) -> ToolOutcome:
        _require(payload, "name", "why")
        name = str(payload["name"])
        if not self.approve("skill_remove", f"{name}.py siliniyor", str(payload["why"])):
            raise Denied(f"Berkay {name} yeteneğinin silinmesini onaylamadı.")
        try:
            path = self.skills.remove(name)
        except SkillError as exc:
            raise ToolError(str(exc)) from None
        return ToolOutcome(content=f"{path.name} silindi.")

    def _do_button_write(self, payload: dict[str, Any]) -> ToolOutcome:
        _require(payload, "name", "label", "instruction", "why")
        shortcut = Shortcut(
            name=str(payload["name"]),
            label=str(payload["label"]),
            instruction=str(payload["instruction"]),
            glyph=str(payload.get("glyph") or "yetenek"),
        )
        # Düğme Berkay'ın arayüzünü değiştiriyor; sessizce eklenmemeli.
        detail = f"{shortcut.label} -> {shortcut.instruction}"
        if not self.approve("button_write", detail, str(payload["why"])):
            raise Denied(f"Berkay {shortcut.name} düğmesini onaylamadı.")
        try:
            self.buttons.save(shortcut)
        except ShortcutError as exc:
            raise ToolError(str(exc)) from None
        return ToolOutcome(
            content=f"{shortcut.label!r} düğmesi çubukta. Berkay düzenleyip silebilir."
        )

    def _do_button_remove(self, payload: dict[str, Any]) -> ToolOutcome:
        _require(payload, "name", "why")
        name = str(payload["name"])
        if not self.approve("button_remove", f"{name} düğmesi siliniyor", str(payload["why"])):
            raise Denied(f"Berkay {name} düğmesinin silinmesini onaylamadı.")
        try:
            self.buttons.remove(name)
        except ShortcutError as exc:
            raise ToolError(str(exc)) from None
        return ToolOutcome(content=f"{name} düğmesi kaldırıldı.")

    # --- uzak makine ------------------------------------------------------

    def _remote_session(self) -> SshSession:
        """Bağlı sunucu.

        Adı `_session` idi ve sınıfta terminal oturumu için zaten bir
        `_session` vardı; sonra tanımlanan öncekini eziyordu ve bütün
        `remote_*` araçları "missing 1 required positional argument"
        hatasıyla düşüyordu. Python bu çakışmayı sessizce kabul ediyor.
        """
        if self.remote is None or not self.remote.connected:
            raise ToolError(
                "Sunucuya bağlı değilsin. Önce remote_connect çağır "
                "(Berkay'ın sunucusu için alias=\"brky\")."
            )
        return self.remote

    def _do_remote_connect(self, payload: dict[str, Any]) -> ToolOutcome:
        host = SshHost(
            alias=str(payload.get("alias", "")).strip(),
            host=str(payload.get("host", "")).strip(),
            user=str(payload.get("user", "") or "root").strip(),
            port=int(payload.get("port") or 22),
        )
        if not host.alias and not host.host:
            raise ToolError("alias ya da host gerekli")
        session = SshSession(host)
        try:
            banner = session.connect()
        except RemoteError as exc:
            raise ToolError(str(exc)) from None
        self.remote = session
        return ToolOutcome(
            content=f"Bağlandı: {banner}\nBulunduğun yer: {session.cwd}"
        )

    def _do_remote_list(self, payload: dict[str, Any]) -> ToolOutcome:
        session = self._remote_session()
        path = str(payload.get("path") or session.cwd)
        try:
            entries = session.enter(path)
        except RemoteError as exc:
            raise ToolError(str(exc)) from None
        if not entries:
            return ToolOutcome(content=f"{path} boş.")
        lines = [f"{path}:"]
        for entry in entries:
            kind = "d" if entry.is_dir else "-"
            lines.append(
                f"  {kind} {entry.mode} {entry.size_label:>9} "
                f"{entry.modified}  {entry.name}"
            )
        return ToolOutcome(content="\n".join(lines))

    def _do_remote_read(self, payload: dict[str, Any]) -> ToolOutcome:
        _require(payload, "path")
        try:
            return ToolOutcome(content=self._remote_session().read(str(payload["path"])))
        except RemoteError as exc:
            raise ToolError(str(exc)) from None

    def _do_remote_write(self, payload: dict[str, Any]) -> ToolOutcome:
        _require(payload, "path", "content", "why")
        session = self._remote_session()
        path, content = str(payload["path"]), str(payload["content"])
        # Uzak yazma her zaman soruluyor ve onay ekranında hangi sunucu
        # olduğu yazıyor: iki sunucuya bağlıyken hangisine yazdığını
        # bilmemek, yanlış makineyi bozmanın en kolay yolu.
        detail = f"{session.host.label}:{path}\n\n{content[:2000]}"
        if not self.approve("remote_write", detail, str(payload["why"])):
            raise Denied(f"Berkay {path} yazımını reddetti.")
        try:
            return ToolOutcome(content=session.write(path, content))
        except RemoteError as exc:
            raise ToolError(str(exc)) from None

    def _do_remote_run(self, payload: dict[str, Any]) -> ToolOutcome:
        _require(payload, "command")
        session = self._remote_session()
        command = str(payload["command"])
        verdict = gate.classify_remote(command)
        if verdict.needs_confirmation and not self.approve(
            "remote_run", f"{session.host.label}$ {command}", verdict.reason
        ):
            raise Denied(f"Berkay reddetti ({verdict.reason}).")
        try:
            out = session.run(command, timeout=int(payload.get("timeout") or 60))
        except RemoteError as exc:
            raise ToolError(str(exc)) from None
        return ToolOutcome(content=out.strip() or "(çıktı yok)")

    # --- görsel -----------------------------------------------------------

    def _do_screenshot(self, _payload: dict[str, Any]) -> ToolOutcome:
        frame = self.capture.grab(self.active)
        return ToolOutcome(content=_png_block(frame.to_png()))

    def _do_zoom(self, payload: dict[str, Any]) -> ToolOutcome:
        region = payload.get("region")
        if not (isinstance(region, (list, tuple)) and len(region) == 4):
            raise ToolError(f"region [x0, y0, x1, y1] olmalı, gelen: {region!r}")

        # Taze yakalama: model bölgeyi büyütmek istediğinde ilgilendiği şey
        # ekranın şu anki hali. Eski kareden kırpmak, aradan geçen sürede
        # değişmiş bir arayüzü değişmemiş gibi göstermek olurdu.
        frame = self.capture.grab(self.active)
        try:
            crop = frame.crop(tuple(int(v) for v in region))
        except ValueError as exc:
            raise ToolError(str(exc)) from None

        buffer = io.BytesIO()
        crop.save(buffer, format="PNG", compress_level=1)
        return ToolOutcome(content=_png_block(buffer.getvalue()))

    # --- fare -------------------------------------------------------------

    def _click(self, name: str, payload: dict[str, Any]) -> ToolOutcome:
        coordinate = payload.get("coordinate")
        with kb.modifiers_held(payload.get("text")):
            if coordinate is None:
                vx, vy = kb.cursor_position()
            else:
                vx, vy = self._virtual(coordinate)
            kb.click(vx, vy, button=_CLICK_BUTTONS.get(name, "left"),
                     count=_CLICK_COUNTS.get(name, 1))
        return ToolOutcome(content="OK")

    def _do_left_click(self, payload): return self._click("left_click", payload)
    def _do_right_click(self, payload): return self._click("right_click", payload)
    def _do_middle_click(self, payload): return self._click("middle_click", payload)
    def _do_double_click(self, payload): return self._click("double_click", payload)
    def _do_triple_click(self, payload): return self._click("triple_click", payload)

    def _do_mouse_move(self, payload: dict[str, Any]) -> ToolOutcome:
        kb.move_to(*self._virtual(payload.get("coordinate")))
        return ToolOutcome(content="OK")

    def _do_left_mouse_down(self, _payload) -> ToolOutcome:
        kb.mouse_down("left")
        return ToolOutcome(content="OK")

    def _do_left_mouse_up(self, _payload) -> ToolOutcome:
        kb.mouse_up("left")
        return ToolOutcome(content="OK")

    def _do_cursor_position(self, _payload) -> ToolOutcome:
        vx, vy = kb.cursor_position()
        display = self.displays.locate_virtual(vx, vy)
        if display is None:
            return ToolOutcome(content="İmleç hiçbir ekranın üstünde değil")
        x, y = display.from_virtual(vx, vy)
        return ToolOutcome(content=f"[{x}, {y}] (ekran {display.index})")

    def _do_left_click_drag(self, payload: dict[str, Any]) -> ToolOutcome:
        start = payload.get("start_coordinate")
        end = payload.get("coordinate")
        if start is None or end is None:
            raise ToolError("left_click_drag hem start_coordinate hem coordinate ister")
        with kb.modifiers_held(payload.get("text")):
            kb.drag(self._virtual(start), self._virtual(end))
        return ToolOutcome(content="OK")

    def _do_scroll(self, payload: dict[str, Any]) -> ToolOutcome:
        direction = payload.get("scroll_direction")
        amount = int(payload.get("scroll_amount", 3))
        coordinate = payload.get("coordinate")
        at = self._virtual(coordinate) if coordinate is not None else None
        with kb.modifiers_held(payload.get("text")):
            try:
                kb.scroll(direction, amount, at=at)
            except ValueError as exc:
                raise ToolError(str(exc)) from None
        return ToolOutcome(content="OK")

    # --- klavye ve zamanlama ----------------------------------------------

    def _do_type(self, payload: dict[str, Any]) -> ToolOutcome:
        text = payload.get("text")
        if not isinstance(text, str):
            raise ToolError(f"type için metin gerekli, gelen: {text!r}")
        kb.type_text(text)
        return ToolOutcome(content="OK")

    def _do_key(self, payload: dict[str, Any]) -> ToolOutcome:
        combo = payload.get("text")
        if not isinstance(combo, str) or not combo.strip():
            # Eksik alanda ham bir AttributeError dönüyordu; modele de
            # yeteneğe de neyin eksik olduğunu söylemiyordu.
            raise ToolError(
                f"key için tuş gerekli — 'text' alanına 'ctrl+k' gibi bir "
                f"kombinasyon yaz. Gelen: {combo!r}"
            )
        repeat = int(payload.get("repeat", 1))
        try:
            kb.press(combo, repeat=repeat)
        except ValueError as exc:
            raise ToolError(str(exc)) from None
        return ToolOutcome(content="OK")

    def _do_hold_key(self, payload: dict[str, Any]) -> ToolOutcome:
        duration = _duration(payload.get("duration"))
        try:
            kb.hold(payload.get("text"), duration)
        except ValueError as exc:
            raise ToolError(str(exc)) from None
        return ToolOutcome(content="OK")

    def _do_wait(self, payload: dict[str, Any]) -> ToolOutcome:
        duration = _duration(payload.get("duration"))
        # Beklerken de acil durdurmaya cevap vermeli — 300 saniyelik bir
        # `sleep` Esc'yi 5 dakika sağır eder.
        _interruptible_sleep(duration, self.kill)
        return ToolOutcome(content="OK")

    # --- özel araçlar -----------------------------------------------------

    def _do_read_ui_tree(self, _payload: dict[str, Any]) -> ToolOutcome:
        result = uia.snapshot(self.active)
        if result.thin:
            return ToolOutcome(
                content=(
                    f"{result.text}\n\n"
                    "Ağaç yüzeysel — bu pencere erişilebilirlik bilgisi vermiyor. "
                    "Ekran görüntüsü al."
                )
            )
        return ToolOutcome(content=result.text)

    def _do_launch_app(self, payload: dict[str, Any]) -> ToolOutcome:
        target = str(payload.get("target", "")).strip()
        if not target:
            raise ToolError("launch_app için target gerekli")
        arguments = str(payload.get("arguments", "")).strip()

        before = win.foreground_title()
        try:
            if target.startswith(("http://", "https://")):
                os.startfile(target)
                expect = None
            else:
                resolved = shutil.which(target) or target
                subprocess.Popen(
                    f'"{resolved}" {arguments}'.strip(),
                    shell=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                expect = os.path.basename(resolved)
        except OSError as exc:
            raise ToolError(f"{target} başlatılamadı: {exc}") from None

        # Öne gelmesini bekle. Gelmezse modele söyle — sessizce devam edip
        # yanlış pencereye yazmak Faz 1'de tam olarak bu şekilde patlamıştı.
        appeared = self._wait_for_new_foreground(before, expect)
        now = win.foreground_title()
        if not appeared:
            return ToolOutcome(
                content=(
                    f"{target} başlatıldı ama öne gelmedi. Odakta {now!r} var. "
                    "Yazmadan önce ekran görüntüsü alıp doğrula."
                )
            )
        return ToolOutcome(content=f"{target} açıldı, ön planda: {now!r}")

    def _wait_for_new_foreground(
        self, before: str, expect: str | None, timeout: float = 10.0
    ) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.kill.check()
            if expect and win.matches_foreground(expect, None):
                return True
            title = win.foreground_title()
            if title and title != before:
                return True
            time.sleep(0.15)
        return False

    def _do_run_shell(self, payload: dict[str, Any]) -> ToolOutcome:
        command = str(payload.get("command", "")).strip()
        if not command:
            raise ToolError("run_shell için command gerekli")
        timeout = min(int(payload.get("timeout", 30)), 300)

        try:
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                timeout=timeout,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except subprocess.TimeoutExpired:
            raise ToolError(
                f"Komut {timeout} saniyede bitmedi ve durduruldu. Girdi bekliyor olabilir."
            ) from None

        output = (completed.stdout or "").strip()
        errors = (completed.stderr or "").strip()
        if len(output) > 8000:
            output = output[:8000] + f"\n... ({len(output)} karakterden kesildi)"

        parts = [f"cikis_kodu={completed.returncode}"]
        if output:
            parts.append(output)
        if errors:
            parts.append(f"stderr:\n{errors[:2000]}")
        return ToolOutcome(
            content="\n".join(parts), is_error=completed.returncode != 0
        )

    # --- dosyalar ---------------------------------------------------------

    def _do_write_file(self, payload: dict[str, Any]) -> ToolOutcome:
        try:
            return ToolOutcome(
                content=files.write(
                    str(payload.get("path", "")),
                    str(payload.get("content", "")),
                    append=bool(payload.get("append", False)),
                )
            )
        except files.FileError as exc:
            raise ToolError(str(exc)) from None

    def _do_read_file(self, payload: dict[str, Any]) -> ToolOutcome:
        try:
            return ToolOutcome(content=files.read(str(payload.get("path", ""))))
        except files.FileError as exc:
            raise ToolError(str(exc)) from None

    def _do_edit_file(self, payload: dict[str, Any]) -> ToolOutcome:
        try:
            return ToolOutcome(
                content=files.edit(
                    str(payload.get("path", "")),
                    str(payload.get("old", "")),
                    str(payload.get("new", "")),
                )
            )
        except files.FileError as exc:
            raise ToolError(str(exc)) from None

    def _do_list_dir(self, payload: dict[str, Any]) -> ToolOutcome:
        try:
            return ToolOutcome(content=files.list_dir(str(payload.get("path", ""))))
        except files.FileError as exc:
            raise ToolError(str(exc)) from None

    # --- terminaller ------------------------------------------------------

    def _do_terminal_open(self, payload: dict[str, Any]) -> ToolOutcome:
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ToolError("terminal_open için name gerekli")
        try:
            session = self.terminals.open(
                name,
                command=(payload.get("command") or None),
                cwd=(payload.get("cwd") or None),
            )
        except TerminalError as exc:
            raise ToolError(str(exc)) from None

        settled = session.wait_idle(timeout=20)
        return ToolOutcome(content=self._screen(session, settled))

    def _do_terminal_send(self, payload: dict[str, Any]) -> ToolOutcome:
        session = self._session(payload)
        text = payload.get("text")
        key = payload.get("key")
        if text is None and key is None:
            raise ToolError("terminal_send için text ya da key gerekli")

        try:
            if text is not None:
                session.send(str(text))
                if payload.get("submit", True):
                    session.send_key("enter")
            if key is not None:
                session.send_key(str(key))
        except TerminalError as exc:
            raise ToolError(str(exc)) from None

        wait = min(float(payload.get("wait", 15)), 120.0)
        settled = session.wait_idle(timeout=wait)
        return ToolOutcome(content=self._screen(session, settled))

    def _do_terminal_read(self, payload: dict[str, Any]) -> ToolOutcome:
        session = self._session(payload)
        wait = float(payload.get("wait", 0))
        settled = session.wait_idle(timeout=wait) if wait > 0 else True
        return ToolOutcome(content=self._screen(session, settled))

    def _do_terminal_close(self, payload: dict[str, Any]) -> ToolOutcome:
        name = str(payload.get("name", ""))
        try:
            self.terminals.close(name)
        except TerminalError as exc:
            raise ToolError(str(exc)) from None
        return ToolOutcome(content=f"{name!r} oturumu kapatıldı.")

    def _session(self, payload: dict[str, Any]):
        try:
            return self.terminals.get(str(payload.get("name", "")))
        except TerminalError as exc:
            raise ToolError(str(exc)) from None

    def _screen(self, session, settled: bool) -> str:
        text = session.screen_text()
        if not settled:
            # Durmadıysa bunu söylemek şart: model ekranı bitmiş sanıp yarım
            # çizilmiş bir arayüze göre karar verirse yanlış tuşa basar.
            text += "\n[hâlâ çıktı geliyor — terminal_read ile tekrar bak]"
        if not session.alive:
            text += "\n[oturumdaki süreç sonlandı]"
        return text

    # --- ofis -------------------------------------------------------------

    def _do_office_open(self, payload: dict[str, Any]) -> ToolOutcome:
        try:
            document = self.office.open(
                str(payload.get("name", "")), str(payload.get("path", ""))
            )
        except OfficeError as exc:
            raise ToolError(str(exc)) from None
        return ToolOutcome(content=document.summary())

    def _do_office_read(self, payload: dict[str, Any]) -> ToolOutcome:
        document = self._document(payload)
        try:
            if isinstance(document, Workbook):
                return ToolOutcome(
                    content=document.read(
                        ref=payload.get("ref"), sheet=payload.get("sheet")
                    )
                )
            return ToolOutcome(content=document.read(start=int(payload.get("start", 0))))
        except (SheetError, TextError) as exc:
            raise ToolError(str(exc)) from None

    def _do_office_edit(self, payload: dict[str, Any]) -> ToolOutcome:
        document = self._document(payload)
        operation = str(payload.get("operation", ""))
        why = str(payload.get("why", ""))

        try:
            if operation == "write":
                _require(payload, "ref", "values")
                return ToolOutcome(
                    content=document.write(
                        str(payload["ref"]), payload["values"], why,
                        sheet=payload.get("sheet"),
                    )
                )
            if operation == "add_sheet":
                _require(payload, "sheet")
                return ToolOutcome(content=document.add_sheet(str(payload["sheet"]), why))
            if operation == "append":
                _require(payload, "text")
                return ToolOutcome(
                    content=document.append(
                        str(payload["text"]), why, style=payload.get("style")
                    )
                )
            if operation == "replace":
                _require(payload, "index", "text")
                return ToolOutcome(
                    content=document.replace(int(payload["index"]), str(payload["text"]), why)
                )
            if operation == "add_table":
                _require(payload, "values")
                return ToolOutcome(content=document.add_table(payload["values"], why))
        except AttributeError:
            raise ToolError(
                f"{operation!r} bu belge türünde yok. {document.path} bir "
                f"{document.kind} belgesi."
            ) from None
        except ValueError as exc:
            raise ToolError(str(exc)) from None
        except (SheetError, TextError) as exc:
            raise ToolError(str(exc)) from None

        raise ToolError(f"Bilinmeyen işlem: {operation!r}")

    def _do_office_save(self, payload: dict[str, Any]) -> ToolOutcome:
        document = self._document(payload)
        try:
            return ToolOutcome(content=document.save(payload.get("path")))
        except (SheetError, TextError) as exc:
            raise ToolError(str(exc)) from None

    def _do_office_history(self, payload: dict[str, Any]) -> ToolOutcome:
        document = self._document(payload)
        undo = int(payload.get("undo", 0))
        if undo > 0:
            result = document.undo(undo)
            return ToolOutcome(content=f"{result}\n\n{document.ledger.report()}")
        return ToolOutcome(content=document.ledger.report())

    def _do_office_close(self, payload: dict[str, Any]) -> ToolOutcome:
        name = str(payload.get("name", ""))
        try:
            if payload.get("discard"):
                return ToolOutcome(content=self.office.discard(name))
            return ToolOutcome(content=self.office.close(name))
        except OfficeError as exc:
            raise ToolError(str(exc)) from None

    def _document(self, payload: dict[str, Any]):
        try:
            return self.office.get(str(payload.get("name", "")))
        except OfficeError as exc:
            raise ToolError(str(exc)) from None

    def _do_switch_display(self, payload: dict[str, Any]) -> ToolOutcome:
        try:
            index = int(payload["index"])
            display = self.displays[index]
        except (KeyError, ValueError, TypeError) as exc:
            raise ToolError(f"Geçersiz ekran indeksi: {exc}") from None
        except IndexError as exc:
            raise ToolError(str(exc)) from None

        self.active_index = index
        return ToolOutcome(
            content=f"Ekran {index} ({display.width}x{display.height}) aktif."
        )


def _require(payload: dict[str, Any], *keys: str) -> None:
    missing = [k for k in keys if payload.get(k) is None]
    if missing:
        raise ToolError(
            f"Bu islem icin eksik alan: {', '.join(missing)}"
        )


def _duration(value: Any) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        raise ToolError(f"Süre sayı olmalı, gelen: {value!r}") from None
    if not 0 <= seconds <= 300:
        raise ToolError(f"Süre 0-300 saniye arasında olmalı, gelen: {seconds}")
    return seconds


def _interruptible_sleep(seconds: float, kill: KillSwitch, step: float = 0.1) -> None:
    import time

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        kill.check()
        time.sleep(min(step, max(0.0, deadline - time.monotonic())))
