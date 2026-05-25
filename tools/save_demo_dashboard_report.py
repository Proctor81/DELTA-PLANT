# Salva il report DEMO HERO dashboard in locale
from tools.generate_demo_dashboard_report import generate_demo_dashboard
from datetime import datetime

# Esempio: lat/lng/radius di test
lat, lng, radius = 41.2008, 15.4746, 50
md, html = generate_demo_dashboard(lat, lng, radius)

# Salva Markdown
with open('dashboard_demo_hero.md', 'w', encoding='utf-8') as f:
    f.write(md)

# Salva HTML
with open('dashboard_demo_hero.html', 'w', encoding='utf-8') as f:
    f.write(html)

print('Report dashboard DEMO HERO salvato come dashboard_demo_hero.md e dashboard_demo_hero.html')
