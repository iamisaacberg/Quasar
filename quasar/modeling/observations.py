"""Explicit public observation acquisition, separate from forecasts and training.

County geometry validates every mapped point. Reports, station measurements and
high-water marks retain their different meanings; none automatically labels a
whole parcel or supplies covered negatives.
"""
import csv
import gzip
import hashlib
import io
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from ..geometry import covers
from ..adapters.weathernext import timestamp
from . import finite, read_json, utcnow, write_json

SELECTED = ("2026-10-09T05:00:00Z", "2026-10-10T11:00:00Z")
SALLY = ("2020-09-13T04:00:00Z", "2020-09-21T04:00:00Z")
STN = "https://api.waterdata.usgs.gov/stnservices"


def gauge_series(data, geometry, start, end):
    result, excluded = [], 0
    for series in data["value"]["timeSeries"]:
        source, variable = series["sourceInfo"], series["variable"]
        location = source["geoLocation"]["geogLocation"]
        lon, lat = location.get("longitude"), location.get("latitude")
        if (location.get("srs") != "EPSG:4326" or not finite(lon) or not finite(lat)
                or not covers([lon, lat], geometry)):
            excluded += 1
            continue
        parameter, unit = variable["variableCode"][0]["value"], variable["unit"]["unitCode"]
        supported = (parameter, unit) in (("00065", "ft"), ("00060", "ft3/s"), ("00045", "in"))
        observations, seen = [], set()
        for group in series["values"]:
            for raw in group["value"]:
                at = timestamp(raw["dateTime"])
                if not timestamp(start) <= at <= timestamp(end):
                    continue
                # Duplicated or overlapping series are not summed or silently replaced.
                if at in seen:
                    raise ValueError("Duplicate station/parameter measurement time")
                seen.add(at)
                try:
                    value = float(raw["value"])
                except (ValueError, TypeError):
                    value = None
                missing = not supported or not finite(value) or value == variable.get("noDataValue")
                observations.append({"at": at.isoformat(), "value": None if missing else value,
                                     "qualifiers": raw.get("qualifiers", []), "missing": missing})
        result.append({"site_id": source["siteCode"][0]["value"], "site_name": source["siteName"],
                       "coordinates": [lon, lat], "county_fips": "12091", "boundary_validated": True,
                       "crs": "EPSG:4326", "parameter_code": parameter, "units": unit,
                       "vertical_reference": "Gauge-local datum; not parcel NAVD88 terrain" if parameter == "00065" else "not applicable",
                       "scope": "Station observation, not parcel inundation", "observations": observations})
    return result, excluded


def storm_reports(rows, geometry):
    records, rejected = [], 0
    for row in rows:
        if (row.get("STATE_FIPS") != "12" or row.get("CZ_TYPE") != "C"
                or row.get("CZ_FIPS", "").zfill(3) != "091"
                or row.get("EVENT_TYPE") not in ("Flash Flood", "Flood", "Heavy Rain")):
            continue
        try:
            lon, lat = float(row["BEGIN_LON"]), float(row["BEGIN_LAT"])
        except (ValueError, TypeError, KeyError):
            lon = lat = None
        verified = finite(lon) and finite(lat) and covers([lon, lat], geometry)
        if finite(lon) and finite(lat) and not verified:
            rejected += 1
            continue
        records.append({"event_id": row["EVENT_ID"], "episode_id": row["EPISODE_ID"], "event_type": row["EVENT_TYPE"],
                        "county_fips": "12091", "coordinates": [lon, lat] if verified else None,
                        "boundary_validated": bool(verified), "crs": "EPSG:4326" if verified else "unlocated",
                        "begin_time_raw": row.get("BEGIN_DATE_TIME"), "end_time_raw": row.get("END_DATE_TIME"),
                        "source_timezone": row.get("CZ_TIMEZONE"), "source": row.get("SOURCE"),
                        "location": row.get("BEGIN_LOCATION"), "narrative": row.get("EVENT_NARRATIVE"),
                        "scope": "Reported event location/interval; spatial uncertainty and parcel association require review",
                        "parcel_label": None, "coverage_backed_negative": False})
    return records, rejected


def high_water_marks(rows, geometry, event):
    records, rejected = [], 0
    for row in rows:
        # Current STN serialized field names, not legacy county-tag assumptions.
        lon = row.get("longitude") if row.get("longitude") is not None else row.get("longitude_dd")
        lat = row.get("latitude") if row.get("latitude") is not None else row.get("latitude_dd")
        datum = str(row.get("horizontal_datum_name", "")).upper().replace(" ", "")
        if not finite(lon) or not finite(lat) or "WGS84" not in datum or not covers([lon, lat], geometry):
            rejected += 1
            continue
        records.append({"hwm_id": row.get("hwm_id", row.get("id")), "site_id": row.get("site_id", row.get("site")),
                        "event": event, "coordinates": [lon, lat], "county_fips": "12091", "boundary_validated": True,
                        "crs": "EPSG:4326", "source_fields": row,
                        "scope": "Surveyed peak evidence at a point; event interval does not establish an exact six-hour peak time",
                        "mechanism": "unreviewed; coastal storm tide must not be relabeled rainfall-driven",
                        "parcel_label": None, "coverage_backed_negative": False})
    return records, rejected


def rainfall_reports(text, geometry):
    records, rejected = [], 0
    reader = csv.DictReader(io.StringIO(text))
    if not {"station", "valid", "lon", "lat", "p01i"} <= set(reader.fieldnames or []):
        raise ValueError("METAR archive missing required columns")
    for row in reader:
        if row.get("station") not in ("CEW", "DTS", "VPS"):
            continue
        lon, lat = float(row["lon"]), float(row["lat"])
        if not finite(lon) or not finite(lat) or not covers([lon, lat], geometry):
            rejected += 1
            continue
        at = datetime.strptime(row["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        if not timestamp(SELECTED[0]) <= at <= timestamp(SELECTED[1]):
            continue
        raw = row["p01i"]
        try:
            value = float(raw)
        except (ValueError, TypeError):
            value = None
        invalid = raw != "T" and (not finite(value) or value < 0)
        if invalid:
            value = None
        records.append({"station": row["station"], "at": at.isoformat(), "coordinates": [lon, lat],
                        "county_fips": "12091", "boundary_validated": True, "crs": "EPSG:4326", "units": "inches",
                        "precipitation_1h": value, "trace": raw == "T", "missing": invalid,
                        "source_value": raw,
                        "scope": "Archived METAR one-hour precipitation; overlapping routine/SPECI periods are not summed",
                        "period_start": (at-timedelta(hours=1)).isoformat(), "parcel_label": None})
    return records, rejected


def local_storm_reports(text, geometry):
    """NWS reports archived by IEM; source and location uncertainty are retained."""
    records, rejected = [], 0
    reader = csv.DictReader(io.StringIO(text))
    if not {"VALID", "LAT", "LON", "TYPETEXT", "SOURCE", "CITY", "REMARK"} <= set(reader.fieldnames or []):
        raise ValueError("Local storm report archive missing required columns")
    for row in reader:
        if row.get("TYPETEXT") not in ("FLASH FLOOD", "FLOOD", "HEAVY RAIN"):
            continue
        lon, lat = float(row["LON"]), float(row["LAT"])
        if not finite(lon) or not finite(lat) or not covers([lon, lat], geometry):
            rejected += 1
            continue
        at = datetime.strptime(row["VALID"], "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
        if not timestamp(SELECTED[0]) <= at <= timestamp(SELECTED[1]):
            continue
        records.append({"at": at.isoformat(), "event_type": row["TYPETEXT"], "coordinates": [lon, lat],
                        "county_fips": "12091", "boundary_validated": True, "crs": "EPSG:4326",
                        "source": row.get("SOURCE"), "city": row.get("CITY"), "remark": row.get("REMARK"),
                        "source_product": "NWS local storm report archived by Iowa State IEM",
                        "scope": "Reported flood occurrence at a coarse location; source precision is not a parcel survey",
                        "association_verified": False, "parcel_label": None, "coverage_backed_negative": False})
    return records, rejected


def acquire(boundary, raw_directory, output, historical=False):
    """Explicit, bounded downloads. No model fitting, cloud queries or delivery."""
    county = read_json(boundary)
    if len(county["features"]) != 1 or county["features"][0]["properties"].get("GEOID") != "12091":
        raise ValueError("Authoritative Okaloosa county boundary required")
    geometry = county["features"][0]["geometry"]
    raw, root = Path(raw_directory), Path(output)
    raw.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=False)
    sources, errors = [], []
    prior = read_json(raw/"retrieval-manifest.json") if (raw/"retrieval-manifest.json").exists() else {}
    cached = {r.get("source_url"): r for r in prior.get("sources", []) if r.get("status") == "retrieved"}
    def fetch(url, name, identifier, units, crs="source-defined; normalized points EPSG:4326"):
        receipt = {"source_url": url, "source_identifier": identifier, "retrieved_at": utcnow(),
                   "license": "Not independently reviewed; retain source attribution and consult source terms before redistribution",
                   "crs": crs, "units": units, "processing": "Retained original bytes; derived mapped points checked against authoritative county geometry"}
        try:
            previous = cached.get(url)
            if previous and previous.get("file") == name and (raw/name).is_file():
                data = (raw/name).read_bytes()
                if len(data) <= 30*1024*1024 and hashlib.sha256(data).hexdigest() == previous["sha256"]:
                    sources.append({**previous, "license": receipt["license"], "cache_verified": True})
                    return data
            with urlopen(Request(url, headers={"User-Agent": "Quasar datathon public observation research", "Accept": "application/json,text/csv,*/*"}), timeout=40) as response:
                data = response.read(30*1024*1024+1)
                receipt["final_url"] = response.url
            if len(data) > 30*1024*1024:
                raise ValueError("30 MiB per-download cap exceeded")
            (raw/name).write_bytes(data)
            receipt.update(status="retrieved", file=name, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
            sources.append(receipt)
            return data
        except (OSError, ValueError) as exc:
            receipt.update(status="unavailable", message=str(exc));sources.append(receipt);errors.append(identifier+": "+str(exc))
            return None
    def normalize(identifier, callback):
        try:
            return callback()
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(identifier+": "+str(exc));return None
    gauges = {}
    for name, window in [("selected", SELECTED)]+([("sally-2020", SALLY)] if historical else []):
        url = "https://waterservices.usgs.gov/nwis/iv/?format=json&countyCd=12091&startDT="+window[0]+"&endDT="+window[1]+"&parameterCd=00060,00065,00045&siteStatus=all"
        data = fetch(url, "usgs-"+name+".json", "USGS instantaneous measurements "+name, "Original parameter units retained")
        if data:
            normalized = normalize("USGS "+name, lambda: gauge_series(json.loads(data), geometry, *window))
            if normalized:
                gauges[name] = {"series": normalized[0], "excluded_series": normalized[1], "window": window}
    observations = []
    metar = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=CEW&station=DTS&station=VPS&data=p01i&year1=2026&month1=10&day1=9&year2=2026&month2=10&day2=11&tz=Etc%2FUTC&format=onlycomma&latlon=yes&elev=yes&missing=M&trace=T&direct=no&report_type=3&report_type=4"
    data = fetch(metar, "iem-metar.csv", "Iowa State IEM archive of CEW/DTS/VPS METAR", "One-hour precipitation inches; source timestamps UTC", "EPSG:4326")
    if data:
        normalized = normalize("METAR", lambda: rainfall_reports(data.decode(), geometry))
        if normalized:observations = normalized[0]
    local_reports = []
    url = "https://mesonet.agron.iastate.edu/cgi-bin/request/gis/lsr.py?sts=2026-10-09T05:00Z&ets=2026-10-10T11:00Z&wfo=MOB&fmt=csv"
    data = fetch(url, "iem-local-storm-reports.csv", "Iowa State IEM archive of NWS MOB local storm reports", "Original report magnitude and UTC timestamps retained", "EPSG:4326")
    if data:
        normalized = normalize("NWS local storm reports", lambda: local_storm_reports(data.decode(), geometry))
        if normalized:local_reports = normalized[0]
    reports = []
    index = fetch("https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/", "noaa-index.html", "NOAA Storm Events bulk index", "not applicable", "not applicable") if historical else None
    if index:
        for year in range(2018, 2026):
            names = sorted(set(re.findall(r"StormEvents_details-ftp_v1\.0_d"+str(year)+r"_c\d+\.csv\.gz", index.decode(errors="replace"))))
            if not names:
                errors.append(f"NOAA year {year} unavailable");continue
            name = names[-1]
            data = fetch("https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"+name, name, "NOAA Storm Events "+str(year), "Source event units/times retained", "EPSG:4326 event coordinates")
            if data:
                def parse():
                    with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
                        return storm_reports(csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig")), geometry)
                normalized = normalize("NOAA "+str(year), parse)
                if normalized:reports.extend(normalized[0])
    marks = []
    if historical:
        # These identifiers were verified against the current public STN event inventory.
        data = fetch(STN+"/events/", "stn-events.json", "USGS current STN events", "not applicable", "not applicable")
        events = normalize("STN events", lambda: json.loads(data)) if data else None
        if isinstance(events, list):
            for name in ("2018 Michael", "2020 Sally"):
                event = next((e for e in events if e.get("name") == name), None)
                if event is None:
                    errors.append("STN event missing: "+name);continue
                url = STN+f"/hwms/filteredhwms/?event={event['id']}&states=FL&format=json"
                data = fetch(url, "stn-"+name.replace(" ", "-")+".json", "USGS HWM "+name, "Source elevations, datum, quality and uncertainty retained")
                if data:
                    normalized = normalize("HWM "+name, lambda: high_water_marks(json.loads(data), geometry, event))
                    if normalized:marks.extend(normalized[0])
    write_json(root/"gauges.json", gauges)
    write_json(root/"rainfall.json", observations)
    write_json(root/"storm-reports.json", reports)
    write_json(root/"high-water-marks.json", marks)
    write_json(root/"local-storm-reports.json", local_reports)
    counts = {"gauge_series": sum(len(g["series"]) for g in gauges.values()),
              "gauge_observations": sum(len(s["observations"]) for g in gauges.values() for s in g["series"]),
              "rainfall_reports": len(observations), "storm_event_reports": len(reports), "high_water_marks": len(marks),
              "selected_replay_flood_reports": len(local_reports)}
    manifest = {"schema_version": 1, "county_fips": "12091", "normalized_at": utcnow(), "boundary_sha256": hashlib.sha256(Path(boundary).read_bytes()).hexdigest(),
                "status": "partial" if errors else "observations_acquired" if any(counts.values()) else "unavailable", "historical_authorized": historical,
                "counts": counts, "sources": sources, "errors": errors, "verified_parcel_labels": 0,
                "limitations": ["No covered parcel negatives or verified parcel associations generated.",
                                "Point evidence is not full-parcel inundation; coastal HWMs are not automatically rainfall-driven.",
                                "Historical observations do not validate the selected replay without matching inputs and times.",
                                "Station stage uses a local gauge datum, not parcel terrain elevation.",
                                "Overlapping METAR precipitation periods are retained without invented hourly totals."],
                "artifacts": {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ("gauges.json", "rainfall.json", "storm-reports.json", "high-water-marks.json", "local-storm-reports.json")}}
    write_json(raw/"retrieval-manifest.json", manifest)
    write_json(root/"manifest.json", manifest)
    return manifest
