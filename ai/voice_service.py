from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from chat.chat_engine import ChatEngine
from interface.telegram_bot import _prepare_telegram_voice_payload, text_to_speech_warm_male


class _SyntheticTelegramContext:
    def __init__(self) -> None:
        self.application = SimpleNamespace(bot_data={})
        self.user_data: dict[str, object] = {}


class VoiceService:
    def __init__(self, chat_engine: ChatEngine | None = None) -> None:
        self.chat_engine = chat_engine

    async def synthesize(self, text: str, language: str = "it", output_format: str = "ogg") -> tuple[bytes, str, str]:
        text_for_voice = await self._prepare_text(text, language)
        context = _SyntheticTelegramContext()
        audio = await text_to_speech_warm_male(context, text_for_voice)
        if output_format.lower() == "ogg":
            audio = await _prepare_telegram_voice_payload(audio)
            return audio.getvalue(), "audio/ogg", "voice.ogg"
        return audio.getvalue(), self._content_type(audio), Path(getattr(audio, "name", "voice.wav")).name or "voice.wav"

    async def _prepare_text(self, text: str, language: str) -> str:
        if language.lower() != "en" or self.chat_engine is None:
            return text
        translation = await asyncio.to_thread(
            self.chat_engine.chat_internal,
            f"Translate this agronomic message to concise English without adding new facts:\n\n{text}",
        )
        return translation.strip() or text

    @staticmethod
    def _content_type(audio: BytesIO) -> str:
        suffix = Path(getattr(audio, "name", "voice.wav")).suffix.lower()
        if suffix == ".mp3":
            return "audio/mpeg"
        if suffix == ".ogg":
            return "audio/ogg"
        return "audio/wav"
