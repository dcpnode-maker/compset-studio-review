"use strict";
// Independently authored proof. Runs the shipped workspace and its event listeners;
// no browser, server, collection request, or external network is used.
const test = require("node:test");
const assert = require("node:assert/strict");
const dual = require("../compset/static/dual-workspace.js");

class Element {
  constructor(tag, doc) {
    this.tagName = tag.toUpperCase(); this.ownerDocument = doc; this.children = [];
    this.listeners = {}; this.attrs = {}; this.style = { touchAction: "pan-x pan-y", cursor: "grab" };
    this.className = ""; this._text = ""; this.hidden = false; this.disabled = false; this.captured = new Set();
    this.classList = { add: (...names) => { this.className += ` ${names.join(" ")}`; }, toggle() {} };
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
  appendChild(child) { child.remove(); this.children.push(child); child.parentNode = this; return child; }
  replaceChildren(...children) { for (const child of this.children) child.parentNode = null; this.children = []; this._text = ""; children.forEach(child => this.appendChild(child)); }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(child => child !== this); this.parentNode = null; }
  get isConnected() { return this === this.ownerDocument.body || Boolean(this.parentNode && this.parentNode.isConnected); }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  getAttribute(name) { return this.attrs[name]; }
  removeAttribute(name) { delete this.attrs[name]; }
  contains(node) { return node === this || this.children.some(child => child.contains(node)); }
  addEventListener(name, fn, options) { (this.listeners[name] ||= []).push({ fn, options }); }
  removeEventListener(name, fn, options) { this.listeners[name] = (this.listeners[name] || []).filter(value => value.fn !== fn || value.options !== options); }
  dispatch(name, properties = {}) {
    const event = { target: this, defaultPrevented: false, propagationStopped: false,
      preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this.propagationStopped = true; }, ...properties };
    for (const { fn } of [...this.listeners[name] || []]) fn(event);
    return event;
  }
  click() { if (!this.disabled) this.dispatch("click"); }
  focus() { this.ownerDocument.activeElement = this; }
  querySelectorAll() { return nodes(this).filter(node => ["BUTTON", "INPUT", "SELECT", "A"].includes(node.tagName)); }
  setPointerCapture(id) { if (this.captureFails) throw new Error("capture rejected"); this.captured.add(id); }
  hasPointerCapture(id) { return this.captured.has(id); }
  releasePointerCapture(id) { this.captured.delete(id); this.dispatch("lostpointercapture", { pointerId: id }); }
}
class Document {
  constructor() { this.body = new Element("body", this); this.listeners = {}; this.activeElement = this.body; }
  createElement(tag) { return new Element(tag, this); }
  createElementNS(_, tag) { return this.createElement(tag); }
  addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
  removeEventListener(name, fn) { this.listeners[name] = (this.listeners[name] || []).filter(value => value !== fn); }
  dispatch(name, properties) { const event = { preventDefault() {}, ...properties }; [...this.listeners[name] || []].forEach(fn => fn(event)); }
}
const nodes = root => root.children.flatMap(child => [child, ...nodes(child)]);
const find = (root, fn) => { const found = nodes(root).find(fn); assert.ok(found, "Expected rendered node"); return found; };
const click = (root, text) => find(root, node => node.tagName === "BUTTON" && node.textContent.endsWith(text)).click();
const settle = async () => { for (let i = 0; i < 12; i++) await new Promise(resolve => setImmediate(resolve)); };
const subject = { id: "bnbme_direct:review", subject_id: "bnbme_direct:review", title: "Observed subject", namespace: "bnbme_direct", latitude: 25, longitude: 55, city: "Dubai", currency: "AED", bedrooms: 1 };
const candidates = [
  { id: "airbnb:near", title: "=HYPERLINK(\"bad\")", latitude: 25.002, longitude: 55, selected: true, eligibility: "eligible", bedrooms: 2, bathrooms: 1, missing_fields: [], reasons: ["observed attributes"], source_url: "https://www.airbnb.com/rooms/100", observed_at: "2026-09-27T22:00:00Z", distance_km: .22 },
  { id: "airbnb:far", title: "Far observed candidate", latitude: 25.015, longitude: 55, selected: false, eligibility: "provisional", bedrooms: 1, missing_fields: ["operator"], source_url: "javascript:bad", observed_at: "2026-09-26T22:00:00Z", distance_km: 1.66 },
  { id: "airbnb:unknown", title: "Missing location", latitude: null, longitude: null, selected: false, eligibility: "excluded", missing_fields: ["latitude"] }
];
function leaflet(doc) {
  const stats = { maps: [], circles: [], markers: [], groups: [] };
  const layer = kind => ({ kind, handlers: {}, layers: new Set(), on(name, fn) { this.handlers[name] = fn; return this; },
    addTo(target) { this.target = target; if (target.layers) target.layers.add(this); return this; },
    setLatLng(point) { this.point = [...point]; return this; }, getLatLng() { return { lat: this.point[0], lng: this.point[1] }; },
    setRadius(radius) { this.radius = radius; return this; }, bindPopup(fn) { this.popup = fn; return this; },
    removeLayer(value) { this.layers.delete(value); }, remove() { this.removed = true; }, invalidateSize() {} });
  return { stats, api: {
    map(node) {
      const map = layer("map"); map.node = node; node.className += " leaflet-container leaflet-touch leaflet-grab"; map.setView = (point, zoom) => { map.center = [...point]; map.zoom = zoom; return map; };
      map.mouseEventToLatLng = event => event.latlng || { lat: 25 + event.clientY / 10000, lng: 55 + event.clientX / 10000 };
      for (const name of ["dragging", "touchZoom", "doubleClickZoom", "scrollWheelZoom", "boxZoom", "keyboard", "tap"]) {
        let enabled = !["scrollWheelZoom", "tap"].includes(name);
        map[name] = { enabled: () => enabled, disable() { enabled = false; }, enable() { enabled = true; } };
      }
      stats.maps.push(map); return map;
    },
    tileLayer() { return layer("tile"); },
    circle(point, options) { const value = layer("circle").setLatLng(point).setRadius(options.radius); stats.circles.push(value); return value; },
    divIcon(options) { return options; },
    marker(point, options) { const value = layer("marker").setLatLng(point); value.element = doc.createElement("div"); value.options = options; value.getElement = () => value.element; stats.markers.push(value); return value; },
    circleMarker(point) { return layer("candidate").setLatLng(point); },
    layerGroup() { const value = layer("group"); stats.groups.push(value); return value; }
  } };
}
async function fixture(t, savedCandidates = candidates) {
  const previous = { fetch: global.fetch, L: global.L, URL: global.URL, matchMedia: global.matchMedia };
  const doc = new Document(), fake = leaflet(doc), root = doc.createElement("div"), requests = [], snapshot = JSON.stringify(candidates);
  doc.body.appendChild(root); global.L = fake.api; global.URL = class extends previous.URL { static createObjectURL = undefined; };
  global.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
  global.fetch = async (url, options = {}) => {
    requests.push({ url, method: options.method || "GET" });
    let data;
    if (url === "/api/workspace/job") data = { state: "idle", busy: false };
    else if (url === "/api/intelligence") data = { revision: "review-r1", str: { properties: [subject], subjects: [subject], default_start: "2026-10-01", summary: {} }, hotel: { label: "Hotel Aketa" } };
    else if (url.includes("/str/calendar?")) data = { revision: "review-r1", dates: ["2026-10-01"], entities: [subject], cells: [], total: 1, request: { start: "2026-10-01", days: 14, offset: 0, limit: 25, namespace: "bnbme_direct", city: null, currency: null, bedrooms: null, query: "" } };
    else if (url.includes("/str/compset?")) data = { revision: "review-r1", subject, candidates: savedCandidates, map_points: savedCandidates, candidate_total: savedCandidates.length, summary: {}, request: { subject_id: subject.id, offset: 0, limit: 25, decision: null } };
    else if (url === "/api/intelligence/hotel") data = { revision: "review-r1", dataset: { entities: [], dates: [], cells: [] }, compset: { subject: { ...subject, id: "hotel:aketa", title: "Hotel Aketa" }, candidates: savedCandidates, map_points: savedCandidates } };
    else throw new Error(`Unexpected local read: ${url}`);
    return { ok: true, json: async () => data };
  };
  t.after(() => { dual.destroy(); Object.assign(global, previous); assert.equal(JSON.stringify(candidates), snapshot, "Saved candidate evidence is immutable"); });
  await dual.mount(root); click(root, "Map"); await settle();
  const map = fake.stats.maps[0], node = map.node, circle = fake.stats.circles[0];
  assert.ok(circle); return { doc, fake, root, requests, map, node, circle };
}
const handlerState = map => Object.fromEntries(["dragging", "touchZoom", "doubleClickZoom", "scrollWheelZoom", "boxZoom", "keyboard", "tap"].map(name => [name, map[name].enabled()]));
const pointer = (node, name, props = {}) => node.dispatch(name, { pointerId: 1, pointerType: "touch", isPrimary: true, button: 0, clientX: 0, clientY: 0, ...props });
const draw = (view, end, props = {}) => { click(view.root, "Draw area"); pointer(view.node, "pointerdown", props); pointer(view.node, "pointermove", { clientY: end, ...props }); pointer(view.node, "pointerup", { clientY: end, ...props }); };

for (const pointerType of ["mouse", "touch", "pen"]) test(`review: ${pointerType} draws one geographic circle and restores exactly the original map handlers`, async t => {
  const view = await fixture(t), prior = handlerState(view.map), original = [...view.circle.point], reads = view.requests.length;
  click(view.root, "Draw area"); assert.ok(Object.values(handlerState(view.map)).every(value => !value)); assert.equal(view.node.style.touchAction, "none");
  const down = pointer(view.node, "pointerdown", { pointerType }); assert.ok(down.defaultPrevented && down.propagationStopped); assert.ok(view.node.captured.has(1));
  for (const className of ["leaflet-container", "leaflet-touch", "leaflet-grab"]) assert.ok(view.node.className.split(/\s+/).includes(className), "Editing must preserve Leaflet runtime classes");
  pointer(view.node, "pointermove", { pointerType, clientY: 100 }); assert.match(view.root.textContent, /preview/i);
  pointer(view.node, "pointerup", { pointerType, clientY: 100 });
  assert.deepEqual(view.circle.point, original); assert.ok(view.circle.radius > 1000 && view.circle.radius < 1200);
  assert.equal(view.fake.stats.circles.length, 1); assert.deepEqual(handlerState(view.map), prior); assert.equal(view.node.captured.size, 0);
  assert.equal(view.node.style.touchAction, "pan-x pan-y"); assert.equal(view.node.style.cursor, "grab"); assert.equal(view.requests.length, reads);
  for (const className of ["leaflet-container", "leaflet-touch", "leaflet-grab"]) assert.ok(view.node.className.split(/\s+/).includes(className));
});

for (const interruption of ["Cancel", "Escape", "pointercancel", "lostpointercapture", "second-touch"]) test(`review: ${interruption} retains the committed area after preview and releases capture`, async t => {
  const view = await fixture(t), prior = handlerState(view.map), point = [...view.circle.point], radius = view.circle.radius;
  click(view.root, "Draw area"); pointer(view.node, "pointerdown"); pointer(view.node, "pointermove", { clientY: 100 }); assert.notEqual(view.circle.radius, radius);
  if (interruption === "Cancel") click(view.root, "Cancel");
  else if (interruption === "Escape") view.doc.dispatch("keydown", { key: "Escape" });
  else if (interruption === "second-touch") pointer(view.node, "pointerdown", { pointerId: 2, isPrimary: false });
  else pointer(view.node, interruption);
  assert.deepEqual(view.circle.point, point); assert.equal(view.circle.radius, radius); assert.deepEqual(handlerState(view.map), prior); assert.equal(view.node.captured.size, 0);
  pointer(view.node, "pointerup", { clientY: 100 }); assert.equal(view.circle.radius, radius, "A later release cannot resurrect a cancelled draft");
});

test("review: unavailable capture, right mouse button, taps, and foreign pointer releases cannot alter the area", async t => {
  const view = await fixture(t), radius = view.circle.radius, prior = handlerState(view.map);
  view.node.captureFails = true; click(view.root, "Draw area"); pointer(view.node, "pointerdown"); assert.deepEqual(handlerState(view.map), prior); assert.equal(view.circle.radius, radius);
  view.node.captureFails = false; click(view.root, "Draw area"); pointer(view.node, "pointerdown", { button: 2 }); pointer(view.node, "pointerup", { button: 2, clientY: 100 }); assert.equal(view.circle.radius, radius); click(view.root, "Cancel");
  click(view.root, "Draw area"); pointer(view.node, "pointerdown"); pointer(view.node, "pointerup"); assert.equal(view.circle.radius, radius); assert.deepEqual(handlerState(view.map), prior);
  click(view.root, "Draw area"); pointer(view.node, "pointerdown"); pointer(view.node, "pointermove", { clientY: 100 }); pointer(view.node, "pointerup", { pointerId: 2, clientY: 200 });
  assert.equal(view.node.captured.size, 1); click(view.root, "Cancel"); assert.equal(view.circle.radius, radius);
});

test("review: final draw endpoint inside minimum radius cannot commit an earlier larger preview", async t => {
  const view = await fixture(t), prior = view.circle.radius;
  click(view.root, "Draw area"); pointer(view.node, "pointerdown"); pointer(view.node, "pointermove", { clientY: 100 });
  pointer(view.node, "pointermove", { clientY: 1 }); pointer(view.node, "pointerup", { clientY: 1 });
  assert.ok(view.circle.radius === prior || view.circle.radius === 100, "Final release must retain prior area or explicitly select the minimum; it must not select the stale 1.11 km preview");
});

test("review: page hiding and a second touch outside the map cancel drafts and restore prior controls", async t => {
  const view = await fixture(t), prior = handlerState(view.map), radius = view.circle.radius;
  for (const outsideEvent of ["pointerdown", "visibilitychange"]) {
    click(view.root, "Draw area"); pointer(view.node, "pointerdown"); pointer(view.node, "pointermove", { clientY: 100 });
    if (outsideEvent === "pointerdown") view.doc.dispatch(outsideEvent, { pointerId: 2, isPrimary: false });
    else { view.doc.hidden = true; view.doc.dispatch(outsideEvent, {}); view.doc.hidden = false; }
    assert.equal(view.circle.radius, radius); assert.equal(view.node.captured.size, 0); assert.deepEqual(handlerState(view.map), prior);
  }
});

test("review: missing saved match decisions remain Unknown in area metrics, popup and CSV", async t => {
  const row = { ...candidates[0], selected: undefined, eligibility: undefined }, view = await fixture(t, [row]);
  const summary = find(view.root, node => node.className === "dw-map-summary");
  assert.match(summary.textContent, /Saved selectedUnknown/); assert.match(summary.textContent, /Saved provisionalUnknown/); assert.match(summary.textContent, /Decision evidence missing1/);
  const marker = [...view.fake.stats.groups[0].layers][0], popup = marker.popup();
  assert.match(popup.textContent, /Unknown/); assert.doesNotMatch(popup.textContent, /provisional/i);
  click(view.root, "Export map view ↓"); const csv = find(view.root, node => node.className === "dw-export-preview").textContent;
  assert.doesNotMatch(csv, /provisional|,selected,/i);
});

test("review: direct center and edge handles edit without ordinary map clicks silently changing the area", async t => {
  const view = await fixture(t), radius = view.circle.radius, prior = handlerState(view.map);
  pointer(view.node, "pointerdown"); pointer(view.node, "pointermove", { clientY: 100 }); pointer(view.node, "pointerup", { clientY: 100 });
  if (view.map.handlers.click) view.map.handlers.click({ latlng: { lat: 26, lng: 56 } }); assert.deepEqual(view.circle.point, [25, 55]);
  const center = view.fake.stats.markers[0].element;
  pointer(view.node, "pointerdown", { target: center }); assert.ok(Object.values(handlerState(view.map)).every(value => !value));
  pointer(view.node, "pointermove", { target: center, clientY: 100 }); pointer(view.node, "pointerup", { target: center, clientY: 100 });
  assert.deepEqual(view.circle.point, [25.01, 55]); assert.equal(view.circle.radius, radius); assert.deepEqual(handlerState(view.map), prior);
  const edge = view.fake.stats.markers[1].element; edge.dispatch("keydown", { key: "Enter" });
  assert.equal(find(view.root, node => node.tagName === "BUTTON" && node.textContent === "Resize area").getAttribute("aria-pressed"), "true");
  pointer(view.node, "pointerdown", { target: edge, clientY: 100 }); pointer(view.node, "pointermove", { target: edge, clientY: 150 }); pointer(view.node, "pointerup", { target: edge, clientY: 150 });
  assert.deepEqual(view.circle.point, [25.01, 55]); assert.ok(view.circle.radius > 500 && view.circle.radius < 600); assert.deepEqual(handlerState(view.map), prior);
});

test("review: selected-area CSV uses committed evidence and candidate inspector preserves source, attributes, identity and decisions", async t => {
  const view = await fixture(t), reads = view.requests.length;
  draw(view, 100); assert.match(view.root.textContent, /1 observed candidates inside/);
  const control = find(view.root, node => node.getAttribute("aria-label") === "Area radius in kilometres"); assert.equal(control.type, "number"); assert.equal(control.min, "0.1"); assert.equal(control.max, "50");
  click(view.root, "Draw area"); pointer(view.node, "pointerdown"); pointer(view.node, "pointermove", { clientY: 300 }); click(view.root, "Export map view ↓");
  const csv = find(view.root, node => node.className === "dw-export-preview").textContent;
  assert.match(csv, /bnbme_direct:review/); assert.match(csv, /airbnb:near/); assert.doesNotMatch(csv, /airbnb:far|airbnb:unknown/);
  assert.match(csv, /selected/); assert.match(csv, /2026-09-27T22:00:00Z/); assert.match(csv, /https:\/\/www.airbnb.com\/rooms\/100/); assert.match(csv, /'=?HYPERLINK/);
  const row = find(view.root, node => node.className === "dw-map-candidate"); row.click(); await settle();
  assert.match(view.root.textContent, /Selected/); assert.match(view.root.textContent, /Bedrooms2/); assert.match(view.root.textContent, /observed attributes/);
  const source = find(view.root, node => node.tagName === "A" && node.textContent === "Open evidence source"); assert.equal(source.href, candidates[0].source_url);
  assert.equal(view.requests.length, reads); assert.ok(view.requests.every(request => request.method === "GET"));
});

test("review: navigation and teardown cancel drafts, restore handlers, remove listeners, and reject old callbacks", async t => {
  const view = await fixture(t), prior = handlerState(view.map), radius = view.circle.radius;
  click(view.root, "Draw area"); pointer(view.node, "pointerdown"); pointer(view.node, "pointermove", { clientY: 100 });
  const oldMove = view.node.listeners.pointermove[0].fn;
  click(view.root, "Hotels"); await settle(); assert.deepEqual(handlerState(view.map), prior); assert.equal(view.circle.radius, radius); assert.equal(view.node.captured.size, 0);
  assert.ok(Object.values(view.node.listeners).every(values => !values.length)); assert.ok(view.map.removed);
  oldMove({ pointerId: 1, clientX: 0, clientY: 900, preventDefault() {}, stopPropagation() {} }); assert.equal(view.circle.radius, radius);
  click(view.root, "Map"); await settle(); const next = view.fake.stats.maps.at(-1), nextCircle = view.fake.stats.circles.at(-1), nextPrior = handlerState(next), nextRadius = nextCircle.radius;
  click(view.root, "Draw area"); pointer(next.node, "pointerdown"); pointer(next.node, "pointermove", { clientY: 100 }); dual.destroy();
  assert.deepEqual(handlerState(next), nextPrior); assert.equal(next.node.captured.size, 0); assert.ok(next.removed); assert.ok(Object.values(next.node.listeners).every(values => !values.length));
  assert.equal(view.doc.listeners.keydown.length, 0); assert.equal(view.doc.listeners.focusin.length, 0);
});

test("review: animation frames coalesce previews, release commits its own endpoint, and cancelled frames cannot paint after teardown", async t => {
  const view = await fixture(t), previous = { requestAnimationFrame: global.requestAnimationFrame, cancelAnimationFrame: global.cancelAnimationFrame }, frames = new Map();
  let nextId = 0, cancelled = [];
  global.requestAnimationFrame = fn => { frames.set(++nextId, fn); return nextId; };
  global.cancelAnimationFrame = id => { cancelled.push(frames.get(id)); frames.delete(id); };
  t.after(() => Object.assign(global, previous));
  const radius = view.circle.radius, prior = handlerState(view.map), reads = view.requests.length;
  click(view.root, "Draw area"); pointer(view.node, "pointerdown"); pointer(view.node, "pointermove", { clientY: 100 }); pointer(view.node, "pointermove", { clientY: 300 });
  assert.equal(frames.size, 1); assert.equal(view.circle.radius, radius, "Preview paint is deferred to one frame");
  const first = [...frames.values()][0]; frames.clear(); first(); assert.ok(view.circle.radius > 3300 && view.circle.radius < 3400);
  pointer(view.node, "pointermove", { clientY: 400 }); assert.equal(frames.size, 1);
  pointer(view.node, "pointerup", { clientY: 500 }); const committed = view.circle.radius;
  assert.ok(committed > 5500 && committed < 5600); assert.equal(frames.size, 0); assert.deepEqual(handlerState(view.map), prior);
  cancelled.filter(Boolean).forEach(fn => fn()); assert.equal(view.circle.radius, committed, "A cancelled frame cannot overwrite the release endpoint");
  click(view.root, "Draw area"); pointer(view.node, "pointerdown"); pointer(view.node, "pointermove", { clientY: 800 }); const late = [...frames.values()][0]; dual.destroy();
  assert.equal(frames.size, 0); assert.deepEqual(handlerState(view.map), prior); const removedRadius = view.circle.radius; late(); assert.equal(view.circle.radius, removedRadius);
  assert.equal(view.requests.length, reads);
});
