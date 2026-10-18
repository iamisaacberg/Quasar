"""Dependency-free validation of additive model diagnostics sent to the browser."""
import math
import re
from datetime import timedelta

from ..adapters.weathernext import timestamp, query_sql
from . import FEATURES, POLICY, TARGET, finite


def details(value, score):
    keys = {"susceptibility", "raw_susceptibility", "rainfall_6h_mm", "rainfall_stress",
            "model_instability", "baseline", "attributions"}
    if not isinstance(value, dict) or set(value) != keys or score is None:
        raise ValueError("Invalid model diagnostics")
    if any(not finite(value[k]) for k in keys-{"attributions"}):
        raise ValueError("Nonfinite model diagnostics")
    attrs = value["attributions"]
    if (not 0 <= value["susceptibility"] <= 1 or not 0 <= value["rainfall_stress"] < 1
            or value["rainfall_6h_mm"] < 0 or not 0 <= value["model_instability"] <= .5
            or not isinstance(attrs, dict) or set(attrs) != set(FEATURES)
            or not all(finite(v) for v in attrs.values())
            or not math.isclose(value["baseline"]+sum(attrs.values()), value["raw_susceptibility"], abs_tol=1e-6)
            or not math.isclose(value["rainfall_stress"], value["rainfall_6h_mm"]/(value["rainfall_6h_mm"]+50), abs_tol=1e-8)
            or not math.isclose(score, 100*value["susceptibility"]*value["rainfall_stress"], abs_tol=1e-5)):
        raise ValueError("Inconsistent model diagnostics")
    return value


def metadata(value):
    if (not isinstance(value, dict) or set(value) != {"schema_version", "model_version", "target", "policy", "promoted", "model_sha256", "notice"}
            or value["schema_version"] != 1 or value["target"] != TARGET or value["policy"] != POLICY
            or value["promoted"] is not True or not isinstance(value["model_version"], str)
            or not 1 <= len(value["model_version"]) <= 200
            or not isinstance(value["model_sha256"], str) or not re.fullmatch("[0-9a-f]{64}", value["model_sha256"])
            or not isinstance(value["notice"], str) or not 1 <= len(value["notice"]) <= 1000):
        raise ValueError("Invalid/unpromoted model metadata")
    return value


def forecast(value):
    allowed = {"status", "init_time", "published_at", "retrieved_at", "source_table", "native_resolution", "statistic",
               "units", "valid_from", "valid_to", "expires_at", "source_sha256", "mode", "availability_basis"}
    if (not isinstance(value, dict) or set(value) != allowed or value["status"] not in ("ready", "stale")
            or value["native_resolution"] != "0.1 degree" or value["statistic"] != "ensemble_mean"
            or value["units"] != "mm / 6h" or value["mode"] not in ("current", "replay")
            or not isinstance(value["source_sha256"], str) or not re.fullmatch("[0-9a-f]{64}", value["source_sha256"])):
        raise ValueError("Invalid model forecast provenance")
    query_sql(value["source_table"])
    for key in ("init_time", "retrieved_at", "valid_from", "valid_to", "expires_at"):
        timestamp(value[key])
    if value["published_at"] is not None:
        timestamp(value["published_at"])
    init, start, end, retrieved, expires = [timestamp(value[k]) for k in
                                            ("init_time", "valid_from", "valid_to", "retrieved_at", "expires_at")]
    if (end-start != timedelta(hours=6) or init > start or retrieved < init
            or (value["status"] == "ready" and start-init > timedelta(hours=12))
            or expires > min(init+timedelta(hours=12), retrieved+timedelta(hours=2), end)
            or value["availability_basis"] not in ("publication-constrained", "initialization-based reconstruction")
            or (value["published_at"] is not None and not init <= timestamp(value["published_at"]) <= start)):
        raise ValueError("Inconsistent model forecast times")
    return value
