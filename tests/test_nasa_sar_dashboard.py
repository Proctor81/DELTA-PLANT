import datetime

import bot.nasa_sar_dashboard as dashboard


def test_fetch_nasa_soil_normalizes_power_proxy(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "properties": {
                    "parameter": {
                        "GWETROOT": {
                            "20260519": 0.42,
                            "20260520": -999.0,
                        },
                        "GWETTOP": {
                            "20260519": 0.32,
                            "20260520": 0.28,
                        },
                    }
                }
            }

    monkeypatch.setattr(dashboard.requests, "get", lambda *args, **kwargs: FakeResponse())

    soil = dashboard.fetch_nasa_soil(41.9028, 12.4964, datetime.date(2026, 5, 19), datetime.date(2026, 5, 20))

    assert soil == [
        {"date": "2026-05-19", "soil": 37.0},
        {"date": "2026-05-20", "soil": 28.0},
    ]


def test_generate_dashboard_uses_weather_dates_and_weekly_mean(monkeypatch):
    monkeypatch.setattr(
        dashboard,
        "fetch_nasa_soil",
        lambda lat, lon, start, end: [
            {"date": "2026-05-19", "soil": 40.0},
            {"date": "2026-05-21", "soil": 44.0},
            {"date": "2026-05-25", "soil": 52.0},
        ],
    )
    monkeypatch.setattr(
        dashboard,
        "fetch_openmeteo_weather",
        lambda lat, lon, start, end: [
            {"date": "2026-05-19", "temp": 20.0, "humidity": 60.0, "rain": 0.0},
            {"date": "2026-05-20", "temp": 21.0, "humidity": 65.0, "rain": 1.0},
            {"date": "2026-05-21", "temp": 22.0, "humidity": 70.0, "rain": 3.0},
            {"date": "2026-05-22", "temp": 23.0, "humidity": 74.0, "rain": 5.0},
            {"date": "2026-05-23", "temp": 24.0, "humidity": 78.0, "rain": 6.0},
            {"date": "2026-05-24", "temp": 22.0, "humidity": 82.0, "rain": 4.0},
            {"date": "2026-05-25", "temp": 20.0, "humidity": 85.0, "rain": 2.0},
        ],
    )

    result = dashboard.generate_dashboard(
        41.9028,
        12.4964,
        start=datetime.date(2026, 5, 19),
        end=datetime.date(2026, 5, 25),
    )

    assert result["dashboard"][-1]["date"] == "2026-05-25"
    assert result["dashboard"][1]["soil"] == 40.0
    assert result["dashboard"][2]["soil"] == 44.0
    assert result["dashboard"][-1]["soil"] == 52.0
    assert result["weekly_risk"] > result["dashboard"][0]["risk"]
    assert result["weekly_label"] in {"BASSO", "MEDIO", "ALTO"}
    assert result["summary"]["weather_window_end"] == "2026-05-25"


def test_build_dashboard_plaintext_report_keeps_same_layout_across_languages():
    sample_dashboard = {
        "dashboard": [
            {
                "date": "2026-05-19",
                "soil": 12.3,
                "temp": 23.4,
                "humidity": 78,
                "rain": 4.5,
                "risk": 0.62,
            },
            {
                "date": "2026-05-20",
                "soil": 14.7,
                "temp": 24.1,
                "humidity": 69,
                "rain": 0.0,
                "risk": 0.41,
            },
        ],
        "weekly_risk": 0.52,
        "weekly_label": "MEDIO",
    }

    report_it = dashboard.build_dashboard_plaintext_report(sample_dashboard, language=dashboard.REPORT_LANGUAGE_IT)
    report_en = dashboard.build_dashboard_plaintext_report(sample_dashboard, language=dashboard.REPORT_LANGUAGE_EN)

    lines_it = report_it.splitlines()
    lines_en = report_en.splitlines()

    assert len(lines_it) == len(lines_en)
    assert lines_it[0] == lines_en[0] == "🌎 NASA-ISRO/SAR Dashboard"
    assert lines_it[1] == lines_en[1] == ""
    assert lines_it[3:5] == lines_en[3:5] == [
        "2026-05-19 | 12.3 | 23.4 | 78 | 4.5 | 0.62",
        "2026-05-20 | 14.7 | 24.1 | 69 | 0.0 | 0.41",
    ]
    assert lines_it[5] == lines_en[5] == ""
    assert lines_it[6].startswith("Rischio settimanale: 0.52 (")
    assert lines_en[6].startswith("Weekly risk: 0.52 (")
    assert report_it.count("🌎") == report_en.count("🌎") == 1