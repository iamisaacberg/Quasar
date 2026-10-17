// Exercise data selection, nulls and failure states in Node. Isaac reviews visuals.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const {execFileSync} = require('node:child_process');

const comparison = JSON.parse(execFileSync('python3', ['-c', 'import json; from quasar.analysis import report; print(json.dumps(report("compare")))'], {encoding: 'utf8'}));
const reports = Object.fromEntries(comparison.scenarios.map(item => [item.scenario.id, {
  ...comparison, ...item, scenarios: undefined, rows: comparison.rows.filter(row => row.scenario === item.scenario.id),
}]));
const source = ts.transpileModule(fs.readFileSync('frontend/data-dashboard.tsx', 'utf8'), {
  compilerOptions: {jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
}).outputText;
const elements = (tree, predicate) => !tree || typeof tree !== 'object' ? [] : Array.isArray(tree) ? tree.flatMap(child => elements(child, predicate)) : [
  ...(predicate(tree) ? [tree] : []), ...elements(tree.props?.children, predicate),
];

function mount({active = true, reply} = {}) {
  const states = [], effects = [], calls = [];
  let stateCursor, effectCursor, queued, tree;
  const exported = {};
  const context = {exports: exported, AbortController, fetch: async (url, options) => {
    calls.push({url, ...options});
    const body = reply ? await reply(url, options) : undefined;
    const data = body ?? (url === '/api/scenarios' ? {scenarios: [...comparison.scenarios.map(item => item.scenario), {id: 'isaias-2026'}, {id: 'weathernext', label: 'WeatherNext 3 + fictional site inputs'}]} :
      url === '/api/weather/status' ? {status: 'not_configured', message: 'Access confirmed; no snapshot configured.'} :
      url === '/api/official-alerts' ? {status: 'not_connected', message: 'Official feed is not connected. This is not an all-clear.'} :
      reports[new URL(url, 'http://localhost').searchParams.get('scenario')]);
    return {ok: !data?.error, json: async () => data || {error: 'No snapshot'}};
  }, require: name => name === 'react' ? {
    useState: initial => {
      const slot = stateCursor++;
      if (!(slot in states)) states[slot] = initial;
      return [states[slot], value => {states[slot] = typeof value === 'function' ? value(states[slot]) : value;}];
    },
    useEffect: (fn, deps) => {
      const slot = effectCursor++, previous = effects[slot];
      if (!previous || deps.some((value, index) => value !== previous.deps[index])) {
        queued.push(() => { previous?.cleanup?.(); effects[slot] = {deps, cleanup: fn()}; });
      }
    },
  } : name === './data-dashboard.css' ? {} : require(name)};
  vm.runInNewContext(source, context);
  const render = () => {
    stateCursor = 0; effectCursor = 0; queued = [];
    tree = exported.DataDashboard({active});
    queued.forEach(fn => fn());
    return renderToStaticMarkup(tree);
  };
  return {calls, render,
    async settle() { for (let i = 0; i < 3; i++) { await new Promise(setImmediate); render(); } return render(); },
    find: predicate => elements(tree, predicate),
    select: value => elements(tree, node => node.type === 'select')[0].props.onChange({target: {value}}),
    setActive: value => {active = value; return render();},
  };
}

test('Data starts only when active, uses shared pipeline values, and excludes replay from choices', async () => {
  const app = mount({active: false});
  assert.match(app.render(), /hidden=""/);
  assert.equal(app.calls.length, 0);
  app.setActive(true);
  const html = await app.settle();
  assert.match(html, /SYNTHETIC DEMO/);
  assert.match(html, /5 scored · 1 unknown/);
  assert.ok(html.includes(String(reports.baseline.summary.mean_score)));
  assert.match(html, /Missing terrain exercise site/);
  assert.match(html, /<meter min="0" max="6" value="5" aria-label="Terrain elevation available sites"/);
  assert.match(html, /role="img"/);
  assert.match(html, /View band counts/);
  assert.match(html, /scenario=baseline&amp;format=csv/);
  assert.doesNotMatch(html, /value="isaias-2026"/);
  assert.equal(app.calls.length, 4);
  assert.ok(app.calls.every(call => call.url.startsWith('/api/') && call.cache === 'no-store'));
});

test('search and band filters affect only the table; CSV keeps the selected window', async () => {
  const app = mount(); app.render(); await app.settle();
  app.find(node => node.type === 'input')[0].props.onChange({target: {value: 'demo-006'}});
  let html = app.render();
  assert.match(html, /1 of 6 sites/);
  assert.match(html, /5 scored · 1 unknown/);
  assert.match(html, /scenario=baseline&amp;format=csv/);
  const siteRows = () => app.find(node => node.type === 'section' && node.props.className === 'data-card data-explorer')[0];
  assert.doesNotMatch(renderToStaticMarkup(siteRows()), /Biscayne exercise site/);
  app.find(node => node.type === 'select')[1].props.onChange({target: {value: 'elevated'}});
  html = app.render();
  assert.match(html, /No sites match these filters/);
});

test('switching windows hides old data immediately and ignores aborted responses', async () => {
  let release;
  const app = mount({reply: url => url.includes('scenario=heavy-rain') ? new Promise(resolve => {release = resolve;}) : undefined});
  app.render(); await app.settle();
  app.select('heavy-rain');
  assert.doesNotMatch(app.render(), /scenario=heavy-rain&amp;format=csv/);
  await new Promise(setImmediate);
  app.select('peak'); app.render();
  let html = await app.settle();
  assert.match(html, /scenario=peak&amp;format=csv/);
  const old = app.calls.find(call => call.url.includes('scenario=heavy-rain'));
  assert.equal(old.signal.aborted, true);
  release(reports['heavy-rain']);
  html = await app.settle();
  assert.match(html, /scenario=peak&amp;format=csv/);
  assert.doesNotMatch(html, /scenario=heavy-rain&amp;format=csv/);
});

test('unavailable status endpoints stay independent of available exercise data', async () => {
  const app = mount({reply: url => {if (['/api/weather/status', '/api/official-alerts'].includes(url)) throw new Error('offline');}});
  app.render(); const html = await app.settle();
  assert.match(html, /5 scored · 1 unknown/);
  assert.match(html, /Could not check the imported forecast/);
  assert.match(html, /Official feed status unavailable. This is not an all-clear/);
  assert.doesNotMatch(html, /data-status="ready"/);
});

test('stale rainfall stays unknown even with six hourly inputs and retains provenance', async () => {
  const stale = {...reports.baseline, mode: 'mixed_forecast_demo', scenario: {...reports.baseline.scenario, id: 'weathernext'},
    summary: {site_count: 6, scored_count: 0, unknown_count: 6, mean_score: null, bands: {unknown: 6}},
    forecast: {status: 'stale', source_table: 'project.dataset.forecast', init_time: '2026-10-17T12:00:00Z', retrieved_at: '2026-10-17T12:30:00Z', valid_from: '2026-10-17T12:00:00Z', valid_to: '2026-10-17T18:00:00Z', native_resolution: '0.1 degree', statistic: 'ensemble_mean'},
    rows: reports.baseline.rows.map(row => ({...row, score: null, rainfall_6h_mm: null, band: 'unknown', factors: [], missing: [...row.missing, 'rainfall_6h_mm'], forecast_status: 'stale', available_hours: 6})),
  };
  const app = mount({reply: url => url.includes('scenario=weathernext') ? stale : undefined});
  app.render(); await app.settle(); app.select('weathernext'); app.render();
  const html = await app.settle();
  assert.match(html, /MIXED DEMO/);
  assert.match(html, /0 scored · 6 unknown/);
  assert.match(html, /Mean relative score<\/p><strong>Unknown<\/strong>/);
  assert.match(html, /data-status="stale"/);
  assert.match(html, /0\/6<\/div><\/td><td>6<\/td><td>Imported forecast/);
  assert.match(html, /6\/6 hourly inputs/);
  assert.match(html, /project.dataset.forecast/);
  for (const label of ['Initialized', 'Imported', 'Valid from', 'Valid to', '0.1 degree']) assert.ok(html.includes(label));
});

test('report failure clears metrics and download; recheck retries local endpoints', async () => {
  let failed = false;
  const app = mount({reply: url => failed && url.includes('/api/reports?') ? {error: 'Invalid snapshot'} : undefined});
  app.render(); await app.settle(); failed = true;
  app.find(node => node.type === 'button')[0].props.onClick();
  app.render();
  const html = await app.settle();
  assert.match(html, /role="alert"/);
  assert.match(html, /Invalid snapshot/);
  assert.doesNotMatch(html, /href="\/api\/exports|5 scored · 1 unknown/);
  assert.equal(app.calls.length, 8);
  app.setActive(false);
  assert.ok(app.calls.slice(4).every(call => call.signal.aborted));
});

test('a valid zero rainfall value renders as zero rather than unknown', async () => {
  const zero = {...reports.baseline, rows: reports.baseline.rows.map(row => ({...row, rainfall_6h_mm: 0}))};
  const app = mount({reply: url => url.includes('/api/reports?') ? zero : undefined});
  app.render(); const html = await app.settle();
  assert.match(html, /Six-hour rainfall in millimeters\. Biscayne: 0/);
  assert.match(html, /width:0%/);
});
