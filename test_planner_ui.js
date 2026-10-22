const assert = require('node:assert/strict');
const test = process.argv.includes('--serve') ? () => {} : require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const planner = require('./static/js/planner.js');

function config() {
  return { mode: 'two-stream', attemptYear: 2028, phase: 'auto', prelimsFocusDays: 112, weekendConsolidation: true,
    gsSubjectOrder: [], optionalSubjectOrder: [], allocations: {
      integrated: { gs: 40, optional: 26.67, recall: 15.56, practice: 11.11, currentAffairs: 6.66 },
      prelims: { gs: 35, optional: 5, recall: 25, practice: 30, currentAffairs: 5 },
      mains: { gs: 10, optional: 10, recall: 20, practice: 55, currentAffairs: 5 },
    } };
}

test('validates every phase total and positive allocations for both learning streams', () => {
  assert.deepEqual(planner.validatePlannerConfig(config()), []);
  const invalid = config();
  invalid.allocations.prelims.optional = 0;
  assert.match(planner.validatePlannerConfig(invalid).join(' '), /prelims: allocation must total 100%/);
  assert.match(planner.validatePlannerConfig(invalid).join(' '), /both learning streams/);
  invalid.allocations.mains.practice = NaN;
  assert.match(planner.validatePlannerConfig(invalid).join(' '), /percentages must be numbers/);
});

test('validates phase, year, focus window, boolean and subject queues', () => {
  const invalid = { ...config(), phase: 'other', attemptYear: 2028.5, prelimsFocusDays: 0, weekendConsolidation: 'true', gsSubjectOrder: ['a', 'a'] };
  assert.equal(planner.validatePlannerConfig(invalid).length, 5);
});

test('explicit classification wins; mains-only Essay remains GS', () => {
  assert.equal(planner.plannerStream({ name: 'Sociology', studyStream: 'gs' }), 'gs');
  assert.equal(planner.plannerStream({ name: 'Other', stream: 'optional' }), 'optional');
  assert.equal(planner.plannerStream({ strategy: { profile: 'sociology1' } }), 'optional');
  assert.equal(planner.plannerStream({ strategy: { profile: 'sociology2' } }), 'optional');
  assert.equal(planner.plannerStream({ name: 'Sociology Paper II' }), 'optional');
  assert.equal(planner.plannerStream({ name: 'Optional Paper 1' }), 'optional');
  assert.equal(planner.plannerStream({ name: 'Essay', examType: 'mains' }), 'gs');
});

test('recall guard validation matches backend bounds and can be disabled', () => {
  assert.deepEqual(planner.validatePlannerConfig({ ...config(), recallGuardDays: 0 }), []);
  assert.match(planner.validatePlannerConfig({ ...config(), recallGuardDays: 91 }).join(' '), /Recall backlog guard/);
});

test('stage time logging is distinct from whole-activity completion', () => {
  const markup = planner.plannerStageControl({ topicId: 'topic', type: 'R1', canMark: true, isProjected: false });
  assert.match(markup, /data-planner-action="stage-log"/);
  assert.match(markup, /Session hours today/);
  assert.match(markup, /data-planner-action="stage"/);
});

test('time labels distinguish measured, estimated used, and remaining planned hours', () => {
  const markup = planner.plannerBudgetLabel({ totalHours: 5, plannedHours: 2, actualHours: 1, estimatedSpentHours: 2 });
  assert.match(markup, /Remaining planned: 2h/);
  assert.match(markup, /Logged: 1h/);
  assert.match(markup, /Estimated time used: 2h/);
});

test('started topics do not block switching learning sessions', () => {
  const gs = { id: 'gs', name: 'Polity', topics: [{ status: 'learning' }] };
  const optional = { id: 'optional', name: 'Sociology', topics: [] };
  assert.equal(planner.plannerCanStart(gs, [gs, optional]), true);
  assert.equal(planner.plannerCanStart(optional, [gs, optional]), true);
  optional.learningTopics = 1;
  assert.equal(planner.plannerCanStart(optional, [gs, optional]), true);
});

test('subject queues follow configured order within the assigned stream', () => {
  const subjects = [{ id: 'a', name: 'Essay' }, { id: 'b', name: 'Polity' }, { id: 'c', name: 'Sociology' }];
  assert.deepEqual(planner.plannerQueue(subjects, { gsSubjectOrder: ['b', 'a'] }, 'gs').map(subject => subject.id), ['b', 'a']);
  assert.equal(planner.plannerEscape('<script>"&'), '&lt;script&gt;&quot;&amp;');
});

test('unknown and invalid dates remain unscheduled, and forecast dates include years', () => {
  for (const date of [null, '', 'unknown', '2028-02-31']) assert.equal(planner.plannerDate(date), 'Not scheduled');
  assert.match(planner.plannerDate('2028-10-21'), /2028/);
  const html = planner.renderPlannerMilestones({ streams: { gs: { coverageDate: '2028-03-01', pipelineDate: '2029-02-01', totalTopics: 211 } },
    milestones: { prelims: { deadline: '2028-05-01', lateTopics: [{ topicName: '<unsafe>', subjectName: 'Polity' }], unscheduledTopics: [{ topicName: 'Budget' }] } } });
  assert.match(html, /First-pass coverage/);
  assert.match(html, /Full activity pipeline/);
  assert.match(html, /2029/);
  assert.match(html, /Optional stream/);
  assert.match(html, /Not scheduled/);
  assert.match(html, /Prelims-scoped activities/);
  assert.match(html, /1 late topics/);
  assert.match(html, /1 unscheduled topics/);
  assert.ok(!html.includes('<unsafe>'));
});

test('provisional forecasts warn about default estimates without claiming readiness', () => {
  assert.equal(planner.plannerProvisionalWarning({ provisionalTopics: 0 }), '');
  assert.match(planner.plannerProvisionalWarning({ provisionalTopics: 211 }), /211 topic\(s\) use default estimates/);
});

test('learning lanes show started work, stopwatch actions and no speculative starts', () => {
  const html = planner.renderPlannerLearning({ learningTopics: [{ id: 'gs', subjectName: 'Polity', stream: 'gs', timerStartedAt: '2026-10-21T00:00:00Z' }], learningPlan: [
    { topicId: 'gs', topicName: 'Rights', subjectName: 'Polity', stream: 'gs', hours: 2, remaining: null, isSuggested: false },
    { topicId: 'opt', topicName: '<Sociology>', subjectName: 'Sociology', stream: 'optional', hours: 1.5, isSuggested: true },
  ] });
  assert.match(html, /GS planned learning/);
  assert.match(html, /Optional planned learning/);
  assert.match(html, /2h planned/);
  assert.equal((html.match(/data-planner-action="log"/g) || []).length, 1);
  assert.match(html, /data-planner-action="pause"/);
  assert.match(html, /Finish/);
  assert.ok(!html.includes('Suggested'));
  assert.ok(!html.includes('Sociology'));
  const history = planner.renderPlannerLearning({ learningPlan: [{ topicId: 'done', stream: 'gs', hours: 1, actualHours: 1, plannedHours: 0, topicStatus: 'completed', isSuggested: false }] });
  assert.match(history, /1h logged/);
  assert.match(history, /Learning complete/);
  assert.ok(!history.includes('data-planner-action="start"'));
  assert.ok(!history.includes('data-planner-action="log"'));
  const calendar = planner.renderPlannerLearning({ learningPlan: [{ topicId: 'active', stream: 'gs', hours: 1, isSuggested: false }] }, { allowLog: false });
  assert.match(calendar, /In progress/);
  assert.ok(!calendar.includes('data-planner-action="start"'));
});

test('forecast stages never get completion controls; real controls refer to the full activity', () => {
  for (const task of [{ isProjected: true, canMark: true }, { canMark: false }, { status: 'learning' }, { topicStatus: 'not-started' }]) {
    assert.equal(planner.plannerStageCanMark(task), false);
    assert.ok(!planner.plannerStageControl(task).includes('data-planner-action="stage"'));
  }
  assert.match(planner.plannerStageControl({ type: 'R1', canMark: true, hours: 0.5 }), /Mark entire R1 activity done \(all sessions\)/);
    assert.match(planner.plannerBudgetLabel({ totalHours: 4, loggedHours: 0, phase: 'integrated' }), /Remaining planned: 4h.*Logged: 0h/);
});

function appFunction(name, asynchronous = false) {
  const source = fs.readFileSync(path.join(__dirname, 'static/js/app.js'), 'utf8').replace(/\r\n/g, '\n');
  const start = source.indexOf(`${asynchronous ? 'async ' : ''}function ${name}(`);
  assert.ok(start >= 0, name);
  return source.slice(start, source.indexOf('\n}\n', start) + 2);
}

test('Subjects uses canonical classifications and permits explicit starts without estimates', async () => {
  const subjects = [{ id: 'gs', name: 'Polity', roi: 'high', topics: [{ id: 'active', name: 'Rights', roi: 'high', status: 'learning' }, { id: 'queued', name: 'Parliament', roi: 'high', status: 'not-started' }] },
    { id: 'opt', name: 'Renamed paper', roi: 'high', topics: [{ id: 'next', name: 'Thinkers', roi: 'high', status: 'not-started' }] }];
  const nodes = new Map();
  const element = id => { if (!nodes.has(id)) nodes.set(id, { innerHTML: '', textContent: '' }); return nodes.get(id); };
  const context = vm.createContext({ document: { getElementById: element }, api: async url => url === '/api/data' ? { subjects } : url === '/api/planner' ? {
    config: config(), subjects: [{ id: 'gs', stream: 'gs', learningTopics: 1 }, { id: 'opt', stream: 'optional', learningTopics: 0 }]
  } : { estimates: {}, summary: {} } });
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'static/js/planner.js'), 'utf8'), context);
  vm.runInContext(['roiBadgeClass', 'roiEmoji', 'topicRoiBadge', 'loggedLearningHours', 'learningElapsedSeconds', 'formatLearningTime', 'learningTimerMarkup', 'learningControlsMarkup'].map(name => appFunction(name)).join('\n') + '\n' + appFunction('renderSubjects', true), context);
  await context.renderSubjects();
  assert.match(element('subjects-list').innerHTML, /planner-stream-optional/);
  assert.match(element('subjects-list').innerHTML, /startLearning\('opt','next'\)/);
  assert.match(element('subjects-list').innerHTML, /startLearning\('gs','queued'\)/);
  assert.ok(!element('subjects-list').innerHTML.includes('stream is busy'));
  assert.match(element('subjects-list').innerHTML, /Actual learning/);
  assert.equal(element('target-attempt').textContent, 'Target: UPSC 2028');
});

test('template wires one bounded planner section and loads planner before the app', () => {
  const source = fs.readFileSync(path.join(__dirname, 'templates/index.html'), 'utf8');
  assert.equal((source.match(/id="planner-settings"/g) || []).length, 1);
  assert.equal((source.match(/id="target-attempt"/g) || []).length, 1);
  assert.ok(source.indexOf('src="/static/js/planner.js') < source.indexOf('src="/static/js/app.js'));
  assert.match(source, /planner\.css\?v=\{\{ cache_bust \}\}/);
  assert.ok(!source.includes('Target: UPSC 2027'));
});

test('validation is safe when a failed refresh replaces the settings form with Retry', () => {
  const context = vm.createContext({ document: { getElementById: () => ({ querySelector: () => null }) } });
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'static/js/planner.js'), 'utf8'), context);
  assert.doesNotThrow(() => context.refreshPlannerValidation());
});

function fixtureData() {
  const topic = (id, name, status = 'not-started') => ({ id, name, status, roi: 'high', estimatedHours: 7.5, notes: '', examType: 'both', links: [], startDate: status === 'learning' ? '2026-10-20' : null });
  const subjects = [
    { id: 'polity', name: 'Polity', studyStream: 'gs', color: '#d4af37', roi: 'high', topics: [topic('gs-active', 'Fundamental rights', 'learning'), topic('gs-next', 'Parliament'), topic('review', 'Constitution', 'completed')] },
    { id: 'essay', name: 'Essay', studyStream: 'gs', color: '#f2d272', roi: 'medium', topics: [topic('essay-next', 'Argument and structure')] },
    { id: 'sociology1', name: 'Sociology Paper 1', studyStream: 'optional', color: '#22d3ee', roi: 'high', topics: [topic('opt-next', 'Sociological thinkers')] },
    { id: 'sociology2', name: 'Sociology Paper 2', studyStream: 'optional', color: '#2dd4bf', roi: 'high', topics: [topic('opt-second', 'Indian social structure')] },
  ];
  return { config: { ...config(), gsSubjectOrder: ['polity', 'essay'], optionalSubjectOrder: ['sociology1', 'sociology2'] }, subjects,
    settings: { weekdayHours: 6, weekendHours: 12, revisionMins: 60, weekendRevHrs: 3, intervals: { r1: 1, r3: 5, r7: 14, r30: 35 }, activityHours: { R1: 1.5, R7: 1.5, PYQ: 1 }, examDates: {} }, logs: [], requests: [] };
}

function createPlannerFixtureServer() {
  const http = require('node:http');
  let state = fixtureData();
  const today = '2026-10-21';
  const assets = new Map([
    ['/static/js/app.js', 'text/javascript'], ['/static/js/planner.js', 'text/javascript'], ['/static/js/preparation.js', 'text/javascript'],
    ['/static/css/style.css', 'text/css'], ['/static/css/planner.css', 'text/css'], ['/static/css/preparation.css', 'text/css'],
    ['/static/images/ashoka-emblem.webp', 'image/webp'], ['/static/manifest.json', 'application/json'],
  ]);
  const flatTopics = () => state.subjects.flatMap(subject => subject.topics.map(topic => ({ ...topic, subjectId: subject.id, subjectName: subject.name, subjectColor: subject.color, stream: subject.studyStream })));
  const learningPlan = () => ['gs', 'optional'].flatMap(stream => {
    const ordered = state.config[stream === 'gs' ? 'gsSubjectOrder' : 'optionalSubjectOrder'];
    const topics = flatTopics().filter(topic => topic.stream === stream);
    const current = topics.find(topic => topic.status === 'learning') || topics.filter(topic => topic.status === 'not-started').sort((first, second) => ordered.indexOf(first.subjectId) - ordered.indexOf(second.subjectId))[0];
    return current ? [{ topicId: current.id, topicName: current.name, subjectId: current.subjectId, subjectName: current.subjectName, stream, hours: stream === 'gs' ? 2.4 : 1.6, remaining: 5, isSuggested: current.status !== 'learning' }] : [];
  });
  const tasks = () => [
    { topicId: 'review', topicName: 'Constitution', subjectId: 'polity', subjectName: 'Polity', subjectColor: '#d4af37', type: 'R1', label: '1st Revision', hours: 0.5, activityHours: 1.5, canMark: true, isProjected: false, done: false, date: today },
    { topicId: 'gs-next', topicName: 'Parliament (forecast)', subjectId: 'polity', subjectName: 'Polity', subjectColor: '#d4af37', type: 'PYQ', label: 'PYQ Practice', hours: 0.75, canMark: false, isProjected: true, done: false, date: today },
  ];
  const budget = () => ({ budget: 6, totalHours: 6, remaining: 0, utilization: 100, overloaded: false, revisionHours: 1.25, learningHours: 4, cumulativeHours: 0, loggedHours: state.logs.reduce((sum, log) => sum + log.hours, 0), phase: 'integrated', streams: { gs: 2.4, optional: 1.6 },
    activities: [{ category: 'reserve', label: 'Current affairs and repair reserve', hours: 0.75 }, ...learningPlan().map(item => ({ ...item, category: 'learning' }))] });
  const timeline = () => ({ today, summary: { totalTopics: 211, inPipeline: 211, notStarted: 209, learning: 1, scheduledTopics: 139, weeklyStudyHours: 54, remainingLearningHours: 1582.5, remainingFollowUpHours: 900,
    overallFinishDate: null, provisionalTopics: 211, attemptYear: state.config.attemptYear, phase: 'integrated', plannerConfig: state.config,
    streams: { gs: { coverageDate: '2028-03-01', pipelineDate: null, totalTopics: 147 }, optional: { coverageDate: '2028-04-15', pipelineDate: '2028-09-20', totalTopics: 64 } },
    milestones: { prelims: { finishDate: null, deadline: '2028-05-15', lateTopics: [{ topicId: 'gs-next', topicName: 'Parliament', subjectName: 'Polity' }], unscheduledTopics: [{ topicId: 'essay-next', topicName: 'Argument and structure', subjectName: 'Essay' }] }, mains: { finishDate: '2028-09-20', deadline: '2028-09-01', lateTopics: [], unscheduledTopics: [] } },
    schedulingErrors: Array.from({ length: 72 }, (_, index) => ({ topicId: `limit-${index}`, error: '400-day forecast limit reached' })) },
    estimates: Object.fromEntries(flatTopics().map((topic, index) => [topic.id, { topicName: topic.name, subjectName: topic.subjectName, subjectColor: topic.subjectColor, stream: topic.stream, roi: topic.roi, status: topic.status, startDate: today,
      completionDate: '2028-03-01', masteryDate: index === 1 ? null : '2028-09-20', prelimsFinishDate: topic.stream === 'gs' ? '2028-05-01' : null, mainsFinishDate: '2028-09-20', isEstimate: true, queuePosition: index + 1 }])) });
  const server = http.createServer(async (incoming, outgoing) => {
    const pathname = new URL(incoming.url, 'http://127.0.0.1').pathname;
    const json = (value, status = 200) => { outgoing.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); outgoing.end(JSON.stringify(value)); };
    try {
      if (pathname === '/') {
        outgoing.writeHead(200, { 'Content-Type': 'text/html', 'Cache-Control': 'no-store' });
        outgoing.end(fs.readFileSync(path.join(__dirname, 'templates/index.html'), 'utf8').replaceAll('{{ cache_bust }}', 'planner-fixture'));
        return;
      }
      if (pathname.endsWith('/sw.js')) { outgoing.writeHead(200, { 'Content-Type': 'text/javascript' }); outgoing.end(''); return; }
      if (assets.has(pathname)) {
        outgoing.writeHead(200, { 'Content-Type': assets.get(pathname), 'Cache-Control': 'no-store' });
        outgoing.end(fs.readFileSync(path.join(__dirname, pathname.slice(1))));
        return;
      }
      let raw = '';
      for await (const chunk of incoming) raw += chunk;
      const body = raw ? JSON.parse(raw) : {};
      if (pathname === '/fixture/state') { json(state); return; }
      if (pathname === '/fixture/reset') { state = fixtureData(); json({ ok: true }); return; }
      if (pathname === '/fixture/stop' && incoming.method === 'POST') { json({ ok: true }); server.close(); return; }
      state.requests.push({ method: incoming.method, pathname, body });
      if (pathname === '/api/planner') {
        if (incoming.method === 'PUT') {
          const errors = planner.validatePlannerConfig(body.config);
          const streams = body.subjectStreams || {};
          if (Object.entries(streams).some(([id, stream]) => !state.subjects.some(subject => subject.id === id) || !['gs', 'optional'].includes(stream))) errors.push('Invalid subject stream.');
          if (errors.length) { json({ error: errors.join(' ') }, 400); return; }
          state.config = body.config;
          state.subjects.forEach(subject => { subject.studyStream = streams[subject.id] || subject.studyStream; });
        }
        json({ config: state.config, subjects: state.subjects.map(subject => ({ id: subject.id, name: subject.name, stream: subject.studyStream, learningTopics: subject.topics.filter(topic => topic.status === 'learning').length })), phase: 'integrated', weeklyStudyHours: 54 });
        return;
      }
      if (pathname === '/api/data') { json({ subjects: state.subjects, settings: state.settings, completedRevisions: {} }); return; }
      if (pathname === '/api/timeline-estimate') { json(timeline()); return; }
      if (pathname === '/api/today' || pathname === '/api/dashboard') {
        const due = tasks();
        json({ today, dayOfWeek: 2, isWeekend: false, settings: state.settings, todayTasks: due, overdueTasks: [], learningPlan: learningPlan(), learningTopics: flatTopics().filter(topic => topic.status === 'learning'), timeBudget: budget(), repairTasks: [{ id: 'repair' }],
          stats: { totalTopics: 211, completed: 1, learning: 1, todayTasks: 2, todayDone: 0, overdue: 0, totalRevisions: 0 }, upcoming: {}, cumulativeUpcoming: [] });
        return;
      }
      if (/^\/api\/calendar\/day\//.test(pathname)) {
        const date = pathname.split('/').pop();
        json({ dayName: 'Wednesday', isToday: date === today, isPast: date < today, isFuture: date > today, isWeekend: false, tasks: tasks(), total: 2, done: 0, pending: 2, overdue: 0, timeBudget: budget(), learningPlan: learningPlan(), learningTopics: flatTopics().filter(topic => topic.status === 'learning') });
        return;
      }
      if (/^\/api\/calendar\/\d+\/\d+$/.test(pathname)) { json({ today, daysInMonth: 31, events: { [today]: tasks() }, learningByDate: { [today]: learningPlan() }, reservesByDate: { [today]: budget().activities.filter(item => item.category === 'reserve') } }); return; }
      const start = pathname.match(/^\/api\/subjects\/([^/]+)\/topics\/([^/]+)\/start$/);
      if (start) {
        const subject = state.subjects.find(entry => entry.id === start[1]);
        const topic = subject?.topics.find(entry => entry.id === start[2]);
        if (!topic) { json({ error: 'Topic not found' }, 404); return; }
        if (state.subjects.some(entry => entry.studyStream === subject.studyStream && entry.topics.some(current => current.status === 'learning'))) { json({ error: 'This learning stream is busy', limitReached: true }, 400); return; }
        if (!topic.links.length) { json({ error: 'Add current affairs links before starting this topic' }, 400); return; }
        topic.status = 'learning';
        topic.startDate = today;
        json({ topic });
        return;
      }
      if (pathname === '/api/study-logs' && incoming.method === 'POST') { state.logs.push(body); json({ ok: true }); return; }
      if (pathname === '/api/preparation') { json({ subjects: [], profiles: {}, policy: {}, repairs: [], errorTypes: [] }); return; }
      json({ error: 'Not a planner fixture route' }, 404);
    } catch (error) { json({ error: error.message }, 500); }
  });
  return server;
}

test('isolated fixture validates atomic saves and rejects invalid configuration', async context => {
  const server = createPlannerFixtureServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  context.after(() => new Promise(resolve => server.close(resolve)));
  const base = `http://127.0.0.1:${server.address().port}`;
  const initial = await (await fetch(`${base}/api/planner`)).json();
  const invalid = structuredClone(initial.config);
  invalid.allocations.integrated.gs = 0;
  const response = await fetch(`${base}/api/planner`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ config: invalid, subjectStreams: { sociology1: 'gs' } }) });
  assert.equal(response.status, 400);
  const unchanged = await (await fetch(`${base}/api/planner`)).json();
  assert.deepEqual(unchanged, initial);
});

if (process.argv.includes('--serve')) {
  const server = createPlannerFixtureServer();
  server.listen(0, '127.0.0.1', () => process.stdout.write(`Planner fixture (memory only): http://127.0.0.1:${server.address().port}\n`));
}