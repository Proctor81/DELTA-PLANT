"""
Genera un report tabellare (Markdown e HTML) DEMO HERO per DELTA Plant
Dati: Soil | Temp | Humidity | Rain | Risk per 7 giorni (oggi + 6 precedenti) + Weekly Fungal Risk
"""
import sys
from datetime import datetime, timedelta
from ai.demo_hero_fallback import build_demo_analysis_payload

def generate_demo_dashboard(lat, lng, radius, crop_answers=None):
    if crop_answers is None:
        crop_answers = []
    today = datetime.now().date()
    geo_data = {
        'type': 'circle',
        'center': {'lat': lat, 'lng': lng},
        'radius': radius
    }
    # Finestra: oggi + 6 giorni precedenti
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    date_start = days[0].strftime('%Y-%m-%d')
    date_end = days[-1].strftime('%Y-%m-%d')
    payload = build_demo_analysis_payload(geo_data, date_start, date_end, crop_answers)
    dashboard = []
    for d in days:
        # Per ogni giorno, rigenera il payload cambiando la finestra per la data
        p = build_demo_analysis_payload(geo_data, d.strftime('%Y-%m-%d'), d.strftime('%Y-%m-%d'), crop_answers)
        sar = p['field_state']['sar_features']
        dashboard.append({
            'date': d.strftime('%Y-%m-%d'),
            'soil': sar['soil_moisture_percent'],
            'temp': round(25.2 + lat/1000, 1),
            'humidity': round(59.4 + lng/1000, 1),
            'rain': round(4.67 + (lat+lng)/10000, 2),
            'risk': sar['disease_risk_composite']/100
        })
    # Weekly risk
    weekly_risk = payload['field_state']['sar_features']['disease_risk_composite']/100
    weekly_label = 'NESSUNO' if weekly_risk < 0.2 else 'BASSO' if weekly_risk < 0.4 else 'MEDIO' if weekly_risk < 0.7 else 'ALTO'
    # Markdown table
    md = '| Date | Soil (%) | Temp (°C) | Humidity (%) | Rain (mm) | Risk (%) |\n|------|----------|-----------|--------------|-----------|----------|\n'
    for d in dashboard:
        md += f"| {d['date']} | {d['soil']} | {d['temp']} | {d['humidity']} | {d['rain']} | {d['risk']*100:.1f} |\n"
    md += f"\n**Weekly Fungal Risk:** {weekly_risk*100:.1f}% ({weekly_label})\n"
    # HTML table
    html = '<table><thead><tr><th>Date</th><th>Soil (%)</th><th>Temp (°C)</th><th>Humidity (%)</th><th>Rain (mm)</th><th>Risk (%)</th></tr></thead><tbody>'
    for d in dashboard:
        html += f"<tr><td>{d['date']}</td><td>{d['soil']}</td><td>{d['temp']}</td><td>{d['humidity']}</td><td>{d['rain']}</td><td>{d['risk']*100:.1f}</td></tr>"
    html += f"</tbody></table><p><b>Weekly Fungal Risk:</b> {weekly_risk*100:.1f}% ({weekly_label})</p>"
    return md, html

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print('Usage: python tools/generate_demo_dashboard_report.py <lat> <lng> <radius>')
        sys.exit(1)
    lat = float(sys.argv[1])
    lng = float(sys.argv[2])
    radius = float(sys.argv[3])
    md, html = generate_demo_dashboard(lat, lng, radius)
    print('--- MARKDOWN ---\n')
    print(md)
    print('\n--- HTML ---\n')
    print(html)
