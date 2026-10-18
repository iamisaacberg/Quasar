"""Bounded numeric-tree format and standard-library scoring; no XGBoost on the server."""
import math
import struct

from . import FEATURES, TARGET, finite, read_json


def float32(value):
    # XGBoost compares float32 input values, including at exact split boundaries.
    return struct.unpack("f", struct.pack("f", value))[0]


def validate(model):
    if (not isinstance(model, dict) or model.get("schema_version") != 1
            or model.get("county_fips") != "12091" or model.get("features") != FEATURES
            or model.get("objective") != "reg:squarederror" or model.get("target") != TARGET
            or not isinstance(model.get("model_version"), str) or not model["model_version"]
            or not isinstance(model.get("training_dataset_id"), str)
            or not isinstance(model.get("inventory_id"), str)
            or not isinstance(model.get("boundary_version"), str)
            or type(model.get("promoted")) is not bool):
        raise ValueError("Unsupported portable model identity/features/objective")
    bounds = model.get("feature_ranges")
    if (not isinstance(bounds, list) or len(bounds) != len(FEATURES)
            or any(not isinstance(b, list) or len(b) != 2 or not all(finite(x) for x in b)
                   or b[0] > b[1] or max(abs(x) for x in b) > 3.4e38 for b in bounds)):
        raise ValueError("Invalid training feature ranges")
    members = model.get("members")
    if not isinstance(members, list) or len(members) != 5:
        raise ValueError("Five ensemble members required")
    for member in members:
        if not isinstance(member, dict) or not finite(member.get("bias")) or not isinstance(member.get("trees"), list) or not 1 <= len(member["trees"]) <= 400:
            raise ValueError("Invalid ensemble member")
        for tree in member["trees"]:
            if not isinstance(tree, list) or not 1 <= len(tree) <= 511:
                raise ValueError("Oversized/malformed tree")
            seen = set()
            def walk(index, depth=0):
                if type(index) is not int or index < 0 or index >= len(tree) or index in seen or depth > 8:
                    raise ValueError("Invalid tree topology")
                seen.add(index)
                node = tree[index]
                if not isinstance(node, dict) or not finite(node.get("expected")):
                    raise ValueError("Invalid tree node")
                if "leaf" in node:
                    if set(node) != {"leaf", "expected"} or not finite(node["leaf"]) or node["leaf"] != node["expected"]:
                        raise ValueError("Invalid leaf")
                else:
                    if (set(node) != {"feature", "threshold", "left", "right", "expected"}
                            or type(node["feature"]) is not int or not 0 <= node["feature"] < len(FEATURES)
                            or not finite(node["threshold"])):
                        raise ValueError("Unsupported split")
                    walk(node["left"], depth+1)
                    walk(node["right"], depth+1)
            walk(0)
            if len(seen) != len(tree):
                raise ValueError("Unreachable nodes")
    return model


def load(path):
    return validate(read_json(path, 32 * 1024 * 1024))


def predict(model, values):
    if (not isinstance(values, list) or len(values) != len(FEATURES)
            or not all(finite(x) for x in values)):
        return {"susceptibility": None, "missing": ["model_features"]}
    if any(not low <= x <= high for x, (low, high) in zip(values, model["feature_ranges"])):
        return {"susceptibility": None, "missing": ["outside_training_ranges"]}
    values = [float32(x) for x in values]
    predictions, raw_predictions = [], []
    baseline, contributions = 0., [0.] * len(FEATURES)
    for member in model["members"]:
        raw = member["bias"]
        baseline += member["bias"] / len(model["members"])
        for tree in member["trees"]:
            node = tree[0]
            baseline += node["expected"] / len(model["members"])
            while "leaf" not in node:
                feature = node["feature"]
                child = tree[node["left"] if values[feature] < node["threshold"] else node["right"]]
                contributions[feature] += (child["expected"] - node["expected"]) / len(model["members"])
                node = child
            raw += node["leaf"]
        raw_predictions.append(raw)
        predictions.append(max(0., min(1., raw)))
    mean = sum(predictions) / len(predictions)
    return {"susceptibility": mean, "raw_susceptibility": sum(raw_predictions) / len(predictions),
            "model_instability": math.sqrt(sum((x-mean)**2 for x in predictions) / len(predictions)),
            "baseline": baseline, "attributions": dict(zip(FEATURES, contributions)), "missing": []}


def export_saved(saved, metadata):
    """Convert XGBoost save_model JSON, never an untrusted pickle or dump_model."""
    members = []
    for data in saved:
        learner = data["learner"]
        params = learner["learner_model_param"]
        gradient = learner["gradient_booster"]
        if (learner["objective"]["name"] != "reg:squarederror" or gradient["name"] != "gbtree"
                or int(params["num_feature"]) != len(FEATURES) or int(params["num_target"]) != 1
                or learner.get("feature_names") != FEATURES):
            raise ValueError("Only scalar numeric regression trees are exportable")
        bias = params["base_score"]
        bias = float(bias.strip("[]"))
        trees = []
        for source in gradient["model"]["trees"]:
            if any(source["split_type"]) or source.get("categories") or source["tree_param"].get("size_leaf_vector", "1") not in ("0", "1"):
                raise ValueError("Categorical/vector trees are unsupported")
            tree = []
            for i, left in enumerate(source["left_children"]):
                if left == -1:
                    tree.append({"leaf": source["split_conditions"][i], "expected": source["split_conditions"][i]})
                else:
                    tree.append({"feature": source["split_indices"][i], "threshold": float32(source["split_conditions"][i]),
                                 "left": left, "right": source["right_children"][i], "expected": 0.})
            visited = set()
            def expected(i):
                if i in visited or not 0 <= i < len(tree):
                    raise ValueError("Malformed saved tree")
                visited.add(i)
                node = tree[i]
                if "leaf" not in node:
                    left, right = node["left"], node["right"]
                    a, b = expected(left), expected(right)
                    wa, wb = source["sum_hessian"][left], source["sum_hessian"][right]
                    if not finite(wa) or not finite(wb) or wa < 0 or wb < 0 or wa+wb <= 0:
                        raise ValueError("Invalid training cover")
                    node["expected"] = (wa*a + wb*b) / (wa+wb)
                return node["expected"]
            expected(0)
            trees.append(tree)
        members.append({"bias": bias, "trees": trees})
    return validate({**metadata, "schema_version": 1, "county_fips": "12091", "objective": "reg:squarederror",
                     "features": FEATURES, "target": TARGET, "members": members})
