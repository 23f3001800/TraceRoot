import { initializeWorkspace } from './controller.js';

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

buildApp();
initializeWorkspace();

// ── Render: Stages ────────────────────────────────
