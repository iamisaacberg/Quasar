const {test}=require('node:test');
const assert=require('node:assert/strict');
const {covers,bounds,createSearch,createPlayback}=require('../quasar/static/map-ui.js');

class Element {
  constructor(){this.children=[];this.value='';this.attributes={};}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=items;}
  setAttribute(k,v){this.attributes[k]=v;}
  removeAttribute(k){delete this.attributes[k];}
  focus(){this.focused=true;}
}
const elements=()=>{const ids=new Map();return id=>{if(!ids.has(id))ids.set(id,new Element());return ids.get(id);};};
const geometry={type:'MultiPolygon',coordinates:[
  [[[0,0],[4,0],[4,4],[0,4],[0,0]],[[1,1],[2,1],[2,2],[1,2],[1,1]]],
  [[[5,0],[6,0],[6,1],[5,1],[5,0]]]
]};
const point=(name,coordinates)=>({type:'Feature',geometry:{type:'Point',coordinates},properties:{full_address:name}});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function search(request){
  const get=elements(),selected=[],jobs=new Map();let count=0;
  const api=createSearch({get,element:(_tag,text)=>Object.assign(new Element(),{textContent:text}),token:'pk.test',geometry,request,
    select:f=>selected.push(f),schedule:(fn,ms)=>{assert.equal(ms,300);jobs.set(++count,fn);return count;},cancel:id=>jobs.delete(id)});
  return {get,selected,api,jobs,type(value){get('map-search').value=value;get('map-search').oninput();},async run(){const fn=Array.from(jobs.values()).at(-1);jobs.clear();await fn();}};
}

test('county containment includes island polygons and boundaries but excludes holes and bounding-box gaps',()=>{
  assert.equal(covers([.5,.5],geometry),true);
  assert.equal(covers([1.5,1.5],geometry),false);
  assert.equal(covers([4.5,.5],geometry),false);
  assert.equal(covers([5.5,.5],geometry),true);
  assert.equal(covers([1,1.5],geometry),true);
  assert.equal(covers([NaN,1],geometry),false);
  assert.deepEqual(bounds(geometry),[0,0,6,4]);
});
test('search debounces at three characters, filters county geometry, and supports keyboard select and clear',async()=>{
  let calls=0;
  const app=search(async url=>{calls++;const p=new URL(url).searchParams;assert.equal(p.get('country'),'us');assert.equal(p.get('bbox'),'0,0,6,4');
    return {ok:true,json:async()=>({features:[point('Inside',[.5,.5]),point('Hole',[1.5,1.5]),point('Island',[5.5,.5]),point('Outside',[10,10])]})};});
  app.type('ab');assert.equal(app.jobs.size,0);
  app.type('abcd');app.type('abcde');assert.equal(app.jobs.size,1);await app.run();assert.equal(calls,1);
  assert.equal(app.get('map-search-results').children.length,2);
  const key=key=>app.get('map-search').onkeydown({key,preventDefault(){}});
  key('ArrowUp');key('Enter');
  assert.equal(app.selected[0].properties.full_address,'Island');assert.equal(app.get('map-search-results').hidden,true);
  assert.match(app.get('map-search-status').textContent,/scores remain unknown/);
  app.get('map-search-clear').onclick();assert.equal(app.selected[1],null);assert.equal(app.get('map-search').value,'');
});
test('a pasted H3 cell ID is selected locally without a geocoder request',()=>{
  const get=elements(),selected=[];let requests=0;
  createSearch({get,element:(_tag,text)=>Object.assign(new Element(),{textContent:text}),token:'pk.test',geometry,
    isCellId:value=>value==='8928308280fffff',request:async()=>{requests++;throw new Error('should not geocode an H3 ID');},select:feature=>selected.push(feature)});
  get('map-search').value='8928308280FFFFF';get('map-search').oninput();
  assert.equal(get('map-search-results').children.length,1);
  assert.equal(get('map-search-results').children[0].children[0].textContent,'8928308280fffff');
  get('map-search').onkeydown({key:'Enter',preventDefault(){}});
  assert.equal(requests,0);assert.equal(selected[0].properties.h3_index,'8928308280fffff');
  assert.match(get('map-search-status').textContent,/scores remain unknown/);
});
test('cancelled and late geocodes cannot reopen old results; provider errors remain explicit',async()=>{
  const pending=[];
  const app=search((url,options)=>new Promise(resolve=>pending.push({resolve,signal:options.signal})));
  app.type('first');const first=app.run();await tick();app.type('second');const second=app.run();await tick();
  assert.equal(pending[0].signal.aborted,true);
  pending[1].resolve({ok:true,json:async()=>({features:[point('New',[.5,.5])]})});await second;
  pending[0].resolve({ok:true,json:async()=>({features:[point('Old',[.5,.5])]})});await first;
  assert.equal(app.get('map-search-results').children[0].children[0].textContent,'New');
  app.get('map-search').onkeydown({key:'Escape'});assert.equal(app.get('map-search-results').hidden,true);
  const failed=search(async()=>({ok:false}));failed.type('error');await failed.run();assert.match(failed.get('map-search-status').textContent,/unavailable/);
  const empty=search(async()=>({ok:true,json:async()=>({features:[]})}));empty.type('empty');await empty.run();assert.match(empty.get('map-search-status').textContent,/No matching/);
});
test('search stays disabled without a public token or authoritative geometry',()=>{
  for(const options of [{token:null,geometry},{token:'pk.test',geometry:null}]){
    const get=elements();createSearch({get,element:()=>new Element(),select(){},...options});
    assert.equal(get('map-search').disabled,true);assert.match(get('map-search-status').textContent,/county boundary/);
  }
});
const times=Array.from({length:3},(_,i)=>`2026-10-17T${String(12+i).padStart(2,'0')}:00:00Z`);
function playback(select=async()=>true){
  const get=elements(),timers=new Map();let next=0;
  const controller=createPlayback({get,select,every:(fn,ms)=>{assert.equal(ms,250);timers.set(++next,fn);return next;},stop:id=>timers.delete(id)});
  controller.configure('forecast',times,0);
  return {get,timers,controller};
}
test('shared playback pauses, scrubs, waits for responses and stops at the final frame',async()=>{
  let finish;const selected=[];
  const app=playback((kind,index)=>{selected.push([kind,index]);return new Promise(resolve=>{finish=resolve;});});
  await app.get('replay-play').onclick();assert.equal(app.timers.size,1);
  const timer=app.timers.values().next().value;timer();timer();assert.equal(selected.length,1);
  assert.equal(app.get('replay-hour').value,'0');finish(true);await tick();assert.equal(app.get('replay-hour').value,'1');
  timer();finish(true);await tick();assert.equal(app.get('replay-hour').value,'2');assert.equal(app.timers.size,0);
  app.get('replay-hour').value='0';const scrub=app.get('replay-hour').oninput();finish(true);await scrub;assert.equal(app.get('replay-hour').value,'0');
  await app.get('replay-play').onclick();app.controller.pause();assert.equal(app.timers.size,0);
});
test('failed and superseded playback keep the last displayed timestamp',async()=>{
  const failed=playback(async()=>false),clock=failed.get('playback-clock').textContent;
  await failed.get('replay-next').onclick();assert.equal(failed.get('playback-clock').textContent,clock);assert.match(failed.get('playback-status').textContent,/Playback paused/);
  let finish;const app=playback(()=>new Promise(resolve=>{finish=resolve;}));const old=app.get('replay-next').onclick();
  app.controller.configure('archive',times,2);finish(true);await old;assert.equal(app.get('replay-hour').value,'2');assert.match(app.get('playback-clock').textContent,/Isaias/);
  app.controller.configure('none',[],0,false);assert.equal(app.get('replay-play').disabled,true);
  app.controller.configure('forecast',times,0,false,'Imported forecast is stale.');assert.equal(app.get('replay-play').disabled,true);assert.match(app.get('playback-status').textContent,/stale/);
});
test('a direct selection supersedes a pending hour even within the same archive',async()=>{
  let finish;const app=playback(()=>new Promise(resolve=>{finish=resolve;}));
  const pending=app.get('replay-next').onclick();
  app.controller.configure('forecast',times,2);
  finish(true);await pending;
  assert.equal(app.get('replay-hour').value,'2');
  assert.equal(app.get('replay-hour').disabled,false);
});
test('restarting from the end stays paused if the first hour cannot load its scores',async()=>{
  const app=playback(async(_kind,index)=>{
    app.controller.configure('forecast',times,index);
    throw new Error('scores offline');
  });
  app.controller.configure('forecast',times,2);
  await app.get('replay-play').onclick();
  assert.equal(app.timers.size,0);
  assert.match(app.get('playback-status').textContent,/Playback paused.*scores offline/);
});
test('pausing during a slow restart prevents playback from starting when scores arrive',async()=>{
  let finish;const app=playback(()=>new Promise(resolve=>{finish=resolve;}));
  app.controller.configure('forecast',times,2);
  const restart=app.get('replay-play').onclick();
  app.controller.pause();finish(true);await restart;
  assert.equal(app.timers.size,0);
  assert.equal(app.get('replay-play').textContent,'▶');
});

test('the 8 AM archive reaches noon in four 250 ms ticks and restarts at 8 AM',async()=>{
  const get=elements(),selected=[],prepared=[];let timer,interval;
  const hours=Array.from({length:25},(_,i)=>new Date(Date.parse('2026-10-09T05:00:00Z')+i*3600000).toISOString());
  const controller=createPlayback({get,select:async(_kind,index)=>{selected.push(index);return true;},
    prepare:(_kind,index)=>prepared.push(index),every:(fn,ms)=>{timer=fn;interval=ms;return 1;},stop:()=>{timer=null;}});
  controller.configure('archive',hours,8,true,'Synthetic archive',8);
  assert.match(get('playback-clock').textContent,/8 AM/);
  await get('replay-play').onclick();await tick();
  assert.deepEqual(prepared,[9]);assert.deepEqual(selected,[]);
  for(let i=0;i<4;i++){timer();await tick();}
  assert.equal(interval*4,1000);assert.deepEqual(selected,[9,10,11,12]);
  assert.match(get('playback-clock').textContent,/12 PM|noon/i);
  for(let i=0;i<12;i++){timer();await tick();}
  assert.equal(timer,null);
  await get('replay-play').onclick();await tick();
  assert.equal(selected.at(-1),8);assert.match(get('playback-clock').textContent,/8 AM/);
});
