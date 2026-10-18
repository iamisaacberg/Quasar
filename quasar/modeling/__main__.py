"""Explicit local modeling commands. Never imports data or queries cloud services automatically."""
import argparse
import json
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
        return 0 if result.get("status") not in ("missing", "insufficient_evidence") else 2
    except (ValueError, OSError, KeyError, TypeError, StopIteration, ImportError) as exc:
        print(json.dumps({"status": "unavailable", "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
