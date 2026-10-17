const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const Replay=require('../quasar/static/replay.js');

class Element {
  constructor(tag='div'){this.tag=tag;this.children=[];this.style={};this.value='';this.checked=true;}
  append(...items){this.children.push(...items);if(this.tag==='select'&&!this.value)this.value=items[0]?.value;}
  replaceChildren(...items){this.children=items;}
  setAttribute(name,value){this[name]=value;}
}
async function boot(){
  const ids=new Map(),timers=new Map(),requests=[],held=[];
  let hold=null,fail=null;
  const get=id=>{if(!ids.has(id))ids.set(id,new Element(id==='scenario'?'select':'div'));return ids.get(id);};
  get('replay-mode').value='archive';get('replay-preset').value='archived';get('road-state').value='closed';
  const events={};
  const feature=(id,score)=>({type:'Feature',id,geometry:{type:'Point',coordinates:[-80.2,25.8]},properties:{id,label:id,risk:{score,band:score===null?'unknown':'moderate',factors:[],missing:[]}}});
  const fetch=async(url,options)=>{
    requests.push({url,body:options?.body});
    const path=url.split('?')[0],params=options?.body?JSON.parse(options.body):Object.fromEntries(new URLSearchParams(url.split('?')[1]));
    if(params.at===hold)await new Promise(resolve=>held.push(resolve));
    if(path==='/api/timeline'&&params.at===fail)return{ok:false,json:async()=>({error:'timeline unavailable'})};
    let body;
    if(path==='/api/config')body={map:{configured:false}};
    else if(path==='/api/scenarios')body={scenarios:[{id:'baseline',label:'Baseline'},{id:'isaias-2026',label:'Isaias 2026'}]};
    else if(path==='/api/weather/status')body={status:'not_configured',message:'No current forecast'};
    else if(path==='/api/official-alerts')body={message:'Not connected'};
    else if(path==='/api/replay/context')body={status:'loaded',advisories:[{number:1,issued_at:'2026-10-06T21:00:00Z',text:'Synthetic test advisory context',source_url:'https://www.nhc.noaa.gov/'}]};
    else if(path==='/api/properties')body={type:'FeatureCollection',mode:'historical_mixed_demo',notice:'Mixed exercise',scenario:{id:'isaias-2026',valid_from:params.at,valid_to:Replay.hour(6)},replay:{at:params.at},features:[feature('demo-001',33),feature('demo-002',44)]};
    else if(path==='/api/timeline')body={...params,source_status:'loaded',reconstruction:'initialization-based',label:'Illustrative exposure for the next six hours',points:Array.from({length:25},(_,i)=>({at:Replay.hour(i),risk:{score:i===2?null:33},change:i===0||i===2||i===3?null:0,forecast:{status:i===2?'incomplete':'ready'}}))};
    else if(path==='/api/routes')body={...params,status:params.mode==='what_if'?'ready':'historical_conditions_unavailable',message:'Exercise routing',route:null,unrestricted:null,notice:'Exercise only',excluded_roads:[],network:{type:'FeatureCollection',features:[{id:'road-1',geometry:{type:'LineString',coordinates:[[-80.2,25.8],[-80.21,25.8]]},properties:{id:'road-1',label:'Test road',kind:'road',state:'open'}}]},destinations:[{id:'exercise-north',label:'Exercise North',coordinates:[-80.21,25.8],available:true}]};
    else throw Error(url);
    return {ok:true,json:async()=>body};
  };
  const context={console,URLSearchParams,fetch,document:{getElementById:get,createElement:t=>new Element(t),createElementNS:(_,t)=>new Element(t),createTextNode:text=>({textContent:text}),dispatchEvent:()=>{}},
    Event:class{},setInterval:(fn)=>{timers.set(1,fn);return 1;},clearInterval:id=>timers.delete(id),
    window:{location:{hash:'#isaias-replay'},addEventListener:(name,fn)=>{events[name]=fn;}}};
  vm.runInNewContext(fs.readFileSync('quasar/static/replay.js','utf8'),context);
  await vm.runInNewContext(fs.readFileSync('quasar/static/app.js','utf8'),context);
  return{get,requests,timers,hold:at=>{hold=at;},release:()=>{for(const fn of held.splice(0))fn();},fail:at=>{fail=at;}};
}

test('replay hour bounds and chart gaps preserve isolated valid points',()=>{
  assert.equal(Replay.hour(-1),Replay.hour(0));assert.equal(Replay.hour(25),Replay.hour(24));
  const paths=Replay.segments([{risk:{score:5}},{risk:{score:null}},{risk:{score:7}}]);
  assert.equal(paths.length,2);assert.equal(paths[0].length,1);assert.equal(paths[1].length,1);
});
test('replay boots without a map and synchronizes hourly controls, timeline and routes',async()=>{
  const app=await boot();
  assert.equal(app.get('isaias-replay').hidden,false);
  assert.equal(app.get('timeline-rows').children.length,25);
  assert.equal(app.get('detail-heading').textContent,'demo-001');
  assert.match(app.get('route-summary').textContent,/historical conditions unavailable/);
  await app.get('replay-next').onclick();
  const routes=app.requests.filter(r=>r.url==='/api/routes');
  assert.equal(JSON.parse(routes.at(-1).body).at,Replay.hour(1));
  assert.match(app.get('replay-clock').textContent,/1 AM/);
});
test('presets and overrides enter what-if mode; reset clears overrides and clock',async()=>{
  const app=await boot();
  app.get('replay-preset').value='plus-5';await app.get('replay-preset').onchange();
  assert.equal(app.get('replay-mode').value,'what_if');
  app.get('road-select').value='road-1';await app.get('road-apply').onclick();
  let body=JSON.parse(app.requests.filter(r=>r.url==='/api/routes').at(-1).body);
  assert.equal(body.roads['road-1'],'closed');
  const input=app.get('destination-controls').children[0].children[0];input.checked=false;await input.onchange();
  body=JSON.parse(app.requests.filter(r=>r.url==='/api/routes').at(-1).body);assert.equal(body.destinations['exercise-north'],false);
  await app.get('replay-reset').onclick();body=JSON.parse(app.requests.filter(r=>r.url==='/api/routes').at(-1).body);
  assert.deepEqual(body.roads,{});assert.deepEqual(body.destinations,{});assert.equal(body.at,Replay.hour(0));assert.equal(body.mode,'archive');assert.equal(body.preset,'archived');
});
test('late responses cannot overwrite a newer hour or selected site',async()=>{
  const app=await boot();app.hold(Replay.hour(1));
  const old=app.get('replay-next').onclick();
  await app.get('replay-next').onclick();
  const clock=app.get('replay-clock').textContent;
  app.release();await old;
  assert.equal(app.get('replay-clock').textContent,clock);
  assert.match(app.get('timeline-change').textContent,/Unknown/);
  const row=app.get('sites').children[1];row.children.at(-1).children[0].onclick();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(app.get('detail-heading').textContent,'demo-002');
  assert.match(app.get('timeline-heading').textContent,/demo-002/);
});
test('one failed response keeps all displayed results at the preceding clock',async()=>{
  const app=await boot(),clock=app.get('replay-clock').textContent;
  app.fail(Replay.hour(1));await app.get('replay-next').onclick();
  assert.equal(app.get('replay-clock').textContent,clock);
  assert.match(app.get('error').textContent,/timeline unavailable/);
});
test('playback stops at the last hour and pause removes its timer',async()=>{
  const app=await boot();app.get('replay-hour').value='23';await app.get('replay-hour').oninput();
  app.get('replay-play').onclick();assert.equal(app.timers.size,1);
  app.timers.get(1)();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(app.get('replay-hour').value,'24');assert.equal(app.timers.size,0);assert.equal(app.get('replay-play').textContent,'Play');
});
