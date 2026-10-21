'use strict';

const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { escape, localToday, request, resultText, evidenceCell, buildAttempt, buildRepair } = require('./static/js/preparation.js');

function fakeForm(values = {}, errors = []) {
  const fields = {
    kind: 'mcq', topicId: '', date: localToday(), minutes: '15', setType: 'unseen', notes: '',
    correct: '8', wrong: '2', unattempted: '0', marksPerQuestion: '2', penaltyFraction: '',
    reviewer: 'unreviewed', maxMarks: '10', score: '', skill: '', ...values
  };
  return {
    elements: { namedItem: name => ({ value: String(fields[name] ?? '') }) },
    querySelectorAll: () => errors.map(value => ({ value }))
  };
}

function preparationHarness(data) {
  const { runInNewContext } = require('node:vm');
  const nodes = new Map();
  const closedModals = [];
  function getNode(key) {
    if (!nodes.has(key)) {
      const node = {
        value: '', innerHTML: '', children: [], handlers: {},
        addEventListener(type, handler) { this.handlers[type] = handler; },
        setAttribute() {}, replaceChildren() { this.innerHTML = ''; },
        focus() { this.focused = true; },
        querySelector(selector) { return getNode(`${key} ${selector}`); },
        querySelectorAll() { return []; },
        elements: { namedItem: name => getNode(`${key} [name="${name}"]`) }
      };
      nodes.set(key, node);
    }
    return nodes.get(key);
  }
  const context = {
    document: { getElementById: getNode, querySelector: () => null, querySelectorAll: () => [] },
    fetch: async () => ({ ok: true, json: async () => data }),
    closeModal: name => closedModals.push(name)
  };
  runInNewContext(readFileSync(join(__dirname, 'static/js/preparation.js'), 'utf8'), context);
  return { context, getNode, closedModals };
}

function runTests() {
  const { test } = require('node:test');

  test('escapes text and both attribute quote styles', () => {
    assert.equal(escape('<img title="x" onerror=\'bad\'>&'), '&lt;img title=&quot;x&quot; onerror=&#39;bad&#39;&gt;&amp;');
    assert.equal(escape(null), '');
    assert.equal(escape(0), '0');
  });

  test('uses the existing local todayStr helper when present', () => {
    global.todayStr = () => '2026-10-21';
    try { assert.equal(localToday(), '2026-10-21'); } finally { delete global.todayStr; }
  });

  test('builds subject-level MCQ requests without replacing backend penalty defaults', () => {
    const body = buildAttempt(fakeForm({ notes: '  Diagnostic notes  ' }, ['concept', 'time']));
    assert.equal(body.topicId, null);
    assert.equal(body.notes, 'Diagnostic notes');
    assert.equal(body.minutes, 15);
    assert.equal(body.marksPerQuestion, 2);
    assert.equal(Object.hasOwn(body, 'penaltyFraction'), false);
    assert.deepEqual(body.errors, ['concept', 'time']);
  });

  test('allows a zero MCQ penalty and all-unattempted nonempty sets', () => {
    const body = buildAttempt(fakeForm({ penaltyFraction: '0', correct: '0', wrong: '0', unattempted: '20' }));
    assert.equal(body.penaltyFraction, 0);
    assert.equal(body.unattempted, 20);
  });

  test('unreviewed writing always sends null score and no hidden question counts', () => {
    const body = buildAttempt(fakeForm({ kind: 'writing', score: '8' }));
    assert.equal(body.score, null);
    assert.equal(body.reviewer, 'unreviewed');
    assert.equal(Object.hasOwn(body, 'correct'), false);
    assert.equal(Object.hasOwn(body, 'marksPerQuestion'), false);
  });

  test('reviewed writing preserves awarded zero and rejects missing or excessive marks', () => {
    const body = buildAttempt(fakeForm({ kind: 'writing', reviewer: 'external', score: '0' }));
    assert.equal(body.score, 0);
    assert.throws(() => buildAttempt(fakeForm({ kind: 'writing', reviewer: 'self' })), /numeric fields/);
    assert.throws(() => buildAttempt(fakeForm({ kind: 'writing', reviewer: 'external', score: '11' })), /maximum marks/);
  });

  test('recall excludes hidden marking fields and skill requires a nonblank name', () => {
    const recall = buildAttempt(fakeForm({ kind: 'recall', topicId: 'topic1' }));
    assert.equal(recall.topicId, 'topic1');
    assert.equal(Object.hasOwn(recall, 'penaltyFraction'), false);
    assert.throws(() => buildAttempt(fakeForm({ kind: 'skill', skill: '  ' })), /Name the subject skill/);
    assert.equal(buildAttempt(fakeForm({ kind: 'skill', skill: ' Blank-map recall ' })).skill, 'Blank-map recall');
  });

  test('rejects empty counts, fractional counts, invalid numbers, and future dates', () => {
    assert.throws(() => buildAttempt(fakeForm({ correct: '0', wrong: '0' })), /at least one/);
    assert.throws(() => buildAttempt(fakeForm({ correct: '1.5' })), /integers/);
    assert.throws(() => buildAttempt(fakeForm({ minutes: 'NaN' })), /numeric fields/);
    assert.throws(() => buildAttempt(fakeForm({ date: '9999-12-31' })), /no later than today/);
  });

  test('repair resolution requires both correction and retest outcome', () => {
    assert.throws(() => buildRepair(fakeForm({ correction: 'Fixed notes', retestOutcome: '' })), /both/);
    assert.throws(() => buildRepair(fakeForm({ correction: '  ', retestOutcome: '4/5 correct' })), /both/);
    assert.deepEqual(buildRepair(fakeForm({ correction: ' Fixed the mechanism ', retestOutcome: ' 4/5 correct after two days ' })), {
      resolution: 'Correction: Fixed the mechanism\nRetest outcome: 4/5 correct after two days'
    });
  });

  test('repair resolution fits the API limit without silently truncating the retest', () => {
    const body = buildRepair(fakeForm({ correction: 'a'.repeat(980), retestOutcome: 'b'.repeat(980) }));
    assert.ok(body.resolution.length <= 2000);
    assert.throws(() => buildRepair(fakeForm({ correction: 'a'.repeat(2000), retestOutcome: 'Retested' })), /2000 characters/);
  });

  test('displays recorded results without inventing marks or treating absent marks as zero', () => {
    assert.equal(resultText({ kind: 'writing', score: null, maxMarks: 10 }), 'Unreviewed');
    assert.equal(resultText({ kind: 'writing', score: 0, maxMarks: 10, reviewer: 'external' }), '0 / 10 marks (external)');
    assert.equal(resultText({ kind: 'recall', retrievalPercent: 0, accuracy: 90 }), '0% retrieved');
    assert.equal(resultText({ kind: 'mcq', netMarks: -2, accuracy: 0 }), '-2 net marks | 0% accuracy');
    assert.equal(resultText({ kind: 'skill' }), 'Recorded');
  });

  test('preserves every backend evidence distinction and escapes unknown statuses', () => {
    for (const status of ['not-assessed', 'diagnostic-only', 'early-recall', 'on-target', 'stale', 'self-assessed', 'small-sample', 'needs-practice', 'recorded']) {
      const markup = evidenceCell({ status, attempts: 0 });
      assert.match(markup, /0 checks/);
      assert.equal(markup.includes('undefined'), false);
    }
    assert.match(evidenceCell(), /Not assessed/);
    assert.match(evidenceCell({ status: '<script>bad</script>' }), /&lt;script&gt;/);
    assert.equal(evidenceCell({ status: 'on-target' }).includes('data-tone="positive"'), true);
  });

  test('checked request sends JSON and rejects HTTP, JSON, and backend errors', async () => {
    const originalFetch = global.fetch;
    try {
      global.fetch = async (url, options) => {
        assert.equal(url, '/fixture');
        assert.equal(options.credentials, 'same-origin');
        assert.deepEqual(JSON.parse(options.body), { resolution: 'Retested' });
        return { ok: true, status: 200, json: async () => ({ ok: true }) };
      };
      assert.deepEqual(await request('/fixture', 'PUT', { resolution: 'Retested' }), { ok: true });
      global.fetch = async () => ({ ok: false, status: 400, json: async () => ({ error: 'Prerequisites cannot contain a cycle' }) });
      await assert.rejects(request('/fixture'), /cannot contain a cycle/);
      global.fetch = async () => ({ ok: false, status: 503, json: async () => ({}) });
      await assert.rejects(request('/fixture'), /503/);
      global.fetch = async () => ({ ok: true, status: 200, json: async () => ({ error: 'Application failure' }) });
      await assert.rejects(request('/fixture'), /Application failure/);
      global.fetch = async () => ({ ok: true, status: 200, json: async () => { throw new Error('Invalid JSON'); } });
      await assert.rejects(request('/fixture'), /unreadable response/);
      global.fetch = async () => ({ ok: false, status: 401, json: async () => { throw new Error('HTML login page'); } });
      await assert.rejects(request('/fixture'), /Refresh your session/);
    } finally { global.fetch = originalFetch; }
  });

  test('template owns one nav/page and loads preparation after shared script with cache busting', () => {
    const template = readFileSync(join(__dirname, 'templates/index.html'), 'utf8');
    assert.equal((template.match(/data-page="preparation"/g) || []).length, 1);
    assert.equal((template.match(/id="page-preparation"/g) || []).length, 1);
    assert.ok(template.indexOf('src="/static/js/preparation.js') > template.indexOf('src="/static/js/app.js'));
    assert.match(template, /preparation\.css\?v=\{\{ cache_bust \}\}/);
    assert.match(template, /preparation\.js\?v=\{\{ cache_bust \}\}/);
  });

  test('public navigation clears stale history scope, closes the modal, and focuses the page', async () => {
    const data = fixtureData();
    data.subjects[1].attempts.push({ id: 'polity-check', kind: 'recall', date: localToday(), topicId: 'constitution', notes: 'New subject assessment', errors: [] });
    const { context, getNode, closedModals } = preparationHarness(data);
    await context.renderPreparation('economy');
    getNode('prep-history-topic').handlers.change({ target: { value: 'inflation' } });
    await context.openPreparation('polity', 'constitution');
    assert.match(getNode('prep-history-records').innerHTML, /polity-check/);
    assert.match(getNode('preparation-content').innerHTML, /<option value="\*" selected>All scopes/);
    assert.deepEqual(closedModals, ['topic-detail']);
    assert.equal(getNode('preparation-title').focused, true);
  });

  test('overlapping renders coalesce the GET and honor the latest subject and topic', async () => {
    const data = fixtureData();
    const { context, getNode } = preparationHarness(data);
    let release;
    let requests = 0;
    context.fetch = async () => {
      requests += 1;
      await new Promise(resolve => { release = resolve; });
      return { ok: true, json: async () => data };
    };
    const first = context.renderPreparation('economy', 'inflation');
    const second = context.renderPreparation('polity', 'constitution');
    release();
    await Promise.all([first, second]);
    assert.equal(requests, 1);
    assert.match(getNode('preparation-content').innerHTML, /<option value="polity" selected>/);
    assert.match(getNode('preparation-content').innerHTML, /<option value="constitution" selected>/);
  });
}

function fixtureData() {
  const date = localToday();
  const attempt = (id, kind, extras = {}) => ({
    id, subjectId: 'economy', topicId: 'inflation', date, kind, minutes: 20, setType: 'unseen',
    correct: 16, wrong: 4, unattempted: 0, accuracy: 80, retrievalPercent: 80,
    notes: 'A recorded test fixture, not tracker data.', errors: [], ...extras
  });
  const mcq = attempt('attempt-mcq', 'mcq', { netMarks: 29.33, errors: ['concept'] });
  const writing = attempt('attempt-writing', 'writing', { reviewer: 'self', score: 6, maxMarks: 10 });
  const recall = attempt('attempt-recall', 'recall');
  return {
    profiles: {
      general: { name: 'General GS', outputs: ['Concept recall', 'Question application'] },
      economy: { name: 'Economy', outputs: ['Mechanism explanation', 'Policy application'] },
      polity: { name: 'Polity and Governance', outputs: ['Rules and exceptions', 'Institutional comparison'] }
    },
    policy: { mcqAccuracy: 70, recallAccuracy: 70, writingPercent: 50, minMcqQuestions: 20, minRecallItems: 5, delayedRecallDays: 7, freshDays: 21 },
    errorTypes: ['concept', 'fact', 'application', 'elimination', 'time', 'structure', 'evidence', 'map', 'chronology'],
    repairs: [{ id: 'repair1', subjectId: 'economy', topicId: 'inflation', attemptId: mcq.id, category: 'concept', status: 'open', dueDate: date }],
    subjects: [{
      id: 'economy', name: 'Economy',
      strategy: { profile: 'economy', stagePreset: 'standard', resources: [{ tier: 'spine', title: 'Economy notes', scope: 'Inflation, chapters 1-2', reason: '' }], syllabus: [{ title: 'Inflation and growth', topicIds: ['inflation'] }], syllabusVerified: false },
      coverage: { total: 1, covered: 0, verified: false },
      topics: [{ id: 'inflation', name: 'Inflation & monetary policy', prerequisiteIds: [], evidence: { attempts: 3, openRepairs: 1, dimensions: { mcq: { status: 'on-target', attempts: 1, latest: mcq }, writing: { status: 'self-assessed', attempts: 1, latest: writing }, recall: { status: 'early-recall', attempts: 1, latest: recall }, skill: { status: 'not-assessed', attempts: 0, latest: null } } } },
        { id: 'fiscal', name: 'Fiscal policy <img src=x onerror="globalThis.prepXss=true">', evidence: { attempts: 2, openRepairs: 0, dimensions: { mcq: { status: 'diagnostic-only', attempts: 1 }, writing: { status: 'stale', attempts: 1 }, recall: { status: 'small-sample', attempts: 1 }, skill: { status: 'recorded', attempts: 1 } } } }],
      attempts: [mcq, writing, recall, attempt('subject-writing', 'writing', { topicId: null, reviewer: 'unreviewed', score: null, maxMarks: 10, notes: '<script>globalThis.prepXss=true</script>' })]
    }, { id: 'polity', name: 'Polity', strategy: { profile: 'polity', stagePreset: 'compact' }, coverage: { total: 0, covered: 0, verified: false }, topics: [{ id: 'constitution', name: 'Constitutional principles' }], attempts: [] }]
  };
}

function serveFixture() {
  const http = require('node:http');
  let data = fixtureData();
  let nextId = 1;
  const requests = [];
  const bootstrap = `
    function todayStr() { const date = new Date(); return date.getFullYear() + '-' + String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0'); }
    function showToast(message) { document.getElementById('toast-container').textContent = message; }
    function closeModal(name) { document.getElementById('modal-' + name)?.classList.remove('show'); }
    function showTopicDetail(subjectId, topicId) { globalThis.fixtureDetail = { subjectId, topicId }; document.getElementById('detail-title').textContent = topicId; document.getElementById('modal-topic-detail').classList.add('show'); }
    function renderPage(page) { if (page === 'preparation') return renderPreparation(); }
    document.querySelectorAll('.nav-item').forEach(button => button.addEventListener('click', () => {
      document.querySelectorAll('.nav-item').forEach(item => item.classList.toggle('active', item === button));
      document.querySelectorAll('.page').forEach(item => item.classList.toggle('active', item.id === 'page-' + button.dataset.page));
      renderPage(button.dataset.page);
    }));
  `;
  const files = new Map([
    ['/static/css/style.css', ['static/css/style.css', 'text/css']],
    ['/static/css/preparation.css', ['static/css/preparation.css', 'text/css']],
    ['/static/js/preparation.js', ['static/js/preparation.js', 'text/javascript']],
    ['/static/images/ashoka-emblem.webp', ['static/images/ashoka-emblem.webp', 'image/webp']],
    ['/static/manifest.json', ['static/manifest.json', 'application/json']]
  ]);
  const server = http.createServer(async (incoming, outgoing) => {
    const pathname = new URL(incoming.url, 'http://localhost').pathname;
    const json = (value, status = 200) => { outgoing.writeHead(status, { 'Content-Type': 'application/json' }); outgoing.end(JSON.stringify(value)); };
    try {
      if (pathname === '/') {
        outgoing.writeHead(200, { 'Content-Type': 'text/html' });
        outgoing.end(readFileSync(join(__dirname, 'templates/index.html'), 'utf8').replaceAll('{{ cache_bust }}', 'fixture'));
        return;
      }
      if (pathname === '/static/js/app.js' || pathname === '/static/sw.js' || pathname === '/sw.js') {
        outgoing.writeHead(200, { 'Content-Type': 'text/javascript' });
        outgoing.end(pathname.endsWith('app.js') ? bootstrap : '');
        return;
      }
      if (files.has(pathname)) {
        const [filename, contentType] = files.get(pathname);
        outgoing.writeHead(200, { 'Content-Type': contentType });
        outgoing.end(readFileSync(join(__dirname, filename)));
        return;
      }
      if (pathname === '/fixture/state') { json({ data, requests }); return; }
      if (pathname === '/fixture/reset') { data = fixtureData(); requests.length = 0; json({ ok: true }); return; }
      if (incoming.method === 'GET' && pathname === '/api/preparation') {
        requests.push({ method: 'GET', pathname });
        json(data);
        return;
      }
      let raw = '';
      for await (const chunk of incoming) raw += chunk;
      const body = raw ? JSON.parse(raw) : {};
      requests.push({ method: incoming.method, pathname, body });
      const parts = pathname.split('/').filter(Boolean).map(decodeURIComponent);
      if (parts[0] !== 'api') { json({ error: 'Fixture route not found' }, 404); return; }
      if (parts[1] === 'subjects') {
        const subject = data.subjects.find(entry => entry.id === parts[2]);
        if (!subject) { json({ error: 'Subject not found' }, 404); return; }
        if (parts[3] === 'strategy' && incoming.method === 'PUT') {
          subject.strategy = body;
          subject.coverage = { total: body.syllabus.length, covered: 0, verified: body.syllabusVerified };
        } else if (parts[3] === 'topics' && incoming.method === 'PUT') {
          Object.assign(subject.topics.find(topic => topic.id === parts[4]), body);
        } else if (parts[3] === 'attempts' && incoming.method === 'POST') {
          const record = { ...body, id: `fixture-${nextId++}`, subjectId: subject.id };
          if (body.kind !== 'writing') {
            record.total = body.correct + body.wrong + body.unattempted;
            record.accuracy = body.correct + body.wrong ? Math.round(1000 * body.correct / (body.correct + body.wrong)) / 10 : 0;
            record.retrievalPercent = Math.round(1000 * body.correct / record.total) / 10;
            if (body.kind === 'mcq') record.netMarks = Math.round(100 * body.marksPerQuestion * (body.correct - body.wrong * (body.penaltyFraction ?? 1 / 3))) / 100;
          }
          subject.attempts.push(record);
          for (const category of body.errors) data.repairs.push({ id: `repair-${nextId++}`, subjectId: subject.id, topicId: body.topicId, attemptId: record.id, category, status: 'open', dueDate: localToday() });
          json(record, 201);
          return;
        } else { json({ error: 'Fixture route not found' }, 404); return; }
      } else if (parts[1] === 'preparation' && parts[2] === 'policy') {
        data.policy = body;
      } else if (parts[1] === 'preparation' && parts[2] === 'repairs') {
        Object.assign(data.repairs.find(repair => repair.id === parts[3]), { status: 'resolved', resolution: body.resolution });
      } else if (parts[1] === 'preparation' && parts[2] === 'attempts') {
        for (const subject of data.subjects) subject.attempts = subject.attempts.filter(attempt => attempt.id !== parts[3]);
        for (const repair of data.repairs) if (repair.attemptId === parts[3] && repair.status === 'open') repair.status = 'cancelled';
      } else { json({ error: 'Fixture route not found' }, 404); return; }
      json({ ok: true });
    } catch (error) { json({ error: error.message }, 500); }
  });
  server.listen(0, '127.0.0.1', () => process.stdout.write(`Preparation fixture (memory only): http://127.0.0.1:${server.address().port}\n`));
}

if (process.argv.includes('--serve')) serveFixture();
else runTests();