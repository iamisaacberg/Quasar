"""Acquire Okaloosa roads and hydrography as research inputs; no score joins."""
import hashlib
import json
import sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from quasar.acquisition import features
from quasar.adapters.historical import write_json
from quasar.config import COUNTY_FIPS, COUNTY_TERMS_URL, PARCEL_LICENSE
from quasar.geometry import line_covered

BASE='https://okgis.myokaloosa.com/arcgis/rest/services/'
SOURCES={'roads':('Infrastructure/Transportation/MapServer/120','OBJECTID,PREDIR,NAME,TYPE,SUFDIR'),
         'rivers':('Natural-Features/LandCover_Planimetrics/MapServer/3','OBJECTID'),
         'streams':('Natural-Features/LandCover_Planimetrics/MapServer/5','OBJECTID'),
         'water-bodies':('Natural-Features/LandCover_Planimetrics/MapServer/2','OBJECTID'),
         'lakes':('Natural-Features/LandCover_Planimetrics/MapServer/6','OBJECTID')}


def main():
    from acquire_county_parcels import CountyBoundaryIndex
    boundary_path=Path('data/raw/census_okaloosa_county.geojson')
    b=json.loads(boundary_path.read_text())
    if b['features'][0]['properties']['GEOID']!=COUNTY_FIPS:raise ValueError('Wrong county')
    geom=b['features'][0]['geometry']; index=CountyBoundaryIndex(geom)
    for name,(route,fields) in SOURCES.items():
        url=BASE+route
        target=Path(f'data/processed/okaloosa/{name}.geojson')
        if target.exists():
            existing=json.loads(target.read_text())
            if existing.get('county_fips')==COUNTY_FIPS and existing.get('source_url')==url:
                print(f'{name}: validated snapshot already acquired',flush=True)
                continue
        try:
            raw=features(url,fields)
        except (OSError,ValueError) as exc:
            write_json(Path(f'data/processed/okaloosa/{name}-status.json'),{'status':'unavailable','source_url':url,'county_fips':COUNTY_FIPS,'retrieved_at':datetime.now(timezone.utc).isoformat(),'message':str(exc)})
            print(f'{name}: source unavailable; coverage remains unknown',flush=True)
            continue
        retrieved=datetime.now(timezone.utc).isoformat()
        path=Path(f'data/raw/okaloosa/{name}.geojson')
        write_json(path,{'type':'FeatureCollection','features':raw})
        retained=[]
        for row in raw:
            g=row.get('geometry') or {};kind=g.get('type');coords=g.get('coordinates')
            if kind in ('LineString','MultiLineString'):
                valid=all(index._line_inside(part) for part in ([coords] if kind=='LineString' else coords))
            elif kind in ('Polygon','MultiPolygon'):valid=index.covers_parcel(g)
            else:valid=False
            if valid:retained.append(row)
        data={'type':'FeatureCollection','county_fips':COUNTY_FIPS,'features':retained,
              'source_url':url,'source_identifier':route,'retrieved_at':retrieved,'license':PARCEL_LICENSE,
              'terms_url':COUNTY_TERMS_URL,'crs':'EPSG:4326','source_crs':'EPSG:2238 (US survey feet)',
              'units':'decimal degrees','source_count':len(raw),'excluded_count':len(raw)-len(retained),
              'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
              'county_boundary_sha256':hashlib.sha256(boundary_path.read_bytes()).hexdigest(),
              'processing':'Minimal fields; paginated complete ID inventory; full geometry containment against Census county. Boundary-crossing features excluded, not silently clipped.',
              'notice':'Current reference geometry; not historic flood conditions, stage observations or validated parcel inputs.'}
        write_json(Path(f'data/processed/okaloosa/{name}.geojson'),data)
        print(f'{name}: {len(retained)}/{len(raw)} county-contained features',flush=True)

if __name__=='__main__':main()
