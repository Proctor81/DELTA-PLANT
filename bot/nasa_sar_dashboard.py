import io
import logging
import os
from datetime import date as date_type

from PIL import Image, ImageDraw
import numpy as np
from PIL import ImageFont
def generate_dashboard_report_image(dashboard: dict, lat: float, lon: float, size: int = 700) -> Image.Image:
    """
    Genera un report grafico professionale NASA-ISRO/SAR Dashboard con tabella dati settimanali e barra rischio.
    """
    img = Image.new("RGB", (size, size), (18, 24, 38))
    draw = ImageDraw.Draw(img)
    # Titolo
    title = "NASA-ISRO/SAR Dashboard"
    font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 32) if hasattr(ImageFont, 'truetype') else ImageFont.load_default()
    font_header = ImageFont.truetype("DejaVuSans-Bold.ttf", 18) if hasattr(ImageFont, 'truetype') else ImageFont.load_default()
    font = ImageFont.truetype("DejaVuSans.ttf", 16) if hasattr(ImageFont, 'truetype') else ImageFont.load_default()
    draw.text((20, 18), title, fill=(25,245,193), font=font_title)

    # Barra rischio settimanale
    bar_x, bar_y, bar_w, bar_h = 20, 80, 420, 32
    draw.rectangle([bar_x, bar_y, bar_x+bar_w, bar_y+bar_h], outline=(121,231,255), width=2)
    fill_w = int(bar_w * dashboard["weekly_risk"])
    draw.rectangle([bar_x, bar_y, bar_x+fill_w, bar_y+bar_h], fill=(255,90,90,180))
    draw.text((bar_x+bar_w+16, bar_y+4), f"Rischio medio settimanale: {dashboard['weekly_risk']:.2f} ({dashboard['weekly_label']})", fill=(255,255,255), font=font_header)

    # Tabella dati
    headers = ["Data", "Soil", "Temp", "Humidity", "Rain", "Risk"]
    col_x = [20, 120, 200, 280, 380, 460]
    y0 = 140
    for i, h in enumerate(headers):
        draw.text((col_x[i], y0), h, fill=(121,231,255), font=font_header)
    for idx, d in enumerate(dashboard["dashboard"]):
        y = y0 + 28 + idx * 28
        draw.text((col_x[0], y), d["date"], fill=(255,255,255), font=font)
        draw.text((col_x[1], y), f"{d['soil']:.1f}", fill=(200,255,200), font=font)
        draw.text((col_x[2], y), f"{d['temp']:.1f}", fill=(255,255,200), font=font)
        draw.text((col_x[3], y), f"{d['humidity']}", fill=(200,200,255), font=font)
        draw.text((col_x[4], y), f"{d['rain']:.1f}", fill=(200,255,255), font=font)
        draw.text((col_x[5], y), f"{d['risk']:.2f}", fill=(255,180,180), font=font)

    # Dati di sintesi
    synth = f"Lat: {lat:.5f}, Lon: {lon:.5f}"
    draw.text((20, size-40), synth, fill=(121,231,255), font=font)
    return img
import requests


def _fallback_satellite_image(lat: float, lon: float, radius_m: int = 50, size: int = 512) -> Image.Image:
    img = Image.new("RGBA", (size, size), (18, 24, 38, 255))
    draw = ImageDraw.Draw(img)
    center = (size // 2, size // 2)
    radius_px = max(size // 10, 18)
    grid_color = (43, 60, 83, 255)

    for step in range(0, size, 64):
        draw.line([(step, 0), (step, size)], fill=grid_color, width=1)
        draw.line([(0, step), (size, step)], fill=grid_color, width=1)

    draw.ellipse(
        [
            center[0] - radius_px,
            center[1] - radius_px,
            center[0] + radius_px,
            center[1] + radius_px,
        ],
        outline=(255, 90, 90, 255),
        width=3,
    )
    cross_len = 16
    draw.line([center[0] - cross_len, center[1], center[0] + cross_len, center[1]], fill=(255, 90, 90, 255), width=2)
    draw.line([center[0], center[1] - cross_len, center[0], center[1] + cross_len], fill=(255, 90, 90, 255), width=2)
    font = ImageFont.truetype("DejaVuSans.ttf", 18) if hasattr(ImageFont, "truetype") else ImageFont.load_default()
    draw.text((20, 18), "GPS fallback map", fill=(121, 231, 255, 255), font=font)
    draw.text((20, 44), f"Lat {lat:.5f} | Lon {lon:.5f}", fill=(220, 230, 240, 255), font=font)
    draw.text((20, 70), f"Area radius {radius_m} m", fill=(220, 230, 240, 255), font=font)
    return img


def get_satellite_image_with_marker(lat: float, lon: float, radius_m: int = 50, zoom: int = 18, size: int = 512) -> Image.Image:
    """
    Scarica un'immagine satellitare centrata su lat/lon e disegna un mirino + cerchio di raggio specificato.
    Usa Mapbox Static API se e presente un token ambiente; altrimenti genera un fallback locale.
    """
    access_token = (os.getenv("DELTA_MAPBOX_ACCESS_TOKEN") or os.getenv("MAPBOX_ACCESS_TOKEN") or "").strip()
    if not access_token:
        logging.warning("NASA/SAR map fallback: token Mapbox non configurato, uso placeholder locale")
        return _fallback_satellite_image(lat, lon, radius_m=radius_m, size=size)

    url = (
        f"https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/"
        f"pin-s+ff0000({lon},{lat})/{lon},{lat},{zoom},0/{size}x{size}?access_token={access_token}"
    )
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        img = Image.open(io.BytesIO(response.content)).convert("RGBA")
        draw = ImageDraw.Draw(img)
        center = (size // 2, size // 2)
        meters_per_pixel = 156543.03392 * abs(np.cos(np.radians(lat))) / (2 ** zoom)
        radius_px = max(int(radius_m / meters_per_pixel), 12)
        draw.ellipse([
            center[0] - radius_px, center[1] - radius_px,
            center[0] + radius_px, center[1] + radius_px
        ], outline="red", width=3)
        cross_len = 16
        draw.line([center[0] - cross_len, center[1], center[0] + cross_len, center[1]], fill="red", width=2)
        draw.line([center[0], center[1] - cross_len, center[0], center[1] + cross_len], fill="red", width=2)
        return img
    except Exception as exc:
        logging.warning("NASA/SAR map fallback: download mappa satellite fallito (%s), uso placeholder locale", exc)
        return _fallback_satellite_image(lat, lon, radius_m=radius_m, size=size)
import datetime
from typing import Dict, Any, List, Optional
from nasa_delta_plant.utils.power_client import compute_fungal_risk_score


NASA_SOIL_PARAMETERS = ("GWETROOT", "GWETTOP")


def _normalize_power_soil_value(raw_value: Any) -> Optional[float]:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    if value <= -900.0:
        return None
    if 0.0 <= value <= 1.0:
        return round(value * 100.0, 3)
    return round(value, 3)


def _power_day_to_iso(raw_day: Any) -> str:
    text = str(raw_day or "").strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text


def _fill_missing_values(values: List[Optional[float]], fallback: float = 50.0) -> List[float]:
    if not values:
        return []

    filled = list(values)
    last_seen: Optional[float] = None
    for index, value in enumerate(filled):
        if value is None:
            if last_seen is not None:
                filled[index] = last_seen
            continue
        last_seen = value

    next_seen: Optional[float] = None
    for index in range(len(filled) - 1, -1, -1):
        value = filled[index]
        if value is None:
            if next_seen is not None:
                filled[index] = next_seen
            continue
        next_seen = value

    return [round(float(value if value is not None else fallback), 3) for value in filled]


def _align_soil_values(dates: List[str], soil_series: List[Dict[str, Any]]) -> List[float]:
    soil_by_date = {
        str(item.get("date") or ""): _normalize_power_soil_value(item.get("soil"))
        for item in soil_series
        if item.get("date")
    }
    ordered = [soil_by_date.get(day) for day in dates]
    valid = [value for value in ordered if value is not None]
    fallback = round(sum(valid) / len(valid), 3) if valid else 50.0
    return _fill_missing_values(ordered, fallback=fallback)

def fetch_nasa_soil(lat: float, lon: float, start: datetime.date, end: datetime.date) -> List[float]:
    """Restituisce una serie giornaliera di soil moisture proxy da NASA POWER."""
    # NASA POWER API: https://power.larc.nasa.gov/api/temporal/daily/point
    url = (
        f"https://power.larc.nasa.gov/api/temporal/daily/point?parameters={','.join(NASA_SOIL_PARAMETERS)}&community=AG&longitude={lon}&latitude={lat}&start={start.strftime('%Y%m%d')}&end={end.strftime('%Y%m%d')}&format=JSON"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        parameters = ((data or {}).get("properties") or {}).get("parameter") or {}
        root_values = parameters.get("GWETROOT", {}) or {}
        top_values = parameters.get("GWETTOP", {}) or {}
        days = sorted(set(root_values.keys()) | set(top_values.keys()))
        soil_series: List[Dict[str, Any]] = []
        for raw_day in days:
            root_value = _normalize_power_soil_value(root_values.get(raw_day))
            top_value = _normalize_power_soil_value(top_values.get(raw_day))
            samples = [value for value in (root_value, top_value) if value is not None]
            soil_series.append(
                {
                    "date": _power_day_to_iso(raw_day),
                    "soil": round(sum(samples) / len(samples), 3) if samples else None,
                }
            )
        return soil_series
    except Exception as exc:
        import logging
        logging.error(f"[NASA_SOIL_FETCH_ERROR] {exc}")
        raise RuntimeError(f"Errore fetch NASA SOIL: {exc}")

def fetch_openmeteo_weather(lat: float, lon: float, start: datetime.date, end: datetime.date) -> List[Dict[str, Any]]:
    """Restituisce una lista di dict con Temp, Humidity, Rain (Open-Meteo Archive API, daily)."""
    url = (
        f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={start.isoformat()}&end_date={end.isoformat()}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,relative_humidity_2m_max,relative_humidity_2m_min&timezone=auto"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()["daily"]
        n = len(data["temperature_2m_max"])
        result = []
        for i in range(n):
            temp = (data["temperature_2m_max"][i] + data["temperature_2m_min"][i]) / 2.0
            humidity = (data["relative_humidity_2m_max"][i] + data["relative_humidity_2m_min"][i]) / 2.0
            rain = data["precipitation_sum"][i]
            result.append(
                {
                    "date": data["time"][i],
                    "temp": round(temp, 3),
                    "humidity": round(humidity, 3),
                    "rain": round(float(rain), 3),
                }
            )
        return result
    except Exception as exc:
        import logging
        logging.error(f"[OPENMETEO_FETCH_ERROR] {exc}")
        raise RuntimeError(f"Errore fetch Open-Meteo: {exc}")

def risk_label(average_risk: float, peak_risk: float, high_risk_days: int) -> str:
    if peak_risk >= 0.86 or high_risk_days >= 4 or average_risk >= 0.74:
        return "ALTO"
    if peak_risk >= 0.66 or high_risk_days >= 2 or average_risk >= 0.52:
        return "MEDIO"
    return "BASSO"

def generate_dashboard(
    lat: float,
    lon: float,
    start: Optional[date_type] = None,
    end: Optional[date_type] = None,
) -> Dict[str, Any]:
    import logging
    try:
        today = datetime.date.today()
        end = end or today
        start = start or (end - datetime.timedelta(days=6))
        days = [(start + datetime.timedelta(days=i)) for i in range(((end - start).days) + 1)]
        warnings: List[str] = []

        try:
            soil_series = fetch_nasa_soil(lat, lon, start, end)
        except Exception as exc:
            logging.error(f"[DASHBOARD_GENERATION_ERROR] Errore fetch_nasa_soil: {exc}")
            warnings.append(str(exc))
            soil_series = []
        try:
            weather_vals = fetch_openmeteo_weather(lat, lon, start, end)
        except Exception as exc:
            logging.error(f"[DASHBOARD_GENERATION_ERROR] Errore fetch_openmeteo_weather: {exc}")
            warnings.append(str(exc))
            weather_vals = []

        if not weather_vals:
            raise RuntimeError("Open-Meteo non ha restituito dati giornalieri utili")

        weather_vals = sorted(weather_vals, key=lambda item: str(item.get("date") or ""))
        weather_dates = [str(item.get("date") or "") for item in weather_vals]
        soil_vals = _align_soil_values(weather_dates, soil_series)

        daily = []
        prev_risk = 0.0
        for i, weather_day in enumerate(weather_vals):
            soil = soil_vals[i] if i < len(soil_vals) else 50.0
            temp = weather_vals[i]["temp"]
            humidity = weather_vals[i]["humidity"]
            rain = weather_vals[i]["rain"]
            risk = compute_fungal_risk_score(temp, humidity, rain, prev_risk)
            prev_risk = risk
            daily.append({
                "date": str(weather_day.get("date") or days[i].isoformat()),
                "soil": round(float(soil), 3),
                "temp": round(float(temp), 3),
                "humidity": round(float(humidity), 3),
                "rain": round(float(rain), 3),
                "risk": round(risk, 3)
            })
        values = [d["risk"] for d in daily]
        average_risk = sum(values) / len(values)
        peak_risk = max(values)
        high_risk_days = sum(1 for v in values if v >= 0.75)
        weekly_label = risk_label(average_risk, peak_risk, high_risk_days)

        dashboard = {
            "dashboard": daily,
            "weekly_risk": round(average_risk, 3),
            "weekly_label": weekly_label,
            "summary": {
                "sar_soil_moisture_percent": round(float(daily[-1]["soil"]), 3) if daily else 0.0,
                "sar_source": "NASA POWER GWETROOT/GWETTOP soil proxy",
                "sar_product_name": None,
                "sar_acquired_at": daily[-1]["date"] if daily else None,
                "weather_window_start": daily[0]["date"] if daily else start.isoformat(),
                "weather_window_end": daily[-1]["date"] if daily else end.isoformat(),
                "weather_source": "Open-Meteo Archive",
            },
        }
        if warnings:
            dashboard["warnings"] = warnings
        return dashboard
    except Exception as exc:
        logging.error(f"[DASHBOARD_GENERATION_ERROR] {exc}")
        # Fallback di emergenza: dati statici
        daily = []
        today = datetime.date.today()
        for i in range(7):
            day = (today - datetime.timedelta(days=6-i)).isoformat()
            daily.append({
                "date": day,
                "soil": 50.0,
                "temp": 22.0,
                "humidity": 60.0,
                "rain": 2.0,
                "risk": 0.5
            })
        return {
            "dashboard": daily,
            "weekly_risk": 0.5,
            "weekly_label": "LOW",
            "error": str(exc)
        }
