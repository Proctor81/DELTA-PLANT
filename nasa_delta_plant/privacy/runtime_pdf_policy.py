"""Runtime-only PDF generation utilities with no persistent PDF storage."""

from __future__ import annotations

from io import BytesIO
from typing import Any


class RuntimePDFPolicy:
    """Generate agronomic PDFs in memory only."""

    def build_farmer_pdf(self, field_state: dict[str, Any], diagnosis: dict[str, Any]) -> bytes:
        return self._build_pdf(field_state, diagnosis, report_type="farmer")

    def build_scientist_pdf(self, field_state: dict[str, Any], diagnosis: dict[str, Any]) -> bytes:
        return self._build_pdf(field_state, diagnosis, report_type="scientist")

    def _build_pdf(self, field_state: dict[str, Any], diagnosis: dict[str, Any], report_type: str) -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, String

        buffer = BytesIO()
        document = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1.4 * cm, bottomMargin=1.4 * cm)
        styles = getSampleStyleSheet()
        story = []
        title = "DELTA Plant Field Report" if report_type == "farmer" else "DELTA Plant Scientific Report"
        story.append(Paragraph(title, styles["Title"]))
        story.append(Spacer(1, 0.3 * cm))

        geo_area = field_state.get("geo_area", {})
        drawing = Drawing(14 * cm, 5 * cm)
        drawing.add(Line(0, 0.5 * cm, 14 * cm, 0.5 * cm, strokeColor=colors.HexColor("#8BAA5A")))
        area_type = str(geo_area.get("type", "unknown"))
        if area_type == "circle":
            radius = max(min(float(geo_area.get("radius", 500.0)) / 80.0, 90.0), 12.0)
            drawing.add(Circle(7 * cm, 2.7 * cm, radius, strokeColor=colors.HexColor("#224F3B"), fillColor=colors.HexColor("#DDE9C8")))
        elif "geojson" in geo_area:
            coordinates = geo_area["geojson"].get("geometry", geo_area["geojson"]).get("coordinates", [])
            ring = coordinates[0] if coordinates and isinstance(coordinates[0], list) else []
            if ring:
                xs = [float(point[0]) for point in ring]
                ys = [float(point[1]) for point in ring]
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)
                scaled_points: list[float] = []
                for lon, lat in ring:
                    x = 1.0 * cm + ((float(lon) - min_x) / max(max_x - min_x, 0.0001)) * 11.5 * cm
                    y = 1.0 * cm + ((float(lat) - min_y) / max(max_y - min_y, 0.0001)) * 3.2 * cm
                    scaled_points.extend([x, y])
                drawing.add(Polygon(scaled_points, strokeColor=colors.HexColor("#224F3B"), fillColor=colors.HexColor("#DDE9C8")))
        drawing.add(String(0.5 * cm, 4.2 * cm, f"Area type: {area_type}", fontSize=10, fillColor=colors.HexColor("#163323")))
        drawing.add(String(0.5 * cm, 0.9 * cm, "Runtime generated - no PDF persisted on disk", fontSize=9, fillColor=colors.HexColor("#4A4A4A")))
        story.append(drawing)
        story.append(Spacer(1, 0.3 * cm))

        feature_rows = [["Metric", "Value"]]
        feature_rows.extend(
            [
                ["Crop", str(diagnosis.get("probable_crop") or field_state.get("crop_class") or "Unknown")],
                ["Soil moisture", f"{field_state['sar_features'].get('soil_moisture_percent', 0):.2f}%"],
                ["Biomass index", f"{field_state['sar_features'].get('biomass_index', 0):.2f}"],
                ["Crop height estimate", f"{field_state['sar_features'].get('crop_height_estimate_cm', 0):.1f} cm"],
                ["Disease risk", f"{field_state['sar_features'].get('disease_risk_composite', 0):.2f}/100"],
                ["Yield forecast", f"{field_state['sar_features'].get('yield_forecast_index', 0):.2f}/100"],
                ["Confidence", f"{field_state.get('confidence_score', 0):.2f}"],
            ]
        )
        feature_table = Table(feature_rows, colWidths=[7 * cm, 8.5 * cm])
        feature_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#224F3B")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#6C8E60")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#F3F8EB")]),
                ]
            )
        )
        story.append(feature_table)
        story.append(Spacer(1, 0.3 * cm))

        narrative_key = "report_farmer" if report_type == "farmer" else "report_scientist"
        story.append(Paragraph(str(diagnosis.get(narrative_key, "")), styles["BodyText"]))
        story.append(PageBreak())

        procedural_rows = [["Procedure", "Recommendation"]]
        procedural_rows.extend(
            [
                ["Irrigation", str(diagnosis.get("irrigation_recommendation", "n/a"))],
                ["Drainage", str(diagnosis.get("drainage_recommendation", "n/a"))],
                ["Anomalies", ", ".join(diagnosis.get("anomalies", [])) or "none"],
                ["Flags", ", ".join(diagnosis.get("phytopathology_flags", [])) or "none"],
            ]
        )
        procedural_table = Table(procedural_rows, colWidths=[5 * cm, 10.5 * cm])
        procedural_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0E2A3B")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#6F8DA5")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(Paragraph("Operational recommendations", styles["Heading2"]))
        story.append(procedural_table)

        document.build(story)
        buffer.seek(0)
        return buffer.getvalue()