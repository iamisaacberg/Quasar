"""The pilot is deliberately fixed to one county."""

import os
from pathlib import Path

COUNTY_FIPS = "12091"
COUNTY_NAME = "Okaloosa County, Florida"
TIMEZONE = "America/Chicago"
COUNTY_SLUG = "okaloosa"
COUNTY_BOUNDARY_URL = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1"
PARCEL_SOURCE_URL = "https://okgis.myokaloosa.com/arcgis/rest/services/Land-Ownership/Parcels/MapServer/0"
COUNTY_TERMS_URL = "https://www.okaloosapa.com/gis-mapping/"
PARCEL_LICENSE = ("Okaloosa County GIS and Property Appraiser public reference data; "
                  "retain attribution and the source's no-warranty disclaimer. Not a survey or legal document.")
MODEL_VERSION = "illustrative-baseline-v1"
NOTICE = (
    "Synthetic demonstration only. Relative risk estimates are unvalidated, "
    "not flood depths or probabilities. Follow official NWS and local emergency guidance."
)


def require_county(fips: str) -> None:
    if fips != COUNTY_FIPS:
        raise ValueError("This pilot supports Okaloosa County (12091) only.")


def load_env(path=Path(".env")) -> None:
    """Small, non-executing KEY=VALUE loader. No shell expansion or commands."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key.strip().replace("_", "").isalnum():
            raise ValueError("Expected KEY=VALUE lines in .env")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def map_settings() -> dict:
    token = os.environ.get("MAPBOX_PUBLIC_TOKEN", "").strip()
    if token and (not token.startswith("pk.") or any(c.isspace() for c in token)):
        raise ValueError("MAPBOX_PUBLIC_TOKEN must be a public pk. token; secret tokens are never served")
    style = os.environ.get("MAPBOX_STYLE") or "mapbox://styles/mapbox/light-v11"
    if not style.startswith("mapbox://styles/"):
        raise ValueError("MAPBOX_STYLE must be a Mapbox style URL")
    return {"provider": "mapbox", "public_token": token, "style": style,
            "configured": bool(token), "h3_resolution": 7}
