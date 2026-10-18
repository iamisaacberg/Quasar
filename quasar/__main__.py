import argparse

from .config import load_env, map_settings
from .server import make_server


def main():
    parser = argparse.ArgumentParser(description="Run the Quasar Okaloosa source-data app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    load_env()
    map_settings()  # Refuse secret tokens before the server starts.
    with make_server(args.host, args.port) as server:
        print(f"Quasar: http://{args.host}:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
