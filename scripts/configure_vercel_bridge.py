"""Verify or configure Preview bridge settings without writing credentials to disk.

The default only verifies authenticated HTTPS reads. --apply changes Vercel
Preview environment variables and requires deployment/operator authorization.
It does not deploy or restart any service.
"""
import argparse
import json
import subprocess
from urllib.parse import urlsplit
from urllib.request import Request, build_opener
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quasar.bridge import _NoRedirect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ssh-target', required=True)
    parser.add_argument('--identity', type=Path, required=True)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--scope', required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    parsed = urlsplit(args.base_url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.path not in ('', '/')
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        parser.error('Use the public HTTPS origin without a path or credentials')
    result = subprocess.run(['ssh', '-i', str(args.identity), '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
                             '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=12',
                             args.ssh_target, 'sudo -n cat /etc/quasar/bridge.env'], capture_output=True, text=True)
    if result.returncode:
        raise SystemExit('Could not read the existing private service settings over SSH')
    values = {}
    for line in result.stdout.splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip().strip('\"\'')
    bridge = values.get('QUASAR_DATA_BRIDGE_TOKEN', '')
    parcel = values.get('QUASAR_PARCEL_API_TOKEN', '')
    if len(bridge) < 32 or len(parcel) < 32:
        raise SystemExit('Existing bridge and parcel credentials must both be configured')
    origin = args.base_url.rstrip('/')
    # Verify the exact public source before pointing the hosted application at it.
    request = Request(origin + '/bridge/v1/snapshots/weathernext', headers={'Authorization': 'Bearer ' + bridge})
    with build_opener(_NoRedirect).open(request, timeout=15) as response:
        data = json.loads(response.read(5_000_001))
    if data.get('county_fips') != '12091' or data.get('schema_version') != 3:
        raise SystemExit('The public bridge did not return an Okaloosa county snapshot')
    print('Verified authenticated public HTTPS: Okaloosa schema-3 snapshot')
    settings = {'QUASAR_DATA_BRIDGE_URL': origin + '/bridge/v1', 'QUASAR_DATA_BRIDGE_TOKEN': bridge,
                'QUASAR_LINUXONE_API_URL': origin, 'QUASAR_LINUXONE_API_TOKEN': parcel}
    for name, value in settings.items():
        if not args.apply:
            print('Prepared Preview setting:', name)
            continue
        result = subprocess.run(['vercel', 'env', 'add', name, 'preview', '--sensitive', '--force',
                                 '--scope', args.scope, '--project', args.project],
                                input=value, capture_output=True, text=True)
        if result.returncode:
            # CLI diagnostics are deliberately withheld: never risk echoing a secret.
            raise SystemExit('Vercel rejected setting ' + name + '; inspect its project permissions')
        print('Configured Preview setting:', name)
    print('No deployment or service restart was started.')


if __name__ == '__main__':
    main()
