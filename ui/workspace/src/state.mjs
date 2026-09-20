// Pure event projection: only backend facts, scoped IDs, and idempotent replay.
export const stages = ['Incident intake', 'Reproduction', 'Runtime evidence', 'Investigation',
  'Evidence audit', 'Root cause', 'Remediation', 'Approval', 'Execution', 'Verification', 'PR / Report'];
export const agents = ['Investigator', 'Evidence Auditor', 'Remediation Planner', 'Executor', 'Verifier'];

export function emptyState(incident = null) {
  return { incident, run: {}, events: [], seen: new Set(), cursor: '0', evidence: new Map(),
    hypotheses: [], verdict: null, stages: {}, agents: {}, currentStage: null };
}

export function applyEvent(state, event) {
  if (!event.id || event.investigation_id !== state.incident?.id || state.seen.has(String(event.id))) return false;
  state.seen.add(String(event.id));
  if (BigInt(event.id) > BigInt(state.cursor)) state.cursor = String(event.id);
  state.events.push(event);
  state.events.sort((a, b) => Number(a.sequence) - Number(b.sequence));
  const d = event.data || {}, type = event.type;
  if (type === 'stage.changed') {
    state.currentStage = d.label || event.stage;
    state.stages[state.currentStage] = 'Visited';
  }
  if (type === 'incident.reported') state.stages['Incident intake'] = 'Recorded';
  if (type === 'reproduction.result') state.stages.Reproduction = d.result?.data?.reproduced === true ? 'Reproduced' : 'Not reproduced';
  if (type === 'agent.started') state.agents[d.label] = 'running';
  if (type === 'agent.finished') state.agents[d.label] = 'finished';
  if (type === 'agent.failed') state.agents[d.label] = 'failed';
  if (type === 'evidence.added' && d.id) state.evidence.set(d.id, { ...d, at: event.at });
  if (type === 'hypothesis.updated') state.hypotheses = d.hypotheses || [];
  if (type === 'auditor.verdict') state.verdict = d;
  const status = { 'run.queued': 'STARTING', 'run.started': 'RUNNING', 'run.resumed': 'RUNNING',
    'run.pause_requested': 'PAUSE_REQUESTED', 'run.paused': 'PAUSED', 'run.stop_requested': 'STOP_REQUESTED',
    'run.stopped': 'STOPPED', 'run.completed': 'FINISHED', 'run.failed': 'FAILED',
    'patch.ready': 'AWAITING_APPROVAL', 'verification.result': d.status }[type];
  if (status) state.run.status = status;
  if (type === 'approval.received') state.run.status = d.decision;
  if (type === 'report.ready' && d.report) state.run.final = d.report;
  if (type === 'verification.result') state.run.verification = d;
  return true;
}

export function actionAllowed(state, action) {
  const r = state.run, status = r.status;
  if (!state.incident) return false;
  if (action === 'runs') return !status;
  if (action === 'pause') return status === 'RUNNING';
  if (action === 'resume') return ['PAUSED', 'INTERRUPTED'].includes(status);
  if (action === 'stop') return ['STARTING', 'RUNNING', 'PAUSE_REQUESTED', 'PAUSED'].includes(status);
  if (action === 'messages') return !!r.session && ['RUNNING', 'PAUSE_REQUESTED', 'PAUSED'].includes(status);
  if (action === 'plan') return r.final?.status === 'ROOT_CAUSE_SUPPORTED' && !['STARTING', 'RUNNING', 'APPROVED'].includes(status);
  if (action === 'approve' || action === 'reject') return status === 'AWAITING_APPROVAL' && !!r.patch_hash;
  if (action === 'execute') return status === 'APPROVED';
  return action === 'snapshot';
}

export function evidenceType(e) {
  const tool = e.tool || '';
  if (/database|sql/.test(tool)) return 'database';
  if (/file|source|search/.test(tool)) return 'source';
  if (/logs/.test(tool)) return 'log';
  if (/test|reproduction/.test(tool)) return 'test';
  if (/http/.test(tool)) return 'http';
  return 'other';
}
