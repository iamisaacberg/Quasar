// Native forecast selection, nulls and failure states; no browser or cloud queries.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const path = require('node:path');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');

// Load the real UI blocks and primitives without a browser or a dev server.
// Only the dashboard's request/state lifecycle is controlled by this harness.
const componentCache = new Map();
function loadComponent(name, parent = process.cwd()) {
  const base = name.startsWith('@/') ? path.resolve('frontend', name.slice(2)) : path.resolve(parent, name);
  const file = ['.tsx', '.ts', ''].map(ext => base + ext).find(file => fs.existsSync(file) && fs.statSync(file).isFile());
  if (!file) throw new Error(`Missing UI module: ${name}`);
  if (componentCache.has(file)) return componentCache.get(file);
  const exported = {};
  componentCache.set(file, exported);
  const compiled = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: {jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
  }).outputText;
  vm.runInNewContext(compiled, {exports: exported, require: dependency => dependency.startsWith('@/') || dependency.startsWith('.') ? loadComponent(dependency, path.dirname(file)) : require(dependency)}, {filename: file});
  return exported;
}

// Synthetic API responses test the real-source contract; never production data.
const cells = [
  {native_cell_id: 'native-a', rainfall_6h_mm: 0, available_hours: 6, status: 'ready'},
  {native_cell_id: 'native-b', rainfall_6h_mm: 12, available_hours: 6, status: 'ready'},
  {native_cell_id: 'native-c', rainfall_6h_mm: null, available_hours: 5, status: 'incomplete'},
];
const forecast = {county_fips: '12091', status: 'incomplete', generated_at: '2026-10-17T20:00:00Z', default_index: 0,
  source_table: 'test.project.forecast', init_time: '2026-10-17T18:00:00Z', retrieved_at: '2026-10-17T19:00:00Z', native_resolution: '0.1 degree', statistic: 'ensemble_mean',
  frames: [{at: '2026-10-17T20:00:00Z', valid_to: '2026-10-18T02:00:00Z', rows: cells},
    {at: '2026-10-17T21:00:00Z', valid_to: '2026-10-18T03:00:00Z', rows: cells.map(row => ({...row, rainfall_6h_mm: null, status: 'stale'}))}],
};
const source = ts.transpileModule(fs.readFileSync('frontend/data-dashboard.tsx', 'utf8'), {
  compilerOptions: {jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
}).outputText;
const elements = (tree, predicate) => !tree || typeof tree !== 'object' ? [] : Array.isArray(tree) ? tree.flatMap(child => elements(child, predicate)) : [
  ...(predicate(tree) ? [tree] : []), ...elements(tree.props?.children, predicate), ...elements(tree.props?.controls, predicate),
];

function mount({active = true, reply} = {}) {
  const states = [], effects = [], calls = [];
  let stateCursor, effectCursor, queued, tree;
  const exported = {};
  const context = {exports: exported, window:{addEventListener(){},removeEventListener(){},dispatchEvent(){}},CustomEvent:class{}, AbortController, setTimeout, clearTimeout, fetch: async (url, options) => {
    calls.push({url, ...options});
    const body = reply ? await reply(url, options) : undefined;
    const data = body ?? (url === '/api/data/weather?source=archive' ? forecast :
      url === '/api/parcels/manifest' ? {county_fips: '12091', status: 'ready', source_mode: 'indexed', parcel_count: 1234} :
      {status: 'not_connected', message: 'Official feed is not connected. This is not an all-clear.'});
    return {ok: !data?.error, json: async () => data || {error: 'No snapshot'}};
  }, require: name => name === 'react' ? {
    useState: initial => {
      const slot = stateCursor++;
      if (!(slot in states)) states[slot] = typeof initial === 'function' ? initial() : initial;
      return [states[slot], value => {states[slot] = typeof value === 'function' ? value(states[slot]) : value;}];
    },
    useEffect: (fn, deps) => {
      const slot = effectCursor++, previous = effects[slot];
      if (!previous || deps.some((value, index) => value !== previous.deps[index])) {
        queued.push(() => { previous?.cleanup?.(); effects[slot] = {deps, cleanup: fn()}; });
      }
    },
  } : name === './lib/replay-selection' ? hook : name === './data-dashboard.css' ? {} : name.startsWith('@/') ? loadComponent(name) : require(name)};
  const hook={};
  const hookSource=ts.transpileModule(fs.readFileSync('frontend/lib/replay-selection.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
  vm.runInNewContext(hookSource,{...context,exports:hook});
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
    select: value => elements(tree, node => typeof node.props?.onValueChange === 'function')[0].props.onValueChange(value),
    setActive: value => {active = value; return render();},
  };
}

test('Data loads real-source endpoints only when active, with zero and unknown distinct', async () => {
  const app = mount({active: false});
  assert.match(app.render(), /hidden=""/);
  assert.equal(app.calls.length, 0);
  app.setActive(true);
  const html = await app.settle();
  assert.match(html, /1,234/);
  assert.match(html, /Real source data/);
  assert.match(html, /Six-hour rainfall in millimeters. Cell 1: 0; Cell 2: 12; Cell 3: Unknown/);
  assert.match(html, /test.project.forecast/);
  assert.match(html, /0.1 degree/);
  assert.doesNotMatch(html, /demo-00|Exercise hour|SYNTHETIC DEMO|Mean relative score|api\/exports/);
  assert.equal(app.calls.length, 3);
  assert.deepEqual(app.calls.map(call => call.url).sort(), ['/api/data/weather?source=archive', '/api/official-alerts', '/api/parcels/manifest']);
  assert.ok(app.calls.every(call => call.cache === 'no-store'));
});

test('search and status filters affect only the native-cell table', async () => {
  const app = mount(); app.render(); await app.settle();
  app.find(node => node.props?.['aria-label'] === 'Find a native forecast cell')[0].props.onChange({target: {value: 'native-c'}});
  let html = app.render();
  assert.match(html, /1 of 3 cells/);
  const table = () => renderToStaticMarkup(app.find(node => node.props?.id === 'data-explorer')[0]).split('<tbody')[1].split('</tbody>')[0];
  assert.doesNotMatch(table(), /native-a/);
  app.find(node => typeof node.props?.onValueChange === 'function')[1].props.onValueChange('ready');
  assert.match(app.render(), /No native cells match/);
  assert.equal(app.find(node => node.type?.name === 'ChartGroup6')[0].props.rainfall.length, 3);
});

test('retained window selection uses native cells and preserves stale unknowns', async () => {
  const app = mount(); app.render(); await app.settle();
  app.select('1');
  const html = app.render();
  assert.match(html, /Unknown/);
  const chart = app.find(node => node.type?.name === 'ChartGroup6')[0];
  assert.ok(chart.props.rainfall.every(row => row.value === null));
  assert.equal(chart.props.bands.find(row => row.name === 'Stale').value, 3);
  assert.equal(app.calls.length, 3);
});

test('source failures stay independent and never load demo fallbacks', async () => {
  const app = mount({reply: url => {if (url !== '/api/data/weather?source=archive') throw new Error('offline');}});
  app.render(); const html = await app.settle();
  assert.match(html, /native-a/);
  assert.match(html, /Could not verify the parcel inventory/);
  assert.match(html, /Official feed status unavailable. This is not an all-clear/);
  const stats = app.find(node => node.type?.name === 'DashboardStats')[0];
  assert.equal(stats.props.parcelCount, null);
});

test('absent county weather and legacy parcel counts remain unknown', async () => {
  const app = mount({reply: url => url === '/api/data/weather?source=archive' ? {...forecast, status: 'not_configured', frames: [], message: 'No imported county forecast is configured.'} :
    url === '/api/parcels/manifest' ? {county_fips: '12091', status: 'ready', source_mode: 'indexed'} : undefined});
  app.render(); const html = await app.settle();
  assert.match(html, /County rainfall unavailable/);
  assert.doesNotMatch(html, /data-explorer/);
  const stats = app.find(node => node.type?.name === 'DashboardStats')[0];
  for (const key of ['parcelCount', 'cellCount', 'availableCount', 'meanRainfall']) assert.equal(stats.props[key], null);
});

test('expired snapshots cannot display rainfall even if the response says ready', async () => {
  const app = mount({reply: url => url === '/api/data/weather?source=archive' ? {...forecast, expires_at: '2000-01-01T00:00:00Z'} : undefined});
  app.render(); const html = await app.settle();
  assert.match(html, /data-status="stale"/);
  assert.ok(app.find(node => node.type?.name === 'ChartGroup6')[0].props.rainfall.every(row => row.value === null));
});

test('recheck clears failed forecast metrics and aborted old responses cannot replace new data', async () => {
  let release, pending = false;
  const app = mount({reply: url => pending && url === '/api/data/weather?source=archive' ? new Promise(resolve => {release = resolve;}) : undefined});
  app.render(); await app.settle(); pending = true;
  const recheck = () => app.find(node => typeof node.props?.onClick === 'function')[0].props.onClick();
  recheck(); app.render(); await new Promise(setImmediate);
  const old = app.calls[3];
  pending = false; recheck(); app.render(); await app.settle();
  assert.equal(old.signal.aborted, true);
  release({...forecast, frames: []});
  assert.match(await app.settle(), /native-a/);
  app.setActive(false);
  assert.ok(app.calls.slice(6).every(call => call.signal.aborted));
});

test('wrong county responses fail closed', async () => {
  const app = mount({reply: url => url === '/api/data/weather?source=archive' ? {...forecast, county_fips: '12086'} : undefined});
  app.render(); const html = await app.settle();
  assert.match(html, /Could not read the Isaias county archive/);
  assert.doesNotMatch(html, /native-a/);
});

test('CSV keeps every selected native cell, provenance, valid zero and blank unknowns', async () => {
  const app = mount(); app.render(); await app.settle();
  app.find(node => node.props?.['aria-label'] === 'Find a native forecast cell')[0].props.onChange({target: {value: 'native-c'}});
  app.render();
  const link = app.find(node => node.props?.download === 'quasar-native-forecast.csv')[0];
  const csv = decodeURIComponent(link.props.href.split(',').slice(1).join(','));
  const lines = csv.split('\r\n');
  assert.equal(lines.length, 4);
  assert.match(lines[1], /"native-a".*,"0","mm \/ 6h","ready"/);
  assert.match(lines[3], /"native-c".*,,"mm \/ 6h","incomplete"/);
  assert.ok(lines.slice(1).every(line => line.includes('"test.project.forecast"') && line.includes('"0.1 degree"')));
  assert.match(csv, /"init_time","retrieved_at"/);
});
