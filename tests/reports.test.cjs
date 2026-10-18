// Render report presets in Node; Isaac owns browser and print layout review.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const {execFileSync} = require('node:child_process');

const source = ts.transpileModule(fs.readFileSync('frontend/reports.tsx', 'utf8'), {
  compilerOptions: {jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}
}).outputText;
function render(data, {selectedFrame=2,error=''}={}) {
  let index=0;
  const values=[data,error,0], exported={};
  vm.runInNewContext(source,{exports:exported,window:{},require:name=>name==='react'?{useState:()=>[values[index++],()=>{}],useEffect:()=>{}}:name==='./lib/replay-selection'?{useReplaySelection:()=>[selectedFrame,()=>{}]}:name==='./reports.css'?{}:require(name)});
  return renderToStaticMarkup(React.createElement(exported.Reports,{active:true}));
}
const data={source:'archive',status:'incomplete',selected_index:2,init_time:'2026-10-17T12:00:00Z',retrieved_at:'2026-10-17T12:30:00Z',source_table:'test-only.native-forecast',rows:[
  {native_cell_id:'native-test-zero',rainfall_6h_mm:0,available_hours:6,status:'ready',valid_from:'2026-10-17T12:00:00Z',valid_to:'2026-10-17T18:00:00Z'},
  {native_cell_id:'native-test-unknown',rainfall_6h_mm:null,available_hours:5,status:'incomplete',valid_from:'2026-10-17T12:00:00Z',valid_to:'2026-10-17T18:00:00Z'}]};

test('reports preserve native source identity, zero and unknown values and exports',()=>{
  const html=render(data);
  assert.match(html,/native-test-zero/);assert.match(html,/>0.00</);assert.match(html,/>Unknown</);
  assert.match(html,/source=archive&amp;frame=2&amp;format=zip/);
  assert.match(html,/test-only.native-forecast/);assert.match(html,/Initialized/);assert.match(html,/Imported/);
  assert.doesNotMatch(html,/fictional|synthetic|demo-00/i);
});

test('source changes and absent imports cannot show old reports or offer exports',()=>{
  for(const [report,options] of [[data,{selectedFrame:3}],[null,{error:'Source offline'}],[{...data,rows:[]},{}]]){
    const html=render(report,options);
    assert.doesNotMatch(html,/href="\/api\/exports/);assert.match(html,/disabled=""/);
  }
});

test('archive reports do not expire against today and have no current source selector',()=>{
  const html=render(data);
  assert.match(html,/>0.00</);assert.match(html,/Isaias/);
  assert.doesNotMatch(html,/Current county forecast/);
});

for (const initialView of ['#reports', '#data']) test(`returning from ${initialView} restores the map and signals Mapbox to resize`, () => {
  let hash = initialView, state = [], deps = [], cursor = 0, effectCursor = 0, queued = [], events = [];
  const listeners = new Map();
  const exported = {};
  const dashboard = ts.transpileModule(fs.readFileSync('frontend/dashboard.tsx', 'utf8'), {
    compilerOptions: {jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}
  }).outputText;
  const context = {exports: exported, Event, window: {
    location: {get hash() {return hash;}},
    Quasar: {start:async()=>{}},
    dispatchEvent:event=>events.push(event.type),
    addEventListener:(name,fn)=>listeners.set(name,[...(listeners.get(name)||[]),fn]), removeEventListener:()=>{},
  }, require:name=> name === 'react' ? {...React, memo: fn=>fn,
    useState: initial => {const slot=cursor++; if (!(slot in state)) state[slot]=typeof initial==='function' ? initial() : initial; return [state[slot],value=>state[slot]=value];},
    useEffect: (fn, dependencies) => {const slot=effectCursor++; if (!deps[slot] || dependencies.some((d,i)=>d!==deps[slot][i])) queued.push(fn); deps[slot]=dependencies;},
  } : name === './reports' ? {Reports:()=>null} : name === './components/map-selection-panel' ? {MapSelectionPanel:()=>null} : name === './data-dashboard' ? {DataDashboard:()=>null} : require(name)};
  vm.runInNewContext(dashboard, context);
  const renderDashboard = () => { cursor=0; effectCursor=0; queued=[]; const tree=exported.QuasarDashboard(); queued.forEach(fn=>fn()); return tree; };
  const initial = renderDashboard();
  assert.ok(initial.props.className.includes(initialView === '#data' ? 'is-data-view' : 'is-reports-view'));
  assert.equal(events.includes('resize'), false);
  hash='#map-overview';
  listeners.get('hashchange').forEach(fn=>fn());
  // The real React effect runs after its render has restored the container.
  const map = renderDashboard();
  assert.ok(map.props.className.includes('is-map-view'));
  assert.ok(!map.props.className.includes('is-data-view'));
  assert.ok(!map.props.className.includes('is-reports-view'));
  assert.equal(events.includes('resize'), true);
});
