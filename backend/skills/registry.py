"""Yetenek defteri — ajanın kendine yazdığı araçlar.

Ajan bir işi ikinci kez yaparken aynı on adımı tekrar ediyor. Yetenek, o on
adımı bir araca çeviriyor: bir kez yazılıyor, sonra tek çağrıyla çalışıyor.
Ajan bunları kendisi yazıyor — yetenek eklemek için uygulamayı yeniden
derlemek ya da başka bir programın eklenti sistemine bağlanmak gerekmiyor.

Dosyalar `~/.ajan/yetenekler/` içinde, depoda değil: ajanın kendine yazdığı
kod uygulamanın kaynağına karışmamalı ve güncelleme onları silmemeli.

**Bozuk yetenek gizlenmiyor.** Yüklenemeyen bir dosya sessizce atlanmıyor;
hatasıyla birlikte listede duruyor ve ajan da Berkay da görüyor. Sessizce
atlamak, "yazdım" deyip hiç çalışmayan bir yetenek bırakmanın en kolay yolu.

Kod bu süreçte, tam yetkiyle çalışıyor. Kum havuzu yok ve olduğunu iddia
etmiyoruz: yetenek yazmak her seferinde onay istiyor ve kodun tamamı onay
ekranında görünüyor.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

#: Yetenek dosyalarının yeri. `AJAN_STATE_DIR` ile taşınabiliyor.
SKILL_DIR = (
    Path(os.environ.get("AJAN_STATE_DIR") or (Path.home() / ".ajan")) / "yetenekler"
)

#: Araç adı kuralı. Model bu adı yazacak ve ad API şemasına birebir giriyor;
#: boşluk ve Türkçe harf kabul edilmiyor.
NAME_RULE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")

#: Komut adı kuralı, araç adından ayrı ve bilerek daha gevşek. Araç adını
#: model yazıyor ve okunur olmalı; komutu Berkay elle yazıyor ve kısalık
#: onun tek amacı. `/oz` araç adı kuralına takılıyordu — bir kısayolun üç
#: harf zorunluluğu olması kısayol olmasını engelliyor.
COMMAND_RULE = re.compile(r"^[a-z][a-z0-9_]{0,30}$")

#: Sözleşmenin zorunlu alanları. Türkçe, çünkü yeteneği okuyacak olan Berkay.
REQUIRED_KEYS = ("ad", "aciklama", "girdi")


class SkillError(RuntimeError):
    """Yetenek yüklenemedi ya da sözleşmeye uymuyor."""


@dataclass
class Skill:
    name: str
    description: str
    path: Path
    run: Callable[[dict[str, Any], Any], Any]
    schema: dict[str, Any]
    needs_approval: bool = False
    command: Command | None = None

    def tool(self) -> dict[str, Any]:
        """Modele gönderilecek araç tanımı."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.schema,
        }


@dataclass
class Command:
    """Berkay'ın çubuğa `/ad` yazarak çağırdığı hazır talimat.

    Yetenek ajanın kullandığı bir araç; komut Berkay'ın kullandığı bir
    kısayol. İkisi aynı dosyada durabiliyor çünkü çoğu zaman aynı işin iki
    ucu: ajan yeteneği yazıyor, komut onu tek kelimeyle çağırıyor.
    """

    name: str
    description: str
    instruction: str
    path: Path


@dataclass
class Broken:
    path: Path
    error: str

    @property
    def name(self) -> str:
        return self.path.stem


@dataclass
class SkillRegistry:
    """Klasörü izler, değiştiğinde yeniden yükler."""

    directory: Path = SKILL_DIR
    #: Yerleşik araçların adları — üstlerine yazılamaz.
    reserved: frozenset[str] = frozenset()
    skills: dict[str, Skill] = field(default_factory=dict)
    commands: dict[str, Command] = field(default_factory=dict)
    broken: list[Broken] = field(default_factory=list)
    _stamp: tuple | None = field(default=None, repr=False)
    _serial: int = field(default=0, repr=False)

    def _signature(self) -> tuple:
        """Klasörün içeriğinin özeti.

        Önce (ad, değiştirilme zamanı, boyut) kullanılıyordu ve bir testte
        yakalandı: bir karakteri değiştiren düzeltme — `+` yerine `*` —
        boyutu değiştirmiyor ve Windows'ta zaman damgası aynı tikte
        kalabiliyor, yani düzeltilmiş dosya eski hâliyle çalışmaya devam
        ediyordu. İçeriğin özeti bunu tümden ortadan kaldırıyor; dosyalar
        birkaç kilobayt olduğu için maliyeti yok.
        """
        if not self.directory.exists():
            return ()
        out = []
        for path in sorted(self.directory.glob("*.py")):
            try:
                data = path.read_bytes()
            except OSError:
                continue
            out.append((path.name, hashlib.blake2b(data, digest_size=16).digest()))
        return tuple(out)

    def refresh(self, force: bool = False) -> None:
        """Klasör değiştiyse yeniden yükler.

        Berkay bir yetenek dosyasını Not Defteri'nde açıp düzeltebilsin diye
        her turda bakılıyor; imza aynıysa hiçbir şey yapılmıyor.
        """
        signature = self._signature()
        if not force and signature == self._stamp:
            return
        self._stamp = signature
        self.skills = {}
        self.commands = {}
        self.broken = []
        if not self.directory.exists():
            return
        for path in sorted(self.directory.glob("*.py")):
            try:
                skill = self._load(path)
            except SkillError as exc:
                self.broken.append(Broken(path, str(exc)))
                continue
            if skill.name in self.skills:
                owner = self.skills[skill.name].path.name
                self.broken.append(
                    Broken(path, f"the name {skill.name!r} is already used in {owner}")
                )
                continue
            self.skills[skill.name] = skill
            if skill.command is not None:
                self.commands[skill.command.name] = skill.command

    def _load(self, path: Path) -> Skill:
        """Dosyayı okur, derler ve çalıştırır.

        `importlib` yerine kaynağı doğrudan derliyoruz ve bunun somut bir
        sebebi var: `importlib` `__pycache__` içindeki bayt kodunu boyut ve
        zaman damgasıyla doğruluyor. Bir karakteri değiştiren düzeltme —
        `+` yerine `*` — ikisini de değiştirmiyor, yani düzeltilmiş dosya
        eski bayt koduyla çalışmaya devam ediyordu. Bir testte yakalandı.

        Kaynağı elle derlemek önbelleği tümden devre dışı bırakıyor;
        yetenekler küçük dosyalar, derleme maliyeti ölçülemez.
        """
        self._serial += 1
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise SkillError(f"could not read the file: {exc}") from None
        try:
            code = compile(source, str(path), "exec")
        except SyntaxError as exc:
            raise SkillError(
                f"syntax error on line {exc.lineno}: {exc.msg}"
            ) from None

        module_name = f"ajan_yetenek_{path.stem}_{self._serial}"
        module = ModuleType(module_name)
        module.__file__ = str(path)
        # Yetenek içinden `import` çalışabilsin diye modül geçici olarak
        # kayıtlı; iş bitince kaldırılıyor ki liste şişmesin.
        sys.modules[module_name] = module
        try:
            exec(code, module.__dict__)
        except Exception as exc:
            raise SkillError(f"{type(exc).__name__}: {exc}") from None
        finally:
            sys.modules.pop(module_name, None)

        return self._build(path, module)

    def _build(self, path: Path, module: Any) -> Skill:
        spec = getattr(module, "ARAC", None)
        if not isinstance(spec, dict):
            raise SkillError("there is no ARAC dict")
        missing = [k for k in REQUIRED_KEYS if k not in spec]
        if missing:
            raise SkillError(f"missing field in ARAC: {', '.join(missing)}")

        name = str(spec["ad"])
        if not NAME_RULE.match(name):
            raise SkillError(
                f"{name!r} is not a valid name — lower case, digits and underscore, 3-41 characters"
            )
        if name in self.reserved:
            raise SkillError(f"{name!r} is a built-in tool name and cannot be overwritten")

        run = getattr(module, "calistir", None)
        if not callable(run):
            raise SkillError("there is no calistir(girdi, ortam) function")

        properties = spec["girdi"]
        if not isinstance(properties, dict):
            raise SkillError("ARAC['girdi'] must be a dict")
        required = spec.get("zorunlu", list(properties))
        if not isinstance(required, list):
            raise SkillError("ARAC['zorunlu'] must be a list")
        unknown = [r for r in required if r not in properties]
        if unknown:
            raise SkillError(
                f"a required field is not defined in girdi: {', '.join(map(str, unknown))}"
            )

        return Skill(
            name=name,
            description=str(spec["aciklama"]),
            path=path,
            command=self._command(path, module),
            run=run,
            schema={
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
            needs_approval=bool(spec.get("onay", False)),
        )

    def _command(self, path: Path, module: Any) -> Command | None:
        spec = getattr(module, "KOMUT", None)
        if spec is None:
            return None
        if not isinstance(spec, dict):
            raise SkillError("KOMUT must be a dict")
        missing = [k for k in ("ad", "aciklama", "talimat") if k not in spec]
        if missing:
            raise SkillError(f"missing field in KOMUT: {', '.join(missing)}")
        name = str(spec["ad"]).lstrip("/")
        if not COMMAND_RULE.match(name):
            raise SkillError(
                f"{name!r} is not a valid command name — it must start with a lower "
                f"case letter, then lower case/digits/underscore"
            )
        return Command(
            name=name,
            description=str(spec["aciklama"]),
            instruction=str(spec["talimat"]),
            path=path,
        )

    def expand(self, line: str) -> str | None:
        """`/rapor mart` -> komutun talimatı + kalan metin.

        Komut yoksa `None`; çağıran metni olduğu gibi ajana gönderiyor.
        Bilinmeyen bir `/kelime`yi hata sayıp reddetmek, eğik çizgiyle
        başlayan bir dosya yolunu yazmayı imkânsız kılardı.
        """
        if not line.startswith("/"):
            return None
        self.refresh()
        head, _, rest = line[1:].partition(" ")
        command = self.commands.get(head.strip())
        if command is None:
            return None
        rest = rest.strip()
        return f"{command.instruction}\n\n{rest}" if rest else command.instruction

    # --- yazma ------------------------------------------------------------

    def write(self, name: str, code: str) -> Skill:
        """Yeteneği yazar ve hemen yükler.

        Yükleme başarısız olursa dosya eski hâline dönüyor. Yarım bir yetenek
        bırakmak, ajanın bir sonraki turda kendi bozuk kodunu bulup
        şaşırmasına yol açar.
        """
        if not NAME_RULE.match(name):
            raise SkillError(
                f"{name!r} is not a valid file name — lower case, digits and underscore"
            )
        try:
            compile(code, f"<{name}>", "exec")
        except SyntaxError as exc:
            raise SkillError(
                f"syntax error on line {exc.lineno}: {exc.msg}"
            ) from None

        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{name}.py"
        previous = path.read_text(encoding="utf-8") if path.exists() else None
        path.write_text(code, encoding="utf-8")
        try:
            skill = self._load(path)
        except SkillError:
            if previous is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(previous, encoding="utf-8")
            self.refresh(force=True)
            raise
        self.refresh(force=True)
        return skill

    def read(self, name: str) -> str:
        path = self.directory / f"{name}.py"
        if not path.exists():
            raise SkillError(f"there is no skill called {name}")
        return path.read_text(encoding="utf-8")

    def remove(self, name: str) -> Path:
        path = self.directory / f"{name}.py"
        if not path.exists():
            raise SkillError(f"there is no skill called {name}")
        path.unlink()
        self.refresh(force=True)
        return path

    # --- okuma ------------------------------------------------------------

    def tools(self) -> list[dict[str, Any]]:
        self.refresh()
        return [skill.tool() for skill in self.skills.values()]

    def get(self, name: str) -> Skill | None:
        self.refresh()
        return self.skills.get(name)

    def report(self) -> str:
        self.refresh()
        lines: list[str] = []
        if self.skills:
            lines.append(f"{len(self.skills)} yetenek:")
            for skill in self.skills.values():
                onay = " [onay ister]" if skill.needs_approval else ""
                lines.append(f"  {skill.name}{onay} — {skill.description}")
        else:
            lines.append("No skills yet.")
        if self.commands:
            lines.append("")
            lines.append(f"{len(self.commands)} commands (the user calls them by typing /name):")
            for command in self.commands.values():
                lines.append(f"  /{command.name} — {command.description}")
        if self.broken:
            lines.append("")
            lines.append(f"{len(self.broken)} bozuk dosya:")
            for item in self.broken:
                lines.append(f"  {item.path.name}: {item.error}")
            lines.append("Fix or delete these; they did not load, so they cannot be called.")
        return "\n".join(lines)
