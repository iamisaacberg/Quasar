"""Synthetic artifacts only: no source downloads, host access or model claims."""
import copy
import importlib.util
import json
import os
import io
import sqlite3
import tempfile
import unittest
import zlib
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import test_api
from quasar import parcel_context as pc, parcels

CELL = "874452db5ffffff"
COARSE = "864452db7ffffff"
GEOMETRY = {"type": "Polygon", "coordinates": [[[-86.6,30.4],[-86.4,30.4],[-86.4,30.6],[-86.6,30.6],[-86.6,30.4]]]}
PARCEL = {"type": "Polygon", "coordinates": [[[-86.51,30.49],[-86.49,30.49],[-86.49,30.51],[-86.51,30.51],[-86.51,30.49]]]}


def fixture(root):
    boundary = root / "county.json"
    boundary.write_text(json.dumps({"features": [{"geometry": GEOMETRY, "properties": {"GEOID": "12091"}}]}))
    source = {"output_sha256": "parcel-snapshot", "source_url": "https://example.test/parcels", "retrieved_at": "2026-10-17T12:00:00Z",
              "county_boundary": {"sha256": pc.digest(boundary), "retrieved_at": "2026-10-17T12:00:00Z"},
              "terms_url": "https://example.test/terms", "crs": "EPSG:4326", "units": "degrees", "license": "Synthetic test fixture"}
    meta = {"county_fips": "12091", "h3_resolutions": [4,5,6,7], "cell_index_sha256": "cell-index", "source_provenance": source}
    database = root / "parcels.sqlite3"
    with closing(sqlite3.connect(database)) as db:
        db.executescript("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT); CREATE TABLE parcels(parcel_id INTEGER PRIMARY KEY,feature_z BLOB); CREATE TABLE county_cells(cell_id TEXT PRIMARY KEY,resolution INTEGER); CREATE TABLE cell_parcels(cell_id TEXT,parcel_id INTEGER,PRIMARY KEY(cell_id,parcel_id));")
        db.executemany("INSERT INTO metadata VALUES (?,?)", [(k,json.dumps(v)) for k,v in meta.items()])
        for identifier in (1,2):
            feature={"id": identifier,"geometry": PARCEL,"properties":{"parcel_id":identifier,"county_fips":"12091","risk_score":None,"risk_band":"unknown"}}
            db.execute("INSERT INTO parcels VALUES (?,?)",(identifier,zlib.compress(json.dumps(feature).encode())))
        db.executemany("INSERT INTO county_cells VALUES (?,?)",[(CELL,7),(COARSE,6)])
        # The same two parcels are members of both levels, not four distinct parcels.
        db.executemany("INSERT INTO cell_parcels VALUES (?,?)",[(cell,i) for cell in (CELL,COARSE) for i in (1,2)])
        db.commit()
    database.with_suffix(".sqlite3.manifest.json").write_text(json.dumps({"county_fips":"12091","database_sha256":pc.digest(database)}))
    inputs=root / "inputs";inputs.mkdir()
    with closing(sqlite3.connect(inputs / "parcel-inputs.sqlite3")) as db:
        db.execute("CREATE TABLE parcel_inputs(parcel_id INTEGER PRIMARY KEY,county_fips TEXT,inputs_json TEXT)")
        for identifier in (1,2):
            record={"parcel_id":identifier,"county_fips":"12091","risk_score":None,"risk_band":"unknown",
                    "terrain":{"status":"complete" if identifier==1 else "no_pixel_centers","min_m":0 if identifier==1 else None},
                    "fema":{"status":"partial" if identifier==1 else "complete"},"hydrography":{"status":"partial_reference_coverage"}}
            db.execute("INSERT INTO parcel_inputs VALUES (?,?,?)",(identifier,"12091",json.dumps(record)))
        db.commit()
    parent={"county_fips":"12091","sources":{"parcels":source,"boundary_sha256":pc.digest(boundary)},
            "terrain":{"source_date_range":["2019","2022"]},"fema":{"later_revision_completeness":"unverified"},"hydrography":{},
            "artifacts":[{"path":"parcel-inputs.sqlite3","sha256":pc.digest(inputs / "parcel-inputs.sqlite3")} ]}
    (inputs / "manifest.json").write_text(json.dumps(parent))
    return database,inputs,boundary,meta


class ParcelContextTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.database,self.inputs,self.boundary,self.meta=fixture(self.root)
        self.output=self.root / "inspection";self.output.mkdir()
        with closing(sqlite3.connect(self.output / "inspection.sqlite3")) as db:
            db.execute("CREATE TABLE inspection(kind TEXT,identifier TEXT,context_json TEXT,PRIMARY KEY(kind,identifier))")
            context={"county_fips":"12091","parcel_id":1,"risk_score":None,"inputs":{"terrain":{"status":"partial"}},"forecast_overlaps":[]}
            db.execute("INSERT INTO inspection VALUES ('parcel','1',?)",(json.dumps(context),));db.commit()
        self.manifest={"schema_version":1,"county_fips":"12091","inventory_id":"parcel-snapshot","cell_index_version":"cell-index",
                       "boundary_version":pc.digest(self.boundary),"database_sha256":pc.digest(self.output / "inspection.sqlite3"),
                       "prepared_at":"2026-10-17T12:00:00Z","provenance":{"fema":{"later_revision_completeness":"unverified"}}}
        self.write_manifest()
        self.env=patch.dict(os.environ,{"QUASAR_PARCEL_DATABASE":str(self.database),"QUASAR_PARCEL_CONTEXT_DIRECTORY":str(self.output),"QUASAR_LINUXONE_API_URL":""})
        self.env.start();self.addCleanup(self.env.stop)

    def write_manifest(self):
        (self.output / "manifest.json").write_text(json.dumps(self.manifest))

    def test_context_keeps_descriptive_coverage_unknown_score_and_provenance(self):
        result=pc.inspection("parcel","1","parcel-snapshot")
        self.assertIsNone(result["risk_score"]);self.assertEqual(result["risk_band"],"unknown")
        self.assertEqual(result["inputs"]["terrain"]["status"],"partial")
        self.assertEqual(result["provenance"]["fema"]["later_revision_completeness"],"unverified")

    def test_bad_identity_missing_records_and_changed_inventory(self):
        for kind,identifier in (("parcel","-1"),("parcel","1/other"),("cell","bad"),("cell","834452db5ffffff")):
            with self.subTest(identifier=identifier),self.assertRaises(ValueError):pc.inspection(kind,identifier)
        with self.assertRaises(ValueError):pc.inspection("parcel","999")
        with self.assertRaises(parcels.SourceUnavailable):pc.inspection("parcel","1","other-snapshot")

    def test_wrong_county_boundary_inventory_index_and_checksum_fail_closed(self):
        for key,value in (("county_fips","12086"),("boundary_version","different"),("inventory_id","other"),
                          ("cell_index_version","other"),("database_sha256","bad")):
            original=copy.deepcopy(self.manifest);self.manifest[key]=value;self.write_manifest()
            with self.subTest(key=key),self.assertRaises(parcels.SourceUnavailable):pc.inspection("parcel","1")
            self.manifest=original
        self.write_manifest()
        with (self.output / "inspection.sqlite3").open("ab") as stream:stream.write(b"corruption")
        with self.assertRaises(parcels.SourceUnavailable):pc.inspection("parcel","1")

    def test_incomplete_artifact_and_missing_configuration_are_unavailable(self):
        (self.output / "manifest.json").unlink()
        with self.assertRaises(parcels.SourceUnavailable):pc.inspection("parcel","1")
        with patch.dict(os.environ,{"QUASAR_PARCEL_CONTEXT_DIRECTORY":""}),self.assertRaises(parcels.SourceUnavailable):pc.inspection("parcel","1")

    def test_manifest_versions_geometry_and_index_without_loading_polygons(self):
        result=parcels.parcel_manifest()
        self.assertEqual(result["dataset_version"],"parcel-snapshot:cell-index")
        self.assertEqual(result["boundary_version"],pc.digest(self.boundary))
        self.assertEqual(result["inventory_id"],"parcel-snapshot")


class InspectionApiTests(unittest.TestCase):
    setUpClass=classmethod(test_api.ApiTests.setUpClass.__func__)
    tearDownClass=classmethod(test_api.ApiTests.tearDownClass.__func__)
    request=test_api.ApiTests.request

    def test_proxy_pages_reach_authenticated_indexed_host_with_full_query(self):
        """Only HTTPS transport is redirected; exercise the real host handler/DB."""
        from urllib.parse import urlsplit, parse_qs
        from urllib.request import Request, urlopen
        from test_parcels import RING
        token = "synthetic-test-token-" * 2
        with tempfile.TemporaryDirectory() as folder:
            database, _, _, _ = fixture(Path(folder))
            with closing(sqlite3.connect(database)) as db:
                for identifier in range(3, 103):
                    feature = {"type": "Feature", "id": identifier, "geometry": PARCEL,
                               "properties": {"parcel_id": identifier, "county_fips": "12091",
                                              "risk_score": None, "risk_band": "unknown"}}
                    db.execute("INSERT INTO parcels VALUES (?,?)", (identifier, zlib.compress(json.dumps(feature).encode())))
                    db.execute("INSERT INTO cell_parcels VALUES (?,?)", (CELL, identifier))
                db.commit()

            def host(request, timeout):
                url = urlsplit(request.full_url)
                query = parse_qs(url.query)
                self.assertEqual(json.loads(query["ring"][0]), RING)
                self.assertEqual(query["cell"], [CELL])
                self.assertEqual(query["inventory_id"], ["parcel-snapshot"])
                self.assertNotIn(token, request.full_url)
                forwarded = Request(f"http://127.0.0.1:{self.server.server_port}{url.path}?{url.query}",
                                    headers=dict(request.header_items()))
                # The actual source host has a database, not another proxy.
                with patch.dict(os.environ, {"QUASAR_LINUXONE_API_URL": ""}):
                    with urlopen(forwarded, timeout=timeout) as response:
                        return io.BytesIO(response.read())

            with patch.dict(os.environ, {"QUASAR_PARCEL_DATABASE": str(database),
                    "QUASAR_PARCEL_API_TOKEN": token, "QUASAR_LINUXONE_API_URL": "https://example.test",
                    "QUASAR_LINUXONE_API_TOKEN": token}), \
                    patch.object(parcels, "county_boundary", return_value={"features": [{"geometry": GEOMETRY}]}), \
                    patch.object(parcels, "build_opener") as opener:
                opener.return_value.open.side_effect = host
                first = parcels.parcel_page(json.dumps(RING), "0", "parcel-snapshot", CELL)
                last = parcels.parcel_page(json.dumps(RING), str(first["next_offset"]), "parcel-snapshot", CELL)
                self.assertEqual(len(first["features"]), 100)
                self.assertEqual(len(last["features"]), 2)
                self.assertEqual(last["checked_count"], 102)
                self.assertIsNone(last["next_offset"])
                self.assertEqual({f["id"] for page in (first, last) for f in page["features"]}, set(range(1, 103)))
                self.assertEqual(self.request(f"/api/parcels?cell={CELL}")[0], 401)

    def test_missing_inputs_bad_scope_and_ids(self):
        with patch.dict(os.environ,{"QUASAR_PARCEL_CONTEXT_DIRECTORY":"","QUASAR_PARCEL_DATABASE":"","QUASAR_LINUXONE_API_URL":""}):
            for path in ("/api/parcels/1/context",f"/api/cells/{CELL}/summary"):
                status,body,_=self.request(path);self.assertEqual(status,502);self.assertEqual(json.loads(body)["status"],"unavailable")
            for path in ("/api/parcels/-1/context","/api/cells/bad/summary","/api/parcels/1/context?county_fips=12086"):
                self.assertEqual(self.request(path)[0],400)

    def test_all_routes_retain_parcel_authentication(self):
        with patch.dict(os.environ,{"QUASAR_PARCEL_API_TOKEN":"x"*32,"QUASAR_PARCEL_DATABASE":"indexed"}):
            for path in ("/api/parcels/manifest","/api/parcels/1/context",f"/api/cells/{CELL}/summary"):
                self.assertEqual(self.request(path)[0],401)

    @patch("quasar.server.remote_inspection",return_value={"status":"ready","county_fips":"12091","risk_score":None})
    def test_proxy_uses_fixed_routes_and_server_only_auth(self,remote):
        with patch.dict(os.environ,{"QUASAR_LINUXONE_API_URL":"https://example.test","QUASAR_PARCEL_DATABASE":""}):
            self.assertEqual(self.request("/api/parcels/1/context?inventory_id=snapshot")[0],200)
            remote.assert_called_once_with("/api/parcels/1/context","snapshot")

    def test_proxy_validates_scope_unknown_scores_and_keeps_token_in_server_header(self):
        result={"status":"ready","county_fips":"12091","risk_score":None,"risk_band":"unknown","inventory_id":"snapshot"}
        with patch.dict(os.environ,{"QUASAR_LINUXONE_API_URL":"https://example.test","QUASAR_LINUXONE_API_TOKEN":"x"*32}):
            for changed in ({}, {"county_fips":"12086"}, {"risk_score":0}, {"inventory_id":"other"}):
                response=io.BytesIO(json.dumps({**result,**changed}).encode())
                with patch.object(parcels,"build_opener") as opener:
                    opener.return_value.open.return_value=response
                    if changed:
                        with self.assertRaises(parcels.SourceUnavailable):parcels.remote_inspection("/api/parcels/1/context","snapshot")
                    else:
                        self.assertEqual(parcels.remote_inspection("/api/parcels/1/context","snapshot")["risk_band"],"unknown")
                        request=opener.return_value.open.call_args.args[0]
                        self.assertNotIn("x"*32,request.full_url)
                        self.assertIn("x"*32,request.headers.values())


@unittest.skipUnless(importlib.util.find_spec("shapely") and importlib.util.find_spec("pyproj"),"Optional local GIS preparation environment")
class OfflineInspectionTests(unittest.TestCase):
    def test_fips_tag_does_not_substitute_for_exact_county_containment(self):
        from quasar.inspection_prepare import prepare
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);database,inputs,boundary,_=fixture(root)
            outside={"type":"Polygon","coordinates":[[[-80,25],[-79,25],[-79,26],[-80,25]]]}
            with closing(sqlite3.connect(database)) as db:
                feature={"id":1,"geometry":outside,"properties":{"county_fips":"12091","parcel_id":1}}
                db.execute("UPDATE parcels SET feature_z=? WHERE parcel_id=1",(zlib.compress(json.dumps(feature).encode()),));db.commit()
            database.with_suffix(".sqlite3.manifest.json").write_text(json.dumps({"county_fips":"12091","database_sha256":pc.digest(database)}))
            with self.assertRaisesRegex(ValueError,"outside exact county"):
                prepare(database,inputs,boundary,[],root / "rejected")
            self.assertFalse((root / "rejected/manifest.json").exists())

    def test_preparation_preserves_inputs_counts_distinct_parcels_and_native_overlaps(self):
        from quasar.inspection_prepare import prepare
        from quasar.adapters.county_weather import normalize
        from datetime import datetime,timezone,timedelta
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);database,inputs,boundary,meta=fixture(root)
            now=datetime(2026,10,17,12,tzinfo=timezone.utc)
            geometries=[{"type":"Polygon","coordinates":[[[-86.6,30.4],[-86.5,30.4],[-86.5,30.6],[-86.6,30.6],[-86.6,30.4]]]},
                        {"type":"Polygon","coordinates":[[[-86.5,30.4],[-86.4,30.4],[-86.4,30.6],[-86.5,30.6],[-86.5,30.4]]]}]
            from shapely.geometry import shape
            rows=[{"native_cell_wkt":shape(g).wkt,"native_cell_geojson":json.dumps(g),"init_time":now.isoformat(),
                   "forecast_time":(now+timedelta(hours=h)).isoformat(),"rainfall_1h_mm":0} for g in geometries for h in range(1,7)]
            import test_county_weather
            snapshot=normalize(rows,test_county_weather.TABLE,GEOMETRY,valid_from=now.isoformat(),now=now)
            weather=root / "weather.json";weather.write_text(json.dumps(snapshot))
            output=root / "inspection"
            prepare(database,inputs,boundary,[weather],output)
            with patch.dict(os.environ,{"QUASAR_PARCEL_DATABASE":str(database),"QUASAR_PARCEL_CONTEXT_DIRECTORY":str(output)}):
                parcel=pc.inspection("parcel","1");summary=pc.inspection("cell",COARSE)
            self.assertEqual(len(parcel["forecast_overlaps"]),2)
            self.assertAlmostEqual(sum(c["area_fraction"] for c in parcel["forecast_overlaps"]),1,places=5)
            self.assertEqual(parcel["inputs"]["terrain"]["min_m"],0)
            self.assertEqual(summary["parcel_count"],2)
            self.assertEqual(summary["terrain_complete_count"],1)
            self.assertEqual(summary["fema_complete_count"],1)
            self.assertEqual(summary["fema_partial_count"],1)
            self.assertIsNone(parcel["risk_score"])
            with self.assertRaises(FileExistsError):prepare(database,inputs,boundary,[weather],output)
