// Build app/data/cities.json from plotly/datasets us-cities-top-1k.csv
// County FIPS derived by planar point-in-polygon against us-atlas counties-10m
// (pre-projected AlbersUsa 975x610; same projection applied to city lon/lat).
import fs from "node:fs";
import { geoAlbersUsa } from "d3-geo";
import { polygonContains } from "d3-polygon";
import { feature } from "topojson-client";

const [,, csvPath, countiesPath, statesPath, outPath] = process.argv;

const csv = fs.readFileSync(csvPath, "utf8").trim().split(/\r?\n/);
const header = csv.shift().split(",");
const rows = csv.map(line => {
  // simple CSV: no quoted commas in this file
  const parts = line.split(",");
  const o = {};
  header.forEach((h, i) => o[h.trim()] = parts[i]);
  return o;
});

const counties = JSON.parse(fs.readFileSync(countiesPath, "utf8"));
const states = JSON.parse(fs.readFileSync(statesPath, "utf8"));
const countyFeats = feature(counties, counties.objects.counties).features;
const stateFeats = feature(states, states.objects.states).features;

const stateNameToFips = new Map(stateFeats.map(f => [f.properties.name, f.id]));
const stateFipsToPostal = {
  "01":"AL","02":"AK","04":"AZ","05":"AR","06":"CA","08":"CO","09":"CT","10":"DE","11":"DC","12":"FL","13":"GA","15":"HI","16":"ID","17":"IL","18":"IN","19":"IA","20":"KS","21":"KY","22":"LA","23":"ME","24":"MD","25":"MA","26":"MI","27":"MN","28":"MS","29":"MO","30":"MT","31":"NE","32":"NV","33":"NH","34":"NJ","35":"NM","36":"NY","37":"NC","38":"ND","39":"OH","40":"OK","41":"OR","42":"PA","44":"RI","45":"SC","46":"SD","47":"TN","48":"TX","49":"UT","50":"VT","51":"VA","53":"WA","54":"WV","55":"WI","56":"WY","72":"PR"
};

const projection = geoAlbersUsa().scale(1300).translate([487.5, 305]);

// Precompute bboxes + rings for each county
const idx = countyFeats.map(f => {
  const polys = f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates;
  let minx=Infinity,miny=Infinity,maxx=-Infinity,maxy=-Infinity;
  for (const poly of polys) for (const ring of poly) for (const [x,y] of ring) {
    if (x<minx)minx=x; if (x>maxx)maxx=x; if (y<miny)miny=y; if (y>maxy)maxy=y;
  }
  return { id: f.id, name: f.properties.name, polys, bbox:[minx,miny,maxx,maxy] };
});

function containsPt(entry, pt) {
  const [x,y] = pt; const b = entry.bbox;
  if (x<b[0]||x>b[2]||y<b[1]||y>b[3]) return false;
  for (const poly of entry.polys) {
    if (polygonContains(poly[0], pt)) {
      let inHole = false;
      for (let i=1;i<poly.length;i++) if (polygonContains(poly[i], pt)) { inHole = true; break; }
      if (!inHole) return true;
    }
  }
  return false;
}

function nearest(entry_list, pt, stateFips) {
  // fallback: nearest county centroid within the same state
  let best=null, bd=Infinity;
  for (const e of entry_list) {
    if (stateFips && e.id.slice(0,2)!==stateFips) continue;
    const cx=(e.bbox[0]+e.bbox[2])/2, cy=(e.bbox[1]+e.bbox[3])/2;
    const d=(cx-pt[0])**2+(cy-pt[1])**2;
    if (d<bd){bd=d;best=e;}
  }
  return best;
}

const slugify = s => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g,"").replace(/[^a-z0-9]+/g,"-").replace(/^-+|-+$/g,"");

const out = [];
let missed = 0, fallback = 0;
for (const r of rows) {
  const pop = +r.Population;
  if (!(pop >= 50000)) continue;
  const lat = +r.lat, lon = +r.lon;
  const state_fips = stateNameToFips.get(r.State);
  if (!state_fips) { missed++; console.error("no state fips for", r.State); continue; }
  const pt = projection([lon, lat]);
  let county = null;
  if (pt) {
    for (const e of idx) { if (e.id.slice(0,2)===state_fips && containsPt(e, pt)) { county = e; break; } }
    if (!county) for (const e of idx) { if (containsPt(e, pt)) { county = e; break; } }
  }
  if (!county && pt) { county = nearest(idx, pt, state_fips); fallback++; }
  if (!county) { missed++; console.error("no county for", r.City, r.State); continue; }
  out.push({
    slug: slugify(r.City),
    name: r.City,
    state: stateFipsToPostal[state_fips] || null,
    state_fips,
    county_fips: county.id,
    county_name: county.name,
    lat: +lat.toFixed(5), lon: +lon.toFixed(5),
    pop
  });
}
out.sort((a,b)=>b.pop-a.pop);

const doc = {
  _meta: {
    source: "plotly/datasets us-cities-top-1k.csv (https://github.com/plotly/datasets/blob/master/us-cities-top-1k.csv), U.S. Census population estimates as published in that file",
    filter: "population >= 50000",
    county_fips: "derived by planar point-in-polygon of AlbersUsa-projected lon/lat against us-atlas@3.0.1 counties-albers-10m.json (shipped here as data/counties-10m.json); " + fallback + " cities assigned to nearest county centroid in-state when the point fell outside every polygon (coastal simplification)",
    built_at: new Date().toISOString(),
    count: out.length
  },
  cities: out
};
fs.writeFileSync(outPath, JSON.stringify(doc));
console.log("cities:", out.length, "fallback:", fallback, "missed:", missed);
