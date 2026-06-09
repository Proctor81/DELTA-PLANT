import asyncio
import sys
import types
from pathlib import Path


def test_handle_message_sends_async_nasa_photo_from_running_loop(monkeypatch, tmp_path):
    import bot.deltaplano_bot as deltaplano
    import bot.nasa_sar_dashboard as nasa_dashboard
    import tempfile

    class FakeChatEngine:
        pass

    class FakeMobileNetService:
        pass

    class FakeImage:
        def save(self, path):
            Path(path).write_bytes(b"fake-dashboard")

    class FakeOrchestrator:
        async def analyze_nasa_only(self, geo_data, date_range):
            return {
                "dashboard": {
                    "dashboard": [
                        {
                            "date": "2026-05-19",
                            "soil": 12.3,
                            "temp": 23.4,
                            "humidity": 78,
                            "rain": 4.5,
                            "risk": 0.62,
                        }
                    ],
                    "weekly_risk": 0.62,
                    "weekly_label": "MEDIO",
                }
            }

    class FakeTelegramBot:
        def __init__(self):
            self.calls = []

        async def send_photo(self, chat_id, photo, caption=None):
            self.calls.append((chat_id, caption))

    fake_orchestrator_module = types.ModuleType("nasa_delta_plant.orchestrator_node")
    fake_orchestrator_module.NASADeltaPlantOrchestrator = FakeOrchestrator
    monkeypatch.setitem(sys.modules, "nasa_delta_plant.orchestrator_node", fake_orchestrator_module)
    monkeypatch.setattr(deltaplano, "ChatEngine", FakeChatEngine)
    monkeypatch.setattr(deltaplano, "MobileNetService", FakeMobileNetService)
    monkeypatch.setattr(nasa_dashboard, "generate_dashboard_report_image", lambda dashboard, lat, lon, **kwargs: FakeImage())
    monkeypatch.setattr(tempfile, "mktemp", lambda **kwargs: str(tmp_path / "nasa_deltaplano.png"))

    bot = deltaplano.DELTAPLANOBot()
    telegram_bot = FakeTelegramBot()

    async def _invoke():
        return bot.handle_message(
            user_id=7,
            text="dashboard",
            telegram_bot=telegram_bot,
            chat_id=12345,
        )

    result = asyncio.run(_invoke())

    assert result == "[Immagine dashboard inviata su Telegram]"
    assert telegram_bot.calls == [
        (12345, "\U0001F30E NASA-ISRO/SAR Dashboard\n\nData | Suolo | Temp | Umidita' | Pioggia | Rischio\n2026-05-19 | 12.3 | 23.4 | 78 | 4.5 | 0.62\n\nRischio settimanale: 0.62 (MEDIO)\nRischio medio settimanale 0.62. La persistenza dell'umidita' e il supporto del meteo ufficiale indicano una pressione fungina media nel raggio di 50 metri.")
    ]


def test_handle_message_localizes_nasa_report_to_english(monkeypatch, tmp_path):
    import bot.deltaplano_bot as deltaplano
    import bot.nasa_sar_dashboard as nasa_dashboard
    import tempfile

    class FakeChatEngine:
        pass

    class FakeMobileNetService:
        pass

    class FakeImage:
        def save(self, path):
            Path(path).write_bytes(b"fake-dashboard")

    class FakeOrchestrator:
        async def analyze_nasa_only(self, geo_data, date_range):
            return {
                "dashboard": {
                    "dashboard": [
                        {
                            "date": "2026-05-19",
                            "soil": 12.3,
                            "temp": 23.4,
                            "humidity": 78,
                            "rain": 4.5,
                            "risk": 0.62,
                        }
                    ],
                    "weekly_risk": 0.62,
                    "weekly_label": "MEDIO",
                }
            }

    class FakeTelegramBot:
        def __init__(self):
            self.calls = []

        async def send_photo(self, chat_id, photo, caption=None):
            self.calls.append((chat_id, caption))

    fake_orchestrator_module = types.ModuleType("nasa_delta_plant.orchestrator_node")
    fake_orchestrator_module.NASADeltaPlantOrchestrator = FakeOrchestrator
    monkeypatch.setitem(sys.modules, "nasa_delta_plant.orchestrator_node", fake_orchestrator_module)
    monkeypatch.setattr(deltaplano, "ChatEngine", FakeChatEngine)
    monkeypatch.setattr(deltaplano, "MobileNetService", FakeMobileNetService)
    monkeypatch.setattr(nasa_dashboard, "generate_dashboard_report_image", lambda dashboard, lat, lon, **kwargs: FakeImage())
    monkeypatch.setattr(tempfile, "mktemp", lambda **kwargs: str(tmp_path / "nasa_deltaplano_en.png"))

    bot = deltaplano.DELTAPLANOBot()
    telegram_bot = FakeTelegramBot()

    async def _invoke():
        return bot.handle_message(
            user_id=7,
            text="dashboard",
            telegram_bot=telegram_bot,
            chat_id=12345,
            response_language="en",
        )

    result = asyncio.run(_invoke())

    assert result == "[Dashboard image sent on Telegram]"
    assert telegram_bot.calls == [
        (12345, "\U0001F30E NASA-ISRO/SAR Dashboard\n\nDate | Soil | Temp | Humidity | Rain | Risk\n2026-05-19 | 12.3 | 23.4 | 78 | 4.5 | 0.62\n\nWeekly risk: 0.62 (MEDIUM)\nWeekly mean risk 0.62. Moisture persistence and official weather support indicate a medium fungal pressure around this 50 m radius.")
    ]