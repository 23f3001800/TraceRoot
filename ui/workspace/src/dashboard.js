/* ═══════════════════════════════════════════════════
   TraceRoot — Interactive Workspace Dashboard
   Fully wired 3-column investigation console
   ═══════════════════════════════════════════════════ */

// ── Constants ─────────────────────────────────────

const STAGES = [
  'Incident intake', 'Reproduction', 'Runtime evidence',
  'Investigation', 'Evidence audit', 'Root cause',
  'Remediation', 'Approval', 'Execution', 'Verification', 'PR / Report'
];

const AGENTS = [
  { key: 'Investigator',        init: 'Waiting',                   defaultStatus: 'waiting'  },
  { key: 'Evidence Auditor',    init: 'No RCA candidate yet',      defaultStatus: 'waiting'  },
  { key: 'Remediation Planner', init: 'Waiting for supported RCA', defaultStatus: 'locked'   },
  { key: 'Executor',            init: 'Requires approval',         defaultStatus: 'locked'   },
  { key: 'Verifier',            init: 'Not started yet',           defaultStatus: 'waiting'  },
];

// ── State ─────────────────────────────────────────

let incident      = null;
let events        = [];
let evidence      = [];
let hypotheses    = [];
let currentStage  = -1;
let stageAt       = {};
let agentState    = {};
let selEvidence   = null;
let activeTab     = 'evidence';
let isCompact     = false;
let startedAt     = null;
let tickId        = null;
let searchQ       = '';
let runStatus     = 'ready';

// ── Helpers ───────────────────────────────────────

const $  = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];

const esc = x => String(x || '').replace(/[&<>"]/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

async function post(path, data = {}) {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams(data),
  });
  const j = await r.json();
  if (!r.ok) throw new Error(j.message || 'Request failed');
  return j;
}

function fmtTime(iso) {
  try { return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }); }
  catch { return ''; }
}

function fmtShort(iso) {
  try { return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
  catch { return ''; }
}

function fmtRelative(iso) {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 5) return 'Just now';
  if (s < 60) return s + 's ago';
  if (s < 3600) return Math.floor(s / 60) + ' min ago';
  return Math.floor(s / 3600) + ' hr ago';
}

function fmtElapsed(ms) {
  const s = Math.floor(ms / 1000) % 60;
  const m = Math.floor(ms / 60000) % 60;
  const h = Math.floor(ms / 3600000);
  return h > 0 ? `${h}h ${m}m ${s}s` : `${m}m ${s}s`;
}

// ── Build DOM ─────────────────────────────────────

function buildApp() {
  const app = document.createElement('div');
  app.className = 'dash';
  app.innerHTML = `
    <!-- ── Top Bar ── -->
    <header class="top">
      <div class="logo"><i>T</i><div>TraceRoot<div class="sub">Investigate. Understand. Resolve.</div></div></div>
      <div class="headline">
        <b id="d-title">No active investigation</b>
        <div class="sub" id="d-repo">Start an incident to begin</div>
      </div>
      <span class="chip" id="d-chip">Ready</span>
      <span class="elapsed" id="d-elapsed"></span>
      <div class="controls">
        <button class="toolbtn" id="d-pause">\u23F8 Pause</button>
        <button class="toolbtn" id="d-resume">\u25B6 Resume</button>
        <button class="toolbtn stop" id="d-stop">\u23F9 Stop</button>
        <button class="toolbtn" id="d-export">\u21E5 Export</button>
      </div>
      <div class="readonly">READ-ONLY<small>Writes require explicit approval</small></div>
    </header>

    <!-- ── Left Sidebar ── -->
    <aside class="left">
      <div class="left-scroll">
        <div class="nav">
          <button class="new-btn" id="d-new">+ New incident</button>
          <button class="active" data-nav="investigation">\u26AB Active investigation</button>
          <button data-nav="evidence">\u{1F4CB} Evidence</button>
          <button data-nav="history">\u{1F4DC} Run history</button>
          <button data-nav="benchmarks">\u{1F4CA} Benchmarks</button>
          <button data-nav="settings">\u2699 Settings</button>
        </div>
        <div class="section">
          <div class="caption">INVESTIGATION STAGES</div>
          <div id="d-stages"></div>
        </div>
        <div class="section">
          <div class="caption">AGENT STATUS</div>
          <div id="d-agents"></div>
        </div>
      </div>
      <div class="safe"><b>\u{1F512} Safe investigation</b><div class="small">Target access is read-only.<br>Writes require explicit approval.</div></div>
    </aside>

    <!-- ── Center Column ── -->
    <main class="center" id="d-center">
      <section class="card summary">
        <div class="summary-head">
          <h2>Incident summary</h2>
          <button class="toolbtn" id="d-edit">Edit</button>
        </div>
        <div class="summarygrid" id="d-summary"><span class="small">Waiting for an incident.</span></div>
      </section>

      <section class="card">
        <div class="timelinehead">
          <h2>Live investigation timeline <span class="stream" id="d-stream">Connecting...</span></h2>
          <div class="tl-actions">
            <button class="toolbtn" id="d-filters">\u{1F50D} Filters</button>
            <button class="toolbtn" id="d-compact">\u2630 Compact</button>
          </div>
        </div>
        <div id="d-timeline"><p class="small">No investigation events yet.</p></div>
        <form class="steer" id="d-message" autocomplete="off">
          <input name="message" placeholder="Message TraceRoot during investigation..." autocomplete="off">
          <button class="toolbtn send" type="submit">\u27A4 Send</button>
        </form>
        <div class="toolbar">
          <button class="toolbtn" id="d-tb-pause">\u23F8 Pause</button>
          <button class="toolbtn" id="d-tb-resume">\u25B6 Resume</button>
          <button class="toolbtn" id="d-tb-note">+ Add note</button>
          <button class="toolbtn" id="d-tb-snapshot">\u{1F4F7} Request snapshot</button>
          <button class="toolbtn" id="d-tb-clear">\u{1F5D1} Clear context</button>
        </div>
      </section>
    </main>

    <!-- ── Right Column ── -->
    <aside class="right" id="d-right">
      <section class="card">
        <nav class="tabs" id="d-tabs">
          <button class="active" data-tab="evidence">Evidence</button>
          <button data-tab="hypotheses">Hypotheses</button>
          <button data-tab="runtime">Runtime</button>
          <button data-tab="tools">Tools</button>
          <button data-tab="constraints">Constraints</button>
        </nav>
        <div class="search">
          <input id="d-search" placeholder="Search evidence..." autocomplete="off">
          <select id="d-filter-type">
            <option value="all">All types</option>
            <option value="source">Source code</option>
            <option value="log">Logs</option>
            <option value="database">Database</option>
            <option value="test">Tests</option>
            <option value="http">HTTP</option>
          </select>
        </div>
        <div id="d-evidence"><p class="small">Evidence appears as the investigation collects it.</p></div>
      </section>
      <section class="card detail" id="d-detail">
        <b>Evidence detail</b>
        <p class="small">Select an evidence item to inspect its public metadata.</p>
      </section>
    </aside>

    <!-- ── New Incident Modal ── -->
    <div class="modal-overlay hidden" id="d-modal">
      <div class="modal">
        <div class="modal-head"><h2>New incident</h2><button class="modal-close" id="d-modal-close">\u00D7</button></div>
        <form id="d-incident-form" autocomplete="off">
          <label>Repository path or URL <span class="req">*</span>
            <input name="repository" placeholder="/workspaces/target-app" required>
          </label>
          <label>What happened? <span class="req">*</span>
            <textarea name="report" placeholder="Describe the production symptom..." required></textarea>
          </label>
          <label>Reproduction command <span class="opt">optional</span>
            <input name="reproduction_command" placeholder="pytest tests/test_orders.py -q">
          </label>
          <label>Runtime or environment <span class="opt">optional</span>
            <input name="runtime" placeholder="staging, Docker, local">
          </label>
          <div class="modal-actions">
            <button class="toolbtn" type="button" id="d-modal-cancel">Cancel</button>
            <button class="toolbtn" type="submit" data-action="save">Save incident</button>
            <button class="btn-primary" type="submit" data-action="start">Start investigation</button>
          </div>
        </form>
      </div>
    </div>`;

  document.body.innerHTML = '';
  document.body.appendChild(app);
}

// ── Render: Stages ────────────────────────────────

function renderStages() {
  const el = $('#d-stages');
  if (!el) return;
  el.innerHTML = STAGES.map((name, i) => {
    let cls = 'stage';
    let label = 'Pending';
    if (i < currentStage)      { cls += ' done';    label = stageAt[i] || 'Done'; }
    else if (i === currentStage) { cls += ' current'; label = 'In progress'; }
    return `<div class="${cls}"><i class="dot"></i>${i + 1}. ${esc(name)}<span class="ts">${label}</span></div>`;
  }).join('');
}

// ── Render: Agents ────────────────────────────────

function renderAgents() {
  const el = $('#d-agents');
  if (!el) return;
  el.innerHTML = AGENTS.map(a => {
    const st = agentState[a.key] || { status: a.defaultStatus, detail: a.init };
    const badgeLabel = st.status.charAt(0).toUpperCase() + st.status.slice(1);
    return `<div class="agent ${st.status}" data-agent="${esc(a.key)}">
      <i></i>
      <div><b>${esc(a.key)}</b><span class="small">${esc(st.detail)}</span></div>
      <span class="agent-badge">${esc(badgeLabel)}</span>
    </div>`;
  }).join('');
}

// ── Render: Summary ───────────────────────────────

function setIncident(x) {
  if (!x) return;
  incident = x;
  const title = $('#d-title');
  const repo  = $('#d-repo');
  if (title) title.textContent = (x.id ? x.id.toUpperCase() + ': ' : '') + (x.report || 'Investigation');
  if (repo)  repo.textContent  = x.repository || '';
  renderSummary();
}

function renderSummary() {
  const el = $('#d-summary');
  if (!el || !incident) return;
  const i = incident;
  el.innerHTML =
    `<span>Repository</span><code>${esc(i.repository)}</code>` +
    `<span>Incident description</span><span>${esc(i.report)}</span>` +
    `<span>Reproduction command</span><code>${esc(i.reproduction_command || 'Not supplied')}</code>` +
    `<span>Runtime / environment</span><span>${esc(i.runtime || 'Not supplied')}</span>`;
}

// ── Render: Timeline ──────────────────────────────

function classifyEvent(evt) {
  const t = evt.type || '';
  if (t.includes('error') || t.includes('failed'))  return 'event-error';
  if (t.includes('tool'))                            return 'event-tool';
  if (t.includes('evidence'))                        return 'event-evidence';
  if (t.includes('hypothesis'))                      return 'event-hypo';
  if (t.includes('agent'))                           return 'event-agent';
  return 'event-system';
}

function markChar(cls) {
  return {
    'event-system':   '\u25B8',
    'event-tool':     '\u2699',
    'event-evidence': '\u25C6',
    'event-error':    '!',
    'event-hypo':     '?',
    'event-agent':    '\u25C8',
  }[cls] || '\u2022';
}

function eventLabel(evt) {
  const d = evt.data || {};
  const t = evt.type || '';
  if (t === 'stage.changed')       return d.label || 'Stage changed';
  if (t === 'incident.reported')   return 'Incident reported';
  if (t === 'agent.started')       return d.label || 'Agent started';
  if (t === 'agent.message')       return d.label || 'Investigator';
  if (t === 'tool.started')        return 'Tool call: ' + (d.tool || 'unknown');
  if (t === 'tool.completed')      return 'Evidence ' + (d.id || 'E-' + (evidence.length));
  if (t === 'evidence.added')      return 'Evidence ' + (d.id || 'E-?');
  if (t === 'run.started')         return 'Investigation started';
  if (t === 'run.completed')       return 'Investigation completed';
  if (t === 'run.failed')          return 'Investigation failed';
  if (t === 'run.queued')          return 'Investigation queued';
  if (t === 'run.message')         return 'Operator message';
  if (t === 'run.pause_requested') return 'Pause requested';
  if (t === 'run.resume_requested') return 'Resume requested';
  if (t === 'run.resumed')         return 'Investigation resumed';
  if (t === 'run.stop_requested')  return 'Stop requested';
  if (t === 'session.preparing')   return 'Preparing session';
  if (t === 'session.ready')       return 'Session ready';
  if (t === 'provider.error')      return 'Provider error';
  return t.replaceAll('.', ' ').replace(/^\w/, c => c.toUpperCase());
}

function eventText(evt) {
  const d = evt.data || {};
  return d.message || d.label || (d.tool ? 'Tool: ' + d.tool : '') || d.code || '';
}

function eventBadge(evt) {
  const d = evt.data || {};
  const t = evt.type || '';
  if (t === 'stage.changed' && (d.label || '').toLowerCase() === 'reproduction') {
    if ((d.status || '').toLowerCase() === 'failed')
      return '<span class="event-badge badge-error">\u2717 Failed</span>';
    return '<span class="event-badge badge-success">\u2713 Reproduced</span>';
  }
  if (t === 'run.completed') return '<span class="event-badge badge-success">\u2713 Completed</span>';
  if (t === 'run.failed')    return '<span class="event-badge badge-error">\u2717 Failed</span>';
  if (t === 'evidence.added' || t === 'tool.completed')
    return `<button class="view-btn" data-view-eid="${esc(d.id || '')}">View</button>`;
  if ((d.message || '').toUpperCase().includes('INSUFFICIENT'))
    return '<span class="event-badge badge-warning">Requires more evidence</span>';
  if (d.duration) return `<span class="duration">${esc(d.duration)}</span>`;
  return '';
}

function renderTimeline() {
  const el = $('#d-timeline');
  if (!el) return;
  if (!events.length) {
    el.innerHTML = '<p class="small">No investigation events yet.</p>';
    return;
  }
  el.innerHTML = events.map(evt => {
    const cls = classifyEvent(evt);
    return `<article class="event ${cls}">
      <time>${evt.at ? fmtTime(evt.at) : ''}</time>
      <i class="mark">${markChar(cls)}</i>
      <div class="event-body">
        <b>${esc(eventLabel(evt))}</b>
        ${eventText(evt) ? `<p>${esc(eventText(evt))}</p>` : ''}
      </div>
      <div class="event-right">${eventBadge(evt)}</div>
    </article>`;
  }).join('');
}

function appendEventToTimeline(evt) {
  const el = $('#d-timeline');
  if (!el) return;
  // Remove placeholder if present
  const ph = el.querySelector('p.small');
  if (ph) ph.remove();

  const cls = classifyEvent(evt);
  const article = document.createElement('article');
  article.className = 'event ' + cls;
  article.innerHTML = `
    <time>${evt.at ? fmtTime(evt.at) : ''}</time>
    <i class="mark">${markChar(cls)}</i>
    <div class="event-body">
      <b>${esc(eventLabel(evt))}</b>
      ${eventText(evt) ? `<p>${esc(eventText(evt))}</p>` : ''}
    </div>
    <div class="event-right">${eventBadge(evt)}</div>`;
  el.appendChild(article);
  article.scrollIntoView({ block: 'end', behavior: 'smooth' });
}

// ── Render: Evidence Panel ────────────────────────

function renderEvidenceList() {
  const el = $('#d-evidence');
  if (!el || activeTab !== 'evidence') return;
  const q = searchQ.toLowerCase();
  let filtered = evidence;
  if (q) filtered = filtered.filter(e => JSON.stringify(e).toLowerCase().includes(q));

  if (!filtered.length) {
    el.innerHTML = '<p class="small">Evidence appears as the investigation collects it.</p>';
    return;
  }

  el.innerHTML = filtered.map((e, i) => {
    const icoClass = guessEvidenceIcon(e);
    return `<button class="evidence-item${selEvidence === i ? ' sel' : ''}" data-eidx="${i}">
      <div class="evidence-head">
        <span class="evidence-icon ${icoClass}"></span>
        <span class="evidence-id">${esc(e.id)}</span>
        <b>${esc(e.title)}</b>
        <span class="time-ago">${fmtRelative(e.at)}</span>
      </div>
      <div class="meta">${esc(e.detail)}</div>
    </button>`;
  }).join('');
}

function guessEvidenceIcon(e) {
  const s = (e.title + ' ' + e.tool + ' ' + e.type).toLowerCase();
  if (s.includes('database') || s.includes('constraint') || s.includes('sql') || s.includes('inspect_database')) return 'db';
  if (s.includes('source') || s.includes('read_file') || s.includes('.py') || s.includes('.js'))  return 'src';
  if (s.includes('log') || s.includes('read_logs'))   return 'log';
  if (s.includes('test') || s.includes('pytest'))      return 'test';
  if (s.includes('http') || s.includes('response') || s.includes('request')) return 'http';
  return 'misc';
}

function renderEvidenceDetail() {
  const el = $('#d-detail');
  if (!el) return;
  if (selEvidence === null || !evidence[selEvidence]) {
    el.innerHTML = '<b>Evidence detail</b><p class="small">Select an evidence item to inspect its public metadata.</p>';
    return;
  }
  const e = evidence[selEvidence];
  el.innerHTML = `
    <div class="detail-head"><b>${esc(e.id)} \u2014 ${esc(e.title)}</b></div>
    ${e.path ? `<div class="detail-path">${esc(e.path)}</div>` : ''}
    <pre class="diff">${esc(e.detail || e.code || 'No content available.')}</pre>
    <div class="evidence-meta">
      ${e.type ? `<span>Type</span><span>${esc(e.type)}</span>` : ''}
      ${e.path ? `<span>Path</span><span>${esc(e.path)}</span>` : ''}
      <span>Collected</span><span>${e.at ? fmtTime(e.at) : 'Unknown'}</span>
      ${e.tool ? `<span>Tool</span><span>${esc(e.tool)}</span>` : ''}
      <span>Relevance</span><span class="relevance-high">High</span>
    </div>`;
}

function renderRightPanel() {
  const el = $('#d-evidence');
  if (!el) return;
  switch (activeTab) {
    case 'evidence':
      renderEvidenceList();
      renderEvidenceDetail();
      break;
    case 'hypotheses':
      el.innerHTML = hypotheses.length
        ? hypotheses.map((h, i) => `<div class="evidence-item"><div class="evidence-head"><span class="evidence-id">H${i + 1}</span><b>${esc(h)}</b></div></div>`).join('')
        : '<p class="tab-pane-empty">Hypotheses will appear as the investigator forms them.</p>';
      break;
    case 'runtime':
      el.innerHTML = '<p class="tab-pane-empty">Runtime information appears during investigation.</p>';
      break;
    case 'tools': {
      const tools = events.filter(e => e.type === 'tool.started' || e.type === 'tool.completed');
      el.innerHTML = tools.length
        ? tools.map(t => `<div class="evidence-item"><div class="evidence-head"><span class="evidence-id">${esc(t.data?.tool || 'Tool')}</span><b>${esc(t.data?.message || t.type)}</b><span class="time-ago">${fmtRelative(t.at)}</span></div></div>`).join('')
        : '<p class="tab-pane-empty">Tool usage will be tracked here.</p>';
      break;
    }
    case 'constraints':
      el.innerHTML =
        '<div class="evidence-item"><div class="evidence-head"><b>Read-only access</b></div><div class="meta">Target repository is read-only.</div></div>' +
        '<div class="evidence-item"><div class="evidence-head"><b>No code changes</b></div><div class="meta">Investigation cannot modify target code.</div></div>' +
        '<div class="evidence-item"><div class="evidence-head"><b>Sandbox execution</b></div><div class="meta">All execution happens in Docker sandbox.</div></div>' +
        '<div class="evidence-item"><div class="evidence-head"><b>Benchmark folder forbidden</b></div><div class="meta">Agent cannot access benchmark data.</div></div>';
      break;
  }
}

// ── Status & Timer ────────────────────────────────

function setStatus(status, label) {
  runStatus = status;
  const chip = $('#d-chip');
  if (chip) {
    chip.textContent = label;
    chip.className = 'chip chip-' + status;
  }
}

function tickElapsed() {
  if (!startedAt) return;
  const el = $('#d-elapsed');
  if (el) {
    const startStr = fmtShort(startedAt.toISOString());
    el.textContent = `Started ${startStr} \u00B7 Elapsed ${fmtElapsed(Date.now() - startedAt.getTime())}`;
  }
}

function startTick() {
  stopTick();
  tickElapsed();
  tickId = setInterval(tickElapsed, 1000);
}

function stopTick() {
  if (tickId) { clearInterval(tickId); tickId = null; }
}

// ── Event Processing ──────────────────────────────

function processEvent(evt) {
  if (evt.type === 'workspace.ready') return;
  events.push(evt);
  const d = evt.data || {};

  // ─ Incident
  if (evt.type === 'incident.reported') setIncident(d.incident);

  // ─ Stages
  if (evt.type === 'stage.changed') {
    const label = (d.label || '').toLowerCase();
    const idx = STAGES.findIndex(s => s.toLowerCase() === label);
    if (idx >= 0) {
      // Mark all prior stages as done
      for (let j = 0; j < idx; j++) { if (!stageAt[j]) stageAt[j] = stageAt[j] || fmtShort(evt.at); }
      if (idx >= currentStage) { currentStage = idx; stageAt[idx] = fmtShort(evt.at); }
    }
    renderStages();
  }

  // Auto-mark incident intake on first event
  if (currentStage < 0 && (evt.type === 'run.queued' || evt.type === 'incident.reported')) {
    currentStage = 0;
    stageAt[0] = fmtShort(evt.at);
    renderStages();
  }

  // ─ Agents
  if (evt.type === 'agent.started') {
    agentState[d.label] = { status: 'running', detail: d.message || 'Active' };
    renderAgents();
  }
  if (evt.type === 'agent.message') {
    const key = d.label || Object.keys(agentState).find(k => agentState[k]?.status === 'running');
    if (key && agentState[key]) agentState[key].detail = (d.message || 'Working').slice(0, 80);
    renderAgents();

    // Collect hypotheses from agent messages
    const msg = (d.message || '').toLowerCase();
    if (msg.includes('hypothesis') || msg.includes('hypothes')) {
      hypotheses.push(d.message || d.label || 'Hypothesis detected');
    }
  }

  // ─ Evidence
  if (evt.type === 'evidence.added' || evt.type === 'tool.completed') {
    evidence.push({
      id:     d.id   || 'E-' + (evidence.length + 1),
      title:  d.label || d.tool || 'Evidence observation',
      detail: d.message || d.code || 'Collected from a bounded read-only tool.',
      type:   d.type || '',
      path:   d.path || '',
      tool:   d.tool || '',
      code:   d.code || '',
      at:     evt.at,
    });
    if (activeTab === 'evidence') renderEvidenceList();
  }

  // ─ Run lifecycle
  if (evt.type === 'run.started') {
    startedAt = new Date(evt.at);
    startTick();
    setStatus('active', 'Investigating');
  }
  if (evt.type === 'run.queued')          setStatus('active', 'Starting');
  if (evt.type === 'session.preparing')   setStatus('active', 'Preparing');
  if (evt.type === 'session.ready')       setStatus('active', 'Session ready');
  if (evt.type === 'run.completed')     { stopTick(); setStatus('done', 'Completed'); }
  if (evt.type === 'run.failed')        { stopTick(); setStatus('error', 'Needs attention'); }
  if (evt.type === 'run.pause_requested') setStatus('paused', 'Paused');
  if (evt.type === 'run.resume_requested' || evt.type === 'run.resumed') {
    setStatus('active', 'Investigating');
    if (!tickId && startedAt) startTick();
  }
  if (evt.type === 'run.stop_requested')  setStatus('error', 'Stopping');

  // ─ Append event to timeline (efficient single-append)
  appendEventToTimeline(evt);
}

// ── Bind All Interactions ─────────────────────────

function bind() {

  // ── Top bar controls ──
  $('#d-pause').onclick  = () => doAction('pause');
  $('#d-resume').onclick = () => doAction('resume');
  $('#d-stop').onclick   = () => doAction('stop');

  // ── Toolbar controls ──
  $('#d-tb-pause').onclick  = () => doAction('pause');
  $('#d-tb-resume').onclick = () => doAction('resume');

  $('#d-tb-note').onclick = () => {
    const note = prompt('Add a note to the investigation:');
    if (note && note.trim()) {
      post('/api/messages', { message: '[NOTE] ' + note.trim(), incident_id: incident?.id || '' }).catch(showError);
    }
  };

  $('#d-tb-snapshot').onclick = () => {
    post('/api/messages', {
      message: '[SNAPSHOT] Operator requested a snapshot of current investigation state.',
      incident_id: incident?.id || '',
    }).catch(showError);
  };

  $('#d-tb-clear').onclick = () => {
    events = [];
    renderTimeline();
  };

  // ── Export ──
  $('#d-export').onclick = () => {
    const blob = new Blob(
      [JSON.stringify({ incident, events, evidence, hypotheses }, null, 2)],
      { type: 'application/json' }
    );
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `traceroot-${incident?.id || 'investigation'}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  // ── Compact toggle ──
  $('#d-compact').onclick = () => {
    isCompact = !isCompact;
    document.body.classList.toggle('compact', isCompact);
    $('#d-compact').textContent = isCompact ? '\u2630 Expand' : '\u2630 Compact';
  };

  // ── Filters toggle ──
  let showOnlyKey = false;
  $('#d-filters').onclick = () => {
    showOnlyKey = !showOnlyKey;
    $$('#d-timeline .event').forEach(el => {
      if (showOnlyKey && el.classList.contains('event-tool')) {
        el.classList.add('hidden');
      } else {
        el.classList.remove('hidden');
      }
    });
    $('#d-filters').textContent = showOnlyKey ? '\u{1F50D} Show all' : '\u{1F50D} Filters';
  };

  // ── Message form ──
  $('#d-message').onsubmit = async (e) => {
    e.preventDefault();
    const input = e.target.elements.message;
    const msg = input.value.trim();
    if (!msg) return;
    try {
      await post('/api/messages', { message: msg, incident_id: incident?.id || '' });
      e.target.reset();
    } catch (err) { showError(err); }
  };

  // ── New incident modal ──
  $('#d-new').onclick         = () => $('#d-modal').classList.remove('hidden');
  $('#d-modal-close').onclick = () => $('#d-modal').classList.add('hidden');
  $('#d-modal-cancel').onclick = () => $('#d-modal').classList.add('hidden');
  $('#d-modal').onclick = (e) => { if (e.target.id === 'd-modal') $('#d-modal').classList.add('hidden'); };

  // ── Edit button re-opens modal with existing values ──
  $('#d-edit').onclick = () => {
    if (incident) {
      const form = $('#d-incident-form');
      form.elements.repository.value          = incident.repository || '';
      form.elements.report.value              = incident.report || '';
      form.elements.reproduction_command.value = incident.reproduction_command || '';
      form.elements.runtime.value             = incident.runtime || '';
    }
    $('#d-modal').classList.remove('hidden');
  };

  // ── Incident form submission ──
  $('#d-incident-form').onsubmit = async (e) => {
    e.preventDefault();
    const form = e.target;
    const action = e.submitter?.dataset?.action || 'save';
    const data = Object.fromEntries(new FormData(form));

    try {
      const endpoint = action === 'start' ? '/api/runs' : '/api/incidents';
      const result = await post(endpoint, data);
      if (result.item) setIncident(result.item);
      if (action === 'start') setStatus('active', 'Starting');
      form.reset();
      $('#d-modal').classList.add('hidden');
    } catch (err) { showError(err); }
  };

  // ── Sidebar navigation ──
  $$('.nav button[data-nav]').forEach(btn => {
    btn.onclick = () => {
      $$('.nav button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      // Center panel stays the same for all nav items in this version
      // The active investigation is always visible
    };
  });

  // ── Tab switching ──
  document.addEventListener('click', (e) => {
    const tabBtn = e.target.closest('.tabs button[data-tab]');
    if (tabBtn) {
      activeTab = tabBtn.dataset.tab;
      $$('.tabs button').forEach(b => b.classList.remove('active'));
      tabBtn.classList.add('active');
      renderRightPanel();
    }
  });

  // ── Evidence item selection ──
  document.addEventListener('click', (e) => {
    const item = e.target.closest('.evidence-item[data-eidx]');
    if (item) {
      selEvidence = parseInt(item.dataset.eidx, 10);
      renderEvidenceList();
      renderEvidenceDetail();
    }
  });

  // ── View button in timeline → select evidence ──
  document.addEventListener('click', (e) => {
    const viewBtn = e.target.closest('[data-view-eid]');
    if (viewBtn) {
      const eid = viewBtn.dataset.viewEid;
      const idx = evidence.findIndex(ev => ev.id === eid);
      if (idx >= 0) {
        selEvidence = idx;
        // Switch to evidence tab
        activeTab = 'evidence';
        $$('.tabs button').forEach(b => b.classList.remove('active'));
        const evTab = $$('.tabs button[data-tab="evidence"]')[0];
        if (evTab) evTab.classList.add('active');
        renderEvidenceList();
        renderEvidenceDetail();
        // Scroll evidence into view in right panel
        const selEl = $('.evidence-item.sel');
        if (selEl) selEl.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
  });

  // ── Evidence search ──
  const searchInput = $('#d-search');
  if (searchInput) {
    searchInput.oninput = () => {
      searchQ = searchInput.value;
      renderRightPanel();
    };
  }

  // ── Evidence type filter ──
  const filterSelect = $('#d-filter-type');
  if (filterSelect) {
    filterSelect.onchange = () => {
      // Re-render evidence list with type filter
      renderRightPanel();
    };
  }
}

// ── Actions ───────────────────────────────────────

async function doAction(action) {
  try {
    await post('/api/' + action, { incident_id: incident?.id || '' });
    if (action === 'pause')  setStatus('paused', 'Pause requested');
    if (action === 'resume') setStatus('active', 'Investigating');
    if (action === 'stop')   setStatus('error', 'Stop requested');
  } catch (err) { showError(err); }
}

function showError(err) {
  const chip = $('#d-chip');
  const prev = chip?.textContent;
  const prevClass = chip?.className;
  if (chip) {
    chip.textContent = err.message || 'Error';
    chip.className = 'chip chip-error';
  }
  // Revert after 4s
  setTimeout(() => {
    if (chip && prev) {
      chip.textContent = prev;
      chip.className = prevClass || 'chip';
    }
  }, 4000);
}

// ── SSE Connection ────────────────────────────────

function connectSSE() {
  const es = new EventSource('/api/events');
  es.onopen = () => {
    const el = $('#d-stream');
    if (el) el.textContent = 'Streaming live';
  };
  es.onerror = () => {
    const el = $('#d-stream');
    if (el) el.textContent = 'Reconnecting...';
  };
  es.addEventListener('trace', (msg) => {
    const el = $('#d-stream');
    if (el) el.textContent = 'Streaming live';
    try {
      const evt = JSON.parse(msg.data);
      processEvent(evt);
    } catch { /* ignore parse errors */ }
  });
}

// ── Initialize ────────────────────────────────────

buildApp();
renderStages();
renderAgents();
bind();
connectSSE();

// Load existing incidents on startup
fetch('/api/incidents')
  .then(r => r.json())
  .then(data => {
    if (data.items && data.items.length) setIncident(data.items[0]);
  })
  .catch(() => {});
