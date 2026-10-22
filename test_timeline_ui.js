const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync('static/js/app.js', 'utf8').replace(/\r\n/g, '\n');
function extract(name, async = false) {
  const start = source.indexOf(`${async ? 'async ' : ''}function ${name}(`);
  assert.ok(start >= 0, name);
  return source.slice(start, source.indexOf('\n}\n', start) + 2);
}
const warnings = vm.runInNewContext(`${extract('schedulingWarnings')}\nschedulingWarnings`);

test('groups repeated forecast errors rather than printing a warning for every topic', () => {
  const html = warnings(Array.from({ length: 72 }, (_, index) => ({ topicId: `topic-${index}`, error: 'Forecast limit reached' })));
  assert.match(html, /72 topics/);
  assert.equal((html.match(/Forecast limit reached/g) || []).length, 1);
});

test('escapes errors and folds additional unique warning types', () => {
  const html = warnings(Array.from({ length: 7 }, (_, index) => ({ error: `<script>${index}</script>` })));
  assert.ok(!html.includes('<script>'));
  assert.match(html, /2 more warning types/);
  assert.match(html, /&lt;script&gt;6/);
});

test('empty warning input produces no alert', () => {
  assert.equal(warnings([]), '');
});

test('predictive estimator page and requests are removed', () => {
  const template = fs.readFileSync('templates/index.html', 'utf8');
  assert.ok(!template.includes('id="page-timeline"'));
  assert.ok(!template.includes('data-page="timeline"'));
  assert.ok(!source.includes('/api/timeline-estimate'));
  assert.ok(!source.includes('function renderTimeline('));
});

test('duration and priority remain blank until entered', () => {
  const values = vm.runInNewContext(`${extract('optionalTopicValues')}\noptionalTopicValues`);
  assert.equal(values('', '').estimatedHours, null);
  assert.equal(values('', '').roi, null);
  assert.equal(values('0.25', 'high').estimatedHours, .25);
  assert.throws(() => values('-1', ''), /Enter learning hours/);
  assert.ok(!extract('openAddTopic', true).includes('7.5'));
});

test('stopwatch uses persisted seconds plus active elapsed time, never estimates', () => {
  const elapsed = vm.runInNewContext(`${extract('learningElapsedSeconds')}\nlearningElapsedSeconds`);
  const started = '2026-10-21T00:00:00Z';
  assert.equal(elapsed({ learningSeconds: 90, timerStartedAt: started }, Date.parse(started) + 60000), 150);
  assert.equal(elapsed({ learningSeconds: 90, timerStartedAt: null }, Date.parse(started)), 90);
  assert.equal(elapsed({ estimatedHours: 7.5 }, Date.parse(started)), 0);
  const controls = vm.runInNewContext(`${extract('learningControlsMarkup')}\nlearningControlsMarkup`);
  assert.match(controls('subject', { id: 'topic', status: 'learning', timerStartedAt: started }), /Pause.*Finish/);
  assert.match(controls('subject', { id: 'topic', status: 'learning' }), /Resume.*Finish/);
});

test('failed related linking shows an error and retains selection for retry', async () => {
  const button = { disabled: false };
  const messages = [];
  const state = { subjectId: 'subject', topicId: 'topic', selectedId: 'related', candidates: [{ id: 'related', name: 'Related topic' }] };
  const context = vm.createContext({ document: { getElementById: () => button }, relatedSearchState: state,
    checkedApi: async () => { throw new Error('Link unavailable'); },
    relatedMessage: (...args) => messages.push(args), showToast: () => {}, showTopicDetail: async () => {} });
  vm.runInContext(extract('addRelated', true), context);
  await context.addRelated('subject', 'topic');
  assert.equal(messages[0][1], 'Link unavailable');
  assert.equal(messages[0][2], true);
  assert.equal(state.selectedId, 'related');
  assert.equal(button.disabled, false);
});

test('related search matches topic and subject words without a dropdown', () => {
  const match = vm.runInNewContext(`${extract('relatedMatches')}\nrelatedMatches`);
  const candidates = [{ id: 'a', name: 'Fiscal Policy', subjectName: 'Economy' }, { id: 'b', name: 'Policy Institutions', subjectName: 'Polity' }];
  assert.equal(match(candidates, 'ECONOMY fiscal')[0].id, 'a');
  assert.equal(match(candidates, 'unknown').length, 0);
  assert.match(source, /type="search" id="related-search-/);
  assert.match(extract('addRelated', true), /checkedApi[\s\S]*relatedMessage/);
});