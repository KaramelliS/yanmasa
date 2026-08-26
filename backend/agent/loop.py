"""Ajan döngüsü.

SDK'nın `tool_runner`'ı yerine elle döngü var, çünkü üç şeye ihtiyacımız var
ve runner üçünü de vermiyor: bir partideki eylemlerin ilk hatada durması,
her adımda acil durdurma kontrolü, ve eski ekran görüntülerinin bağlamdan
budanması.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import anthropic

from .. import config
from ..computer.capture import ScreenCapture
from ..computer.displays import DisplayMap
from ..safety.killswitch import Aborted, KillSwitch
from .dispatch import Dispatcher, ToolError, ToolOutcome
from .prompts import build_system
from .tools import CUSTOM_TOOLS

COMPUTER_TOOLSET = "computer"

#: Bağlamda tutulacak ekran görüntüsü sayısı. Her kare ~1000-1800 token, ve
#: istek başına 20 görsel sınırı var. Model bir önceki birkaç adımı görsün
#: yeter — daha eskisi neredeyse hiç işe yaramıyor ama tokeni yiyor.
KEEP_IMAGES = 4

#: Budama eşiği. Her turda budamak prompt cache'ini her turda geçersiz kılar;
#: birikmesini bekleyip toplu budamak çok daha ucuz.
PRUNE_AT = 12

PRUNED_PLACEHOLDER = "[eski ekran görüntüsü bağlamdan çıkarıldı]"


@dataclass
class Turn:
    """Bir tur boyunca dışarıya bildirilenler — arayüz buraya bağlanacak."""

    on_text: Callable[[str], None] = lambda _t: None
    on_thinking: Callable[[str], None] = lambda _t: None
    on_action: Callable[[str, dict[str, Any]], None] = lambda _n, _i: None
    on_result: Callable[[str, ToolOutcome], None] = lambda _n, _o: None


#: Reddedilme mesajı. Computer-use çağrılarında Anthropic bir güvenlik
#: sınıflandırıcısı çalıştırıyor ve bu sınıflandırıcı **ekran görüntüsünün
#: içeriğine** de bakıyor. Ekranda doğrulama kodu, bankacılık ekranı ya da
#: kimlik bilgisi varken reddedilen şey çoğu zaman kullanıcının isteği değil,
#: karenin içeriği oluyor.
#:
#: Eski hâli yalnızca "Model bu isteği reddetti." diyordu: ne reddedildiğini,
#: neden reddedildiğini ve ne yapılacağını söylemiyor, üstelik modelin kendi
#: açıklamasını da çöpe atıyordu.
REFUSAL_HINT = (
    "İstek reddedildi. Bu genellikle senin yazdığın şeyle değil, o anda "
    "ekranda olanla ilgili: doğrulama kodu, bankacılık ekranı ya da şifre "
    "alanı görünen bir kare güvenlik denetimini tetikliyor.\n\n"
    "O pencereyi kapatıp ya da başka bir ekrana geçip tekrar dene."
)


def _refusal_text(model_text: str) -> str:
    """Modelin kendi açıklaması varsa o kaybolmuyor."""
    said = model_text.strip()
    return f"{said}\n\n{REFUSAL_HINT}" if said else REFUSAL_HINT


@dataclass
class Agent:
    displays: DisplayMap
    capture: ScreenCapture
    kill: KillSwitch
    client: anthropic.Anthropic
    approve: Callable[[str, str, str], bool] | None = None
    dispatcher: Dispatcher = field(init=False)
    messages: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.dispatcher = Dispatcher(
            self.displays, self.capture, self.kill, approve=self.approve
        )

    @classmethod
    def create(cls, cfg: config.Config, displays: DisplayMap, capture: ScreenCapture,
               kill: KillSwitch, approve=None) -> Agent:
        return cls(
            displays=displays,
            capture=capture,
            kill=kill,
            client=anthropic.Anthropic(api_key=cfg.anthropic_api_key),
            approve=approve,
        )

    @property
    def tools(self) -> list[dict[str, Any]]:
        """Araç listesi her model çağrısında yeniden kuruluyor.

        Sabit bir liste, ajanın az önce yazdığı yeteneği aynı turda
        çağırmasını imkânsız kılardı — yetenek ancak uygulama yeniden
        başlatılınca görünürdü ve "yaz, hemen dene" döngüsü kapanmazdı.

        Önbellek noktası yeteneklerden **önce**: yetenek listesi değiştiğinde
        computer araç setinin şeması yine önbellekten geliyor.
        """
        return [
            {
                "type": "computer_toolset_20260801",
                "cache_control": {"type": "ephemeral"},
            },
            *CUSTOM_TOOLS,
            *self.dispatcher.skills.tools(),
        ]

    def run(self, instruction: str, turn: Turn | None = None, max_steps: int = 60) -> str:
        """Bir talimatı ajan bitene kadar sürer. Son metni döndürür."""
        turn = turn or Turn()
        self.kill.reset()
        self.messages.append({"role": "user", "content": instruction})

        final_text = ""
        stuck = False
        for step in range(max_steps):
            self.kill.check()
            response = self._call_model(turn, effort=_effort_for(step, stuck))

            final_text = "".join(
                block.text for block in response.content if block.type == "text"
            )
            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "refusal":
                # Son ekran görüntüsünü geçmişten düşür. Kalırsa bir sonraki
                # istek de aynı kareyi taşıyor ve aynı yerde reddediliyor —
                # kullanıcı "neden hiçbir şey çalışmıyor" diye kalıyor.
                self._drop_last_images()
                return _refusal_text(final_text)
            if response.stop_reason != "tool_use":
                return final_text

            results = self._run_batch(response.content, turn)
            stuck = any(r.get("is_error") for r in results)
            self.messages.append({"role": "user", "content": results})
            self._prune_images()

        return final_text or f"{max_steps} adımda bitmedi, durdum."

    def _drop_last_images(self) -> None:
        """Geçmişteki görselleri metin yer tutucuyla değiştirir."""
        for message in self.messages:
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "image":
                    block.clear()
                    block.update({
                        "type": "text",
                        "text": "(ekran görüntüsü kaldırıldı)",
                    })

    # --- model çağrısı ----------------------------------------------------

    def _call_model(self, turn: Turn, effort: str = config.EFFORT):
        """Modeli akışla çağırır ve tam mesajı döndürür.

        Akış zorunlu: SDK, 10 dakikayı aşabilecek isteklerde bloke çağrıyı
        reddediyor ve yüksek `max_tokens` bu eşiği tetikliyor. İşe yarıyor
        da — metin ve düşünce özeti tur bitmeden görünüyor.
        """
        thinking_buffer: list[str] = []

        with self.client.messages.stream(
            model=config.MODEL,
            max_tokens=config.MAX_TOKENS,
            system=build_system(self.displays, self.dispatcher.active_index),
            tools=self.tools,
            messages=self.messages,
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": effort},
        ) as stream:
            for event in stream:
                if event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        turn.on_text(delta.text)
                    elif delta.type == "thinking_delta":
                        thinking_buffer.append(delta.thinking)
                elif event.type == "content_block_stop" and thinking_buffer:
                    # Düşünce parça parça geliyor; bloğu tamamlanınca tek
                    # seferde bildiriyoruz, yoksa arayüz kelime kelime titrer.
                    turn.on_thinking("".join(thinking_buffer))
                    thinking_buffer.clear()

            return stream.get_final_message()

    # --- araç partisi -----------------------------------------------------

    def _run_batch(self, content, turn: Turn) -> list[dict[str, Any]]:
        """Bir turdaki tüm araç çağrılarını sırayla çalıştırır.

        Model tek yanıtta birkaç eylem gönderebiliyor ("tıkla, yaz, görüntü
        al"). Bunlar birbirini varsayar: tıklama başarısızsa yazma yanlış
        yere gider. Bu yüzden ilk hatadan sonrakiler çalıştırılmıyor,
        modele de neden çalıştırılmadığı söyleniyor.
        """
        results: list[dict[str, Any]] = []
        failed = False

        for block in content:
            if block.type != "tool_use":
                continue

            payload = dict(block.input or {})
            if failed:
                results.append(
                    self._result_block(
                        block,
                        ToolOutcome(
                            content="Not executed: an earlier computer action "
                                    "in this turn failed.",
                            is_error=True,
                        ),
                    )
                )
                continue

            turn.on_action(block.name, payload)
            try:
                outcome = self.dispatcher.run(block.name, payload)
            except Aborted:
                raise
            except ToolError as exc:
                outcome = ToolOutcome(content=str(exc), is_error=True)
                failed = True
            except Exception as exc:  # beklenmeyen: modele söyle, çökme
                outcome = ToolOutcome(
                    content=f"{type(exc).__name__}: {exc}", is_error=True
                )
                failed = True

            turn.on_result(block.name, outcome)
            results.append(self._result_block(block, outcome))

        return results

    def _result_block(self, block, outcome: ToolOutcome) -> dict[str, Any]:
        result: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": outcome.content,
        }
        # Üye araçların sonucu hangi toolset'e ait olduğunu söylemek zorunda;
        # `switch_display` bizim kendi aracımız, onda bu alan olmamalı.
        toolset = getattr(block, "toolset_name", None)
        if toolset:
            result["toolset_name"] = toolset
        if outcome.is_error:
            result["is_error"] = True
        return result

    # --- bağlam -----------------------------------------------------------

    def _prune_images(self) -> None:
        """Eski ekran görüntülerini metin yer tutucusuyla değiştirir."""
        positions = [
            (mi, ci)
            for mi, message in enumerate(self.messages)
            for ci, block in enumerate(_blocks(message))
            if _is_image_result(block)
        ]
        if len(positions) <= PRUNE_AT:
            return

        for mi, ci in positions[:-KEEP_IMAGES]:
            self.messages[mi]["content"][ci]["content"] = PRUNED_PLACEHOLDER


def _blocks(message: dict[str, Any]) -> list[Any]:
    content = message.get("content")
    return content if isinstance(content, list) else []


def _is_image_result(block: Any) -> bool:
    return (
        isinstance(block, dict)
        and block.get("type") == "tool_result"
        and isinstance(block.get("content"), list)
        and any(
            isinstance(part, dict) and part.get("type") == "image"
            for part in block["content"]
        )
    )


def _effort_for(step: int, stuck: bool) -> str:
    """Adıma göre düşünme bütçesi.

    İlk adım pahalı olmalı: yaklaşımı orada seçiyor ve yanlış yaklaşım
    sonraki on adımı çöpe atıyor. Ondan sonrası çoğunlukla mekanik —
    "düğmeye tıkla, sonucu doğrula" — ve `medium` yetiyor.

    Bir eylem hata verdiyse ajan tıkanmış demektir; orada tekrar `high`e
    çıkıyoruz. Aynı hatayı `medium` ile tekrarlamak en pahalı yol.
    """
    if step == 0 or stuck:
        return "high"
    return "medium"
