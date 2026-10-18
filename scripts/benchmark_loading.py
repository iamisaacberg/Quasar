"""Offline, synthetic dense-cell benchmark. No server or real-source access."""
import json
import os
import sqlite3
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quasar import exposure
from quasar.exposure_store import prepare, _verified


def timings(function, count=30):
    samples = []
    for _ in range(count):
        start = time.perf_counter()
        function()
        samples.append((time.perf_counter() - start) * 1000)
    return {"median_ms": round(statistics.median(samples), 3), "p95_ms": round(sorted(samples)[int((len(samples)-1)*.95)], 3), "samples": count}


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        inventory, artifact, serving = root/"synthetic.sqlite3", root/"synthetic.json", root/"serving.sqlite3"
        with sqlite3.connect(inventory) as db:
            db.executescript("CREATE TABLE metadata(key TEXT,value TEXT); CREATE TABLE parcels(parcel_id INTEGER PRIMARY KEY); CREATE TABLE county_cells(cell_id TEXT PRIMARY KEY,resolution INTEGER); CREATE TABLE cell_parcels(cell_id TEXT,parcel_id INTEGER,PRIMARY KEY(cell_id,parcel_id));")
            db.executemany("INSERT INTO metadata VALUES(?,?)", [("county_fips", '"12091"'), ("source_provenance", json.dumps({"output_sha256": "synthetic-only", "county_boundary": {"sha256": "synthetic-only"}}))])
            db.executemany("INSERT INTO parcels VALUES(?)", ((i,) for i in range(3165)))
            for resolution in range(4,8):
                db.execute("INSERT INTO county_cells VALUES(?,?)", (f"synthetic-r{resolution}",resolution))
                db.executemany("INSERT INTO cell_parcels VALUES(?,?)", ((f"synthetic-r{resolution}",i) for i in range(3165)))
        start, end = "2026-10-09T05:00:00Z", "2026-10-09T11:00:00Z"
        artifact.write_text(json.dumps({"schema_version":1,"county_fips":"12091","run_id":"synthetic-only","inventory_id":"synthetic-only","method_version":"synthetic-only","windows":[{"valid_from":start,"valid_to":end,"computed_at":datetime.now(timezone.utc).isoformat(),"parcels":[{"parcel_id":i,"score":None if i%10==0 else 50,"factors":[] if i%10==0 else [{"name":"synthetic","value":50,"contribution":50}],"missing":["synthetic_unknown"] if i%10==0 else []} for i in range(3165)]}]}))
        os.environ.update(QUASAR_LINUXONE_API_URL="",QUASAR_PARCEL_DATABASE=str(inventory),QUASAR_EXPOSURE_FILE=str(artifact),QUASAR_EXPOSURE_DIRECTORY="",QUASAR_EXPOSURE_DATABASE="")
        query={"from":start,"to":end,"mode":"replay","parcel_ids":"1,2,3,4"}
        baseline=exposure.exposure(query)
        def cold_legacy():
            exposure._artifact.cache_clear();exposure._aggregate.cache_clear()
            return exposure.exposure(query)
        report={"label":"Synthetic 3,165-parcel fixture; not production or browser performance", "legacy_cold":timings(cold_legacy,10)}
        prepare(inventory,artifact,serving)
        os.environ["QUASAR_EXPOSURE_DATABASE"]=str(serving)
        if exposure.exposure(query)!=baseline:
            raise AssertionError("Prepared/legacy parity failed")
        def cold_prepared():
            _verified.cache_clear()
            return exposure.exposure(query)
        report.update(prepared_cold=timings(cold_prepared,10),prepared_warm=timings(lambda:exposure.exposure(query),50),parity=True)
        print(json.dumps(report,indent=2))


if __name__ == "__main__":
    main()
