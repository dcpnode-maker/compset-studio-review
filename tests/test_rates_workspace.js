"use strict";

// Node-only DOM proof. Deliberately does not start a browser or make network calls.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const rates = require("../compset/static/rates-workspace.js");
const { model } = rates;

function fixture() {
  const dates = Array.from({ length: 9 }, (_, i) => `2026-10-${String(i + 1).padStart(2, "0")}`);
  const hotel = {
    id: "aketa", label: "Hotel Aketa · Dehradun", kind: "hotel", currency: "INR", dates,
    observed_at: "2026-09-28T07:00:00+00:00", context: { adults: 1, rooms: 1, children: 0, currency: "INR", stay_nights: 1 },
    entities: [{ id: "google", label: "Google Hotels", source: "google_hotels", role: "source", source_url: "https://www.google.com/travel/hotels/entity/test" }, { id: "agoda", label: "Agoda", source: "agoda", role: "source", source_url: "https://www.agoda.com/hotel-aketa/hotel/dehradun-in.html" }],
    cells: [], summary: { date_cells: 18, quoted_cells: 1, indicative_cells: 9, unavailable_cells: 1, restricted_cells: 0, unknown_cells: 7, rate_rows: 10 },
    source_states: [{ source: "agoda", status: "unavailable", last_stay: dates[1], observed_at: "2026-09-28T07:00:00+00:00", reason: "source_unavailable_for_requested_stay" }],
    profiles: [{ source: "agoda", provider_id: "110205", name: "Current Aketa", sale_status: "dated_display_offer_observed", branding: "current_name", url: "https://www.agoda.com/hotel-aketa/hotel/dehradun-in.html", observed_at: "2026-09-28T07:00:00+00:00" }, { source: "agoda", provider_id: "27746358", name: "Legacy Aketa", sale_status: "unknown", branding: "legacy_name" }],
    comparison_note: "Room, tax and meal conditions have not been matched for rate parity.", candidates: [], warnings: [],
  };
  for (const [i, date] of dates.entries()) {
    const checkout = `2026-10-${String(i + 2).padStart(2, "0")}`;
    hotel.cells.push({ entity_id: "google", date, checkout, state: "indicative", amount: null, display_amount: "₹5K", currency: "INR", precision: "abbreviated", amount_basis: "google_calendar_minimum", offers: [], observed_at: hotel.observed_at });
    hotel.cells.push({ entity_id: "agoda", date, checkout, state: i === 0 ? "quoted" : i === 1 ? "unavailable" : "unknown", amount: i === 0 ? "5169.25" : null, currency: "INR", precision: i === 0 ? "exact" : null, amount_basis: i === 0 ? "one_night_stay_total" : null, reason: i === 1 ? "source_unavailable_for_requested_stay" : i > 1 ? "not_observed" : null, observed_at: hotel.observed_at, offers: i === 0 ? [{ amount: "5169.25", currency: "INR", precision: "exact", room_name: "Deluxe", rate_plan: "Member offer", taxes_included: false, conditions: ["Member price", "Coupon applied"], observed_at: hotel.observed_at }] : [] });
  }
  const airbnb = {
    id: "airbnb-compset", kind: "airbnb", label: "Airbnb · Dubai", currency: "AED", dates: dates.slice(0, 2), context: { adults: 1, currency: "AED", stay_nights: 1 }, discovery_context: { adults: 2, stay_nights: 3 }, observed_at: hotel.observed_at,
    entities: [{ id: "subject", label: "BnBMe subject", source: "airbnb", role: "subject", source_url: "https://www.airbnb.com/rooms/123" }],
    cells: [{ entity_id: "subject", date: dates[0], checkout: dates[1], state: "quoted", currency: "AED", amount: "610.36", amount_basis: "stay_total", precision: "exact", observed_at: hotel.observed_at, offers: [{ amount: "610.36", currency: "AED", precision: "exact", rate_plan_name: "Non-refundable", observed_at: hotel.observed_at, rate_options: [{ rate_plan_name: "Non-refundable", is_selected: true, amount: "610.36", currency: "AED", amount_basis: "stay_total", cancellation_terms: ["No refund"], taxes_included: null, observed_at: hotel.observed_at }, { rate_plan_name: "Refundable", is_selected: false, amount: "650.40", currency: "AED", amount_basis: "stay_total", cancellation_terms: ["Cancel before the stated cutoff"], taxes_included: null, observed_at: hotel.observed_at }] }] }, { entity_id: "subject", date: dates[1], checkout: dates[2], state: "restricted", amount: null, currency: "AED", reason: "minimum_stay_not_met", offers: [] }],
    candidates: [{ id: "comp1", title: "<script>not HTML</script>", selected: true, bedrooms: 1, bathrooms: 1, rating: 4.8, review_count: 17, circle_distance_km: 0.24, eligibility: "eligible", host_name: "Host One", host_listing_count: 500, operator_size: "large", operator_size_basis: "public_profile_count", amenities: [{ title: "Pool", available: true }], source_url: "javascript:alert(1)" }, { id: "comp2", title: "Other apartment", selected: false, eligibility: "excluded", rejection_reasons: ["Bedroom count mismatch"], missing_fields: ["floor_area_sqm"] }],
    summary: { date_cells: 2, quoted_cells: 1, indicative_cells: 0, unavailable_cells: 0, restricted_cells: 1, unknown_cells: 0 }, profiles: [], source_states: [], warnings: [],
  };
  return { schema_version: 1, generated_at: "2026-09-28T08:00:00Z", datasets: [hotel, airbnb], warnings: [], portfolio: { observed_at: hotel.observed_at, properties: [{ id: "p1", title: "Dubai apartment", city: "Dubai", country: "UAE", bedrooms: 1, bathrooms: 1, person_capacity: 2, operator_name: "BnBMe", currency: "AED", publication_status: "active", link_status: "verified", source_url: "https://bnbmehomes.com/properties/dubai" }, { id: "p2", title: "London apartment", city: "London", country: "UK", currency: "GBP", source_url: "https://bnbmehomes.com/properties/london" }] } };
}

class Element {
  constructor(tagName, doc) { this.tagName = tagName.toUpperCase(); this.ownerDocument = doc; this.children = []; this.parentNode = null; this.attrs = {}; this.listeners = {}; this.className = ""; this._text = ""; this.disabled = false; this.hidden = false; this.classList = { add: (...names) => { this.className = [...new Set([...this.className.split(" "), ...names])].filter(Boolean).join(" "); } }; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
  set innerHTML(_) { throw new Error("Unsafe innerHTML in workspace"); }
  appendChild(child) { if (child.parentNode) child.remove(); this.children.push(child); child.parentNode = this; return child; }
  replaceChildren(...children) { for (const child of this.children) child.parentNode = null; this.children = []; this._text = ""; children.forEach(child => this.appendChild(child)); }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(child => child !== this); this.parentNode = null; }
  get isConnected() { return this === this.ownerDocument.body || Boolean(this.parentNode && this.parentNode.isConnected); }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  getAttribute(name) { return this.attrs[name]; }
  addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
  dispatch(name, properties = {}) { for (const fn of this.listeners[name] || []) fn({ target: this, preventDefault() {}, ...properties }); }
  click() { if (!this.disabled) this.dispatch("click"); }
  focus() { this.ownerDocument.activeElement = this; }
  querySelectorAll() { return descendants(this).filter(node => node.tagName === "BUTTON" || node.tagName === "SELECT" || node.tagName === "INPUT" || (node.tagName === "A" && node.href) || node.tabIndex === 0); }
}
class Document {
  constructor() { this.body = new Element("body", this); this.activeElement = this.body; this.listeners = {}; }
  createElement(tag) { return new Element(tag, this); }
  addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
  removeEventListener(name, fn) { this.listeners[name] = (this.listeners[name] || []).filter(item => item !== fn); }
}
function descendants(root) { return root.children.flatMap(child => [child, ...descendants(child)]); }
function find(root, predicate) { const match = descendants(root).find(predicate); assert.ok(match, "Expected matching rendered element"); return match; }
function clickText(root, text) { find(root, node => node.tagName === "BUTTON" && node.textContent === text).click(); }
function selectValue(root, value) { const select = find(root, node => node.tagName === "SELECT" && node.children.some(option => option.value === value)); select.value = value; select.dispatch("change"); }
async function mounted(payload = fixture(), handler = null) {
  const doc = new Document(), root = doc.createElement("div"); doc.body.appendChild(root);
  const requests = [];
  global.fetch = async (url, options) => { requests.push({ url, options }); return handler ? handler(url, options) : { ok: true, json: async () => url === "/api/workspace/job" ? { state: "idle", job_id: null, busy: false } : payload }; };
  await rates.mount(root);
  return { doc, root, requests };
}

test("model pages seven dates and scopes source, state and text together", () => {
  const dataset = fixture().datasets[0];
  assert.equal(model.visibleModel(dataset).cells.length, 14);
  assert.equal(model.visibleModel(dataset, { page: 1 }).cells.length, 4);
  assert.equal(model.visibleModel(dataset, { page: 100 }).page, 1);
  const view = model.visibleModel(dataset, { source: "agoda", state: "unavailable", query: "ago" });
  assert.equal(view.cells.length, 1); assert.equal(view.cells[0].cell.date, "2026-10-02");
  assert.equal(model.visibleModel(dataset, { source: "booking" }).cells.length, 0);
});

test("missing cells, unknown prices and abbreviated displays do not become zero or quotes", () => {
  const dataset = fixture().datasets[0]; dataset.cells = [];
  const view = model.visibleModel(dataset);
  assert.ok(view.cells.every(({ cell }) => cell.state === "unknown" && cell.amount === null));
  assert.equal(model.priceLabel({ state: "unknown", amount: "12", currency: "INR" }), "Unknown");
  assert.equal(model.priceLabel({ state: "unavailable", amount: "0" }), "Unavailable");
  assert.equal(model.priceLabel({ state: "indicative", amount: null, display_amount: "₹5K" }), "₹5K");
  assert.equal(model.priceLabel({ state: "quoted", amount: "610.36", currency: "AED" }), "AED 610.36");
});

test("CSV follows window and filters, retains source context and guards formulas", () => {
  const dataset = fixture().datasets[0]; dataset.entities[1].label = " \t=HYPERLINK(\"evil\")";
  const csv = model.exportCsv(dataset, { source: "agoda", state: "quoted" });
  assert.equal(csv.split("\r\n").length, 2);
  assert.match(csv, /"5169.25"/); assert.match(csv, /"INR"/); assert.match(csv, /"' \t=HYPERLINK/);
  assert.match(csv, /requested_context/); assert.match(csv, /Member price/);
  assert.doesNotMatch(csv, /google_calendar_minimum/);
  const page2 = model.exportCsv(dataset, { source: "agoda", page: 1 });
  assert.equal(page2.split("\r\n").length, 3); assert.doesNotMatch(page2, /2026-10-01/);
  for (const input of ["=SUM(1)", "+cmd", "-cmd", "@function", "  =function", "\ttext", "\rvalue", "\nvalue", "\u0000@cmd"]) assert.ok(model.csvField(input).startsWith('"\''), input);
  assert.equal(model.csvField(null), '""'); assert.equal(model.csvField('a"b'), '"a""b"');
});

test("only public http(s) property links can become anchors", () => {
  for (const url of ["javascript:alert(1)", "data:text/html,test", "file:///c:/private", "https://user:pass@airbnb.com/rooms/1", "http://127.0.0.1:8765/", "http://2130706433/", "http://10.1.2.3/", "http://localhost/", "https://test.local/", "http://[::1]/", "/relative"]) assert.equal(model.safeUrl(url), null, url);
  assert.equal(model.safeUrl("https://www.airbnb.com/rooms/123"), "https://www.airbnb.com/rooms/123");
});

test("observation age uses source timestamp and does not imply a live refresh", () => {
  assert.equal(model.ageLabel(null), "Time unknown");
  assert.equal(model.ageLabel("2026-09-27T00:00:00Z", Date.parse("2026-09-28T02:00:00Z")), "Historical · 1d old");
  assert.match(model.observedLabel("2026-09-28T07:00:00Z"), /12:30 IST/);
  assert.equal(model.contextSummary({ adults: 2, rooms: 1, currency: "INR" }), "2 adults · 1 room · INR");
});

test("mount defaults to Aketa with saved-only GET and interactive calendar paging", async () => {
  const { root, requests } = await mounted();
  assert.equal(requests.length, 2); assert.equal(requests[0].url, "/api/workspace"); assert.equal(requests[0].options.method, "GET"); assert.equal(requests[0].options.cache, "no-store"); assert.equal(requests[1].url, "/api/workspace/job"); assert.equal(requests[1].options.method, "GET");
  assert.match(root.textContent, /Reload saved data/); assert.match(root.textContent, /1 adult · 0 children · 1 room · 1 night · INR/);
  assert.equal(descendants(root).filter(node => node.className.includes("rw-rate-cell")).length, 14);
  find(root, node => node.getAttribute("aria-label") === "Next seven days").click();
  assert.equal(descendants(root).filter(node => node.className.includes("rw-rate-cell")).length, 4);
  assert.match(root.textContent, /8 Oct – 9 Oct 2026/);
  assert.equal(requests.length, 2);
});

test("source and evidence controls filter UI and distinguish contextual unavailability", async () => {
  const { root } = await mounted(); selectValue(root, "agoda"); selectValue(root, "unavailable");
  const buttons = descendants(root).filter(node => node.className.includes("rw-rate-cell"));
  assert.equal(buttons.length, 1); buttons[0].click();
  assert.match(root.textContent, /does not establish that the property is booked/);
  assert.match(root.textContent, /2 Oct 2026 → 3 Oct 2026/);
  assert.ok(descendants(root).some(node => node.getAttribute("aria-modal") === "true"));
  clickText(root, "Close ×");
  assert.ok(!descendants(root).some(node => node.getAttribute("aria-modal") === "true"));
});

test("Airbnb selection retains AED exact decimals and distinct refundable rate option", async () => {
  const { root } = await mounted(); selectValue(root, "airbnb-compset");
  assert.match(root.textContent, /1 adult · 1 night · AED/);
  find(root, node => node.className.includes("rw-rate-cell") && node.textContent.includes("610.36")).click();
  assert.match(root.textContent, /Non-refundable/); assert.match(root.textContent, /Refundable/); assert.match(root.textContent, /AED 650.40/); assert.match(root.textContent, /Alternative/); assert.match(root.textContent, /Cancel before the stated cutoff/);
});

test("candidate view renders actual decision, distance, operator and discovery context safely", async () => {
  const { root } = await mounted(); selectValue(root, "airbnb-compset"); clickText(root, "Competitor set");
  assert.match(root.textContent, /adults: 2/); assert.match(root.textContent, /0.24 km/); assert.match(root.textContent, /large · public profile count/); assert.match(root.textContent, /Bedroom count mismatch/);
  assert.match(root.textContent, /<script>not HTML<\/script>/);
  assert.ok(!descendants(root).some(node => node.tagName === "SCRIPT"));
  assert.ok(!descendants(root).some(node => node.tagName === "A" && String(node.href).startsWith("javascript:")));
  const search = find(root, node => node.tagName === "INPUT"); search.value = "host one"; search.dispatch("input");
  assert.match(root.textContent, /1 shown/); assert.doesNotMatch(root.textContent, /Other apartment/);
  selectValue(root, "selected"); assert.doesNotMatch(root.textContent, /Other apartment/);
  clickText(root, "Review match →"); assert.match(root.textContent, /observed host listings: 500/);
});

test("source profile identity and BnBMe portfolio remain separate", async () => {
  const { root } = await mounted(); clickText(root, "Sources & profiles");
  assert.match(root.textContent, /110205/); assert.match(root.textContent, /27746358/); assert.match(root.textContent, /Legacy Aketa/); assert.match(root.textContent, /whole-calendar availability claim/);
  clickText(root, "Portfolio overview"); assert.match(root.textContent, /Dubai apartment/); assert.match(root.textContent, /London apartment/);
  selectValue(root, "London"); assert.match(root.textContent, /1 of 2 catalog properties/); assert.doesNotMatch(root.textContent, /Dubai apartment/);
});

test("list toggle and client CSV download work without a new request", async () => {
  const { root, requests } = await mounted(); clickText(root, "List");
  assert.equal(descendants(root).filter(node => node.tagName === "BUTTON" && node.textContent === "Inspect →").length, 14);
  let captured = null, linkName = null;
  const create = URL.createObjectURL, revoke = URL.revokeObjectURL, timeout = global.setTimeout;
  URL.createObjectURL = blob => { captured = blob; return "blob:local-csv"; }; URL.revokeObjectURL = () => {}; global.setTimeout = fn => { fn(); return 0; };
  const oldClick = Element.prototype.click;
  Element.prototype.click = function () { if (this.tagName === "A" && this.download) linkName = this.download; return oldClick.call(this); };
  try {
    clickText(root, "Export filtered window ↓");
    assert.ok(captured instanceof Blob); assert.match(await captured.text(), /google_calendar_minimum/); assert.match(linkName, /^aketa-2026-10-01-2026-10-07-evidence\.csv$/); assert.equal(requests.length, 2);
  } finally { URL.createObjectURL = create; URL.revokeObjectURL = revoke; global.setTimeout = timeout; Element.prototype.click = oldClick; }
});

test("failed refresh preserves saved data and shows an explicit error", async () => {
  const { root } = await mounted();
  global.fetch = async () => { throw new Error("Connection refused"); };
  await rates.refresh();
  assert.match(root.textContent, /Could not refresh saved evidence/); assert.match(root.textContent, /previous saved view remains visible/); assert.match(root.textContent, /5169.25/);
  global.fetch = async () => ({ ok: true, json: async () => ({ schema_version: 1, datasets: [null] }) });
  await rates.refresh(); assert.match(root.textContent, /unsupported format/);
  global.fetch = async () => ({ ok: false, status: 404 });
  await rates.refresh(); assert.match(root.textContent, /Restart CompSet Studio to load the new rate-workspace API/);
});

const settle = () => new Promise(resolve => setImmediate(resolve));
const ok = payload => ({ ok: true, status: 200, json: async () => payload });
const failed = (status, error) => ({ ok: false, status, json: async () => ({ error }) });
function job(overrides = {}) {
  return { job_id: "job-aketa-1", dataset_id: "aketa", mode: "fresh", state: "running", busy: true, pause_supported: true,
    phase: "prices", message: "Checking the configured sources", started_at: "2026-09-28T08:00:00Z", updated_at: "2026-09-28T08:00:00Z",
    context: { start_date: "2026-09-28", days: 30, adults: 1, children: 0, rooms: 1, stay_nights: 1, currency: "INR" },
    progress: { checked_dates: 1, request_budget: 20 }, ...overrides };
}
function fakeClock() {
  const originalSet = global.setTimeout, originalClear = global.clearTimeout;
  let next = 1;
  const timers = new Map();
  global.setTimeout = (callback, delay) => { const id = next++; timers.set(id, { callback, delay }); return id; };
  global.clearTimeout = id => timers.delete(id);
  return {
    timers,
    async tick() { const entry = timers.entries().next().value; assert.ok(entry, "Expected an active job poll"); const [id, timer] = entry; timers.delete(id); assert.equal(timer.delay, 3000); await timer.callback(); await settle(); },
    restore() { global.setTimeout = originalSet; global.clearTimeout = originalClear; },
  };
}

test("collection-only dock mounts with one status GET and reloads via its owner", async () => {
  const doc = new Document(), root = doc.createElement("div"); doc.body.appendChild(root);
  const requests = []; let reloads = 0;
  global.fetch = async (url, options) => { requests.push({ url, options }); return ok({ state: "idle", busy: false }); };
  const dock = rates.mountCollection(root, { datasetId: "airbnb-compset", onReload: async () => { reloads++; } });
  await dock.ready;
  assert.deepEqual(requests.map(item => item.url), ["/api/workspace/job"]);
  assert.match(root.textContent, /saved Dubai Airbnb comparison set/i);
  assert.match(root.textContent, /direct-site portfolio.*outside this collection/);
  assert.equal(reloads, 0);
  dock.setDataset("aketa");
  assert.equal(requests.length, 1);
  await dock.refresh();
  assert.equal(reloads, 1);
  assert.ok(requests.every(item => item.url === "/api/workspace/job" && item.options.method === "GET"));
  assert.throws(() => dock.setDataset("bnbme_direct:1"), /Unsupported/);
  dock.setDataset(null);
  assert.match(root.textContent, /collection not configured/);
  assert.equal(find(root, node => node.tagName === "BUTTON" && node.textContent === "Fetch fresh data").disabled, true);
  dock.destroy();
});

test("collection-only view switch preserves active job and resume identity", async () => {
  const clock = fakeClock();
  let dock;
  try {
    const doc = new Document(), root = doc.createElement("div"); doc.body.appendChild(root);
    const requests = []; let status = job(); let reloads = 0;
    global.fetch = async (url, options) => {
      requests.push({ url, options });
      if (url === "/api/workspace/collect") status = job({ job_id: "resumed-aketa", mode: "resume" });
      return ok(status);
    };
    dock = rates.mountCollection(root, { datasetId: "aketa", onReload: () => { reloads++; } });
    await dock.ready; dock.setDataset("airbnb-compset");
    assert.match(root.textContent, /Hotel Aketa/);
    assert.equal(find(root, node => node.tagName === "BUTTON" && node.textContent === "Fetch fresh data").disabled, true);
    status = job({ state: "partial", busy: false, updated_at: "2026-09-28T08:03:00Z" });
    await clock.tick(); assert.equal(reloads, 1);
    clickText(root, "Resume collection"); await settle();
    const posts = requests.filter(item => item.options.method === "POST");
    assert.equal(posts.length, 1);
    assert.deepEqual(JSON.parse(posts[0].options.body), { dataset_id: "aketa", mode: "resume" });
    assert.ok(requests.every(item => item.url !== "/api/workspace"));
  } finally { if (dock) dock.destroy(); clock.restore(); }
});

test("Fetch fresh data posts once with dashboard guard and full dataset rather than view filters", async () => {
  const clock = fakeClock();
  try {
    let status = { state: "idle", job_id: null, busy: false };
    const { root, requests } = await mounted(fixture(), async (url, options) => {
      if (url === "/api/workspace") return ok(fixture());
      if (url === "/api/workspace/job") return ok(status);
      if (url === "/api/workspace/collect") { status = job(); return ok(status); }
      throw new Error(`Unexpected request ${url}`);
    });
    selectValue(root, "agoda"); selectValue(root, "unknown");
    clickText(root, "Fetch fresh data"); await settle();
    const starts = requests.filter(item => item.options.method === "POST");
    assert.equal(starts.length, 1);
    assert.equal(starts[0].url, "/api/workspace/collect");
    assert.deepEqual(JSON.parse(starts[0].options.body), { dataset_id: "aketa", mode: "fresh" });
    assert.equal(starts[0].options.headers["X-CompSet-Request"], "dashboard-v1");
    assert.equal(starts[0].options.headers["Content-Type"], "application/json");
    const fetch = find(root, node => node.tagName === "BUTTON" && node.textContent === "Fetch fresh data");
    assert.equal(fetch.disabled, true); fetch.click(); await settle();
    assert.equal(requests.filter(item => item.options.method === "POST").length, 1);
    assert.match(root.textContent, /30 arrival dates from 28 Sept? 2026/);
    assert.match(root.textContent, /one room, no children|1 room/);
    assert.equal(clock.timers.size, 1);
  } finally { clock.restore(); }
});

test("poll stays with its job through dataset changes and does not dismiss an open evidence drawer", async () => {
  const clock = fakeClock();
  try {
    let status = job();
    const callbacks = [];
    global.CompSetCollectionStatus = update => callbacks.push(update);
    const { root, requests } = await mounted(fixture(), async url => ok(url === "/api/workspace" ? fixture() : status));
    selectValue(root, "airbnb-compset");
    find(root, node => node.className.includes("rw-rate-cell") && node.textContent.includes("610.36")).click();
    status = job({ updated_at: "2026-09-28T08:01:00Z", message: "Aketa source check 2", progress: { checked_dates: 2 } });
    await clock.tick();
    assert.match(root.textContent, /Aketa source check 2/); assert.match(root.textContent, /AED 650.40/);
    assert.ok(descendants(root).some(node => node.getAttribute("aria-modal") === "true"));
    assert.equal(callbacks.at(-1).dataset_id, "aketa");
    assert.equal(requests.filter(item => item.options.method === "POST").length, 0);
    assert.ok(requests.every(item => ["/api/workspace", "/api/workspace/job"].includes(item.url)));
  } finally { delete global.CompSetCollectionStatus; clock.restore(); }
});

test("pause uses exact active job ID, then resume targets that paused dataset despite view switch", async () => {
  const clock = fakeClock();
  try {
    let status = job();
    const { root, requests } = await mounted(fixture(), async (url, options) => {
      if (url === "/api/workspace") return ok(fixture());
      if (url === "/api/workspace/job") return ok(status);
      if (url === "/api/workspace/pause") { status = job({ pause_requested: true, message: "Pause requested" }); return ok(status); }
      if (url === "/api/workspace/collect") { status = job({ job_id: "job-aketa-resumed", mode: "resume" }); return ok(status); }
      throw new Error(`Unexpected request ${url}`);
    });
    selectValue(root, "airbnb-compset"); clickText(root, "Pause collection"); await settle();
    assert.deepEqual(JSON.parse(requests.find(item => item.url === "/api/workspace/pause").options.body), { job_id: "job-aketa-1" });
    assert.ok(find(root, node => node.tagName === "BUTTON" && node.textContent === "Pause requested…").disabled);
    status = job({ state: "paused", busy: false, pause_requested: true, updated_at: "2026-09-28T08:02:00Z" });
    await clock.tick();
    assert.match(root.textContent, /Resumes Hotel Aketa · Dehradun/); assert.match(root.textContent, /Saved request: 1 adult · 1 night · AED/);
    assert.equal(clock.timers.size, 0);
    clickText(root, "Resume collection"); await settle();
    const post = requests.filter(item => item.url === "/api/workspace/collect");
    assert.equal(post.length, 1); assert.deepEqual(JSON.parse(post[0].options.body), { dataset_id: "aketa", mode: "resume" });
    assert.match(root.textContent, /job-aketa-resumed/);
  } finally { clock.restore(); }
});

test("terminal job reloads saved evidence once, preserves view filters and never restarts sources", async () => {
  const clock = fakeClock();
  try {
    let status = job();
    const { root, requests } = await mounted(fixture(), async url => ok(url === "/api/workspace" ? fixture() : status));
    selectValue(root, "agoda"); selectValue(root, "unknown"); clickText(root, "List");
    status = job({ state: "partial", busy: false, updated_at: "2026-09-28T08:03:00Z", message: "Budget finished; some dates remain unknown", progress: { unknown_cells: 118 } });
    await clock.tick();
    assert.equal(requests.filter(item => item.url === "/api/workspace").length, 2);
    assert.equal(requests.filter(item => item.options.method === "POST").length, 0);
    assert.equal(find(root, node => node.tagName === "SELECT" && node.children.some(option => option.value === "agoda")).value, "agoda");
    assert.equal(find(root, node => node.tagName === "SELECT" && node.children.some(option => option.value === "unknown")).value, "unknown");
    assert.ok(descendants(root).some(node => node.tagName === "BUTTON" && node.textContent === "Inspect →"));
    assert.match(root.textContent, /Budget finished; some dates remain unknown/);
    assert.match(root.textContent, /Resume collection/);
    assert.equal(clock.timers.size, 0);
  } finally { clock.restore(); }
});

test("mount observing a legacy collector disables Fetch and does not expose stale workspace pause/progress", async () => {
  const clock = fakeClock();
  try {
    const legacy = { state: "running", busy: true, job_id: null, dataset_id: null, phase: "legacy collection", legacy: true, pause_supported: false, message: "Property inventory is collecting", progress: {} };
    const { root, requests } = await mounted(fixture(), async url => ok(url === "/api/workspace" ? fixture() : legacy));
    assert.ok(find(root, node => node.tagName === "BUTTON" && node.textContent === "Fetch fresh data").disabled);
    assert.match(root.textContent, /Property inventory is collecting/);
    assert.ok(!descendants(root).some(node => node.tagName === "BUTTON" && node.textContent === "Pause collection"));
    assert.equal(requests.filter(item => item.options.method === "POST").length, 0);
  } finally { clock.restore(); }
});

test("Fetch preflight notices a newly active collector and sends no POST", async () => {
  const clock = fakeClock();
  try {
    let status = { state: "idle", job_id: null };
    const { root, requests } = await mounted(fixture(), async url => ok(url === "/api/workspace" ? fixture() : status));
    status = job({ job_id: "other-browser-job", dataset_id: "airbnb-compset" });
    clickText(root, "Fetch fresh data"); await settle();
    assert.equal(requests.filter(item => item.options.method === "POST").length, 0);
    assert.match(root.textContent, /A collection is already running/);
    assert.match(root.textContent, /other-browser-job/);
  } finally { clock.restore(); }
});

test("an older in-flight status read cannot overwrite the newly started job", async () => {
  const clock = fakeClock();
  try {
    let statusCalls = 0, resolveOld;
    const idle = { state: "idle", job_id: null };
    const { root, requests } = await mounted(fixture(), async (url, options) => {
      if (url === "/api/workspace") return ok(fixture());
      if (options.method === "POST") return ok(job({ job_id: "new-job" }));
      statusCalls += 1;
      if (statusCalls === 2) return new Promise(resolve => { resolveOld = resolve; });
      return ok(idle);
    });
    const oldRead = rates.refresh(); await settle();
    clickText(root, "Fetch fresh data"); await settle();
    assert.match(root.textContent, /new-job/);
    resolveOld(ok(idle)); await oldRead;
    assert.match(root.textContent, /new-job/);
    assert.ok(find(root, node => node.tagName === "BUTTON" && node.textContent === "Fetch fresh data").disabled);
    assert.equal(requests.filter(item => item.options.method === "POST").length, 1);
  } finally { clock.restore(); }
});

test("a foreign terminal job cannot end the active job or reload its data", async () => {
  const clock = fakeClock();
  try {
    let status = job();
    const { root, requests } = await mounted(fixture(), async url => ok(url === "/api/workspace" ? fixture() : status));
    status = job({ job_id: "old-foreign-job", state: "complete", busy: false, message: "Old completion" });
    await clock.tick();
    assert.match(root.textContent, /different job/); assert.doesNotMatch(root.textContent, /Old completion/);
    assert.match(root.textContent, /job-aketa-1/);
    assert.equal(requests.filter(item => item.url === "/api/workspace").length, 1);
    assert.ok(find(root, node => node.tagName === "BUTTON" && node.textContent === "Fetch fresh data").disabled);
    assert.equal(clock.timers.size, 0);
  } finally { clock.restore(); }
});

test("a same-job terminal snapshot older than running progress is ignored", async () => {
  const clock = fakeClock();
  try {
    let status = job({ updated_at: "2026-09-28T08:10:00Z", message: "Latest running progress" });
    const { root, requests } = await mounted(fixture(), async url => ok(url === "/api/workspace" ? fixture() : status));
    status = job({ state: "complete", busy: false, updated_at: "2026-09-28T08:05:00Z", message: "Stale finished state" });
    await clock.tick();
    assert.match(root.textContent, /Latest running progress/); assert.doesNotMatch(root.textContent, /Stale finished state/);
    assert.equal(requests.filter(item => item.url === "/api/workspace").length, 1);
    assert.equal(clock.timers.size, 1);
  } finally { clock.restore(); }
});

test("status/service/start failures are visible, keep rates and never automatically retry a POST", async () => {
  const clock = fakeClock();
  try {
    let statusResponse = ok({ state: "idle", job_id: null });
    const { root, requests } = await mounted(fixture(), async (url, options) => url === "/api/workspace" ? ok(fixture()) : options.method === "POST" ? failed(400, "Unsupported request context") : statusResponse);
    clickText(root, "Fetch fresh data"); await settle();
    assert.match(root.textContent, /Unsupported request context/); assert.match(root.textContent, /start was not retried/);
    assert.match(root.textContent, /5169.25/);
    assert.equal(requests.filter(item => item.options.method === "POST").length, 1);
    statusResponse = failed(404, "missing"); clickText(root, "Check collection status"); await settle();
    assert.match(root.textContent, /Restart CompSet Studio to load the updated collection service/);
    assert.equal(clock.timers.size, 0);
    assert.equal(requests.filter(item => item.options.method === "POST").length, 1);
  } finally { clock.restore(); }
});

test("stopped results never schedule a retry and Reload saved data only performs GETs", async () => {
  const { root, requests } = await mounted(fixture(), async url => ok(url === "/api/workspace" ? fixture() : job({ state: "stopped", busy: false, message: "Source access stopped" })));
  assert.ok(!descendants(root).some(node => node.tagName === "BUTTON" && node.textContent === "Resume collection"));
  clickText(root, "↻  Reload saved data"); await settle();
  assert.equal(requests.length, 4); assert.ok(requests.every(item => item.options.method === "GET"));
  assert.match(root.textContent, /Source access stopped/);
});

test("coverage note derives catalog, unlinked records and saved compset counts from evidence", async () => {
  const payload = fixture();
  payload.portfolio.summary = { property_count: 113, airbnb_listing_count: 60, airbnb_linked_count: 0, active_inventory_complete: false };
  payload.datasets[1].candidates = Array.from({ length: 67 }, (_, i) => ({ id: String(i), selected: true }));
  const { root } = await mounted(payload);
  assert.match(root.textContent, /113 returned public BnBMe properties · 60 Airbnb records without a verified portfolio link/);
  assert.match(root.textContent, /1 saved Dubai subject · 67 selected Airbnb competitors/);
  assert.match(root.textContent, /Aketa: 2 observation sources · 2 property profiles · no hotel competitor set collected/);
  assert.match(root.textContent, /do not establish complete corporate inventory/);
});

// Optional fixture is a projection already produced by Python, never fetched here.
if (process.env.COMPSET_WORKSPACE_FIXTURE) test("actual saved projection renders every section and exports all visible cells", async () => {
  const payload = JSON.parse(fs.readFileSync(process.env.COMPSET_WORKSPACE_FIXTURE, "utf8"));
  const { root } = await mounted(payload);
  for (const dataset of payload.datasets) {
    selectValue(root, dataset.id);
    for (const section of ["Rate calendar", "Competitor set", "Sources & profiles", "Portfolio overview"]) { clickText(root, section); assert.ok(root.textContent.length > 200); }
    clickText(root, "Rate calendar");
    const first = descendants(root).find(node => node.className.includes("rw-rate-cell")); if (first) { first.click(); clickText(root, "Close ×"); }
    assert.equal(model.exportCsv(dataset).split("\r\n").length, model.visibleModel(dataset).cells.length + 1);
  }
});
