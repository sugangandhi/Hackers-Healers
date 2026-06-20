// API_BASE is defined in index.html before this script loads

function esc(str) {
  return String(str || '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── State ────────────────────────────────────────────────────────────────────
let selectedFile  = null;
let currentResult = null;

// ── Patient list ──────────────────────────────────────────────────────────────
async function loadPatients() {
  try {
    const res  = await fetch(`${API_BASE}/patients`);
    const data = await res.json();
    const sel  = document.getElementById('patientSelect');
    data.patients.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = `${p.name}  (DOB: ${p.birthDate})`;
      sel.appendChild(opt);
    });
    // Pre-select patient if coming from scheduler
    const prefill = sessionStorage.getItem('prefill_patient');
    if (prefill) {
      sel.value = prefill;
      sessionStorage.removeItem('prefill_patient');
      sessionStorage.removeItem('prefill_label');
      updateButtons();
    }
  } catch { /* backend may not be running yet */ }
}
loadPatients();

// ── File upload ───────────────────────────────────────────────────────────────
const dropzone        = document.getElementById('dropzone');
const fileInput       = document.getElementById('formFileInput');
const preview         = document.getElementById('dropzonePreview');
const fileNameEl      = document.getElementById('selectedFileName');
const clearFileBtn    = document.getElementById('clearFileBtn');
const fillBtn         = document.getElementById('fillFormBtn');
const analyseBtn      = document.getElementById('analyzeOnlyBtn');
const idlePlaceholder = document.getElementById('idlePlaceholder');

function setFile(file) {
  selectedFile = file;
  fileNameEl.textContent = file.name;
  dropzone.querySelector('.dropzone-inner').classList.add('hidden');
  preview.classList.remove('hidden');
  updateButtons();
}

function clearFile() {
  selectedFile = null;
  fileInput.value = '';
  dropzone.querySelector('.dropzone-inner').classList.remove('hidden');
  preview.classList.add('hidden');
  updateButtons();
}

function updateButtons() {
  const hasFile    = !!selectedFile;
  const hasPatient = !!document.getElementById('patientSelect').value;
  analyseBtn.disabled = !hasFile;
  fillBtn.disabled    = !hasFile || !hasPatient;
}

fileInput.addEventListener('change', e => { if (e.target.files[0]) setFile(e.target.files[0]); });
clearFileBtn.addEventListener('click', clearFile);
document.getElementById('patientSelect').addEventListener('change', updateButtons);

dropzone.addEventListener('dragover',  e => { e.preventDefault(); dropzone.classList.add('drag-over'); });
dropzone.addEventListener('dragleave', ()  => dropzone.classList.remove('drag-over'));
dropzone.addEventListener('drop', e => {
  e.preventDefault();
  dropzone.classList.remove('drag-over');
  if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]);
});

// ── Progress timer ────────────────────────────────────────────────────────────
let _timerStart    = null;
let _timerInterval = null;
let _stepStarts    = {};

function startTimer() {
  _timerStart = Date.now();
  _stepStarts = {};
  document.getElementById('progressTimer').textContent = '0.0s';
  _timerInterval = setInterval(() => {
    const s = ((Date.now() - _timerStart) / 1000).toFixed(1);
    document.getElementById('progressTimer').textContent = `${s}s`;
  }, 100);
}

function stopTimer() {
  clearInterval(_timerInterval);
}

// ── Progress steps ────────────────────────────────────────────────────────────
function setStep(n, state) {
  const dot    = document.getElementById(`step${n}dot`);
  const timeEl = document.getElementById(`step${n}time`);
  if (!dot) return;

  dot.className = `step-indicator ${state}`;

  if (state === 'active') {
    _stepStarts[n] = Date.now();
    if (timeEl) { timeEl.classList.add('hidden'); timeEl.textContent = ''; }
  }

  if ((state === 'done' || state === 'error') && _stepStarts[n]) {
    const elapsed = ((Date.now() - _stepStarts[n]) / 1000).toFixed(1);
    if (timeEl) {
      timeEl.textContent = `${elapsed}s`;
      timeEl.classList.remove('hidden');
    }
  }
}

function resetSteps() {
  [1, 2, 3].forEach(n => {
    setStep(n, 'pending');
    const timeEl = document.getElementById(`step${n}time`);
    if (timeEl) { timeEl.textContent = ''; timeEl.classList.add('hidden'); }
  });
}

// ── Main fill action — two real stages ───────────────────────────────────────
fillBtn.addEventListener('click', async () => {
  if (!selectedFile || !document.getElementById('patientSelect').value) return;

  const patientId = document.getElementById('patientSelect').value;

  setStatus('Processing…');
  showSection('progress');
  resetSteps();
  startTimer();

  try {
    // ── Stage 1: local OCR (fast, ~1s) ──────────────────────────────────────
    setStep(1, 'active');

    const form1 = new FormData();
    form1.append('file', selectedFile);

    const ocrRes = await fetch(`${API_BASE}/ocr-extract`, { method: 'POST', body: form1 });
    if (!ocrRes.ok) throw new Error((await ocrRes.json()).detail || 'OCR failed');
    const ocrData = await ocrRes.json();

    setStep(1, 'done');

    // ── Stage 2: Claude AI — analyze + fill (single call, ~3-5s) ────────────
    setStep(2, 'active');
    updateStepDetail(2, `Analyzing form and filling fields for selected patient…`);

    const form2 = new FormData();
    form2.append('file', selectedFile);
    form2.append('patient_id', patientId);
    form2.append('ocr_text', ocrData.ocr_text);

    const fillRes = await fetch(`${API_BASE}/fill-form`, { method: 'POST', body: form2 });
    if (!fillRes.ok) throw new Error((await fillRes.json()).detail || 'Fill failed');
    const data = await fillRes.json();
    currentResult = data;

    setStep(2, 'done');

    // ── Stage 3: render preview (already done server-side, just show it) ────
    setStep(3, 'active');
    await delay(120); // brief visual beat so step 3 is visible
    setStep(3, 'done');

    stopTimer();
    setStatus('Review draft');
    renderSideBySide(data);

  } catch (err) {
    stopTimer();
    [1, 2, 3].forEach(n => {
      if (document.getElementById(`step${n}dot`)?.classList.contains('active') ||
          document.getElementById(`step${n}dot`)?.classList.contains('pending'))
        setStep(n, 'error');
    });
    setStatus('Error');
    showSection('error');
    document.getElementById('errorMsg').textContent = err.message;
  }
});

function updateStepDetail(n, text) {
  const el = document.getElementById(`step${n}detail`);
  if (el) el.textContent = text;
}

// ── Side-by-side render ───────────────────────────────────────────────────────
function renderSideBySide(data) {
  const s = data.confidence_summary || {};
  document.getElementById('confHigh').textContent    = s.HIGH    || 0;
  document.getElementById('confMed').textContent     = s.MEDIUM  || 0;
  document.getElementById('confLow').textContent     = s.LOW     || 0;
  document.getElementById('confMissing').textContent = s.MISSING || 0;
  document.getElementById('confidenceSummary').classList.remove('hidden');

  document.getElementById('formTitle').textContent  = data.form_type || 'Form';
  document.getElementById('formIssuer').textContent = data.issuer    || '';

  renderPageStrip('origStrip',   data.original_pages || []);
  renderPageStrip('filledStrip', data.filled_pages   || []);
  renderFieldsPanel(data.filled_fields || []);

  showSection('review');
}

function renderPageStrip(containerId, pages) {
  const el = document.getElementById(containerId);
  if (!pages.length) {
    el.innerHTML = '<p class="no-preview">No preview available</p>';
    return;
  }
  el.innerHTML = pages.map((b64, i) =>
    `<img class="pdf-page-img" src="data:image/png;base64,${b64}" alt="Page ${i+1}" loading="lazy" />`
  ).join('');
}

function renderFieldsPanel(fields) {
  const container = document.getElementById('fieldsPanel');
  if (!fields.length) { container.innerHTML = ''; return; }
  container.innerHTML = `<div class="fields-list">${fields.map(f => buildFieldRow(f)).join('')}</div>`;
  container.querySelectorAll('.editable-value').forEach(input => {
    input.addEventListener('change', debounce(refreshFilledPreview, 600));
  });
}

function buildFieldRow(f) {
  const conf = (f.confidence || 'MISSING').toLowerCase();
  return `
    <div class="field-row ${conf}" data-key="${esc(f.key)}" data-conf="${esc(f.confidence || 'MISSING')}">
      <div class="field-row-header">
        <span class="field-label-text">${esc(f.label)}</span>
      </div>
      <input class="editable-value" type="text"
             value="${esc(f.value || '')}"
             placeholder="${conf === 'missing' ? 'Required — please fill in' : ''}" />
      <div class="field-meta">
        ${f.source ? `<span class="field-source">${esc(f.source)}</span>` : ''}
        ${f.note   ? `<span class="field-note">${esc(f.note)}</span>`   : ''}
      </div>
    </div>
  `;
}

async function refreshFilledPreview() {
  if (!selectedFile || !currentResult) return;
  const form = new FormData();
  form.append('file', selectedFile);
  form.append('fields_json', JSON.stringify(collectEditedFields()));
  try {
    document.getElementById('filledStrip').style.opacity = '0.5';
    await fetch(`${API_BASE}/generate-pdf`, { method: 'POST', body: form });
    document.getElementById('filledStrip').style.opacity = '1';
  } catch { document.getElementById('filledStrip').style.opacity = '1'; }
}

// ── Download ──────────────────────────────────────────────────────────────────
document.getElementById('downloadBtn').addEventListener('click', async () => {
  if (!selectedFile) return;

  const form = new FormData();
  form.append('file', selectedFile);
  form.append('fields_json', JSON.stringify(collectEditedFields()));

  setStatus('Generating…');
  document.getElementById('downloadBtn').disabled = true;

  try {
    const res = await fetch(`${API_BASE}/generate-pdf`, { method: 'POST', body: form });
    if (!res.ok) throw new Error('PDF generation failed');

    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = selectedFile.name.replace(/\.[^.]+$/, '') + '-approved.pdf';
    a.click();
    URL.revokeObjectURL(url);

    setStatus('Downloaded ✓');
    document.getElementById('downloadBtn').textContent = 'Downloaded ✓';
  } catch (err) {
    setStatus('Download error');
    alert('Download failed: ' + err.message);
    document.getElementById('downloadBtn').disabled = false;
  }
});

document.getElementById('discardBtn').addEventListener('click', () => {
  currentResult = null;
  showSection('idle');
  setStatus('Ready');
  document.getElementById('confidenceSummary').classList.add('hidden');
  resetSteps();
  stopTimer();
  clearFile();
  document.getElementById('downloadBtn').disabled = false;
  document.getElementById('downloadBtn').innerHTML = `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
    Confirm &amp; Download PDF`;
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function collectEditedFields() {
  return Array.from(document.querySelectorAll('#fieldsPanel .field-row')).map(row => ({
    key:        row.getAttribute('data-key'),
    value:      row.querySelector('.editable-value')?.value || '',
    confidence: row.getAttribute('data-conf') || 'MEDIUM',
    label:      row.querySelector('.field-label-text')?.textContent || row.getAttribute('data-key'),
  }));
}

function showSection(name) {
  const progressEl    = document.getElementById('progressLog');
  const reviewEl      = document.getElementById('reviewSection');
  const errorEl       = document.getElementById('errorSection');
  const placeholderEl = document.getElementById('idlePlaceholder');

  progressEl.classList.toggle('hidden',  name !== 'progress');
  reviewEl.classList.toggle('hidden',    name !== 'review');
  errorEl.classList.toggle('hidden',     name !== 'error');
  if (placeholderEl) placeholderEl.style.display = name === 'idle' ? '' : 'none';
}

function setStatus(text) {
  document.getElementById('ffStatus').textContent = text;
}

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}
