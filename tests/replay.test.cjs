// Source-only playback integration. No browser, cloud or LinuxONE access.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const QuasarParcelCache=require('../quasar/static/parcel-cache.js');
const QuasarInspection=require('../quasar/static/inspection.js');
class Element {
  constructor(tag='div'){this.tag=tag;this.children=[];this.style={};this.value='';this.checked=true;}
  append(...items){this.children.push(...items);if(this.tag==='select'&&!this.value)this.value=items[0]?.value;}
  replaceChildren(...items){this.children=items;}
  setAttribute(name,value){this[name]=value;}
  getAttribute(name){return this[name];}
  removeAttribute(name){delete this[name];}
  querySelectorAll(){return [];}
  querySelector(){return new Element();}
  addEventListener(){}
  focus(){}
}
async function boot(hash='#map-overview'){
  const ids=new Map(),timers=new Map(),requests=[],held=[];let hold=null,fail=null;
  const get=id=>{if(!ids.has(id))ids.set(id,new Element(id==='scenario'?'select':'div'));return ids.get(id);};
  get('map-layer').value='rainfall';
  const hour=(source,i)=>new Date(Date.parse(source==='archive'?'2026-10-09T05:00:00Z':'2026-10-17T12:00:00Z')+i*3600000).toISOString();
  const events={};
  const fetch=async url=>{
    requests.push(url);const source=new URLSearchParams(url.split('?')[1]).get('source');
    if(hold && source===hold)await new Promise(resolve=>held.push(resolve));
    if(fail && source===fail)return {ok:false,json:async()=>({error:'source offline'})};
    let body;
    if(url==='/api/config')body={map:{configured:false}};
    else if(url==='/api/parcels/manifest')return {ok:false,json:async()=>({error:'not configured'})};
    else if(url==='/api/official-alerts')body={message:'Not connected'};
    else if(url.startsWith('/api/weather/timeline?'))body={county_fips:'12091',source,status:'ready',default_index:0,frames:Array.from({length:source==='archive'?25:3},(_,i)=>({at:hour(source,i),collection:{type:'FeatureCollection',mode:source==='archive'?'county_archive':'county_forecast',scenario:{id:source==='archive'?'isaias-2026':'weathernext',valid_from:hour(source,i),valid_to:hour(source,i+6)},features:[],forecast:{status:'ready'},weather_cells:{type:'FeatureCollection',features:[]}}}))};
    else throw Error(url);
    return {ok:true,json:async()=>body};
  };
  const context={console,URLSearchParams,fetch,QuasarSpatial:require('../quasar/static/spatial.js'),document:{getElementById:get,createElement:t=>new Element(t),dispatchEvent:()=>{}},
    Event:class{},MutationObserver:class{observe(){}},setTimeout,clearTimeout,setInterval:fn=>{timers.set(1,fn);return 1;},clearInterval:id=>timers.delete(id),
    window:{QuasarParcelCache,QuasarInspection,location:{hash},matchMedia:()=>({matches:false}),addEventListener:(name,fn)=>{(events[name]??=[]).push(fn);}}};
  vm.runInNewContext(fs.readFileSync('quasar/static/map-ui.js','utf8'),context);context.window.QuasarMapUI=context.QuasarMapUI;
  await vm.runInNewContext(fs.readFileSync('quasar/static/app.js','utf8'),context);
  return {get,requests,timers,hold:value=>{hold=value;},release:()=>held.splice(0).forEach(fn=>fn()),fail:value=>{fail=value;},
    navigate:hash=>{context.window.location.hash=hash;for(const fn of events.hashchange||[])fn();},
    source:async value=>{get('scenario').value=value;return get('scenario').onchange();}};
}
test('shared playback switches between real current and archived forecasts without simulation calls',async()=>{
  const app=await boot();assert.equal(app.get('replay-hour').max,'2');assert.match(app.get('playback-clock').textContent,/Forecast/);
  await app.get('replay-next').onclick();assert.equal(app.get('replay-hour').value,'1');
  await app.source('isaias-2026');assert.equal(app.get('replay-hour').max,'24');assert.match(app.get('playback-clock').textContent,/Archive/);
  await app.get('replay-next').onclick();assert.equal(app.get('replay-hour').value,'1');
  assert.ok(app.requests.every(url=>!/^\/api\/(routes|timeline|properties|notifications|replay)/.test(url)));
  app.get('replay-play').onclick();assert.equal(app.timers.size,1);app.navigate('#data');assert.equal(app.timers.size,0);
});
test('the archive deep link uses only native rainfall and playback stops at the last frame',async()=>{
  const app=await boot('#isaias-replay');assert.equal(app.get('mode-badge').textContent,'ARCHIVED FORECAST');
  app.get('replay-hour').value='23';await app.get('replay-hour').oninput();app.get('replay-play').onclick();
  app.timers.get(1)();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(app.get('replay-hour').value,'24');assert.equal(app.timers.size,0);
});
test('a failed source clears its old clock and disables playback until source reload',async()=>{
  const app=await boot();app.fail('archive');await app.source('isaias-2026');
  assert.equal(app.get('replay-hour').max,'0');assert.equal(app.get('replay-play').disabled,true);
  assert.match(app.get('error').textContent,/source offline/);
  app.fail(null);await app.source('isaias-2026');assert.equal(app.get('replay-hour').max,'24');
});
test('late archive responses cannot overwrite a newer current-source selection',async()=>{
  const app=await boot();app.hold('archive');const old=app.source('isaias-2026');
  await app.source('weathernext');app.release();await old;
  assert.equal(app.get('scenario').value,'weathernext');assert.equal(app.get('mode-badge').textContent,'COUNTY SOURCES');
  assert.equal(app.get('replay-hour').max,'2');
});
