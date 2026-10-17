"""Optional point-based official alert fetch, separate from synthetic risk scoring.

Point queries avoid assuming a single forecast zone represents Okaloosa.
The point must come from the curated county-scoped fixture catalog.
No results does not imply no hazard. This client is not wired to the demo UI.
"""

import argparse
import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..pipeline import collection


def fetch_for_demo_point(property_id: str, user_agent: str, *, opener=urlopen) -> dict:
    if not user_agent.strip() or "\n" in user_agent or "\r" in user_agent:
        raise ValueError("Provide an identifying NWS User-Agent")
    feature = next((f for f in collection()["features"] if f["id"] == property_id), None)
    if feature is None:
        raise ValueError("Unknown Okaloosa demo point")
    lon, lat = feature["geometry"]["coordinates"]
    url = "https://api.weather.gov/alerts/active?" + urlencode({"point": f"{lat},{lon}"})
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/geo+json"})
    # Errors propagate to the caller; an outage must never become an empty success.
    with opener(request, timeout=15) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("NWS response exceeded size limit")
    data = json.loads(raw)
    if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        raise ValueError("Unexpected NWS response")
    if data.get("pagination", {}).get("next"):
        raise ValueError("Paginated NWS response: implement pagination before using this result")
    return {"source": "NWS", "source_url": url, "scope": "single_demo_point",
            "county_fips": "12091", "property_id": property_id,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "notice": "Point-specific official feed response; not countywide coverage or an all-clear.",
            "data": data}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--property-id", default="demo-001")
    parser.add_argument("--user-agent", required=True)
    args = parser.parse_args()
    print(json.dumps(fetch_for_demo_point(args.property_id, args.user_agent), indent=2))


if __name__ == "__main__":
    main()
