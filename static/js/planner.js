const PLANNER_PHASES = ['integrated', 'prelims', 'mains'];
const PLANNER_ALLOCATIONS = { gs: 'GS learning', optional: 'Optional learning', recall: 'Recall', practice: 'Practice', currentAffairs: 'Current affairs' };
let plannerSnapshot = null;
let plannerDraft = null;
let plannerSaving = false;

function plannerEscape(value) {
  return String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
}

function plannerStream(subject = {}) {
  const explicit = subject.studyStream || subject.stream;
  if (explicit === 'gs' || explicit === 'optional') return explicit;
  const profile = String(subject.strategy?.profile || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  return /^sociology(?:paper)?[12]$/.test(profile) || /sociology|optional/i.test(subject.name || subject.subjectName || '') ? 'optional' : 'gs';
}

function plannerSubject(subject) {
  const canonical = plannerSnapshot?.subjects?.find(entry => entry.id === subject.id);
  return canonical ? { ...subject, studyStream: canonical.stream } : subject;
}

function plannerCanStart(subject, subjects = []) {
  return true;
}

function plannerBadge(subject) {
  const stream = plannerStream(subject);
  return `<span class="planner-stream planner-stream-${stream}">${stream === 'gs' ? 'GS' : 'Optional'}</span>`;
}

function validatePlannerConfig(config) {
  const errors = [];
  if (!config || config.mode !== 'two-stream') errors.push('Planner mode must be two-stream.');
  if (!['auto', ...PLANNER_PHASES].includes(config?.phase)) errors.push('Select a valid phase.');
  if (!Number.isInteger(config?.attemptYear) || config.attemptYear < 2026 || config.attemptYear > 2100) errors.push('Attempt year must be between 2026 and 2100.');
  if (!Number.isInteger(config?.prelimsFocusDays) || config.prelimsFocusDays < 14 || config.prelimsFocusDays > 365) errors.push('Prelims focus window must be between 14 and 365 days.');
  if (config?.recallGuardDays !== undefined && (!Number.isInteger(config.recallGuardDays) || config.recallGuardDays < 0 || config.recallGuardDays > 90)) errors.push('Recall backlog guard must be between 0 and 90 days.');
  if (typeof config?.weekendConsolidation !== 'boolean') errors.push('Choose a weekend consolidation setting.');
  PLANNER_PHASES.forEach(phase => {
    const row = config?.allocations?.[phase] || {};
    const values = Object.keys(PLANNER_ALLOCATIONS).map(key => row[key]);
    if (values.some(value => typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > 100)) {
      errors.push(`${phase}: percentages must be numbers between 0 and 100.`);
    } else if (Math.abs(values.reduce((total, value) => total + value, 0) - 100) > 0.005) {
      errors.push(`${phase}: allocation must total 100%.`);
    }
    if (!(row.gs > 0) || !(row.optional > 0)) errors.push(`${phase}: both learning streams must have a positive allocation.`);
  });
  ['gsSubjectOrder', 'optionalSubjectOrder'].forEach(key => {
    if (!Array.isArray(config?.[key]) || new Set(config[key]).size !== config[key].length) errors.push(`${key}: subject order must contain unique IDs.`);
  });
  return errors;
}

function updatePlannerTarget(config) {
  const target = document.getElementById('target-attempt');
  if (target && Number.isInteger(config?.attemptYear)) target.textContent = `Target: UPSC ${config.attemptYear}`;
}

async function loadPlanner() {
  const result = await api('/api/planner');
  if (result.error || !result.config || !Array.isArray(result.subjects)) throw new Error(result.error || 'Planner settings are unavailable.');
  plannerSnapshot = result;
  updatePlannerTarget(result.config);
  return result;
}

async function refreshPlannerTarget() {
  try { await loadPlanner(); } catch (_) { return null; }
}

function plannerQueue(subjects, config, stream) {
  const order = config[stream === 'gs' ? 'gsSubjectOrder' : 'optionalSubjectOrder'] || [];
  const selected = subjects.filter(subject => plannerStream(subject) === stream);
  return [...selected].sort((first, second) => {
    const firstIndex = order.indexOf(first.id);
    const secondIndex = order.indexOf(second.id);
    return (firstIndex < 0 ? order.length : firstIndex) - (secondIndex < 0 ? order.length : secondIndex);
  });
}

function normalizePlannerOrders() {
  ['gs', 'optional'].forEach(stream => {
    plannerDraft.config[stream === 'gs' ? 'gsSubjectOrder' : 'optionalSubjectOrder'] = plannerQueue(plannerDraft.subjects, plannerDraft.config, stream).map(subject => subject.id);
  });
}

function plannerSettingsMarkup() {
  const { config, subjects } = plannerDraft;
  const escape = plannerEscape;
  return `<form id="planner-form">
    <div class="planner-fields">
      <label>Attempt year<input class="form-input" name="attemptYear" type="number" min="2026" max="2100" step="1" required value="${escape(config.attemptYear)}"></label>
      <label>Phase<select class="form-select" name="phase">${['auto', ...PLANNER_PHASES].map(phase => `<option value="${phase}" ${config.phase === phase ? 'selected' : ''}>${phase === 'auto' ? 'Auto' : phase[0].toUpperCase() + phase.slice(1)}</option>`).join('')}</select></label>
      <label>Prelims focus window (days)<input class="form-input" name="prelimsFocusDays" type="number" min="14" max="365" step="1" required value="${escape(config.prelimsFocusDays)}"></label>
      <label>Recall backlog guard (days; 0 disables)<input class="form-input" name="recallGuardDays" type="number" min="0" max="90" step="1" required value="${escape(config.recallGuardDays ?? 7)}"></label>
      <label class="planner-checkbox"><input name="weekendConsolidation" type="checkbox" ${config.weekendConsolidation ? 'checked' : ''}>Weekend consolidation</label>
    </div>
    <div class="planner-meta">Active phase: ${escape(plannerSnapshot.phase || config.phase)}${Number.isFinite(plannerSnapshot.weeklyStudyHours) ? ` &middot; ${escape(plannerSnapshot.weeklyStudyHours)}h/week` : ''} &middot; Started topics only; one running stopwatch</div>
    <div class="planner-table-scroll" tabindex="0" role="region" aria-label="Phase allocation percentages">
      <table class="planner-allocation"><caption>Phase allocation (%)</caption><thead><tr><th scope="col">Phase</th>${Object.values(PLANNER_ALLOCATIONS).map(label => `<th scope="col">${label}</th>`).join('')}<th scope="col">Total</th></tr></thead><tbody>
      ${PLANNER_PHASES.map(phase => `<tr><th scope="row">${phase[0].toUpperCase() + phase.slice(1)}</th>${Object.entries(PLANNER_ALLOCATIONS).map(([key, label]) => `<td><input class="form-input" type="number" required min="0" max="100" step="0.01" data-phase="${phase}" data-allocation="${key}" aria-label="${phase} ${label} percent" value="${escape(config.allocations?.[phase]?.[key])}"></td>`).join('')}<td><output data-total="${phase}"></output></td></tr>`).join('')}
      </tbody></table>
    </div>
    <div class="planner-queues">${['gs', 'optional'].map(stream => {
      const queue = plannerQueue(subjects, config, stream);
      return `<section aria-labelledby="planner-${stream}-title"><h4 id="planner-${stream}-title">${stream === 'gs' ? 'GS' : 'Optional'} subject queue</h4><ol class="planner-subject-order">${queue.map((subject, index) => `<li>
        <span class="planner-subject-name">${escape(subject.name)}</span>
        <select class="form-select" data-subject="${escape(subject.id)}" aria-label="Learning stream for ${escape(subject.name)}"><option value="gs" ${stream === 'gs' ? 'selected' : ''}>GS</option><option value="optional" ${stream === 'optional' ? 'selected' : ''}>Optional</option></select>
        <div class="planner-order-controls">${[-1, 1].map(direction => `<button class="btn btn-sm btn-icon" type="button" data-move="${direction}" data-subject="${escape(subject.id)}" ${direction === -1 && index === 0 || direction === 1 && index === queue.length - 1 ? 'disabled' : ''} aria-label="Move ${escape(subject.name)} ${direction === -1 ? 'up' : 'down'}" title="Move ${direction === -1 ? 'up' : 'down'}">${direction === -1 ? '&#8593;' : '&#8595;'}</button>`).join('')}</div>
      </li>`).join('') || '<li class="planner-empty">No subjects assigned</li>'}</ol></section>`;
    }).join('')}</div>
    <div id="planner-validation" role="status" aria-live="polite"></div>
    <div id="planner-save-status" role="status" aria-live="polite"></div>
    <button class="btn btn-primary" type="submit">Save Planner</button>
  </form>`;
}

function refreshPlannerValidation() {
  const root = document.getElementById('planner-settings');
  if (!root?.querySelector('#planner-form') || !plannerDraft) return;
  PLANNER_PHASES.forEach(phase => {
    const total = Object.values(plannerDraft.config.allocations[phase]).reduce((sum, value) => sum + value, 0);
    const output = root.querySelector(`[data-total="${phase}"]`);
    output.textContent = Number.isFinite(total) ? `${total.toFixed(2)}%` : 'Invalid';
    output.classList.toggle('planner-invalid', !Number.isFinite(total) || Math.abs(total - 100) > 0.005);
  });
  const errors = validatePlannerConfig(plannerDraft.config);
  root.querySelector('#planner-validation').textContent = errors.join(' ');
  root.querySelector('[type="submit"]').disabled = plannerSaving || errors.length > 0;
}

function drawPlannerSettings() {
  document.getElementById('planner-settings-body').innerHTML = plannerSettingsMarkup();
  refreshPlannerValidation();
}

async function renderPlannerSettings() {
  const root = document.getElementById('planner-settings');
  if (!root) return;
  const body = document.getElementById('planner-settings-body');
  body.textContent = 'Loading planner...';
  root.setAttribute('aria-busy', 'true');
  try {
    const result = await loadPlanner();
    plannerDraft = { config: JSON.parse(JSON.stringify(result.config)), subjects: result.subjects.map(subject => ({ ...subject })) };
    normalizePlannerOrders();
    drawPlannerSettings();
    root.oninput = event => {
      const input = event.target;
      if (input.dataset.allocation) plannerDraft.config.allocations[input.dataset.phase][input.dataset.allocation] = input.value === '' ? NaN : Number(input.value);
      else if (['attemptYear', 'prelimsFocusDays', 'recallGuardDays'].includes(input.name)) plannerDraft.config[input.name] = input.value === '' ? NaN : Number(input.value);
      else if (input.name === 'phase') plannerDraft.config.phase = input.value;
      else if (input.name === 'weekendConsolidation') plannerDraft.config.weekendConsolidation = input.checked;
      refreshPlannerValidation();
    };
    root.onchange = event => {
      const input = event.target;
      if (!input.matches('select[data-subject]')) return;
      plannerDraft.subjects.find(subject => subject.id === input.dataset.subject).stream = input.value;
      normalizePlannerOrders();
      drawPlannerSettings();
      Array.from(root.querySelectorAll('select[data-subject]')).find(select => select.dataset.subject === input.dataset.subject)?.focus();
    };
    root.onclick = event => {
      const button = event.target.closest('button[data-move]');
      if (!button) return;
      const subject = plannerDraft.subjects.find(entry => entry.id === button.dataset.subject);
      const key = plannerStream(subject) === 'gs' ? 'gsSubjectOrder' : 'optionalSubjectOrder';
      const queue = plannerDraft.config[key];
      const index = queue.indexOf(subject.id);
      const next = index + Number(button.dataset.move);
      if (next < 0 || next >= queue.length) return;
      [queue[index], queue[next]] = [queue[next], queue[index]];
      drawPlannerSettings();
      const controls = Array.from(root.querySelectorAll('button[data-move]')).filter(control => control.dataset.subject === subject.id);
      (controls.find(control => control.dataset.move === button.dataset.move && !control.disabled) || controls.find(control => !control.disabled))?.focus();
    };
    root.onsubmit = savePlannerSettings;
  } catch (error) {
    body.innerHTML = `<p role="alert">${plannerEscape(error.message)}</p><button type="button" class="btn" id="planner-retry">Retry</button>`;
    body.querySelector('#planner-retry').onclick = renderPlannerSettings;
  } finally {
    root.setAttribute('aria-busy', 'false');
  }
}

async function savePlannerSettings(event) {
  event.preventDefault();
  if (plannerSaving || validatePlannerConfig(plannerDraft.config).length) return;
  plannerSaving = true;
  const form = document.getElementById('planner-form');
  const controls = Array.from(form.querySelectorAll('input, select, button'));
  const disabled = controls.map(control => control.disabled);
  controls.forEach(control => { control.disabled = true; });
  try {
    const response = await api('/api/planner', 'PUT', {
      config: plannerDraft.config,
      subjectStreams: Object.fromEntries(plannerDraft.subjects.map(subject => [subject.id, plannerStream(subject)])),
    });
    if (response.error || response.errors) throw new Error(response.error || JSON.stringify(response.errors));
    await renderPlannerSettings();
    const status = document.getElementById('planner-save-status');
    if (status) status.textContent = 'Planner saved.';
  } catch (error) {
    const status = document.getElementById('planner-save-status');
    if (status) status.textContent = `Not saved: ${error.message}`;
  } finally {
    plannerSaving = false;
    controls.forEach((control, index) => { control.disabled = disabled[index]; });
    refreshPlannerValidation();
  }
}

function plannerDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return 'Not scheduled';
  const [year, month, day] = value.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return 'Not scheduled';
  return date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

function plannerProvisionalWarning(summary = {}) {
  const count = Number(summary.provisionalTopics) || 0;
  return count > 0 ? `<div class="planner-forecast-note" role="note">Provisional forecast: ${plannerEscape(count)} topic(s) use default estimates. Coverage and activity dates may change as actual hours are recorded.</div>` : '';
}

function renderPlannerMilestones(summary = {}) {
  const streams = summary.streams || {};
  const milestones = summary.milestones || {};
  const row = (label, value) => `<dt>${label}</dt><dd>${plannerDate(value)}</dd>`;
  const topicList = (label, topics = []) => topics.length ? `<details><summary>${topics.length} ${label}</summary><ul>${topics.map(topic => `<li>${plannerEscape(topic.topicName || topic.topicId || topic)}${topic.subjectName ? ` &middot; ${plannerEscape(topic.subjectName)}` : ''}</li>`).join('')}</ul></details>` : '';
  const pressure = ['gs', 'optional'].map(stream => {
    const delay = Number(summary.recallPressure?.[stream]?.maxDelayDays) || 0;
    const held = Number(summary.guardedLearningDays?.[stream]) || 0;
    return delay || held ? `<div class="planner-forecast-note" role="note">${stream === 'gs' ? 'GS' : 'Optional'} review pressure: up to ${delay} days of projected recall delay; new learning deferred on ${held} forecast days. The backlog guard is a planning tolerance, not a guarantee of on-time recall.</div>` : '';
  }).join('');
  return pressure + `<div class="planner-milestones">${['gs', 'optional'].map(stream => {
    const info = streams[stream] || (stream === 'optional' ? milestones.optional : null) || {};
    return `<section><h3>${stream === 'gs' ? 'GS' : 'Optional'} stream${info.totalTopics !== undefined ? ` &middot; ${plannerEscape(info.totalTopics)} topics` : ''}</h3><dl>${row('First-pass coverage', info.coverageDate)}${row('Full activity pipeline', info.pipelineDate)}</dl></section>`;
  }).join('')}${['prelims', 'mains'].map(exam => {
    const info = milestones[exam] || {};
    return `<section><h3>${exam === 'prelims' ? 'Prelims' : 'Mains'}-scoped activities</h3><dl>${row('Activity finish', info.finishDate)}${row('Planning deadline', info.deadline)}</dl>${topicList('late topics', info.lateTopics)}${topicList('unscheduled topics', info.unscheduledTopics)}</section>`;
  }).join('')}</div>`;
}

function plannerActionButton(action, label, item, disabled = false, title = '') {
  return `<button type="button" class="btn btn-sm" data-planner-action="${action}" data-topic="${plannerEscape(item.topicId || item.id)}" data-subject="${plannerEscape(item.subjectId)}" ${disabled ? 'disabled' : ''}${title ? ` title="${plannerEscape(title)}"` : ''}>${label}</button>`;
}

function renderPlannerLearning(data, options = {}) {
  const actual = data.learningTopics || [];
  const plan = (data.learningPlan || []).filter(item => item.isSuggested !== true).map(item => ({ ...item }));
  actual.forEach(topic => {
    if (!plan.some(item => (item.topicId || item.id) === (topic.id || topic.topicId))) {
      plan.push({ ...topic, topicId: topic.id || topic.topicId, topicName: topic.name, hours: 0, isSuggested: false });
    }
  });
  const subjects = plannerSnapshot?.subjects || [];
  const classify = item => plannerStream({ ...item, name: item.subjectName, studyStream: item.stream || subjects.find(subject => subject.id === item.subjectId)?.stream || item.studyStream });
  return `<div class="planner-learning">${['gs', 'optional'].map(stream => {
    const entries = plan.filter(item => classify(item) === stream);
    return `<section class="planner-lane" data-stream="${stream}" aria-label="${stream === 'gs' ? 'GS' : 'Optional'} planned learning"><h4>${stream === 'gs' ? 'GS' : 'Optional'} learning</h4>${entries.map(item => {
      const topic = actual.find(topic => (topic.id || topic.topicId) === (item.topicId || item.id)) || item;
      const finished = ['completed', 'pipeline-complete'].includes(item.topicStatus || topic.status);
      const planned = Number.isFinite(item.plannedHours) ? item.plannedHours : item.hours;
      const hours = Number.isFinite(planned) ? `${plannerEscape(planned)}h planned` : 'No duration set';
      const measured = Number.isFinite(item.actualHours) ? ` &middot; ${plannerEscape(item.actualHours)}h logged` : '';
      const remaining = Number.isFinite(item.remaining) ? ` &middot; ${plannerEscape(item.remaining)}h remaining` : '';
      const timer = typeof learningTimerMarkup === 'function' ? learningTimerMarkup(topic) : '';
      return `<div class="planner-learning-topic"><div class="planner-learning-name">${plannerEscape(item.topicName || item.name)}</div>
        <div class="planner-meta">${plannerEscape(item.subjectName)} &middot; ${hours}${measured}${remaining} &middot; ${finished ? 'Learning complete' : 'In progress'}</div>${timer}
        <div class="planner-learning-actions">${plannerActionButton('view', 'View', item)}
        ${!finished && options.allowLog !== false ? `${plannerActionButton(topic.timerStartedAt ? 'pause' : 'start', topic.timerStartedAt ? 'Pause' : 'Resume', item)}${plannerActionButton('complete', 'Finish', item)}<label>Actual hours (untimed session)<input type="number" class="form-input" min="0.01" max="24" step="0.01" placeholder="Not logged" aria-label="Actual hours for ${plannerEscape(item.topicName || item.name)}"></label>${plannerActionButton('log', 'Log', item)}` : ''}</div></div>`;
    }).join('') || '<div class="planner-empty">No started learning allocated</div>'}</section>`;
  }).join('')}</div>`;
}

function plannerStageCanMark(task) {
  return task.isProjected !== true && task.canMark !== false && !['not-started', 'learning'].includes(task.topicStatus || task.status);
}

function plannerStageControl(task, date = '') {
  if (!plannerStageCanMark(task)) return '<span class="planner-stage-note">Waiting for prerequisite work</span>';
  const label = task.done ? `Undo ${task.type} completion` : `Mark entire ${task.type} activity done (all sessions)`;
  return `<div class="planner-learning-actions" onclick="event.stopPropagation()"><button type="button" class="planner-stage-check" data-planner-action="stage" data-topic="${plannerEscape(task.topicId)}" data-type="${plannerEscape(task.type)}" data-date="${plannerEscape(date)}" data-done="${task.done ? 'true' : 'false'}" aria-label="${plannerEscape(label)}" title="${plannerEscape(label)}">${task.done ? '&#10003;' : '&#9633;'}</button>
    <label>Session hours today<input type="number" class="form-input" data-stage-hours min="0.01" max="24" step="0.01" value="0.5" aria-label="Actual ${plannerEscape(task.type)} session hours today"></label>
    <button type="button" class="btn btn-sm" data-planner-action="stage-log" data-topic="${plannerEscape(task.topicId)}" data-type="${plannerEscape(task.type)}" title="Record actual session time without completing the stage">Log</button></div>`;
}

function plannerBudgetLabel(budget = {}) {
  const logged = budget.loggedHours ?? budget.actualHours;
  return `<div class="planner-meta">Remaining planned: ${plannerEscape(budget.plannedHours ?? budget.totalHours ?? '?')}h${Number.isFinite(logged) ? ` &middot; Logged: ${plannerEscape(logged)}h` : ' &middot; Actual time is recorded in study logs'}${budget.estimatedSpentHours ? ` &middot; Estimated time used: ${plannerEscape(budget.estimatedSpentHours)}h` : ''}${budget.phase ? ` &middot; ${plannerEscape(budget.phase)} phase` : ''}</div>`;
}

function installPlannerActions() {
  document.addEventListener('click', async event => {
    const button = event.target.closest('[data-planner-action]');
    if (!button || button.disabled) return;
    event.stopPropagation();
    const { plannerAction: action, subject, topic, type, date, done } = button.dataset;
    button.disabled = true;
    try {
      if (action === 'view') await showTopicDetail(subject, topic);
      if (action === 'start') await startLearning(subject, topic);
      if (action === 'pause') await pauseLearning(subject, topic);
      if (action === 'log') await logStudyHours(topic, button.parentElement.querySelector('input').value);
      if (action === 'complete') await completeLearning(subject, topic);
      if (action === 'stage-log') {
        const hours = Number(button.parentElement.querySelector('[data-stage-hours]').value);
        if (!Number.isFinite(hours) || hours <= 0 || hours > 24) throw new Error('Enter actual session hours between 0 and 24.');
        const response = await api('/api/study-logs', 'POST', { topicId: topic, stage: type, hours });
        if (response.error) throw new Error(response.error);
        showToast('Stage session recorded. Completion remains a separate action.');
        renderAll();
      }
      if (action === 'stage') {
        if (done !== 'true' && !confirm(`Complete the entire ${type} activity, including any sessions on other days? Only confirm after all work is finished.`)) return;
        if (date) await calToggleRevision(topic, type, date);
        else await toggleRevision(topic, type);
      }
    } catch (error) {
      showToast(error.message || 'Action failed. Please retry.', 'warning');
    } finally {
      button.disabled = false;
    }
  }, true);
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { plannerStream, plannerCanStart, plannerEscape, plannerQueue, validatePlannerConfig,
    plannerDate, plannerProvisionalWarning, renderPlannerMilestones, renderPlannerLearning, plannerStageCanMark, plannerStageControl, plannerBudgetLabel };
}