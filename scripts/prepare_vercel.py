"""Serve only allowlisted app routes, never private deployment files."""

from pathlib import Path

directory = Path(__file__).resolve().parents[1] / "vercel-output"
directory.mkdir(exist_ok=True)
placeholder = directory / "_gate-placeholder.txt"
if any(path != placeholder or path.is_dir() for path in directory.iterdir()):
    raise SystemExit("Refusing a deployment with public files outside the team gate.")
# Vercel rejects empty output directories. No app content goes in this file.
# The unconditional route in vercel.json runs before filesystem lookup.
placeholder.write_text("All requests must go through the Quasar application route allowlist.\n")
