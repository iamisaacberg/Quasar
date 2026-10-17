"""Password-protected HTTPS launcher for a temporary team Wi-Fi demo."""

import argparse
import getpass
import hashlib
import ipaddress
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile

from .config import load_env, map_settings
from .server import make_server
from .access import TeamGate


def wifi_address():
    """Use the actual macOS Wi-Fi device, which is not always en0."""
    if sys.platform != "darwin":
        raise ValueError("Specify your Wi-Fi IPv4 address with --host ADDRESS on this system.")
    ports = subprocess.run(
        ["/usr/sbin/networksetup", "-listallhardwareports"],
        check=True, capture_output=True, text=True, timeout=5,
    ).stdout
    for block in ports.split("\n\n"):
        if "Hardware Port: Wi-Fi" not in block and "Hardware Port: AirPort" not in block:
            continue
        for line in block.splitlines():
            if line.startswith("Device: "):
                result = subprocess.run(
                    ["/usr/sbin/ipconfig", "getifaddr", line.removeprefix("Device: ")],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
    raise ValueError("No connected Wi-Fi IPv4 address found. Connect to Wi-Fi or use --host ADDRESS.")


def lan_address(value):
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as exc:
        raise ValueError("--host must be your Wi-Fi IPv4 address.") from exc
    if address.is_unspecified or address.is_loopback or address.is_multicast or address.is_reserved:
        raise ValueError("--host must be your Wi-Fi IPv4 address, not a wildcard or loopback address.")
    return str(address)


def tls_context(directory, host):
    openssl = shutil.which("openssl")
    if not openssl:
        raise ValueError("OpenSSL is required to create the local HTTPS certificate.")
    directory = Path(directory)
    certificate = directory / "certificate.pem"
    key = directory / "key.pem"
    config = directory / "openssl.cnf"
    config.write_text(
        "[req]\nprompt=no\ndistinguished_name=subject\nx509_extensions=extensions\n"
        "[subject]\nCN=Quasar team demo\n[extensions]\nbasicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n"
        f"subjectAltName=IP:{host},IP:127.0.0.1,DNS:localhost\n"
    )
    subprocess.run(
        [openssl, "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-nodes", "-days", "2",
         "-keyout", str(key), "-out", str(certificate), "-config", str(config)],
        check=True, capture_output=True, timeout=30,
    )
    key.chmod(0o600)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certificate, key)
    der = ssl.PEM_cert_to_DER_cert(certificate.read_text())
    fingerprint = ":".join(f"{byte:02X}" for byte in hashlib.sha256(der).digest())
    return context, fingerprint


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", help="Wi-Fi IPv4 address; detected automatically on macOS")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    try:
        host = lan_address(args.host or wifi_address())
        load_env()
        map_settings()
        password = os.environ.pop("QUASAR_WIFI_PASSWORD", None)
        if password is None:
            if not sys.stdin.isatty():
                raise ValueError("Run in a terminal to enter the password, or set QUASAR_WIFI_PASSWORD in .env.")
            password = getpass.getpass("Create shared team password (12+ characters): ")
            if password != getpass.getpass("Confirm team password: "):
                raise ValueError("Passwords did not match.")
        gate = TeamGate(password)
        del password
        with tempfile.TemporaryDirectory(prefix="quasar-wifi-") as directory:
            context, fingerprint = tls_context(directory, host)
            with make_server(host, args.port, access_gate=gate) as server:
                server.socket = context.wrap_socket(
                    server.socket, server_side=True, do_handshake_on_connect=False,
                )
                print(f"\nTeam URL: https://{host}:{server.server_port}", flush=True)
                print("Sign in with the shared passphrase on the access page.", flush=True)
                print("Local certificate: verify this SHA-256 fingerprint before accepting the browser warning:")
                print(fingerprint, flush=True)
                print("Keep this laptop awake. Ctrl-C stops sharing. No public tunnel is opened.\n", flush=True)
                server.serve_forever()
    except KeyboardInterrupt:
        print("\nWi-Fi sharing stopped.")
    except (ValueError, OSError, EOFError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Wi-Fi sharing could not start: {exc}\n")


if __name__ == "__main__":
    main()
