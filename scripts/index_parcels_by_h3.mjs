// Build a compact R7 cell-to-parcel index for the LinuxONE SQLite bundle.
// Reads only the county-validated, minimal-field GeoJSONL importer output.
import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import zlib from "node:zlib";
import { once } from "node:events";
import h3 from "h3-js";

const root = path.resolve(import.meta.dirname, "..");
const input = path.resolve(process.argv[2] || path.join(root, "data/raw/okaloosa_parcels_wgs84.geojsonl.gz"));
const boundaryPath = path.resolve(process.argv[3] || path.join(root, "data/raw/census_okaloosa_county.geojson"));
const output = path.resolve(process.argv[4] || path.join(root, "data/processed/okaloosa/linuxone"));
const resolutions = [4, 5, 6, 7];

if (!fs.existsSync(input) || !fs.existsSync(boundaryPath)) throw new Error("Parcel snapshot and Census boundary are required");
const boundary = JSON.parse(fs.readFileSync(boundaryPath, "utf8"));
if (boundary.features?.length !== 1 || boundary.features[0].properties?.GEOID !== "12091") {
  throw new Error("Expected the Census boundary for Okaloosa GEOID 12091");
}
const countyGeometry = boundary.features[0].geometry;
const countyPolygons = countyGeometry.type === "Polygon" ? [countyGeometry.coordinates] : countyGeometry.coordinates;
const countyCellsByResolution = new Map(resolutions.map(resolution => [resolution, new Set()]));
for (const rings of countyPolygons) {
  for (const resolution of resolutions) {
    for (const cell of h3.polygonToCellsExperimental(rings, resolution, h3.POLYGON_TO_CELLS_FLAGS.containmentOverlapping, true)) {
      countyCellsByResolution.get(resolution).add(cell);
    }
  }
}
if (!countyCellsByResolution.get(7).size) throw new Error("H3 produced no county cells");

fs.mkdirSync(output, { recursive: true });
const mappingPath = path.join(output, "parcel-cell-index.tsv.gz");
const metadataPath = path.join(output, "county-cells.json");
const temporary = `${mappingPath}.partial`;
const gzip = zlib.createGzip({ level: 9, mtime: 0 });
const destination = fs.createWriteStream(temporary);
gzip.pipe(destination);
let features = 0;
let mappings = 0;
const seen = new Set();

for await (const line of readline.createInterface({
  input: fs.createReadStream(input).pipe(zlib.createGunzip()),
  crlfDelay: Infinity,
})) {
  if (!line) continue;
  const feature = JSON.parse(line);
  const parcelId = feature.properties?.parcel_id ?? feature.id;
  if (!Number.isSafeInteger(parcelId) || feature.properties?.county_fips !== "12091") {
    throw new Error(`Invalid county parcel row at feature ${features + 1}`);
  }
  if (seen.has(parcelId)) throw new Error(`Duplicate parcel ID ${parcelId}`);
  seen.add(parcelId);
  const geometry = feature.geometry;
  const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.type === "MultiPolygon" ? geometry.coordinates : null;
  if (!polygons) throw new Error(`Parcel ${parcelId} has non-polygon geometry`);
  const cellsByResolution = new Map(resolutions.map(resolution => [resolution, new Set()]));
  for (const rings of polygons) {
    for (const cell of h3.polygonToCellsExperimental(rings, 7, h3.POLYGON_TO_CELLS_FLAGS.containmentOverlapping, true)) {
      if (countyCellsByResolution.get(7).has(cell)) {
        for (const resolution of resolutions) {
          const indexedCell = resolution === 7 ? cell : h3.cellToParent(cell, resolution);
          if (countyCellsByResolution.get(resolution).has(indexedCell)) cellsByResolution.get(resolution).add(indexedCell);
        }
      }
    }
  }
  if (!cellsByResolution.get(7).size) throw new Error(`Parcel ${parcelId} did not intersect any Okaloosa R7 cell`);
  for (const resolution of resolutions) {
    for (const cell of cellsByResolution.get(resolution)) {
      if (!gzip.write(`${cell}\t${parcelId}\n`)) await once(gzip, "drain");
      mappings += 1;
    }
  }
  features += 1;
  if (features % 50000 === 0) process.stdout.write(`Indexed ${features.toLocaleString()} parcels; ${mappings.toLocaleString()} cell memberships\n`);
}

gzip.end();
await once(destination, "finish");
fs.renameSync(temporary, mappingPath);
const cellsByResolution = Object.fromEntries(resolutions.map(resolution => [
  resolution, [...countyCellsByResolution.get(resolution)].sort(),
]));
const metadata = {
  schema_version: 1,
  county_fips: "12091",
  source_snapshot: path.relative(root, input),
  source_count: features,
  h3_resolutions: resolutions,
  cell_counts: Object.fromEntries(resolutions.map(resolution => [resolution, cellsByResolution[resolution].length])),
  cells_by_resolution: cellsByResolution,
  mapping_rows: mappings,
  indexing: "H3 polygonToCellsExperimental containmentOverlapping; parcels county-validated before indexing; R7 memberships aggregated to H3 ancestors for resolutions 4 through 6.",
};
fs.writeFileSync(metadataPath, `${JSON.stringify(metadata)}\n`);
process.stdout.write(`${JSON.stringify({ features, mappings, county_cells: metadata.cell_counts, mapping_file: mappingPath, metadata_file: metadataPath }, null, 2)}\n`);
