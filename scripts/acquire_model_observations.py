"""Explicit Okaloosa observation acquisition. No training, cloud queries or activation."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quasar.modeling.observations import acquire

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--boundary", type=Path, required=True)
parser.add_argument("--raw", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--historical", action="store_true", help="Also acquire 2018-2025 county reports and Michael/Sally observations")
args = parser.parse_args()
result = acquire(args.boundary, args.raw, args.output, historical=args.historical)
print(json.dumps(result, indent=2))
sys.exit(0 if result["status"] == "observations_acquired" else 2)
