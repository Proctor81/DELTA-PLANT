import datetime
from typing import Dict, Any, List

# MOCK: da sostituire con fetch reali

def fetch_nasa_soil(lat: float, lon: float, start: datetime.date, end: datetime.date) -> List[float]:
    """Restituisce una lista di valori Soil (mock)."""
    return [32.1, 33.0, 34.2, 35.1, 34.8, 33.7, 32.9]

def fetch_openmeteo_weather(lat: float, lon: float, start: datetime.date, end: datetime.date) -> List[Dict[str, Any]]:
    """Restituisce una lista di dict con Temp, Humidity, Rain (mock)."""
    return [
        {"temp": 21.2, "humidity": 68, "rain": 2.1},
        {"temp": 22.0, "humidity": 70, "rain": 0.0},
        {"temp": 23.1, "humidity": 72, "rain": 0.5},
        {"temp": 24.0, "humidity": 74, "rain": 1.2},
        {"temp": 23.5, "humidity": 73, "rain": 0.0},
        {"temp": 22.8, "humidity": 71, "rain": 0.0},
        {"temp": 21.9, "humidity": 69, "rain": 0.3},
    ]

def compute_risk(soil: float, temp: float, humidity: float, rain: float) -> float:
    """Calcola un rischio normalizzato (mock)."""
    # Semplificato: rischio cresce con umidità e pioggia, penalità per soil basso
    base = 0.3 * (humidity / 100) + 0.3 * (rain / 10) + 0.2 * (soil / 100) + 0.2 * (temp / 40)
    return min(max(base, 0.0), 1.0)

def risk_label(score: float) -> str:
    if score >= 0.65:
        return "HIGH"
    elif score >= 0.45:
        return "MEDIUM"
    elif score >= 0.25:
        return "LOW"
    else:
        return "NONE"

def generate_dashboard(lat: float, lon: float) -> Dict[str, Any]:
    today = datetime.date.today()
    days = [(today - datetime.timedelta(days=i)) for i in range(6, -1, -1)]
    soil_vals = fetch_nasa_soil(lat, lon, days[0], days[-1])
    weather_vals = fetch_openmeteo_weather(lat, lon, days[0], days[-1])
    daily = []
    for i in range(7):
        soil = soil_vals[i]
        temp = weather_vals[i]["temp"]
        humidity = weather_vals[i]["humidity"]
        rain = weather_vals[i]["rain"]
        risk = compute_risk(soil, temp, humidity, rain)
        daily.append({
            "date": days[i].isoformat(),
            "soil": soil,
            "temp": temp,
            "humidity": humidity,
            "rain": rain,
            "risk": round(risk, 3)
        })
    weekly_risk = sum(d["risk"] for d in daily) / 7.0
    return {
        "dashboard": daily,
        "weekly_risk": round(weekly_risk, 3),
        "weekly_label": risk_label(weekly_risk)
    }
