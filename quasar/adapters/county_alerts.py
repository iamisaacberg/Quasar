"""Explicit NWS county-alert import, kept separate from archived forecasts.

County UGC queries include intersecting zone products per the official NWS
Geolocation Guide. Serving reads a saved snapshot only; it never fetches NWS.
"""
import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, build_opener

from .weathernext import iso, timestamp
from ..modeling import read_json, write_json
from ..parcels import _NoRedirect

SOURCE_URL = "https://api.weather.gov/alerts?active=true&zone=FLC091&status=actual"
GUIDE = "https://www.weather.gov/media/documentation/docs/NWS_Geolocation.pdf"
MAX_PAGES, MAX_BYTES, TTL_SECONDS = 8, 8_000_000, 120
NOTICE = "Official NWS county-query results, separate from experimental exposure. An empty result is not an all-clear. Follow official NWS/local guidance."


def page_url(url):
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    if (parts.scheme != "https" or parts.netloc != "api.weather.gov" or parts.path != "/alerts"
            or parts.fragment or query.get("zone") != ["FLC091"]
            or query.get("active") != ["true"] or query.get("status") != ["actual"]
            or set(query) - {"zone", "active", "status", "cursor", "limit"}):
        raise ValueError("Unexpected NWS pagination URL")
    return url


def import_snapshot(user_agent, *, opener=None, now=None):
    if not isinstance(user_agent, str) or not user_agent.strip() or any(c in user_agent for c in "\r\n"):
        raise ValueError("Provide an identifying NWS User-Agent")
    now = now or datetime.now(timezone.utc)
    opener = opener or build_opener(_NoRedirect).open
    url, seen, features, total = SOURCE_URL, set(), [], 0
    snapshot = {"schema_version": 1, "county_fips": "12091", "source_url": SOURCE_URL,
                "retrieved_at": iso(now), "complete": False, "pages": 0, "features": features,
                "coverage": "NWS county UGC FLC091 including intersecting public/fire zones; not parcel coverage",
                "coverage_reference": GUIDE, "failure_reason": None,
                "source_identifier": "NWS active Actual alerts for county UGC FLC091",
                "license": "NWS open government data; retain attribution and original official text",
                "terms_url": "https://www.weather.gov/documentation/services-web-api",
                "crs": "EPSG:4326 for source GeoJSON where geometry is supplied",
                "units": "Official message text and timezone-aware timestamps; no derived flood depth",
                "processing": ["Explicit county query; bounded pagination; no retries in this invocation",
                               "Preserve source features; derive lifecycle only when serving"]}
    try:
        while url:
            if url in seen or len(seen) >= MAX_PAGES:
                raise ValueError("Pagination repeated or exceeded page cap")
            seen.add(page_url(url))
            request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/geo+json"})
            with opener(request, timeout=10) as response:
                body = response.read(min(2_000_001, MAX_BYTES-total+1))
            total += len(body)
            if len(body) > 2_000_000 or total > MAX_BYTES:
                raise ValueError("NWS response exceeded byte cap")
            data = json.loads(body)
            if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
                raise ValueError("Invalid NWS collection")
            features.extend(data["features"])
            snapshot["pages"] += 1
            url = data.get("pagination", {}).get("next")
        snapshot["complete"] = True
    except Exception:
        # Do not serialize URLs, headers, upstream text, or identifying contact.
        snapshot["failure_reason"] = "NWS import incomplete; network, pagination or response validation failed"
    return snapshot


def interpret(snapshot, *, now=None):
    now = now or datetime.now(timezone.utc)
    base = {"connected": False, "status": "invalid", "county_fips": "12091", "alerts": [],
            "source_url": SOURCE_URL, "notice": NOTICE, "message": "Official alert snapshot invalid; this is not an all-clear."}
    try:
        if (snapshot.get("schema_version") != 1 or snapshot.get("county_fips") != "12091"
                or snapshot.get("source_url") != SOURCE_URL or type(snapshot.get("complete")) is not bool
                or type(snapshot.get("pages")) is not int or not 0 <= snapshot["pages"] <= MAX_PAGES
                or not isinstance(snapshot.get("features"), list) or len(snapshot["features"]) > 10000
                or not isinstance(snapshot.get("coverage"), str) or snapshot.get("coverage_reference") != GUIDE):
            return base
        retrieved = timestamp(snapshot["retrieved_at"])
        if retrieved > now or (snapshot["complete"] and snapshot["pages"] < 1):
            return base
        common = {**base, "connected": snapshot["pages"] > 0, "retrieved_at": snapshot["retrieved_at"],
                  "expires_at": iso(retrieved+timedelta(seconds=TTL_SECONDS)),
                  "coverage": snapshot["coverage"], "coverage_reference": GUIDE}
        if now-retrieved >= timedelta(seconds=TTL_SECONDS):
            return {**common, "status": "stale", "message": "Official alert snapshot stale; current alerts are unknown."}
        messages = {}
        for feature in snapshot["features"]:
            if not isinstance(feature, dict) or feature.get("type") != "Feature":
                return common
            props = feature["properties"]
            identifier = props["id"]
            if not isinstance(identifier, str) or not identifier or len(identifier) > 1000:
                return common
            if identifier in messages:
                if messages[identifier] != props:
                    return common
                continue
            if (props.get("status") != "Actual" or props.get("messageType") not in ("Alert", "Update", "Cancel")
                    or not isinstance(props.get("event"), str) or not isinstance(props.get("references", []), list)):
                return common
            for key in ("sent", "effective", "expires"):
                timestamp(props[key])
            if props.get("onset") is not None:
                timestamp(props["onset"])
            if props.get("ends") is not None:
                timestamp(props["ends"])
            if timestamp(props["expires"]) <= timestamp(props["sent"]):
                return common
            if any(not isinstance(p, dict) or not isinstance(p.get("identifier"), str)
                   for p in props.get("references", [])):
                return common
            if any(props.get(k) is not None and not isinstance(props[k], str) for k in
                   ("headline", "description", "instruction", "areaDesc", "severity", "urgency", "certainty")):
                return common
            messages[identifier] = props
        retired = {reference["identifier"] for p in messages.values()
                   if p["messageType"] in ("Update", "Cancel") and timestamp(p["sent"]) <= now
                   for reference in p.get("references", [])
                   if reference["identifier"] not in messages or timestamp(messages[reference["identifier"]]["sent"]) <= timestamp(p["sent"])}
        alerts = []
        from urllib.parse import quote
        for identifier, props in messages.items():
            expiry = min(timestamp(props["expires"]), timestamp(props.get("ends") or props["expires"]))
            if identifier in retired or props["messageType"] == "Cancel" or timestamp(props["sent"]) > now or expiry <= now:
                continue
            alerts.append({**{k: props.get(k) for k in ("id", "event", "sent", "effective", "onset", "expires", "ends",
                         "headline", "description", "instruction", "areaDesc", "severity", "urgency", "certainty", "messageType")},
                           "source_url": "https://api.weather.gov/alerts/"+quote(identifier, safe=""),
                           "lifecycle": "upcoming" if timestamp(props.get("onset") or props["effective"]) > now else "active"})
        status = ("ready" if alerts else "empty") if snapshot["complete"] else "partial" if snapshot["pages"] else "error"
        return {**common, "status": status, "alerts": alerts,
                "message": f"{len(alerts)} matching official messages returned; this is not an all-clear." if snapshot["complete"]
                           else "Official alert coverage incomplete; additional current messages may be missing.",
                "failure_reason": None if snapshot["complete"] else "Incomplete NWS import"}
    except (ValueError, TypeError, KeyError, AttributeError):
        return base


def official_alerts(source="archive"):
    if source not in ("archive", "current"):
        raise ValueError("Official alert source must be current or archive")
    missing = {"connected": False, "status": "not_connected", "county_fips": "12091", "alerts": [],
               "source_url": "https://www.weather.gov/mob/", "notice": NOTICE,
               "message": "Official NWS alerts are not loaded for this archive. This is not an all-clear."}
    if source == "archive":
        return missing
    path = os.environ.get("QUASAR_NWS_ALERTS_FILE")
    if not path:
        return {**missing, "message": "Current official NWS alerts are not connected. This is not an all-clear."}
    try:
        return interpret(read_json(path, MAX_BYTES))
    except (OSError, ValueError):
        return {**missing, "status": "invalid", "message": "Official alert snapshot invalid or unavailable; current alerts are unknown."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-agent", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshot = import_snapshot(args.user_agent)
    result = interpret(snapshot)
    write_json(args.output, snapshot)
    print(json.dumps(result, allow_nan=False))
    return 0 if result["status"] in ("ready", "empty") else 2


if __name__ == "__main__":
    raise SystemExit(main())
