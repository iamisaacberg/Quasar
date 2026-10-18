// Check the actual JSX hierarchy without a browser, map credentials or source requests.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');

function dashboard() {
  const exported = {};
  const compiled = ts.transpileModule(fs.readFileSync('frontend/dashboard.tsx', 'utf8'), {
    compilerOptions: {jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS},
  }).outputText;
  vm.runInNewContext(compiled, {
    exports: exported,
    window: {location: {hash: '#map-overview'}},
    require: name => name === 'react' ? {
      lazy: React.lazy, Suspense: React.Suspense,
      memo: component => component,
      useState: initial => [initial, () => {}],
      useEffect() {},
    } : name.startsWith('./') ? {} : require(name),
  });
  return exported.QuasarDashboard();
}

const children = node => [node?.props?.children].flat(Infinity).filter(Boolean);
const hasClass = (node, name) => node?.props?.className?.split(' ').includes(name);
function find(node, name) {
  if (hasClass(node, name)) return node;
  return children(node).map(child => find(child, name)).find(Boolean);
}

test('rainfall bars have their own grid area outside the compact playback controls', () => {
  const layout = find(dashboard(), 'map-layout');
  const chart = find(layout, 'map-replay-trend');
  const controls = find(layout, 'map-bottom-bar');
  assert.ok(chart, 'Replay chart must remain visible on the map');
  assert.ok(controls, 'Map controls must remain available');
  assert.ok(children(layout).includes(chart), 'Replay chart needs a direct grid area so playback cannot squeeze it');
  assert.ok(children(layout).includes(controls));
  assert.equal(find(controls, 'map-replay-trend'), undefined);
  assert.ok(find(controls, 'map-playback'));
  assert.ok(find(controls, 'map-tool-dock'));
});
