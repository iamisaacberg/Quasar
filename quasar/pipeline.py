"""Fixture adapter -> county validation -> scoring -> GeoJSON contract."""

import json
import math
from pathlib import Path

from .config import COUNTY_FIPS, COUNTY_NAME, NOTICE, require_county
from .scoring import score
from .adapters.weathernext import load_forecast

FIXTURES = Path(__file__).parent / "fixtures"


def scenarios() -> list[dict]:
    items = json.loads((FIXTURES / "scenarios.json").read_text())
    forecast = load_forecast()
    if "records" in forecast:
        items.append({"id": "weathernext", "label": "WeatherNext 3 + fictional site inputs",
                      "valid_from": forecast["valid_from"], "valid_to": forecast["valid_to"],
                      "rainfall_6h_mm": None, "gauge_margin_m": 1.2})
    from .replay import descriptor
    items.append(descriptor())
    return items


def feature_for(record: dict, scenario: dict) -> dict:
    require_county(record.get("county_fips"))
    lon, lat = record["longitude"], record["latitude"]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (lon, lat)):
        raise ValueError("Coordinates must be finite numbers")
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError("Coordinates must use WGS84 longitude/latitude")
    values = {**record, "rainfall_6h_mm": scenario["rainfall_6h_mm"],
              "gauge_margin_m": scenario["gauge_margin_m"]}
    return {"type": "Feature", "id": record["id"],
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"id": record["id"], "label": record["label"],
                           "county_fips": COUNTY_FIPS, "risk": score(values)}}


def collection(scenario_id: str = "baseline", *, at=None, preset="archived", mode="archive") -> dict:
    if scenario_id == "isaias-2026":
        from .replay import collection as replay_collection
        return replay_collection(at, preset, mode)
    if at is not None or preset != "archived" or mode != "archive":
        raise ValueError("Replay parameters require the Isaias scenario")
    scenario = next((s for s in scenarios() if s["id"] == scenario_id), None)
    if scenario is None:
        raise ValueError("Unknown scenario")
    source = json.loads((FIXTURES / "properties.json").read_text())
    require_county(source["county_fips"])
    features = [feature_for(p, scenario) for p in source["properties"]]
    forecast = None
    if scenario_id == "weathernext":
        forecast = load_forecast()
        if "records" not in forecast:
            raise ValueError("WeatherNext snapshot is unavailable or invalid")
        features = []
        for record in source["properties"]:
            weather = forecast["records"][record["id"]]
            feature = feature_for(record, {**scenario, "rainfall_6h_mm": weather["rainfall_6h_mm"]})
            feature["properties"]["forecast"] = weather
            if feature["properties"]["risk"]["score"] is not None:
                feature["properties"]["risk"]["data_status"] = "mixed_demo"
            features.append(feature)
    # Unknown values sort last and are never treated as zero risk.
    features.sort(key=lambda f: (f["properties"]["risk"]["score"] is None,
                                 -(f["properties"]["risk"]["score"] or 0)))
    return {"type": "FeatureCollection", "county_fips": COUNTY_FIPS,
            "county_name": COUNTY_NAME, "mode": "mixed_forecast_demo" if forecast else "synthetic_demo",
            "scenario": scenario, "provenance": source["provenance"],
            "notice": "WeatherNext 3 rainfall with fictional property, FEMA, terrain and gauge inputs. Unvalidated mixed demonstration; not an official warning." if forecast else NOTICE,
            "forecast": {k: v for k, v in forecast.items() if k != "records"} if forecast else None,
            "features": features}
