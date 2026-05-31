// ===========================================================================
// UPSC SPACED REPETITION TRACKER — Frontend (Flask API-backed)
// ===========================================================================

// ===== API HELPER =====
async function api(url, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  return res.json();
}

// ===== UTILITY FUNCTIONS =====
function todayStr() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function parseDate(s) {
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function daysBetween(d1, d2) {
  return Math.round((new Date(d2) - new Date(d1)) / 86400000);
}

function formatDate(dateString) {
  const d = parseDate(dateString);
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

function formatDateShort(dateString) {
  const d = parseDate(dateString);
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}

function isWeekend(dateString) {
  const dow = parseDate(dateString).getDay();
  return dow === 0 || dow === 6;
}

// ===== ROI HELPERS =====
function roiBadgeClass(roi) {
  return roi === 'very-high' ? 'red' : roi === 'high' ? 'green' : roi === 'medium' ? 'yellow' : 'orange';
}
function roiEmoji(roi) {
  return roi === 'very-high' ? '💎' : roi === 'high' ? '🔥' : roi === 'medium' ? '⚡' : '📌';
}

function addDays(dateString, days) {
  const d = parseDate(dateString);
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

// ===== NAVIGATION =====
document.querySelectorAll('.nav-item').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('page-' + btn.dataset.page).classList.add('active');
    renderPage(btn.dataset.page);
  });
});

// ===== MODAL MANAGEMENT =====
function openModal(name) { document.getElementById('modal-' + name).classList.add('show'); }
function closeModal(name) { document.getElementById('modal-' + name).classList.remove('show'); }

document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', e => {
    if (e.target === overlay) overlay.classList.remove('show');
  });
});

// ===== TOAST NOTIFICATIONS =====
function showToast(msg, type = 'success') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 2500);
}

// ===== SUBJECT MANAGEMENT =====
async function addSubject() {
  const name = document.getElementById('subj-name').value.trim();
  if (!name) { showToast('Please enter a subject name', 'warning'); return; }
  const stageChecks = document.querySelectorAll('#subj-default-stages input:checked');
  const defaultStages = [...stageChecks].map(cb => cb.value);
  const allStages = ['R1','PYQ','ERA','R3','MN','MCQ','MCQA','R7','MVA','MAINS','R30'];
  await api('/api/subjects', 'POST', {
    name,
    roi: document.getElementById('subj-roi').value,
    color: document.getElementById('subj-color').value,
    ntfyTopic: document.getElementById('subj-ntfy-topic').value.trim(),
    notes: document.getElementById('subj-notes').value.trim(),
    defaultStages: defaultStages.length < allStages.length ? defaultStages : null,
  });
  closeModal('add-subject');
  document.getElementById('subj-name').value = '';
  document.getElementById('subj-ntfy-topic').value = '';
  document.getElementById('subj-notes').value = '';
  showToast(`Subject "${name}" added!`);
  renderPage('subjects');
}

async function deleteSubject(id) {
  if (!confirm('Delete this subject and all its topics? This cannot be undone.')) return;
  await api(`/api/subjects/${id}`, 'DELETE');
  showToast('Subject deleted', 'warning');
  renderPage('subjects');
}

// ===== TOPIC MANAGEMENT =====
async function openAddTopic(subjId) {
  document.getElementById('topic-subj-id').value = subjId;
  document.getElementById('topic-name').value = '';
  document.getElementById('topic-notes').value = '';
  // Smart default: average actual hours of completed topics in this subject
  try {
    const data = await api('/api/data');
    const subj = (data.subjects || []).find(s => s.id === subjId);
    if (subj) {
      const completed = subj.topics.filter(t => (t.status === 'completed' || t.status === 'pipeline-complete') && t.estimatedHours > 0);
      if (completed.length > 0) {
        const avg = completed.reduce((sum, t) => sum + t.estimatedHours, 0) / completed.length;
        document.getElementById('topic-days').value = Math.round(avg * 2) / 2; // round to 0.5
      } else {
        document.getElementById('topic-days').value = '3';
      }
    } else {
      document.getElementById('topic-days').value = '3';
    }
  } catch(e) {
    document.getElementById('topic-days').value = '3';
  }
  openModal('add-topic');
}

async function addTopic() {
  const subjId = document.getElementById('topic-subj-id').value;
  const name = document.getElementById('topic-name').value.trim();
  if (!name) { showToast('Enter a topic name', 'warning'); return; }
  await api(`/api/subjects/${subjId}/topics`, 'POST', {
    name,
    estimatedHours: parseFloat(document.getElementById('topic-days').value) || 7.5,
    roi: document.getElementById('topic-roi').value,
    examType: document.getElementById('topic-exam-type').value,
    notes: document.getElementById('topic-notes').value.trim(),
  });
  closeModal('add-topic');
  showToast(`Topic "${name}" added!`);
  renderPage('subjects');
}

async function deleteTopic(subjId, topicId) {
  if (!confirm('Delete this topic and its revision schedule?')) return;
  await api(`/api/subjects/${subjId}/topics/${topicId}`, 'DELETE');
  showToast('Topic deleted', 'warning');
  renderPage('subjects');
}

async function editTopic(subjId, topicId) {
  // Fetch topic data directly — fully self-contained, no dependency on showTopicDetail
  const detail = await api(`/api/subjects/${subjId}/topics/${topicId}/detail`);
  if (detail.error) { showToast('Could not load topic', 'warning'); return; }

  const topic = detail.topic;
  const subj = detail.subject;
  const currentName = topic.name;
  const currentHours = topic.estimatedHours || 7.5;
  const currentRoi = topic.roi || 'medium';
  const currentExamType = topic.examType || 'both';

  const statusMap = {
    'not-started': { badge: 'badge-accent', text: 'Not Started' },
    'learning': { badge: 'badge-yellow', text: 'Currently Learning' },
    'completed': { badge: 'badge-green', text: 'Completed — Revision Active' },
    'pipeline-complete': { badge: 'badge-cyan', text: 'Pipeline Complete' }
  };
  const st = statusMap[topic.status] || statusMap['not-started'];

  const roiOptions = ['very-high', 'high', 'medium', 'low'];
  const roiLabels = { 'very-high': 'Very High ROI', 'high': 'High ROI', 'medium': 'Medium ROI', 'low': 'Low ROI' };
  const optionsHtml = roiOptions.map(r =>
    `<option value="${r}" ${r === currentRoi ? 'selected' : ''}>${roiLabels[r]}</option>`
  ).join('');
  const examTypeOptions = [
    { v: 'both',    l: 'Both (Prelims + Mains)' },
    { v: 'prelims', l: 'Prelims Only — skip MVA & MAINS' },
    { v: 'mains',   l: 'Mains Only — skip MCQ & MCQA' },
  ];
  const examTypeHtml = examTypeOptions.map(o =>
    `<option value="${o.v}" ${o.v === currentExamType ? 'selected' : ''}>${o.l}</option>`
  ).join('');

  let html = '';

  // Status info bar
  html += `<div style="margin-bottom: 14px;">
    <span class="badge ${st.badge}">${st.text}</span>
    <span class="badge badge-${roiBadgeClass(topic.roi)}" style="margin-left: 6px;">${roiEmoji(topic.roi)} ${topic.roi.toUpperCase()} ROI</span>
  </div>`;

  // Edit form
  html += `
    <div style="background:var(--card); border:1px solid var(--border); border-radius:10px; padding:16px; margin-bottom:16px;">
      <div style="font-weight:600; font-size:13px; margin-bottom:12px; color:var(--accent2);">✏️ Edit Topic</div>
      <div class="form-group" style="margin-bottom:10px;">
        <label class="form-label">Topic Name</label>
        <input type="text" class="form-input" id="edit-topic-name" value="${currentName.replace(/"/g, '&quot;')}">
      </div>
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:12px;">
        <div class="form-group" style="margin-bottom:0;">
          <label class="form-label">Est. Hours</label>
          <input type="number" class="form-input" id="edit-topic-days" value="${currentHours}" min="0.5" max="100" step="0.5">
        </div>
        <div class="form-group" style="margin-bottom:0;">
          <label class="form-label">ROI Priority</label>
          <select class="form-select" id="edit-topic-roi">${optionsHtml}</select>
        </div>
      </div>
      <div class="form-group" style="margin-bottom:12px;">
        <label class="form-label">Exam Type</label>
        <select class="form-select" id="edit-topic-exam-type">${examTypeHtml}</select>
      </div>
      <div style="display:flex; gap:8px;">
        <button class="btn btn-primary btn-sm" onclick="saveTopicEdit('${subjId}','${topicId}')">Save</button>
        <button class="btn btn-sm" onclick="showTopicDetail('${subjId}','${topicId}')">Cancel</button>
      </div>
    </div>`;

  // Set modal content and open
  document.getElementById('detail-title').textContent = `${topic.name} — ${subj.name}`;
  document.getElementById('detail-content').innerHTML = html;
  openModal('topic-detail');
  document.getElementById('edit-topic-name').focus();
  document.getElementById('edit-topic-name').select();
}

async function saveTopicEdit(subjId, topicId) {
  const name = document.getElementById('edit-topic-name').value.trim();
  const hours = parseFloat(document.getElementById('edit-topic-days').value) || 7.5;
  const roi = document.getElementById('edit-topic-roi').value;
  const examType = document.getElementById('edit-topic-exam-type').value;
  if (!name) { showToast('Name cannot be empty', 'warning'); return; }
  await api(`/api/subjects/${subjId}/topics/${topicId}`, 'PUT', { name, estimatedHours: hours, roi, examType });
  showToast('Topic updated!');
  showTopicDetail(subjId, topicId);
  renderPage('subjects');
}

async function startLearning(subjId, topicId) {
  const result = await api(`/api/subjects/${subjId}/topics/${topicId}/start`, 'POST');
  if (result.limitReached) {
    showToast(`Slot full! Complete a current topic before starting a new one. (${result.currentlyLearning}/${result.maxParallel} active)`, 'warning');
    return;
  }
  if (result.error) {
    showToast(result.error, 'warning');
    return;
  }
  showToast('Started learning!');
  renderPage('subjects');
}

async function completeLearning(subjId, topicId) {
  const result = await api(`/api/subjects/${subjId}/topics/${topicId}/complete`, 'POST');
  showToast(`"${result.topic.name}" completed! Revision schedule created.`);
  showTopicDetail(subjId, topicId);
  renderPage('subjects');
}

async function resetTopic(subjId, topicId) {
  if (!confirm('Reset this topic? All revision progress will be lost.')) return;
  await api(`/api/subjects/${subjId}/topics/${topicId}/reset`, 'POST');
  showToast('Topic reset', 'info');
  renderPage('subjects');
}

// ===== CONFIDENCE PICKER =====
function showConfidencePicker(type, onPick, onCancel) {
  document.getElementById('conf-picker')?.remove();
  document.getElementById('conf-backdrop')?.remove();

  const backdrop = document.createElement('div');
  backdrop.id = 'conf-backdrop';
  backdrop.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9998';

  const picker = document.createElement('div');
  picker.id = 'conf-picker';
  picker.style.cssText = [
    'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%)',
    'background:var(--card);border:1px solid var(--border);border-radius:14px',
    'padding:22px 24px;z-index:9999;text-align:center',
    'box-shadow:0 8px 32px rgba(0,0,0,.35);min-width:270px',
  ].join(';');
  picker.innerHTML = `
    <div style="font-size:15px;font-weight:700;margin-bottom:4px;color:var(--text1)">${type} — How was it?</div>
    <div style="font-size:11px;color:var(--text3);margin-bottom:18px">Rate your recall to tune the next review interval</div>
    <div style="display:flex;gap:10px;justify-content:center">
      <button id="conf-hard" style="padding:9px 16px;border-radius:9px;border:none;background:#c0392b;color:#fff;cursor:pointer;font-size:13px;font-weight:700">😰 Hard</button>
      <button id="conf-okay" style="padding:9px 16px;border-radius:9px;border:none;background:#d68910;color:#fff;cursor:pointer;font-size:13px;font-weight:700">😐 Okay</button>
      <button id="conf-easy" style="padding:9px 16px;border-radius:9px;border:none;background:#1e8449;color:#fff;cursor:pointer;font-size:13px;font-weight:700">😊 Easy</button>
    </div>
    <div style="margin-top:12px;font-size:10px;color:var(--text3)">Hard → shorter interval · Easy → longer interval</div>
  `;

  const cleanup = () => {
    document.getElementById('conf-picker')?.remove();
    document.getElementById('conf-backdrop')?.remove();
  };

  picker.querySelector('#conf-hard').onclick = () => { cleanup(); onPick(1); };
  picker.querySelector('#conf-okay').onclick = () => { cleanup(); onPick(2); };
  picker.querySelector('#conf-easy').onclick = () => { cleanup(); onPick(3); };
  backdrop.onclick = () => { cleanup(); if (onCancel) onCancel(); };

  document.body.appendChild(backdrop);
  document.body.appendChild(picker);
}

// ===== REVISION TOGGLE =====
async function toggleRevision(topicId, type) {
  const data = await api('/api/data');
  const key = `${topicId}_${type}`;
  if (data.completedRevisions && data.completedRevisions[key]) {
    await api('/api/revisions/unmark', 'POST', { topicId, type });
    renderAll();
  } else {
    const ratesConfidence = ['R1', 'R3', 'R7'].includes(type);
    if (ratesConfidence) {
      showConfidencePicker(type, async (confidence) => {
        await api('/api/revisions/mark', 'POST', { topicId, type, confidence });
        const label = confidence === 1 ? 'Hard' : confidence === 3 ? 'Easy' : 'Okay';
        showToast(`${type} done! (${label})`);
        renderAll();
      });
    } else {
      await api('/api/revisions/mark', 'POST', { topicId, type, confidence: 2 });
      showToast(`${type} marked done!`);
      renderAll();
    }
  }
}

async function toggleHoliday(dateStr) {
  const result = await api('/api/holidays/toggle', 'POST', { date: dateStr });
  if (result.error) { showToast(result.error, 'warning'); return; }
  showToast(result.isHoliday ? `${dateStr} → 12hr day` : `${dateStr} → back to normal`, result.isHoliday ? 'success' : 'warning');
  renderAll();
}

async function markRevisionDone(topicId, type) {
  const ratesConfidence = ['R1', 'R3', 'R7'].includes(type);
  if (ratesConfidence) {
    showConfidencePicker(type, async (confidence) => {
      await api('/api/revisions/mark', 'POST', { topicId, type, confidence });
      const label = confidence === 1 ? 'Hard' : confidence === 3 ? 'Easy' : 'Okay';
      showToast(`${type} done! (${label})`);
      renderAll();
    });
  } else {
    await api('/api/revisions/mark', 'POST', { topicId, type, confidence: 2 });
    showToast(`${type} marked done!`);
    renderAll();
  }
}

// ===== SHOW TOPIC DETAIL / TIMELINE =====
async function showTopicDetail(subjId, topicId) {
  const detail = await api(`/api/subjects/${subjId}/topics/${topicId}/detail`);
  if (detail.error) return;

  const topic = detail.topic;
  const subj = detail.subject;
  const schedule = detail.schedule;

  document.getElementById('detail-title').textContent = `${topic.name} — ${subj.name}`;

  let html = '';

  // Status info
  const statusMap = {
    'not-started': { badge: 'badge-accent', text: 'Not Started' },
    'learning': { badge: 'badge-yellow', text: 'Currently Learning' },
    'completed': { badge: 'badge-green', text: 'Completed — Revision Active' },
    'pipeline-complete': { badge: 'badge-cyan', text: 'Pipeline Complete' }
  };
  const st = statusMap[topic.status];
  html += `<div style="margin-bottom: 14px;">
    <span class="badge ${st.badge}">${st.text}</span>
    <span class="badge badge-${roiBadgeClass(topic.roi)}" style="margin-left: 6px;">${roiEmoji(topic.roi)} ${topic.roi.toUpperCase()} ROI</span>
  </div>`;

  if (topic.notes) {
    html += `<div style="font-size:12px; color: var(--text2); margin-bottom: 14px; padding: 10px; background: var(--bg); border-radius: 6px;">${topic.notes}</div>`;
  }

  if (topic.startDate) html += `<div style="font-size:12px; color:var(--text2); margin-bottom:4px;">Started: ${formatDate(topic.startDate)}</div>`;
  if (topic.completionDate) html += `<div style="font-size:12px; color:var(--text2); margin-bottom:14px;">Completed: ${formatDate(topic.completionDate)}</div>`;

  // Estimated timeline (for not-started and learning topics)
  const estimate = detail.estimate;
  if (estimate && estimate.isEstimate) {
    html += `<div style="background: rgba(99,102,241,0.08); border: 1px solid rgba(99,102,241,0.15); border-radius: 8px; padding: 14px; margin-bottom: 16px;">`;
    html += `<div style="font-weight:600; font-size:13px; color:var(--accent2); margin-bottom:10px;">📊 Progressive Time Estimate</div>`;
    if (estimate.queuePosition) {
      html += `<div style="font-size:12px; color:var(--text2); margin-bottom:6px;">Queue Position: <strong>#${estimate.queuePosition}</strong> (${MAX_PARALLEL || 2} topics run in parallel)</div>`;
    }
    const daysToMastery = daysBetween(todayStr(), estimate.masteryDate);

    html += `<div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px; margin-bottom:10px;">
      <div style="text-align:center; padding:8px; background:var(--bg); border-radius:6px;">
        <div style="font-size:10px; color:var(--text3); text-transform:uppercase; letter-spacing:0.5px;">Start</div>
        <div style="font-size:13px; font-weight:600; color:var(--accent2); margin-top:2px;">${formatDateShort(estimate.startDate)}</div>
      </div>
      <div style="text-align:center; padding:8px; background:var(--bg); border-radius:6px;">
        <div style="font-size:10px; color:var(--text3); text-transform:uppercase; letter-spacing:0.5px;">Completion</div>
        <div style="font-size:13px; font-weight:600; color:var(--yellow); margin-top:2px;">${formatDateShort(estimate.completionDate)}</div>
      </div>
      <div style="text-align:center; padding:8px; background:var(--bg); border-radius:6px;">
        <div style="font-size:10px; color:var(--text3); text-transform:uppercase; letter-spacing:0.5px;">Mastery</div>
        <div style="font-size:13px; font-weight:600; color:var(--green); margin-top:2px;">${formatDateShort(estimate.masteryDate)}</div>
      </div>
    </div>`;

    html += `<div style="font-size:11px; color:var(--text3);">~${daysToMastery} days from today to full mastery (learning + 12 revision stages)</div>`;

    // Show estimated revision stages
    if (estimate.revisionSchedule) {
      const stageLabels = {r1: 'R1 · 1st Revision', pyq: 'PYQ · Practice', era: 'ERA · Error Analysis', r3: 'R3 · 2nd Revision', mn: 'MN · Micro Notes', mcq: 'MCQ · Practice', mcqa: 'MCQA · MCQ Analysis', r7: 'R7 · 3rd Revision', mva: 'MVA · Value Addition', mains: 'MAINS · Writing', r30: 'R30 · Final'};
      const stageColors = {r1: 'var(--red)', pyq: 'var(--cyan)', era: 'var(--pink)', r3: 'var(--orange)', mn: 'var(--lime)', ca: 'var(--purple)', mcq: 'var(--teal)', mcqa: 'var(--indigo)', r7: 'var(--yellow)', mva: 'var(--emerald)', mains: 'var(--accent)', r30: 'var(--blue)'};
      html += `<div style="margin-top:10px; display:flex; flex-wrap:wrap; gap:6px;">`;
      for (const [key, date] of Object.entries(estimate.revisionSchedule)) {
        html += `<span style="font-size:10px; padding:3px 8px; border-radius:4px; background:var(--bg); border-left:3px solid ${stageColors[key] || 'var(--text3)'};">
          ${stageLabels[key] || key}: <strong>${formatDateShort(date)}</strong>
        </span>`;
      }
      html += `</div>`;
    }

    html += `</div>`;
  }

  // Study Progress (for learning topics)
  if (topic.status === 'learning') {
    const logged = detail.loggedHours || 0;
    const remaining = detail.remainingHours || topic.estimatedHours;
    const pct = topic.estimatedHours > 0 ? Math.min(100, Math.round(logged / topic.estimatedHours * 100)) : 0;
    html += `<div style="background:var(--bg); border-radius:8px; padding:12px; margin-bottom:14px;">
      <div style="font-weight:600; font-size:13px; margin-bottom:8px;">Study Progress</div>
      <div class="progress-bar" style="height:8px; margin-bottom:6px;"><div class="progress-fill" style="width:${pct}%; background:var(--accent2);"></div></div>
      <div style="font-size:11px; color:var(--text2);">${logged}h logged / ${topic.estimatedHours}h estimated (${pct}%) — ${remaining}h remaining</div>
    </div>`;
  }

  // Timeline — only show active stages
  if (schedule) {
    const resolvedStages = detail.resolvedStages || [];
    html += `<div style="font-weight:600; font-size:14px; margin-bottom:12px;">Revision Timeline <span style="font-size:11px; font-weight:400; color:var(--text3);">(${resolvedStages.length} stages active)</span></div>`;
    html += `<div class="timeline-track">`;

    const keyMap = {R1:'r1',PYQ:'pyq',ERA:'era',R3:'r3',MN:'mn',CA:'ca',MCQ:'mcq',MCQA:'mcqa',R7:'r7',MVA:'mva',MAINS:'mains',R30:'r30'};
    resolvedStages.forEach(stageCode => {
      const key = keyMap[stageCode];
      const step = schedule[key];
      if (!step) return;
      const nodeClass = step.done ? 'done' : (step.isToday || step.overdue) ? 'active' : 'pending';
      const dateLabel = step.isToday ? 'TODAY' : formatDate(step.date);
      const overdueTag = step.overdue ? '<span class="badge badge-red" style="font-size:9px">OVERDUE</span>' : '';

      html += `<div class="timeline-node ${nodeClass}">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div>
            <div style="font-size:13px; font-weight:600;">${step.label} ${overdueTag}</div>
            <div style="font-size:11px; color:var(--text3); margin-top:2px;">${dateLabel}</div>
          </div>
          <div>
            ${step.done
              ? '<span class="badge badge-green">Done</span>'
              : `<button class="btn btn-sm btn-success" onclick="markRevisionDone('${topic.id}','${step.type}');setTimeout(()=>showTopicDetail('${subjId}','${topicId}'),300);">Mark Done</button>`
            }
          </div>
        </div>
      </div>`;
    });
    html += `</div>`;
  }

  // Active Stages Customization
  const allStages = ['R1','PYQ','ERA','R3','MN','MCQ','MCQA','R7','MVA','MAINS','R30'];
  const activeStages = detail.resolvedStages || allStages;
  html += `<details style="margin-top:14px; margin-bottom:14px;">
    <summary style="font-size:13px; font-weight:600; cursor:pointer; color:var(--text2);">Customize Active Stages</summary>
    <div style="display:flex; flex-wrap:wrap; gap:6px; margin-top:10px;" id="stage-picker-${topicId}">`;
  allStages.forEach(s => {
    const checked = activeStages.includes(s);
    html += `<label style="display:flex; align-items:center; gap:4px; font-size:12px; padding:4px 8px; background:var(--bg); border-radius:4px; cursor:pointer;">
      <input type="checkbox" value="${s}" ${checked ? 'checked' : ''} style="accent-color:var(--accent);"> ${s}
    </label>`;
  });
  html += `</div>
    <button class="btn btn-sm btn-primary" style="margin-top:8px;" onclick="saveTopicStages('${subjId}','${topicId}')">Save Stages</button>
  </details>`;

  // CA Links
  const links = topic.links || [];
  html += `<div style="margin-top:14px;">
    <div style="font-weight:600; font-size:14px; margin-bottom:10px;">Current Affairs Links <span class="badge badge-cyan" style="font-size:10px;">${links.length}</span></div>`;
  const readCount = links.filter(l => l.read).length;
  if (links.length > 0) {
    html += `<div style="font-size:11px; color:var(--text3); margin-bottom:6px;">${readCount}/${links.length} read</div>`;
    links.forEach(link => {
      const readStyle = link.read ? 'opacity:0.6;' : '';
      const titleStyle = link.read ? 'text-decoration:line-through;' : '';
      html += `<div style="display:flex; align-items:center; padding:8px 10px; background:var(--bg); border-radius:6px; margin-bottom:6px; ${readStyle}">
        <div class="task-check ${link.read ? 'done' : ''}" style="width:18px; height:18px; margin-right:8px; cursor:pointer; flex-shrink:0;" onclick="toggleLinkRead('${subjId}','${topicId}','${link.id}')"></div>
        <div style="min-width:0; flex:1;">
          <a href="${link.url}" target="_blank" style="font-size:12px; color:var(--accent2); text-decoration:none; display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; ${titleStyle}">${link.title || link.url}</a>
          <div style="font-size:10px; color:var(--text3);">${link.dateAdded}</div>
        </div>
        <button class="btn btn-sm btn-danger" style="margin-left:8px; padding:2px 6px; font-size:10px;" onclick="deleteLink('${subjId}','${topicId}','${link.id}')">x</button>
      </div>`;
    });
  }
  html += `<div style="display:flex; gap:6px; margin-top:8px;">
    <input type="text" id="link-url-${topicId}" placeholder="Paste URL" class="form-input" style="flex:2; font-size:11px;">
    <input type="text" id="link-title-${topicId}" placeholder="Title" class="form-input" style="flex:1; font-size:11px;">
    <button class="btn btn-sm btn-primary" onclick="addLink('${subjId}','${topicId}')">Add</button>
  </div></div>`;

  // Related Topics
  const related = detail.relatedTopics || [];
  html += `<div style="margin-top:14px;">
    <div style="font-weight:600; font-size:14px; margin-bottom:10px;">Related Topics <span class="badge badge-purple" style="font-size:10px;">${related.length}</span></div>`;
  if (related.length > 0) {
    related.forEach(r => {
      html += `<div style="display:flex; justify-content:space-between; align-items:center; padding:6px 10px; background:var(--bg); border-radius:6px; margin-bottom:4px;">
        <span style="font-size:12px; cursor:pointer; color:var(--text1);" onclick="showTopicDetail('${r.subjectId}','${r.topicId}')">
          <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:${r.subjectColor}; margin-right:6px;"></span>${r.topicName} <span style="color:var(--text3); font-size:10px;">${r.subjectName}</span>
        </span>
        <button class="btn btn-sm btn-danger" style="padding:2px 6px; font-size:10px;" onclick="removeRelated('${subjId}','${topicId}','${r.topicId}')">x</button>
      </div>`;
    });
  }
  html += `<div style="display:flex; gap:6px; margin-top:8px;">
    <select id="related-select-${topicId}" class="form-select" style="flex:1; font-size:11px;">
      <option value="">Select a topic...</option>
    </select>
    <button class="btn btn-sm btn-primary" onclick="addRelated('${subjId}','${topicId}')">Link</button>
  </div></div>`;

  // Actions
  html += `<div style="margin-top:16px; display:flex; gap:8px; flex-wrap:wrap;">`;
  if (topic.status === 'not-started') {
    const preData = await api('/api/data');
    const currentLearning = preData.subjects.reduce((sum, s) => sum + s.topics.filter(t => t.status === 'learning').length, 0);
    const maxSlots = 3;
    if (currentLearning < maxSlots) {
      html += `<button class="btn btn-primary btn-sm" onclick="startLearning('${subjId}','${topicId}');setTimeout(()=>showTopicDetail('${subjId}','${topicId}'),300);">Start Learning</button>`;
    } else {
      html += `<button class="btn btn-sm" disabled style="opacity:0.45;cursor:not-allowed;" title="Complete a learning topic first (${currentLearning}/${maxSlots} slots used)">🔒 Start Learning (${currentLearning}/${maxSlots} slots full)</button>`;
    }
  }
  if (topic.status === 'learning') {
    html += `<button class="btn btn-success btn-sm" onclick="completeLearning('${subjId}','${topicId}');">Mark as Completed</button>`;
  }
  html += `<button class="btn btn-sm" onclick="editTopic('${subjId}','${topicId}')" style="margin-right:auto;">✏️ Edit</button>`;
  html += `<button class="btn btn-danger btn-sm" onclick="resetTopic('${subjId}','${topicId}');closeModal('topic-detail');">Reset</button>`;
  html += `<button class="btn btn-danger btn-sm" onclick="deleteTopic('${subjId}','${topicId}');closeModal('topic-detail');">Delete</button>`;
  html += `</div>`;

  document.getElementById('detail-content').innerHTML = html;
  openModal('topic-detail');

  // Populate related topic dropdown (async after render)
  const allData = await api('/api/data');
  const sel = document.getElementById(`related-select-${topicId}`);
  if (sel) {
    const existingIds = new Set((topic.relatedTopicIds || []).concat([topicId]));
    allData.subjects.forEach(s => {
      s.topics.forEach(t => {
        if (!existingIds.has(t.id)) {
          const opt = document.createElement('option');
          opt.value = t.id;
          opt.textContent = `${t.name} (${s.name})`;
          sel.appendChild(opt);
        }
      });
    });
  }
}

async function saveTopicStages(subjId, topicId) {
  const container = document.getElementById(`stage-picker-${topicId}`);
  const checked = [...container.querySelectorAll('input:checked')].map(cb => cb.value);
  await api(`/api/subjects/${subjId}/topics/${topicId}`, 'PUT', { activeStages: checked.length > 0 ? checked : null });
  showToast('Stages updated!');
  showTopicDetail(subjId, topicId);
}

async function addLink(subjId, topicId) {
  const url = document.getElementById(`link-url-${topicId}`).value.trim();
  const title = document.getElementById(`link-title-${topicId}`).value.trim();
  if (!url) { showToast('Enter a URL', 'warning'); return; }
  await api(`/api/subjects/${subjId}/topics/${topicId}/links`, 'POST', { url, title: title || url });
  showTopicDetail(subjId, topicId);
}

async function toggleLinkRead(subjId, topicId, linkId) {
  await api(`/api/subjects/${subjId}/topics/${topicId}/links/${linkId}/toggle-read`, 'POST');
  showTopicDetail(subjId, topicId);
}

async function deleteLink(subjId, topicId, linkId) {
  await api(`/api/subjects/${subjId}/topics/${topicId}/links/${linkId}`, 'DELETE');
  showTopicDetail(subjId, topicId);
}

async function addRelated(subjId, topicId) {
  const sel = document.getElementById(`related-select-${topicId}`);
  const relatedId = sel.value;
  if (!relatedId) { showToast('Select a topic', 'warning'); return; }
  await api(`/api/subjects/${subjId}/topics/${topicId}/related`, 'POST', { relatedTopicId: relatedId });
  showTopicDetail(subjId, topicId);
}

async function removeRelated(subjId, topicId, relatedId) {
  await api(`/api/subjects/${subjId}/topics/${topicId}/related/${relatedId}`, 'DELETE');
  showTopicDetail(subjId, topicId);
}

async function logStudyHours(topicId, hours) {
  const h = parseFloat(hours);
  if (!h || h <= 0) { showToast('Enter valid hours', 'warning'); return; }
  await api('/api/study-logs', 'POST', { topicId, hours: h });
  showToast(`Logged ${h}h!`, 'success');
  // Re-render today page to update time budget live
  renderToday();
}

// ===== RENDER HELPERS =====
function renderTimeBudgetActivities(activities) {
  const pending = activities.filter(a => !a.done);
  if (pending.length === 0) return '';
  const colors = {revision: 'var(--red)', learning: 'var(--accent2)', cumulative_sectional: 'var(--purple)', cumulative_subject: 'var(--cyan)', subject_cycle: 'var(--emerald)'};
  const items = pending.map(a => {
    let label;
    if (a.category === 'revision') label = a.revType + ' · ' + a.topicName;
    else if (a.category === 'learning') label = '📖 ' + a.topicName;
    else if (a.category === 'cumulative_sectional') label = '🔄 Sectional R' + a.round;
    else if (a.category === 'subject_cycle') label = '📚 ' + (a.label || a.subjectName);
    else label = '🔄 ' + a.subjectName + ' R' + a.round;
    const color = colors[a.category] || 'var(--text3)';
    const warn = a.overdue ? ' ⚠️' : '';
    return '<span style="font-size:10px; padding:2px 6px; border-radius:3px; background:var(--bg); border-left:3px solid ' + color + ';">' + label + ' <strong>' + a.hours + 'h</strong>' + warn + '</span>';
  });
  return '<div style="margin-top:10px; display:flex; flex-wrap:wrap; gap:4px;">' + items.join('') + '</div>';
}

function renderTaskItem(t) {
  const typeColors = { R1: 'red', PYQ: 'cyan', ERA: 'pink', R3: 'orange', MN: 'lime', CA: 'purple', MCQ: 'teal', MCQA: 'indigo', R7: 'yellow', MVA: 'emerald', R30: 'blue', MAINS: 'accent' };
  return `<div class="task-item ${t.overdue ? 'overdue' : ''}" style="cursor:pointer;" onclick="showTopicDetail('${t.subjectId}','${t.topicId}')">
    <div class="task-check ${t.done ? 'done' : ''}" onclick="event.stopPropagation();toggleRevision('${t.topicId}','${t.type}')"></div>
    <div class="task-info">
      <div class="task-name ${t.done ? 'done-text' : ''}">${t.topicName}</div>
      <div class="task-meta">${t.subjectName} · ${t.label}${t.overdue ? ' · <span style="color:var(--red)">OVERDUE (' + formatDateShort(t.date) + ')</span>' : ''}</div>
    </div>
    <span class="badge badge-${typeColors[t.type] || 'accent'} task-badge">${t.type}</span>
  </div>`;
}

// ===== RENDER: DASHBOARD =====
async function renderDashboard() {
  const [data, timeline] = await Promise.all([api('/api/dashboard'), api('/api/timeline-estimate')]);
  const today = data.today;
  const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  const dow = parseDate(today).getDay();
  const dayType = data.isWeekend;
  const dashHoliday = data.isHoliday;
  const dashLabel = dashHoliday ? '12HR DAY - Extended Session' : dayType ? 'WEEKEND - Extended Session' : 'WEEKDAY';

  document.getElementById('dash-day-type').innerHTML = `
    <span>${dayNames[dow]}, ${formatDate(today)}</span>
    <span class="day-type-badge ${dayType ? 'weekend-badge' : 'weekday-badge'}">${dashLabel}</span>
  `;

  const s = data.stats;
  document.getElementById('dash-stats').innerHTML = `
    <div class="stat-card blue"><div class="stat-label">Total Topics</div><div class="stat-value">${s.totalTopics}</div><div class="stat-sub">${data.learningTopics ? data.learningTopics.length : 0} subjects</div></div>
    <div class="stat-card green"><div class="stat-label">Completed</div><div class="stat-value">${s.completed}</div><div class="stat-sub">learning: ${s.learning}</div></div>
    <div class="stat-card orange"><div class="stat-label">Due Today</div><div class="stat-value">${s.todayTasks}</div><div class="stat-sub">${s.todayDone} done</div></div>
    <div class="stat-card red"><div class="stat-label">Overdue</div><div class="stat-value">${s.overdue}</div><div class="stat-sub">catch up needed</div></div>
    <div class="stat-card accent"><div class="stat-label">Revisions Done</div><div class="stat-value">${s.totalRevisions}</div><div class="stat-sub">total all-time</div></div>
  `;

  document.getElementById('dash-due-count').textContent = s.todayTasks + s.overdue;

  // Exam Countdown
  const examEl = document.getElementById('dash-exam-countdown');
  if (examEl) {
    const ei = data.examInfo || {};
    const dte = ei.daysToExam || {};
    if (dte.prelims !== undefined || dte.mains !== undefined) {
      let html = '<div style="display:flex; gap:12px; flex-wrap:wrap;">';
      if (dte.prelims !== undefined) {
        const col = dte.prelims <= 30 ? 'var(--red)' : dte.prelims <= 90 ? 'var(--orange)' : 'var(--green)';
        html += `<div class="stat-card" style="border-left-color:${col}; flex:1; min-width:140px;"><div class="stat-label">Prelims</div><div class="stat-value" style="color:${col}">${dte.prelims}d</div><div class="stat-sub">${ei.examDates.prelims}</div></div>`;
      }
      if (dte.mains !== undefined) {
        const col = dte.mains <= 60 ? 'var(--red)' : dte.mains <= 120 ? 'var(--orange)' : 'var(--green)';
        html += `<div class="stat-card" style="border-left-color:${col}; flex:1; min-width:140px;"><div class="stat-label">Mains</div><div class="stat-value" style="color:${col}">${dte.mains}d</div><div class="stat-sub">${ei.examDates.mains}</div></div>`;
      }
      html += '</div>';
      const ms = ei.milestones || {};
      if (ms.r3Window) {
        const r3days = Math.ceil((new Date(ms.r3Window) - new Date(today)) / 86400000);
        const r4days = Math.ceil((new Date(ms.r4Window) - new Date(today)) / 86400000);
        html += `<div style="display:flex; gap:8px; margin-top:8px; flex-wrap:wrap;">`;
        html += `<span class="badge badge-orange" style="font-size:11px;">R3 window in ${r3days}d</span>`;
        html += `<span class="badge badge-red" style="font-size:11px;">R4 window in ${r4days}d</span>`;
        html += `</div>`;
      }
      // Feasibility warnings
      const feas = ei.feasibility || {};
      if (feas.warnings && feas.warnings.length > 0) {
        const statusColor = feas.status === 'behind' ? 'var(--red)' : 'var(--green)';
        const statusLabel = feas.status === 'behind' ? 'BEHIND SCHEDULE' : 'ON TRACK';
        html += `<div style="margin-top:12px; padding:10px 14px; background:${feas.status === 'behind' ? 'var(--red-bg, rgba(239,68,68,0.1))' : 'var(--green-bg, rgba(34,197,94,0.1))'}; border-left:3px solid ${statusColor}; border-radius:6px;">`;
        html += `<div style="font-weight:600; font-size:13px; color:${statusColor}; margin-bottom:6px;">${statusLabel}</div>`;
        feas.warnings.forEach(w => {
          html += `<div style="font-size:12px; color:var(--text2); margin-bottom:4px;">
            <span style="color:var(--red); margin-right:4px;">!</span> ${w.message}
          </div>`;
          if (w.topics && w.topics.length > 0) {
            html += `<div style="font-size:11px; color:var(--text3); margin-left:16px; margin-bottom:4px;">${w.topics.slice(0,5).join(', ')}${w.topics.length > 5 ? ` +${w.topics.length-5} more` : ''}</div>`;
          }
        });
        html += `</div>`;
      } else if (dte.prelims !== undefined) {
        html += `<div style="margin-top:12px; padding:8px 14px; background:var(--green-bg, rgba(34,197,94,0.1)); border-left:3px solid var(--green); border-radius:6px; font-size:12px; color:var(--green); font-weight:600;">ON TRACK</div>`;
      }
      examEl.innerHTML = html;
    } else {
      examEl.innerHTML = '<div style="font-size:12px; color:var(--text3);">Set exam dates in Settings for countdown</div>';
    }
  }

  // Time Budget Card
  const tb = data.timeBudget;
  if (tb) {
    const pct = tb.utilization;
    const barColor = tb.overloaded ? 'var(--red)' : pct > 80 ? 'var(--yellow)' : 'var(--green)';
    const spillover = tb.spilloverHours || 0;
    const spillItems = tb.spilloverItems || [];
    const statusText = tb.overloaded
      ? `<span style="color:var(--red); font-weight:600;">OVERLOADED by ${tb.overloadHours}h</span>`
      : `<span style="color:var(--green);">${tb.remaining}h free</span>`;
    const spillDetail = spillItems.map(s => `${s.label} ${s.hours}h`).join(', ');
    const spilloverText = spillover > 0
      ? `<div style="margin-top:8px; padding:6px 10px; background:rgba(255,165,0,0.1); border-left:3px solid var(--orange, orange); border-radius:4px; font-size:11px; color:var(--text2);">
          ↪ <strong>${spillover}h</strong> spills to tomorrow: ${spillDetail}
        </div>`
      : '';

    document.getElementById('dash-time-budget').innerHTML = `
      <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:10px; margin-bottom:12px;">
        <div style="text-align:center; padding:8px; background:var(--bg); border-radius:6px;">
          <div style="font-size:10px; color:var(--text3); text-transform:uppercase;">Budget</div>
          <div style="font-size:18px; font-weight:700; color:var(--text1);">${tb.budget}h</div>
        </div>
        <div style="text-align:center; padding:8px; background:var(--bg); border-radius:6px;">
          <div style="font-size:10px; color:var(--text3); text-transform:uppercase;">Revisions</div>
          <div style="font-size:18px; font-weight:700; color:var(--red);">${tb.revisionHours}h</div>
        </div>
        <div style="text-align:center; padding:8px; background:var(--bg); border-radius:6px;">
          <div style="font-size:10px; color:var(--text3); text-transform:uppercase;">Learning</div>
          <div style="font-size:18px; font-weight:700; color:var(--accent2);">${tb.learningHours}h</div>
          ${spillover > 0 ? `<div style="font-size:9px; color:orange;">+${spillover}h tmrw</div>` : ''}
        </div>
        <div style="text-align:center; padding:8px; background:var(--bg); border-radius:6px;">
          <div style="font-size:10px; color:var(--text3); text-transform:uppercase;">Cumulative</div>
          <div style="font-size:18px; font-weight:700; color:var(--purple);">${tb.cumulativeHours}h</div>
        </div>
      </div>
      <div style="background:var(--bg2); border-radius:4px; height:8px; overflow:hidden; margin-bottom:8px;">
        <div style="height:100%; width:${Math.min(100, pct)}%; background:${barColor}; border-radius:4px; transition:width 0.3s;"></div>
      </div>
      <div style="display:flex; justify-content:space-between; font-size:11px; color:var(--text3);">
        <span>${tb.totalHours}h / ${tb.budget}h used (${pct}%)</span>
        ${statusText}
      </div>
      ${spilloverText}
      ${tb.activities && tb.activities.length > 0 ? renderTimeBudgetActivities(tb.activities) : ''}
    `;
  }

  // Due today + overdue
  const allDue = [...data.overdueTasks, ...data.todayTasks];
  if (allDue.length === 0) {
    document.getElementById('dash-due-list').innerHTML = '<div class="empty-state"><div class="empty-state-text">All caught up! Nothing due today.</div></div>';
  } else {
    document.getElementById('dash-due-list').innerHTML = allDue.map(t => renderTaskItem(t)).join('');
  }

  // Currently learning
  const learningTopics = data.learningTopics;
  if (!learningTopics || learningTopics.length === 0) {
    document.getElementById('dash-learning-list').innerHTML = '<div class="empty-state"><div class="empty-state-text">No topics in progress.<br>Go to Subjects to start learning!</div></div>';
  } else {
    document.getElementById('dash-learning-list').innerHTML = learningTopics.map(t => {
      const daysIn = daysBetween(t.startDate, today);
      return `<div class="task-item" style="cursor:pointer;" onclick="showTopicDetail('${t.subjectId}','${t.id}')">
        <div style="width: 4px; height: 32px; border-radius: 2px; background: ${t.subjectColor};"></div>
        <div class="task-info">
          <div class="task-name">${t.name}</div>
          <div class="task-meta">${t.subjectName} · ${t.estimatedHours || '?'}h est. · ${t.roi} ROI</div>
        </div>
        <button class="btn btn-sm btn-success" onclick="event.stopPropagation();completeLearning('${t.subjectId}','${t.id}');">Done</button>
      </div>`;
    }).join('');
  }

  // Upcoming 7 days
  let upcomingHtml = '';
  if (data.upcoming) {
    const sortedDates = Object.keys(data.upcoming).sort();
    sortedDates.forEach(d => {
      const tasks = data.upcoming[d];
      const dayName = dayNames[parseDate(d).getDay()].slice(0, 3);
      upcomingHtml += `<div style="margin-bottom:10px;">
        <div style="font-size:12px; font-weight:600; color:var(--text2); margin-bottom:6px;">${dayName}, ${formatDateShort(d)} — ${tasks.length} task(s)</div>
        ${tasks.map(t => `<div style="font-size:12px; padding:4px 0; display:flex; align-items:center; gap:8px;">
          <span class="badge badge-${({R1:'red',PYQ:'cyan',ERA:'pink',R3:'orange',MN:'lime',CA:'purple',MCQ:'teal',MCQA:'indigo',R7:'yellow',MVA:'emerald',R30:'blue',MAINS:'accent'})[t.type] || 'accent'}" style="font-size:10px">${t.type}</span>
          <span>${t.topicName}</span>
          <span style="color:var(--text3)"> · ${t.subjectName}</span>
        </div>`).join('')}
      </div>`;
    });
  }
  document.getElementById('dash-upcoming-list').innerHTML = upcomingHtml || '<div style="font-size:13px; color:var(--text3); padding:20px; text-align:center;">No upcoming tasks in the next 7 days</div>';

  // Cumulative revision alerts on dashboard
  const cumUpcoming = data.cumulativeUpcoming || [];
  if (cumUpcoming.length > 0) {
    const cumCard = document.querySelector('#dash-cumulative-card');
    let cumHtml = '';
    cumUpcoming.forEach(s => {
      const daysUntil = daysBetween(today, s.date);
      const isOverdue = s.overdue;
      const label = s.type === 'sectional'
        ? `Sectional Batch (${s.topicCount} topics) · Round ${s.round}`
        : `${s.subjectName} — Full Subject · Round ${s.round}`;
      cumHtml += `<div class="task-item ${isOverdue ? 'overdue' : ''}" style="cursor:pointer;" onclick="document.querySelector('[data-page=cumulative]').click();">
        <div style="width: 4px; height: 32px; border-radius: 2px; background: ${s.type === 'sectional' ? 'var(--accent)' : 'var(--cyan)'};"></div>
        <div class="task-info">
          <div class="task-name">${label}</div>
          <div class="task-meta">${formatDate(s.date)} · ${isOverdue ? '<span style="color:var(--red);">OVERDUE</span>' : s.isToday ? '<span style="color:var(--green);font-weight:600;">TODAY</span>' : `${daysUntil} days away`}</div>
        </div>
        <span class="badge badge-${s.type === 'sectional' ? 'accent' : 'cyan'}">${s.type === 'sectional' ? 'SECTIONAL' : 'SUBJECT'}</span>
      </div>`;
    });
    document.getElementById('dash-cumulative-list').innerHTML = cumHtml;
    document.getElementById('dash-cumulative-card').style.display = 'block';
  } else {
    document.getElementById('dash-cumulative-card').style.display = 'none';
  }

  // Timeline estimator summary on dashboard
  const tlSummary = timeline.summary || {};
  const tlEstimates = timeline.estimates || {};
  const dashTlCard = document.getElementById('dash-timeline-card');
  if (tlSummary.inPipeline > 0) {
    const nextTopics = Object.values(tlEstimates)
      .filter(e => e.status === 'not-started' || e.status === 'learning')
      .sort((a, b) => (a.masteryDate || '').localeCompare(b.masteryDate || ''))
      .slice(0, 5);

    let tlHtml = `<div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px; margin-bottom:12px;">
      <div style="text-align:center; padding:8px; background:var(--bg); border-radius:6px;">
        <div style="font-size:10px; color:var(--text3);">IN PIPELINE</div>
        <div style="font-size:18px; font-weight:700; color:var(--accent2);">${tlSummary.inPipeline}</div>
      </div>
      <div style="text-align:center; padding:8px; background:var(--bg); border-radius:6px;">
        <div style="font-size:10px; color:var(--text3);">PARALLEL SLOTS</div>
        <div style="font-size:18px; font-weight:700; color:var(--text1);">${tlSummary.parallelSlots}</div>
      </div>
      <div style="text-align:center; padding:8px; background:var(--bg); border-radius:6px;">
        <div style="font-size:10px; color:var(--text3);">ALL DONE BY</div>
        <div style="font-size:13px; font-weight:600; color:var(--green); margin-top:2px;">${tlSummary.overallFinishDate ? formatDateShort(tlSummary.overallFinishDate) : '—'}</div>
      </div>
    </div>`;
    nextTopics.forEach(t => {
      const statusIcon = t.status === 'learning' ? '📖' : '⏳';
      const daysLeft = daysBetween(today, t.masteryDate);
      tlHtml += `<div style="display:flex; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid var(--bg2);">
        <span>${statusIcon}</span>
        <div style="flex:1; min-width:0;">
          <div style="font-size:12px; font-weight:500; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${t.topicName}</div>
          <div style="font-size:10px; color:var(--text3);">${t.subjectName} · Mastery ~${formatDateShort(t.masteryDate)}</div>
        </div>
        <span style="font-size:11px; color:var(--text3); white-space:nowrap;">${daysLeft}d</span>
      </div>`;
    });
    document.getElementById('dash-timeline-list').innerHTML = tlHtml;
    dashTlCard.style.display = 'block';
  } else {
    dashTlCard.style.display = 'none';
  }
}

// ===== RENDER: SUBJECTS =====
async function renderSubjects() {
  const [data, timeline] = await Promise.all([api('/api/data'), api('/api/timeline-estimate')]);
  const container = document.getElementById('subjects-list');
  const estimates = timeline.estimates || {};

  if (!data.subjects || data.subjects.length === 0) {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-text">No subjects added yet.<br>Click "Add Subject" to get started.</div></div>';
    return;
  }

  const roiOrder = { 'very-high': 0, high: 1, medium: 2, low: 3 };
  const sorted = [...data.subjects].sort((a, b) => roiOrder[a.roi] - roiOrder[b.roi]);

  // Count all currently-learning topics across all subjects
  const learningCount = data.subjects.reduce((sum, s) => sum + s.topics.filter(t => t.status === 'learning').length, 0);
  const slotsAvailable = learningCount < (timeline.summary?.parallelSlots || 2);

  container.innerHTML = sorted.map(subj => {
    const topicsSorted = [...subj.topics].sort((a, b) => roiOrder[a.roi] - roiOrder[b.roi]);
    const completed = subj.topics.filter(t => t.status === 'completed' || t.status === 'pipeline-complete').length;
    const mastered = subj.topics.filter(t => t.status === 'pipeline-complete').length;
    const total = subj.topics.length;
    const pct = total > 0 ? Math.round(completed / total * 100) : 0;
    const masteryPct = total > 0 ? Math.round(mastered / total * 100) : 0;
    const hmTopics = subj.topics.filter(t => t.roi === 'very-high' || t.roi === 'high' || t.roi === 'medium');
    const hmMastered = hmTopics.filter(t => t.status === 'pipeline-complete').length;

    return `<div class="subject-card">
      <div class="subject-header" onclick="this.parentElement.querySelector('.subject-body').classList.toggle('hide')">
        <div style="display:flex; align-items:center; gap:12px;">
          <div style="width:4px; height:28px; border-radius:2px; background:${subj.color};"></div>
          <div>
            <div class="subject-name">${subj.name}</div>
            <div style="font-size:11px; color:var(--text3);">${total} topics · ${completed} completed · ${mastered} pipeline-complete · <span class="badge badge-${roiBadgeClass(subj.roi)}" style="font-size:10px">${roiEmoji(subj.roi)} ${subj.roi.toUpperCase()} ROI</span>${subj.ntfyTopic ? ` · <span class="badge badge-cyan" style="font-size:10px">${subj.ntfyTopic}</span>` : ''}${hmTopics.length > 0 ? ` · <span style="font-size:10px;color:${hmMastered === hmTopics.length && hmTopics.length > 0 ? 'var(--green)' : 'var(--text3)'};">VH+H+M: ${hmMastered}/${hmTopics.length}</span>` : ''}</div>
            ${subj.notes ? `<div style="font-size:11px; color:var(--text2); margin-top:4px; max-width:420px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${subj.notes.replace(/"/g, '&quot;')}">📝 ${subj.notes}</div>` : ''}
          </div>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
          <div style="width:80px;" title="Completion: ${pct}% · Mastery: ${masteryPct}%">
            <div class="progress-bar" style="margin-bottom:3px;"><div class="progress-fill" style="width:${pct}%; background:${subj.color};"></div></div>
            <div class="progress-bar"><div class="progress-fill" style="width:${masteryPct}%; background:var(--cyan);"></div></div>
          </div>
          <span style="font-size:12px; color:var(--text3);">${pct}%</span>
          <button class="btn btn-sm" onclick="event.stopPropagation();openAddTopic('${subj.id}')">+ Topic</button>
          <button class="btn btn-sm" onclick="event.stopPropagation();editSubjectNtfy('${subj.id}','${(subj.ntfyTopic || '').replace(/'/g, "\\'")}')" title="Set ntfy channel">Notify</button>
          <button class="btn btn-sm btn-danger btn-icon" onclick="event.stopPropagation();deleteSubject('${subj.id}')" title="Delete Subject">🗑️</button>
        </div>
      </div>
      <div class="subject-body">
        ${topicsSorted.length === 0
          ? '<div style="padding:12px 0; font-size:12px; color:var(--text3); text-align:center;">No topics yet. Click "+ Topic" to add micro-topics.</div>'
          : `<table><thead><tr><th>Topic</th><th>ROI</th><th>Status</th><th>Est. Timeline</th><th>Actions</th></tr></thead><tbody>
            ${topicsSorted.map(t => {
              const statusBadge = {
                'not-started': '<span class="badge badge-accent">Not Started</span>',
                'learning': '<span class="badge badge-yellow">Learning</span>',
                'completed': '<span class="badge badge-green">Revising</span>',
                'pipeline-complete': '<span class="badge badge-cyan">Pipeline Complete</span>'
              }[t.status];
              const roiBadge = `<span class="badge badge-${roiBadgeClass(t.roi)}">${roiEmoji(t.roi)} ${t.roi}</span>`;
              let actions = `<button class="btn btn-sm" onclick="event.stopPropagation();editTopic('${subj.id}','${t.id}')" title="Edit topic">✏️</button> `;
              if (t.status === 'not-started') actions += slotsAvailable
                ? `<button class="btn btn-sm btn-primary" onclick="event.stopPropagation();startLearning('${subj.id}','${t.id}');">Start</button>`
                : `<button class="btn btn-sm" disabled title="Complete a learning topic first (${learningCount}/${timeline.summary?.parallelSlots || 2} slots used)" style="opacity:0.45;cursor:not-allowed;">🔒 Start</button>`;
              else if (t.status === 'learning') actions += `<button class="btn btn-sm btn-success" onclick="event.stopPropagation();completeLearning('${subj.id}','${t.id}');">Done</button>`;
              else actions += `<button class="btn btn-sm" onclick="event.stopPropagation();showTopicDetail('${subj.id}','${t.id}');">Plan</button>`;

              // Timeline estimate column
              const est = estimates[t.id];
              let estHtml = `<span style="color:var(--text3);">${t.estimatedHours || '?'}h</span>`;
              if (est) {
                if (t.status === 'pipeline-complete') {
                  estHtml = '<span style="color:var(--green);font-weight:600;">✓ Pipeline Complete</span>';
                } else if (t.status === 'completed') {
                  estHtml = `<div style="font-size:11px;line-height:1.5;">
                    <span style="color:var(--green);">Mastery</span><br>
                    <span style="color:var(--text2);font-weight:500;">${formatDateShort(est.masteryDate)}</span><br>
                    <span style="color:var(--text3);">${est.doneRevisions}/12 done</span>
                  </div>`;
                } else if (t.status === 'learning') {
                  const daysToMastery = daysBetween(todayStr(), est.masteryDate);
                  estHtml = `<div style="font-size:11px;line-height:1.5;">
                    <span style="color:var(--yellow);">Done ~${formatDateShort(est.completionDate)}</span><br>
                    <span style="color:var(--text2);">Mastery ${formatDateShort(est.masteryDate)}</span><br>
                    <span style="color:var(--text3);">${daysToMastery}d left</span>
                  </div>`;
                } else {
                  // not-started
                  const qPos = est.queuePosition || '—';
                  const daysToMastery = daysBetween(todayStr(), est.masteryDate);
                  estHtml = `<div style="font-size:11px;line-height:1.5;">
                    <span style="color:var(--accent2);">Start ~${formatDateShort(est.startDate)}</span><br>
                    <span style="color:var(--text2);">Mastery ~${formatDateShort(est.masteryDate)}</span><br>
                    <span style="color:var(--text3);">Q#${qPos} · ${daysToMastery}d</span>
                  </div>`;
                }
              }

              return `<tr style="cursor:pointer;" onclick="showTopicDetail('${subj.id}','${t.id}')">
                <td><div style="font-weight:500;">${t.name}</div>${t.notes ? '<div style="font-size:11px;color:var(--text3);margin-top:2px;">' + t.notes.slice(0, 60) + '</div>' : ''}</td>
                <td>${roiBadge}</td>
                <td>${statusBadge}</td>
                <td>${estHtml}</td>
                <td onclick="event.stopPropagation();">${actions}</td>
              </tr>`;
            }).join('')}
          </tbody></table>`
        }
      </div>
    </div>`;
  }).join('');
}

// ===== RENDER: TODAY'S PLAN =====
async function renderToday() {
  const data = await api('/api/today');
  const today = data.today;
  const weekend = data.isWeekend;
  const dayNames = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  const dow = data.dayOfWeek;
  const jsDow = parseDate(today).getDay();
  const jsDayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  const settings = data.settings;
  const actHrs = settings.activityHours || {};

  // Time Budget Summary at top
  const tb = data.timeBudget;
  let timeSummaryHtml = '';
  if (tb) {
    const pct = tb.utilization;
    const barColor = tb.overloaded ? 'var(--red)' : pct > 80 ? 'var(--yellow)' : 'var(--green)';
    const tpSpillover = tb.spilloverHours || 0;
    timeSummaryHtml = `
      <div style="background:var(--bg2); border-radius:8px; padding:12px; margin-bottom:16px; border-left:4px solid ${barColor};">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <span style="font-size:13px; font-weight:600;">Time Budget: ${tb.totalHours}h / ${tb.budget}h</span>
          <span style="font-size:11px; color:${tb.overloaded ? 'var(--red)' : 'var(--green)'}; font-weight:600;">
            ${tb.overloaded ? '⚠️ OVERLOADED by ' + tb.overloadHours + 'h' : '✓ ' + tb.remaining + 'h free'}
          </span>
        </div>
        <div style="background:var(--bg); border-radius:4px; height:6px; overflow:hidden;">
          <div style="height:100%; width:${Math.min(100, pct)}%; background:${barColor}; border-radius:4px;"></div>
        </div>
        <div style="display:flex; gap:12px; margin-top:8px; font-size:11px; color:var(--text3);">
          <span>📝 Revisions: ${tb.revisionHours}h</span>
          <span>📖 Learning: ${tb.learningHours}h</span>
          <span>🔄 Cumulative: ${tb.cumulativeHours}h</span>
        </div>
        ${tpSpillover > 0 ? `<div style="margin-top:8px; padding:6px 10px; background:rgba(255,165,0,0.1); border-left:3px solid orange; border-radius:4px; font-size:11px; color:var(--text2);">↪ <strong>${tpSpillover}h</strong> spills to tomorrow: ${(tb.spilloverItems||[]).map(s => s.label + ' ' + s.hours + 'h').join(', ')}</div>` : ''}
      </div>`;
  }

  const isHoliday = data.isHoliday;
  const isNaturalWeekend = jsDow === 0 || jsDow === 6;

  document.getElementById('today-day-type').innerHTML = `
    <span>${jsDayNames[jsDow]}, ${formatDate(today)}</span>
    <span class="day-type-badge ${weekend ? 'weekend-badge' : 'weekday-badge'}">${weekend ? (isHoliday ? '12HR DAY' : 'WEEKEND') : 'WEEKDAY'}</span>
    ${!isNaturalWeekend ? `<button onclick="toggleHoliday('${today}')" style="margin-left:8px; padding:2px 10px; font-size:11px; border-radius:6px; border:1px solid ${isHoliday ? 'var(--red)' : 'var(--accent)'}; background:${isHoliday ? 'rgba(255,70,70,0.15)' : 'rgba(100,180,255,0.1)'}; color:${isHoliday ? 'var(--red)' : 'var(--accent)'}; cursor:pointer;">${isHoliday ? '✕ Remove 12hr' : '⏫ Make 12hr day'}</button>` : ''}
    <span style="margin-left: auto; font-size:12px; color:var(--text2);">Total: ${weekend ? settings.weekendHours : settings.weekdayHours}h available</span>
  `;

  const todayTasks = data.todayTasks;
  const overdueTasks = data.overdueTasks;
  const learningTopics = data.learningTopics;

  let html = '';

  // === BLOCK 1: First Hour — Revision (R1, R3 + Overdue) ===
  const revisionTasks = [...overdueTasks, ...todayTasks.filter(t => ['R1', 'R3'].includes(t.type))];
  const revisionMins = weekend ? settings.weekendRevHrs * 60 : settings.revisionMins;
  const revBlockHrs = revisionTasks.reduce((sum, t) => sum + (actHrs[t.type] || 1), 0);
  html += `<div class="time-block revision">
    <div class="time-block-header">
      <div class="time-block-title">Revision Block</div>
      <div class="time-block-time">${revisionTasks.length} item(s) · ~${revBlockHrs}h · 1st/2nd Revision + Overdue</div>
    </div>
    <div style="font-size: 11px; color: var(--text2); margin-bottom: 10px;">Active recall only — no new material. Quick recollection, self-test, write key points from memory.</div>
    ${revisionTasks.length > 0
      ? revisionTasks.map(t => renderTaskItem(t)).join('')
      : '<div style="padding: 8px; font-size: 12px; color: var(--text3);">No revisions due. Use this time for self-testing any recent topics.</div>'
    }
  </div>`;

  // === BLOCK 2: Weekend R7 Consolidation (Only on Sundays) ===
  if (jsDow === 0) {
    const r7Tasks = todayTasks.filter(t => t.type === 'R7');
    const r7Hrs = r7Tasks.length * (actHrs['R7'] || 1.5);
    html += `<div class="time-block" style="background: var(--yellow-bg); border-color: var(--yellow);">
      <div class="time-block-header">
        <div class="time-block-title">Sunday Consolidation - 3rd Revision</div>
        <div class="time-block-time">${r7Tasks.length} item(s) · ~${r7Hrs}h</div>
      </div>
      <div style="font-size: 11px; color: var(--text2); margin-bottom: 10px;">All 3rd revisions are grouped to Sunday. Deeper review — re-read notes, test with PYQs.</div>
      ${r7Tasks.length > 0
        ? r7Tasks.map(t => renderTaskItem(t)).join('')
        : '<div style="padding: 8px; font-size: 12px; color: var(--text3);">No 3rd revisions due this Sunday.</div>'
      }
    </div>`;
  }

  // === BLOCK 3: New Learning ===
  const totalLearnHrs = learningTopics.reduce((sum, t) => sum + (t.estimatedHours || 7.5), 0);
  html += `<div class="time-block learning">
    <div class="time-block-header">
      <div class="time-block-title">New Learning Block</div>
      <div class="time-block-time">${learningTopics.length} topic(s) · ~${totalLearnHrs.toFixed(1)}h total est.</div>
    </div>
    <div style="font-size: 11px; color: var(--text2); margin-bottom: 10px;">Focus on current topics. Hours are set per-topic. Very High & High ROI topics first.</div>
    ${learningTopics.length > 0
      ? learningTopics.map(t => {
          const daysIn = daysBetween(t.startDate, today);
          const linkCount = (t.links || []).length;
          return `<div class="task-item" style="cursor:pointer;" onclick="showTopicDetail('${t.subjectId}','${t.id}')">
            <div style="width: 4px; height: 32px; border-radius: 2px; background: ${t.subjectColor};"></div>
            <div class="task-info">
              <div class="task-name">${t.name}${linkCount > 0 ? ` <span class="badge badge-cyan" style="font-size:9px;">${linkCount} links</span>` : ''}</div>
              <div class="task-meta">${t.subjectName} · Day ${daysIn + 1} · ${t.estimatedHours || '?'}h total · ${t.roi} ROI</div>
            </div>
            <div style="display:flex; gap:4px; align-items:center;" onclick="event.stopPropagation();">
              <input type="number" id="log-hrs-${t.id}" value="2" min="0.5" max="12" step="0.5" class="form-input" style="width:55px; padding:4px 6px; font-size:11px; text-align:center;">
              <button class="btn btn-sm" onclick="logStudyHours('${t.id}', document.getElementById('log-hrs-${t.id}').value)" title="Log study hours">Log</button>
              <button class="btn btn-sm btn-success" onclick="completeLearning('${t.subjectId}','${t.id}');">Done</button>
            </div>
          </div>`;
        }).join('')
      : '<div style="padding: 8px; font-size: 12px; color: var(--text3);">No topics in progress. Go to Subjects and start a topic!</div>'
    }
  </div>`;

  // === BLOCK 4: Practice (PYQs, MCQs, Current Affairs, Mains due today) ===
  const practiceTasks = todayTasks.filter(t => ['PYQ', 'ERA', 'MCQ', 'MCQA', 'MN', 'MVA', 'MAINS'].includes(t.type));
  if (practiceTasks.length > 0) {
    const practiceHrs = practiceTasks.reduce((sum, t) => sum + (actHrs[t.type] || 1), 0);
    html += `<div class="time-block practice">
      <div class="time-block-header">
        <div class="time-block-title">Practice Block</div>
        <div class="time-block-time">${practiceTasks.length} item(s) · ~${practiceHrs}h</div>
      </div>
      <div style="font-size: 11px; color: var(--text2); margin-bottom: 10px;">PYQ solving, Error Analysis, MCQ practice, MCQ Analysis, Micro Notes, Current Affairs + Mapping, Mains Value Addition & Mains answer writing.</div>
      ${practiceTasks.map(t => renderTaskItem(t)).join('')}
    </div>`;
  }

  // === BLOCK 5: R30 / Mock Test ===
  const r30Tasks = todayTasks.filter(t => t.type === 'R30');
  if (r30Tasks.length > 0) {
    const r30Hrs = r30Tasks.length * (actHrs['R30'] || 1);
    html += `<div class="time-block mock">
      <div class="time-block-header">
        <div class="time-block-title">Final Revision</div>
        <div class="time-block-time">${r30Tasks.length} item(s) · ~${r30Hrs}h</div>
      </div>
      <div style="font-size: 11px; color: var(--text2); margin-bottom: 10px;">30-day deep revision — full topic recall before mastery.</div>
      ${r30Tasks.map(t => renderTaskItem(t)).join('')}
    </div>`;
  }

  // === BLOCK 6: Cumulative Revision Sessions (Weekend) ===
  const cumSessions = data.cumulativeSessions || [];
  if (cumSessions.length > 0) {
    const overdueCum = cumSessions.filter(s => s.overdue);
    const dueCum = cumSessions.filter(s => !s.overdue);
    html += `<div class="time-block" style="background: rgba(99,102,241,0.08); border-color: var(--accent);">
      <div class="time-block-header">
        <div class="time-block-title">🔄 Cumulative Revision Sessions</div>
        <div class="time-block-time">${cumSessions.length} session(s)</div>
      </div>
      <div style="font-size: 11px; color: var(--text2); margin-bottom: 10px;">
        Weekend consolidation — interleaved cross-topic review for deep long-term retention.
      </div>`;

    [...overdueCum, ...dueCum].forEach(s => {
      const isOverdue = s.overdue;
      const label = s.type === 'sectional'
        ? `Sectional Batch (${s.topicCount} topics) · Round ${s.round}/3`
        : `${s.subjectName} — Full Subject Review · Round ${s.round}/4`;
      const details = s.type === 'sectional' && s.topicDetails
        ? s.topicDetails.map(t => t.topicName).join(', ')
        : '';

      html += `<div class="task-item ${isOverdue ? 'overdue' : ''}" style="cursor:pointer;" onclick="document.querySelector('[data-page=cumulative]').click();">
        <div style="width: 4px; height: 32px; border-radius: 2px; background: ${s.type === 'sectional' ? 'var(--accent)' : 'var(--cyan)'};"></div>
        <div class="task-info">
          <div class="task-name">${label}</div>
          <div class="task-meta">${formatDate(s.date)}${isOverdue ? ' · <span style="color:var(--red);">OVERDUE</span>' : ''}</div>
          ${details ? `<div style="font-size:10px; color:var(--text3); margin-top:2px;">${details}</div>` : ''}
        </div>
        <span class="badge badge-${s.type === 'sectional' ? 'accent' : 'cyan'}">${s.type === 'sectional' ? 'SECTIONAL' : 'SUBJECT'}</span>
      </div>`;
    });
    html += `</div>`;
  }

  document.getElementById('today-time-blocks').innerHTML = timeSummaryHtml + html;
}

// ===== RENDER: CALENDAR =====
let calMonth = new Date().getMonth() + 1;
let calYear = new Date().getFullYear();
let calSelectedDate = null;

function calNav(dir) {
  calMonth += dir;
  if (calMonth > 12) { calMonth = 1; calYear++; }
  if (calMonth < 1) { calMonth = 12; calYear--; }
  renderCalendar();
}

function calGoToday() {
  const now = new Date();
  calMonth = now.getMonth() + 1;
  calYear = now.getFullYear();
  calSelectedDate = todayStr();
  renderCalendar();
  setTimeout(() => showCalDay(todayStr()), 100);
}

async function renderCalendar() {
  const monthNames = ['', 'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  document.getElementById('cal-month-label').textContent = `${monthNames[calMonth]} ${calYear}`;

  const data = await api(`/api/calendar/${calYear}/${calMonth}`);
  const firstDayJS = new Date(calYear, calMonth - 1, 1).getDay();
  const daysInMonth = data.daysInMonth;
  const daysInPrevMonth = new Date(calYear, calMonth - 1, 0).getDate();
  const todayD = data.today;
  const events = data.events || {};

  let html = '';
  ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].forEach(d => {
    html += `<div class="cal-header">${d}</div>`;
  });

  // Previous month padding
  for (let i = firstDayJS - 1; i >= 0; i--) {
    const d = daysInPrevMonth - i;
    html += `<div class="cal-day other-month"><div class="cal-day-num">${d}</div></div>`;
  }

  // Current month
  for (let d = 1; d <= daysInMonth; d++) {
    const ds = `${calYear}-${String(calMonth).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    const isTodays = ds === todayD;
    const isSelected = ds === calSelectedDate;
    const dayEvents = events[ds] || [];
    const hasTasks = dayEvents.length > 0;
    const allDone = hasTasks && dayEvents.every(e => e.done);
    const hasOverdue = dayEvents.some(e => e.overdue);
    const doneCount = dayEvents.filter(e => e.done).length;

    let classes = 'cal-day';
    if (isTodays) classes += ' today';
    if (isSelected) classes += ' selected';
    if (hasTasks) classes += ' has-tasks';
    if (allDone) classes += ' all-done';
    if (hasOverdue) classes += ' has-overdue';

    html += `<div class="${classes}" onclick="showCalDay('${ds}')" data-date="${ds}">
      <div class="cal-day-num" style="${isTodays ? 'color:var(--accent2);font-weight:700;' : ''}">${d}${hasTasks ? `<span style="font-size:9px;color:var(--text3);font-weight:400;">(${doneCount}/${dayEvents.length})</span>` : ''}</div>
      ${dayEvents.slice(0, 3).map(e => {
        const cls = ({R1:'r1',PYQ:'pyq',ERA:'era',R3:'r3',MN:'mn',CA:'ca',MCQ:'mcq',MCQA:'mcqa',R7:'r7',MVA:'mva',MAINS:'mains',R30:'r30'})[e.type] || 'mains';
        const doneClass = e.done ? 'done-event' : '';
        return `<div class="cal-event ${cls} ${doneClass}" title="${e.topicName} · ${e.label}${e.done ? ' ✓' : ''}" onclick="event.stopPropagation();showTopicDetail('${e.subjectId}','${e.topicId}')">${e.done ? '✓ ' : ''}${e.type} ${e.topicName.slice(0, 10)}</div>`;
      }).join('')}
      ${dayEvents.length > 3 ? `<div style="font-size:9px;color:var(--text3);">+${dayEvents.length - 3} more</div>` : ''}
    </div>`;
  }

  // Next month padding
  const totalCells = firstDayJS + daysInMonth;
  const remaining = (7 - totalCells % 7) % 7;
  for (let d = 1; d <= remaining; d++) {
    html += `<div class="cal-day other-month"><div class="cal-day-num">${d}</div></div>`;
  }

  document.getElementById('cal-grid').innerHTML = html;

  if (calSelectedDate) {
    showCalDay(calSelectedDate, true);
  }
}

async function showCalDay(dateStr, skipHighlight = false) {
  calSelectedDate = dateStr;

  if (!skipHighlight) {
    document.querySelectorAll('.cal-day.selected').forEach(el => el.classList.remove('selected'));
    const dayEl = document.querySelector(`.cal-day[data-date="${dateStr}"]`);
    if (dayEl && !dayEl.classList.contains('other-month')) {
      dayEl.classList.add('selected');
    }
  }

  const data = await api(`/api/calendar/day/${dateStr}`);

  // Date header
  const dateLabel = `${data.dayName}, ${formatDate(dateStr)}`;
  const isNaturalWknd = data.dayName === 'Saturday' || data.dayName === 'Sunday';
  let headerHtml = dateLabel;
  if (data.isToday) headerHtml += ' <span class="badge badge-accent" style="font-size:10px;margin-left:6px;">TODAY</span>';
  if (data.isWeekend && !data.isHoliday) headerHtml += ' <span class="badge badge-yellow" style="font-size:10px;margin-left:4px;">WEEKEND</span>';
  if (data.isHoliday) headerHtml += ' <span class="badge badge-green" style="font-size:10px;margin-left:4px;">12HR DAY</span>';
  if (data.isPast && !data.isToday) headerHtml += ' <span class="badge badge-red" style="font-size:10px;margin-left:4px;">PAST</span>';
  if (!isNaturalWknd) headerHtml += ` <button onclick="toggleHoliday('${dateStr}')" style="margin-left:8px; padding:2px 8px; font-size:10px; border-radius:5px; border:1px solid ${data.isHoliday ? 'var(--red)' : 'var(--accent)'}; background:${data.isHoliday ? 'rgba(255,70,70,0.15)' : 'rgba(100,180,255,0.1)'}; color:${data.isHoliday ? 'var(--red)' : 'var(--accent)'}; cursor:pointer;">${data.isHoliday ? '✕ Remove 12hr' : '⏫ 12hr day'}</button>`;
  document.getElementById('cal-detail-date').innerHTML = headerHtml;

  // Stats
  let statsHtml = '';
  if (data.total > 0) {
    statsHtml += `<div class="cal-detail-stat"><strong>${data.total}</strong> total</div>`;
    statsHtml += `<div class="cal-detail-stat" style="color:var(--green)"><strong>${data.done}</strong> done</div>`;
    if (data.pending > 0) statsHtml += `<div class="cal-detail-stat" style="color:var(--yellow)"><strong>${data.pending}</strong> pending</div>`;
    if (data.overdue > 0) statsHtml += `<div class="cal-detail-stat" style="color:var(--red)"><strong>${data.overdue}</strong> overdue</div>`;
    const pct = Math.round(data.done / data.total * 100);
    statsHtml += `<div style="width:100%;margin-top:4px;"><div class="progress-bar"><div class="progress-fill" style="width:${pct}%; background:${pct === 100 ? 'var(--green)' : 'var(--accent)'};"></div></div><div style="font-size:10px;color:var(--text3);text-align:center;margin-top:2px;">${pct}% complete</div></div>`;
  } else {
    statsHtml = `<div class="cal-detail-stat">No tasks scheduled</div>`;
  }
  document.getElementById('cal-detail-stats').innerHTML = statsHtml;

  // Time Budget
  let budgetHtml = '';
  const tb = data.timeBudget;
  if (tb) {
    const pct = tb.utilization;
    const barColor = tb.overloaded ? 'var(--red)' : pct > 80 ? 'var(--yellow)' : 'var(--green)';
    const statusText = tb.overloaded
      ? '<span style="color:var(--red); font-weight:600;">⚠️ OVERLOADED by ' + tb.overloadHours + 'h</span>'
      : '<span style="color:var(--green); font-weight:600;">✓ ' + tb.remaining + 'h free</span>';

    budgetHtml = '<div style="background:var(--bg2); border-radius:8px; padding:10px; margin:8px 0; border-left:4px solid ' + barColor + ';">'
      + '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">'
      + '<span style="font-size:12px; font-weight:600;">Time Budget</span>'
      + '<span style="font-size:11px;">' + statusText + '</span>'
      + '</div>'
      + '<div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:6px; margin-bottom:8px;">'
      + '<div style="text-align:center; padding:6px 4px; background:var(--bg); border-radius:4px;">'
      + '<div style="font-size:9px; color:var(--text3); text-transform:uppercase;">Budget</div>'
      + '<div style="font-size:16px; font-weight:700; color:var(--text1);">' + tb.budget + 'h</div></div>'
      + '<div style="text-align:center; padding:6px 4px; background:var(--bg); border-radius:4px;">'
      + '<div style="font-size:9px; color:var(--text3); text-transform:uppercase;">Revisions</div>'
      + '<div style="font-size:16px; font-weight:700; color:var(--red);">' + tb.revisionHours + 'h</div></div>'
      + '<div style="text-align:center; padding:6px 4px; background:var(--bg); border-radius:4px;">'
      + '<div style="font-size:9px; color:var(--text3); text-transform:uppercase;">Learning</div>'
      + '<div style="font-size:16px; font-weight:700; color:var(--accent2);">' + tb.learningHours + 'h</div></div>'
      + '<div style="text-align:center; padding:6px 4px; background:var(--bg); border-radius:4px;">'
      + '<div style="font-size:9px; color:var(--text3); text-transform:uppercase;">Cumulative</div>'
      + '<div style="font-size:16px; font-weight:700; color:var(--purple);">' + tb.cumulativeHours + 'h</div></div>'
      + '</div>'
      + '<div style="background:var(--bg); border-radius:4px; height:6px; overflow:hidden; margin-bottom:6px;">'
      + '<div style="height:100%; width:' + Math.min(100, pct) + '%; background:' + barColor + '; border-radius:4px;"></div>'
      + '</div>'
      + '<div style="font-size:10px; color:var(--text3); text-align:center;">' + tb.totalHours + 'h / ' + tb.budget + 'h used (' + pct + '%)</div>'
      + ((tb.spilloverHours || 0) > 0 ? '<div style="margin-top:6px; padding:5px 8px; background:rgba(255,165,0,0.1); border-left:3px solid orange; border-radius:4px; font-size:10px; color:var(--text2);">↪ <strong>' + tb.spilloverHours + 'h</strong> spills to next day: ' + (tb.spilloverItems||[]).map(function(s){return s.label+' '+s.hours+'h'}).join(', ') + '</div>' : '')
      + (tb.activities && tb.activities.length > 0 ? renderTimeBudgetActivities(tb.activities) : '')
      + '</div>';
  }
  document.getElementById('cal-detail-budget').innerHTML = budgetHtml;

  // Tasks
  let tasksHtml = '';
  if (data.tasks.length === 0) {
    tasksHtml = `<div class="empty-state" style="padding: 30px 0;">
      <div class="empty-state-text">${data.isFuture ? 'No revisions scheduled<br>for this day yet' : data.isPast ? 'Nothing was scheduled<br>for this day' : 'No tasks for today!'}</div>
    </div>`;
  } else {
    const typeOrder = ['R1', 'PYQ', 'ERA', 'R3', 'MN', 'CA', 'MCQ', 'MCQA', 'R7', 'MVA', 'MAINS', 'R30'];
    const typeLabels = { R1: '1st Revision', PYQ: 'PYQ Practice', ERA: 'Error Analysis', R3: '2nd Revision', MN: 'Micro Note Making', MCQ: 'MCQ Practice', MCQA: 'MCQ Analysis', R7: '3rd Revision', MVA: 'Mains Value Addition', MAINS: 'Mains Writing', R30: 'Final Revision' };
    const typeColors = { R1: 'red', PYQ: 'cyan', ERA: 'pink', R3: 'orange', MN: 'lime', CA: 'purple', MCQ: 'teal', MCQA: 'indigo', R7: 'yellow', MVA: 'emerald', R30: 'blue', MAINS: 'accent' };

    const grouped = {};
    data.tasks.forEach(t => {
      if (!grouped[t.type]) grouped[t.type] = [];
      grouped[t.type].push(t);
    });

    typeOrder.forEach(type => {
      const tasks = grouped[type];
      if (!tasks) return;
      const allTypeDone = tasks.every(t => t.done);
      tasksHtml += `<div style="margin-bottom:12px;">
        <div style="display:flex; align-items:center; gap:6px; margin-bottom:6px; padding:4px 0;">
          <span class="badge badge-${typeColors[type]}" style="font-size:10px">${type}</span>
          <span style="font-size:11px; color:var(--text2); flex:1;">${typeLabels[type]}</span>
          ${allTypeDone ? '<span style="font-size:10px; color:var(--green);">All done</span>' : `<span style="font-size:10px; color:var(--text3);">${tasks.filter(t => t.done).length}/${tasks.length}</span>`}
        </div>`;

      tasks.forEach(t => {
        const overdueClass = t.overdue ? 'task-overdue' : '';
        const doneClass = t.done ? 'task-done' : '';
        tasksHtml += `<div class="cal-task-item ${doneClass} ${overdueClass}">
          <div class="cal-task-top">
            <div class="cal-task-check ${t.done ? 'checked' : ''}" onclick="calToggleRevision('${t.topicId}','${t.type}','${dateStr}')"></div>
            <div class="cal-task-name ${t.done ? 'done-text' : ''}">${t.topicName}</div>
          </div>
          <div class="cal-task-meta">
            <span style="display:inline-flex; align-items:center; gap:4px;">
              <span style="width:6px; height:6px; border-radius:2px; background:${t.subjectColor}; display:inline-block;"></span>
              ${t.subjectName}
            </span>
            ${t.overdue ? ' · <span style="color:var(--red)">OVERDUE</span>' : ''}
            ${t.done ? ' · <span style="color:var(--green)">Completed</span>' : ''}
          </div>
          <div class="cal-task-actions">
            <button class="btn btn-sm" onclick="showTopicDetail('${t.subjectId}','${t.topicId}')" style="font-size:10px;">Details</button>
            ${!t.done ? `<button class="btn btn-sm btn-success" onclick="calToggleRevision('${t.topicId}','${t.type}','${dateStr}')" style="font-size:10px;">Mark Done</button>` : `<button class="btn btn-sm" onclick="calToggleRevision('${t.topicId}','${t.type}','${dateStr}')" style="font-size:10px;">Undo</button>`}
          </div>
        </div>`;
      });
      tasksHtml += `</div>`;
    });
  }

  document.getElementById('cal-detail-tasks').innerHTML = tasksHtml;
}

async function calToggleRevision(topicId, type, dateStr) {
  const data = await api('/api/data');
  const key = `${topicId}_${type}`;
  if (data.completedRevisions && data.completedRevisions[key]) {
    await api('/api/revisions/unmark', 'POST', { topicId, type });
    renderCalendar();
  } else {
    showConfidencePicker(type, async (confidence) => {
      await api('/api/revisions/mark', 'POST', { topicId, type, confidence });
      const label = confidence === 1 ? 'Hard' : confidence === 3 ? 'Easy' : 'Okay';
      showToast(`${type} done! (${label})`);
      renderCalendar();
    });
  }
}

function closeCalDetail() {
  calSelectedDate = null;
  document.querySelectorAll('.cal-day.selected').forEach(el => el.classList.remove('selected'));
  document.getElementById('cal-detail-date').textContent = 'Select a day';
  document.getElementById('cal-detail-stats').innerHTML = '';
  document.getElementById('cal-detail-tasks').innerHTML = `<div class="empty-state" style="padding: 40px 0;">
    <div class="empty-state-text">Click a day on the calendar<br>to see its tasks</div>
  </div>`;
}

// ===== RENDER: ANALYTICS =====
async function renderAnalytics() {
  const data = await api('/api/analytics');
  const s = data.stats;

  document.getElementById('analytics-stats').innerHTML = `
    <div class="stat-card blue"><div class="stat-label">Total Topics</div><div class="stat-value">${s.total}</div></div>
    <div class="stat-card accent"><div class="stat-label">Not Started</div><div class="stat-value">${s.notStarted}</div></div>
    <div class="stat-card orange"><div class="stat-label">Learning</div><div class="stat-value">${s.learning}</div></div>
    <div class="stat-card green"><div class="stat-label">Completed</div><div class="stat-value">${s.completed}</div></div>
    <div class="stat-card cyan"><div class="stat-label">Revision Compliance</div><div class="stat-value">${s.compliance}%</div><div class="stat-sub">${s.totalDone}/${s.totalExpected} revisions</div></div>
    <div class="stat-card red"><div class="stat-label">Overdue</div><div class="stat-value">${s.overdue}</div></div>
  `;

  // Subject progress
  const sp = data.subjectProgress;
  document.getElementById('analytics-subject-progress').innerHTML = sp.length > 0
    ? sp.map(subj => `<div style="margin-bottom:14px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
          <span style="font-size:13px; font-weight:500;">${subj.name}</span>
          <span style="font-size:12px; color:var(--text3);">${subj.done}/${subj.total} · ${subj.pct}%</span>
        </div>
        <div class="progress-bar"><div class="progress-fill" style="width:${subj.pct}%; background:${subj.color};"></div></div>
      </div>`).join('')
    : '<div style="font-size:13px; color:var(--text3); text-align:center; padding:20px;">No subjects to display</div>';

  // Revision compliance breakdown
  const types = ['R1', 'PYQ', 'ERA', 'R3', 'MN', 'CA', 'MCQ', 'MCQA', 'R7', 'MVA', 'MAINS', 'R30'];
  const colors = { R1: 'var(--red)', PYQ: 'var(--cyan)', ERA: 'var(--pink)', R3: 'var(--orange)', MN: 'var(--lime)', CA: 'var(--purple)', MCQ: 'var(--teal)', MCQA: 'var(--indigo)', R7: 'var(--yellow)', MVA: 'var(--emerald)', MAINS: 'var(--accent)', R30: 'var(--blue)' };
  document.getElementById('analytics-revision-stats').innerHTML = types.map(type => {
    const rs = data.revStats[type];
    const pct = rs.total > 0 ? Math.round(rs.done / rs.total * 100) : 0;
    return `<div style="margin-bottom:10px;">
      <div style="display:flex; justify-content:space-between; margin-bottom:3px;">
        <span style="font-size:12px; font-weight:500;">${type}</span>
        <span style="font-size:11px; color:var(--text3);">${rs.done}/${rs.total} · ${pct}%</span>
      </div>
      <div class="progress-bar"><div class="progress-fill" style="width:${pct}%; background:${colors[type]};"></div></div>
    </div>`;
  }).join('');

  // Lifecycle
  const lifecycle = data.lifecycle;
  document.getElementById('analytics-lifecycle').innerHTML = lifecycle.length > 0
    ? `<table><thead><tr><th>Topic</th><th>Subject</th><th>Completed</th><th>Progress</th></tr></thead><tbody>
      ${lifecycle.map(t => {
        const pct = Math.round(t.progress / t.totalStages * 100);
        return `<tr style="cursor:pointer;" onclick="showTopicDetail('${t.subjectId}','${t.id}')">
          <td style="font-weight:500;">${t.name}</td>
          <td><span style="display:inline-flex; align-items:center; gap:6px;"><span style="width:8px; height:8px; border-radius:2px; background:${t.subjectColor}; display:inline-block;"></span>${t.subjectName}</span></td>
          <td style="font-size:12px; color:var(--text3);">${formatDateShort(t.completionDate)}</td>
          <td>
            <div style="display:flex; align-items:center; gap:8px;">
              <div class="progress-bar" style="width:80px;"><div class="progress-fill" style="width:${pct}%; background:var(--green);"></div></div>
              <span style="font-size:11px; color:var(--text3);">${t.progress}/${t.totalStages}</span>
            </div>
          </td>
        </tr>`;
      }).join('')}
    </tbody></table>`
    : '<div style="font-size:13px; color:var(--text3); text-align:center; padding:20px;">Complete some topics to see their lifecycle progress here</div>';
}

// ===== SETTINGS =====
async function renderSettings() {
  const data = await api('/api/data');
  const s = data.settings;
  document.getElementById('set-weekday-hrs').value = s.weekdayHours;
  document.getElementById('set-weekend-hrs').value = s.weekendHours;
  document.getElementById('set-revision-mins').value = s.revisionMins;
  document.getElementById('set-weekend-rev-hrs').value = s.weekendRevHrs;
  document.getElementById('set-r1').value = s.intervals.r1;
  document.getElementById('set-r3').value = s.intervals.r3;
  document.getElementById('set-r7').value = s.intervals.r7;
  document.getElementById('set-r30').value = s.intervals.r30;

  // Activity duration settings
  const ah = s.activityHours || {};
  document.getElementById('set-act-r1').value = ah.R1 || 1.5;
  document.getElementById('set-act-r3').value = ah.R3 || 1;
  document.getElementById('set-act-r7').value = ah.R7 || 1.5;
  document.getElementById('set-act-r30').value = ah.R30 || 1;
  document.getElementById('set-act-pyq').value = ah.PYQ || 1;
  document.getElementById('set-act-era').value = ah.ERA || 1;
  document.getElementById('set-act-mn').value = ah.MN || 1;
  document.getElementById('set-act-mcq').value = ah.MCQ || 0.5;
  document.getElementById('set-act-mcqa').value = ah.MCQA || 0.5;
  document.getElementById('set-act-mva').value = ah.MVA || 1;
  document.getElementById('set-act-mains').value = ah.MAINS || 1.5;
  document.getElementById('set-act-sectional').value = ah.sectionalBatch || 12;
  document.getElementById('set-act-subject').value = ah.subjectRevision || 24;

  // Exam dates + buffer
  const examDates = s.examDates || {};
  document.getElementById('set-exam-prelims').value = examDates.prelims || '';
  document.getElementById('set-exam-mains').value = examDates.mains || '';
  document.getElementById('set-exam-buffer').value = s.examBufferDays || 10;

  // ntfy settings
  const ntfy = s.ntfy || {};
  document.getElementById('set-ntfy-enabled').value = ntfy.enabled ? 'true' : 'false';
  document.getElementById('set-ntfy-topic').value = ntfy.topic || '';
  document.getElementById('set-ntfy-server').value = ntfy.server || 'https://ntfy.sh';

  // Show status
  const statusEl = document.getElementById('ntfy-status');
  if (ntfy.enabled && ntfy.topic) {
    let statusHtml = `<span style="color: var(--green);">Global channel: <strong>${ntfy.server || 'https://ntfy.sh'}/${ntfy.topic}</strong></span>`;
    const subjChannels = (data.subjects || []).filter(s => s.ntfyTopic);
    if (subjChannels.length > 0) {
      statusHtml += `<br><span style="color: var(--cyan); margin-top:4px; display:inline-block;">Subject channels:</span>`;
      subjChannels.forEach(s => {
        statusHtml += `<br><span style="color:var(--text2); margin-left:16px;">• ${s.name} → <strong>${s.ntfyTopic}</strong></span>`;
      });
    }
    statusEl.innerHTML = statusHtml;
  } else if (ntfy.enabled) {
    statusEl.innerHTML = '<span style="color: var(--yellow);">Enabled but no global topic set</span>';
  } else {
    statusEl.innerHTML = '<span style="color: var(--text3);">Notifications disabled</span>';
  }
}

async function saveSettings() {
  const settings = {
    weekdayHours: parseInt(document.getElementById('set-weekday-hrs').value) || 6,
    weekendHours: parseInt(document.getElementById('set-weekend-hrs').value) || 12,
    revisionMins: parseInt(document.getElementById('set-revision-mins').value) || 60,
    weekendRevHrs: parseInt(document.getElementById('set-weekend-rev-hrs').value) || 3,
    intervals: {
      r1: parseInt(document.getElementById('set-r1').value) || 1,
      r3: parseInt(document.getElementById('set-r3').value) || 3,
      r7: parseInt(document.getElementById('set-r7').value) || 7,
      r30: parseInt(document.getElementById('set-r30').value) || 30,
    },
    activityHours: {
      R1: parseFloat(document.getElementById('set-act-r1').value) || 1.5,
      PYQ: parseFloat(document.getElementById('set-act-pyq').value) || 1,
      ERA: parseFloat(document.getElementById('set-act-era').value) || 1,
      R3: parseFloat(document.getElementById('set-act-r3').value) || 1,
      MN: parseFloat(document.getElementById('set-act-mn').value) || 1,
      MCQ: parseFloat(document.getElementById('set-act-mcq').value) || 0.5,
      MCQA: parseFloat(document.getElementById('set-act-mcqa').value) || 0.5,
      R7: parseFloat(document.getElementById('set-act-r7').value) || 1.5,
      MVA: parseFloat(document.getElementById('set-act-mva').value) || 1,
      MAINS: parseFloat(document.getElementById('set-act-mains').value) || 1.5,
      R30: parseFloat(document.getElementById('set-act-r30').value) || 1,
      sectionalBatch: parseFloat(document.getElementById('set-act-sectional').value) || 12,
      subjectRevision: parseFloat(document.getElementById('set-act-subject').value) || 24,
    },
    ntfy: {
      enabled: document.getElementById('set-ntfy-enabled').value === 'true',
      topic: document.getElementById('set-ntfy-topic').value.trim(),
      server: document.getElementById('set-ntfy-server').value.trim() || 'https://ntfy.sh',
    },
    examDates: {
      prelims: document.getElementById('set-exam-prelims').value || '',
      mains: document.getElementById('set-exam-mains').value || '',
    },
    examBufferDays: parseInt(document.getElementById('set-exam-buffer').value) || 10,
  };
  await api('/api/settings', 'PUT', settings);
  showToast('Settings saved!');
  renderSettings();
}

async function testNtfy() {
  const topic = document.getElementById('set-ntfy-topic').value.trim();
  const server = document.getElementById('set-ntfy-server').value.trim() || 'https://ntfy.sh';
  const enabled = document.getElementById('set-ntfy-enabled').value === 'true';

  if (!enabled) {
    showToast('Enable notifications first!', 'warning');
    return;
  }
  if (!topic) {
    showToast('Enter a global ntfy topic name first!', 'warning');
    return;
  }

  await saveSettings();

  const result = await api('/api/ntfy/test', 'POST', {});
  if (result.ok) {
    showToast('Test notification sent to global channel! Check your phone.', 'success');
  } else {
    showToast('Failed: ' + (result.error || 'Unknown error'), 'warning');
  }
}

async function editSubjectNtfy(subjId, currentTopic) {
  const newTopic = prompt(
    `Set ntfy channel for this subject.\n\n` +
    `Current: ${currentTopic || '(none — using global)'}\n\n` +
    `Enter a unique ntfy topic name (e.g., upsc-polity).\n` +
    `Subscribe to this topic in the ntfy app on your phone.\n` +
    `Leave empty to use the global channel.`,
    currentTopic || ''
  );
  if (newTopic === null) return;

  await api(`/api/subjects/${subjId}/ntfy`, 'PUT', { ntfyTopic: newTopic.trim() });

  if (newTopic.trim()) {
    showToast(`ntfy channel set to "${newTopic.trim()}". Subscribe in the ntfy app!`);
    if (confirm(`Send a test notification to "${newTopic.trim()}"?`)) {
      const result = await api('/api/ntfy/test', 'POST', { subjectId: subjId });
      if (result.ok) {
        showToast('Test sent! Check the ntfy app.', 'success');
      } else {
        showToast('Failed: ' + (result.error || 'Unknown error'), 'warning');
      }
    }
  } else {
    showToast('Subject will use the global ntfy channel.');
  }
  renderPage('subjects');
}

// ===== DATA EXPORT / IMPORT =====
function exportData() {
  window.location.href = '/api/export';
  showToast('Data exported!', 'info');
}

async function importData(e) {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = async function(ev) {
    try {
      const imported = JSON.parse(ev.target.result);
      if (!imported.subjects) throw new Error('Invalid data');
      await api('/api/import', 'POST', imported);
      showToast('Data imported successfully!');
      renderAll();
    } catch { showToast('Invalid file format', 'warning'); }
  };
  reader.readAsText(file);
  e.target.value = '';
}

async function clearAllData() {
  if (!confirm('Delete ALL data? This cannot be undone!')) return;
  if (!confirm('Are you really sure? All subjects, topics, and revision history will be permanently lost.')) return;
  await api('/api/clear', 'POST');
  showToast('All data cleared', 'warning');
  renderAll();
}

// ===== CUMULATIVE REVISIONS =====
async function renderCumulative() {
  const data = await api('/api/cumulative');
  const today = data.today;

  // Stats
  document.getElementById('cum-stats').innerHTML = `
    <div class="stat-card accent"><div class="stat-label">Sectional Batches</div><div class="stat-value">${data.stats.totalBatches}</div><div class="stat-sub">cross-topic groups</div></div>
    <div class="stat-card cyan"><div class="stat-label">Subject Revisions</div><div class="stat-value">${data.stats.totalSubjectRevisions}</div><div class="stat-sub">full subject reviews</div></div>
    <div class="stat-card yellow"><div class="stat-label">Pending Topics</div><div class="stat-value">${data.stats.pendingCount}</div><div class="stat-sub">ready for synthesis batches</div></div>
    <div class="stat-card green"><div class="stat-label">Upcoming Sessions</div><div class="stat-value">${data.stats.upcomingCount}</div><div class="stat-sub">weekend sessions</div></div>
  `;

  // Create batch button — always show when pending > 0
  const forceBatchBtn = document.getElementById('force-batch-btn');
  if (data.stats.pendingCount >= 2) {
    forceBatchBtn.style.display = 'inline-flex';
    forceBatchBtn.textContent = `Create Custom Batch`;
  } else {
    forceBatchBtn.style.display = 'none';
  }

  // Upcoming sessions
  document.getElementById('cum-upcoming-count').textContent = data.upcomingSessions.length;
  if (data.upcomingSessions.length === 0) {
    document.getElementById('cum-upcoming-list').innerHTML = '<div class="empty-state" style="padding: 20px 0;"><div class="empty-state-text">No upcoming sessions. Master more topics to trigger cumulative revisions!</div></div>';
  } else {
    document.getElementById('cum-upcoming-list').innerHTML = data.upcomingSessions.map(s => {
      const daysUntil = daysBetween(today, s.date);
      const isThisWeekend = daysUntil <= 2 && daysUntil >= 0;
      return `<div class="task-item ${isThisWeekend ? '' : ''}" style="cursor:default;">
        <div style="width: 4px; height: 32px; border-radius: 2px; background: ${s.type === 'sectional' ? 'var(--accent)' : 'var(--cyan)'};"></div>
        <div class="task-info">
          <div class="task-name">${s.type === 'sectional' ? `Sectional Batch (${s.topicCount} topics)` : `${s.subjectName} — Full Subject`} · Round ${s.round}</div>
          <div class="task-meta">${formatDate(s.date)} · ${daysUntil === 0 ? '<span style="color:var(--green);font-weight:600;">TODAY</span>' : daysUntil === 1 ? '<span style="color:var(--yellow);">Tomorrow</span>' : `${daysUntil} days away`}</div>
        </div>
        <span class="badge badge-${s.type === 'sectional' ? 'accent' : 'cyan'}">${s.type === 'sectional' ? 'SECTIONAL' : 'SUBJECT'}</span>
      </div>`;
    }).join('');
  }

  // Pending topics
  document.getElementById('cum-pending-count').textContent = data.stats.pendingCount;
  if (data.pendingTopics.length === 0) {
    document.getElementById('cum-pending-list').innerHTML = '<div style="font-size: 12px; color: var(--text3); text-align: center; padding: 16px;">No pipeline-complete topics waiting. Complete all revision stages for a topic to add it here.</div>';
  } else {
    document.getElementById('cum-pending-list').innerHTML = data.pendingTopics.map(t => {
      const roiBadge = `<span class="badge badge-${roiBadgeClass(t.roi)}" style="font-size:10px">${roiEmoji(t.roi)} ${t.roi.toUpperCase()}</span>`;
      return `<div class="task-item" style="cursor:pointer;" onclick="this.querySelector('input').click()">
        <input type="checkbox" class="batch-select-cb" value="${t.topicId}" style="margin-right:8px; cursor:pointer;" onclick="event.stopPropagation(); updateBatchSelection();">
        <div class="task-info">
          <div class="task-name">${t.topicName}</div>
          <div class="task-meta">${t.subjectName} · Pipeline-complete ${formatDateShort(t.masteredAt)}</div>
        </div>
        ${roiBadge}
      </div>`;
    }).join('') + `<div id="batch-create-form" style="display:none; margin-top:10px; padding:10px; background:var(--bg2); border-radius:8px; border:1px solid var(--accent);">
      <div style="font-size:12px; font-weight:600; color:var(--accent); margin-bottom:8px;"><span id="batch-selected-count">0</span> topics selected for synthesis batch</div>
      <div style="display:flex; gap:6px; align-items:center;">
        <input type="text" id="batch-name-input" placeholder="Batch name (e.g. Macro Loop)" class="form-input" style="flex:1; font-size:12px;">
        <button class="btn btn-sm btn-primary" onclick="createCustomBatch()">Create Batch</button>
        <button class="btn btn-sm" onclick="clearBatchSelection()" style="font-size:11px;">Clear</button>
      </div>
    </div>`;
  }

  // Sectional batches
  if (data.sectionalBatches.length === 0) {
    document.getElementById('cum-batches-list').innerHTML = '<div class="card"><div class="empty-state" style="padding: 20px 0;"><div class="empty-state-text">No synthesis batches yet. Select topics from the pending pool above to create cross-topic revision groups.</div></div></div>';
  } else {
    document.getElementById('cum-batches-list').innerHTML = data.sectionalBatches.map(batch => {
      const completedSessions = batch.sessions.filter(s => s.completed).length;
      const totalSessions = batch.sessions.length;
      const pct = Math.round(completedSessions / totalSessions * 100);
      const topics = batch.topicDetails || [];

      return `<div class="card cum-batch-card">
        <div class="cum-batch-header" onclick="this.parentElement.querySelector('.cum-batch-body').classList.toggle('hide')">
          <div style="display:flex; align-items:center; gap:12px;">
            <div style="width:4px; height:28px; border-radius:2px; background:var(--accent);"></div>
            <div>
              <div style="font-weight:600; font-size:14px;">${batch.name || 'Batch'} — ${topics.length} Topics</div>
              <div style="font-size:11px; color:var(--text3);">Created ${formatDate(batch.createdAt)} · ${completedSessions}/${totalSessions} sessions done</div>
            </div>
          </div>
          <div style="display:flex; align-items:center; gap:8px;">
            <div style="width:80px;">
              <div class="progress-bar"><div class="progress-fill" style="width:${pct}%; background:var(--accent);"></div></div>
            </div>
            <span style="font-size:12px; color:var(--text3);">${pct}%</span>
          </div>
        </div>
        <div class="cum-batch-body">
          <div style="margin-bottom:12px;">
            <div style="font-size:12px; font-weight:600; color:var(--text2); margin-bottom:6px;">Topics in this batch:</div>
            <div style="display:flex; flex-wrap:wrap; gap:6px;">
              ${topics.map(t => `<span class="badge badge-${roiBadgeClass(t.roi)}" style="font-size:10px;">${t.topicName} (${t.subjectName})</span>`).join('')}
            </div>
          </div>
          <div style="font-size:12px; font-weight:600; color:var(--text2); margin-bottom:8px;">Weekend Sessions (Ebbinghaus Schedule):</div>
          <div class="timeline-track">
            ${batch.sessions.map(s => {
              const nodeClass = s.completed ? 'done' : (s.isOverdue ? 'active' : 'pending');
              const overdueTag = s.isOverdue ? '<span class="badge badge-red" style="font-size:9px">OVERDUE</span>' : '';
              const weekendTag = s.isThisWeekend && !s.completed ? '<span class="badge badge-green" style="font-size:9px">THIS WEEKEND</span>' : '';
              return `<div class="timeline-node ${nodeClass}">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <div>
                    <div style="font-size:13px; font-weight:600;">Round ${s.round} — ${s.label || (s.round === 1 ? 'Synthesis' : 'Gap-check')} ${overdueTag} ${weekendTag}</div>
                    <div style="font-size:11px; color:var(--text3); margin-top:2px;">${formatDate(s.scheduledDate)} (Saturday-Sunday)</div>
                  </div>
                  <div>
                    ${s.completed
                      ? `<span class="badge badge-green">Done ${s.completedAt ? formatDateShort(s.completedAt) : ''}</span>`
                      : `<button class="btn btn-sm btn-success" onclick="event.stopPropagation();completeBatchSession('${batch.id}',${s.round});">Mark Done</button>`
                    }
                  </div>
                </div>
              </div>`;
            }).join('')}
          </div>
        </div>
      </div>`;
    }).join('');
  }

  // Subject-level revisions removed — replaced by Subject Revision Cycles (R1-R5)
  // Hide the old section entirely
  const cumSubjList = document.getElementById('cum-subject-list');
  if (cumSubjList) {
    cumSubjList.innerHTML = '';
    const parentCard = cumSubjList.closest('.card');
    if (parentCard) parentCard.style.display = 'none';
  }
}

async function completeBatchSession(batchId, round) {
  await api(`/api/cumulative/batch/${batchId}/session/${round}/complete`, 'POST');
  showToast(`Sectional Review Round ${round} completed!`);
  renderCumulative();
}

async function completeSubjectSession(subjId, round) {
  await api(`/api/cumulative/subject/${subjId}/session/${round}/complete`, 'POST');
  showToast(`Subject Review Round ${round} completed!`);
  renderCumulative();
}

function updateBatchSelection() {
  const checked = document.querySelectorAll('.batch-select-cb:checked');
  const form = document.getElementById('batch-create-form');
  const countEl = document.getElementById('batch-selected-count');
  if (form && countEl) {
    if (checked.length >= 2) {
      form.style.display = 'block';
      countEl.textContent = checked.length;
    } else {
      form.style.display = 'none';
    }
  }
}

function clearBatchSelection() {
  document.querySelectorAll('.batch-select-cb:checked').forEach(cb => { cb.checked = false; });
  const form = document.getElementById('batch-create-form');
  if (form) form.style.display = 'none';
}

async function createCustomBatch() {
  const checked = document.querySelectorAll('.batch-select-cb:checked');
  const topicIds = [...checked].map(cb => cb.value);
  const nameInput = document.getElementById('batch-name-input');
  const name = nameInput ? nameInput.value.trim() : '';
  if (topicIds.length < 2) { showToast('Select at least 2 topics', 'warning'); return; }
  await api('/api/cumulative/create-batch', 'POST', { topicIds, name });
  showToast(`Synthesis batch created with ${topicIds.length} topics!`);
  renderCumulative();
}

async function forceBatch() {
  showToast('Select topics from pending pool and click Create Batch', 'info');
}

// ===== SUBJECT REVISION CYCLES =====
async function renderSubjectCycles() {
  const data = await api('/api/subject-cycles');
  const container = document.getElementById('cum-subject-cycles');
  if (!container) return;

  const statuses = Object.values(data.subjectStatus || {});
  if (statuses.length === 0) {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-text">Add subjects to see revision cycle planning.</div></div>';
    return;
  }

  const cycleOrder = ['R1','R2','R3','R4','R5'];
  const configs = data.configs || {};
  const seq = data.sequencing || {};
  let html = '';

  // Sequencing warning if R3 blocks overflow into R4 window
  if (seq.r3Overflow) {
    html += `<div style="padding:10px 14px; margin-bottom:12px; background:rgba(239,68,68,0.1); border-left:3px solid var(--red); border-radius:6px; font-size:12px;">
      <strong style="color:var(--red);">R3 OVERFLOW:</strong> Not enough days to fit all subjects' R3 before R4 starts. Consider reducing R3 duration in some subjects or starting earlier.
    </div>`;
  }
  if (seq.bufferDays) {
    html += `<div style="font-size:11px; color:var(--text3); margin-bottom:12px;">R3→R5 auto-sequenced across subjects (one at a time, no overlap). Last ${seq.bufferDays} days before Prelims are your personal buffer.</div>`;
  }

  statuses.forEach(ss => {
    const cycleMap = {};
    (ss.cycles || []).forEach(c => { cycleMap[c.cycle] = c; });

    html += `<div class="card" style="margin-bottom:12px; border-left:4px solid ${ss.color};">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <div>
          <div style="font-weight:600; font-size:14px;">${ss.subjectName}</div>
          <div style="font-size:11px; color:var(--text3);">${ss.learnedTopics}/${ss.totalTopics} topics learned${ss.r0Ready ? ' — R0 Complete' : ''}</div>
        </div>
      </div>
      <div class="timeline-track" style="padding-left:20px;">`;

    cycleOrder.forEach(cyc => {
      const existing = cycleMap[cyc];
      const cfg = configs[cyc] || {};
      const suggestion = (ss.suggestions || {})[cyc];

      if (existing) {
        const nodeClass = existing.completed ? 'done' : 'active';
        html += `<div class="timeline-node ${nodeClass}">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
              <div style="font-size:13px; font-weight:600;">${cyc} — ${existing.label}</div>
              <div style="font-size:11px; color:var(--text3);">${formatDate(existing.startDate)} to ${formatDate(existing.endDate)} · ${existing.hoursPerDay}h/day</div>
            </div>
            <div>
              ${existing.completed
                ? '<span class="badge badge-green">Done</span>'
                : `<button class="btn btn-sm btn-success" onclick="completeSubjectCycle('${existing.id}')">Done</button>`
              }
            </div>
          </div>
        </div>`;
      } else {
        html += `<div class="timeline-node pending">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
              <div style="font-size:13px; font-weight:600; color:var(--text3);">${cyc} — ${cfg.label || cyc}</div>
              <div style="font-size:11px; color:var(--text3);">${cfg.durationDays || '?'}d · ${cfg.hoursPerDay || '?'}h/day${suggestion ? ` · Suggested: ${formatDate(suggestion)}` : ''}</div>
            </div>
            <div>
              ${suggestion
                ? `<button class="btn btn-sm btn-primary" onclick="scheduleSubjectCycle('${ss.subjectId}','${cyc}','${suggestion}')">Schedule</button>`
                : `<button class="btn btn-sm" disabled style="opacity:0.4;">Not ready</button>`
              }
            </div>
          </div>
        </div>`;
      }
    });

    html += `</div></div>`;
  });

  container.innerHTML = html;
}

async function scheduleSubjectCycle(subjectId, cycle, suggestedDate) {
  const startDate = prompt(`Schedule ${cycle} starting from:`, suggestedDate);
  if (!startDate) return;
  await api('/api/subject-cycles', 'POST', { subjectId, cycle, startDate });
  showToast(`${cycle} cycle scheduled!`);
  renderCumulative();
  renderSubjectCycles();
}

async function completeSubjectCycle(cycleId) {
  await api(`/api/subject-cycles/${cycleId}/complete`, 'POST');
  showToast('Cycle completed!');
  renderSubjectCycles();
}

// ===== WEEKLY REVIEW =====
async function renderWeeklyReview(dateStr) {
  const date = dateStr || todayStr();
  const data = await api(`/api/weekly-review?date=${date}`);
  const container = document.getElementById('analytics-weekly');
  if (!container) return;

  const w = data.week;
  const hbs = data.hoursBySubject || [];
  const rev = data.revisions || {};

  let html = `<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
    <button class="btn btn-sm" onclick="renderWeeklyReview('${addDays(w.start, -7)}')">Prev</button>
    <span style="font-size:13px; font-weight:600;">${formatDate(w.start)} — ${formatDate(w.end)}</span>
    <button class="btn btn-sm" onclick="renderWeeklyReview('${addDays(w.end, 1)}')">Next</button>
  </div>`;

  // Hours summary
  const deltaSign = data.hoursDelta >= 0 ? '+' : '';
  const deltaColor = data.hoursDelta >= 0 ? 'var(--green)' : 'var(--red)';
  html += `<div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px; margin-bottom:14px;">
    <div class="stat-card blue"><div class="stat-label">This Week</div><div class="stat-value">${data.totalHours}h</div></div>
    <div class="stat-card accent"><div class="stat-label">Last Week</div><div class="stat-value">${data.prevWeekHours}h</div></div>
    <div class="stat-card" style="border-left-color:${deltaColor};"><div class="stat-label">Change</div><div class="stat-value" style="color:${deltaColor};">${deltaSign}${data.hoursDelta}h</div></div>
  </div>`;

  // Subject balance
  if (hbs.length > 0) {
    html += `<div style="font-weight:600; font-size:13px; margin-bottom:8px;">Hours by Subject</div>`;
    const maxH = Math.max(...hbs.map(s => s.hours), 1);
    hbs.sort((a, b) => b.hours - a.hours);
    hbs.forEach(s => {
      const pct = Math.round(s.hours / maxH * 100);
      html += `<div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
        <span style="font-size:11px; width:100px; text-align:right; color:var(--text2); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${s.name}</span>
        <div style="flex:1; height:14px; background:var(--bg); border-radius:3px; overflow:hidden;">
          <div style="height:100%; width:${pct}%; background:${s.color}; border-radius:3px;"></div>
        </div>
        <span style="font-size:11px; width:40px; color:var(--text1); font-weight:600;">${s.hours}h</span>
      </div>`;
    });
  } else {
    html += `<div style="font-size:12px; color:var(--text3); margin-bottom:12px;">No study hours logged this week. Use "Log" buttons on the Today page.</div>`;
  }

  // Compliance
  html += `<div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:14px;">
    <div class="stat-card green"><div class="stat-label">Compliance</div><div class="stat-value">${data.compliance}%</div><div class="stat-sub">${rev.onTime || 0} on-time</div></div>
    <div class="stat-card ${rev.overdue > 0 ? 'red' : 'accent'}"><div class="stat-label">Revisions Due</div><div class="stat-value">${rev.due || 0}</div><div class="stat-sub">${rev.late || 0} late · ${rev.overdue || 0} overdue</div></div>
  </div>`;

  container.innerHTML = html;
}

// ===== RENDER: TIMELINE ESTIMATOR =====
async function renderTimeline() {
  const data = await api('/api/timeline-estimate');
  const today = data.today;
  const estimates = data.estimates || {};
  const summary = data.summary || {};

  // Stats
  document.getElementById('tl-stats').innerHTML = `
    <div class="stat-card blue"><div class="stat-label">Total Topics</div><div class="stat-value">${summary.totalTopics || 0}</div><div class="stat-sub">${summary.parallelSlots || 2} parallel slots</div></div>
    <div class="stat-card orange"><div class="stat-label">In Pipeline</div><div class="stat-value">${summary.inPipeline || 0}</div><div class="stat-sub">${summary.notStarted || 0} queued · ${summary.learning || 0} learning</div></div>
    <div class="stat-card green"><div class="stat-label">Overall Finish</div><div class="stat-value">${summary.overallFinishDate ? formatDateShort(summary.overallFinishDate) : '—'}</div><div class="stat-sub">${summary.overallFinishDate ? daysBetween(today, summary.overallFinishDate) + ' days' : 'no topics'}</div></div>
  `;

  // Overall timeline visualization
  const estArr = Object.values(estimates).sort((a, b) => (a.masteryDate || '').localeCompare(b.masteryDate || ''));
  if (estArr.length === 0) {
    document.getElementById('tl-overall').innerHTML = '<div class="empty-state" style="padding:20px 0;"><div class="empty-state-text">No topics added yet. Add topics to see projections.</div></div>';
  } else {
    // Group by subject for a visual overview
    const bySubject = {};
    estArr.forEach(e => {
      if (!bySubject[e.subjectName]) bySubject[e.subjectName] = { color: e.subjectColor, topics: [] };
      bySubject[e.subjectName].topics.push(e);
    });

    let overallHtml = '';
    for (const [subjName, info] of Object.entries(bySubject)) {
      const subjTopics = info.topics;
      const latestMastery = subjTopics.reduce((max, t) => t.masteryDate > max ? t.masteryDate : max, '');
      const completed = subjTopics.filter(t => t.status === 'pipeline-complete').length;
      const total = subjTopics.length;
      const pct = total > 0 ? Math.round(completed / total * 100) : 0;

      overallHtml += `<div style="margin-bottom:14px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
          <span style="font-size:13px; font-weight:500; display:flex; align-items:center; gap:6px;">
            <span style="width:8px; height:8px; border-radius:2px; background:${info.color}; display:inline-block;"></span>
            ${subjName}
          </span>
          <span style="font-size:11px; color:var(--text3);">${completed}/${total} pipeline-complete · Finish ~${latestMastery ? formatDateShort(latestMastery) : '?'}</span>
        </div>
        <div class="progress-bar"><div class="progress-fill" style="width:${pct}%; background:${info.color};"></div></div>
        <div style="display:flex; flex-wrap:wrap; gap:4px; margin-top:6px;">
          ${subjTopics.map(t => {
            const statusColor = t.status === 'pipeline-complete' ? 'var(--green)' : t.status === 'completed' ? 'var(--cyan)' : t.status === 'learning' ? 'var(--yellow)' : 'var(--text3)';
            return `<span style="font-size:10px; padding:2px 6px; border-radius:3px; background:var(--bg); border-left:3px solid ${statusColor};" title="${t.topicName}: Mastery ~${t.masteryDate}">${t.topicName.slice(0, 15)}${t.topicName.length > 15 ? '…' : ''}</span>`;
          }).join('')}
        </div>
      </div>`;
    }
    document.getElementById('tl-overall').innerHTML = overallHtml;
  }

  // Full topic table (filtered)
  const filter = document.getElementById('tl-filter-status')?.value || 'all';
  const filtered = estArr.filter(e => filter === 'all' || e.status === filter);

  if (filtered.length === 0) {
    document.getElementById('tl-topic-list').innerHTML = `<div style="padding:20px; text-align:center; font-size:12px; color:var(--text3);">No topics matching this filter.</div>`;
  } else {
    let tableHtml = `<table><thead><tr>
      <th>#</th><th>Topic</th><th>Subject</th><th>ROI</th><th>Status</th>
      <th>Est. Start</th><th>Est. Complete</th><th>Est. Mastery</th><th>Days Left</th>
    </tr></thead><tbody>`;

    filtered.forEach((e, idx) => {
      const roiBadge = `<span class="badge badge-${roiBadgeClass(e.roi)}" style="font-size:10px">${roiEmoji(e.roi)}</span>`;
      const statusBadge = {
        'not-started': '<span class="badge badge-accent" style="font-size:10px">Queued</span>',
        'learning': '<span class="badge badge-yellow" style="font-size:10px">Learning</span>',
        'completed': '<span class="badge badge-green" style="font-size:10px">Revising</span>',
        'pipeline-complete': '<span class="badge badge-cyan" style="font-size:10px">Pipeline Complete</span>',
      }[e.status] || '';
      const daysLeft = daysBetween(today, e.masteryDate);
      const isEstimate = e.isEstimate;
      const tilde = isEstimate ? '~' : '';
      const qLabel = e.queuePosition ? `<span style="color:var(--text3);font-size:10px;"> Q#${e.queuePosition}</span>` : '';

      tableHtml += `<tr>
        <td style="font-size:11px;color:var(--text3);">${idx + 1}${qLabel}</td>
        <td style="font-weight:500;font-size:12px;">${e.topicName}</td>
        <td><span style="display:inline-flex;align-items:center;gap:4px;font-size:12px;"><span style="width:6px;height:6px;border-radius:2px;background:${e.subjectColor};display:inline-block;"></span>${e.subjectName}</span></td>
        <td>${roiBadge}</td>
        <td>${statusBadge}</td>
        <td style="font-size:11px;color:var(--text2);">${tilde}${formatDateShort(e.startDate)}</td>
        <td style="font-size:11px;color:var(--text2);">${tilde}${formatDateShort(e.completionDate)}</td>
        <td style="font-size:11px;font-weight:600;color:${e.status === 'pipeline-complete' ? 'var(--green)' : 'var(--accent2)'};">${tilde}${formatDateShort(e.masteryDate)}</td>
        <td style="font-size:11px;color:${daysLeft <= 0 ? 'var(--green)' : daysLeft <= 7 ? 'var(--yellow)' : 'var(--text3)'};">${e.status === 'pipeline-complete' ? '✓' : daysLeft + 'd'}</td>
      </tr>`;
    });

    tableHtml += '</tbody></table>';
    document.getElementById('tl-topic-list').innerHTML = tableHtml;
  }
}

// ===== THEME SYSTEM =====
const APP_THEMES = [
  { id: 'black-gold', name: 'Black & Gold', desc: 'Elegant dark with gold accents', colors: ['#0a0a0a','#111111','#d4af37','#f2d272'] },
  { id: 'midnight-navy', name: 'Midnight Navy', desc: 'Original deep blue theme', colors: ['#0f1117','#1a1d27','#6366f1','#818cf8'] },
  { id: 'arc-dark', name: 'Arc Dark', desc: 'Tokyo Night inspired', colors: ['#1a1b26','#1f2029','#7aa2f7','#bb9af7'] },
  { id: 'solarized-dark', name: 'Solarized Dark', desc: 'Classic solarized palette', colors: ['#002b36','#073642','#268bd2','#2aa198'] },
  { id: 'crimson-noir', name: 'Crimson Noir', desc: 'Black with red highlights', colors: ['#0d0d0d','#141414','#dc2626','#f87171'] },
  { id: 'forest-green', name: 'Forest Green', desc: 'Nature-inspired dark green', colors: ['#0a100e','#101a16','#22c55e','#4ade80'] },
];

function getTheme() {
  return localStorage.getItem('upsc-theme') || 'black-gold';
}

function setTheme(themeId) {
  document.documentElement.setAttribute('data-theme', themeId);
  localStorage.setItem('upsc-theme', themeId);
  // Update picker UI if visible
  document.querySelectorAll('.theme-option').forEach(el => {
    el.classList.toggle('active-theme', el.dataset.theme === themeId);
  });
}

function cycleTheme() {
  const current = getTheme();
  const idx = APP_THEMES.findIndex(t => t.id === current);
  const next = APP_THEMES[(idx + 1) % APP_THEMES.length];
  setTheme(next.id);
  showToast(`Theme: ${next.name}`, 'info');
}

function renderThemePicker() {
  const picker = document.getElementById('theme-picker');
  if (!picker) return;
  const current = getTheme();
  picker.innerHTML = APP_THEMES.map(t => `
    <div class="theme-option ${t.id === current ? 'active-theme' : ''}" data-theme="${t.id}" onclick="setTheme('${t.id}')">
      <div class="theme-preview">
        ${t.colors.map(c => `<div class="theme-preview-swatch" style="background:${c}"></div>`).join('')}
      </div>
      <div class="theme-option-name">${t.name}</div>
      <div class="theme-option-desc">${t.desc}</div>
    </div>
  `).join('');
}

// Apply saved theme immediately on load
setTheme(getTheme());

// ===== PAGE RENDERER =====
function renderPage(page) {
  switch (page) {
    case 'dashboard': renderDashboard(); break;
    case 'subjects': renderSubjects(); break;
    case 'today': renderToday(); break;
    case 'calendar': renderCalendar(); break;
    case 'analytics': renderAnalytics(); renderWeeklyReview(); break;
    case 'cumulative': renderCumulative(); renderSubjectCycles(); break;
    case 'timeline': renderTimeline(); break;
    case 'settings': renderSettings(); renderThemePicker(); break;
    case 'htmlpages': renderHtmlPages(); break;
    case 'help': break;  // Static content, no render needed
  }
}

function renderAll() {
  const activePage = document.querySelector('.nav-item.active')?.dataset.page || 'dashboard';
  renderPage(activePage);
}

// ===== KEYBOARD SHORTCUTS =====
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
  const shortcuts = { '1': 'dashboard', '2': 'subjects', '3': 'today', '4': 'calendar', '5': 'analytics', '6': 'cumulative', '7': 'timeline', '8': 'settings', '9': 'htmlpages', '0': 'help' };
  if (shortcuts[e.key]) {
    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const btn = document.querySelector(`.nav-item[data-page="${shortcuts[e.key]}"]`);
    btn.classList.add('active');
    document.getElementById('page-' + shortcuts[e.key]).classList.add('active');
    renderPage(shortcuts[e.key]);
  }
});

// ===== INITIAL RENDER =====
renderDashboard();

// ===== HTML PAGES =====

async function renderHtmlPages() {
  const list = document.getElementById('html-files-list');
  if (!list) return;
  list.innerHTML = '<div style="color:var(--text3);font-size:12px;">Loading…</div>';
  try {
    const res = await fetch('/api/uploads');
    const files = await res.json();
    if (!files.length) {
      list.innerHTML = '<div class="empty-state" style="padding:30px 0;"><div class="empty-state-icon">📄</div><div class="empty-state-text">No HTML files uploaded yet.<br>Click the upload button or drag files above.</div></div>';
      return;
    }
    const baseUrl = window.location.origin;
    list.innerHTML = files.map(f => {
      const fullUrl = baseUrl + f.url;
      const sizeKB = (f.size / 1024).toFixed(1);
      return `<div class="upload-file-card">
        <div class="upload-file-icon">📄</div>
        <div class="upload-file-info">
          <div class="upload-file-name">${escapeHtml(f.name)}</div>
          <div class="upload-file-meta">${sizeKB} KB · Uploaded ${f.uploaded}</div>
        </div>
        <div class="upload-file-actions">
          <input class="upload-link-input" value="${escapeHtml(fullUrl)}" readonly onclick="this.select();document.execCommand('copy');showToast('Link copied!','success')" title="Click to copy link">
          <a href="${f.url}" target="_blank" class="btn btn-sm" title="Open">Open ↗</a>
          <button class="btn btn-sm btn-danger" onclick="deleteUploadedFile('${escapeHtml(f.name)}')" title="Delete">✕</button>
        </div>
      </div>`;
    }).join('');
  } catch (e) {
    list.innerHTML = '<div style="color:var(--red);font-size:12px;">Failed to load files.</div>';
  }
}

function escapeHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

async function uploadHtmlFiles(event) {
  const input = event.target;
  if (!input.files || !input.files.length) return;
  const formData = new FormData();
  for (const f of input.files) formData.append('files', f);
  try {
    const res = await fetch('/api/uploads', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.ok) {
      showToast(`Uploaded ${data.files.length} file(s)`, 'success');
      renderHtmlPages();
    } else {
      showToast(data.error || 'Upload failed', 'warning');
    }
  } catch (e) {
    showToast('Upload failed', 'warning');
  }
  input.value = '';
}

async function deleteUploadedFile(name) {
  if (!confirm(`Delete "${name}"?`)) return;
  try {
    const res = await fetch('/api/uploads/' + encodeURIComponent(name), { method: 'DELETE' });
    const data = await res.json();
    if (data.ok) {
      showToast('Deleted ' + name, 'success');
      renderHtmlPages();
    } else showToast(data.error || 'Delete failed', 'warning');
  } catch (e) { showToast('Delete failed', 'warning'); }
}

// Drag & drop on the upload area
(function() {
  const area = document.getElementById('html-upload-area');
  if (!area) return;
  ['dragenter','dragover'].forEach(ev => area.addEventListener(ev, e => { e.preventDefault(); area.classList.add('drag-over'); }));
  ['dragleave','drop'].forEach(ev => area.addEventListener(ev, () => area.classList.remove('drag-over')));
  area.addEventListener('drop', e => {
    e.preventDefault();
    const files = e.dataTransfer.files;
    if (!files.length) return;
    const input = document.getElementById('html-upload-input');
    input.files = files;
    input.dispatchEvent(new Event('change'));
  });
})();
