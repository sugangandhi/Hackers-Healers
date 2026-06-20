// ─── Sub-tab switching within referralSection ─────────────────────────────────
const refTabs = document.querySelectorAll('#referralSection .tab');

function setActiveTab(tab) {
  refTabs.forEach(btn => {
    const isActive = btn.dataset.tab === tab;
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-selected', String(isActive));
  });
  document.getElementById('outboundPanel').classList.toggle('hidden', tab !== 'outbound');
  document.getElementById('inboundPanel').classList.toggle('hidden',  tab !== 'inbound');
}

refTabs.forEach(btn => btn.addEventListener('click', () => setActiveTab(btn.dataset.tab)));

// ─── Inbound sample loader ────────────────────────────────────────────────────
const loadInboundSample = document.getElementById('loadInboundSample');

if (loadInboundSample) {
  loadInboundSample.addEventListener('click', () => {
    document.querySelectorAll('[data-main-tab]').forEach(t => {
      if (t.dataset.mainTab === 'referral') t.click();
    });
    setActiveTab('inbound');
    const inp = document.getElementById('documentInput');
    if (inp) inp.value = SAMPLE_DATA.inbound;
  });
}

// ─── OUTBOUND REFERRAL ────────────────────────────────────────────────────────
let refSelectedFile  = null;
let refCurrentResult = null;

const refDropzone     = document.getElementById('refDropzone');
const refFileInput    = document.getElementById('refFileInput');
const refPreview      = document.getElementById('refDropzonePreview');
const refFileNameEl   = document.getElementById('refFileName');
const refClearFileBtn = document.getElementById('refClearFileBtn');
const refPatientSel   = document.getElementById('refPatientSelect');
const fillReferralBtn = document.getElementById('fillReferralBtn');

// Load patient list
(async function loadRefPatients() {
  try {
    const res  = await fetch(`${API_BASE}/patients`);
    const data = await res.json();
    data.patients.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = `${p.name}  (DOB: ${p.birthDate})`;
      refPatientSel.appendChild(opt);
    });
  } catch { /* backend not yet running */ }
})();

function setRefFile(file) {
  refSelectedFile = file;
  refFileNameEl.textContent = file.name;
  refDropzone.querySelector('.dropzone-inner').classList.add('hidden');
  refPreview.classList.remove('hidden');
  updateRefBtn();
}

function clearRefFile() {
  refSelectedFile = null;
  refFileInput.value = '';
  refDropzone.querySelector('.dropzone-inner').classList.remove('hidden');
  refPreview.classList.add('hidden');
  updateRefBtn();
}

function updateRefBtn() {
  fillReferralBtn.disabled = !refSelectedFile || !refPatientSel.value;
}

refFileInput.addEventListener('change', e => { if (e.target.files[0]) setRefFile(e.target.files[0]); });
refClearFileBtn.addEventListener('click', clearRefFile);
refPatientSel.addEventListener('change', updateRefBtn);
refDropzone.addEventListener('dragover',  e => { e.preventDefault(); refDropzone.classList.add('drag-over'); });
refDropzone.addEventListener('dragleave', ()  => refDropzone.classList.remove('drag-over'));
refDropzone.addEventListener('drop', e => {
  e.preventDefault();
  refDropzone.classList.remove('drag-over');
  if (e.dataTransfer.files[0]) setRefFile(e.dataTransfer.files[0]);
});

// Timer
let _refStart    = null;
let _refInterval = null;
let _refStepStart = {};

function startRefTimer() {
  _refStart    = Date.now();
  _refStepStart = {};
  document.getElementById('refTimer').textContent = '0.0s';
  _refInterval = setInterval(() => {
    document.getElementById('refTimer').textContent =
      `${((Date.now() - _refStart) / 1000).toFixed(1)}s`;
  }, 100);
}

function stopRefTimer() { clearInterval(_refInterval); }

function setRefStep(n, state) {
  const dot    = document.getElementById(`refStep${n}dot`);
  const timeEl = document.getElementById(`refStep${n}time`);
  if (!dot) return;
  dot.className = `step-indicator ${state}`;
  if (state === 'active') {
    _refStepStart[n] = Date.now();
    if (timeEl) { timeEl.classList.add('hidden'); timeEl.textContent = ''; }
  }
  if ((state === 'done' || state === 'error') && _refStepStart[n] && timeEl) {
    timeEl.textContent = `${((Date.now() - _refStepStart[n]) / 1000).toFixed(1)}s`;
    timeEl.classList.remove('hidden');
  }
}

function showRefPanel(name) {
  document.getElementById('refProgressLog').classList.toggle('hidden',  name !== 'progress');
  document.getElementById('refErrorSection').classList.toggle('hidden', name !== 'error');
  const idle    = document.getElementById('refIdle');
  const results = document.getElementById('refResults');
  idle.style.display = name === 'idle' ? 'flex' : 'none';
  results.classList.toggle('hidden', name !== 'results');
}

function setRefStatus(txt) { document.getElementById('refStatus').textContent = txt; }

// Fill referral button handler
fillReferralBtn.addEventListener('click', async () => {
  if (!refSelectedFile || !refPatientSel.value) return;
  const patientId = refPatientSel.value;

  setRefStatus('Processing…');
  showRefPanel('progress');
  setRefStep(1, 'pending');
  setRefStep(2, 'pending');
  startRefTimer();

  try {
    // Stage 1: OCR
    setRefStep(1, 'active');
    const f1 = new FormData();
    f1.append('file', refSelectedFile);
    const ocrRes = await fetch(`${API_BASE}/ocr-extract`, { method: 'POST', body: f1 });
    if (!ocrRes.ok) throw new Error((await ocrRes.json()).detail || 'OCR failed');
    const ocrData = await ocrRes.json();
    setRefStep(1, 'done');

    // Stage 2: AI fill
    setRefStep(2, 'active');
    const f2 = new FormData();
    f2.append('file', refSelectedFile);
    f2.append('patient_id', patientId);
    f2.append('ocr_text', ocrData.ocr_text);
    const fillRes = await fetch(`${API_BASE}/fill-form`, { method: 'POST', body: f2 });
    if (!fillRes.ok) throw new Error((await fillRes.json()).detail || 'AI fill failed');
    const data = await fillRes.json();
    refCurrentResult = data;
    setRefStep(2, 'done');
    stopRefTimer();

    setRefStatus('Review draft');
    renderRefResults(data);

  } catch (err) {
    stopRefTimer();
    [1, 2].forEach(n => {
      const dot = document.getElementById(`refStep${n}dot`);
      if (dot && (dot.className.includes('active') || dot.className.includes('pending')))
        setRefStep(n, 'error');
    });
    setRefStatus('Error');
    showRefPanel('error');
    document.getElementById('refErrorMsg').textContent = err.message;
  }
});

function renderRefResults(data) {
  document.getElementById('refFormTitle').textContent = data.form_type || 'Referral';
  document.getElementById('refFormMeta').textContent  = data.issuer    || '';

  const s   = data.confidence_summary || {};
  const sum = document.getElementById('refConfidenceSummary');
  sum.innerHTML =
    `<span class="conf-chip high"><span>${s.HIGH    || 0}</span> filled</span>` +
    `<span class="conf-chip medium"><span>${s.MEDIUM || 0}</span> uncertain</span>` +
    `<span class="conf-chip low"><span>${s.LOW      || 0}</span> low confidence</span>` +
    `<span class="conf-chip missing"><span>${s.MISSING || 0}</span> missing</span>`;
  sum.classList.remove('hidden');

  const container = document.getElementById('refFieldsPanel');
  const fields    = data.filled_fields || [];
  container.innerHTML = fields.length
    ? `<div class="fields-list">${fields.map(buildRefFieldRow).join('')}</div>`
    : '';

  showRefPanel('results');
}

function buildRefFieldRow(f) {
  const conf = (f.confidence || 'MISSING').toLowerCase();
  return `
    <div class="field-row ${conf}" data-key="${esc(f.key)}" data-conf="${esc(f.confidence || 'MISSING')}">
      <div class="field-row-header"><span class="field-label-text">${esc(f.label)}</span></div>
      <input class="editable-value" type="text"
             value="${esc(f.value || '')}"
             placeholder="${conf === 'missing' ? 'Required — please fill in' : ''}" />
      <div class="field-meta">
        ${f.source ? `<span class="field-source">${esc(f.source)}</span>` : ''}
        ${f.note   ? `<span class="field-note">${esc(f.note)}</span>`     : ''}
      </div>
    </div>`;
}

document.getElementById('refDownloadBtn').addEventListener('click', async () => {
  if (!refSelectedFile || !refCurrentResult) return;
  const fields = Array.from(document.querySelectorAll('#refFieldsPanel .field-row')).map(row => ({
    key:        row.getAttribute('data-key'),
    value:      row.querySelector('.editable-value')?.value || '',
    confidence: row.getAttribute('data-conf') || 'MEDIUM',
    label:      row.querySelector('.field-label-text')?.textContent || '',
  }));
  const form = new FormData();
  form.append('file', refSelectedFile);
  form.append('fields_json', JSON.stringify(fields));
  try {
    const res = await fetch(`${API_BASE}/generate-pdf`, { method: 'POST', body: form });
    if (!res.ok) throw new Error('PDF generation failed');
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = refSelectedFile.name.replace(/\.[^.]+$/, '') + '-referral.pdf';
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) { alert('Download failed: ' + err.message); }
});

document.getElementById('refDiscardBtn').addEventListener('click', () => {
  refCurrentResult = null;
  clearRefFile();
  showRefPanel('idle');
  setRefStatus('Ready');
  document.getElementById('refConfidenceSummary').classList.add('hidden');
  stopRefTimer();
});

// ─── INBOUND SUMMARY ──────────────────────────────────────────────────────────
const analyzeBtn      = document.getElementById('analyzeBtn');
const clearBtn        = document.getElementById('clearBtn');
const inboundSummary  = document.getElementById('inboundSummary');
const changesList     = document.getElementById('changesList');
const followupList    = document.getElementById('followupList');
const missingInfoList = document.getElementById('missingInfoList');

analyzeBtn.addEventListener('click', runInbound);
clearBtn.addEventListener('click', clearInbound);
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    const panel = document.getElementById('inboundPanel');
    if (panel && !panel.classList.contains('hidden')) runInbound();
  }
});

async function runInbound() {
  const text = document.getElementById('documentInput')?.value?.trim();
  if (!text) return;

  const statusEl = document.getElementById('inboundStatus');
  if (statusEl) statusEl.textContent = 'Analysing…';
  analyzeBtn.disabled = true;
  inboundSummary.textContent = 'Analysing with AI…';
  [changesList, followupList, missingInfoList].forEach(el => { if (el) el.innerHTML = ''; });

  try {
    const res = await fetch(`${API_BASE}/summarize-inbound`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || 'Summarization failed');
    const data = await res.json();

    inboundSummary.textContent = data.summary || 'No summary generated.';
    renderList(changesList,     data.key_changes      || [], 'No key changes identified.');
    renderList(followupList,    data.followup_actions || [], 'No follow-up actions identified.');
    renderList(missingInfoList, data.missing_info     || [], 'No missing information identified.');
    if (statusEl) statusEl.textContent = 'Done';
  } catch (err) {
    inboundSummary.textContent = `Error: ${err.message}`;
    if (statusEl) statusEl.textContent = 'Error';
  } finally {
    analyzeBtn.disabled = false;
  }
}

function clearInbound() {
  const inp = document.getElementById('documentInput');
  if (inp) inp.value = '';
  inboundSummary.textContent = 'Run analysis to see the AI-generated summary.';
  [changesList, followupList, missingInfoList].forEach(el => { if (el) el.innerHTML = ''; });
  const statusEl = document.getElementById('inboundStatus');
  if (statusEl) statusEl.textContent = 'Ready';
}

function renderList(el, items, emptyLabel) {
  if (!el) return;
  el.innerHTML = '';
  const entries = items.length ? items : [emptyLabel];
  entries.forEach(item => {
    const li = document.createElement('li');
    li.textContent = item;
    el.appendChild(li);
  });
}

function esc(str) {
  return String(str || '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Default to outbound tab on load
setActiveTab('outbound');
