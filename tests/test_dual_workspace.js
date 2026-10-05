"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
function workspaceModule() {
  const ref = process.env.COMPSET_DUAL_BASELINE_REF;
  if (!ref) return require("../compset/static/dual-workspace.js");
  if (!/^[a-f0-9]{40}$/.test(ref) || process.env.COMPSET_DUAL_BENCH !== "1") throw new Error("Baseline measurement requires an exact commit and benchmark mode");
  const { execFileSync } = require("node:child_process"), Module = require("node:module"), path = require("node:path");
  const filename = path.resolve(__dirname, "../compset/static/dual-workspace.js"), baseline = new Module(filename, module);
  baseline.filename = filename; baseline.paths = module.paths;
  baseline._compile(execFileSync("git", ["show", `${ref}:compset/static/dual-workspace.js`], { encoding: "utf8" }), filename);
  return baseline.exports;
}
const dual = workspaceModule();
const { model } = dual;

function calendar() {
  return { dates: ["2026-09-28", "2026-09-29"], entities: [{ id: "bnbme_direct:1", label: "Dubai home", currency: "AED", source: "bnbme_direct" }, { id: "bnbme_direct:2", label: "London home", currency: "GBP", source: "bnbme_direct" }],
    cells: [{ entity_id: "bnbme_direct:1", date: "2026-09-28", state: "indicative", availability: "available", amount: "610.36", currency: "AED", amount_basis: "website_calendar_rate", offers: [] }, { entity_id: "bnbme_direct:2", date: "2026-09-28", state: "unknown", availability: "available", amount: null, currency: "GBP", offers: [] }] };
}
test("dates are validated without timezone shifts and studio zero survives query", () => {
  assert.equal(model.isoDate("2026-02-30"), null); assert.equal(model.addDays("2026-09-30", 1), "2026-10-01");
  const url = model.calendarQuery({ start: "2026-09-28", days: 14, city: "London", bedrooms: 0, namespace: "bnbme_direct", query: "A & B" });
  const q = new URL(url, "http://localhost").searchParams; assert.equal(q.get("bedrooms"), "0"); assert.equal(q.get("query"), "A & B"); assert.equal(q.get("namespace"), "bnbme_direct");
});
test("direct inventory availability is independent of exact quote state", () => {
  assert.equal(model.priceLabel(calendar().cells[0]), "AED 610.36");
  assert.equal(model.priceLabel(calendar().cells[1]), "Available · price unknown");
  assert.equal(model.priceLabel({ state: "indicative", availability: "unavailable", amount: "800", currency: "AED" }), "Unavailable");
  assert.equal(model.priceLabel({ state: "unknown", amount: "0" }), "Unknown");
  assert.equal(model.priceLabel({ state: "indicative", amount: null, display_amount: "₹5K" }), "₹5K");
});
test("missing, duplicate and cross-currency cells stay unknown without cross-property joins", () => {
  const data = calendar(); data.cells.push({ ...data.cells[0] });
  let rows = model.calendarView(data); assert.equal(rows[0].cells[0].reason, "duplicate_saved_cell"); assert.equal(rows[0].cells[1].state, "unknown");
  data.cells = [{ ...data.cells[0], currency: "GBP" }]; rows = model.calendarView(data); assert.equal(rows[0].cells[0].reason, "currency_context_mismatch"); assert.equal(rows[1].cells[0].state, "unknown");
});
test("offer filters never retain the unfiltered minimum or imply sold-out", () => {
  const cell = { state: "indicative", amount: "5000", currency: "INR", offers: [{ room_name: "Standard", amount: "5000", meals: ["Breakfast"] }, { room_name: "Deluxe", amount: "7000", meals: ["Breakfast"] }] };
  const filtered = model.filteredOfferCell(cell, { room: "Deluxe" }); assert.equal(filtered.amount, null); assert.equal(filtered.offers.length, 1); assert.equal(filtered.offers[0].amount, "7000");
  const none = model.filteredOfferCell(cell, { room: "Suite" }); assert.equal(none.state, "unknown"); assert.equal(none.reason, "no_matching_saved_offer");
});
test("calendar export preserves currencies, decimals, source context and spreadsheet safety", () => {
  const data = calendar(); data.entities[0].label = " =HYPERLINK(\"x\")";
  const csv = model.exportRows(model.calendarView(data), { adults: 1 }); assert.match(csv, /610\.36/); assert.match(csv, /AED/); assert.match(csv, /GBP/); assert.match(csv, /website_calendar_rate/); assert.match(csv, /"' =HYPERLINK/); assert.match(csv, /adults/);
});
test("map distance uses only observed coordinates and does not rewrite match decisions", () => {
  const candidate = { id: "airbnb:2", latitude: 25.19, longitude: 55.27, selected: false, eligibility: "provisional" };
  const result = model.mapCandidates({ candidates: [candidate, { id: "missing" }] }, { latitude: 25.19, longitude: 55.27 }, 2);
  assert.equal(result.length, 1); assert.equal(result[0].selected, false); assert.equal(result[0].view_distance_km, 0); assert.equal(candidate.view_distance_km, undefined);
  assert.equal(model.distanceKm({ latitude: 0, longitude: null }, candidate), null);
});

test("configured names require one exact subject group and distinguish unknown from observed zero", () => {
  const group = { subject_id: "lighthouse:42", identity_status: "name_only_unresolved", competitor_labels: [] };
  assert.equal(model.configuredGroup({ status: "observed_name_only", groups: [group] }, group.subject_id).count, 0);
  for (const payload of [null, { status: "read_error", groups: [group] }, { status: "observed_name_only", groups: [] }, { status: "observed_name_only", groups: [group, group] }]) assert.equal(model.configuredGroup(payload, group.subject_id).count, null);
  assert.equal(model.configuredGroup({ status: "observed_name_only", groups: [group] }, "lighthouse:43").count, null);
});

test("configured-name export preserves subject provenance and spreadsheet safety without rate fields", () => {
  const payload = { status: "observed_name_only", groups: [{ subject_id: "lighthouse:42", identity_status: "name_only_unresolved", competitor_labels: [" =HYPERLINK(\"x\")", "River Hotel"], observed_at: "2026-09-28T09:57:29Z", source_url: "https://app.mylighthouse.com/market/example" }] };
  const csv = model.configuredCsv({ id: "lighthouse:42", title: "Our Hotel" }, payload);
  assert.match(csv, /lighthouse:42/); assert.match(csv, /name_only_unresolved/); assert.match(csv, /2026-09-28T09:57:29Z/); assert.match(csv, /"' =HYPERLINK/);
  assert.match(csv, /not_collected/); assert.doesNotMatch(csv, /amount|currency|latitude|5169/);
  const unknown = model.configuredCsv({ id: "lighthouse:43", title: "Other Hotel" }, payload);
  assert.match(unknown, /not_observed/); assert.doesNotMatch(unknown, /River Hotel|lighthouse:42/);
});

class Element {
  constructor(tagName, doc) { doc.created = (doc.created || 0) + 1; this.tagName = tagName.toUpperCase(); this.ownerDocument = doc; this.children = []; this.parentNode = null; this.attrs = {}; this.listeners = {}; this.className = ""; this._text = ""; this.disabled = false; this.hidden = false; this.classList = { add: (...names) => { this.className = [...new Set([...this.className.split(" "), ...names])].filter(Boolean).join(" "); } }; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
  set innerHTML(_) { throw new Error("Unsafe innerHTML"); }
  appendChild(child) { if (child.parentNode) child.remove(); this.children.push(child); child.parentNode = this; return child; }
  replaceChildren(...children) { this.children.forEach(c => { c.parentNode = null; }); this.children = []; this._text = ""; children.forEach(c => this.appendChild(c)); }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(c => c !== this); this.parentNode = null; }
  get isConnected() { return this === this.ownerDocument.body || Boolean(this.parentNode && this.parentNode.isConnected); }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  getAttribute(name) { return this.attrs[name]; }
  removeAttribute(name) { delete this.attrs[name]; }
  contains(node) { return node === this || this.children.some(child => child.contains(node)); }
  addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
  removeEventListener(name, fn) { this.listeners[name] = (this.listeners[name] || []).filter(f => f !== fn); }
  setPointerCapture(id) { this.capture = id; }
  hasPointerCapture(id) { return this.capture === id; }
  releasePointerCapture(id) { if (this.capture === id) this.capture = null; }
  dispatch(name, properties = {}) { for (const fn of this.listeners[name] || []) fn({ target: this, preventDefault() {}, ...properties }); }
  click() { if (!this.disabled) this.dispatch("click"); }
  focus() { this.ownerDocument.activeElement = this; }
  querySelectorAll() { return descendants(this).filter(n => ["BUTTON", "INPUT", "SELECT", "A"].includes(n.tagName)); }
}
class Document {
  constructor() { this.body = new Element("body", this); this.activeElement = this.body; this.listeners = {}; }
  createElement(tag) { return new Element(tag, this); }
  createElementNS(_, tag) { return this.createElement(tag); }
  addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
  removeEventListener(name, fn) { this.listeners[name] = (this.listeners[name] || []).filter(f => f !== fn); }
  dispatch(name, properties = {}) { for (const fn of this.listeners[name] || []) fn({ preventDefault() {}, ...properties }); }
}
const descendants = root => root.children.flatMap(child => [child, ...descendants(child)]);
const find = (root, fn) => { const result = descendants(root).find(fn); assert.ok(result, "Rendered control not found"); return result; };
const clickText = (root, label) => find(root, n => n.tagName === "BUTTON" && n.textContent === label).click();
async function settled() { for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve)); }
async function choose(root, label, value) { const n = find(root, n => n.tagName === "SELECT" && n.getAttribute("aria-label") === label); n.value = value; n.dispatch("change"); await settled(); }
function viewport(width) {
  const previous = global.matchMedia, queries = new Map();
  global.matchMedia = query => {
    if (!queries.has(query)) { const listeners = new Set(); queries.set(query, { matches: width <= Number(query.match(/\d+/)[0]), addEventListener: (_, fn) => listeners.add(fn), removeEventListener: (_, fn) => listeners.delete(fn), listeners }); }
    return queries.get(query);
  };
  return { resize(next) { for (const [query, media] of queries) { const matches = next <= Number(query.match(/\d+/)[0]); if (matches !== media.matches) { media.matches = matches; media.listeners.forEach(fn => fn({ matches })); } } }, restore() { global.matchMedia = previous; } };
}
function fakeLeaflet() {
  const stats = { maps: [], tiles: 0, circles: [], markers: [], removed: 0, invalidations: 0 };
  const layer = type => ({ type, handlers: {}, addTo(target) { this.target = target; return this; }, on(name, fn) { this.handlers[name] = fn; return this; }, bindPopup(node) { this.popup = node; return this; }, setLatLng(point) { this.point = point; return this; }, getLatLng() { return { lat: this.point[0], lng: this.point[1] }; }, setRadius(radius) { this.radius = radius; return this; }, clearLayers() { this.cleared = (this.cleared || 0) + 1; return this; }, removeLayer() {}, remove() {} });
  return { stats, api: {
    map(node) { const m = layer("map"); m.node = node; m.mouseEventToLatLng = event => event.latlng; m.setView = (point, zoom) => { m.center = point; m.zoom = zoom; return m; }; m.getZoom = () => m.zoom; m.remove = () => { stats.removed++; }; m.invalidateSize = () => { stats.invalidations++; }; stats.maps.push(m); return m; },
    tileLayer() { stats.tiles++; return layer("tiles"); },
    circle(point, options) { const c = layer("circle").setLatLng(point); c.radius = options.radius; stats.circles.push(c); return c; },
    marker(point) { const m = layer("marker").setLatLng(point); stats.markers.push(m); return m; },
    circleMarker(point) { return layer("candidate").setLatLng(point); },
    layerGroup() { return layer("group"); },
  } };
}
function fixtures() {
  const properties = [{ id: "bnbme_direct:1", subject_id: "bnbme_direct:1", title: "Dubai apartment", label: "Dubai apartment", namespace: "bnbme_direct", source: "bnbme_direct", city: "Dubai", currency: "AED", bedrooms: 0, bathrooms: 1, latitude: 25.19, longitude: 55.27, observed_at: "2026-09-28T06:00:00Z" }, { id: "bnbme_direct:2", subject_id: "bnbme_direct:2", title: "London apartment", label: "London apartment", namespace: "bnbme_direct", source: "bnbme_direct", city: "London", currency: "GBP", bedrooms: 2, bathrooms: 2, latitude: 51.5, longitude: -.15, observed_at: "2026-09-28T06:00:00Z" }];
  const candidates = Array.from({ length: 60 }, (_, i) => ({ id: `airbnb:${i + 10}`, candidate_id: `airbnb:${i + 10}`, title: i === 0 ? "<img src=x onerror=bad>" : `Candidate ${i + 1}`, selected: i < 6, eligibility: i < 6 ? "eligible" : "provisional", bedrooms: 1, bathrooms: 1, latitude: 25.19 + i / 100000, longitude: 55.27, distance_km: .1, missing_fields: ["floor_area_sqm"], observed_at: "2026-09-27T22:00:00Z", source_url: i === 0 ? "javascript:bad" : `https://www.airbnb.com/rooms/${i + 10}` }));
  const summary = { schema_version: 1, revision: "fixture-r1", observed_at: "2026-09-28T06:00:00Z", str: { properties, subjects: properties.map(p => ({ subject_id: p.id })), default_start: "2026-09-28", calendar_bounds: { start: "2026-09-01", end: "2027-09-01" }, summary: {} }, hotel: { label: "Hotel Aketa" }, warnings: [] };
  const data = { id: "aketa", label: "Hotel Aketa", dates: ["2026-09-28", "2026-09-29"], context: { adults: 1, rooms: 1, children: 0, currency: "INR", stay_nights: 1 }, entities: [{ id: "agoda", source: "agoda", label: "Agoda" }, { id: "google", source: "google_hotels", label: "Google Hotels" }], cells: [
    { entity_id: "agoda", date: "2026-09-28", checkout: "2026-09-29", state: "indicative", amount: "5169.00", currency: "INR", amount_basis: "ota_display_price", observed_at: "2026-09-28T06:00:00Z", offers: [{ room_name: "Premium Single", amount: "5169.00", currency: "INR", meals: ["Breakfast"], conditions: ["Membership coupon"], taxes_included: false, fees_included: false, observed_at: "2026-09-28T06:00:00Z" }] },
    { entity_id: "google", date: "2026-09-28", checkout: "2026-09-29", state: "indicative", amount: null, display_amount: "₹5K", currency: "INR", amount_basis: "google_calendar_minimum", offers: [] }, { entity_id: "agoda", date: "2026-09-29", checkout: "2026-09-30", state: "unavailable", amount: null, currency: "INR", offers: [] }], summary: { rate_rows: 2, unknown_cells: 1 }, source_states: [{ source: "agoda", status: "unavailable", last_stay: "2026-09-29", observed_at: "2026-09-28T06:00:00Z" }] };
  return { summary, properties, candidates, hotel: { dataset: data, compset: { subject: { id: "aketa", title: "Hotel Aketa", latitude: 30.3, longitude: 78.04 }, candidates: [{ id: "hotel:1", title: "Observed hotel", latitude: 30.3, longitude: 78.04, selected: true, eligibility: "eligible", distance_km: 1, missing_fields: [], product: { segment: "full_service" }, reasons: ["Restaurant observed"], rate_status: "unknown" }], summary: { selected_count: 1 } } } };
}
function responder(f, url) {
  const u = new URL(url, "http://localhost"), q = u.searchParams;
  if (u.pathname === "/api/workspace/job") return { state: "idle", job_id: null };
  if (u.pathname === "/api/intelligence") return f.summary;
  if (u.pathname === "/api/intelligence/hotel") return f.hotel;
  if (u.pathname === "/api/intelligence/str/calendar") {
    const request = { start: q.get("start"), days: Number(q.get("days")), offset: Number(q.get("offset")), limit: Number(q.get("limit")), city: q.get("city"), currency: q.get("currency"), namespace: q.get("namespace") === "all" ? null : q.get("namespace") || "bnbme_direct", bedrooms: q.has("bedrooms") ? Number(q.get("bedrooms")) : null, query: (q.get("query") || "").trim().replace(/\s+/g, " ") };
    const entities = f.properties.filter(p => (!request.city || p.city === request.city) && (request.bedrooms === null || p.bedrooms === request.bedrooms));
    const dates = Array.from({ length: request.days }, (_, i) => model.addDays(request.start, i));
    return { request, total: entities.length, dates, entities: entities.slice(request.offset, request.offset + request.limit), cells: entities.flatMap(e => dates.map(date => ({ entity_id: e.id, date, checkout: model.addDays(date, 1), state: e.currency === "AED" ? "indicative" : "unknown", availability: "available", amount: e.currency === "AED" ? "610.36" : null, currency: e.currency, amount_basis: "website_calendar_rate", observed_at: e.observed_at, offers: [] }))), source_context: { bnbme_direct: { adults: null, taxes_included: null, fees_included: null } } };
  }
  if (u.pathname === "/api/intelligence/str/compset") {
    const subject = f.properties.find(p => p.id === q.get("subject_id"));
    const decision = q.get("decision"), id = q.get("candidate_id"), offset = Number(q.get("offset") || 0), limit = Number(q.get("limit") || 50);
    const rows = f.candidates.filter(c => (!id || c.id === id) && (!decision || (decision === "selected" ? c.selected : c.eligibility === decision)));
    return { subject, request: { subject_id: subject.id, offset, limit, decision, candidate_id: id }, candidates: rows.slice(offset, offset + limit), candidate_total: rows.length, all_candidate_total: f.candidates.length, map_points: f.candidates.map(({ id, title, latitude, longitude, eligibility, selected }) => ({ id, title, latitude, longitude, eligibility, selected })), criteria: { radius_km: 2 }, summary: { selected_count: 6 }, adaptive: { steps: [], subject_core_unknown_fields: ["room_type"] }, warnings: ["Unlinked source identities"] };
  }
  throw new Error(`Unexpected fetch ${url}`);
}
async function mounted(custom) {
  dual.destroy(); const f = fixtures(), doc = new Document(), root = doc.createElement("div"); doc.body.appendChild(root); const requests = [];
  global.fetch = async (url, options) => { requests.push({ url, options }); const answer = custom ? await custom(url, options, f) : responder(f, url); return { ok: true, json: async () => answer }; };
  await dual.mount(root); await settled(); return { root, doc, requests, f };
}
test("dual mount is lazy GET-only and constructs only the desktop calendar by default", async () => {
  const { root, requests } = await mounted();
  assert.ok(requests.every(r => r.options.method === "GET")); assert.ok(!requests.some(r => r.url === "/api/workspace" || r.url.includes("/hotel")));
  assert.match(root.textContent, /Dubai apartment/); assert.match(root.textContent, /GBP/); assert.match(root.textContent, /Available · price unknown/); assert.match(root.textContent, /Saved Dubai Airbnb comparison set/);
  assert.ok(!descendants(root).some(n => n.className === "dw-day-strip")); assert.ok(descendants(root).some(n => n.className.includes("dw-desktop-calendar"))); dual.destroy();
});
test("property and studio filters request the whole filtered population before pagination", async () => {
  const { root, requests } = await mounted(); await choose(root, "Location", "London"); assert.match(root.textContent, /London apartment/); assert.doesNotMatch(find(root, n => n.className === "dw-canvas").textContent, /Dubai apartment/);
  await choose(root, "Location", "Dubai"); await choose(root, "Bedrooms", "0"); assert.ok(requests.some(r => r.url.includes("bedrooms=0"))); assert.match(root.textContent, /Studio/); dual.destroy();
});
test("comparison audit pagination and decision filters stay server-scoped", async () => {
  const { root, requests } = await mounted(); clickText(root, "Comparison set"); await settled(); assert.match(root.textContent, /60 matching saved candidates/); assert.match(root.textContent, /1–25 of 60/);
  find(root, n => n.getAttribute("aria-label") === "Next candidate page").click(); await settled(); assert.match(root.textContent, /26–50 of 60/); assert.ok(requests.some(r => r.url.includes("offset=25")));
  await choose(root, "Saved decision", "selected"); assert.match(root.textContent, /6 matching saved candidates/); assert.ok(requests.some(r => r.url.includes("decision=selected") && r.url.includes("offset=0"))); dual.destroy();
});
test("map uses all compact points and lazily loads exactly one candidate audit", async () => {
  const { root, requests } = await mounted(); clickText(root, "Map"); await settled(); assert.match(root.textContent, /60 observed candidates/); assert.match(root.textContent, /Map library is unavailable/);
  const b = find(root, n => n.className === "dw-map-candidate"); b.click(); await settled(); assert.ok(requests.some(r => r.url.includes("candidate_id=airbnb%3A10"))); assert.match(root.textContent, /floor_area_sqm/); assert.ok(!descendants(root).some(n => n.tagName === "IMG")); assert.ok(!descendants(root).some(n => String(n.href || "").startsWith("javascript:"))); dual.destroy();
});
test("hotel modes preserve exact source prices and recorded offer conditions", async () => {
  const { root, requests } = await mounted(); clickText(root, "Hotels"); await settled(); assert.ok(requests.some(r => r.url === "/api/intelligence/hotel")); assert.match(root.textContent, /2 sources with rates/);
  await choose(root, "Observation source", "agoda"); assert.match(root.textContent, /INR 5169.00/); clickText(root, "Table");
  find(root, n => n.tagName === "BUTTON" && n.textContent === "All offers →").click(); assert.match(root.textContent, /Membership coupon/); assert.match(root.textContent, /Taxes includedNo/); assert.match(root.textContent, /Fees includedNo/);
  assert.ok(requests.every(r => r.options.method === "GET")); dual.destroy();
});
test("hotel calendar exposes each source and detailed offer terms through Yellow table controls", async () => {
  const { root, requests } = await mounted(async (url, options, fixture) => {
    const offer = fixture.hotel.dataset.cells[0].offers[0];
    Object.assign(offer, { rate_plan_name: "Breakfast Flex", payment_terms: "Pay at property", cancellation_terms: "Free before 18:00", taxes: "INR 500", fees: "INR 100", coupon: "MEMBER10" });
    return responder(fixture, url);
  });
  clickText(root, "Hotels"); await settled();
  const calendar = find(root, n => n.className && n.className.includes("dw-month-grid"));
  assert.match(calendar.textContent, /Agoda/); assert.match(calendar.textContent, /Google Hotels/); assert.match(calendar.textContent, /INR 5169.00/);
  const day = find(calendar, n => n.tagName === "BUTTON" && n.className.includes("dw-month-cell") && n.textContent.includes("INR 5169.00")); day.click();
  assert.match(root.textContent, /Pay at property/); assert.match(root.textContent, /Free before 18:00/); assert.match(root.textContent, /INR 500/); assert.match(root.textContent, /MEMBER10/);
  clickText(root, "Close ×"); clickText(root, "Table");
  assert.match(root.textContent, /Breakfast Flex/); assert.match(root.textContent, /Pay at property/);
  const search = find(root, n => n.getAttribute("aria-label") === "Search saved hotel rates"); search.value = "Breakfast Flex"; search.dispatch("input");
  const table = find(root, n => n.tagName === "TABLE" && n.className.includes("dw-hotel-rate-table"));
  assert.match(table.textContent, /Breakfast Flex/); assert.doesNotMatch(table.textContent, /Google Hotels/);
  clickText(root, "Columns"); const paymentToggle = find(root, n => n.getAttribute("aria-label") === "Show Payment column"); paymentToggle.checked = false; paymentToggle.dispatch("change");
  assert.doesNotMatch(table.textContent, /Pay at property/);
  clickText(root, "Filter"); const sourceFilter = find(root, n => n.getAttribute("aria-label") === "Observation source"); sourceFilter.focus(); await choose(root, "Observation source", "agoda");
  assert.equal(root.ownerDocument.activeElement.getAttribute("aria-label"), "Observation source"); assert.match(root.textContent, /Breakfast Flex/); assert.doesNotMatch(find(root, n => n.tagName === "TABLE" && n.className.includes("dw-hotel-rate-table")).textContent, /Google Hotels/);
  assert.ok(requests.every(request => request.options.method === "GET")); dual.destroy();
});
test("switching to hotels invalidates an older STR response", async () => {
  let unblock; const { root, f } = await mounted(async (url, options, f) => responder(f, url));
  global.fetch = async (url, options) => {
    if (url.includes("/str/calendar") && url.includes("London")) return { ok: true, json: () => new Promise(resolve => { unblock = () => resolve(responder(f, url)); }) };
    return { ok: true, json: async () => responder(f, url) };
  };
  const selector = find(root, n => n.getAttribute("aria-label") === "Location"); selector.value = "London"; selector.dispatch("change"); await settled();
  clickText(root, "Hotels"); await settled(); unblock(); await settled(); assert.match(root.textContent, /Hotel Aketa/); assert.doesNotMatch(find(root, n => n.className === "dw-canvas").textContent, /London apartment/); dual.destroy();
});
test("mismatched returned filter context is rejected without painting wrong data", async () => {
  const { root } = await mounted(async (url, options, f) => { const response = responder(f, url); if (url.includes("/str/calendar")) response.request.city = "London"; return response; });
  assert.match(root.textContent, /different dates, filters or property page/); assert.doesNotMatch(find(root, n => n.className === "dw-canvas").textContent, /Dubai apartment/); dual.destroy();
});
test("different source revision cannot mix into an already loaded summary", async () => {
  const { root } = await mounted(async (url, options, f) => { const response = responder(f, url); if (url.includes("/str/calendar")) response.revision = "later-source-revision"; return response; });
  assert.match(root.textContent, /Saved sources changed/); assert.doesNotMatch(find(root, n => n.className === "dw-canvas").textContent, /Dubai apartment/); dual.destroy();
});
test("detail close restores focus and saved-source context is not replaced by view filters", async () => {
  const { root, doc } = await mounted(); const cell = find(root, n => n.className.includes("dw-cell dw-cell-indicative")); cell.focus(); cell.click(); assert.match(root.textContent, /Source context/); assert.match(root.textContent, /adults: Unknown/);
  clickText(root, "Close ×"); assert.equal(doc.activeElement, cell); assert.ok(find(root, n => n.className === "dw-inspector").hidden); dual.destroy();
});
test("API404 leaves an actionable restart message and never triggers collection", async () => {
  dual.destroy(); const doc = new Document(), root = doc.createElement("div"); doc.body.appendChild(root); const requests = [];
  global.fetch = async (url, options) => { requests.push({ url, options }); return { ok: false, status: 404, json: async () => ({}) }; };
  await dual.mount(root); assert.match(root.textContent, /Restart CompSet Studio/); assert.ok(requests.every(r => r.options.method === "GET")); dual.destroy();
});
test("imported hotel selection cannot borrow Aketa rates or start a new collector", async () => {
  const { root, requests } = await mounted(async (url, options, f) => {
    f.summary.hotel.portfolio = { profiles: [{ id: "lighthouse:42", title: "Configured Hill Hotel", city: "Shimla", roles: ["account_property"], rate_coverage: "not_collected", observed_at: "2026-09-28T07:00:00Z" }] };
    return responder(f, url);
  });
  clickText(root, "Hotels"); await settled(); await choose(root, "Hotel", "lighthouse:42");
  const canvas = find(root, n => n.className === "dw-canvas"); assert.match(canvas.textContent, /Configured Hill Hotel/); assert.match(canvas.textContent, /No dated rate dataset/); assert.doesNotMatch(canvas.textContent, /5169|Google Hotels|Premium Single/);
  assert.match(root.textContent, /collection not configured/); assert.equal(find(root, n => n.tagName === "BUTTON" && n.textContent === "Fetch fresh data").disabled, true); assert.ok(requests.every(r => r.options.method === "GET")); dual.destroy();
});

test("configured competitor names stay with the selected hotel and remain non-priced non-map labels", async () => {
  const { root, requests } = await mounted((url, options, f) => {
    f.summary.hotel.portfolio = { profiles: [{ id: "lighthouse:42", title: "Configured Hill Hotel", configured_label_count: 2, configured_label_status: "observed_name_only" }, { id: "lighthouse:43", title: "Configured Coast Hotel", configured_label_count: 1, configured_label_status: "observed_name_only" }] };
    f.hotel.portfolio = { configured_labels: { status: "observed_name_only", groups: [
      { subject_id: "lighthouse:42", competitor_labels: ["Hill Peer One", "Hill Peer Two"], identity_status: "name_only_unresolved", observed_at: "2026-09-28T09:57:29Z", source_url: "https://app.mylighthouse.com/market/example" },
      { subject_id: "lighthouse:43", competitor_labels: ["Coast Peer"], identity_status: "name_only_unresolved", observed_at: "2026-09-28T09:57:29Z", source_url: "https://app.mylighthouse.com/market/example" }] } };
    return responder(f, url);
  });
  clickText(root, "Hotels"); await settled(); await choose(root, "Hotel", "lighthouse:42"); clickText(root, "Comparison set"); await settled();
  let canvas = find(root, n => n.className === "dw-canvas");
  assert.match(canvas.textContent, /2 names saved for this hotel/); assert.match(canvas.textContent, /Hill Peer One/); assert.match(canvas.textContent, /OTA identities unverified/); assert.match(canvas.textContent, /Membership observed/);
  assert.doesNotMatch(canvas.textContent, /Coast Peer|5169|Premium Single|Observed hotel/);
  assert.equal(descendants(canvas).filter(n => n.tagName === "BUTTON" && /Hill Peer/.test(n.textContent)).length, 0);
  assert.equal(find(root, n => n.tagName === "BUTTON" && n.textContent === "Fetch fresh data").disabled, true);
  await choose(root, "Hotel", "lighthouse:43"); canvas = find(root, n => n.className === "dw-canvas"); assert.match(canvas.textContent, /Coast Peer/); assert.doesNotMatch(canvas.textContent, /Hill Peer|5169/);
  clickText(root, "Map"); await settled(); canvas = find(root, n => n.className === "dw-canvas"); assert.match(canvas.textContent, /Map locations are unknown/); assert.equal(descendants(canvas).filter(n => n.className === "dw-map").length, 0);
  assert.ok(requests.every(r => r.options.method === "GET")); dual.destroy();
});

test("missing configured membership stays unknown while an observed empty group displays zero", async () => {
  const { root } = await mounted((url, options, f) => {
    f.summary.hotel.portfolio = { profiles: [{ id: "lighthouse:42", title: "Unknown Group Hotel", configured_label_count: null, configured_label_status: "not_observed" }, { id: "lighthouse:43", title: "Observed Empty Hotel", configured_label_count: 0, configured_label_status: "observed_name_only" }] };
    f.hotel.portfolio = { configured_labels: { status: "observed_name_only", groups: [{ subject_id: "lighthouse:43", identity_status: "name_only_unresolved", competitor_labels: [] }] } };
    return responder(f, url);
  });
  clickText(root, "Hotels"); await settled(); await choose(root, "Hotel", "lighthouse:42"); clickText(root, "Comparison set"); await settled();
  let canvas = find(root, n => n.className === "dw-canvas"); assert.match(canvas.textContent, /Coverage unknown/); assert.doesNotMatch(canvas.textContent, /0 names saved/);
  const coverage = find(root, n => n.className === "dw-coverage"); assert.match(coverage.textContent, /—configured names/);
  await choose(root, "Hotel", "lighthouse:43"); canvas = find(root, n => n.className === "dw-canvas"); assert.match(canvas.textContent, /0 names saved/); assert.match(canvas.textContent, /observed group contains no configured names/); dual.destroy();
});
test("new workspace delegates explicit fresh and pause to one fixed collection job", async t => {
  t.after(() => dual.destroy()); let job = { state: "idle", job_id: null };
  const { root, requests } = await mounted(async (url, options, f) => {
    if (url === "/api/workspace/job") return job;
    if (url === "/api/workspace/collect") { const body = JSON.parse(options.body); job = { state: "running", job_id: "fixed-job", dataset_id: body.dataset_id, mode: body.mode, busy: true, pause_supported: true, updated_at: "2026-09-28T08:00:00Z", context: { adults: 1, rooms: 1, currency: "INR" }, progress: {}, message: "Collecting bounded source evidence" }; return job; }
    if (url === "/api/workspace/pause") { assert.equal(JSON.parse(options.body).job_id, "fixed-job"); return job = { ...job, pause_requested: true }; }
    return responder(f, url);
  });
  clickText(root, "Hotels"); await settled(); clickText(root, "Fetch fresh data"); await settled(); assert.equal(JSON.parse(requests.find(r => r.url === "/api/workspace/collect").options.body).dataset_id, "aketa");
  clickText(root, "Short-term rentals"); await settled(); assert.match(root.textContent, /fixed-job/); assert.match(root.textContent, /Hotel Aketa/);
  clickText(root, "Pause collection"); await settled(); assert.equal(requests.filter(r => r.options.method === "POST").length, 2); assert.ok(!requests.some(r => r.url === "/api/workspace"));
});
test("Collection tools opens the existing shell only on explicit click", async () => {
  const { root } = await mounted(); let opens = 0; global.CompSetOpenTools = () => { opens++; };
  assert.equal(opens, 0); clickText(root, "Collection tools →"); assert.equal(opens, 1); delete global.CompSetOpenTools; dual.destroy();
});
test("mobile builds only daily rows; breakpoint changes keep the selected date and make no request", async t => {
  const screen = viewport(390); t.after(() => { dual.destroy(); screen.restore(); });
  const { root, requests } = await mounted();
  assert.equal(descendants(root).filter(n => n.className.startsWith("dw-cell ")).length, 0);
  assert.equal(descendants(root).filter(n => n.className === "dw-day-row").length, 2);
  const count = requests.length, toolbar = find(root, n => n.className === "dw-toolbar").children[0];
  find(root, n => n.getAttribute("aria-label") === "Arrival 2026-09-29").click();
  assert.equal(find(root, n => n.className === "dw-toolbar").children[0], toolbar);
  screen.resize(1280); assert.equal(descendants(root).filter(n => n.className.startsWith("dw-cell ")).length, 28);
  assert.equal(descendants(root).filter(n => n.className === "dw-mobile-days").length, 0);
  screen.resize(390); assert.equal(find(root, n => n.getAttribute("aria-label") === "Arrival 2026-09-29").getAttribute("aria-pressed"), "true");
  assert.equal(requests.length, count);
});
test("mobile hotel intersects selected day/source and retains source basis and offer conditions", async t => {
  const screen = viewport(390); t.after(() => { dual.destroy(); screen.restore(); });
  const { root, requests } = await mounted(); clickText(root, "Hotels"); await settled();
  let canvas = find(root, n => n.className === "dw-canvas");
  assert.equal(descendants(root).filter(n => n.className === "dw-month-grid").length, 0);
  assert.match(canvas.textContent, /INR 5169.00/); assert.match(canvas.textContent, /₹5K/); assert.match(canvas.textContent, /ota display price/); assert.match(canvas.textContent, /google calendar minimum/);
  find(canvas, n => n.tagName === "BUTTON" && n.textContent === "INR 5169.00").click(); assert.match(root.textContent, /Membership coupon/); clickText(root, "Close ×");
  find(root, n => n.getAttribute("aria-label") === "Arrival 2026-09-29").click(); canvas = find(root, n => n.className === "dw-canvas");
  assert.match(canvas.textContent, /Unavailable/); assert.doesNotMatch(canvas.textContent, /5169|₹5K/);
  await choose(root, "Observation source", "google_hotels"); canvas = find(root, n => n.className === "dw-canvas"); assert.match(canvas.textContent, /Google Hotels/); assert.doesNotMatch(canvas.textContent, /Agoda|5169/);
  screen.resize(1280); assert.ok(descendants(root).some(n => n.className === "dw-month-grid")); assert.match(canvas.textContent, /₹5K/);
  assert.ok(requests.every(r => r.options.method === "GET"));
});
test("map keeps one tile layer and zoom across circle edits and responsive layout changes", async t => {
  const screen = viewport(1280), leaflet = fakeLeaflet(), previous = global.L; global.L = leaflet.api;
  t.after(() => { dual.destroy(); screen.restore(); global.L = previous; });
  const { root, requests } = await mounted(); clickText(root, "Map"); await settled();
  const map = leaflet.stats.maps[0], originalCount = requests.length; map.zoom = 17;
  const radius = find(root, n => n.getAttribute("aria-label") === "Map view radius in kilometres"); radius.value = "4"; radius.dispatch("change");
  assert.equal(leaflet.stats.circles[0].radius, 4000); assert.equal(leaflet.stats.maps.length, 1); assert.equal(map.zoom, 17);
  map.handlers.click({ latlng: { lat: 25.191, lng: 55.27 } }); assert.deepEqual(leaflet.stats.circles[0].point, [25.19, 55.27], "Ordinary map clicks retain the area");
  clickText(root, "Move center");
  map.node.dispatch("pointerdown", { pointerId: 1, pointerType: "mouse", clientX: 0, clientY: 0, latlng: { lat: 25.19, lng: 55.27 } });
  map.node.dispatch("pointerup", { pointerId: 1, pointerType: "mouse", clientX: 20, clientY: 20, latlng: { lat: 25.192, lng: 55.27 } });
  assert.deepEqual(leaflet.stats.circles[0].point, [25.192, 55.27], "Explicit center movement commits on pointer release");
  screen.resize(390); assert.equal(leaflet.stats.maps[0], map); assert.equal(leaflet.stats.tiles, 1); assert.equal(leaflet.stats.removed, 0); assert.equal(map.zoom, 17); assert.ok(leaflet.stats.invalidations >= 1);
  assert.equal(Object.keys(map.handlers).length, 1); assert.equal(requests.length, originalCount);
  await choose(root, "Saved decision", "selected"); assert.equal(leaflet.stats.maps[0], map); assert.equal(leaflet.stats.maps.length, 1); assert.equal(map.zoom, 17); assert.match(root.textContent, /6 observed candidates/);
  clickText(root, "Hotels"); await settled(); assert.equal(leaflet.stats.removed, 1);
  clickText(root, "Map"); await settled(); assert.deepEqual(leaflet.stats.maps.at(-1).center, [30.3, 78.04]);
});
test("superseded JSON reads are aborted and cannot paint or report an old error", async t => {
  t.after(() => dual.destroy()); let finishOld, oldSignal;
  const { root, f } = await mounted();
  global.fetch = async (url, options) => {
    if (url.includes("city=London")) { oldSignal = options.signal; return { ok: true, json: () => new Promise(resolve => { finishOld = () => resolve(responder(f, url)); }) }; }
    return { ok: true, json: async () => responder(f, url) };
  };
  await choose(root, "Location", "London"); clickText(root, "Hotels"); await settled(); assert.equal(oldSignal.aborted, true);
  finishOld(); await settled(); assert.match(root.textContent, /Hotel Aketa/); assert.doesNotMatch(root.textContent, /superseded|Could not load/);
});
test("overlapping comparison and map consumers coalesce one request without aborting the surviving owner", async t => {
  t.after(() => dual.destroy()); let resolve, signal, calls = 0;
  const { root, f } = await mounted();
  global.fetch = async (url, options) => { if (url.includes("/str/compset")) { calls++; signal = options.signal; return { ok: true, json: () => new Promise(done => { resolve = () => done(responder(f, url)); }) }; } return { ok: true, json: async () => responder(f, url) }; };
  clickText(root, "Comparison set"); await settled(); clickText(root, "Map"); await settled(); assert.equal(calls, 1); assert.equal(signal.aborted, false);
  resolve(); await settled(); assert.match(root.textContent, /60 observed candidates/); assert.doesNotMatch(root.textContent, /Could not load/);
});
test("explicit reload aborts old generation while stale completion cannot delete a new identical pending read", async t => {
  t.after(() => dual.destroy()); const deferred = [];
  const { root, f } = await mounted();
  global.fetch = async (url, options) => {
    if (url === "/api/intelligence") return { ok: true, json: () => new Promise(resolve => deferred.push({ signal: options.signal, resolve: () => resolve(f.summary) })) };
    return { ok: true, json: async () => responder(f, url) };
  };
  const first = dual.refresh(); await settled(); const second = dual.refresh(); await settled(); assert.equal(deferred[0].signal.aborted, true); assert.equal(deferred[1].signal.aborted, false);
  deferred[0].resolve(); await first; assert.equal(deferred[1].signal.aborted, false);
  deferred[1].resolve(); await second; assert.match(root.textContent, /Dubai apartment/); assert.doesNotMatch(root.textContent, /Could not reload/);
});
test("failed coalesced reads are retriable without caching bad evidence", async t => {
  t.after(() => dual.destroy()); let calls = 0;
  const { root, f } = await mounted();
  global.fetch = async (url, options) => { if (url.includes("/hotel") && ++calls === 1) return { ok: false, status: 503 }; return { ok: true, json: async () => responder(f, url) }; };
  clickText(root, "Hotels"); await settled(); assert.match(root.textContent, /HTTP 503/);
  clickText(root, "Hotels"); await settled(); assert.equal(calls, 2); assert.match(root.textContent, /2 sources with rates/); assert.doesNotMatch(root.textContent, /Could not load/);
});
test("mobile details trap focus, exclude hidden controls, release background and restore a connected fallback", async t => {
  const screen = viewport(390); t.after(() => { dual.destroy(); screen.restore(); });
  const { root, doc } = await mounted();
  const opener = find(root, n => n.className === "dw-property-name"); opener.focus(); opener.click();
  const inspector = find(root, n => n.className === "dw-inspector"), canvas = find(root, n => n.className === "dw-canvas");
  assert.equal(inspector.getAttribute("aria-modal"), "true"); assert.equal(canvas.inert, true);
  const focusables = inspector.querySelectorAll(), first = focusables[0], last = focusables.at(-1);
  assert.equal(doc.activeElement, first); first.focus(); doc.dispatch("keydown", { key: "Tab", shiftKey: true }); assert.equal(doc.activeElement, last);
  last.focus(); doc.dispatch("keydown", { key: "Tab" }); assert.equal(doc.activeElement, first);
  last.hidden = true; doc.dispatch("keydown", { key: "Tab", shiftKey: true }); assert.equal(doc.activeElement, first); last.hidden = false;
  opener.focus(); doc.dispatch("focusin", { target: opener }); assert.equal(doc.activeElement, first);
  opener.remove(); doc.dispatch("keydown", { key: "Escape" }); assert.equal(inspector.hidden, true); assert.equal(canvas.inert, false); assert.equal(doc.activeElement.isConnected, true);
  const stable = doc.activeElement; doc.dispatch("keydown", { key: "Tab", shiftKey: true }); assert.equal(doc.activeElement, stable);
  find(root, n => n.className === "dw-property-name").click(); await dual.refresh(); assert.equal(doc.activeElement.isConnected, true);
});
test("mobile export contains only the displayed day/source with original quote basis", async t => {
  const screen = viewport(390), originalCreate = URL.createObjectURL, originalRevoke = URL.revokeObjectURL; let blob;
  URL.createObjectURL = value => { blob = value; return "blob:fixture"; }; URL.revokeObjectURL = () => {};
  t.after(() => { dual.destroy(); screen.restore(); URL.createObjectURL = originalCreate; URL.revokeObjectURL = originalRevoke; });
  const { root } = await mounted(); find(root, n => n.getAttribute("aria-label") === "Arrival 2026-09-29").click(); clickText(root, "Export visible page ↓");
  let csv = await blob.text(); assert.equal(csv.split("\r\n").length, 3); assert.match(csv, /2026-09-29/); assert.match(csv, /website_calendar_rate/); assert.match(csv, /GBP/);
  clickText(root, "Hotels"); await settled(); find(root, n => n.getAttribute("aria-label") === "Arrival 2026-09-29").click();
  await choose(root, "Observation source", "agoda"); clickText(root, "Export visible page ↓"); csv = await blob.text();
  assert.equal(csv.split("\r\n").length, 2); assert.match(csv, /unavailable/); assert.doesNotMatch(csv, /5169|google/);
});
test("destroy aborts a pending detail and late completion cannot change detached UI", async t => {
  t.after(() => dual.destroy()); let signal, resolve;
  const { root, f } = await mounted(); clickText(root, "Map"); await settled();
  global.fetch = async (url, options) => { signal = options.signal; return { ok: true, json: () => new Promise(done => { resolve = () => done(responder(f, url)); }) }; };
  const opener = find(root, n => n.className === "dw-map-candidate"); opener.focus(); opener.click(); await settled(); dual.destroy();
  assert.equal(signal.aborted, true); const before = root.textContent; resolve(); await settled(); assert.equal(root.textContent, before);
});
if (process.env.COMPSET_DUAL_REAL_DATA === "1") test("actual saved projections render both modes and scoped comparison evidence", async t => {
  const { execFileSync } = require("node:child_process");
  const payload = JSON.parse(execFileSync(".venv/Scripts/python.exe", ["-c", "import json; from pathlib import Path; from compset import intelligence as i; r=Path('data'); s=i.summary(r); c=i.str_calendar(r,start=s['str']['default_start']); p=i.str_compset(r,s['str']['properties'][0]['id'],limit=25); h=i.hotel(r); print(json.dumps(dict(summary=s,calendar=c,comparison=p,hotel=h),ensure_ascii=True))"], { encoding: "utf8", maxBuffer: 12 * 1024 * 1024 }));
  const screen = viewport(1280); dual.destroy(); t.after(() => { dual.destroy(); screen.restore(); }); const doc = new Document(), root = doc.createElement("div"); doc.body.appendChild(root); const requests = [];
  global.fetch = async (url, options) => { requests.push({ url, options }); return { ok: true, json: async () => url === "/api/workspace/job" ? { state: "idle", job_id: null } : url === "/api/intelligence" ? payload.summary : url.includes("/str/calendar") ? payload.calendar : url.includes("/str/compset") ? payload.comparison : payload.hotel }; };
  await dual.mount(root); assert.match(root.textContent, /Your rental portfolio/); assert.ok(root.textContent.includes(payload.calendar.entities[0].title)); assert.doesNotMatch(root.textContent, /Could not load/);
  clickText(root, "Comparison set"); await settled(); assert.ok(root.textContent.includes(payload.comparison.subject.title)); assert.doesNotMatch(root.textContent, /Could not load/);
  clickText(root, "Hotels"); await settled(); assert.match(root.textContent, /Hotel Aketa/); assert.match(root.textContent, /source/); assert.doesNotMatch(root.textContent, /Could not load/);
  clickText(root, "Table"); assert.match(root.textContent, /Google Hotels/); assert.match(root.textContent, /Agoda/); assert.ok(requests.every(r => r.options.method === "GET"));
  for (const group of (payload.hotel.portfolio && payload.hotel.portfolio.configured_labels && payload.hotel.portfolio.configured_labels.groups || [])) {
    await choose(root, "Hotel", group.subject_id); clickText(root, "Comparison set"); await settled();
    const canvas = find(root, n => n.className === "dw-canvas");
    assert.ok(canvas.textContent.includes(`${group.competitor_labels.length} names saved for this hotel`));
    group.competitor_labels.forEach(label => assert.ok(canvas.textContent.includes(label)));
    assert.match(canvas.textContent, /OTA identities unverified/); assert.doesNotMatch(canvas.textContent, /Premium Single|Google Hotels/);
    assert.equal(find(root, n => n.tagName === "BUTTON" && n.textContent === "Fetch fresh data").disabled, true);
  }
  if (payload.hotel.portfolio && payload.hotel.portfolio.profiles.length) await choose(root, "Hotel", "aketa");
  clickText(root, "Rates"); await settled(); screen.resize(390);
  assert.equal(descendants(root).filter(n => n.className === "dw-month-grid").length, 0);
  const mobileRates = find(root, n => n.className === "dw-hotel-days");
  assert.ok(mobileRates.textContent.includes(payload.hotel.dataset.entities[0].label));
  clickText(root, "Short-term rentals"); await settled();
  assert.equal(descendants(root).filter(n => n.className.startsWith("dw-cell ")).length, 0);
  assert.ok(descendants(root).some(n => n.className === "dw-day-row"));
});

if (process.env.COMPSET_DUAL_BENCH === "1") test("repeatable offline DOM construction and map lifecycle measurement", async t => {
  const screen = viewport(390), leaflet = fakeLeaflet(), previousL = global.L;
  t.after(() => { dual.destroy(); screen.restore(); global.L = previousL; });
  global.L = leaflet.api;
  const { root, doc, requests } = await mounted((url, options, f) => {
    if (url === "/api/intelligence") { const first = f.properties[0]; f.properties = Array.from({ length: 25 }, (_, i) => ({ ...first, id: `bnbme_direct:${i + 1}`, subject_id: `bnbme_direct:${i + 1}`, title: `Home ${i + 1}`, label: `Home ${i + 1}` })); f.summary.str.properties = f.properties; }
    return responder(f, url);
  });
  const initialCreated = doc.created, retainedNodes = descendants(root).length, initialDesktopCells = descendants(root).filter(n => n.className.startsWith("dw-cell ")).length;
  const beforeDay = doc.created; find(root, n => n.className === "dw-day-strip").children[1].click();
  const dayCreated = doc.created - beforeDay;
  clickText(root, "Map"); await settled(); const currentMap = leaflet.stats.maps.at(-1); currentMap.zoom = 16;
  const beforeMap = doc.created, beforeRequests = requests.length;
  const radius = find(root, n => n.getAttribute("aria-label") === "Map view radius in kilometres"); radius.value = "3"; radius.dispatch("change");
  t.diagnostic(JSON.stringify({ fixture: "25 properties x14 dates;390px;60 map points", initialCreated, retainedNodes, dayCreated,
    mapEditCreated: doc.created - beforeMap, mapInstances: leaflet.stats.maps.length, tileLayers: leaflet.stats.tiles,
    mapRemovals: leaflet.stats.removed, zoomAfterEdit: leaflet.stats.maps.at(-1).zoom, mapEditRequests: requests.length - beforeRequests,
    initialDesktopCells }));
});
