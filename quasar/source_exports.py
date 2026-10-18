"""Exports contain native forecast cells only, with explicit source/validity metadata."""
import csv
import io
import json
import zipfile

from .forecast_timeline import timeline


def report(source="archive", frame=None):
    data = timeline(source=source)
    if frame is not None and (not str(frame).isascii() or not str(frame).isdigit()):
        raise ValueError("Frame must be a nonnegative index")
    index = data["default_index"] if frame is None else int(frame)
    if data["frames"] and index >= len(data["frames"]):
        raise ValueError("Frame is outside the imported timeline")
    collection = data["frames"][index]["collection"] if data["frames"] else None
    rows = []
    if collection:
        for feature in collection["weather_cells"]["features"]:
            p = feature["properties"]
            rows.append({"county_fips": "12091", "native_cell_id": feature["id"],
                         "valid_from": collection["scenario"]["valid_from"],
                         "valid_to": collection["scenario"]["valid_to"],
                         "rainfall_6h_mm": p["rainfall_6h_mm"], "units": "mm / 6h", "status": p["status"],
                         "available_hours": p["available_hours"],
                         "init_time": p.get("init_time") or collection["forecast"].get("init_time"),
                         **{k: data[k] for k in ("retrieved_at", "source_table", "native_resolution", "statistic")}})
    windows = [{"at": f["at"], "valid_to": f["collection"]["scenario"]["valid_to"]} for f in data["frames"]]
    return {k: v for k, v in {**data, "rows": rows, "selected_index": index, "windows": windows,
                             "init_time": collection["forecast"].get("init_time") if collection else None,
                             "collection": collection}.items() if k != "frames"}


def export(source="archive", frame=None, format="csv"):
    if format not in ("csv", "geojson", "zip"):
        raise ValueError("Format must be csv, geojson or zip")
    data = report(source, frame)
    if not data["collection"]:
        raise ValueError(data.get("message", "No imported forecast is available"))
    output = io.StringIO(newline="")
    columns = list(data["rows"][0])
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    writer.writerows(data["rows"])
    csv_bytes = output.getvalue().encode("utf-8")
    cells = data["collection"]["weather_cells"]
    geojson = json.dumps({**cells, "features": [
        {**f, "properties": row} for f, row in zip(cells["features"], data["rows"])]}, allow_nan=False).encode()
    filename = f"quasar-{source}.{format}"
    if format == "csv":
        return csv_bytes, "text/csv; charset=utf-8", filename
    if format == "geojson":
        return geojson, "application/geo+json", filename
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("rainfall.csv", csv_bytes)
        archive.writestr("rainfall.geojson", geojson)
        archive.writestr("provenance.json", json.dumps({k: v for k, v in data.items() if k not in ("rows", "collection")}, allow_nan=False))
    return buffer.getvalue(), "application/zip", filename
