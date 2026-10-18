const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {create,metrics}=require('../quasar/static/data-client.js');
const geometry=require('../quasar/static/geometry-client.js');
const response=value=>({ok:true,text:async()=>JSON.stringify(value)});

test('request cache deduplicates, expires, measures bytes, and rejects stale forced responses',async()=>{
  let clock=1000,calls=0,release;
  const log=metrics(),client=create({now:()=>clock,measure:log.record,fetcher:async()=>{calls++;if(calls===1)await new Promise(resolve=>release=resolve);return response({value:calls});}});
  const first=client.get('/data'),shared=client.get('/data');
  assert.equal(calls,1);
  const replacement=await client.get('/data',{force:true});release();
  await Promise.all([first,shared]);
  assert.equal(await client.get('/data'),replacement);
  clock+=15001;await client.get('/data');assert.equal(calls,3);
  assert.ok(log.snapshot().some(sample=>sample.cache==='hit'));
  assert.ok(log.snapshot().some(sample=>sample.bytes>0));
});

test('consumer cancellation does not cancel shared work and expired forecasts never survive cache',async()=>{
  let release,calls=0,clock=1000;
  const client=create({now:()=>clock,fetcher:async()=>{calls++;await new Promise(resolve=>release=resolve);return response({status:'ready',expires_at:new Date(2000).toISOString()});}});
  const controller=new AbortController();
  const abandoned=client.get('/forecast',{signal:controller.signal}),other=client.get('/forecast');
  controller.abort();await assert.rejects(abandoned,{name:'AbortError'});
  release();await other;assert.equal(calls,1);
  clock=2001;assert.equal(client.peek('/forecast'),undefined);
});

test('failed rechecks erase prior cache and HTTP/source failures are never cached',async()=>{
  let fail=false,calls=0;
  const client=create({fetcher:async()=>{calls++;if(fail)throw Error('offline');return response({status:'ready'});}});
  await client.get('/source');fail=true;
  await assert.rejects(client.get('/source',{force:true}),/offline/);
  assert.equal(client.peek('/source'),undefined);
  await assert.rejects(client.get('/source'),/offline/);assert.equal(calls,3);
  const unavailable=create({fetcher:async()=>response({status:'unavailable'})});
  await unavailable.get('/source');assert.equal(unavailable.peek('/source'),undefined);
});

test('byte bounds evict least recently used entries and metrics stay bounded',async()=>{
  const client=create({maxBytes:60,fetcher:async key=>response({key})});
  await client.get('/aaaaaaaaaa');await client.get('/bbbbbbbbbb');await client.get('/aaaaaaaaaa');await client.get('/cccccccccc');
  assert.ok(client.peek('/aaaaaaaaaa'));assert.equal(client.peek('/bbbbbbbbbb'),undefined);
  const log=metrics();for(let i=0;i<600;i++)log.record('test',{i});assert.equal(log.snapshot().length,500);
});

test('geometry requests deduplicate and worker failure rejects pending and future work',async()=>{
  const messages=[],worker={postMessage:data=>messages.push(data)},client=geometry.create(worker),boundary={type:'Polygon'};
  const first=client.coverage(boundary,7,{features:[]}),shared=client.coverage(boundary,7,{features:[]});
  assert.equal(messages.length,2);assert.equal(first,shared);
  worker.onmessage({data:{id:messages[1].id,resolution:7,grid:{features:[]},rainfall:[]}});
  assert.deepEqual(await first,{grid:{features:[]},rainfall:[]});
  const pending=client.coverage(boundary,6,{features:[]});worker.onerror();
  await assert.rejects(pending,/worker unavailable/);
  await assert.rejects(client.coverage(boundary,7,{}),/worker unavailable/);
});

test('changed county rejects delayed geometry replies',async()=>{
  const messages=[],worker={postMessage:data=>messages.push(data)},client=geometry.create(worker);
  const old=client.coverage({old:true},7,{}),next=client.coverage({new:true},7,{});
  worker.onmessage({data:{id:messages[1].id,resolution:7,grid:{features:['old']}}});
  await assert.rejects(old,/County geometry changed/);
  worker.onmessage({data:{id:messages[3].id,resolution:7,grid:{features:['new']},rainfall:[]}});
  assert.deepEqual((await next).grid.features,['new']);
});

test('the built worker preserves clipping, unknown coverage, and reuses geometry across hours',()=>{
  const files=JSON.parse(fs.readFileSync('quasar/static/ui/assets.json')).files;
  const file=files.find(name=>name.includes('spatial-worker-'));
  const replies=[],context={console,performance,TextDecoder,TextEncoder,postMessage:data=>replies.push(data)};
  vm.createContext(context);vm.runInContext(fs.readFileSync(`quasar/static/ui/${file}`,'utf8'),context);
  const boundary={type:'Polygon',coordinates:[[[-86.50,30.54],[-86.48,30.54],[-86.48,30.56],[-86.50,30.56],[-86.50,30.54]]]};
  context.onmessage({data:{type:'boundary',geometry:boundary}});
  const weather={features:[{id:'synthetic-native',geometry:boundary,properties:{status:'ready',rainfall_6h_mm:0}}]};
  context.onmessage({data:{id:1,resolution:7,weather}});
  assert.ok(replies[0].grid.features.length>0);assert.ok(replies[0].rainfall.some(feature=>feature.properties.rainfall_mm===0));
  weather.features[0].properties.status='stale';weather.features[0].properties.rainfall_6h_mm=null;
  context.onmessage({data:{id:2,resolution:7,weather}});
  assert.equal(replies[1].grid,undefined);assert.ok(replies[1].rainfall.every(feature=>feature.properties.rainfall_mm===null));
});
