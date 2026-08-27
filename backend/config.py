"""Ayarlar — `.env` dosyasından, ortamdan yedekle.

Anahtarlar yalnızca burada okunur. Başka hiçbir modül `os.environ`'a
dokunmuyor ki bir anahtarın nereden geldiği tek yerden görülebilsin.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

MODEL = "claude-opus-5"
MAX_TOKENS = 32000
EFFORT = "high"


@dataclass
class Config:
    anthropic_api_key: str
    elevenlabs_keys: list[str] = field(default_factory=list)
    elevenlabs_voice_id: str = ""
    elevenlabs_model: str = "eleven_flash_v2_5"
    tts_backend: str = "elevenlabs"
    stt_model: str = "small"
    stt_language: str = "tr"
    #: Uzak makine panelinin ön dolduracağı varsayılanlar. Depoda gerçek
    #: bir adres durmasın diye: bir IP, kullanıcı adı ve SSH portu tek
    #: başına parola değil ama "şu adreste root, şu portta" demek, kaba
    #: kuvvet denemesi için hazır bir hedef listesi vermek demek.
    ssh_alias: str = ""
    ssh_host: str = ""
    ssh_user: str = "root"
    ssh_port: int = 22

    @classmethod
    def load(cls) -> Config:
        load_dotenv(REPO_ROOT / ".env")

        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY yok. `.env.example`'ı `.env` olarak kopyalayıp "
                "doldur ya da ortam değişkeni olarak ver."
            )

        raw_keys = os.environ.get("ELEVENLABS_KEYS", "")
        return cls(
            anthropic_api_key=key,
            elevenlabs_keys=[k.strip() for k in raw_keys.split(",") if k.strip()],
            elevenlabs_voice_id=os.environ.get("ELEVENLABS_VOICE_ID", "").strip(),
            elevenlabs_model=os.environ.get("ELEVENLABS_MODEL", "eleven_flash_v2_5"),
            tts_backend=os.environ.get("TTS_BACKEND", "elevenlabs"),
            stt_model=os.environ.get("STT_MODEL", "small"),
            stt_language=os.environ.get("STT_LANGUAGE", "tr"),
            ssh_alias=os.environ.get("SSH_ALIAS", "").strip(),
            ssh_host=os.environ.get("SSH_HOST", "").strip(),
            ssh_user=os.environ.get("SSH_USER", "root").strip(),
            ssh_port=int(os.environ.get("SSH_PORT", "22") or 22),
        )
