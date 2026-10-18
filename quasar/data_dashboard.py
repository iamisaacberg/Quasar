"""Tabular projection of the shared native-cell forecast pipeline."""
from datetime import datetime, timezone

from .adapters.weathernext import iso
from .bridge import read_snapshot
from .forecast_timeline import timeline


def weather_data(*, now=None, source="current"):
    now = now or datetime.now(timezone.utc)
    data = timeline(source=source, now=now, reader=read_snapshot)
    frames = []
    for frame in data["frames"]:
        cells = frame["collection"]["weather_cells"]
        frames.append({"at": frame["at"], "valid_to": cells["valid_to"], "rows": [
            {"native_cell_id": feature["id"], "rainfall_6h_mm": feature["properties"]["rainfall_6h_mm"],
             "available_hours": feature["properties"]["available_hours"], "status": feature["properties"]["status"]}
            for feature in cells["features"]]})
    return {**data, "frames": frames, "generated_at": iso(now),
            "message": data.get("message", "Imported native cells intersecting Okaloosa County; cells may extend beyond the boundary. Forecast rainfall is not observed rain or parcel flood risk.")}
