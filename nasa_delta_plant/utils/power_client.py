"""Async client for the NASA POWER daily point API."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Sequence

import httpx

from nasa_delta_plant.config import Settings, get_settings


DEFAULT_POWER_PARAMETERS = (
    "T2M",
    "RH2M",
    "PS",
    "ALLSKY_SFC_SW_DWN",
    "PRECTOTCORR",
    "WS2M",
    "T2M_MAX",
    "T2M_MIN",
)


@dataclass(slots=True)
class PowerDay:
    day: date
    t2m: float
    rh2m: float
    ps: float
    allsky_sfc_sw_dwn: float
    prectotcorr: float
    ws2m: float
    t2m_max: float
    t2m_min: float
    et0: float
    water_stress_index: float
    gdd: float
    fungal_disease_risk_index: float

    def as_dict(self) -> dict:
        return {
            "day": self.day.isoformat(),
            "T2M": self.t2m,
            "RH2M": self.rh2m,
            "PS": self.ps,
            "ALLSKY_SFC_SW_DWN": self.allsky_sfc_sw_dwn,
            "PRECTOTCORR": self.prectotcorr,
            "WS2M": self.ws2m,
            "T2M_MAX": self.t2m_max,
            "T2M_MIN": self.t2m_min,
            "ET0": self.et0,
            "water_stress_index": self.water_stress_index,
            "GDD": self.gdd,
            "fungal_disease_risk_index": self.fungal_disease_risk_index,
        }


class NasaPowerClient:
    """Fetch and post-process NASA POWER daily agroclimatic data."""

    def __init__(self, settings: Settings | None = None, timeout: float = 60.0) -> None:
        self.settings = settings or get_settings()
        self.timeout = timeout

    async def fetch(
        self,
        latitude: float,
        longitude: float,
        start: date,
        end: date,
        parameters: Sequence[str] = DEFAULT_POWER_PARAMETERS,
        irrigation_mm_per_day: float = 0.0,
    ) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                self.settings.nasa_power_base_url,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "start": start.strftime("%Y%m%d"),
                    "end": end.strftime("%Y%m%d"),
                    "parameters": ",".join(parameters),
                    "community": "AG",
                    "format": "JSON",
                },
            )
            response.raise_for_status()
            payload = response.json()

        days = self._build_days(
            latitude=latitude,
            raw_parameters=payload.get("properties", {}).get("parameter", {}),
            irrigation_mm_per_day=irrigation_mm_per_day,
        )
        return self._build_response(latitude, longitude, start, end, payload, days)

    def _build_days(
        self,
        latitude: float,
        raw_parameters: dict,
        irrigation_mm_per_day: float,
    ) -> list[PowerDay]:
        all_days = sorted(set().union(*(values.keys() for values in raw_parameters.values())))
        results: list[PowerDay] = []
        cumulative_gdd = 0.0
        previous_fungal = 0.0

        for key in all_days:
            dt = datetime.strptime(key, "%Y%m%d").date()
            t2m = self._read_param(raw_parameters, "T2M", key)
            rh2m = self._read_param(raw_parameters, "RH2M", key)
            ps = self._read_param(raw_parameters, "PS", key)
            radiation = self._read_param(raw_parameters, "ALLSKY_SFC_SW_DWN", key)
            precipitation = self._read_param(raw_parameters, "PRECTOTCORR", key)
            wind = self._read_param(raw_parameters, "WS2M", key)
            tmax = self._read_param(raw_parameters, "T2M_MAX", key)
            tmin = self._read_param(raw_parameters, "T2M_MIN", key)

            et0 = self._compute_et0(
                latitude=latitude,
                day=dt,
                t_mean=t2m,
                t_max=tmax,
                t_min=tmin,
                rh_mean=rh2m,
                wind2m=wind,
                pressure_hpa=ps,
                solar_radiation_kwh=radiation,
            )
            available_water = max(precipitation + irrigation_mm_per_day, 0.0)
            water_stress_index = self._compute_water_stress(available_water, et0)
            daily_gdd = max((((tmax + tmin) / 2.0) - 10.0), 0.0)
            cumulative_gdd += daily_gdd
            fungal_risk = self._compute_fungal_risk(
                temperature=t2m,
                humidity=rh2m,
                precipitation=precipitation,
                previous_risk=previous_fungal,
            )
            previous_fungal = fungal_risk

            results.append(
                PowerDay(
                    day=dt,
                    t2m=t2m,
                    rh2m=rh2m,
                    ps=ps,
                    allsky_sfc_sw_dwn=radiation,
                    prectotcorr=precipitation,
                    ws2m=wind,
                    t2m_max=tmax,
                    t2m_min=tmin,
                    et0=round(et0, 3),
                    water_stress_index=round(water_stress_index, 3),
                    gdd=round(cumulative_gdd, 3),
                    fungal_disease_risk_index=round(fungal_risk, 3),
                )
            )

        return results

    @staticmethod
    def _read_param(raw_parameters: dict, key: str, day_key: str) -> float:
        value = raw_parameters.get(key, {}).get(day_key)
        if value in (None, -999.0, -999, "-999"):
            return 0.0
        return float(value)

    @staticmethod
    def _compute_water_stress(actual_water_supply: float, et0: float) -> float:
        demand = max(et0, 0.001)
        satisfaction_ratio = max(min(actual_water_supply / demand, 1.5), 0.0)
        stress = 1.0 - min(satisfaction_ratio, 1.0)
        return max(min(stress, 1.0), 0.0)

    @staticmethod
    def _compute_fungal_risk(
        temperature: float,
        humidity: float,
        precipitation: float,
        previous_risk: float,
    ) -> float:
        humidity_factor = 1.0 if humidity >= 80.0 else humidity / 80.0
        temp_centered = max(0.0, 1.0 - abs(temperature - 20.0) / 10.0)
        rain_factor = min(max(precipitation / 8.0, 0.0), 1.0)
        sustained = previous_risk * 0.45
        return max(min((0.5 * humidity_factor) + (0.35 * temp_centered) + (0.15 * rain_factor) + sustained, 1.0), 0.0)

    @staticmethod
    def _compute_et0(
        latitude: float,
        day: date,
        t_mean: float,
        t_max: float,
        t_min: float,
        rh_mean: float,
        wind2m: float,
        pressure_hpa: float,
        solar_radiation_kwh: float,
    ) -> float:
        phi = math.radians(latitude)
        doy = day.timetuple().tm_yday
        dr = 1.0 + 0.033 * math.cos((2.0 * math.pi / 365.0) * doy)
        solar_declination = 0.409 * math.sin(((2.0 * math.pi) / 365.0) * doy - 1.39)
        sunset_hour_angle = math.acos(max(min(-math.tan(phi) * math.tan(solar_declination), 1.0), -1.0))
        extraterrestrial_radiation = (
            (24.0 * 60.0 / math.pi)
            * 0.0820
            * dr
            * (
                (sunset_hour_angle * math.sin(phi) * math.sin(solar_declination))
                + (math.cos(phi) * math.cos(solar_declination) * math.sin(sunset_hour_angle))
            )
        )
        rs_mj = max(solar_radiation_kwh, 0.0) * 3.6
        rso = max((0.75 * extraterrestrial_radiation), 0.001)
        net_shortwave = (1.0 - 0.23) * rs_mj

        es_tmax = 0.6108 * math.exp((17.27 * t_max) / (t_max + 237.3))
        es_tmin = 0.6108 * math.exp((17.27 * t_min) / (t_min + 237.3))
        es = (es_tmax + es_tmin) / 2.0
        ea = max((rh_mean / 100.0) * es, 0.0)

        sigma = 4.903e-9
        tk_max = t_max + 273.16
        tk_min = t_min + 273.16
        cloudiness_ratio = min(max(rs_mj / rso, 0.0), 1.0)
        net_longwave = sigma * ((tk_max**4 + tk_min**4) / 2.0) * (0.34 - 0.14 * math.sqrt(max(ea, 0.0))) * (1.35 * cloudiness_ratio - 0.35)
        net_radiation = max(net_shortwave - net_longwave, 0.0)

        delta = 4098.0 * (0.6108 * math.exp((17.27 * t_mean) / (t_mean + 237.3))) / ((t_mean + 237.3) ** 2)
        pressure_kpa = pressure_hpa * 0.1
        gamma = 0.000665 * pressure_kpa
        numerator = (0.408 * delta * net_radiation) + (gamma * (900.0 / (t_mean + 273.0)) * wind2m * (es - ea))
        denominator = delta + (gamma * (1.0 + (0.34 * wind2m)))
        return max(numerator / max(denominator, 0.001), 0.0)

    @staticmethod
    def _build_response(
        latitude: float,
        longitude: float,
        start: date,
        end: date,
        payload: dict,
        days: Iterable[PowerDay],
    ) -> dict:
        day_list = list(days)
        if day_list:
            et0_values = [day.et0 for day in day_list]
            stress_values = [day.water_stress_index for day in day_list]
            fungal_values = [day.fungal_disease_risk_index for day in day_list]
            summary = {
                "et0_total": round(sum(et0_values), 3),
                "et0_mean": round(sum(et0_values) / len(et0_values), 3),
                "water_stress_mean": round(sum(stress_values) / len(stress_values), 3),
                "water_stress_peak": round(max(stress_values), 3),
                "gdd_total": round(day_list[-1].gdd, 3),
                "fungal_risk_mean": round(sum(fungal_values) / len(fungal_values), 3),
                "fungal_risk_peak": round(max(fungal_values), 3),
                "high_fungal_risk_days": sum(1 for value in fungal_values if value >= 0.7),
            }
        else:
            summary = {
                "et0_total": 0.0,
                "et0_mean": 0.0,
                "water_stress_mean": 0.0,
                "water_stress_peak": 0.0,
                "gdd_total": 0.0,
                "fungal_risk_mean": 0.0,
                "fungal_risk_peak": 0.0,
                "high_fungal_risk_days": 0,
            }

        return {
            "source": "NASA POWER",
            "latitude": latitude,
            "longitude": longitude,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "community": payload.get("header", {}).get("title", "AG"),
            "raw": payload,
            "daily": [day.as_dict() for day in day_list],
            "summary": summary,
        }
