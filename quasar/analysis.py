"""Shared analysis for notebooks and the command line; no notebook imports.

All scoring still runs through pipeline.collection -> scoring.score. Research
presentation code belongs in notebooks; reusable transformations belong here.
"""

import argparse
import json
from collections import Counter
from datetime import datetime, timezone

from .config import load_env
from .pipeline import collection

SYNTHETIC_SCENARIOS = ("baseline", "heavy-rain", "peak")


def scenario_report(scenario_id="baseline", *, generated_at=None) -> dict:
    if scenario_id not in (*SYNTHETIC_SCENARIOS, "weathernext"):
        raise ValueError("Reports support baseline, heavy-rain, peak, weathernext, or compare")
    data = collection(scenario_id)
    generated_at = generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    rows = []
    for feature in data["features"]:
        p = feature["properties"]
        risk = p["risk"]
        rainfall = p["forecast"]["rainfall_6h_mm"] if "forecast" in p else data["scenario"]["rainfall_6h_mm"]
        forecast = data["forecast"] or {}
        rows.append({"property_id": p["id"], "label": p["label"], "scenario": data["scenario"]["id"],
                     "county_fips": data["county_fips"], "mode": data["mode"],
                     "longitude": feature["geometry"]["coordinates"][0],
                     "latitude": feature["geometry"]["coordinates"][1],
                     "valid_from": data["scenario"]["valid_from"], "valid_to": data["scenario"]["valid_to"],
                     "generated_at": generated_at, "notice": data["notice"],
                     "provenance": data["provenance"],
                     "forecast_status": p.get("forecast", {}).get("status", "not_applicable"),
                     "available_hours": p.get("forecast", {}).get("available_hours"),
                     **{key: forecast.get(key) for key in ("source_table", "init_time", "retrieved_at", "native_resolution", "statistic")},
                     "rainfall_6h_mm": rainfall, "score": risk["score"], "band": risk["band"],
                     "factors": [dict(factor) for factor in risk["factors"]],
                     "missing": list(risk["missing"]), "model_version": risk["model_version"],
                     "data_status": risk["data_status"]})
    known = [row["score"] for row in rows if row["score"] is not None]
    return {"county_fips": data["county_fips"], "mode": data["mode"], "notice": data["notice"],
            "generated_at": generated_at,
            "scenario": data["scenario"], "provenance": data["provenance"], "forecast": data["forecast"],
            "summary": {"site_count": len(rows), "scored_count": len(known),
                        "unknown_count": len(rows) - len(known),
                        "bands": dict(Counter(row["band"] for row in rows)),
                        "mean_score": round(sum(known) / len(known), 2) if known else None},
            "rows": rows}


def compare_scenarios(scenario_ids=SYNTHETIC_SCENARIOS) -> list[dict]:
    """A long-format table; nulls and scenario identity survive the comparison."""
    return [row for scenario_id in scenario_ids for row in scenario_report(scenario_id)["rows"]]


def report(scenario_id="baseline") -> dict:
    """One immutable response snapshot; comparisons never include mixed forecasts."""
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if scenario_id != "compare":
        return scenario_report(scenario_id, generated_at=generated_at)
    reports = [scenario_report(identifier, generated_at=generated_at) for identifier in SYNTHETIC_SCENARIOS]
    return {"county_fips": reports[0]["county_fips"], "mode": "synthetic_demo",
            "generated_at": generated_at, "notice": reports[0]["notice"],
            "provenance": reports[0]["provenance"], "forecast": None,
            "scenarios": [{"scenario": item["scenario"], "summary": item["summary"]} for item in reports],
            "rows": [row for item in reports for row in item["rows"]]}


def main():
    parser = argparse.ArgumentParser(description="Run Quasar's shared analysis without Jupyter")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--scenario", help="baseline, heavy-rain, peak, or configured weathernext")
    group.add_argument("--compare", action="store_true", help="Compare the three synthetic exercise windows")
    args = parser.parse_args()
    load_env()
    try:
        report = compare_scenarios() if args.compare else scenario_report(args.scenario or "baseline")
        print(json.dumps(report, indent=2, allow_nan=False))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
