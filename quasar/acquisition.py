"""Explicit public ArcGIS acquisition with ID completeness checks and minimal fields."""
import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def arcgis(url, params):
    body=urlencode(params).encode()
    request=Request(url,data=body,headers={'User-Agent':'Quasar-datathon/0.1 public GIS research',
                                         'Content-Type':'application/x-www-form-urlencoded'})
    for attempt in range(4):
        try:
            with urlopen(request,timeout=60) as response:data=json.load(response)
            if not isinstance(data,dict) or 'error' in data:raise ValueError('GIS source error')
            return data
        except (OSError,ValueError):
            if attempt==3:raise
            time.sleep(2**attempt)


def features(url, fields='OBJECTID', page_size=500):
    query=url+'/query'
    ids=arcgis(query,{'where':'1=1','returnIdsOnly':'true','f':'json'}).get('objectIds')
    count=arcgis(query,{'where':'1=1','returnCountOnly':'true','f':'json'}).get('count')
    if count == 0 and ids is None:
        ids = []
    if type(count) is not int or not isinstance(ids,list) or len(ids)!=count or len(set(ids))!=count:
        raise ValueError('Source ID inventory is incomplete or duplicated')
    result=[]
    for start in range(0,len(ids),page_size):
        batch=sorted(ids)[start:start+page_size]
        data=arcgis(query,{'objectIds':','.join(map(str,batch)),'outFields':fields,
                          'returnGeometry':'true','outSR':4326,'f':'geojson'})
        rows=data.get('features')
        if (not isinstance(rows,list) or data.get('exceededTransferLimit') or len(rows)!=len(batch)
                or {r.get('properties',{}).get('OBJECTID') for r in rows}!=set(batch)):
            raise ValueError('Source page incomplete; refusing to publish')
        # Drop any fields returned despite outFields before writing a download.
        allowed=set(fields.split(','))
        for row in rows:row['properties']={k:v for k,v in row['properties'].items() if k in allowed}
        result.extend(rows)
    return result
