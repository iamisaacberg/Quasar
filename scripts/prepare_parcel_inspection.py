"""Build a new inspection artifact locally. No network or cloud queries."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quasar.inspection_prepare import prepare


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True, help="Completed descriptive input directory")
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--weather", type=Path, nargs="*", default=[], help="Existing schema-3 snapshots")
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    args = parser.parse_args()
    prepare(args.database, args.inputs, args.boundary, args.weather, args.output)
