"use strict";
// Integrated local DOM/Leaflet interaction proof. No browser, server or collector is started.
const test = require("node:test"), assert = require("node:assert/strict");
const dual = require("../compset/static/dual-workspace.js");

class Element {
  constructor(tag, doc) {
    doc.created = (doc.created || 0) + 1;
    this.tagName = tag.toUpperCase(); this.ownerDocument = doc; this.parentNode = null; this.children = []; this.listeners = {}; this.attrs = {}; this.className = ""; this._text = ""; this.hidden = false; this.disabled = false;
    this.style = { touchAction: "pan-x pan-y", cursor: "grab" }; this.classList = { add: (...names) => { this.className += ` ${names.join(" ")}`; } };
  }
  set textContent(value) { this._text = String(value); this.children.forEach(child => { child.parentNode = null; }); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
  set innerHTML(_) { throw new Error("Unsafe DOM HTML assignment"); }
  appendChild(child) { child.remove(); child.parentNode = this; this.children.push(child); return child; }
  replaceChildren(...children) { this.textContent = ""; children.forEach(child => this.appendChild(child)); }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(child => child !== this); this.parentNode = null; }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  getAttribute(name) { return this.attrs[name]; }
  removeAttribute(name) { delete this.attrs[name]; }
  addEventListener(name, fn, options) { (this.listeners[name] ||= []).push({ fn, capture: options === true || Boolean(options && options.capture) }); }
  removeEventListener(name, fn) { this.listeners[name] = (this.listeners[name] || []).filter(listener => listener.fn !== fn); }
  dispatch(name, properties = {}) {
    const event = { target: this, currentTarget: null, defaultPrevented: false, stopped: false, preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this.stopped = true; }, ...properties };
    const path = []; for (let node = this; node; node = node.parentNode) path.push(node); path.push(this.ownerDocument);
    for (const node of [...path].reverse()) { event.currentTarget = node; for (const listener of node.listeners[name] || []) if (listener.capture) listener.fn(event); if (event.stopped) return event; }
    for (const node of path) { event.currentTarget = node; for (const listener of node.listeners[name] || []) if (!listener.capture) listener.fn(event); if (event.stopped) break; }
    return event;
  }
  click() { if (!this.disabled) this.dispatch("click"); }
  focus() { this.ownerDocument.activeElement = this; }
  get isConnected() { return this === this.ownerDocument.body || Boolean(this.parentNode && this.parentNode.isConnected); }
  querySelectorAll() { return descendants(this).filter(node => ["BUTTON", "INPUT", "SELECT", "A"].includes(node.tagName)); }
  setPointerCapture(id) { if (this.failCapture) throw new Error("Capture failed"); this.ownerDocument.captures.set(id, this); this.captureCalls = (this.captureCalls || 0) + 1; }
  hasPointerCapture(id) { return this.ownerDocument.captures.get(id) === this; }
  releasePointerCapture(id) { if (this.hasPointerCapture(id)) { this.ownerDocument.captures.delete(id); this.dispatch("lostpointercapture", { pointerId: id }); } }
}
class Document {
  constructor() { this.listeners = {}; this.captures = new Map(); this.body = new Element("body", this); this.activeElement = this.body; this.hidden = false; }
  createElement(tag) { return new Element(tag, this); }
  createElementNS(_, tag) { return this.createElement(tag); }
  addEventListener(name, fn, options) { (this.listeners[name] ||= []).push({ fn, capture: options === true || Boolean(options && options.capture) }); }
  removeEventListener(name, fn) { this.listeners[name] = (this.listeners[name] || []).filter(listener => listener.fn !== fn); }
  dispatch(name, properties = {}) { const event = { preventDefault() {}, stopPropagation() {}, ...properties }; (this.listeners[name] || []).slice().forEach(listener => listener.fn(event)); }
  pointer(name, target, properties = {}) { return (this.captures.get(properties.pointerId) || target).dispatch(name, { pointerType: "mouse", button: 0, isPrimary: true, ...properties }); }
}
const descendants = root => root.children.flatMap(child => [child, ...descendants(child)]);
function find(root, predicate) { const node = descendants(root).find(predicate); assert.ok(node, "Expected rendered control"); return node; }
const control = (root, label) => find(root, node => node.getAttribute("aria-label") === label);
const click = (root, label) => find(root, node => node.tagName === "BUTTON" && node.textContent.endsWith(label)).click();
const settle = async () => { for (let i = 0; i < 12; i++) await new Promise(resolve => setImmediate(resolve)); };
const interactions = ["dragging", "touchZoom", "doubleClickZoom", "scrollWheelZoom", "boxZoom", "keyboard", "tap"];
const interactionState = map => Object.fromEntries(interactions.map(name => [name, map[name].enabled()]));
function leaflet() {
  const stats = { maps: [], circles: [], polygons: [], markers: [], tiles: 0, groups: [], removed: 0 };
  const layer = kind => ({ kind, handlers: {}, layers: new Set(), on(name, fn) { this.handlers[name] = fn; return this; }, addTo(target) { target.layers.add(this); this.target = target; return this; }, setLatLng(point) { this.point = point; return this; }, setLatLngs(points) { this.points = points; return this; }, setStyle(style) { this.style = style; return this; }, setOpacity(opacity) { this.opacity = opacity; return this; }, getLatLng() { return { lat: this.point[0], lng: this.point[1] }; }, setRadius(radius) { this.radius = radius; return this; }, bindPopup(fn) { this.popup = fn; return this; }, removeLayer(child) { this.layers.delete(child); if (child.element) child.element.remove(); }, remove() { if (this.target) this.target.removeLayer(this); } });
  return { stats, api: {
    map(node) {
      const map = layer("map"); map.node = node; node.className += " leaflet-container leaflet-touch leaflet-grab";
      for (const name of interactions) { let enabled = !["scrollWheelZoom", "boxZoom"].includes(name); map[name] = { enabled: () => enabled, enable() { enabled = true; }, disable() { enabled = false; } }; }
      map.setView = (point, zoom) => { map.center = point; map.zoom = zoom; map.setViews = (map.setViews || 0) + 1; return map; };
      map.mouseEventToLatLng = event => Object.hasOwn(event, "latlng") ? event.latlng : ({ lat: 25 - event.clientY / 1000, lng: 55 + event.clientX / 1000 });
      map.invalidateSize = () => { map.invalidations = (map.invalidations || 0) + 1; };
      map.remove = () => { stats.removed++; }; stats.maps.push(map); return map;
    },
    tileLayer() { stats.tiles++; return layer("tiles"); },
    circle(point, options) { const circle = layer("circle").setLatLng(point).setRadius(options.radius); stats.circles.push(circle); return circle; },
    polygon(points) { const polygon = layer("polygon").setLatLngs(points); stats.polygons.push(polygon); return polygon; },
    divIcon(options) { return options; },
    marker(point, options) {
      const marker = layer("marker").setLatLng(point); marker.options = options;
      const add = marker.addTo; marker.addTo = map => { add.call(marker, map); marker.element = map.node.ownerDocument.createElement("div"); marker.element.className = options.icon.className; marker.element.setAttribute("tabindex", "0"); map.node.appendChild(marker.element); return marker; };
      marker.getElement = () => marker.element; stats.markers.push(marker); return marker;
    },
    circleMarker(point) { return layer("candidate").setLatLng(point); },
    layerGroup() { const group = layer("group"); stats.groups.push(group); return group; }
  } };
}
function fixtures() {
  const subject = { id: "bnbme_direct:1", subject_id: "bnbme_direct:1", title: "Observed subject", namespace: "bnbme_direct", city: "Dubai", currency: "AED", latitude: 25, longitude: 55 };
  const candidates = [
    { id: "airbnb:1", title: "Saved selected", latitude: 25, longitude: 55, selected: true, eligibility: "eligible" },
    { id: "airbnb:2", title: "Saved provisional", latitude: 25, longitude: 55.005, selected: false, eligibility: "provisional" },
    { id: "airbnb:3", title: "Missing decision", latitude: 25, longitude: 55.012 },
    { id: "airbnb:4", title: "Outside initial area", latitude: 25, longitude: 55.06, selected: false, eligibility: "rejected" },
    { id: "airbnb:5", title: "No coordinates", latitude: null, longitude: null, selected: false, eligibility: "provisional" }
  ];
  const dates = Array.from({ length: 14 }, (_, index) => dual.model.addDays("2026-10-01", index));
  return { subject, candidates, dates, radius: 2 };
}
function response(f, url) {
  const parsed = new URL(url, "http://fixture"), query = parsed.searchParams;
  if (url === "/api/workspace/job") return { state: "idle", busy: false, job_id: null };
  if (url === "/api/intelligence") return { revision: "saved-1", str: { properties: [f.subject], subjects: [f.subject], default_start: f.dates[0], summary: {} }, hotel: {} };
  if (parsed.pathname.endsWith("/str/calendar")) return { revision: "saved-1", request: { start: query.get("start"), days: 14, offset: 0, limit: 25, namespace: "bnbme_direct", city: null, currency: null, bedrooms: null, query: "" }, dates: f.dates, entities: [f.subject], cells: [], total: 1 };
  if (parsed.pathname.endsWith("/str/compset")) {
    const id = query.get("candidate_id"), decision = query.get("decision");
    const candidates = f.candidates.filter(row => !id || row.id === id).filter(row => !decision || (decision === "selected" ? row.selected : row.eligibility === decision));
    return { revision: "saved-1", subject: f.subject, request: { subject_id: f.subject.id, offset: Number(query.get("offset")), limit: Number(query.get("limit")), decision, candidate_id: id }, candidates: candidates.map(row => ({ ...row, missing_fields: ["floor_area_sqm"], observed_at: "2026-09-27T08:00:00Z" })), map_points: f.candidates, candidate_total: candidates.length, criteria: { radius_km: f.radius } };
  }
  if (url === "/api/intelligence/hotel") return { revision: "saved-1", dataset: { dates: [], entities: [], cells: [] }, compset: { subject: { id: "hotel:aketa", latitude: 30.3, longitude: 78.04 }, candidates: [] } };
  throw new Error(`Unexpected local fixture request: ${url}`);
}
async function mounted(t, change) {
  dual.destroy(); const previous = { fetch: global.fetch, L: global.L, matchMedia: global.matchMedia }, f = fixtures(), doc = new Document(), root = doc.createElement("div"), requests = [], fake = leaflet(), medias = new Map();
  if (change) change(f); doc.body.appendChild(root); global.L = fake.api;
  global.matchMedia = query => { if (!medias.has(query)) medias.set(query, { matches: false, listeners: new Set(), addEventListener(_, fn) { this.listeners.add(fn); }, removeEventListener(_, fn) { this.listeners.delete(fn); } }); return medias.get(query); };
  global.fetch = async (url, options) => { requests.push({ url, options }); return { ok: true, json: async () => response(f, url) }; };
  t.after(() => { dual.destroy(); global.fetch = previous.fetch; global.L = previous.L; global.matchMedia = previous.matchMedia; });
  await dual.mount(root); click(root, "Map"); await settle();
  return { root, doc, f, requests, fake, map: fake.stats.maps[0], circle: fake.stats.circles[0], resize(width) { for (const [query, media] of medias) { const matches = width <= Number(query.match(/\d+/)[0]); if (media.matches !== matches) { media.matches = matches; media.listeners.forEach(fn => fn()); } } } };
}
function pointer(fixture, name, x, y, extras = {}) { return fixture.doc.pointer(name, fixture.map.node, { pointerId: 1, clientX: x, clientY: y, ...extras }); }
function draw(fixture, endX = 10, endY = 0, extras = {}) { click(fixture.root, "Draw area"); pointer(fixture, "pointerdown", 0, 0, extras); pointer(fixture, "pointermove", endX, endY, extras); pointer(fixture, "pointerup", endX, endY, extras); }
function assertOriginal(fixture, saved = { center: [25, 55], radius: 2000 }, settings) {
  assert.deepEqual(fixture.circle.point, saved.center); assert.equal(fixture.circle.radius, saved.radius); assert.equal(fixture.doc.captures.size, 0);
  if (settings) assert.deepEqual(interactionState(fixture.map), settings);
  assert.equal(fixture.map.node.style.touchAction, "pan-x pan-y"); assert.equal(fixture.map.node.style.cursor, "grab"); assert.match(fixture.map.node.className, /leaflet-container leaflet-touch leaflet-grab/);
}

for (const pointerType of ["mouse", "touch", "pen"]) test(`explicit ${pointerType} drawing captures, previews geographic radius, commits and preserves map context`, async t => {
  const f = await mounted(t), before = f.requests.length, settings = interactionState(f.map), saved = JSON.stringify(f.f); f.map.zoom = 17;
  click(f.root, "Draw area"); assert.ok(Object.values(interactionState(f.map)).every(value => !value)); assert.equal(f.map.node.style.touchAction, "none");
  pointer(f, "pointerdown", 0, 0, { pointerType }); assert.equal(f.map.node.hasPointerCapture(1), true);
  // Captured move/up stay on the canvas even when the pointer leaves its original element.
  f.doc.pointer("pointermove", f.doc.body, { pointerId: 1, pointerType, clientX: 10, clientY: 0 });
  assert.match(f.root.textContent, /2 observed candidates.*preview/); assert.match(f.root.textContent, /Preview · radius 1.01 km/);
  f.doc.pointer("pointerup", f.doc.body, { pointerId: 1, pointerType, clientX: 10, clientY: 0 });
  const expected = dual.model.distanceKm({ latitude: 25, longitude: 55 }, { latitude: 25, longitude: 55.01 });
  assert.ok(Math.abs(f.circle.radius - expected * 1000) < .001); assert.match(f.root.textContent, /Area selected/); assert.deepEqual(interactionState(f.map), settings);
  assert.equal(f.doc.captures.size, 0); assert.equal(f.map.zoom, 17); assert.equal(f.map.setViews, 1); assert.equal(f.fake.stats.maps.length, 1); assert.equal(f.fake.stats.tiles, 1); assert.equal(f.fake.stats.circles.length, 1);
  assert.equal(f.requests.length, before); assert.equal(JSON.stringify(f.f), saved); assert.match(f.map.node.className, /leaflet-container/);
});

test("ordinary clicks and unmatched pointer events do not relocate or resize the committed area", async t => {
  const f = await mounted(t), settings = interactionState(f.map), before = f.requests.length;
  pointer(f, "pointerdown", 30, 30); pointer(f, "pointermove", 50, 50); pointer(f, "pointerup", 50, 50); f.map.handlers.click({ latlng: { lat: 0, lng: 0 } }); assertOriginal(f, undefined, settings);
  click(f.root, "Draw area"); pointer(f, "pointerdown", 0, 0); pointer(f, "pointermove", 10, 0, { pointerId: 99 }); pointer(f, "pointerup", 10, 0, { pointerId: 99 });
  assert.equal(f.circle.radius, 2000); assert.equal(f.doc.captures.size, 1); click(f.root, "Cancel"); assertOriginal(f, undefined, settings); assert.equal(f.requests.length, before);
});

test("Escape, Cancel, pointercancel, lost capture and hidden document retain the area and restore exact settings", async t => {
  const f = await mounted(t), settings = interactionState(f.map);
  for (const reason of ["Escape", "Cancel", "pointercancel", "lostpointercapture", "hidden"]) {
    click(f.root, "Draw area"); pointer(f, "pointerdown", 20, 0); pointer(f, "pointermove", 50, 0); assert.notEqual(f.circle.radius, 2000);
    if (reason === "Escape") f.doc.dispatch("keydown", { key: "Escape" }); else if (reason === "Cancel") click(f.root, "Cancel"); else if (reason === "hidden") { f.doc.hidden = true; f.doc.dispatch("visibilitychange"); f.doc.hidden = false; } else pointer(f, reason, 50, 0);
    assertOriginal(f, undefined, settings);
  }
  // Controls which were originally disabled must remain disabled after every cancellation.
  assert.equal(f.map.scrollWheelZoom.enabled(), false); assert.equal(f.map.boxZoom.enabled(), false);
});

test("second touch inside or outside the map cancels safely and cannot commit a replacement gesture", async t => {
  const f = await mounted(t), settings = interactionState(f.map);
  for (const target of [f.map.node, f.doc.body]) {
    click(f.root, "Draw area"); pointer(f, "pointerdown", 0, 0, { pointerType: "touch" }); pointer(f, "pointermove", 20, 0, { pointerType: "touch" });
    f.doc.pointer("pointerdown", target, { pointerId: 2, pointerType: "touch", isPrimary: false, clientX: 5, clientY: 5 });
    pointer(f, "pointerup", 20, 0, { pointerType: "touch" }); assertOriginal(f, undefined, settings);
  }
  click(f.root, "Draw area"); pointer(f, "pointerdown", 0, 0, { isPrimary: false }); assertOriginal(f, undefined, settings);
});

test("taps, tiny gestures, return to center, invalid endpoints and capture failure never commit stale previews", async t => {
  const f = await mounted(t), settings = interactionState(f.map);
  const cases = [
    { move: 0, end: 0 }, { move: 5, end: 5 }, { move: 30, end: 0 },
    { move: 30, end: 30, extras: { latlng: { lat: 25, lng: 55.00001 } } },
    { move: 30, end: 30, extras: { latlng: { lat: NaN, lng: 55 } } },
    { move: 30, end: 30, extras: { latlng: { lat: 91, lng: 55 } } },
    { move: 30, end: 30, extras: { latlng: { lat: 25, lng: 181 } } },
    { move: 30, end: NaN }
  ];
  for (const scenario of cases) { click(f.root, "Draw area"); pointer(f, "pointerdown", 0, 0); pointer(f, "pointermove", scenario.move, 0); pointer(f, "pointerup", scenario.end, 0, scenario.extras); assertOriginal(f, undefined, settings); }
  f.map.node.failCapture = true; draw(f); assertOriginal(f, undefined, settings); assert.match(f.root.textContent, /Pointer capture is unavailable/);
  f.map.node.failCapture = false; click(f.root, "Draw area"); pointer(f, "pointerdown", NaN, 0); assertOriginal(f, undefined, settings);
});

test("center and edge handles support direct touch dragging; explicit resize previews cancel to the committed radius", async t => {
  const f = await mounted(t), settings = interactionState(f.map), before = f.requests.length, center = f.fake.stats.markers[0].element, edge = f.fake.stats.markers[1].element;
  f.doc.pointer("pointerdown", center, { pointerId: 1, pointerType: "touch", clientX: 0, clientY: 0 }); pointer(f, "pointerup", 10, 10, { pointerType: "touch" });
  assert.deepEqual(f.circle.point, [24.99, 55.01]); assert.equal(f.circle.radius, 2000); assert.deepEqual(interactionState(f.map), settings);
  f.doc.pointer("pointerdown", edge, { pointerId: 1, pointerType: "pen", clientX: 0, clientY: 0 }); pointer(f, "pointerup", 20, 10, { pointerType: "pen" });
  const committed = { center: [...f.circle.point], radius: f.circle.radius }; assert.notEqual(committed.radius, 2000);
  click(f.root, "Resize area"); pointer(f, "pointerdown", 0, 0); pointer(f, "pointermove", 30, 0); f.doc.dispatch("keydown", { key: "Escape" }); assertOriginal(f, committed, settings);
  edge.dispatch("keydown", { key: "Enter" }); assert.match(f.root.textContent, /Resize enabled/); click(f.root, "Cancel"); assert.equal(f.requests.length, before);
});

test("labelled numeric and range radius controls reject nonfinite input and bound radius without map or request churn", async t => {
  const f = await mounted(t), number = control(f.root, "Area radius in kilometres"), range = control(f.root, "Map view radius in kilometres"), before = f.requests.length; f.map.zoom = 16;
  assert.equal(number.type, "number"); assert.equal(range.type, "range"); assert.equal(number.min, "0.1"); assert.equal(number.max, "50");
  for (const [value, metres] of [["100", 50000], ["Infinity", 50000], ["NaN", 50000], ["", 50000], ["-9", 100], ["0", 100], ["3.5", 3500]]) { number.value = value; number.dispatch("change"); assert.equal(f.circle.radius, metres); }
  range.value = "4"; range.dispatch("change"); assert.equal(f.circle.radius, 4000); assert.equal(number.value, "4");
  draw(f, 1000); assert.equal(f.circle.radius, 50000); assert.ok(f.circle.point.every(Number.isFinite)); assert.equal(f.map.zoom, 16); assert.equal(f.fake.stats.maps.length, 1); assert.equal(f.fake.stats.tiles, 1); assert.equal(f.requests.length, before);
});

test("selected-area summary uses observed candidates, recorded decisions and geometry without invented prices", async t => {
  const f = await mounted(t), summary = control(f.root, "Selected area observed evidence");
  assert.match(summary.textContent, /Observed candidates3Saved selected1Saved provisional1Decision evidence missing1/); assert.match(summary.textContent, /Radius2.00 kmCircle area12.57 km²/); assert.match(summary.textContent, /Available candidates without coordinates1/);
  draw(f); assert.match(summary.textContent, /Observed candidates2Saved selected1Saved provisional1/); assert.doesNotMatch(summary.textContent, /AED|INR|revenue|occupancy|market total/i);
});

test("responsive changes keep captured gesture, map instance, Leaflet classes and zoom intact", async t => {
  const f = await mounted(t), before = f.requests.length; f.map.zoom = 18; click(f.root, "Draw area"); pointer(f, "pointerdown", 0, 0); pointer(f, "pointermove", 10, 0);
  f.resize(390); assert.equal(f.doc.captures.size, 1); assert.match(f.map.node.className, /leaflet-container/); assert.match(f.map.node.className, /is-drawing/); pointer(f, "pointerup", 10, 0);
  f.resize(1280); assert.equal(f.fake.stats.maps.length, 1); assert.equal(f.fake.stats.tiles, 1); assert.equal(f.fake.stats.removed, 0); assert.equal(f.map.zoom, 18); assert.ok(f.map.invalidations >= 2); assert.equal(f.requests.length, before);
});

test("animation frames coalesce expensive preview renders and final release/cancellation flush or discard pending work", async t => {
  const f = await mounted(t), frames = new Map(), previousRequest = global.requestAnimationFrame, previousCancel = global.cancelAnimationFrame; let sequence = 0;
  global.requestAnimationFrame = fn => { frames.set(++sequence, fn); return sequence; }; global.cancelAnimationFrame = id => { frames.delete(id); };
  t.after(() => { global.requestAnimationFrame = previousRequest; global.cancelAnimationFrame = previousCancel; });
  click(f.root, "Draw area"); pointer(f, "pointerdown", 0, 0); const created = f.doc.created;
  for (const x of [10, 11, 12, 13, 14]) pointer(f, "pointermove", x, 0);
  assert.equal(frames.size, 1); assert.equal(f.doc.created, created, "Pointer frequency must not rebuild summaries/lists before the animation frame"); assert.equal(f.circle.radius, 2000);
  const [id, callback] = [...frames][0]; frames.delete(id); callback(); assert.match(f.root.textContent, /preview/); assert.ok(f.doc.created > created);
  pointer(f, "pointermove", 15, 0); const pending = [...frames.values()][0]; pointer(f, "pointerup", 16, 0);
  assert.equal(frames.size, 0); const committed = { center: [...f.circle.point], radius: f.circle.radius }; assert.ok(Math.abs(committed.radius - dual.model.distanceKm(f.f.subject, { latitude: 25, longitude: 55.016 }) * 1000) < .001);
  pending(); assert.deepEqual(f.circle.point, committed.center); assert.equal(f.circle.radius, committed.radius);
  click(f.root, "Draw area"); pointer(f, "pointerdown", 0, 0); pointer(f, "pointermove", 30, 0); const cancelled = [...frames.values()][0]; f.doc.dispatch("keydown", { key: "Escape" });
  assert.equal(frames.size, 0); cancelled(); assertOriginal(f, committed);
});

test("navigation and destroy release capture/listeners and stale pointer callbacks cannot edit a later map", async t => {
  const f = await mounted(t), settings = interactionState(f.map), oldNode = f.map.node;
  click(f.root, "Draw area"); pointer(f, "pointerdown", 0, 0); pointer(f, "pointermove", 20, 0); const staleUp = oldNode.listeners.pointerup[0].fn;
  click(f.root, "Hotels"); await settle(); assertOriginal(f, undefined, settings); assert.equal(f.fake.stats.removed, 1); assert.equal(oldNode.listeners.pointerup.length, 0); assert.equal(f.doc.listeners.pointerdown.length, 0);
  click(f.root, "Map"); await settle(); const nextCircle = f.fake.stats.circles.at(-1), nextMap = f.fake.stats.maps.at(-1); staleUp({ pointerId: 1, clientX: 20, clientY: 0, preventDefault() {}, stopPropagation() {} }); assert.deepEqual(nextCircle.point, [30.3, 78.04]);
  click(f.root, "Draw area"); f.doc.pointer("pointerdown", nextMap.node, { pointerId: 2, clientX: 0, clientY: 0 }); assert.equal(f.doc.captures.size, 1); const nextSettings = { ...settings }; dual.destroy();
  assert.equal(f.doc.captures.size, 0); assert.deepEqual(interactionState(nextMap), nextSettings); assert.equal(f.doc.listeners.pointerdown.length, 0); assert.equal(nextMap.node.listeners.pointerup.length, 0);
});

test("selected-area CSV and saved candidate inspection preserve subject, decisions and explicit collection scope", async t => {
  const f = await mounted(t), beforeData = JSON.stringify(f.f), previousCreate = URL.createObjectURL, previousRevoke = URL.revokeObjectURL; let blob;
  URL.createObjectURL = value => { blob = value; return "blob:local-fixture"; }; URL.revokeObjectURL = () => {}; t.after(() => { URL.createObjectURL = previousCreate; URL.revokeObjectURL = previousRevoke; });
  draw(f); const selected = { center: [...f.circle.point], radius: f.circle.radius }, requests = f.requests.length;
  click(f.root, "Export map view ↓"); const csv = await blob.text(); assert.equal(csv.split("\r\n").length, 3); assert.match(csv, /"bnbme_direct:1","airbnb:1"/); assert.match(csv, /"bnbme_direct:1","airbnb:2"/); assert.doesNotMatch(csv, /airbnb:3|airbnb:4|airbnb:5/);
  assert.equal(f.requests.length, requests); find(f.root, node => node.className === "dw-map-candidate").click(); await settle(); assert.equal(f.requests.length, requests + 1); assert.match(f.requests.at(-1).url, /candidate_id=airbnb%3A1/); assert.match(f.root.textContent, /floor_area_sqm/);
  click(f.root, "Close ×"); click(f.root, "Draw area"); pointer(f, "pointerdown", 20, 0); pointer(f, "pointermove", 50, 0); click(f.root, "Export map view ↓"); assertOriginal(f, selected);
  assert.match(f.root.textContent, /Export contains the committed selected area/); assert.equal((await blob.text()).split("\r\n").length, 3); assert.equal(JSON.stringify(f.f), beforeData); assert.ok(f.requests.every(request => request.options.method === "GET")); assert.match(f.root.textContent, /Saved Dubai Airbnb comparison set/);
});

test("unobserved subject coordinates disable drawing and never guess a map center", async t => {
  const f = await mounted(t, data => { data.subject.latitude = null; data.radius = Infinity; });
  assert.equal(f.fake.stats.maps.length, 0); assert.match(f.root.textContent, /Subject coordinates are not observed/); assert.equal(find(f.root, node => node.textContent === "Draw area").disabled, true);
  const addVertex = find(f.root, node => node.textContent === "Add coordinate vertex"); assert.equal(addVertex.disabled, true);
  control(f.root, "Polygon vertex latitude").value = "25"; control(f.root, "Polygon vertex longitude").value = "55";
  assert.doesNotThrow(() => addVertex.dispatch("click"));
  const number = control(f.root, "Area radius in kilometres"); number.value = "3"; number.dispatch("change"); assert.match(f.root.textContent, /Radius3.00 km/); assert.equal(f.fake.stats.maps.length, 0);
});

test("polygon vertices preview, undo, apply, edit and clear synchronize the table and CSV without data reads", async t => {
  const f = await mounted(t), initialRequests = f.requests.length, beforeData = JSON.stringify(f.f), settings = interactionState(f.map), previousCreate = URL.createObjectURL, previousRevoke = URL.revokeObjectURL; let blob;
  URL.createObjectURL = value => { blob = value; return "blob:polygon-fixture"; }; URL.revokeObjectURL = () => {}; t.after(() => { URL.createObjectURL = previousCreate; URL.revokeObjectURL = previousRevoke; });
  click(f.root, "Draw polygon"); assert.ok(Object.values(interactionState(f.map)).every(value => !value));
  for (const [x, y] of [[-1, -1], [10, -1], [10, 5]]) { pointer(f, "pointerdown", x, y, { pointerType: "touch" }); pointer(f, "pointerup", x, y, { pointerType: "touch" }); }
  pointer(f, "pointermove", -1, 5); assert.equal(f.fake.stats.polygons[0].points.length, 4); assert.match(f.root.textContent, /preview/i);
  click(f.root, "Undo vertex"); assert.equal(f.fake.stats.polygons[0].points.length, 2);
  for (const [x, y] of [[10, 5], [-1, 5]]) { pointer(f, "pointerdown", x, y); pointer(f, "pointerup", x, y); }
  click(f.root, "Apply area"); assert.equal(f.doc.captures.size, 0); assert.deepEqual(interactionState(f.map), settings); assert.match(f.root.textContent, /2 observed candidates inside polygon/); assert.equal(f.circle.style.opacity, 0);
  const table = find(f.root, node => node.className.includes("dw-map-table")); assert.match(table.textContent, /Saved selected/); assert.match(table.textContent, /Saved provisional/); assert.doesNotMatch(table.textContent, /Missing decision/);
  click(f.root, "Export map view ↓"); let csv = await blob.text(); assert.equal(csv.split("\r\n").length, 3); assert.match(csv, /airbnb:1/); assert.match(csv, /airbnb:2/); assert.doesNotMatch(csv, /airbnb:3/);
  const vertex = f.fake.stats.markers.find(marker => marker.options.title === "Drag polygon vertex 2"); assert.ok(vertex);
  f.doc.pointer("pointerdown", vertex.element, { pointerId: 1, pointerType: "touch", clientX: 10, clientY: -1 }); pointer(f, "pointermove", 2, -1, { pointerType: "touch" }); pointer(f, "pointerup", 2, -1, { pointerType: "touch" });
  assert.match(f.root.textContent, /Apply area to keep the edit/); f.doc.dispatch("keydown", { key: "Escape" }); assert.match(f.root.textContent, /2 observed candidates inside polygon/);
  click(f.root, "Clear area"); assert.match(f.root.textContent, /4 observed candidates with coordinates/); click(f.root, "Export map view ↓"); csv = await blob.text(); assert.equal(csv.split("\r\n").length, 5);
  assert.equal(f.requests.length, initialRequests); assert.equal(JSON.stringify(f.f), beforeData); assert.equal(f.fake.stats.maps.length, 1); assert.equal(f.fake.stats.tiles, 1);
});

test("named local sets restore geometry and manual inclusion without changing saved decisions or making data requests", async t => {
  const previous = global.localStorage, stored = new Map(); global.localStorage = { getItem: key => stored.get(key) || null, setItem: (key, value) => stored.set(key, value) }; t.after(() => { global.localStorage = previous; });
  const f = await mounted(t), before = f.requests.length, original = JSON.stringify(f.f);
  const checkbox = find(f.root, node => node.tagName === "INPUT" && node.getAttribute("aria-label") === "Include Saved provisional in local map selection"); checkbox.checked = false; checkbox.dispatch("change");
  assert.match(f.root.textContent, /2 observed candidates inside this/); assert.match(f.root.textContent, /Locally excluded1/);
  const name = control(f.root, "Local selection name"); name.value = "Dubai shortlist"; click(f.root, "Save local set"); assert.match(f.root.textContent, /Saved local set/);
  click(f.root, "Clear area"); click(f.root, "Include all in area"); assert.match(f.root.textContent, /4 observed candidates with coordinates/);
  const picker = control(f.root, "Saved local selection"); picker.value = "Dubai shortlist"; click(f.root, "Load local set");
  assert.match(f.root.textContent, /2 observed candidates inside this/); assert.match(f.root.textContent, /Locally excluded1/);
  assert.equal(f.requests.length, before); assert.equal(JSON.stringify(f.f), original); assert.match(stored.get("compset.map-selections.v1"), /Dubai shortlist/);
});

test("polygon geometry includes boundary points and rejects crossings and degenerate shapes", () => {
  const p = (latitude, longitude) => ({ latitude, longitude }), square = [p(0, 0), p(0, 2), p(2, 2), p(2, 0)];
  assert.equal(dual.model.validPolygon(square), true); assert.equal(dual.model.pointInPolygon(p(1, 1), square), true); assert.equal(dual.model.pointInPolygon(p(0, 1), square), true); assert.equal(dual.model.pointInPolygon(p(3, 3), square), false);
  assert.equal(dual.model.validPolygon([p(0, 0), p(2, 2), p(0, 2), p(2, 0)]), false);
  assert.equal(dual.model.validPolygon([p(0, 0), p(0, 0), p(2, 0)]), false);
  assert.equal(dual.model.validPolygon([p(0, 0), p(0, 2), p(2, 0)]), true);
});

test("map candidate pages expose later rows for manual inclusion and inspection without changing saved data", async t => {
  const f = await mounted(t, data => { for (let index = 0; index < 30; index++) data.candidates.push({ id: `airbnb:extra:${index}`, title: `Extra ${index}`, latitude: 25, longitude: 55 + index / 10000, selected: false, eligibility: "provisional" }); });
  const before = f.requests.length, original = JSON.stringify(f.f), next = control(f.root, "Next map candidates"), previous = control(f.root, "Previous map candidates");
  assert.equal(previous.disabled, true); assert.equal(next.disabled, false); assert.match(f.root.textContent, /1–25 of 33 area candidates/);
  next.click(); assert.match(f.root.textContent, /26–33 of 33 area candidates/); assert.equal(next.disabled, true);
  const later = control(f.root, "Include Extra 29 in local map selection"); later.checked = false; later.dispatch("change");
  assert.match(f.root.textContent, /32 observed candidates inside this/); assert.match(f.root.textContent, /Locally excluded1/);
  const inspect = find(f.root, node => node.tagName === "BUTTON" && node.textContent === "Extra 29"); inspect.click(); await settle(); assert.equal(f.requests.length, before + 1); assert.match(f.requests.at(-1).url, /candidate_id=airbnb%3Aextra%3A29/);
  assert.equal(JSON.stringify(f.f), original); click(f.root, "Close ×"); previous.click(); assert.match(f.root.textContent, /1–25 of 33 area candidates/);
});
