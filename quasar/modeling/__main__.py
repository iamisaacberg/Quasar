"""Explicit local modeling commands. Never imports data or queries cloud services automatically."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("audit", "prepare"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--database", type=Path, required=True)
        cmd.add_argument("--inputs", type=Path, required=True)
        cmd.add_argument("--boundary", type=Path, required=True)
        if name == "prepare": cmd.add_argument("--output", type=Path, required=True)
        else: cmd.add_argument("--inspection", type=Path)
    train = sub.add_parser("train")
    train.add_argument("--dataset", type=Path, required=True)
    train.add_argument("--output", type=Path, required=True)
    for name in ("train-v2", "train-positive"):
        train_cmd = sub.add_parser(name, help="Frozen nested geographic experiment; train-positive excludes zero FEMA overlap")
        for key in ("dataset", "database", "inputs", "boundary", "inspection", "output"):
            train_cmd.add_argument("--"+key, type=Path, required=True)
    review = sub.add_parser("review", help="Local artifact inventory, lineage and exposure sensitivity; never accesses a host")
    qualify = sub.add_parser("qualify-positive", help="Explicit revised qualification policy; ridge comparison is advisory")
    qualify.add_argument("--experiment", type=Path, required=True)
    qualify.add_argument("--output", type=Path, required=True)
    for key in ("dataset", "experiment", "database", "inputs", "boundary", "inspection", "weather", "assessments"):
        review.add_argument("--"+key, type=Path)
    review.add_argument("--output", type=Path, required=True)
    review.add_argument("--research-sensitivity", action="store_true", help="Non-serveable summary comparisons for the research pool, including rejected candidates")
    replay = sub.add_parser("assess-replay", help="Prepare 25 exact v2 replay windows; never activates them")
    for key in ("database", "inputs", "boundary", "inspection", "model", "evaluation", "weather", "output"):
        replay.add_argument("--"+key, type=Path, required=True)
    export = sub.add_parser("export")
    export.add_argument("--experiment", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    assess = sub.add_parser("assess")
    for name in ("database", "inputs", "boundary", "inspection", "model", "evaluation", "weather", "output"):
        assess.add_argument("--"+name, type=Path, required=True)
    assess.add_argument("--from", dest="start", required=True)
    assess.add_argument("--mode", choices=("current", "replay"), required=True)
    bench = sub.add_parser("benchmark")
    for name in ("database", "artifact", "output"):
        bench.add_argument("--"+name, type=Path, required=True)
    for name in ("validate-outcomes", "train-outcomes"):
        cmd = sub.add_parser(name)
        for key in ("dataset", "observations", "inspection"):
            cmd.add_argument("--"+key, type=Path, required=True)
        cmd.add_argument("--weather", type=Path, nargs="+", required=True)
        if name == "train-outcomes": cmd.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "audit":
            from .dataset import audit
            result = audit(args.database, args.inputs, args.boundary, args.inspection)
        elif args.command == "prepare":
            from .dataset import prepare
            result = prepare(args.database, args.inputs, args.boundary, args.output)
        elif args.command == "train":
            from .training import train
            result = train(args.dataset, args.output)
        elif args.command == "train-v2":
            from .v2 import train_v2
            result = train_v2(args.dataset, args.database, args.inputs, args.boundary, args.inspection, args.output)
        elif args.command == "train-positive":
            from .v2 import train_positive
            result = train_positive(args.dataset, args.database, args.inputs, args.boundary, args.inspection, args.output)
        elif args.command == "qualify-positive":
            from .v2 import qualify_positive
            result = qualify_positive(args.experiment, args.output)
        elif args.command == "review":
            from .review import review
            result = review(args.output, research_sensitivity=args.research_sensitivity, **{k: getattr(args, k) for k in
                ("dataset", "experiment", "database", "inputs", "boundary", "inspection", "weather", "assessments")})
        elif args.command == "assess-replay":
            from .production import produce_replay
            result = produce_replay(args.database, args.inputs, args.boundary, args.inspection, args.model,
                                    args.evaluation, args.weather, args.output)
        elif args.command == "export":
            from .training import export
            result = export(args.experiment, args.output)
        elif args.command == "assess":
            from .production import produce
            result = produce(args.database, args.inputs, args.boundary, args.inspection, args.model,
                             args.evaluation, args.weather, args.start, args.mode, args.output)
        elif args.command == "benchmark":
            from .production import benchmark
            result = benchmark(args.database, args.artifact, args.output)
        else:
            from .outcomes import prepare_outcomes, train_outcomes
            if args.command == "train-outcomes":
                result = train_outcomes(args.dataset, args.observations, args.inspection, args.weather, args.output)
            else:
                _, result = prepare_outcomes(args.dataset, args.observations, args.inspection, args.weather)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0 if result.get("status") not in ("missing", "insufficient_evidence", "incomplete", "research_only") else 2
    except (ValueError, OSError, KeyError, TypeError, StopIteration, ImportError, sqlite3.Error) as exc:
        print(json.dumps({"status": "unavailable", "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
