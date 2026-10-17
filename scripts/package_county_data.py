"""Manifest the local Okaloosa research bundle. No uploads or infrastructure changes."""
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from quasar.adapters.historical import write_json


def main():
    paths=[Path('data/raw/census_okaloosa_county.geojson'),Path('data/raw/census_okaloosa_county.provenance.json'),Path('data/raw/okaloosa_parcels_wgs84.geojsonl.gz'),
           Path('data/raw/okaloosa_parcels_wgs84.manifest.json'),Path('data/raw/fema_nfhl_okaloosa_12091c.zip'),
           Path('data/raw/usgs_okaloosa_stream_locations.geojson'),Path('data/processed/source_manifest.json'),
           Path('data/processed/usgs_okaloosa_stream_locations.geojson'),Path('data/processed/isaias-advisories.json'),
           Path('data/processed/evacuation-network.json'),Path('data/processed/weathernext.json'),
           Path('data/processed/isaias-2026.json')]
    excluded_incomplete=set()
    for folder in ('data/processed/okaloosa','data/raw/okaloosa','data/raw/usgs_3dep_10m','data/raw/isaias','data/raw/weathernext/okaloosa'):
        for path in sorted(Path(folder).rglob('*')):
            if not path.is_file() or path.name=='bundle-manifest.json':
                continue
            if path.name.endswith(('.partial', '-journal', '-wal', '-shm')):
                continue
            research_root=Path('data/processed/okaloosa/parcel-inputs')
            if path.is_relative_to(research_root):
                parts=path.relative_to(research_root).parts
                run=research_root/parts[0]
                if len(parts)<2 or not (run/'manifest.json').exists():
                    excluded_incomplete.add(str(run))
                    continue
            paths.append(path)
    entries=[];missing=[]
    for path in paths:
        if not path.exists():missing.append(str(path));continue
        h=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
        entries.append({'path':str(path),'bytes':path.stat().st_size,'sha256':h.hexdigest()})
    total=sum(x['bytes'] for x in entries)
    result={'county_fips':'12091','generated_at':datetime.now(timezone.utc).isoformat(),'files':entries,
            'missing':missing,'excluded_incomplete_research_runs':sorted(excluded_incomplete),
            'bytes':total,'local_free_bytes':shutil.disk_usage('.').free,
            'transfer':'Stage to a separate 12091 directory; require free disk >= 2 * bundle bytes + 1 GB, verify checksums, then switch paths together. Keep the prior 12086 bundle for rollback.',
            'notice':'Local acquisition and preparation only. No server transfer/deployment is implied. Parcels remain unscored; USGS station metadata is not stage observations.'}
    write_json(Path('data/processed/okaloosa/bundle-manifest.json'),result)
    print(json.dumps({'bundle_bytes':total,'missing':missing,'local_free_bytes':result['local_free_bytes']}))

if __name__=='__main__':main()
