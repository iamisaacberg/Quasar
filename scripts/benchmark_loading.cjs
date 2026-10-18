// Offline synthetic geometry/storage/tab-reuse benchmark; no browser or server.
const fs=require('node:fs'),vm=require('node:vm'),zlib=require('node:zlib');
const {IDBFactory}=require('fake-indexeddb');
const {create}=require('../quasar/static/data-client.js');
const parcels=require('../quasar/static/parcel-cache.js');
const timed=async task=>{const start=performance.now();await task();return +(performance.now()-start).toFixed(3);};
(async()=>{
  const manifest=JSON.parse(fs.readFileSync('quasar/static/ui/.vite/manifest.json'));
  const entry=fs.readFileSync(`quasar/static/ui/${manifest['frontend/main.tsx'].file}`);
  const files=JSON.parse(fs.readFileSync('quasar/static/ui/assets.json')).files,replies=[];
  const worker={console,performance,TextDecoder,TextEncoder,postMessage:data=>replies.push(data)};
  vm.createContext(worker);vm.runInContext(fs.readFileSync(`quasar/static/ui/${files.find(name=>name.includes('spatial-worker-'))}`,'utf8'),worker);
  const geometry={type:'Polygon',coordinates:[[[-86.6,30.4],[-86.4,30.4],[-86.4,30.6],[-86.6,30.6],[-86.6,30.4]]]};
  worker.onmessage({data:{type:'boundary',geometry}});
  const geometryMs=await timed(async()=>{for(let i=0;i<25;i++)worker.onmessage({data:{id:i,resolution:7,weather:{features:[{id:'synthetic-native',geometry,properties:{status:'ready',rainfall_6h_mm:i}}]}}});});
  let requests=0;
  const client=create({fetcher:async()=>{requests++;return {ok:true,json:async()=>({status:'ready'})};}});
  const tabs=['/api/weather/timeline?source=archive','/api/data/weather?source=archive','/api/reports?source=archive&frame=0','/api/weather/timeline?source=archive'];
  const coldTabs=await timed(()=>Promise.all(tabs.map(url=>client.get(url))));
  const warmTabs=await timed(()=>Promise.all(tabs.map(url=>client.get(url))));
  const indexedDB=new IDBFactory(),cache=parcels.create({indexedDB});
  const version={status:'ready',county_fips:'12091',source_url:'https://synthetic.invalid',dataset_version:'synthetic-only',boundary_version:'synthetic-only',crs:'EPSG:4326'};
  const all=[];const storageMs=await timed(async()=>{for(let offset=0;offset<3165;offset+=100){const page=Array.from({length:Math.min(100,3165-offset)},(_,i)=>({id:offset+i,type:'Feature',geometry,properties:{county_fips:'12091'}}));all.push(...page);await cache.put('synthetic-cell',version,{features:all,checked_count:all.length,next_offset:all.length<3165?all.length:null,complete:all.length===3165},cache.token,{offset,features:page});}});
  const restoreMs=await timed(()=>parcels.create({indexedDB}).get('synthetic-cell',version));
  console.log(JSON.stringify({label:'Synthetic offline processor/storage measurements; no rendered or network proof',initial_ui_gzip_bytes:zlib.gzipSync(entry).length,geometry_25_hours_ms:geometryMs,geometry_first_hour_ms:replies[0].duration_ms,geometry_warm_max_ms:Math.max(...replies.slice(1).map(reply=>reply.duration_ms)),cold_tab_cycle_ms:coldTabs,warm_tab_cycle_ms:warmTabs,tab_network_requests:requests,dense_cell_storage_ms:storageMs,dense_cell_restore_ms:restoreMs},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
