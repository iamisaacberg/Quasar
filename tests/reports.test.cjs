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
function render(preset, data, {loading = false, error = '', site = 'demo-006'} = {}) {
  let index = 0;
  const values = [preset, 'baseline', [], site, data, error, loading];
  const exports = {};
  const context = {exports, window: {location: {origin: 'http://localhost:8000'}},
    require: name => name === 'react' ? {
      useState: () => [values[index++], () => {}], useEffect: () => {},
    } : name === './reports.css' ? {} : require(name)};
  vm.runInNewContext(source, context);
  return renderToStaticMarkup(React.createElement(exports.Reports, {active: true}));
}
const data = JSON.parse(execFileSync('python3', ['-c', 'import json; from quasar.analysis import report; print(json.dumps(report("compare")))'], {encoding:'utf8'}));
const baseline = {...data, ...data.scenarios[0], scenarios: undefined, rows: data.rows.filter(row => row.scenario === 'baseline')};

test('overview renders accessible charts, unknown rows, context and downloads', () => {
  const html = render('overview', baseline);
  assert.match(html, /Scenario overview/);
  assert.match(html, /role="img"/);
  assert.match(html, /<caption>Relative scores and input completeness/);
  assert.match(html, /Missing terrain exercise site/);
  assert.match(html, /Unknown/);
  assert.match(html, /SYNTHETIC DEMO/);
  assert.match(html, /Generated/);
  assert.match(html, /Miami time/);
  assert.match(html, /scenario=baseline&amp;format=zip/);
  assert.match(html, /not trained AI/);
  assert.match(html, /not an all-clear/);
});

test('comparison renders all three windows with gaps explicitly unknown', () => {
  const html = render('compare', data);
  assert.match(html, /Exercise hour 0/);
  assert.match(html, /Exercise hour 6/);
  assert.match(html, /Exercise hour 12/);
  assert.match(html, /Missing terrain exercise site<\/th><td>Unknown<\/td><td>Unknown<\/td><td>Unknown/);
  assert.match(html, /scenario=compare&amp;format=csv/);
  assert.match(html, /18 site\/window rows/);
});

test('site explainer does not manufacture factor contributions for unknown sites', () => {
  const html = render('site', baseline);
  assert.match(html, /No factor contributions are assigned/);
  assert.doesNotMatch(html, /<caption>Factors behind the illustrative score/);
  assert.match(html, /Terrain elevation/);
  assert.match(html, /Model: illustrative-baseline-v1/);
});

test('unavailable and loading reports do not offer downloads or printing', () => {
  for (const state of [{error: 'Invalid forecast snapshot'}, {loading: true}]) {
    const html = render('overview', null, state);
    assert.doesNotMatch(html, /href="\/api\/exports/);
    assert.match(html, /disabled=""/);
    assert.match(html, state.loading ? /Loading report/ : /role="alert"/);
  }
});

test('mixed reports retain forecast status, source, native resolution and separate times', () => {
  const html = render('overview', {...baseline, mode:'mixed_forecast_demo', forecast: {
    status:'stale', source_table:'project.dataset.table', init_time:'2026-10-17T12:00:00Z',
    retrieved_at:'2026-10-17T12:30:00Z', native_resolution:'0.1 degree', statistic:'ensemble_mean',
  }});
  assert.match(html, /MIXED DEMO/);
  assert.match(html, /Forecast status: stale/);
  assert.match(html, /project.dataset.table/);
  assert.match(html, /Initialized/);
  assert.match(html, /Imported/);
  assert.match(html, /Native resolution: 0.1 degree/);
});


test('known site explanation renders actual pipeline contributions', () => {
  const html = render('site', baseline, {site:'demo-001'});
  assert.match(html, /<caption>Factors behind the illustrative score/);
  for (const factor of baseline.rows.find(row => row.property_id === 'demo-001').factors) {
    assert.ok(html.includes(String(factor.contribution)));
  }
});

test('changing preset never labels the previous window data as the requested comparison', () => {
  const html = render('compare', baseline);
  assert.doesNotMatch(html, /href="\/api\/exports/);
  assert.doesNotMatch(html, /class="report-document"/);
  assert.match(html, /disabled=""/);
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
  } : name === './reports' ? {Reports:()=>null} : name === './data-dashboard' ? {DataDashboard:()=>null} : require(name)};
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
