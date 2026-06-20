const tabs = document.querySelectorAll('.tab');
const inboundPanel = document.getElementById('inboundPanel');
const inputTitle = document.getElementById('inputTitle');
const inputDescription = document.getElementById('inputDescription');
const analysisDescription = document.getElementById('analysisDescription');
const modePill = document.getElementById('modePill');
const documentInput = document.getElementById('documentInput');
const analyzeBtn = document.getElementById('analyzeBtn');
const clearBtn = document.getElementById('clearBtn');
const loadReferralSample = document.getElementById('loadReferralSample');
const loadInboundSample = document.getElementById('loadInboundSample');

const scoreValue = document.getElementById('scoreValue');
const scoreBar = document.getElementById('scoreBar');
const missingList = document.getElementById('missingList');
const suggestionsList = document.getElementById('suggestionsList');
const structuredOutput = document.getElementById('structuredOutput');
const inboundSummary = document.getElementById('inboundSummary');
const changesList = document.getElementById('changesList');
const followupList = document.getElementById('followupList');

let activeTab = 'referral';
const referralFields = [
  { key: 'reason', label: 'Reason for referral', patterns: [/reason for referral/i, /request/i, /assessment/i] },
  { key: 'history', label: 'Relevant history', patterns: [/history/i, /pmh/i, /problem/i] },
  { key: 'meds', label: 'Medication list', patterns: [/medications?/i, /med list/i] },
  { key: 'allergies', label: 'Allergies', patterns: [/allerg/i] },
  { key: 'labs', label: 'Recent labs / imaging', patterns: [/labs?/i, /imaging/i, /ecg/i, /x-ray/i] },
  { key: 'urgency', label: 'Urgency / timeline', patterns: [/urgent/i, /asap/i, /timeline/i, /priority/i] },
  { key: 'contact', label: 'Referring provider contact info', patterns: [/doctor/i, /provider/i, /clinic/i, /contact/i] }
];

function setActiveTab(tab) {
  activeTab = tab;
  tabs.forEach(btn => {
    const isActive = btn.dataset.tab === tab;
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-selected', String(isActive));
  });
  const referralMode = tab === 'referral';
  inboundPanel.classList.toggle('hidden', referralMode);
  inputTitle.textContent = referralMode ? 'Referral draft' : 'Inbound specialist note';
  inputDescription.textContent = referralMode
    ? 'Paste or load a referral draft to check for missing fields before sending.'
    : 'Paste or load an inbound note to generate a concise clinical summary.';
  analysisDescription.textContent = referralMode
    ? 'See missing items, suggested fixes, and a structured referral summary.'
    : 'See key changes, follow-up items, and red flags from the specialist note.';
  modePill.textContent = referralMode ? 'Referral mode' : 'Inbound mode';
  document.getElementById('analyzeBtn').textContent = referralMode ? 'Check document' : 'Summarize note';
}

function analyzeReferral(text) {
  const lower = text.toLowerCase();
  const missing = [];
  const found = [];
  referralFields.forEach(field => {
    const exists = field.patterns.some(p => p.test(lower));
    if (exists) found.push(field.label);
    else missing.push(field.label);
  });
  const score = Math.max(20, Math.round(((referralFields.length - missing.length) / referralFields.length) * 100));
  const suggestions = missing.map(item => `Add ${item.toLowerCase()} to reduce bounce-back risk.`);
  const summary = [
    'Referral summary',
    `Detected sections: ${found.length ? found.join(', ') : 'none identified'}.`,
    `Completeness score: ${score}%.`,
    missing.length ? `Missing items: ${missing.join(', ')}.` : 'No major missing items detected.',
    'Doctor review recommended before sending.'
  ].join('
');
  return { score, missing, suggestions, summary, found };
}

function analyzeInbound(text) {
  const lower = text.toLowerCase();
  const changes = [];
  const followups = [];
  if (/amlodipine|medication change|added/i.test(text)) changes.push('Medication changed: a new blood pressure medication was added or adjusted.');
  if (/bp|blood pressure|hypertension/i.test(lower)) changes.push('Blood pressure remains an active issue and needs primary care follow-up.');
  if (/stress|non-cardiac|reassure/i.test(lower)) changes.push('Specialist impression suggests the symptoms may be non-cardiac.');
  if (/labs?|electrolytes/i.test(lower)) followups.push('Repeat the requested lab work in 2 weeks.');
  if (/follow up|4 weeks|worsen/i.test(lower)) followups.push('Book follow-up in 4 weeks and advise urgent care if symptoms worsen.');
  if (/red flag|shortness of breath|chest pain/i.test(lower)) followups.push('Monitor red flags such as exertional chest pain or shortness of breath.');
  const summary = [
    'Inbound note summary',
    changes.length ? `Key changes: ${changes.join(' ')}` : 'No major medication or management changes detected.',
    followups.length ? `Follow-up items: ${followups.join(' ')}` : 'No specific follow-up actions detected.',
    'Primary care review recommended to update the chart and next steps.'
  ].join('
');
  return { changes, followups, summary };
}

function renderList(el, items, emptyLabel) {
  el.innerHTML = '';
  if (!items.length) {
    const li = document.createElement('li');
    li.textContent = emptyLabel;
    el.appendChild(li);
    return;
  }
  items.forEach(item => {
    const li = document.createElement('li');
    li.textContent = item;
    el.appendChild(li);
  });
}

function runAnalysis() {
  const text = documentInput.value.trim();
  if (!text) return;
  if (activeTab === 'referral') {
    const result = analyzeReferral(text);
    scoreValue.textContent = `${result.score}%`;
    scoreBar.style.width = `${result.score}%`;
    renderList(missingList, result.missing, 'No missing fields detected.');
    renderList(suggestionsList, result.suggestions, 'No suggestions needed.');
    structuredOutput.textContent = result.summary;
  } else {
    const result = analyzeInbound(text);
    scoreValue.textContent = '--';
    scoreBar.style.width = '0%';
    missingList.innerHTML = '';
    suggestionsList.innerHTML = '';
    inboundSummary.textContent = result.summary;
    renderList(changesList, result.changes, 'No key changes detected.');
    renderList(followupList, result.followups, 'No follow-up items detected.');
    structuredOutput.textContent = 'Switch to Referral Checker for completeness scoring.';
  }
}

tabs.forEach(btn => btn.addEventListener('click', () => setActiveTab(btn.dataset.tab)));
loadReferralSample.addEventListener('click', () => {
  setActiveTab('referral');
  documentInput.value = SAMPLE_DATA.referral;
});
loadInboundSample.addEventListener('click', () => {
  setActiveTab('inbound');
  documentInput.value = SAMPLE_DATA.inbound;
});
clearBtn.addEventListener('click', () => {
  documentInput.value = '';
  scoreValue.textContent = '--';
  scoreBar.style.width = '0%';
  missingList.innerHTML = '';
  suggestionsList.innerHTML = '';
  structuredOutput.textContent = 'Run analysis to generate output.';
  inboundSummary.textContent = 'Load a note and run analysis to see the summary.';
  changesList.innerHTML = '';
  followupList.innerHTML = '';
});
analyzeBtn.addEventListener('click', runAnalysis);

document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') runAnalysis();
});

setActiveTab('referral');
