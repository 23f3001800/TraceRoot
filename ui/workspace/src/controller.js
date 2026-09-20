import { emptyState, applyEvent, actionAllowed, evidenceType, stages, agents } from './state.mjs';

const $ = s => document.querySelector(s);
const all = s => [...document.querySelectorAll(s)];
const esc = x => String(x ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const json = x => esc(JSON.stringify(x, null, 2));
const time = at => at ? new Date(at).toLocaleTimeString() : '';
let state = emptyState(), stream, selection = null, tab = 'evidence', keyOnly = true, metrics = {};
let generation = 0, refreshTimer, busy = false;

async function request(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || 'Request failed');
  return result;
}
function notice(message, error = false) {
  const el = $('#d-notice');
  el.textContent = message;
  el.className = 'workspace-notice' + (error ? ' error' : '');
  el.hidden = !message;
}
function disabled(selector, enabled, reason) {
  all(selector).forEach(el => {
    el.disabled = !enabled || busy;
    el.title = enabled ? '' : reason;
  });
}
function pretty(value) { return String(value || 'Saved').replaceAll('_', ' '); }
function render() {
  const { incident, run } = state;
  $('#d-title').textContent = incident ? incident.report : 'No active investigation';
  $('#d-repo').textContent = incident?.repository || 'Create or select an incident';
  $('#d-chip').textContent = pretty(run.status);
  $('#d-chip').className = 'chip ' + (run.status === 'RUNNING' ? 'chip-active' :
    ['FAILED', 'INTERRUPTED'].includes(run.status) ? 'chip-error' : 'chip-paused');
  $('#d-elapsed').textContent = state.events.length ? 'Last event ' + time(state.events.at(-1).at) : '';
  $('#d-summary').innerHTML = incident ? [
    ['Repository', incident.repository], ['Incident', incident.id], ['Description', incident.report],
    ['Reproduction', incident.reproduction_command || 'Automatic bounded test selection'],
    ['Environment', incident.runtime || 'Isolated Docker'], ['Run', run.run_id || 'Not started'],
  ].map(([k, v]) => '<span>' + k + '</span><span>' + esc(v) + '</span>').join('') :
    '<p class="small">Save an incident or start an investigation.</p>';
  $('#d-stages').innerHTML = stages.map((s, i) =>
    '<div class="stage ' + (s === state.currentStage ? 'current' : '') + '"><i class="dot"></i>' +
    (i + 1) + '. ' + s + '<span class="ts">' + esc(state.stages[s] || 'Pending') + '</span></div>').join('');
  $('#d-agents').innerHTML = agents.map(a => {
    const status = state.agents[a] === 'running' && !['RUNNING', 'STARTING'].includes(run.status) ?
      'waiting' : state.agents[a] || 'waiting';
    return '<div class="agent ' + status + '"><i></i><b>' + a + '</b><span class="agent-badge">' + status + '</span></div>';
  }).join('');
  for (const action of ['pause', 'resume', 'stop'])
    disabled('#d-' + action + ', #d-tb-' + action, actionAllowed(state, action), 'Unavailable in the current run state.');
  disabled('#d-message input, #d-message button, #d-tb-note', actionAllowed(state, 'messages'), 'Steering requires an active or paused investigation session.');
  disabled('#d-export, #d-tb-snapshot', !!incident, 'Select an incident first.');
  disabled('#d-start-saved', actionAllowed(state, 'runs'), 'This incident already has a run.');
  renderTimeline();
  renderRight();
  renderRecovery();
  renderMetrics();
}
function renderMetrics() {
  $('#d-usage').innerHTML = '<span><b>' + Number(metrics.input_tokens || 0).toLocaleString() +
    '</b> input tokens</span><span><b>' + Number(metrics.output_tokens || 0).toLocaleString() +
    '</b> output tokens</span><span><b>' + ((metrics.model_latency_ms || 0) / 1000).toFixed(1) +
    's</b> model latency</span><span><b>' + (metrics.estimated_cost_usd == null ? 'Not configured' :
      '$' + metrics.estimated_cost_usd.toFixed(4)) + '</b> estimated cost</span>';
  $('#d-usage').title = metrics.cost_note || 'Measured model calls; configure rates to calculate a cost estimate.';
}
function renderTimeline() {
  const list = state.events.filter((e, index) => {
    if (!keyOnly) return true;
    if (['checkpoint.saved', 'stage.changed', 'evidence.added'].includes(e.type)) return false;
    if (e.type === 'tool.started' || e.type === 'agent.started') {
      const prefix = e.type.split('.')[0];
      return !state.events.slice(index + 1).some(next =>
        [prefix + '.finished', prefix + '.completed', prefix + '.failed'].includes(next.type) &&
        (prefix === 'tool' ? next.data?.tool === e.data?.tool : next.data?.label === e.data?.label));
    }
    return true;
  });
  $('#d-filters').textContent = keyOnly ? 'Show all events' : 'Agent steps';
  $('#d-timeline').innerHTML = list.map(e => {
    const d = e.data || {};
    const category = e.type.includes('failed') || e.type.includes('error') ? 'error' :
      e.type.startsWith('evidence.') ? 'evidence' : e.type.startsWith('tool.') ? 'tool' : 'system';
    const label = d.tool ? d.tool + ' · ' + e.type.split('.').at(-1) :
      d.label ? d.label + ' · ' + e.type.split('.').at(-1) : e.type.replaceAll('.', ' ');
    const duration = Number.isFinite(d.duration_ms) ? ' · ' + (d.duration_ms / 1000).toFixed(1) + 's' : '';
    const usage = d.usage ? ' · ' + ((d.usage.input_tokens || 0) + (d.usage.output_tokens || 0)).toLocaleString() + ' tokens' : '';
    return '<article class="event event-' + category + '"><time>' + time(e.at) +
      '</time><i class="mark">' + e.sequence + '</i><div class="event-body"><b>' +
      esc(label + duration + usage) + '</b><p>' + esc(d.message || d.status || '') +
      '</p><details><summary>Details</summary><pre class="public-json">' + json(d) +
      '</pre></details></div>' + (e.type === 'evidence.added' ? '<button class="view-btn" data-eid="' +
      esc(d.id) + '">View</button>' : '') + '</article>';
  }).join('') || '<p class="small">No recorded events.</p>';
}
function renderRight() {
  all('[data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  const el = $('#d-evidence');
  if (tab === 'evidence') {
    const query = $('#d-search').value.toLowerCase(), type = $('#d-filter-type').value;
    const items = [...state.evidence.values()].filter(e =>
      (type === 'all' || evidenceType(e) === type) && JSON.stringify(e).toLowerCase().includes(query));
    el.innerHTML = items.map(e => '<button class="evidence-item ' + (selection === e.id ? 'sel' : '') +
      '" data-eid="' + esc(e.id) + '"><div class="evidence-head"><span class="evidence-id">' +
      esc(e.id) + '</span><b>' + esc(e.title || e.tool) + '</b></div><div class="meta">' +
      esc(e.path || evidenceType(e)) + ' · ' + time(e.at) + '</div></button>').join('') ||
      '<p class="small">No matching collected evidence.</p>';
  } else if (tab === 'hypotheses') {
    el.innerHTML = state.hypotheses.map(h => '<details open class="evidence-item"><summary>' +
      esc(h.id || h.hypothesis_id) + ' ' + esc(h.claim) + '</summary><pre class="public-json">' +
      json(h) + '</pre></details>').join('') || '<p class="small">No structured hypotheses yet.</p>';
    if (state.verdict) el.innerHTML += '<h3>Auditor verdict</h3><pre class="public-json">' + json(state.verdict) + '</pre>';
  } else if (tab === 'runtime') {
    el.innerHTML = '<h3>Runtime session</h3><pre class="public-json">' + json({
      mode: state.incident?.runtime || 'Docker', session: state.run.session || null,
      status: state.run.status || 'Not started', deployed_runtime_verified: false
    }) + '</pre>';
  } else if (tab === 'tools') {
    el.innerHTML = state.events.filter(e => e.type.startsWith('tool.')).map(e =>
      '<details class="evidence-item"><summary>' + esc(e.data.tool) + ': ' + esc(e.type) +
      '</summary><pre class="public-json">' + json(e.data) + '</pre></details>').join('') ||
      '<p class="small">No tool calls recorded.</p>';
  } else {
    el.innerHTML = '<p>Investigation tools are read-only. Sandbox patch execution requires approval of the exact SHA-256 digest.</p>' +
      '<p>Sandbox verification does not establish deployed-runtime health. No automatic push, PR, merge, or deployment.</p>';
  }
  const e = state.evidence.get(selection);
  $('#d-detail').innerHTML = e ? '<h3>' + esc(e.id) + ' · ' + esc(e.title || e.tool) +
    '</h3><p class="small">' + esc(e.path || '') + '</p><pre class="public-json">' +
    json(e.result ?? e) + '</pre>' : '<h3>Evidence detail</h3><p class="small">Select a collected evidence item.</p>';
}
function renderRecovery() {
  const r = state.run;
  $('#d-results').innerHTML = r.final ? '<h3>Root-cause report</h3><pre class="public-json">' + json(r.final) + '</pre>' : '';
  $('#d-plan-content').innerHTML = r.plan ? '<pre class="public-json">' + json(r.plan) + '</pre>' : '<p class="small">Available after an independently supported root cause.</p>';
  $('#d-patch').innerHTML = r.patch ? r.patch.split('\n').map(line =>
    '<span class="' + (line.startsWith('+') ? 'diff-add' : line.startsWith('-') ? 'diff-del' : 'diff-context') +
    '">' + esc(line || ' ') + '</span>').join('') : 'No patch has been proposed.';
  $('#d-patch-hash').textContent = r.patch_hash ? 'SHA-256: ' + r.patch_hash : '';
  $('#d-verification').innerHTML = r.verification ? '<h3>Deterministic verification</h3><pre class="public-json">' +
    json(r.verification) + '</pre><p>Deployed runtime: not verified.</p>' : '';
  $('#d-limitation').textContent = r.error?.message || r.limitation || '';
  for (const action of ['plan', 'approve', 'reject', 'execute'])
    disabled('#d-' + action, actionAllowed(state, action), 'Prerequisite not met. Review the recorded run status.');
}

async function selectIncident(id) {
  const token = ++generation;
  stream?.close();
  clearTimeout(refreshTimer);
  const detail = await request('/api/incidents/' + encodeURIComponent(id));
  if (token !== generation) return;
  state = emptyState(detail.incident);
  detail.events.forEach(e => applyEvent(state, e));
  state.run = detail.run;
  metrics = detail.metrics || {};
  selection = null;
  render();
  connect(id, token);
}
async function refresh() {
  const id = state.incident?.id, token = generation;
  if (!id) return;
  const detail = await request('/api/incidents/' + encodeURIComponent(id));
  if (token !== generation) return;
  detail.events.forEach(e => applyEvent(state, e));
  state.run = detail.run;
  metrics = detail.metrics || {};
  render();
}
function connect(id, token) {
  stream = new EventSource('/api/events?investigation_id=' + encodeURIComponent(id) + '&after=' + state.cursor);
  stream.onopen = () => { if (token === generation) $('#d-stream').textContent = 'Connected'; };
  stream.onerror = () => { if (token === generation) $('#d-stream').textContent = 'Reconnecting; recorded events will replay'; };
  stream.addEventListener('trace', event => {
    if (token !== generation) return;
    try {
      if (!applyEvent(state, JSON.parse(event.data))) return;
      render();
      clearTimeout(refreshTimer);
      refreshTimer = setTimeout(() => refresh().catch(e => notice(e.message, true)), 150);
    } catch (e) { notice('Could not read a workspace event: ' + e.message, true); }
  });
}
async function action(name, extra = {}) {
  if (!actionAllowed(state, name)) throw new Error('This action is not available in the current run state.');
  const id = state.incident.id;
  busy = true; render();
  try {
    await request('/api/' + name, { incident_id: id, ...extra });
    notice(name === 'messages' ? 'Message queued for the next safe model boundary.' :
      name === 'pause' ? 'Pause requested; waiting for a safe checkpoint.' : 'Request accepted: ' + name);
    await refresh();
  } finally { busy = false; render(); }
}
function invoke(name, extra) { action(name, extra).catch(e => notice(e.message, true)); }
async function showHistory() {
  const data = await request('/api/incidents');
  $('#d-history-list').innerHTML = data.items.map(i => '<button class="evidence-item" data-incident="' +
    esc(i.id) + '"><b>' + esc(i.report) + '</b><div class="meta">' + esc(i.id) + ' · ' +
    esc(i.repository) + ' · ' + esc(i.created_at) + '</div></button>').join('') || '<p>No saved incidents.</p>';
  $('#d-history').classList.remove('hidden');
}
function download() {
  const blob = new Blob([JSON.stringify({ incident: state.incident, run: state.run, events: state.events }, null, 2)],
    { type: 'application/json' });
  const anchor = document.createElement('a');
  const url = URL.createObjectURL(blob);
  anchor.href = url; anchor.download = 'traceroot-' + state.incident.id + '.json'; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function initializeWorkspace() {
  document.body.classList.add('agent-steps');
  $('#d-center').insertAdjacentHTML('afterbegin', '<div id="d-notice" role="status" aria-live="polite" hidden></div>' +
    '<section class="usage-strip" id="d-usage" aria-label="Model usage and estimated cost"></section>');
  $('.summary').insertAdjacentHTML('beforeend', '<button class="toolbtn" id="d-start-saved">Start saved incident</button>');
  $('#d-center').insertAdjacentHTML('beforeend', '<section class="card" id="d-recovery"><h2>Remediation & verification</h2>' +
    '<div id="d-results"></div><button class="toolbtn" id="d-plan">Generate remediation proposal</button>' +
    '<div id="d-plan-content"></div><h3>Exact patch review</h3><pre class="diff" id="d-patch"></pre>' +
    '<p class="small digest" id="d-patch-hash"></p><label>Approver <input id="d-approver" maxlength="80" autocomplete="name"></label>' +
    '<div class="toolbar"><button class="toolbtn" id="d-approve">Approve this patch</button>' +
    '<button class="toolbtn" id="d-reject">Reject</button><button class="toolbtn" id="d-execute">Execute approved patch in sandbox</button></div>' +
    '<p id="d-limitation" role="status"></p><div id="d-verification"></div>' +
    '<button class="toolbtn" disabled title="Publication review and authorized destination are not configured.">Publish draft PR unavailable</button></section>');
  document.body.insertAdjacentHTML('beforeend', '<div class="modal-overlay hidden" id="d-history"><section class="modal">' +
    '<div class="modal-head"><h2>Saved incidents & run history</h2><button class="toolbtn" id="d-history-close">Close</button></div>' +
    '<div id="d-history-list"></div></section></div>');
  document.body.insertAdjacentHTML('beforeend', '<div class="modal-overlay hidden" id="d-settings"><section class="modal">' +
    '<div class="modal-head"><h2>Usage estimate settings</h2><button class="toolbtn" id="d-settings-close">Close</button></div>' +
    '<p>Enter the rates from your provider agreement. Estimates are not billing totals.</p><form id="d-pricing-form">' +
    '<label>Exact model / deployment<input name="model" required maxlength="150"></label>' +
    '<label>Input USD per million tokens<input name="input_usd_per_million" type="number" min="0" step="any" required></label>' +
    '<label>Output USD per million tokens<input name="output_usd_per_million" type="number" min="0" step="any" required></label>' +
    '<button class="toolbtn" type="submit">Save pricing</button></form><p class="small" id="d-capabilities"></p></section></div>');
  $('#d-settings-close').onclick = () => $('#d-settings').classList.add('hidden');
  $('#d-pricing-form').onsubmit = async event => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    try {
      await request('/api/pricing', data); await refresh();
      $('#d-settings').classList.add('hidden'); notice('Pricing saved. Costs shown are estimates, not billing totals.');
    } catch (e) { notice(e.message, true); }
  };
  $('#d-edit').textContent = 'Duplicate incident';
  $('#d-tb-clear').textContent = 'Reset filters';
  $('#d-tb-snapshot').textContent = 'Save snapshot';
  $('#d-message input').maxLength = 2000;
  const form = $('#d-incident-form');
  form.elements.report.maxLength = 1000;
  form.elements.runtime.disabled = true;
  form.elements.runtime.placeholder = 'Deployed runtime connector not configured';
  form.elements.runtime.title = 'Local Docker investigation is available. Deployed targets are not wired yet.';
  for (const name of ['pause', 'resume', 'stop', 'plan', 'execute'])
    all('#d-' + name + ', #d-tb-' + name).forEach(b => b.onclick = () => invoke(name));
  $('#d-start-saved').onclick = () => invoke('runs');
  for (const name of ['approve', 'reject']) $('#d-' + name).onclick = () => {
    const approved_by = $('#d-approver').value.trim();
    if (!approved_by) return notice('Enter the approver name first.', true);
    invoke(name, { approved_by, patch_hash: state.run.patch_hash });
  };
  $('#d-tb-snapshot').onclick = () => invoke('snapshot');
  $('#d-tb-note').onclick = () => {
    const message = prompt('Note for the next investigator model request:');
    if (message?.trim()) invoke('messages', { message: message.trim() });
  };
  $('#d-message').onsubmit = async event => {
    event.preventDefault();
    const input = event.currentTarget.elements.message, message = input.value.trim();
    if (!message) return;
    try { await action('messages', { message }); input.value = ''; }
    catch (e) { notice(e.message, true); }
  };
  $('#d-export').onclick = download;
  $('#d-compact').textContent = 'Roomy layout';
  $('#d-compact').onclick = () => {
    document.body.classList.toggle('agent-steps');
    $('#d-compact').textContent = document.body.classList.contains('agent-steps') ? 'Roomy layout' : 'Compact layout';
  };
  $('#d-filters').onclick = () => {
    keyOnly = !keyOnly; $('#d-filters').textContent = keyOnly ? 'Show all events' : 'Hide tool events'; renderTimeline();
  };
  $('#d-tb-clear').onclick = () => {
    keyOnly = true; $('#d-search').value = ''; $('#d-filter-type').value = 'all';
    $('#d-filters').textContent = 'Hide tool events'; render();
  };
  $('#d-search').oninput = renderRight; $('#d-filter-type').onchange = renderRight;
  $('#d-new').onclick = () => { form.reset(); $('#d-modal').classList.remove('hidden'); };
  $('#d-edit').onclick = () => {
    form.reset();
    for (const name of ['repository', 'report', 'reproduction_command'])
      form.elements[name].value = state.incident?.[name] || '';
    $('#d-modal').classList.remove('hidden');
  };
  for (const id of ['d-modal-close', 'd-modal-cancel'])
    $('#' + id).onclick = () => $('#d-modal').classList.add('hidden');
  $('#d-history-close').onclick = () => $('#d-history').classList.add('hidden');
  form.onsubmit = async event => {
    event.preventDefault();
    const submitted = event.currentTarget;
    const data = Object.fromEntries(new FormData(submitted));
    const start = event.submitter?.dataset.action === 'start';
    all('#d-incident-form button').forEach(b => b.disabled = true);
    try {
      const result = await request(start ? '/api/runs' : '/api/incidents', data);
      $('#d-modal').classList.add('hidden');
      await selectIncident(result.item.id);
      notice(start ? 'Investigation queued.' : 'Incident saved. Start it when ready.');
    } catch (e) { notice(e.message, true); }
    finally { all('#d-incident-form button').forEach(b => b.disabled = false); }
  };
  document.addEventListener('click', event => {
    const ev = event.target.closest('[data-eid]'), history = event.target.closest('[data-incident]'),
      nextTab = event.target.closest('[data-tab]');
    if (ev) { selection = ev.dataset.eid; tab = 'evidence'; renderRight(); }
    if (nextTab) { tab = nextTab.dataset.tab; renderRight(); }
    if (history) {
      $('#d-history').classList.add('hidden');
      selectIncident(history.dataset.incident).catch(e => notice(e.message, true));
    }
  });
  all('[data-nav]').forEach(button => {
    const name = button.dataset.nav;
    if (name === 'benchmarks') {
      button.disabled = true; button.title = 'No workspace benchmark runner is connected.';
    } else button.onclick = async () => {
      try {
        if (name === 'history') await showHistory();
        else if (name === 'settings') {
          const capabilities = await request('/api/capabilities');
          $('#d-capabilities').textContent = capabilities.limitations.join(' ');
          $('#d-pricing-form').elements.model.value = state.run.summary?.model || metrics.unpriced_models?.[0] || '';
          $('#d-settings').classList.remove('hidden');
        } else if (name === 'evidence') { tab = 'evidence'; renderRight(); $('#d-right').scrollIntoView(); }
        else $('#d-center').scrollIntoView();
      } catch (e) { notice(e.message, true); }
    };
  });
  render();
  try {
    const data = await request('/api/incidents');
    if (data.items.length) await selectIncident(data.items[0].id);
    else $('#d-stream').textContent = 'No incident selected';
  } catch (e) { notice(e.message, true); }
  window.addEventListener('beforeunload', () => stream?.close());
}
