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

test('timeline shows the forecast year and workload instead of hiding a later-year finish', async () => {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, { innerHTML: '', value: 'all' });
    return elements.get(id);
  };
  const data = {
    today: '2026-10-21',
    summary: { totalTopics: 1, inPipeline: 1, scheduledTopics: 1, weeklyStudyHours: 45,
      remainingLearningHours: 7.5, remainingFollowUpHours: 12, overallFinishDate: '2028-10-06', schedulingErrors: [] },
    estimates: { topic: { topicName: 'Economy', subjectName: 'GS', subjectColor: '#ffffff', roi: 'medium',
      status: 'not-started', startDate: '2028-08-01', completionDate: '2028-09-01', masteryDate: '2028-10-06', isEstimate: true } },
  };
  const context = vm.createContext({ document: { getElementById: element }, api: async () => data });
  const utilities = ['parseDate', 'daysBetween', 'formatDate', 'formatDateShort', 'roiBadgeClass', 'roiEmoji', 'schedulingWarnings'];
  vm.runInContext(utilities.map(name => extract(name)).join('\n') + '\n' + extract('renderTimeline', true), context);
  await vm.runInContext('renderTimeline()', context);
  assert.match(element('tl-stats').innerHTML, /2028/);
  assert.match(element('tl-overall').innerHTML, /45h\/week/);
  assert.match(element('tl-overall').innerHTML, /1\/1 topics forecast/);
  assert.match(element('tl-topic-list').innerHTML, /2028/);
});