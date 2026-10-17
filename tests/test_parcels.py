"""Exercise county GIS pagination, geography and source failure contracts offline."""
import json
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from quasar import parcels
import test_api


def polygon(ring):
    return {"type": "Polygon", "coordinates": [ring]}


COUNTY = polygon([[-86.6,30.4],[-86.4,30.4],[-86.4,30.6],[-86.6,30.6],[-86.6,30.4]])
RING = [[-86.51,30.49],[-86.5,30.49],[-86.495,30.5],[-86.5,30.51],[-86.51,30.51],[-86.515,30.5],[-86.51,30.49]]
PARCEL = polygon([[-86.51,30.49],[-86.5,30.49],[-86.5,30.5],[-86.51,30.5],[-86.51,30.49]])
BOUNDARY = {"type":"FeatureCollection", "county_fips":"12091", "retrieved_at":"2026-10-17T12:00:00Z", "features":[{"type":"Feature","geometry":COUNTY,"properties":{"GEOID":"12091"}}]}


class ParcelTests(unittest.TestCase):
    def setUp(self):
        parcels._ids_cache.clear()
        parcels._county.cache_clear()

    def source(self, url, params):
        if params.get("returnIdsOnly") == "true":
            self.assertEqual(params["spatialRel"], "esriSpatialRelIntersects")
            return {"objectIds": list(range(1, 102))}
        self.assertEqual(params["outFields"], "OBJECTID")
        return {"features":[{"type":"Feature", "geometry":PARCEL,
                             "properties":{"OBJECTID":int(i),"FOLIO":str(i),"TRUE_OWNER1":"must not escape"}}
                            for i in params["objectIds"].split(",")]}

    @patch.object(parcels, "county_boundary", return_value=BOUNDARY)
    def test_all_pages_preserve_unknown_scores_and_strip_extra_fields(self, _):
        with patch.object(parcels, "_get", side_effect=self.source) as get:
            first = parcels.parcel_page(json.dumps(RING))
            last = parcels.parcel_page(json.dumps(RING), "100")
        self.assertEqual(len(first["features"]),100)
        self.assertEqual(first["next_offset"],100)
        self.assertEqual(last["checked_count"],101)
        self.assertIsNone(last["next_offset"])
        self.assertEqual(get.call_count,3)
        for feature in first["features"]:
            self.assertIsNone(feature["properties"]["risk_score"])
            self.assertNotIn("TRUE_OWNER1",feature["properties"])

    def test_geometry_rejects_outside_crossing_holes_and_malformed(self):
        self.assertTrue(parcels._covered(PARCEL, COUNTY))
        self.assertFalse(parcels._covered(polygon([[-86.7,30.5],[-86.5,30.5],[-86.5,30.51],[-86.7,30.5]]),COUNTY))
        county_hole = {**COUNTY,"coordinates":COUNTY["coordinates"] + [[[-86.507,30.493],[-86.503,30.493],[-86.503,30.497],[-86.507,30.497],[-86.507,30.493]]]}
        self.assertFalse(parcels._covered(PARCEL,county_hole))
        self.assertFalse(parcels._covered(None,COUNTY))
        # All vertices are inside, but an edge crosses a concave county notch.
        concave = polygon([[0,0],[4,0],[4,4],[3,4],[3,1],[1,1],[1,4],[0,4],[0,0]])
        crossing = polygon([[.5,2],[3.5,2],[3.5,3],[.5,3],[.5,2]])
        self.assertFalse(parcels._covered(crossing,concave))

    @patch.object(parcels, "county_boundary", return_value=BOUNDARY)
    def test_empty_inventory_and_unavailable_inventory_differ(self, _):
        with patch.object(parcels,"_get",return_value={"objectIds":[]}):
            result=parcels.parcel_page(json.dumps(RING))
            self.assertEqual(result["source_total"],0)
            self.assertIsNone(result["next_offset"])
        parcels._ids_cache.clear()
        with patch.object(parcels,"_get",return_value={}):
            with self.assertRaises(parcels.SourceUnavailable):
                parcels.parcel_page(json.dumps(RING))

    @patch.object(parcels, "county_boundary", return_value=BOUNDARY)
    def test_incomplete_source_page_is_an_error(self, _):
        with patch.object(parcels,"_get",side_effect=[{"objectIds":[1,2]},{"features":[{"properties":{"OBJECTID":1},"geometry":PARCEL}]}]):
            with self.assertRaises(parcels.SourceUnavailable):
                parcels.parcel_page(json.dumps(RING))

    @patch.object(parcels, "county_boundary", return_value=BOUNDARY)
    def test_county_validation_exclusions_are_counted(self, _):
        outside=polygon([[-86.8,30.5],[-86.7,30.5],[-86.7,30.6],[-86.8,30.5]])
        with patch.object(parcels,"_get",side_effect=[{"objectIds":[1]},{"features":[{"properties":{"OBJECTID":1},"geometry":outside}]}]):
            result=parcels.parcel_page(json.dumps(RING))
        self.assertEqual(result["features"],[])
        self.assertEqual(result["excluded_count"],1)
        self.assertEqual(result["source_total"],1)

    def test_bad_query_never_calls_source(self):
        with patch.object(parcels,"_get") as get:
            for ring in ["bad","[]",json.dumps([[0,0]]*7),json.dumps([[True,30.5]]*7)]:
                with self.assertRaises(ValueError): parcels.parcel_page(ring)
            for offset in ["-100","1","nope"]:
                with self.assertRaises(ValueError): parcels.parcel_page(json.dumps(RING),offset)
            get.assert_not_called()

    def test_wrong_county_identity_is_unavailable(self):
        wrong={"features":[{"properties":{"GEOID":"12011"},"geometry":COUNTY}]}
        with patch.object(parcels,"_get",return_value=wrong):
            with self.assertRaises(parcels.SourceUnavailable): parcels.county_boundary()

    @patch.object(parcels, "county_boundary", return_value=BOUNDARY)
    def test_changed_inventory_is_not_silently_paged(self, _):
        with patch.object(parcels,"_get",return_value={"objectIds":[1,2]}):
            with self.assertRaises(parcels.SourceUnavailable):
                parcels.parcel_page(json.dumps(RING),"0","previous-inventory")


class ParcelApiTests(unittest.TestCase):
    setUpClass = classmethod(test_api.ApiTests.setUpClass.__func__)
    tearDownClass = classmethod(test_api.ApiTests.tearDownClass.__func__)
    request = test_api.ApiTests.request
    @patch("quasar.server.county_boundary", return_value=BOUNDARY)
    def test_boundary_route(self, _):
        status,body,_=self.request("/api/county")
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)["county_fips"],"12091")

    @patch("quasar.server.parcel_page", side_effect=parcels.SourceUnavailable("GIS unavailable"))
    def test_parcel_source_failure_returns_502(self, _):
        status,body,_=self.request("/api/parcels?"+urlencode({"ring":json.dumps(RING)}))
        self.assertEqual(status,502)
        self.assertEqual(json.loads(body)["status"],"unavailable")

    def test_parcel_route_rejects_bad_input_and_other_counties(self):
        self.assertEqual(self.request("/api/parcels?ring=[]")[0],400)
        self.assertEqual(self.request("/api/county?county_fips=12011")[0],400)


class RemoteCountyTests(unittest.TestCase):
    @patch.object(parcels,"county_boundary",return_value=BOUNDARY)
    def test_remote_pages_require_county_geometry_and_preserve_unknown(self,_):
        import copy
        feature={"type":"Feature","geometry":PARCEL,"properties":{"parcel_id":1,"county_fips":"12091","risk_score":None,"risk_band":"unknown","owner":"strip"}}
        page={"county_fips":"12091","features":[feature]}
        parcels.validate_remote_page(page)
        self.assertNotIn("owner",feature["properties"])
        for change in ("county","geometry","score"):
            bad=copy.deepcopy(page)
            if change=="county":bad["county_fips"]="12086"
            elif change=="score":bad["features"][0]["properties"]["risk_score"]=0
            else:bad["features"][0]["geometry"]={"type":"Polygon","coordinates":[[[-80,25],[-79,25],[-79,26],[-80,25]]]}
            with self.subTest(change=change),self.assertRaises(ValueError):parcels.validate_remote_page(bad)
