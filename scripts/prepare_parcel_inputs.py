"""Prepare local, unscored Okaloosa parcel inputs. No network/cloud operations."""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quasar.parcel_inputs import prepare, reconcile_fema_reference


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/processed/okaloosa/parcel-inputs" /
                        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                        help="New output directory; existing directories are never overwritten")
    parser.add_argument("--reconcile-from", type=Path, help="Existing completed input artifact to reconcile into a new output directory")
    parser.add_argument("--audit", type=Path, default=ROOT / "data/processed/okaloosa/fema-reference-audit.json")
    args = parser.parse_args()
    if args.reconcile_from:
        reconcile_fema_reference(ROOT, args.reconcile_from, args.audit, args.output)
    else:
        prepare(ROOT, args.output)


if __name__ == "__main__":
    main()
