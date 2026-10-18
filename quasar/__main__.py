import argparse
import sqlite3

from .config import load_env, map_settings
from .server import make_server


def main():
    parser = argparse.ArgumentParser(description="Run the Quasar Okaloosa source-data app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--warm-serving", action="store_true", help="Validate and warm local prepared serving inputs before listening")
    args = parser.parse_args()
    load_env()
    map_settings()  # Refuse secret tokens before the server starts.
    if args.warm_serving:
        from .warm_serving import warm_serving
        try:
            warm_serving()
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
            parser.exit(1, "Serving startup failed: check the local exposure database, county archive and source configuration.\n")
    with make_server(args.host, args.port) as server:
        print(f"Quasar: http://{args.host}:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
