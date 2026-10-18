"""Synthetic checks for explicitly conditional, positive-FEMA-only modeling."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quasar.modeling import digest, read_json
from quasar.modeling import contracts, production, v2
from quasar.modeling.portable import validate
import test_modeling as fixtures
from test_modeling_v2 import OPTIONAL, pool


def positive_model():
    model = fixtures.model_fixture()
    model.update(model_version="mapped-susceptibility-v3-positive-synthetic",
                 evaluation_protocol=v2.POSITIVE_PROTOCOL["id"], inference_population="positive_fema_overlap")
    return model


class PositivePopulationTests(unittest.TestCase):
    def test_old_protocol_is_unchanged_and_positive_protocol_has_distinct_identity(self):
        self.assertEqual(v2.protocol_hash(), "6f373dd9a4427338cb3a1fd3f3c57b89024fef96c15c935e1034c3b0bd43bbf4")
        self.assertNotEqual(v2.protocol_hash(), v2.protocol_hash(v2.POSITIVE_PROTOCOL))
        self.assertEqual(v2.POSITIVE_PROTOCOL["gates"], v2.PROTOCOL["gates"])
        self.assertEqual(v2.POSITIVE_PROTOCOL["target_groups"], ["partial", "one"])

    def test_positive_pool_excludes_zeros_and_original_test_without_rewriting_source(self):
        with tempfile.TemporaryDirectory() as temp:
            directory, original = pool(Path(temp))
            hashes = {name: digest(directory/name) for name in ("dataset.sqlite3", "manifest.json", "test-evaluation.json")}
            rows, _ = v2.research_rows(directory, positive_only=True)
            self.assertEqual(rows, [r for r in original if r["target"] > 0])
            self.assertNotIn(9999, {r["parcel_id"] for r in rows})
            self.assertEqual(hashes, {name: digest(directory/name) for name in hashes})
            result = v2.summarize(rows, [r["target"] for r in rows], ["partial", "one"])
            self.assertEqual(result["macro_subgroup_mae"], 0)
            self.assertIsNone(result["target_ranges"]["zero"]["mae"])

    def test_population_identity_cannot_be_removed_or_changed(self):
        self.assertEqual(validate(positive_model())["inference_population"], "positive_fema_overlap")
        for change in (lambda m: m.pop("inference_population"),
                       lambda m: m.update(inference_population="countywide"),
                       lambda m: m.update(evaluation_protocol=v2.PROTOCOL_ID)):
            model = positive_model();change(model)
            with self.assertRaisesRegex(ValueError, "population identity"):
                validate(model)

    def test_zero_and_unknown_fema_are_unscored_without_invoking_the_regressor(self):
        model = positive_model()
        for fraction, expected in ((0., "excluded_zero_fema_overlap"), (None, "verified_positive_fema_overlap_required")):
            inputs = fixtures.inputs_record(1)
            inputs["fema"]["sfha_mapped_area_fraction"] = fraction
            with patch.object(production, "predict") as predict:
                record = production.assessment(1, inputs, [{"native_cell_id": "synthetic", "area_fraction": 1}], model, {"synthetic": 10})
            predict.assert_not_called()
            self.assertIsNone(record["score"])
            self.assertIn(expected, record["missing"])
        inputs = fixtures.inputs_record(1);inputs["fema"]["sfha_mapped_area_fraction"] = .01
        record = production.assessment(1, inputs, [{"native_cell_id": "synthetic", "area_fraction": 1}], model, {"synthetic": 0})
        self.assertEqual(record["score"], 0)
        self.assertEqual(record["missing"], [])

    def test_assessment_metadata_requires_positive_scope_and_cannot_claim_countywide(self):
        from quasar.modeling import NOTICE, POLICY, TARGET
        value = {"schema_version": 1, "model_version": positive_model()["model_version"], "target": TARGET,
                 "policy": POLICY, "promoted": True, "model_sha256": "a"*64, "notice": NOTICE,
                 "training_dataset_id": "b"*64, "evaluation_sha256": "c"*64,
                 "evaluation_protocol": v2.POSITIVE_PROTOCOL["id"], "inference_population": "positive_fema_overlap",
                 "evaluation_summary": {"macro_subgroup_mae": .1, "fully_mapped_mae": .1,
                                        "parcel_rmse": .1, "equal_block_rmse": .1, "coverage": .95}}
        self.assertEqual(contracts.metadata(value), value)
        del value["inference_population"]
        with self.assertRaisesRegex(ValueError, "population identity"):
            contracts.metadata(value)

    def test_local_and_proxy_population_validator_rejects_scored_zero_or_unknown(self):
        from quasar.exposure import validate_model_population
        context = {"model_metadata": {"inference_population": "positive_fema_overlap"}}
        for fraction in (0, None, -1, True):
            with self.assertRaisesRegex(ValueError, "excluded or unknown"):
                validate_model_population({"score": 5, "model_details": {"fema_mapped_area_fraction": fraction}}, context)
        validate_model_population({"score": None}, context)
        validate_model_population({"score": 5, "model_details": {"fema_mapped_area_fraction": .5}}, context)

    def test_qualification_requires_the_revised_population_and_two_groups(self):
        from test_modeling_v2 import evaluation
        report = evaluation()
        report.update(evaluation_protocol=v2.POSITIVE_PROTOCOL["id"], protocol_sha256=v2.protocol_hash(v2.POSITIVE_PROTOCOL),
                      inference_population="positive_fema_overlap", target_groups=["partial", "one"])
        self.assertTrue(all(v2.verify_evaluation(positive_model(), report).values()))
        report["target_groups"] = ["zero", "partial", "one"]
        with self.assertRaisesRegex(ValueError, "population mismatch"):
            v2.verify_evaluation(positive_model(), report)

    def test_requested_ridge_advisory_policy_preserves_other_gates(self):
        from test_modeling_v2 import evaluation
        report = evaluation()
        report["comparisons"]["ridge"]["parcel"]["rmse"] = .01
        report["comparisons"]["ridge"]["equal_block"]["rmse"] = .01
        model = positive_model()
        model.update(model_version="mapped-susceptibility-v4-positive-synthetic", evaluation_protocol=v2.POSITIVE_ADVISORY_PROTOCOL["id"])
        report.update(evaluation_protocol=v2.POSITIVE_ADVISORY_PROTOCOL["id"], protocol_sha256=v2.protocol_hash(v2.POSITIVE_ADVISORY_PROTOCOL),
                      target_groups=["partial", "one"], inference_population="positive_fema_overlap")
        report["gates"] = v2.acceptance(report["comparisons"], report["parity"], report["coverage"], ("constant_mean",))
        self.assertTrue(all(v2.verify_evaluation(model, report).values()))
        self.assertFalse(any("ridge" in key for key in report["gates"]))
        report["coverage"] = .1
        with self.assertRaises(ValueError):v2.verify_evaluation(model, report)

    def test_replay_cache_reuses_inference_but_keeps_rainfall_and_exclusion_dynamic(self):
        model = positive_model();cache = {};inputs = fixtures.inputs_record(1)
        overlaps = [{"native_cell_id": "synthetic", "area_fraction": 1}]
        with patch.object(production, "predict", wraps=production.predict) as predict:
            first = production.assessment(1, inputs, overlaps, model, {"synthetic": 10}, prediction_cache=cache)
            second = production.assessment(1, inputs, overlaps, model, {"synthetic": 20}, prediction_cache=cache)
            inputs["fema"]["sfha_mapped_area_fraction"] = 0
            excluded = production.assessment(1, inputs, overlaps, model, {"synthetic": 20}, prediction_cache=cache)
        self.assertEqual(predict.call_count, 1)
        self.assertNotEqual(first["score"], second["score"])
        self.assertIsNone(excluded["score"])


@unittest.skipUnless(OPTIONAL, "Optional local ML/GIS environment required")
class PositiveNativeExperimentTests(unittest.TestCase):
    def test_positive_training_uses_separate_ledger_and_excludes_zeros_from_every_fold(self):
        from shapely.geometry import box
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp);directory, original = pool(root)
            (directory/"v2-experiment.json").write_text('Frozen previous experiment')
            old_hash = digest(directory/"v2-experiment.json")
            geometry = {r["parcel_id"]: box(r["x"], 0, r["x"]+1, 1) for r in original}
            rows, manifest = v2.research_rows(directory, positive_only=True)
            tuned, tuning = v2._select(rows, geometry, True, ["partial", "one"])
            self.assertIsNotNone(tuned["inner_score"])
            self.assertEqual(len(tuning["folds"]), 3)
            audited = {"status": "verified", **{k: manifest[k] for k in ("inventory_id", "boundary_version", "checksums")}}
            selected = {"params": {"objective": "reg:squarederror", "max_depth": 2, "eta": .05, "nthread": 1}, "rounds": 2}
            with patch.object(v2, "audit", return_value=audited), patch.object(v2, "geometries_and_sources", return_value=geometry), \
                    patch.object(v2, "_select", return_value=(selected, {"selected": selected})):
                result = v2.train_positive(directory, root/"source", root/"inputs", root/"boundary", root/"inspection", root/"run")
            population = read_json(root/"run"/"population.json")
            eligible = {r["parcel_id"] for r in rows}
            self.assertEqual(set(population["included_ids"]), eligible)
            self.assertEqual(len(population["excluded_zero_ids"]), 80)
            for fold in read_json(root/"run"/"folds.json"):
                self.assertTrue(set(fold["fit"]) <= eligible)
                self.assertTrue(set(fold["held"]) <= eligible)
                for selection in (fold["candidate_selection"], fold["unweighted_selection"]):
                    self.assertIn("selected", selection)
            self.assertEqual(result["target_groups"], ["partial", "one"])
            self.assertEqual(result["comparisons"]["candidate"]["target_ranges"]["zero"]["count"], 0)
            self.assertEqual(old_hash, digest(directory/"v2-experiment.json"))
            self.assertTrue((directory/"v3-positive-experiment.json").is_file())
            from quasar.modeling.review import review
            result = review(root/"review", dataset=directory, experiment=root/"run")
            self.assertEqual(result["model_lineage"]["status"], "verified")
            self.assertEqual(result["model_lineage"]["inference_population"], "positive_fema_overlap")
            previous_evaluation = digest(root/"run"/"evaluation.json")
            revised = v2.qualify_positive(root/"run", root/"revised")
            self.assertFalse(any("ridge" in key for key in revised["gates"]))
            self.assertEqual(revised["comparisons"], read_json(root/"run"/"evaluation.json")["comparisons"])
            self.assertEqual(previous_evaluation, digest(root/"run"/"evaluation.json"))
            self.assertFalse(revised["promoted"])  # Small synthetic parity/support cannot be bypassed.
            self.assertEqual(digest(root/"run"/"member-0.json"), digest(root/"revised"/"member-0.json"))
