"use strict";
// Independent reviewer proof; no browser, real network or collector process.
const test = require('node:test');
const assert = require('node:assert/strict');
const rates = require('../compset/static/rates-workspace.js');

class Element {
  constructor(tag, doc) { this.tagName = tag.toUpperCase(); this.ownerDocument = doc; this.children = []; this.listeners = {}; this.attrs = {}; this._text = ''; this.className = ''; this.classList = { add() {}, toggle() {} }; }
  set textContent(v) { this._text = String(v); this.children = []; }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(''); }
  appendChild(child) { child.remove(); child.parentNode = this; this.children.push(child); return child; }
  replaceChildren(...values) { this.children.forEach(c => c.parentNode = null); this.children = []; this._text = ''; values.forEach(c => this.appendChild(c)); }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(c => c !== this); this.parentNode = null; }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener(k, fn) { (this.listeners[k] ||= []).push(fn); }
  click() { if (!this.disabled) (this.listeners.click || []).forEach(fn => fn({ target: this })); }
  focus() {}
  querySelectorAll() { return []; }
}
class Document {
  constructor() { this.listeners = {}; this.body = new Element('body', this); }
  createElement(tag) { return new Element(tag, this); }
  addEventListener(k, fn) { (this.listeners[k] ||= []).push(fn); }
  removeEventListener(k, fn) { this.listeners[k] = (this.listeners[k] || []).filter(x => x !== fn); }
}
const all = node => node.children.flatMap(c => [c, ...all(c)]);
const button = (root, label) => { const found = all(root).find(n => n.tagName === 'BUTTON' && n.textContent === label); assert.ok(found); return found; };
const reply = value => ({ ok: true, json: async () => value });
const idle = { state: 'idle', job_id: null, busy: false };
const running = { state: 'running', job_id: 'observed-job', dataset_id: 'aketa', busy: true, updated_at: '2026-09-28T08:00:00Z', message: 'Actual running job' };
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { resolve, promise }; };
const settle = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
function setup(t, fetch, onReload = () => {}) {
  const old = { fetch: global.fetch, timeout: global.setTimeout, clear: global.clearTimeout };
  const timers = new Map(); let next = 1;
  global.fetch = fetch;
  global.setTimeout = fn => { timers.set(next, fn); return next++; };
  global.clearTimeout = id => timers.delete(id);
  const doc = new Document(), root = doc.createElement('div'); doc.body.appendChild(root);
  const dock = rates.mountCollection(root, { datasetId: 'aketa', onReload });
  t.after(() => { dock.destroy(); global.fetch = old.fetch; global.setTimeout = old.timeout; global.clearTimeout = old.clear; });
  return { dock, root, timers, doc };
}

test('destroyed dock ignores delayed status and removes listeners without polling or posting', async t => {
  const wait = deferred(); const requests = [];
  const { dock, root, timers, doc } = setup(t, (url, options) => { requests.push({ url, options }); return wait.promise; });
  const before = root.textContent;
  dock.destroy(); wait.resolve(reply(running)); await dock.ready;
  assert.equal(root.textContent, before); assert.equal(timers.size, 0); assert.equal(doc.listeners.keydown.length, 0);
  assert.equal(requests.length, 1); assert.equal(requests[0].options.method, 'GET');
});

test('destroy during fresh preflight prevents the not-yet-sent POST', async t => {
  const wait = deferred(); const requests = [];
  const { dock, root, timers } = setup(t, (url, options) => { requests.push({ url, options }); return requests.length === 1 ? Promise.resolve(reply(idle)) : wait.promise; });
  await dock.ready; button(root, 'Fetch fresh data').click(); await settle();
  dock.destroy(); wait.resolve(reply(idle)); await settle();
  assert.equal(requests.length, 2); assert.ok(requests.every(r => r.options.method === 'GET')); assert.equal(timers.size, 0);
});

test('fresh click freezes target even when visible dataset changes during ownership preflight', async t => {
  const wait = deferred(); const requests = [];
  const { dock, root } = setup(t, (url, options) => {
    requests.push({ url, options });
    if (requests.length === 1) return Promise.resolve(reply(idle));
    if (options.method === 'POST') return Promise.resolve(reply(running));
    return wait.promise;
  });
  await dock.ready; button(root, 'Fetch fresh data').click(); await settle();
  dock.setDataset('airbnb-compset'); wait.resolve(reply(idle)); await settle();
  const posts = requests.filter(r => r.options.method === 'POST');
  assert.equal(posts.length, 1); assert.deepEqual(JSON.parse(posts[0].options.body), { dataset_id: 'aketa', mode: 'fresh' });
  assert.match(root.textContent, /Actual running job/);
});

test('destroy after sent POST cannot retarget retry or poll the authorized job', async t => {
  const wait = deferred(); const requests = [];
  const { dock, root, timers } = setup(t, (url, options) => { requests.push({ url, options }); return options.method === 'POST' ? wait.promise : Promise.resolve(reply(idle)); });
  await dock.ready; button(root, 'Fetch fresh data').click(); await settle();
  assert.equal(requests.filter(r => r.options.method === 'POST').length, 1);
  dock.destroy(); const before = root.textContent; wait.resolve(reply(running)); await settle();
  assert.equal(root.textContent, before); assert.equal(timers.size, 0); assert.equal(requests.length, 3);
});

test('job completion during an earlier saved-data reload schedules a fresh follow-up read', async t => {
  let status = running; let reads = 0; const firstRead = deferred();
  const { dock } = setup(t, async () => reply(status), () => { reads++; return reads === 1 ? firstRead.promise : Promise.resolve(); });
  await dock.ready;
  const priorRefresh = dock.refresh(); await settle(); assert.equal(reads, 1);
  status = { ...running, state: 'complete', busy: false, updated_at: '2026-09-28T08:05:00Z' };
  await dock.refreshStatus();
  firstRead.resolve(); await priorRefresh; await settle();
  assert.equal(reads, 2, 'The completion read must not be lost behind an earlier pending snapshot');
});

test('unsupported hotel selection disables fresh but preserves the actual resumable job target', async t => {
  const partial = { ...running, state: 'partial', busy: false }; const requests = [];
  const { dock, root } = setup(t, async (url, options) => { requests.push({ url, options }); return reply(options.method === 'POST' ? running : partial); });
  await dock.ready; dock.setDataset(null);
  assert.equal(button(root, 'Fetch fresh data').disabled, true);
  assert.match(root.textContent, /not configured|not have a verified collection adapter/i);
  button(root, 'Resume collection').click(); await settle();
  const posts = requests.filter(r => r.options.method === 'POST');
  assert.equal(posts.length, 1); assert.deepEqual(JSON.parse(posts[0].options.body), { dataset_id: 'aketa', mode: 'resume' });
});

test('destroy clears a queued completion read instead of starting hidden work after old read resolves', async t => {
  let status = running, reads = 0; const wait = deferred();
  const { dock } = setup(t, async () => reply(status), () => { reads++; return wait.promise; });
  await dock.ready; const refresh = dock.refresh(); await settle();
  status = { ...running, state: 'complete', busy: false, updated_at: '2026-09-28T08:05:00Z' };
  await dock.refreshStatus(); dock.destroy(); wait.resolve(); await refresh; await settle();
  assert.equal(reads, 1);
});

test('actual app shell mounts only the dual view initially and defers legacy reads until an explicit legacy navigation', () => {
  const fs = require('node:fs'), vm = require('node:vm');
  const doc = new Document(), nodes = new Map();
  doc.getElementById = id => { if (!nodes.has(id)) nodes.set(id, new Element('div', doc)); return nodes.get(id); };
  doc.querySelectorAll = () => [];
  const requests = []; let mounts = 0, timers = 0;
  const window = { addEventListener() {}, CompSetDual: { mount: () => { mounts++; } } };
  const context = { document: doc, window, fetch: (url, options) => { requests.push({ url, options }); return new Promise(() => {}); },
    setTimeout: () => { timers++; }, clearTimeout() {}, Intl, Date, console };
  vm.runInNewContext(fs.readFileSync(require.resolve('../compset/static/app.js'), 'utf8'), context);
  assert.equal(mounts, 1); assert.equal(requests.length, 0);
  window.CompSetCollectionStatus(running);
  assert.equal(requests.length, 0); assert.equal(timers, 0);
  doc.getElementById('view-portfolio').click();
  assert.deepEqual(requests.map(r => r.url), ['/api/status']);
  doc.getElementById('view-prices').click();
  assert.equal(requests.length, 1);
});
