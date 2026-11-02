const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');

const base = 'https://gallery.example/GCE-scholar/';
const controls = ['paper-search', 'year', 'sort', 'only-images', 'only-abstracts', 'sources', 'export'];
const scholars = [
  { id: 'alpha', name: 'Alpha Scholar', orcid: '0000-0001-7602-5050' },
  { id: 'beta', name: 'Beta Scholar', orcid: '0000-0002-0402-7417' },
];
const index = { updated: '2026-11-02', scholars: {
  alpha: { file: 'data/scholars/alpha.json', total: 2 },
  beta: { file: 'data/scholars/beta.json', total: 1 },
} };
function paper(scholar, title) {
  return { id: 'DOI:10.1234/' + scholar.id, doi: '10.1234/' + scholar.id,
    title, year: '2026', publicationDate: '2026-10-28', authors: scholar.name,
    authorDetails: [{ fullName: scholar.name, authorId: { type: 'ORCID', value: scholar.orcid } }],
    citations: 0, journal: 'Test journal', url: 'https://doi.org/10.1234/' + scholar.id };
}
const shards = {
  alpha: { papers: [paper(scholars[0], 'Alpha paper'),
    { id: 'wrong', title: 'Name-only paper must be excluded', year: '2026', authorDetails: [{ fullName: 'Alpha Scholar' }] }],
    total: 2, complete: true, updated: '2026-11-02', orcid: scholars[0].orcid },
  beta: { papers: [paper(scholars[1], 'Beta paper')], total: 1, complete: true,
    updated: '2026-11-02', orcid: scholars[1].orcid },
};

function response(payload) {
  return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(payload)) };
}
function normalResponse(path) {
  if (path === 'scholars.json') return response(scholars);
  if (path === 'data/catalog-index.json') return response(index);
  const match = /^data\/scholars\/(alpha|beta)\.json$/.exec(path);
  if (match) return response(shards[match[1]]);
  throw Error('Unexpected request: ' + path);
}
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
async function flush() {
  // All mocked network and JSON work uses promises; no wall-clock sleeps.
  for (let i = 0; i < 40; i += 1) await Promise.resolve();
}
function app({ hash = '', route = normalResponse, abortController = false } = {}) {
  const nodes = new Map(), calls = [], timers = new Map();
  let timerId = 0;
  function node(id) {
    if (!nodes.has(id)) {
      const attributes = new Map();
      nodes.set(id, { id, value: id === 'sort' ? 'new' : '', checked: false,
        disabled: false, hidden: id === 'load-error', innerHTML: '',
        textContent: id === 'name' ? 'Scholar Gallery' : id === 'result-count' ? '正在读取文献…' : '',
        dataset: {}, listeners: {}, style: {},
        addEventListener(type, listener) { this.listeners[type] = listener; },
        querySelectorAll() { return []; },
        querySelector() { return node('nested'); },
        setAttribute(name, value) { attributes.set(name, String(value)); },
        getAttribute(name) { return attributes.has(name) ? attributes.get(name) : null; },
        removeAttribute(name) { attributes.delete(name); },
        insertAdjacentHTML() {}, click() { if (this.onclick) return this.onclick(); },
        classList: { add() {}, remove() {}, toggle() {} },
      });
    }
    return nodes.get(id);
  }
  const document = { baseURI: base, documentElement: node('documentElement'),
    getElementById: node, createElement: () => node('created'),
    querySelectorAll(selector) { return /toolbar/.test(selector) ? controls.map(node) : []; },
  };
  const context = vm.createContext({ document, URL, Blob, console,
    location: { hash }, history: { replaceState() {} },
    fetch(url, options) {
      const path = new URL(String(url), base).pathname.replace('/GCE-scholar/', '');
      calls.push(path);
      return Promise.resolve().then(() => route(path, options));
    },
    setTimeout(callback, delay) { const id = ++timerId; timers.set(id, { callback, delay }); return id; },
    clearTimeout(id) { timers.delete(id); },
  });
  context.window = context;
  if (abortController) context.AbortController = AbortController;
  vm.runInContext(readFileSync(join(__dirname, '../app.js'), 'utf8'), context);
  const run = code => vm.runInContext(code, context);
  return { run, node, calls, ready: run('startup'),
    expireRequests() {
      for (const [id, timer] of Array.from(timers)) {
        if (timer.delay >= 20000) { timers.delete(id); timer.callback(); }
      }
    },
  };
}
function assertReady(instance, name) {
  assert.equal(instance.node('name').textContent, name);
  assert.equal(instance.node('load-error').hidden, true);
  assert.equal(instance.node('documentElement').getAttribute('data-gallery-state'), 'ready');
  assert.doesNotMatch(instance.node('result-count').textContent, /正在读取/);
  for (const id of controls) assert.equal(instance.node(id).disabled, false, id);
}
function assertLoadError(instance) {
  assert.equal(instance.node('load-error').hidden, false);
  assert.ok(instance.node('load-error-message').textContent.trim());
  assert.equal(instance.node('retry-load').disabled, false);
  assert.doesNotMatch(instance.node('result-count').textContent, /正在读取/);
}

test('initial loading works without structuredClone and retains strict ORCID admission', async () => {
  const instance = app();
  assert.equal(instance.run('typeof structuredClone'), 'undefined');
  await instance.ready;
  assertReady(instance, 'Alpha Scholar');
  assert.equal(instance.run('entry.papers.length'), 1);
  assert.equal(instance.run('entry.papers[0].title'), 'Alpha paper');
});

test('a scholar deep link requests only its shard and never the complete catalog', async () => {
  const instance = app({ hash: '#beta' });
  await instance.ready;
  assertReady(instance, 'Beta Scholar');
  assert.deepEqual(instance.calls, ['scholars.json', 'data/catalog-index.json', 'data/scholars/beta.json']);
  assert.ok(!instance.calls.includes('data/catalog.json'));
});

test('HTTP failure stops the initial spinner, shows an error, and retry restores the scholar', async () => {
  let failures = 1;
  const instance = app({ route(path) {
    if (path === 'data/scholars/alpha.json' && failures-- > 0) return { ok: false, status: 404 };
    return normalResponse(path);
  } });
  await instance.ready;
  assertLoadError(instance);
  await instance.node('retry-load').onclick();
  await flush();
  assertReady(instance, 'Alpha Scholar');
});

test('invalid index JSON is visible and retry can restart the index request', async () => {
  let failures = 1;
  const instance = app({ route(path) {
    if (path === 'data/catalog-index.json' && failures-- > 0) {
      return { ok: true, status: 200, json: async () => { throw new SyntaxError('Invalid JSON'); } };
    }
    return normalResponse(path);
  } });
  await instance.ready;
  assertLoadError(instance);
  await instance.node('retry-load').onclick();
  await flush();
  assertReady(instance, 'Alpha Scholar');
  assert.equal(instance.calls.filter(path => path === 'data/catalog-index.json').length, 2);
});

test('a stalled request times out and retries even without AbortController', async () => {
  let failures = 1;
  const instance = app({ route(path) {
    if (path === 'data/scholars/alpha.json' && failures-- > 0) return new Promise(() => {});
    return normalResponse(path);
  } });
  await flush();
  assert.ok(instance.calls.includes('data/scholars/alpha.json'));
  assert.equal(instance.run('typeof AbortController'), 'undefined');
  instance.expireRequests();
  await instance.ready;
  assertLoadError(instance);
  await instance.node('retry-load').onclick();
  await flush();
  assertReady(instance, 'Alpha Scholar');
});

test('late responses from a previous scholar cannot overwrite a newer selection', async () => {
  const oldRequest = deferred();
  const instance = app({ route(path) {
    return path === 'data/scholars/alpha.json' ? oldRequest.promise : normalResponse(path);
  } });
  await flush();
  assert.ok(instance.calls.includes('data/scholars/alpha.json'));
  await instance.run("select('beta')");
  assertReady(instance, 'Beta Scholar');
  oldRequest.resolve(response(shards.alpha));
  await instance.ready;
  assertReady(instance, 'Beta Scholar');
  assert.equal(instance.run('entry.papers[0].title'), 'Beta paper');
});

test('render and export are harmless before the first dataset is ready', async () => {
  const roster = deferred();
  const instance = app({ route(path) { return path === 'scholars.json' ? roster.promise : normalResponse(path); } });
  for (const id of controls) assert.equal(instance.node(id).disabled, true, id);
  assert.doesNotThrow(() => instance.run('render()'));
  assert.doesNotThrow(() => instance.node('export').onclick());
  roster.resolve(response(scholars));
  await instance.ready;
  assertReady(instance, 'Alpha Scholar');
});
