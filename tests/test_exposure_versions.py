"""Synthetic version routing: explicit choices never borrow another model's data."""
import copy
import json
import os
import unittest
from io import BytesIO
from unittest.mock import patch

from quasar import exposure
from quasar.modeling import read_json, write_json
from quasar.modeling import production
import test_modeling as fixtures
import test_county_weather as weather_fixture
import test_modeling_v2 as v2_fixtures


class ExposureVersionTests(unittest.TestCase):
    setUp = fixtures.AuditAndProducerTests.setUp

    def artifacts(self):
        model, evaluation, _ = v2_fixtures.LineageAndServingTests.prepare_v2(self)
        artifact = self.root/"v2.json"
        production.produce(self.database, self.inputs, self.boundary, self.inspection, model, evaluation,
                           self.weather, weather_fixture.iso(weather_fixture.INIT), "current", artifact, now=weather_fixture.NOW)
        data = read_json(artifact)
        original = copy.deepcopy(data)
        original["model_metadata"]["model_version"] = "mapped-susceptibility-v1-synthetic"
        original["run_id"] = "original-run"
        legacy = self.root/"v1.json";write_json(legacy, original)
        self.env = {"QUASAR_LINUXONE_API_URL": "", "QUASAR_PARCEL_DATABASE": str(self.database),
                    "QUASAR_EXPOSURE_V1_FILE": str(legacy), "QUASAR_EXPOSURE_V1_DIRECTORY": "",
                    "QUASAR_EXPOSURE_V2_FILE": str(artifact), "QUASAR_EXPOSURE_V2_DIRECTORY": "",
                    "QUASAR_EXPOSURE_V1_MODEL_VERSION": "mapped-susceptibility-v1-synthetic",
                    "QUASAR_EXPOSURE_V2_MODEL_VERSION": "mapped-susceptibility-v2-synthetic"}
        self.query = {"from": data["windows"][0]["valid_from"], "to": data["windows"][0]["valid_to"],
                      "mode": "replay", "parcel_ids": "1"}
        self.addCleanup(exposure._aggregate.cache_clear);self.addCleanup(exposure._artifact.cache_clear)

    def test_explicit_versions_select_their_own_artifact_and_identity(self):
        self.artifacts()
        with patch.dict(os.environ, self.env):
            first = exposure.exposure({**self.query, "model": "v1"})
            second = exposure.exposure({**self.query, "model": "v2"})
            self.assertEqual(first["model_choice"], "v1")
            self.assertEqual(first["run_id"], "original-run")
            self.assertEqual(second["model_choice"], "v2")
            self.assertEqual(second["model_metadata"]["model_version"], "mapped-susceptibility-v2-synthetic")
            self.assertNotEqual(first["run_id"], second["run_id"])
            for value in ("v3", "../v1", ""):
                with self.assertRaises(ValueError):exposure.exposure({**self.query, "model": value})
        with patch.dict(os.environ, {**self.env, "QUASAR_EXPOSURE_V2_MODEL_VERSION": "wrong-model"}):
            self.assertEqual(exposure.exposure({**self.query, "model": "v2"})["status"], "unavailable")
        with patch.dict(os.environ, {**self.env, "QUASAR_EXPOSURE_V2_FILE": "", "QUASAR_EXPOSURE_FILE": self.env["QUASAR_EXPOSURE_V1_FILE"]}):
            self.assertEqual(exposure.exposure({**self.query, "model": "v2"})["status"], "not_configured")

    def test_proxy_forwards_choice_and_rejects_wrong_or_unlabeled_response(self):
        self.artifacts()
        with patch.dict(os.environ, self.env):
            remote = exposure.exposure({**self.query, "model": "v2"})
        with patch.dict(os.environ, {**self.env, "QUASAR_LINUXONE_API_URL": "https://linuxone.example", "QUASAR_LINUXONE_API_TOKEN": "x"*32}):
            with patch.object(exposure, "build_opener") as opener:
                opener.return_value.open.return_value = BytesIO(json.dumps(remote).encode())
                result = exposure.exposure({**self.query, "model": "v2"})
                self.assertEqual(result["model_choice"], "v2")
                self.assertIn("model=v2", opener.return_value.open.call_args.args[0].full_url)
            for value in ("v1", None):
                bad = {**remote, "model_choice": value}
                with patch.object(exposure, "build_opener") as opener:
                    opener.return_value.open.return_value = BytesIO(json.dumps(bad).encode())
                    with self.assertRaises(exposure.SourceUnavailable):exposure.exposure({**self.query, "model": "v2"})
