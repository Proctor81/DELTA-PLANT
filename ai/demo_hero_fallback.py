# Logica DEMO HERO fallback per DELTA Plant
# Conversione da JavaScript (website/nasa-monitor.html) a Python
# Questa funzione replica la generazione deterministica dei dati demo usata dalla DEMO HERO

from math import pi, cos
from datetime import datetime

def clamp(value, min_value, max_value):
    return max(min_value, min(max_value, value))

def infer_demo_crop(answers):
    answers = set(answers)
    if 'vine' in answers:
        if 'spots' in answers:
            return {
                'probable_crop': 'Grape_Black_rot',
                'candidate_crops': ['Grape_Black_rot', 'Grape_healthy', 'Tomato_Early_blight'],
                'confidence_boost': 0.05
            }
        else:
            return {
                'probable_crop': 'Grape_healthy',
                'candidate_crops': ['Grape_healthy', 'Grape_Black_rot', 'Peach_healthy'],
                'confidence_boost': 0.08
            }
    if 'tree' in answers:
        if 'yellowing' in answers:
            return {
                'probable_crop': 'Apple_Black_rot',
                'candidate_crops': ['Apple_Black_rot', 'Apple_healthy', 'Peach_healthy'],
                'confidence_boost': 0.04
            }
        else:
            return {
                'probable_crop': 'Peach_healthy',
                'candidate_crops': ['Peach_healthy', 'Apple_healthy', 'Apple_Cedar_apple_rust'],
                'confidence_boost': 0.07
            }
    if 'herbaceous' in answers:
        if 'spots' in answers:
            return {
                'probable_crop': 'Tomato_Early_blight',
                'candidate_crops': ['Tomato_Early_blight', 'Tomato_healthy', 'Potato_Early_blight'],
                'confidence_boost': 0.05
            }
        if 'wilting' in answers:
            return {
                'probable_crop': 'Potato_Late_blight',
                'candidate_crops': ['Potato_Late_blight', 'Tomato_Late_blight', 'Tomato_healthy'],
                'confidence_boost': 0.04
            }
        return {
            'probable_crop': 'Tomato_healthy',
            'candidate_crops': ['Tomato_healthy', 'Potato_healthy', 'Pepper_bell_healthy'],
            'confidence_boost': 0.08
        }
    return {
        'probable_crop': 'Tomato_healthy',
        'candidate_crops': ['Tomato_healthy', 'Potato_healthy', 'Grape_healthy'],
        'confidence_boost': 0.0
    }

def geometry_seed(geo_data):
    if geo_data['type'] == 'circle':
        c = geo_data['center']
        return abs((c['lat'] * 13.17) + (c['lng'] * 7.31) + (geo_data['radius'] / 100))
    points = geo_data.get('geojson', {}).get('geometry', {}).get('coordinates', [[]])[0]
    return abs(sum(((p[0] * 9.1 + p[1] * 4.7) * (i + 1)) for i, p in enumerate(points[:6])))

def get_date_window_days(start_value, end_value):
    try:
        start = datetime.strptime(start_value, '%Y-%m-%d')
        end = datetime.strptime(end_value, '%Y-%m-%d')
        diff = (end - start).days
        return clamp(diff + 1, 1, 366)
    except Exception:
        return 30

def compute_area_hectares(geo_data):
    if geo_data['type'] == 'circle':
        r = geo_data['radius']
        return (pi * r * r) / 10000
    points = geo_data.get('geojson', {}).get('geometry', {}).get('coordinates', [[]])[0]
    if not points:
        return 0
    centroid = [sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)]
    lon0, lat0 = centroid
    area = 0
    for i in range(len(points) - 1):
        lon1, lat1 = points[i]
        lon2, lat2 = points[i + 1]
        x1 = (lon1 - lon0) * 111320 * cos(lat0 * pi / 180)
        y1 = (lat1 - lat0) * 110540
        x2 = (lon2 - lon0) * 111320 * cos(lat0 * pi / 180)
        y2 = (lat2 - lat0) * 110540
        area += (x1 * y2) - (x2 * y1)
    return abs(area / 2) / 10000

def build_demo_analysis_payload(geo_data, date_start, date_end, crop_answers, consent=None):
    if consent is None:
        consent = {'llm': False}
    area_ha = compute_area_hectares(geo_data)
    window_days = get_date_window_days(date_start, date_end)
    crop_inf = infer_demo_crop(crop_answers)
    seed = geometry_seed(geo_data)
    symptom_penalty = 18 if 'spots' in crop_answers else 14 if 'yellowing' in crop_answers else 22 if 'wilting' in crop_answers else 4
    moisture = clamp(38 + (seed % 17) + min(window_days / 8, 7) - min(area_ha / 1600, 10), 18, 86)
    biomass = clamp(49 + (seed % 13) + (9 if 'healthy' in crop_inf['probable_crop'] else 3) + min(area_ha / 2200, 7), 18, 96)
    disease_risk = clamp(12 + symptom_penalty + max(0, moisture - 55) * 0.65 + (7 if window_days > 40 else 0), 5, 94)
    yield_forecast = clamp(72 + (biomass * 0.18) - (disease_risk * 0.32) - max(0, 40 - moisture) * 0.25, 18, 95)
    water_stress_level = 'low' if moisture >= 58 else 'moderate' if moisture >= 40 else 'high'
    disease_risk_level = 'high' if disease_risk >= 67 else 'moderate' if disease_risk >= 40 else 'low'
    confidence_score = clamp(0.56 + (len(crop_answers) * 0.06) + crop_inf['confidence_boost'], 0.56, 0.93)
    anomalies = []
    if disease_risk >= 60:
        anomalies.append('Localized disease pressure should be ground-truthed within 48 hours.')
    if moisture <= 35:
        anomalies.append('Surface moisture proxy is trending low for the selected date window.')
    if area_ha > 3000:
        anomalies.append('Large geometry selected: split the field into scouting zones before acting.')
    report_farmer = f"{crop_inf['probable_crop']} shows {water_stress_level} water stress and {disease_risk_level} disease pressure in the browser fallback model. Prioritize a ground check in the hottest parcel, then tune irrigation in the next 24 hours."
    report_scientist = f"Client-side fallback report for {crop_inf['probable_crop']} over {area_ha:.1f} hectares and a {window_days}-day observation window. Moisture={moisture:.1f}%, biomass={biomass:.1f}, disease composite={disease_risk:.1f}, yield forecast={yield_forecast:.1f}. This summary is a deterministic browser preview, not a live satellite retrieval."
    return {
        'field_state': {
            'sar_features': {
                'soil_moisture_percent': round(moisture, 1),
                'biomass_index': round(biomass, 1),
                'disease_risk_composite': round(disease_risk, 1),
                'yield_forecast_index': round(yield_forecast, 1),
            },
            'raw_sar_summary': {
                'source': 'Browser demo fallback',
                'available_channels': ['VV', 'VH'],
                'interpolation_method': 'client-side heuristic',
                'polarimetric_mode': 'pseudo-dual-pol-preview',
                'insar_available': False,
            },
        },
        'diagnosis': {
            'probable_crop': crop_inf['probable_crop'],
            'candidate_crops': crop_inf['candidate_crops'],
            'water_stress_level': water_stress_level,
            'disease_risk_level': disease_risk_level,
            'confidence_score': round(confidence_score, 2),
            'irrigation_recommendation': 'Increase irrigation frequency in short pulses.' if moisture < 45 else 'Maintain current irrigation and verify the driest scouting block.',
            'drainage_recommendation': 'Inspect drainage and compaction in the lowest zones.' if moisture > 70 else 'No drainage intervention is suggested by the fallback model.',
            'anomalies': anomalies,
            'report_farmer': report_farmer,
            'report_scientist': report_scientist,
            'llm_used': consent.get('llm', False),
        },
        'pdf_tokens': {
            'farmer': 'demo-farmer-report',
            'scientist': 'demo-scientist-report',
            'expires_in_minutes': 0,
        },
        'llm_remaining_today': 0 if consent.get('llm', False) else 1,
    }
