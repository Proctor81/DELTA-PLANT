import io
import logging
import os

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
from typing import Dict, Any, List
import requests
from nasa_delta_plant.utils.power_client import compute_fungal_risk_score

def fetch_nasa_soil(lat: float, lon: float, start: datetime.date, end: datetime.date) -> List[float]:
    """Restituisce una lista di valori Soil (NASA POWER API, daily, mm)."""
    # NASA POWER API: https://power.larc.nasa.gov/api/temporal/daily/point
    url = (
        f"https://power.larc.nasa.gov/api/temporal/daily/point?parameters=SOILWATER_10CM&community=AG&longitude={lon}&latitude={lat}&start={start.strftime('%Y%m%d')}&end={end.strftime('%Y%m%d')}&format=JSON"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        vals = data["properties"]["parameter"]["SOILWATER_10CM"]
        # Ordina per data crescente
        return [vals[k] for k in sorted(vals.keys())]
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
            result.append({"temp": temp, "humidity": humidity, "rain": rain})
        return result
    except Exception as exc:
        import logging
        logging.error(f"[OPENMETEO_FETCH_ERROR] {exc}")
        raise RuntimeError(f"Errore fetch Open-Meteo: {exc}")

def risk_label(score: float) -> str:
    # HERO DEMO: HIGH, MEDIUM, LOW
    if score >= 0.74:
        return "HIGH"
    elif score >= 0.52:
        return "MEDIUM"
    else:
        return "LOW"

def generate_dashboard(lat: float, lon: float) -> Dict[str, Any]:
    import logging
    try:
        today = datetime.date.today()
        days = [(today - datetime.timedelta(days=i)) for i in range(6, -1, -1)]
        end = today
        start = days[0]
        try:
            soil_vals = fetch_nasa_soil(lat, lon, start, end)
        except Exception as exc:
            logging.error(f"[DASHBOARD_GENERATION_ERROR] Errore fetch_nasa_soil: {exc}")
            soil_vals = [50.0] * 7
        try:
            weather_vals = fetch_openmeteo_weather(lat, lon, start, end)
        except Exception as exc:
            logging.error(f"[DASHBOARD_GENERATION_ERROR] Errore fetch_openmeteo_weather: {exc}")
            weather_vals = [{"temp": 22.0, "humidity": 60.0, "rain": 2.0}] * 7
        # Fallback se dati incompleti
        if len(soil_vals) < 7:
            soil_vals = (list(soil_vals) + [50.0] * 7)[:7]
        if len(weather_vals) < 7:
            weather_vals = (list(weather_vals) + [{"temp": 22.0, "humidity": 60.0, "rain": 2.0}] * 7)[:7]
        daily = []
        prev_risk = 0.0
        for i in range(7):
            soil = soil_vals[i]
            temp = weather_vals[i]["temp"]
            humidity = weather_vals[i]["humidity"]
            rain = weather_vals[i]["rain"]
            risk = compute_fungal_risk_score(temp, humidity, rain, prev_risk)
            prev_risk = risk
            daily.append({
                "date": days[i].isoformat(),
                "soil": soil,
                "temp": temp,
                "humidity": humidity,
                "rain": rain,
                "risk": round(risk, 3)
            })
        values = [d["risk"] for d in daily]
        average_risk = sum(values) / 7.0
        peak_risk = max(values)
        high_risk_days = sum(1 for v in values if v >= 0.75)
        # HERO DEMO: classificazione
        if peak_risk >= 0.86 or high_risk_days >= 4 or average_risk >= 0.74:
            weekly_label = "HIGH"
        elif peak_risk >= 0.66 or high_risk_days >= 2 or average_risk >= 0.52:
            weekly_label = "MEDIUM"
        else:
            weekly_label = "LOW"
        return {
            "dashboard": daily,
            "weekly_risk": round(average_risk, 3),
            "weekly_label": weekly_label
        }
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
