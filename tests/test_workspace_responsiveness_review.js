"use strict";
// Independent reviewer tests: deterministic DOM model, no browser or live requests.
const test = require('node:test');
const assert = require('node:assert/strict');
const dual = require('../compset/static/dual-workspace.js');
const m = dual.model;
class Element {
  constructor(tag, doc) { this.tagName = tag.toUpperCase(); this.ownerDocument = doc; this.children = []; this.listeners = {}; this.attrs = {}; this._text = ''; this.className = ''; this.style = {}; this.hidden = false; this.captured = new Set(); this.classList = { add() {}, toggle() {} }; }
  set textContent(v) { this._text = String(v); this.children = []; }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(''); }
  appendChild(child) { child.remove(); child.parentNode = this; this.children.push(child); return child; }
  replaceChildren(...values) { this.children.forEach(c => c.parentNode = null); this.children = []; this._text = ''; values.forEach(c => this.appendChild(c)); }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(c => c !== this); this.parentNode = null; }
  setAttribute(k, v) { this.attrs[k] = v; }
  getAttribute(k) { return this.attrs[k]; }
  addEventListener(k, fn) { (this.listeners[k] ||= []).push(fn); }
  removeEventListener(k, fn) { this.listeners[k] = (this.listeners[k] || []).filter(value => value !== fn); }
  dispatch(k, properties = {}) { (this.listeners[k] || []).forEach(fn => fn({ target: this, preventDefault() {}, stopPropagation() {}, ...properties })); }
  setPointerCapture(id) { this.captured.add(id); }
  hasPointerCapture(id) { return this.captured.has(id); }
  releasePointerCapture(id) { this.captured.delete(id); }
  click() { if (!this.disabled) (this.listeners.click || []).forEach(fn => fn({ target: this })); }
  focus() { this.ownerDocument.activeElement = this; }
  get isConnected() { return this === this.ownerDocument.body || Boolean(this.parentNode && this.parentNode.isConnected); }
  querySelectorAll() { return all(this).filter(n => ['BUTTON','INPUT','SELECT','A'].includes(n.tagName)); }
}
class Document {
  constructor() { this.listeners = {}; this.body = new Element('body', this); this.activeElement = this.body; }
  createElement(tag) { return new Element(tag, this); }
  addEventListener(k, fn) { (this.listeners[k] ||= []).push(fn); }
  removeEventListener(k, fn) { this.listeners[k] = (this.listeners[k] || []).filter(x => x !== fn); }
}
const all = node => node.children.flatMap(c => [c, ...all(c)]);
function click(root, label) { const found = all(root).find(n => n.tagName === 'BUTTON' && n.textContent.endsWith(label)); assert.ok(found, label); found.click(); }
const reply = value => ({ ok: true, json: async () => value });
const settle = async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); };
const dates = Array.from({ length: 14 }, (_, i) => m.addDays('2026-10-01', i));
const subject = { id: 'bnbme_direct:1', subject_id: 'bnbme_direct:1', title: 'Subject property', namespace: 'bnbme_direct', city: 'Dubai', currency: 'AED', latitude: 25, longitude: 55 };
const candidate = { id: 'airbnb:2', candidate_id: 'airbnb:2', title: 'Current candidate', latitude: 25, longitude: 55, selected: true, eligibility: 'eligible' };
const summary = revision => ({ revision, str: { properties: [subject], subjects: [subject], default_start: dates[0], summary: {} }, hotel: {} });
const calendar = revision => ({ revision, request: { start: dates[0], days: 14, offset: 0, limit: 25, namespace: 'bnbme_direct', city: null, currency: null, bedrooms: null, query: '' }, dates, entities: [subject], cells: [], total: 1 });
const comparison = revision => ({ revision, subject, request: { subject_id: subject.id, offset: 0, limit: 25, decision: null }, criteria: { radius_km: 2 }, summary: { selected_count: 1 }, candidates: [{ ...candidate, missing_fields: [] }], map_points: [candidate], candidate_total: 1 });

test('navigation during saved-summary reload cannot poison the new revision with an old cached view', async t => {
  const previous = global.fetch; t.after(() => { dual.destroy(); global.fetch = previous; });
  let summaryCalls = 0, hotelCalls = 0, resolveSummary, revision = 'revision1';
  global.fetch = async url => {
    if (url === '/api/workspace/job') return reply({ state: 'idle', busy: false });
    if (url === '/api/intelligence') {
      if (++summaryCalls === 1) return reply(summary(revision));
      return { ok: true, json: () => new Promise(resolve => { resolveSummary = resolve; }) };
    }
    if (url.includes('/str/calendar?')) return reply(calendar(revision));
    if (url === '/api/intelligence/hotel') { hotelCalls++; return reply({ revision, dataset: { dates: [dates[0]], entities: [], cells: [], label: 'Hotel Aketa' }, compset: {} }); }
    throw new Error('Unexpected fixture request');
  };
  const doc = new Document(), root = doc.createElement('div'); doc.body.appendChild(root); await dual.mount(root);
  const reload = dual.refresh(); await settle();
  click(root, 'Hotels'); await settle();
  assert.equal(hotelCalls, 1);
  revision = 'revision2'; resolveSummary(summary(revision)); await reload; await settle();
  assert.equal(hotelCalls, 2, 'Reload must obtain a view for its new revision rather than reuse an intervening old view');
  assert.doesNotMatch(root.textContent, /Could not load|Saved sources changed/);
});

function leafletFixture() {
  const maps = [], circles = [], groups = [];
  const layer = kind => ({ kind, handlers: {}, point: null, layers: new Set(),
    addTo(target) { if (target.layers) target.layers.add(this); return this; },
    on(event, fn) { this.handlers[event] = fn; return this; },
    setLatLng(point) { this.point = point; return this; }, getLatLng() { return { lat: this.point[0], lng: this.point[1] }; },
    setRadius(radius) { this.radius = radius; return this; }, bindPopup(fn) { this.popup = fn; return this; },
    removeLayer(item) { this.layers.delete(item); }, remove() { this.removed = true; }, invalidateSize() {} });
  return { maps, circles, groups, api: {
    map(node) { const value = layer('map'); value.node = node; value.mouseEventToLatLng = event => event.latlng; value.setView = (center, zoom) => { value.center = center; value.zoom = zoom; return value; }; maps.push(value); return value; },
    tileLayer() { return layer('tile'); }, circle(point) { const value = layer('circle').setLatLng(point); circles.push(value); return value; },
    marker(point) { return layer('marker').setLatLng(point); }, circleMarker(point) { return layer('point').setLatLng(point); },
    layerGroup() { const value = layer('group'); groups.push(value); return value; }
  } };
}

test('reload fallback to a different subject clears the removed subject map center and ignores its callbacks', async t => {
  const oldFetch = global.fetch, oldL = global.L, fake = leafletFixture(); global.L = fake.api;
  t.after(() => { dual.destroy(); global.fetch = oldFetch; global.L = oldL; });
  let current = subject, revision = 'revision1';
  global.fetch = async url => {
    if (url === '/api/workspace/job') return reply({ state: 'idle', busy: false });
    if (url === '/api/intelligence') return reply({ ...summary(revision), str: { ...summary(revision).str, properties: [current], subjects: [current] } });
    if (url.includes('/str/calendar?')) return reply({ ...calendar(revision), entities: [current] });
    if (url.includes('/str/compset?')) return reply({ ...comparison(revision), subject: current, request: { ...comparison(revision).request, subject_id: current.id }, candidates: [], map_points: [] });
    throw new Error('Unexpected fixture request');
  };
  const doc = new Document(), root = doc.createElement('div'); doc.body.appendChild(root); await dual.mount(root);
  click(root, 'Map'); await settle();
  const previousMap = fake.maps.at(-1); click(root, 'Move center');
  previousMap.node.dispatch('pointerdown', { pointerId: 1, clientX: 0, clientY: 0, latlng: { lat: 25, lng: 55 } });
  previousMap.node.dispatch('pointerup', { pointerId: 1, clientX: 30, clientY: 30, latlng: { lat: 24.99, lng: 54.99 } });
  assert.deepEqual(fake.circles.at(-1).point, [24.99, 54.99], 'The first subject must have a custom committed area before fallback');
  const previousPointerMove = previousMap.node.listeners.pointermove[0];
  current = { ...subject, id: 'bnbme_direct:99', subject_id: 'bnbme_direct:99', title: 'Replacement London subject', latitude: 51.5, longitude: -0.15 };
  revision = 'revision2'; await dual.refresh(); await settle();
  assert.deepEqual(fake.maps.at(-1).center, [51.5, -0.15], 'A different fallback subject must use its own observed coordinates');
  previousPointerMove({ pointerId: 1, clientX: 100, clientY: 100, latlng: { lat: 1, lng: 2 }, preventDefault() {}, stopPropagation() {} });
  assert.deepEqual(fake.circles.at(-1).point, [51.5, -0.15], 'Removed-map events must not retarget the new subject');
});

test('late reads remain isolated when AbortController is unavailable', async t => {
  const oldFetch = global.fetch, oldAbort = global.AbortController;
  global.AbortController = undefined;
  t.after(() => { dual.destroy(); global.fetch = oldFetch; global.AbortController = oldAbort; });
  let finishComparison;
  global.fetch = async url => {
    if (url === '/api/workspace/job') return reply({ state: 'idle', busy: false });
    if (url === '/api/intelligence') return reply(summary('same-revision'));
    if (url.includes('/str/calendar?')) return reply(calendar('same-revision'));
    if (url.includes('/str/compset?')) return { ok: true, json: () => new Promise(resolve => { finishComparison = resolve; }) };
    if (url === '/api/intelligence/hotel') return reply({ revision: 'same-revision', dataset: { dates: [dates[0]], entities: [], cells: [] }, compset: {} });
    throw new Error('Unexpected fixture request');
  };
  const doc = new Document(), root = doc.createElement('div'); doc.body.appendChild(root); await dual.mount(root);
  click(root, 'Comparison set'); await settle(); click(root, 'Hotels'); await settle();
  finishComparison({ ...comparison('same-revision'), subject: { ...subject, title: 'STALE_NO_ABORT_CANARY' } }); await settle();
  assert.match(root.textContent, /Hotel Aketa/);
  assert.doesNotMatch(root.textContent, /STALE_NO_ABORT_CANARY|Could not load/);
});

test('radius changes reconcile retained marker membership without stale or duplicate layers', async t => {
  const oldFetch = global.fetch, oldL = global.L, fake = leafletFixture(); global.L = fake.api;
  t.after(() => { dual.destroy(); global.fetch = oldFetch; global.L = oldL; });
  let reads = 0;
  const points = [{ ...candidate, id: 'airbnb:1', latitude: 25.001 }, { ...candidate, id: 'airbnb:2', latitude: 25.012 }];
  global.fetch = async url => {
    reads++;
    if (url === '/api/workspace/job') return reply({ state: 'idle', busy: false });
    if (url === '/api/intelligence') return reply(summary('same-revision'));
    if (url.includes('/str/calendar?')) return reply(calendar('same-revision'));
    if (url.includes('/str/compset?')) return reply({ ...comparison('same-revision'), map_points: points });
    throw new Error('Unexpected fixture request');
  };
  const doc = new Document(), root = doc.createElement('div'); doc.body.appendChild(root); await dual.mount(root);
  click(root, 'Map'); await settle(); const initialReads = reads, group = fake.groups[0], map = fake.maps[0];
  assert.equal(group.layers.size, 2);
  const radius = all(root).find(n => n.getAttribute('aria-label') === 'Map view radius in kilometres');
  const setRadius = value => { radius.value = value; radius.listeners.change.forEach(fn => fn({ target: radius })); };
  setRadius('0.5'); assert.equal(group.layers.size, 1);
  setRadius('2'); assert.equal(group.layers.size, 2);
  setRadius('2'); assert.equal(group.layers.size, 2);
  assert.equal(fake.maps.length, 1); assert.equal(fake.maps[0], map); assert.equal(reads, initialReads);
  assert.ok([...group.layers].every(point => typeof point.popup === 'function'));
});

