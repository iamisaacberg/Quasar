const {test}=require('node:test');
const assert=require('node:assert/strict');
const {IDBFactory}=require('fake-indexeddb');
const {create,RETENTION,CHECK_INTERVAL}=require('../quasar/static/parcel-cache.js');
const manifest={status:'ready',county_fips:'12091',source_url:'https://example.test/gis',dataset_version:'v1',boundary_version:'boundary',crs:'EPSG:4326'};
const record={features:[{id:1}],inventory_id:'ids',next_offset:100,complete:false};

test('IndexedDB survives a new app instance and preserves partial pagination',async()=>{
  const indexedDB=new IDBFactory(), a=create({indexedDB});
  await a.put('cell',manifest,record);
  const b=create({indexedDB}), loaded=await b.get('cell',manifest);
  assert.equal(loaded.next_offset,100); assert.equal(loaded.complete,false);
  assert.deepEqual(loaded.features,[{id:1}]);
  assert.equal(await b.get('cell',{...manifest,dataset_version:'v2'}),undefined);
  assert.equal(await b.get('cell',{...manifest,boundary_version:'other'}),undefined);
  await b.clear(); assert.equal(await create({indexedDB}).get('cell',manifest),undefined);
});

test('manifest checks deduplicate, refresh after 15 minutes, and preserve failed revalidation',async()=>{
  let clock=1000,calls=0,fail=false;
  const cache=create({now:()=>clock});
  const fetch=async()=>{calls++;if(fail)throw Error('offline');return manifest;};
  await Promise.all([cache.check(fetch),cache.check(fetch)]); assert.equal(calls,1);
  await cache.put('cell',manifest,record); clock+=CHECK_INTERVAL+1; fail=true;
  const result=await cache.check(fetch); assert.match(result.error.message,/offline/);
  assert.equal((await cache.get('cell')).inventory_id,'ids');
});

test('same ID inventory with a new daily live geometry version cannot reuse old shapes',async()=>{
  let clock=1000;
  const cache=create({now:()=>clock}), first={...manifest,geometry_valid_until:new Date(2000).toISOString()};
  await cache.check(async()=>first); await cache.put('cell',first,record); clock=2001;
  const next=await cache.check(async()=>({...first,dataset_version:'next-day'}));
  assert.equal(await cache.get('cell',next.manifest),undefined);
});

test('disk eviction is LRU and expired data is never restored',async()=>{
  const indexedDB=new IDBFactory();let clock=1000;
  const cache=create({indexedDB,now:()=>clock,maxBytes:1800});
  await cache.put('a',manifest,record);clock++;
  await cache.put('b',manifest,record);clock++;
  await cache.get('a',manifest);clock++;
  await cache.put('c',manifest,record);
  const reader=create({indexedDB,now:()=>clock});
  assert.equal(await reader.get('b',manifest),undefined);
  assert.ok(await reader.get('a',manifest)); assert.ok(await reader.get('c',manifest));
  clock+=RETENTION+1;
  assert.equal(await reader.get('a',manifest),undefined);
});

test('storage failures fall back to memory and clear invalidates late writes',async()=>{
  const cache=create({storage:{get:async()=>{throw Error('blocked');},put:async()=>{throw Error('quota');},all:async()=>{throw Error('blocked');},clear:async()=>{}}});
  await cache.put('cell',manifest,record);
  assert.ok(cache.diskFailed); assert.equal((await cache.get('cell',manifest)).next_offset,100);
  const token=cache.token;await cache.clear();
  await cache.put('cell',manifest,record,token);assert.equal(await cache.get('cell',manifest),undefined);
});

test('single-flight and forced refresh cannot reuse an abandoned loader',async()=>{
  const cache=create();let resolve,calls=0;
  const loader=()=>{calls++;return new Promise(r=>resolve=r);};
  const a=cache.single('cell',manifest,loader), b=cache.single('cell',manifest,loader);
  await Promise.resolve(); assert.equal(calls,1); assert.equal(a,b);
  await cache.remove('cell');
  const c=cache.single('cell',manifest,async()=>42);assert.equal(await c,42);
  resolve(1);await a;
});

test('an older tab cannot overwrite newer saved pagination by reading or writing its cached record',async()=>{
  const indexedDB=new IDBFactory(), older=create({indexedDB}), newer=create({indexedDB});
  await older.put('cell',manifest,{...record,checked_count:100});
  await newer.put('cell',manifest,{...record,checked_count:200,next_offset:200});
  await older.get('cell',manifest);
  await older.put('cell',manifest,{...record,checked_count:100});
  const loaded=await create({indexedDB}).get('cell',manifest);
  assert.equal(loaded.next_offset,200);
});
