(function (root) {
  'use strict';

  const state = {
    data: null, subjectId: null, topicId: null, loading: null,
    historyTopic: '*', historyKind: '*', historyPage: 0, policyOpen: false
  };
  const escape = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[character]);
  const pathPart = value => encodeURIComponent(String(value));
  const localToday = () => {
    if (typeof root.todayStr === 'function') return root.todayStr();
    const date = new Date();
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
  };

  async function request(url, method = 'GET', body) {
    const response = await root.fetch(url, {
      method, credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) })
    });
    let result;
    try { result = await response.json(); } catch (_) {
      throw new Error(response.ok ? 'The server returned an unreadable response.' : `Request failed (${response.status}). Refresh your session and retry.`);
    }
    if (!response.ok || result?.error) {
      throw new Error(typeof result?.error === 'string' ? result.error : `Request failed (${response.status}).`);
    }
    return result;
  }

  const option = (value, label, selected) => `<option value="${escape(value)}"${selected ? ' selected' : ''}>${escape(label)}</option>`;
  const valueOf = (form, name) => form.elements.namedItem(name).value;
  const selectedValues = element => Array.from(element.selectedOptions, entry => entry.value);
  const inputField = (label, name, value, attributes = '') => `<label class="prep-field">${escape(label)}<input name="${escape(name)}" value="${escape(value)}" ${attributes}></label>`;
  const selectField = (label, name, choices, value, attributes = '') => `<label class="prep-field">${escape(label)}<select name="${escape(name)}" ${attributes}>${choices.map(([key, text]) => option(key, text, key === value)).join('')}</select></label>`;
  const feedback = () => '<p class="prep-feedback" role="status" aria-live="polite" hidden></p>';
  const iconButton = (title, attributes, symbol = 'x') => `<button type="button" class="btn btn-sm prep-icon" title="${escape(title)}" aria-label="${escape(title)}" ${attributes}>${symbol}</button>`;
  const subjectUrl = subject => `/api/subjects/${pathPart(subject.id)}`;

  function formMessage(form, message, failed = true) {
    const element = form.querySelector('.prep-feedback');
    element.hidden = !message;
    element.classList.toggle('prep-error', failed);
    element.setAttribute('role', failed ? 'alert' : 'status');
    element.textContent = message;
  }

  function bindSave(form, build, success) {
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const button = form.querySelector('button[type="submit"]');
      if (button.disabled || !form.reportValidity()) return;
      try {
        const operation = build();
        button.disabled = true;
        formMessage(form, 'Saving...', false);
        const result = await request(operation.url, operation.method || 'PUT', operation.body);
        if (typeof root.showToast === 'function') root.showToast(typeof success === 'function' ? success(result) : success);
        await renderPreparation();
      } catch (error) {
        formMessage(form, error.message);
      } finally {
        button.disabled = false;
      }
    });
  }

  function outputMarkup(profileId) {
    const outputs = state.data.profiles[profileId]?.outputs || [];
    return `<h3>Subject outputs</h3><ul class="prep-outputs">${outputs.map(output => `<li>${escape(output)}</li>`).join('')}</ul>`;
  }

  function resourceMarkup(resource = {}) {
    return `<fieldset class="prep-resource prep-row" data-resource>
      <legend>Resource</legend>
      ${selectField('Tier', 'resourceTier', [['foundation', 'Foundation'], ['spine', 'Spine'], ['depth', 'Depth']], resource.tier || 'spine')}
      ${inputField('Title', 'resourceTitle', resource.title || '', 'required maxlength="200"')}
      ${inputField('Chapters / bounded scope', 'resourceScope', resource.scope || '', 'required maxlength="600"')}
      ${inputField('Gap / question (required for depth)', 'resourceReason', resource.reason || '', `maxlength="600"${resource.tier === 'depth' ? ' required' : ''}`)}
      ${iconButton('Remove resource', 'data-remove-resource')}
    </fieldset>`;
  }

  function syllabusMarkup(subject, item = {}) {
    return `<fieldset class="prep-syllabus prep-row" data-syllabus>
      <legend>Syllabus entry</legend>
      ${inputField('Syllabus entry', 'syllabusTitle', item.title || '', 'required maxlength="500"')}
      <label class="prep-field">Linked topics<select name="syllabusTopics" multiple size="4" aria-label="Linked topics">${subject.topics.map(topic => option(topic.id, topic.name, (item.topicIds || []).includes(topic.id))).join('')}</select></label>
      ${iconButton('Remove syllabus entry', 'data-remove-syllabus')}
    </fieldset>`;
  }

  function strategyMarkup(subject) {
    const strategy = subject.strategy || {};
    const coverage = subject.coverage || {};
    return `<form id="prep-strategy" class="prep-section">
      <div class="prep-section-heading"><h3>Subject strategy</h3><span class="prep-muted">Syllabus: ${escape(coverage.covered ?? 0)} / ${escape(coverage.total ?? 0)} covered | ${coverage.verified ? 'Verified' : 'Not verified'}</span></div>
      <div class="prep-grid prep-grid-two">
        ${selectField('Profile', 'profile', Object.entries(state.data.profiles).map(([key, profile]) => [key, profile.name]), strategy.profile || 'general')}
        ${selectField('Activity pipeline', 'stagePreset', [['standard', 'Standard activities'], ['compact', 'Compact activities']], strategy.stagePreset || 'standard')}
      </div>
      <div class="prep-output" id="prep-outputs">${outputMarkup(strategy.profile || 'general')}</div>
      <div class="prep-section-heading"><h4>Resources</h4><button type="button" class="btn btn-sm" data-add-resource>+ Resource</button></div>
      <div id="prep-resources">${(strategy.resources || []).map(resourceMarkup).join('')}</div>
      <div class="prep-section-heading"><h4>Syllabus coverage</h4><button type="button" class="btn btn-sm" data-add-syllabus>+ Entry</button></div>
      <div id="prep-syllabus">${(strategy.syllabus || []).map(item => syllabusMarkup(subject, item)).join('')}</div>
      <label class="prep-check"><input type="checkbox" name="syllabusVerified"${strategy.syllabusVerified ? ' checked' : ''}> Syllabus verified against official syllabus</label>
      ${feedback()}<div class="prep-actions"><button type="submit" class="btn btn-primary">Save strategy</button></div>
    </form>`;
  }

  function bindStrategy(subject) {
    const form = root.document.getElementById('prep-strategy');
    const resources = form.querySelector('#prep-resources');
    const syllabus = form.querySelector('#prep-syllabus');
    const resourceAdd = form.querySelector('[data-add-resource]');
    const syllabusAdd = form.querySelector('[data-add-syllabus]');
    const updateLimits = () => {
      resourceAdd.disabled = resources.children.length >= 20;
      syllabusAdd.disabled = syllabus.children.length >= 200;
    };
    resourceAdd.addEventListener('click', () => {
      if (resources.children.length >= 20) return;
      resources.insertAdjacentHTML('beforeend', resourceMarkup());
      updateLimits();
      resources.lastElementChild.querySelector('[name="resourceTitle"]').focus();
    });
    syllabusAdd.addEventListener('click', () => {
      if (syllabus.children.length >= 200) return;
      syllabus.insertAdjacentHTML('beforeend', syllabusMarkup(subject));
      updateLimits();
      syllabus.lastElementChild.querySelector('input').focus();
    });
    form.addEventListener('click', event => {
      const remove = event.target.closest('[data-remove-resource], [data-remove-syllabus]');
      if (!remove) return;
      remove.closest('fieldset').remove();
      updateLimits();
    });
    form.addEventListener('change', event => {
      if (event.target.name === 'resourceTier') {
        event.target.closest('fieldset').querySelector('[name="resourceReason"]').required = event.target.value === 'depth';
      }
      if (event.target.name === 'profile') root.document.getElementById('prep-outputs').innerHTML = outputMarkup(event.target.value);
    });
    updateLimits();
    bindSave(form, () => ({
      url: `${subjectUrl(subject)}/strategy`,
      body: {
        profile: valueOf(form, 'profile'), stagePreset: valueOf(form, 'stagePreset'),
        resources: Array.from(resources.children, row => ({
          tier: row.querySelector('[name="resourceTier"]').value,
          title: row.querySelector('[name="resourceTitle"]').value.trim(),
          scope: row.querySelector('[name="resourceScope"]').value.trim(),
          reason: row.querySelector('[name="resourceReason"]').value.trim()
        })),
        syllabus: Array.from(syllabus.children, row => ({
          title: row.querySelector('[name="syllabusTitle"]').value.trim(),
          topicIds: selectedValues(row.querySelector('select'))
        })),
        syllabusVerified: form.elements.namedItem('syllabusVerified').checked
      }
    }), 'Subject strategy saved.');
  }

  const statusLabels = {
    'not-assessed': 'Not assessed', 'diagnostic-only': 'Diagnostic only', 'early-recall': 'Early recall',
    'on-target': 'On target', stale: 'Stale', 'self-assessed': 'Self assessed',
    'needs-practice': 'Needs practice', 'small-sample': 'Small sample', recorded: 'Recorded'
  };
  const numberText = value => value === null || value === undefined || value === '' || !Number.isFinite(Number(value)) ? null : String(Number(value));

  function resultText(attempt) {
    if (attempt.kind === 'writing') {
      const score = numberText(attempt.score);
      return score === null ? 'Unreviewed' : `${score} / ${numberText(attempt.maxMarks) ?? '?'} marks (${attempt.reviewer === 'external' ? 'external' : 'self'})`;
    }
    const accuracy = numberText(attempt.kind === 'recall' ? attempt.retrievalPercent : attempt.accuracy);
    const net = attempt.kind === 'mcq' ? numberText(attempt.netMarks) : null;
    return [net === null ? '' : `${net} net marks`, accuracy === null ? '' : `${accuracy}% ${attempt.kind === 'recall' ? 'retrieved' : 'accuracy'}`].filter(Boolean).join(' | ') || 'Recorded';
  }

  function evidenceCell(dimension = {}) {
    const status = dimension.status || 'not-assessed';
    const tone = status === 'on-target' ? 'positive' : ['needs-practice', 'stale', 'small-sample'].includes(status) ? 'warning' : 'neutral';
    return `<span class="prep-status" data-tone="${tone}">${escape(statusLabels[status] || status)}</span><small>${escape(dimension.attempts ?? 0)} checks${dimension.latest ? ` | ${escape(dimension.latest.date)}` : ''}</small>${dimension.latest ? `<small>${escape(resultText(dimension.latest))}</small>` : ''}`;
  }

  function evidenceMarkup(subject) {
    return `<section class="prep-section" aria-labelledby="prep-evidence-heading">
      <div class="prep-section-heading"><h3 id="prep-evidence-heading">Assessment performance</h3><span class="prep-muted">${escape(subject.topics.length)} topics | Training evidence, not syllabus coverage</span></div>
      ${subject.topics.length ? `<div class="prep-table-scroll" role="region" aria-label="Assessment performance" tabindex="0"><table class="prep-table"><caption class="prep-sr-only">Recorded assessment performance and training status, separate from syllabus coverage</caption><thead><tr><th scope="col">Topic</th><th scope="col">Attempts</th><th scope="col">MCQ</th><th scope="col">Writing</th><th scope="col">Recall</th><th scope="col">Skill</th><th scope="col">Open repairs</th></tr></thead><tbody>${subject.topics.map(topic => `<tr${topic.id === state.topicId ? ' class="prep-selected"' : ''}><th scope="row"><div class="prep-topic-name"><button type="button" class="prep-text-button" data-topic-detail="${escape(topic.id)}">${escape(topic.name)}</button>${iconButton('Edit topic strategy', `data-edit-topic="${escape(topic.id)}"`, '&#9998;')}</div></th><td>${escape(topic.evidence?.attempts ?? 0)}</td>${['mcq', 'writing', 'recall', 'skill'].map(kind => `<td>${evidenceCell(topic.evidence?.dimensions?.[kind])}</td>`).join('')}<td>${escape(topic.evidence?.openRepairs ?? 0)}</td></tr>`).join('')}</tbody></table></div>` : '<p class="prep-empty">No topics in this subject.</p>'}
    </section>`;
  }

  function topicMarkup(subject) {
    return `<section class="prep-section" aria-labelledby="prep-topic-heading"><h3 id="prep-topic-heading">Topic activity scope &amp; prerequisites</h3>
      ${selectField('Topic', 'strategyTopic', [['', 'Select topic'], ...subject.topics.map(topic => [topic.id, topic.name])], state.topicId || '', 'id="prep-strategy-topic"')}
      <div id="prep-topic-editor"></div></section>`;
  }

  function drawTopicEditor(subject) {
    const topic = subject.topics.find(entry => entry.id === state.topicId);
    const host = root.document.getElementById('prep-topic-editor');
    if (!topic) { host.replaceChildren(); return; }
    host.innerHTML = `<form id="prep-topic-form"><div class="prep-grid prep-grid-two">
      ${selectField('Activity scope', 'studyScope', [['inherit', `Inherit (${subject.strategy?.stagePreset || 'standard'})`], ['standard', 'Standard activities'], ['compact', 'Compact activities']], topic.studyScope || 'inherit')}
      <label class="prep-field">Prerequisite topics<select name="prerequisiteIds" multiple size="6">${state.data.subjects.map(entry => `<optgroup label="${escape(entry.name)}">${entry.topics.filter(candidate => candidate.id !== topic.id).map(candidate => option(candidate.id, candidate.name, (topic.prerequisiteIds || []).includes(candidate.id))).join('')}</optgroup>`).join('')}</select></label>
      </div>${feedback()}<div class="prep-actions"><button type="submit" class="btn btn-primary">Save topic strategy</button></div></form>`;
    const form = host.querySelector('form');
    bindSave(form, () => ({
      url: `${subjectUrl(subject)}/topics/${pathPart(topic.id)}/strategy`,
      body: { studyScope: valueOf(form, 'studyScope'), prerequisiteIds: selectedValues(form.elements.namedItem('prerequisiteIds')) }
    }), 'Topic strategy saved.');
  }

  function selectTopic(subject, topicId) {
    state.topicId = topicId || null;
    root.document.getElementById('prep-strategy-topic').value = topicId;
    const attemptTopic = root.document.getElementById('prep-attempt-topic');
    if (attemptTopic) attemptTopic.value = topicId;
    drawTopicEditor(subject);
    root.document.querySelectorAll('[data-edit-topic]').forEach(button => {
      button.closest('tr').classList.toggle('prep-selected', button.dataset.editTopic === topicId);
    });
  }

  const kinds = [['mcq', 'MCQ'], ['recall', 'Recall'], ['writing', 'Writing'], ['skill', 'Subject skill']];
  const kindLabel = kind => kinds.find(([key]) => key === kind)?.[1] || kind;
  const scopeLabel = (subject, topicId) => topicId ? subject.topics.find(topic => topic.id === topicId)?.name || 'Unknown topic' : 'Subject / full paper';

  function attemptMarkup(subject) {
    return `<form id="prep-attempt" class="prep-section">
      <h3>Record attempt</h3><div class="prep-grid prep-grid-three">
        ${selectField('Assessment', 'kind', kinds, 'mcq')}
        ${selectField('Scope', 'topicId', [['', 'Subject / full paper'], ...subject.topics.map(topic => [topic.id, topic.name])], state.topicId || '', 'id="prep-attempt-topic"')}
        ${inputField('Date', 'date', localToday(), `type="date" required max="${escape(localToday())}"`)}
        ${inputField('Minutes', 'minutes', 0, 'type="number" min="0" max="1440" step="any" required')}
        ${selectField('Question set', 'setType', [['diagnostic', 'Diagnostic'], ['unseen', 'Unseen'], ['mixed', 'Mixed'], ['repeated', 'Repeated']], 'diagnostic')}
      </div>
      <fieldset data-attempt-skill hidden disabled>${inputField('Subject skill', 'skill', '', 'required maxlength="200"')}</fieldset>
      <fieldset data-attempt-counts class="prep-grid prep-grid-three"><legend>Questions / items</legend>
        ${inputField('Correct', 'correct', 0, 'type="number" min="0" max="100000" step="1" required')}
        ${inputField('Wrong / missed', 'wrong', 0, 'type="number" min="0" max="100000" step="1" required')}
        ${inputField('Unattempted', 'unattempted', 0, 'type="number" min="0" max="100000" step="1" required')}
      </fieldset>
      <fieldset data-attempt-mcq class="prep-grid prep-grid-two"><legend>MCQ marking</legend>
        ${inputField('Marks per question', 'marksPerQuestion', 2, 'type="number" min="0.01" max="100" step="any" required')}
        ${inputField('Wrong-answer penalty fraction', 'penaltyFraction', '', 'type="number" min="0" max="1" step="any" placeholder="1/3 (default)"')}
      </fieldset>
      <fieldset data-attempt-writing class="prep-grid prep-grid-three" hidden disabled><legend>Writing evaluation</legend>
        ${selectField('Reviewer', 'reviewer', [['unreviewed', 'Unreviewed'], ['self', 'Self assessed'], ['external', 'External evaluation']], 'unreviewed')}
        ${inputField('Maximum marks', 'maxMarks', 10, 'type="number" min="0.1" max="100000" step="any" required')}
        ${inputField('Awarded marks', 'score', '', 'type="number" min="0" max="10" step="any" disabled')}
      </fieldset>
      <fieldset class="prep-errors"><legend>Error categories</legend>${(state.data.errorTypes || []).map(category => `<label class="prep-check"><input type="checkbox" name="errors" value="${escape(category)}"> ${escape(category)}</label>`).join('')}</fieldset>
      <label class="prep-field">Notes<textarea name="notes" rows="2" maxlength="2000"></textarea></label>
      ${feedback()}<div class="prep-actions"><button type="submit" class="btn btn-primary">Record attempt</button></div>
    </form>`;
  }

  function numericValue(form, name) {
    const raw = valueOf(form, name);
    const value = Number(raw);
    if (!raw.trim() || !Number.isFinite(value)) throw new Error('Complete the numeric fields.');
    return value;
  }

  function buildAttempt(form) {
    const kind = valueOf(form, 'kind');
    const date = valueOf(form, 'date');
    if (!date || date > localToday()) throw new Error('Choose an assessment date no later than today.');
    const body = {
      kind, topicId: valueOf(form, 'topicId') || null, date,
      minutes: numericValue(form, 'minutes'), setType: valueOf(form, 'setType'),
      notes: valueOf(form, 'notes').trim(),
      errors: Array.from(form.querySelectorAll('[name="errors"]:checked'), checkbox => checkbox.value)
    };
    if (kind === 'writing') {
      body.reviewer = valueOf(form, 'reviewer');
      body.maxMarks = numericValue(form, 'maxMarks');
      body.score = body.reviewer === 'unreviewed' ? null : numericValue(form, 'score');
      if (body.score !== null && (body.score < 0 || body.score > body.maxMarks)) throw new Error('Awarded marks must be between zero and maximum marks.');
    } else {
      for (const name of ['correct', 'wrong', 'unattempted']) {
        body[name] = numericValue(form, name);
        if (!Number.isInteger(body[name]) || body[name] < 0) throw new Error('Question and item counts must be nonnegative integers.');
      }
      if (body.correct + body.wrong + body.unattempted === 0) throw new Error('Record at least one question or recall item.');
      if (kind === 'skill') {
        body.skill = valueOf(form, 'skill').trim();
        if (!body.skill) throw new Error('Name the subject skill being checked.');
      }
      if (kind === 'mcq') {
        body.marksPerQuestion = numericValue(form, 'marksPerQuestion');
        if (valueOf(form, 'penaltyFraction').trim()) body.penaltyFraction = numericValue(form, 'penaltyFraction');
      }
    }
    return body;
  }

  function bindAttempt(subject) {
    const form = root.document.getElementById('prep-attempt');
    const update = () => {
      const kind = valueOf(form, 'kind');
      for (const [selector, active] of [
        ['[data-attempt-counts]', kind !== 'writing'], ['[data-attempt-mcq]', kind === 'mcq'],
        ['[data-attempt-writing]', kind === 'writing'], ['[data-attempt-skill]', kind === 'skill']
      ]) {
        const group = form.querySelector(selector);
        group.hidden = !active;
        group.disabled = !active;
      }
      const score = form.elements.namedItem('score');
      const reviewed = kind === 'writing' && valueOf(form, 'reviewer') !== 'unreviewed';
      score.required = reviewed;
      score.disabled = !reviewed;
      score.max = valueOf(form, 'maxMarks');
    };
    form.addEventListener('change', update);
    form.elements.namedItem('maxMarks').addEventListener('input', update);
    update();
    bindSave(form, () => ({ url: `${subjectUrl(subject)}/attempts`, method: 'POST', body: buildAttempt(form) }), result => `Attempt recorded: ${resultText(result)}.`);
  }

  function historyMarkup(subject) {
    return `<section class="prep-section" id="prep-history" aria-labelledby="prep-history-heading">
      <h3 id="prep-history-heading">Attempt history</h3><div class="prep-grid prep-grid-two">
        ${selectField('Scope filter', 'historyTopic', [['*', 'All scopes'], ['', 'Subject / full paper'], ...subject.topics.map(topic => [topic.id, topic.name])], state.historyTopic, 'id="prep-history-topic"')}
        ${selectField('Assessment filter', 'historyKind', [['*', 'All assessments'], ...kinds], state.historyKind, 'id="prep-history-kind"')}
      </div>${feedback()}<div id="prep-history-records"></div>
    </section>`;
  }

  async function voidAttempt(button, subject) {
    if (!root.confirm('Void this attempt? History is retained and its open repairs are cancelled.')) return;
    const container = root.document.getElementById('prep-history');
    button.disabled = true;
    try {
      await request(`/api/preparation/attempts/${pathPart(button.dataset.voidAttempt)}`, 'DELETE');
      if (typeof root.showToast === 'function') root.showToast('Attempt voided.');
      await renderPreparation(subject.id);
    } catch (error) {
      formMessage(container, error.message);
    } finally {
      button.disabled = false;
    }
  }

  function drawHistory(subject) {
    const host = root.document.getElementById('prep-history-records');
    const attempts = [...(subject.attempts || [])].reverse().filter(attempt => !attempt.voided
      && (state.historyTopic === '*' || (attempt.topicId || '') === state.historyTopic)
      && (state.historyKind === '*' || attempt.kind === state.historyKind))
      .sort((first, second) => String(second.date).localeCompare(String(first.date)));
    const pageSize = 15;
    const pages = Math.max(1, Math.ceil(attempts.length / pageSize));
    state.historyPage = Math.min(state.historyPage, pages - 1);
    const visible = attempts.slice(state.historyPage * pageSize, (state.historyPage + 1) * pageSize);
    host.innerHTML = attempts.length ? `<div class="prep-table-scroll" role="region" aria-label="Attempt history" tabindex="0"><table class="prep-table prep-history-table"><caption class="prep-sr-only">Recorded assessments</caption><thead><tr><th scope="col">Date</th><th scope="col">Scope</th><th scope="col">Assessment</th><th scope="col">Recorded result</th><th scope="col">Minutes</th><th scope="col">Notes / errors</th><th scope="col"><span class="prep-sr-only">Actions</span></th></tr></thead><tbody>${visible.map(attempt => `<tr><td>${escape(attempt.date)}</td><td>${escape(scopeLabel(subject, attempt.topicId))}</td><td>${escape(kindLabel(attempt.kind))}<small>${escape(attempt.setType)}${attempt.skill ? ` | ${escape(attempt.skill)}` : ''}</small></td><td>${escape(resultText(attempt))}${attempt.kind !== 'writing' ? `<small>${escape(attempt.correct)} correct / ${escape(attempt.wrong)} wrong / ${escape(attempt.unattempted)} unattempted</small>` : ''}</td><td>${escape(attempt.minutes)}</td><td>${attempt.notes || attempt.errors?.length ? `<details><summary>${escape(attempt.errors?.join(', ') || 'Notes')}</summary><p class="prep-notes">${escape(attempt.notes || 'No notes recorded.')}</p></details>` : '<span class="prep-muted">None</span>'}</td><td>${iconButton('Void attempt', `data-void-attempt="${escape(attempt.id)}"`)}</td></tr>`).join('')}</tbody></table></div><div class="prep-pagination"><span>${escape(attempts.length)} attempts | Page ${state.historyPage + 1} / ${pages}</span><div>${iconButton('Previous attempts', `data-history-prev${state.historyPage === 0 ? ' disabled' : ''}`, '&lt;')}${iconButton('Next attempts', `data-history-next${state.historyPage >= pages - 1 ? ' disabled' : ''}`, '&gt;')}</div></div>` : '<p class="prep-empty">No attempts for this scope and assessment.</p>';
    host.querySelectorAll('[data-void-attempt]').forEach(button => button.addEventListener('click', () => voidAttempt(button, subject)));
    host.querySelector('[data-history-prev]')?.addEventListener('click', () => { state.historyPage -= 1; drawHistory(subject); });
    host.querySelector('[data-history-next]')?.addEventListener('click', () => { state.historyPage += 1; drawHistory(subject); });
  }

  function bindHistory(subject) {
    for (const [id, key] of [['prep-history-topic', 'historyTopic'], ['prep-history-kind', 'historyKind']]) {
      root.document.getElementById(id).addEventListener('change', event => {
        state[key] = event.target.value;
        state.historyPage = 0;
        drawHistory(subject);
      });
    }
    drawHistory(subject);
  }

  function repairsMarkup(subject) {
    const repairs = (state.data.repairs || []).filter(repair => repair.subjectId === subject.id && repair.status === 'open')
      .sort((first, second) => String(first.dueDate).localeCompare(String(second.dueDate)));
    return `<section class="prep-section" aria-labelledby="prep-repairs-heading"><div class="prep-section-heading"><h3 id="prep-repairs-heading">Open repairs</h3><span class="prep-muted">${repairs.length} open</span></div>
      ${repairs.length ? repairs.map(repair => {
        const attempt = (subject.attempts || []).find(entry => entry.id === repair.attemptId);
        return `<form class="prep-repair" data-repair="${escape(repair.id)}"><div class="prep-section-heading"><h4>${escape(repair.category)} | ${escape(scopeLabel(subject, repair.topicId))}</h4><span class="prep-status" data-tone="${repair.dueDate < localToday() ? 'warning' : 'neutral'}">${repair.dueDate < localToday() ? 'Overdue' : 'Due'} ${escape(repair.dueDate)}</span></div>
          ${attempt ? `<p class="prep-muted">${escape(attempt.date)} | ${escape(kindLabel(attempt.kind))} | ${escape(resultText(attempt))}</p>${attempt.notes ? `<p class="prep-notes">${escape(attempt.notes)}</p>` : ''}` : ''}
          <div class="prep-grid prep-grid-two">
            <label class="prep-field">Correction<textarea name="correction" rows="2" maxlength="980" required></textarea></label>
            <label class="prep-field">Retest outcome<textarea name="retestOutcome" rows="2" maxlength="980" required></textarea></label>
          </div>
          ${feedback()}<div class="prep-actions"><button type="submit" class="btn btn-sm">Resolve repair</button></div></form>`;
      }).join('') : '<p class="prep-empty">No open repairs.</p>'}</section>`;
  }

  function buildRepair(form) {
    const correction = valueOf(form, 'correction').trim();
    const retestOutcome = valueOf(form, 'retestOutcome').trim();
    if (!correction || !retestOutcome) throw new Error('Record both the correction and the retest outcome.');
    const resolution = `Correction: ${correction}\nRetest outcome: ${retestOutcome}`;
    if (resolution.length > 2000) throw new Error('Keep the correction and retest outcome within 2000 characters.');
    return { resolution };
  }

  function bindRepairs() {
    root.document.querySelectorAll('#page-preparation [data-repair]').forEach(form => bindSave(form, () => ({
      url: `/api/preparation/repairs/${pathPart(form.dataset.repair)}`, body: buildRepair(form)
    }), 'Repair resolved.'));
  }

  const policyFields = [
    ['mcqAccuracy', 'MCQ accuracy (%)', 100], ['recallAccuracy', 'Recall retrieval (%)', 100],
    ['writingPercent', 'Externally reviewed writing (%)', 100], ['minMcqQuestions', 'Minimum MCQ questions', 365],
    ['minRecallItems', 'Minimum recall items', 365], ['delayedRecallDays', 'Delayed recall (days)', 365],
    ['freshDays', 'Evidence freshness (days)', 365]
  ];

  function policyMarkup() {
    return `<details class="prep-section prep-policy" id="prep-policy"${state.policyOpen ? ' open' : ''}><summary>Training targets (not selection cutoffs)</summary><form id="prep-policy-form"><div class="prep-grid prep-grid-three">${policyFields.map(([key, label, maximum]) => inputField(label, key, state.data.policy[key], `type="number" min="1" max="${maximum}" step="1" required`)).join('')}</div>${feedback()}<div class="prep-actions"><button type="submit" class="btn btn-primary">Save training targets</button></div></form></details>`;
  }

  function bindPolicy() {
    const details = root.document.getElementById('prep-policy');
    details.addEventListener('toggle', () => { state.policyOpen = details.open; });
    const form = root.document.getElementById('prep-policy-form');
    bindSave(form, () => ({
      url: '/api/preparation/policy',
      body: Object.fromEntries(policyFields.map(([key, , maximum]) => {
        const value = numericValue(form, key);
        if (!Number.isInteger(value) || value < 1 || value > maximum) throw new Error('Training targets must be integers within their allowed range.');
        return [key, value];
      }))
    }), 'Training targets saved.');
  }

  function draw() {
    const host = root.document.getElementById('preparation-content');
    const subjects = state.data.subjects;
    const subject = subjects.find(entry => entry.id === state.subjectId) || subjects[0];
    state.subjectId = subject?.id || null;
    if (!subject?.topics.some(topic => topic.id === state.topicId)) state.topicId = null;
    if (!['*', ''].includes(state.historyTopic) && !subject?.topics.some(topic => topic.id === state.historyTopic)) {
      state.historyTopic = '*';
      state.historyPage = 0;
    }
    if (!subject) {
      host.innerHTML = `<p class="prep-empty">No subjects yet.</p><button type="button" class="btn btn-sm" id="prep-go-subjects">+ Add subject</button>${policyMarkup()}`;
      host.querySelector('#prep-go-subjects').addEventListener('click', () => root.document.querySelector('.nav-item[data-page="subjects"]')?.click());
      bindPolicy();
      return;
    }
    host.innerHTML = `<div class="prep-toolbar">${selectField('Subject', 'subject', subjects.map(entry => [entry.id, entry.name]), subject.id, 'id="prep-subject"')}${iconButton('Refresh preparation', 'id="prep-refresh"', '&#8635;')}</div>
      ${strategyMarkup(subject)}${evidenceMarkup(subject)}${topicMarkup(subject)}${attemptMarkup(subject)}${repairsMarkup(subject)}${historyMarkup(subject)}${policyMarkup()}`;
    host.querySelector('#prep-subject').addEventListener('change', event => {
      state.subjectId = event.target.value;
      state.topicId = null;
      state.historyTopic = '*';
      state.historyPage = 0;
      draw();
    });
    host.querySelector('#prep-refresh').addEventListener('click', () => renderPreparation());
    bindStrategy(subject);
    drawTopicEditor(subject);
    bindAttempt(subject);
    bindHistory(subject);
    bindRepairs();
    bindPolicy();
    host.querySelector('#prep-strategy-topic').addEventListener('change', event => selectTopic(subject, event.target.value));
    host.querySelectorAll('[data-edit-topic]').forEach(button => button.addEventListener('click', () => {
      selectTopic(subject, button.dataset.editTopic);
      root.document.getElementById('prep-strategy-topic').focus();
    }));
    host.querySelectorAll('[data-topic-detail]').forEach(button => button.addEventListener('click', async () => {
      try {
        if (typeof root.showTopicDetail === 'function') await root.showTopicDetail(subject.id, button.dataset.topicDetail);
      } catch (error) {
        if (typeof root.showToast === 'function') root.showToast(error.message, 'error');
      }
    }));
  }

  async function renderPreparation(subjectId, topicId) {
    if (subjectId !== undefined) state.subjectId = subjectId;
    if (topicId !== undefined) state.topicId = topicId;
    const host = root.document.getElementById('preparation-content');
    if (!host) return;
    if (state.loading) return state.loading;
    host.setAttribute('aria-busy', 'true');
    if (!state.data) host.innerHTML = '<p class="prep-empty" role="status">Loading preparation...</p>';
    state.loading = (async () => {
      try {
        const data = await request('/api/preparation');
        if (!Array.isArray(data?.subjects) || !data.profiles || !data.policy) throw new Error('Preparation data is incomplete.');
        state.data = data;
        draw();
      } catch (error) {
        host.replaceChildren();
        const message = root.document.createElement('p');
        message.className = 'prep-error';
        message.setAttribute('role', 'alert');
        message.textContent = error.message;
        const retry = root.document.createElement('button');
        retry.type = 'button';
        retry.className = 'btn btn-sm';
        retry.textContent = 'Retry';
        retry.addEventListener('click', () => renderPreparation());
        host.append(message, retry);
      } finally {
        host.setAttribute('aria-busy', 'false');
        state.loading = null;
      }
    })();
    return state.loading;
  }

  function openPreparation(subjectId, topicId) {
    root.document.querySelectorAll('.nav-item').forEach(element => element.classList.toggle('active', element.dataset.page === 'preparation'));
    root.document.querySelectorAll('.page').forEach(element => element.classList.toggle('active', element.id === 'page-preparation'));
    if (typeof root.closeModal === 'function') root.closeModal('topic-detail');
    root.document.getElementById('preparation-title')?.focus();
    return renderPreparation(subjectId, topicId);
  }

  root.renderPreparation = renderPreparation;
  root.openPreparation = openPreparation;
  if (root.document) {
    root.document.querySelector('.nav-item[data-page="preparation"]')?.addEventListener('click', () => renderPreparation());
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { escape, localToday, request, resultText, evidenceCell, buildAttempt, buildRepair };
})(globalThis);