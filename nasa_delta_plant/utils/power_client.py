from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Sequence

import httpx

from nasa_delta_plant.config import Settings, get_settings


DEFAULT_POWER_PARAMETERS = (
    "T2M",
    "RH2M",
    "PRECTOTCORR",
)

def compute_fungal_risk_score(temperature: float, humidity: float, precipitation: float, previous_risk: float) -> float:
    """Funzione pubblica per compatibilità bot Telegram. Calcola il rischio fungino giornaliero (score normalizzato 0-1)."""
    return NasaPowerClient._compute_fungal_risk(temperature, humidity, precipitation, previous_risk)

@dataclass(frozen=True)
class PowerPoint:
    """Representation of a NASA POWER daily point record."""
    date: date
    temperature: float
    humidity: float
    precipitation: float
    fungal_risk: float


class NasaPowerClient:
    """Client for the NASA POWER daily point API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def fetch(
        self,
        latitude: float,
        longitude: float,
        start: date,
        end: date,
    ) -> dict:
        """Fetch and post-process daily weather data from Open Meteo Archive for orchestrator pipeline (allineato a demo HERO)."""
        import requests
        url = (
            f"https://archive-api.open-meteo.com/v1/archive?latitude={latitude}&longitude={longitude}"
            f"&start_date={start.isoformat()}&end_date={end.isoformat()}"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,relative_humidity_2m_max,relative_humidity_2m_min&timezone=auto"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()["daily"]
        n = len(data["temperature_2m_max"])
        results = []
        previous_risk = 0.0
        for i in range(n):
            d = start + timedelta(days=i)
            temp = (data["temperature_2m_max"][i] + data["temperature_2m_min"][i]) / 2.0
            humidity = (data["relative_humidity_2m_max"][i] + data["relative_humidity_2m_min"][i]) / 2.0
            precipitation = data["precipitation_sum"][i]
            fungal_risk = self._compute_fungal_risk(temp, humidity, precipitation, previous_risk)
            previous_risk = fungal_risk
            results.append({
                "day": d.isoformat(),
                "T2M": temp,
                "RH2M": humidity,
                "PRECTOTCORR": precipitation,
                "fungal_risk": fungal_risk,
            })
        return {"daily": results}

    async def get_daily_point(self, latitude: float, longitude: float) -> PowerPoint:
        """Fetch daily point for a given location."""
        # Simulated API call logic
        return PowerPoint(
            date=date.today(),
            temperature=20.0,
            humidity=60.0,
            precipitation=0.0,
            fungal_risk=0.1
        )

    @staticmethod
    def _compute_fungal_risk(temperature: float, humidity: float, precipitation: float, previous_risk: float) -> float:
        """
        Formula HERO DEMO:
        humidityFactor = clamp((humidity - 60) / 40, 0, 1)
        tempCentered = clamp((temperature - 12) / 18, 0, 1)
        rainFactor = clamp(precipitation / 14, 0, 1)
        sustained = previous_risk * 0.05
        risk = clamp(0.4 * humidityFactor + 0.35 * tempCentered + 0.25 * rainFactor + sustained, 0, 1)
        """
        def clamp(val, minv, maxv):
            return max(minv, min(maxv, val))
        humidity_factor = clamp((humidity - 60) / 40, 0, 1)
        temp_centered = clamp((temperature - 12) / 18, 0, 1)
        rain_factor = clamp(precipitation / 14, 0, 1)
        sustained = previous_risk * 0.05
        risk = 0.4 * humidity_factor + 0.35 * temp_centered + 0.25 * rain_factor + sustained
        return clamp(risk, 0, 1)
