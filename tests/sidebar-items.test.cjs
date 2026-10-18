const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");

// Value: protects=removed help links stay absent; fails_when=a removed sidebar label returns; why_new=no existing test guards these removals; seam=none; no_claim=browser rendering not verified
test("removed map help items stay out of the sidebar and built UI", () => {
  const sidebar = fs.readFileSync("frontend/components/application-shell2.tsx", "utf8");
  const dashboard = fs.readFileSync("frontend/dashboard.tsx", "utf8");
  const builtCss = fs.readFileSync("quasar/static/ui/app-shell.css", "utf8");
  const builtJs = fs.readFileSync("quasar/static/ui/app-shell.js", "utf8");

  assert.doesNotMatch(sidebar, /Official NWS guidance|ShieldCheck/);
  assert.doesNotMatch(dashboard, /exercise-guide|How to read the map/);
  assert.doesNotMatch(builtCss, /exercise-guide/);
  assert.doesNotMatch(builtJs, /Official NWS guidance|Map guide|Reading the map|Understanding the inputs|How to read the map/);
});
