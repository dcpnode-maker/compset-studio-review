"use strict";
// Independent reviewer tests: deterministic DOM model, no browser or live requests.
const test = require('node:test');
const assert = require('node:assert/strict');
const dual = require('../compset/static/dual-workspace.js');
const m = dual.model;
class Element {
  constructor(tag, doc) { this.tagName = tag.toUpperCase(); this.ownerDocument = doc; this.children = []; this.listeners = {}; this.attrs = {}; this._text = ''; this.className = ''; this.hidden = false; this.classList = { add() {}, toggle() {} }; }
  set textContent(v) { this._text = String(v); this.children = []; }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(''); }
  appendChild(child) { child.remove(); child.parentNode = this; this.children.push(child); return child; }
  replaceChildren(...values) { this.children.forEach(c => c.parentNode = null); this.children = []; this._text = ''; values.forEach(c => this.appendChild(c)); }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(c => c !== this); this.parentNode = null; }
  setAttribute(k, v) { this.attrs[k] = v; }
  getAttribute(k) { return this.attrs[k]; }
  addEventListener(k, fn) { (this.listeners[k] ||= []).push(fn); }
  click() { if (!this.disabled) (this.listeners.click || []).forEach(fn => fn({ target: this })); }
  focus() { this.ownerDocument.activeElement = this; }
  get isConnected() { return Boolean(this.parentNode) || this === this.ownerDocument.body; }
  querySelectorAll() { return []; }
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

test('hotel calendar and table never inherit the STR mobile-day selection', () => {
  const data = { dates: dates.slice(0, 2), entities: [{ id: 'agoda', currency: 'INR' }], cells: dates.slice(0, 2).map((date, i) => ({ entity_id: 'agoda', date, state: 'quoted', amount: String(5000 + i * 1000), currency: 'INR' })) };
  const rows = m.hotelView(data, { day: dates[0] });
  assert.deepEqual(rows[0].cells.map(c => c.date), data.dates);
  assert.equal(m.exportRows(rows, { adults: 1 }).split('\r\n').length, 3);
});

test('candidate detail captured before a saved-data reload cannot overwrite the new source revision', async t => {
  const oldFetch = global.fetch; t.after(() => { dual.destroy(); global.fetch = oldFetch; });
  let revision = 'source-v1', resolveDetail;
  const detailReply = new Promise(resolve => { resolveDetail = resolve; });
  global.fetch = async url => {
    if (url === '/api/workspace/job') return reply({ state: 'idle', busy: false });
    if (url === '/api/intelligence') return reply(summary(revision));
    if (url.includes('/str/calendar?')) return reply(calendar(revision));
    if (url.includes('candidate_id=')) return detailReply;
    if (url.includes('/str/compset?')) return reply(comparison(revision));
    throw new Error('Unexpected local fixture URL');
  };
  const doc = new Document(), root = doc.createElement('div'); doc.body.appendChild(root);
  await dual.mount(root);
  click(root, 'Map'); await settle();
  const mapRow = all(root).find(n => n.className === 'dw-map-candidate'); assert.ok(mapRow); mapRow.click(); await settle();
  revision = 'source-v2'; click(root, 'Reload saved'); await settle();
  resolveDetail(reply({ ...comparison('source-v1'), candidates: [{ ...candidate, title: 'STALE_DETAIL_CANARY', missing_fields: [] }] }));
  await settle();
  assert.doesNotMatch(root.textContent, /STALE_DETAIL_CANARY/);
});

const configuredGroup = (subjectId, labels) => ({ subject_id: subjectId, competitor_labels: labels,
  identity_status: 'name_only_unresolved', observed_at: '2026-09-28T09:57:29Z', source_url: 'https://app.mylighthouse.com/hotel/123/rates' });

test('configured names keep unknown coverage distinct from an observed empty group', () => {
  assert.equal(m.configuredGroup(null, 'lighthouse:123').count, null);
  assert.equal(m.configuredGroup({ status: 'read_error', groups: [] }, 'lighthouse:123').status, 'read_error');
  const payload = { status: 'observed_name_only', groups: [configuredGroup('lighthouse:123', [])] };
  assert.equal(m.configuredGroup(payload, 'lighthouse:123').count, 0);
  assert.equal(m.configuredGroup(payload, 'lighthouse:456').count, null);
  assert.equal(m.configuredGroup({ ...payload, groups: [payload.groups[0], payload.groups[0]] }, 'lighthouse:123').status, 'read_error');
});

test('configured-name export preserves exact subject identity and never invents candidate IDs or rates', () => {
  const payload = { status: 'observed_name_only', groups: [configuredGroup('lighthouse:123', ['=HYPERLINK("attacker")', 'Known subject title'])] };
  const csv = m.configuredCsv({ id: 'lighthouse:123', title: 'Selected subject' }, payload);
  assert.match(csv, /lighthouse:123/);
  assert.match(csv, /'=?HYPERLINK/);
  assert.match(csv, /name_only_unresolved/);
  assert.match(csv, /not_collected/);
  assert.match(csv, /2026-09-28T09:57:29Z/);
  assert.doesNotMatch(csv.split('\r\n')[0], /competitor_id|amount|currency/);
  const unknown = m.configuredCsv({ id: 'lighthouse:456', title: 'Unobserved' }, payload);
  assert.match(unknown, /not_observed/);
  assert.doesNotMatch(unknown, /HYPERLINK|Known subject title/);
});

test('imported comparison labels render for the exact selected subject without links to rates or other groups', async t => {
  const oldFetch = global.fetch; t.after(() => { dual.destroy(); global.fetch = oldFetch; });
  const profiles = [{ id: 'lighthouse:123', title: 'Imported selected hotel', roles: ['subject'], configured_label_count: 1, configured_label_status: 'observed_name_only', rate_coverage: { collection_supported: false } },
    { id: 'lighthouse:456', title: 'Unobserved second hotel', roles: ['subject'], configured_label_count: null, configured_label_status: 'not_observed', rate_coverage: { collection_supported: false } }];
  const header = { ...summary('same-revision'), hotel: { portfolio: { profiles } } };
  const hotel = { revision: 'same-revision', dataset: { entities: [{ id: 'agoda', label: 'AKETA_RATE_CANARY' }], dates: dates.slice(0, 1), cells: [] },
    portfolio: { profiles, configured_labels: { status: 'observed_name_only', groups: [configuredGroup('lighthouse:123', ['FIRST_GROUP_CANARY']), configuredGroup('lighthouse:999', ['OTHER_GROUP_CANARY'])] } } };
  const requests = [];
  global.fetch = async (url, options) => {
    requests.push({ url, options });
    if (url === '/api/workspace/job') return reply({ state: 'idle', busy: false });
    if (url === '/api/intelligence') return reply(header);
    if (url.includes('/str/calendar?')) return reply(calendar('same-revision'));
    if (url === '/api/intelligence/hotel') return reply(hotel);
    throw new Error('Unexpected fixture request');
  };
  const doc = new Document(), root = doc.createElement('div'); doc.body.appendChild(root);
  await dual.mount(root); click(root, 'Hotels'); await settle();
  async function chooseHotel(value) {
    const select = all(root).find(n => n.tagName === 'SELECT' && n.getAttribute('aria-label') === 'Hotel');
    assert.ok(select); select.value = value; (select.listeners.change || []).forEach(fn => fn({ target: select })); await settle();
  }
  await chooseHotel('lighthouse:123'); click(root, 'Comparison set'); await settle();
  const canvas = () => all(root).find(n => n.className === 'dw-canvas');
  assert.match(canvas().textContent, /FIRST_GROUP_CANARY/);
  assert.match(canvas().textContent, /OTA identities unverified/);
  assert.match(canvas().textContent, /Not collected/);
  assert.doesNotMatch(canvas().textContent, /OTHER_GROUP_CANARY|AKETA_RATE_CANARY/);
  assert.equal(all(canvas()).filter(n => ['BUTTON', 'A'].includes(n.tagName) && n.textContent.includes('FIRST_GROUP_CANARY')).length, 0);
  await chooseHotel('lighthouse:456');
  assert.match(canvas().textContent, /Coverage unknown/);
  assert.doesNotMatch(canvas().textContent, /FIRST_GROUP_CANARY|OTHER_GROUP_CANARY|AKETA_RATE_CANARY/);
  assert.ok(requests.every(r => r.options.method === 'GET'));
});
