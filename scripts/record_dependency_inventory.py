"""Record locked npm packages and declared licenses, without installing or querying."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lockfile", type=Path, default=Path("package-lock.json"))
    parser.add_argument("--output", type=Path, default=Path("docs/datathon-submission/dependency-inventory.json"))
    args = parser.parse_args()
    raw = args.lockfile.read_bytes()
    lock = json.loads(raw)
    packages = [{"path": path, "version": entry["version"], "declared_license": entry.get("license", "unrecorded"),
                 "resolved": entry.get("resolved"), "integrity": entry.get("integrity"),
                 "development": entry.get("dev", False), "optional": entry.get("optional", False)}
                for path, entry in sorted(lock["packages"].items()) if path]
    result = {"lockfile_sha256": hashlib.sha256(raw).hexdigest(), "packages": packages,
              "notice": "Lockfile inventory, including optional platform packages; not all entries are installed on every host. Declared license metadata is not a permission review. Preserve upstream license/notice files in distributed bundles."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # One package per line keeps the generated inventory reviewable without
    # dropping transitive/optional versions, resolved URLs or integrity hashes.
    lines = ["{", '  "lockfile_sha256": '+json.dumps(result["lockfile_sha256"])+",",
             '  "notice": '+json.dumps(result["notice"])+",", '  "packages": [']
    lines.append(",\n".join("    "+json.dumps(p, separators=(",", ":")) for p in packages))
    lines.extend(["  ]", "}", ""])
    args.output.write_text("\n".join(lines))
    print(f"Recorded {len(packages)} locked package entries")


if __name__ == "__main__":
    main()
