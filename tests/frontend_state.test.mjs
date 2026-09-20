import test from 'node:test';
import assert from 'node:assert/strict';
import { emptyState, applyEvent, actionAllowed } from '../ui/workspace/src/state.mjs';

const event = (id, type, data = {}, iid = 'one') => ({
  id: String(id), sequence: id, investigation_id: iid, type, data
});
test('replay deduplicates and isolates investigations', () => {
  const s = emptyState({ id: 'one' });
  assert.equal(applyEvent(s, event(1, 'tool.completed')), true);
  assert.equal(applyEvent(s, event(1, 'tool.completed')), false);
  assert.equal(applyEvent(s, event(2, 'run.started', {}, 'other')), false);
  assert.equal(s.events.length, 1);
  assert.equal(s.evidence.size, 0);
});
test('pause request is not a paused checkpoint', () => {
  const s = emptyState({ id: 'one' });
  applyEvent(s, event(1, 'run.started'));
  assert.equal(actionAllowed(s, 'pause'), true);
  applyEvent(s, event(2, 'run.pause_requested'));
  assert.equal(s.run.status, 'PAUSE_REQUESTED');
  assert.equal(actionAllowed(s, 'resume'), false);
  applyEvent(s, event(3, 'run.paused'));
  assert.equal(actionAllowed(s, 'resume'), true);
});
test('only structured hypotheses and reproduction results set facts', () => {
  const s = emptyState({ id: 'one' });
  applyEvent(s, event(1, 'stage.changed', { label: 'Reproduction' }));
  assert.notEqual(s.stages.Reproduction, 'Reproduced');
  applyEvent(s, event(2, 'agent.message', { message: 'hypothesis: guess' }));
  assert.deepEqual(s.hypotheses, []);
  applyEvent(s, event(3, 'hypothesis.updated', { hypotheses: [{ id: 'H1', claim: 'Fact' }] }));
  assert.equal(s.hypotheses[0].id, 'H1');
  applyEvent(s, event(4, 'reproduction.result', { result: { data: { reproduced: true } } }));
  assert.equal(s.stages.Reproduction, 'Reproduced');
  assert.equal(s.stages['Runtime evidence'], undefined);
});
test('execution requires explicit approval', () => {
  const s = emptyState({ id: 'one' });
  s.run = { status: 'AWAITING_APPROVAL', patch_hash: 'digest' };
  assert.equal(actionAllowed(s, 'execute'), false);
  applyEvent(s, event(1, 'approval.received', { decision: 'APPROVED' }));
  assert.equal(actionAllowed(s, 'execute'), true);
});
