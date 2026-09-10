"""Recovery behavior across provider failure, process death and budget boundaries."""
import json
from pathlib import Path
import pytest

from traceroot.agents.investigator import Budget, investigate
from traceroot.agents.state import atomic_json, load_state, session_lock
from traceroot.llms.config import LLMConfig
from traceroot.llms.provider import ModelFailure
from test_investigator import (FakeProvider, active, task, action, finish, report,
                               logs_output, source_output, output, evidence)

class Sequence(FakeProvider):
    def __init__(self, decisions, retries=0):
        super().__init__(decisions)
        self.config = LLMConfig(max_transient_retries=retries)
    def generate(self, system, messages, schema, timeout):
        import itertools
        decision = next(self.decisions)
        if isinstance(decision, BaseException):
            self.requests.append((system, messages))
            raise decision
        self.decisions = itertools.chain([decision], self.decisions)
        return super().generate(system, messages, schema, timeout)

def unavailable_provider():
    return ModelFailure('provider_error', 'Gemini request failed (503).', retryable=True)

def reproduction_output():
    return output({
        'command': ['pytest'], 'exit_code': 1, 'stdout': 'expected 201, observed 500', 'stderr': '',
        'duration_ms': 1, 'passed': 0, 'failed': 1, 'skipped': 0, 'errors': 0, 'collected': 1,
        'failing_tests': ['tests/test_api.py::test_public_case'],
        'http_observations': [{'expected': 201, 'observed': 500, 'source': 'test'}],
        'outcome': 'failed', 'stdout_truncated': False, 'stderr_truncated': False,
        'selection_reason': 'public test', 'reproduced': True, 'expected': 201, 'observed': 500,
    })

def test_resume_preserves_reproduction_hypotheses_and_observations(active, monkeypatch):
    import traceroot.agents.investigator as module
    calls = []
    def reproduce(*a, **kw):
        calls.append('reproduction')
        return reproduction_output()
    monkeypatch.setitem(module.TOOLS, 'run_reproduction', reproduce)
    monkeypatch.setitem(module.TOOLS, 'read_logs', lambda *a, **kw: logs_output())
    first = Sequence([action('run_reproduction', {'repository_path': active.repository.source}),
                      action('read_logs', {}), unavailable_provider()])
    failed = investigate(active, task(active), first)
    run_id = failed['summary']['run_id']
    saved = load_state(active, run_id)
    assert saved['phase'] == 'paused'
    assert len(saved['steps']) == 2 and saved['reviewed_step'] == 1
    assert len(saved['hypotheses']) == 1
    assert saved['tool_failures'] == []  # HTTP 500 is application evidence.
    assert saved['provider_failures'][0]['after_step'] == 2
    second = Sequence([finish(report(reproduction='CONFIRMED'))])
    resumed = investigate(active, None, second, resume_run_id=run_id)
    assert calls == ['reproduction']
    assert resumed['summary']['tool_calls'] == 2
    assert resumed['summary']['model_turns'] == 4
    assert resumed['summary']['resume_count'] == 1
    assert resumed['summary']['run_id'] == run_id
    assert 'expected 201, observed 500' in json.dumps(second.requests)
    assert resumed['summary']['hypotheses'] == saved['hypotheses']
    assert resumed['summary']['duration_ms'] >= failed['summary']['duration_ms']

def test_transient_retry_recovers_without_tool_replay(active, monkeypatch):
    import traceroot.agents.investigator as module
    monkeypatch.setitem(module.TOOLS, 'read_logs', lambda *a, **kw: logs_output())
    provider = Sequence([action('read_logs', {}), unavailable_provider(), finish(report())], retries=1)
    result = investigate(active, task(active), provider)
    assert result['final']['status'] == 'INSUFFICIENT_EVIDENCE'
    assert result['summary']['tool_calls'] == 1
    saved = load_state(active, result['summary']['run_id'])
    assert len(saved['provider_failures']) == 1
    assert saved['tool_failures'] == []
    assert [e['delay_seconds'] for e in saved['events'] if e['event'] == 'provider_retry'] == [0.5]
    assert provider.requests[1] == provider.requests[2]

def test_retry_exhaustion_is_bounded_and_checkpointed(active):
    result = investigate(active, task(active), Sequence([unavailable_provider()] * 3, retries=2))
    saved = load_state(active, result['summary']['run_id'])
    assert saved['phase'] == 'paused'
    assert saved['turns'] == 3 and len(saved['provider_failures']) == 3
    assert [e['delay_seconds'] for e in saved['events'] if e['event'] == 'provider_retry'] == [0.5, 1.0]

def test_nontransient_errors_are_not_retried(active):
    result = investigate(active, task(active), Sequence([ModelFailure('provider_error', 'Unauthorized.')], retries=3))
    assert result['summary']['model_turns'] == 1
    assert result['summary']['resumable']

def test_process_death_during_model_keeps_completed_tool(active, monkeypatch):
    import traceroot.agents.investigator as module
    monkeypatch.setitem(module.TOOLS, 'read_logs', lambda *a, **kw: logs_output())
    with pytest.raises(KeyboardInterrupt):
        investigate(active, task(active), Sequence([action('read_logs', {}), KeyboardInterrupt()]))
    run_id = next((active.session_dir / 'agent-runs').iterdir()).name
    saved = load_state(active, run_id)
    assert saved['steps'][0]['tool'] == 'read_logs'
    assert saved['turns'] == 2 and saved['elapsed_seconds'] >= 60
    result = investigate(active, None, Sequence([finish(report())]), resume_run_id=run_id)
    assert result['summary']['tool_calls'] == 1

def test_process_death_during_tool_never_replays_unknown_action(active, monkeypatch):
    import traceroot.agents.investigator as module
    def crash(*a, **kw):
        raise KeyboardInterrupt()
    monkeypatch.setitem(module.TOOLS, 'read_logs', crash)
    with pytest.raises(KeyboardInterrupt):
        investigate(active, task(active), Sequence([action('read_logs', {})]))
    run_id = next((active.session_dir / 'agent-runs').iterdir()).name
    result = investigate(active, None, Sequence([]), resume_run_id=run_id)
    assert result['summary']['stopping_reason'] == 'tool_outcome_unknown'
    assert not result['summary']['resumable']

def test_resume_cannot_reset_budget_or_change_task(active, monkeypatch):
    import traceroot.agents.investigator as module
    monkeypatch.setitem(module.TOOLS, 'read_logs', lambda *a, **kw: logs_output())
    first = investigate(active, task(active), Sequence([action('read_logs', {}), unavailable_provider()]),
                        Budget(max_tool_calls=1))
    run_id = first['summary']['run_id']
    with pytest.raises(ValueError, match='original task'):
        investigate(active, {**task(active), 'bug_report': 'different'}, Sequence([]), resume_run_id=run_id)
    resumed = investigate(active, None, Sequence([action('read_logs', {})]), Budget(max_tool_calls=15), resume_run_id=run_id)
    assert resumed['summary']['budget']['max_tool_calls'] == 1
    assert resumed['summary']['tool_calls'] == 1
    assert resumed['final']['status'] == 'MAX_STEPS_REACHED'
    assert investigate(active, None, Sequence([]), resume_run_id=run_id) == resumed

def test_resume_rejects_snapshot_drift_and_foreign_session(active):
    from traceroot.contracts import ToolFailure
    first = investigate(active, task(active), Sequence([unavailable_provider()]))
    run_id = first['summary']['run_id']
    (active.repository.root / 'app/main.py').write_text('changed')
    with pytest.raises(ToolFailure, match='Snapshot changed'):
        investigate(active, None, Sequence([]), resume_run_id=run_id)
    active.config['id'] = 'another'
    with pytest.raises(ValueError, match='another investigation'):
        investigate(active, None, Sequence([]), resume_run_id=run_id)
    with pytest.raises(ValueError, match='run ID'):
        load_state(active, '../../anything')

def test_hypotheses_cannot_be_dropped_or_supported_without_evidence(active, monkeypatch):
    import traceroot.agents.investigator as module
    monkeypatch.setitem(module.TOOLS, 'read_logs', lambda *a, **kw: logs_output())
    first = investigate(active, task(active), Sequence([action('read_logs', {}), action('read_logs', {}), unavailable_provider()]))
    run_id = first['summary']['run_id']
    bad = {**finish(report()), 'hypotheses': []}
    old = first['summary']['hypotheses'][0]
    unsupported = {**finish(report()), 'hypotheses': [{**old, 'status': 'supported', 'confidence': 'high'}]}
    result = investigate(active, None, Sequence([bad, unsupported, bad]), resume_run_id=run_id)
    assert result['summary']['invalid_decisions'] == 3
    assert result['summary']['hypotheses'] == [old]

def test_supported_and_rejected_hypotheses_link_real_evidence(active, monkeypatch):
    import traceroot.agents.investigator as module
    monkeypatch.setitem(module.TOOLS, 'read_logs', lambda *a, **kw: logs_output())
    cited = evidence(1, '/data/entries/0/message', 'connection refused to port 9001')
    hypothesis = {'id': 'H1', 'claim': 'Connection refused.', 'status': 'supported',
                  'confidence': 'medium', 'evidence': [cited], 'missing_evidence': ['Source confirmation.']}
    rejected = {**hypothesis, 'status': 'rejected'}
    decisions = [action('read_logs', {}), {**action('read_logs', {}), 'hypotheses': [hypothesis]},
                 {**finish(report()), 'hypotheses': [rejected]}]
    result = investigate(active, task(active), Sequence(decisions))
    saved = load_state(active, result['summary']['run_id'])
    history = [e['hypotheses'] for e in saved['events'] if e['event'] == 'hypotheses_updated']
    assert history[-2] == [hypothesis] and history[-1] == [rejected]

def test_checkpoint_replace_failure_preserves_previous_state(tmp_path, monkeypatch):
    import traceroot.agents.state as module
    path = tmp_path / 'state.json'
    atomic_json(path, {'step': 1})
    def fail(*a):
        raise OSError('simulated disk failure')
    monkeypatch.setattr(module.os, 'replace', fail)
    with pytest.raises(OSError):
        atomic_json(path, {'step': 2})
    assert json.loads(path.read_text()) == {'step': 1}
    assert list(tmp_path.iterdir()) == [path]

def test_concurrent_investigation_is_rejected(active):
    with session_lock(active):
        with pytest.raises(ValueError, match='already owns'):
            investigate(active, task(active), Sequence([]))

def test_timeout_then_resume_can_reach_evidence_backed_root_cause(active, monkeypatch):
    import traceroot.agents.investigator as module
    monkeypatch.setitem(module.TOOLS, 'read_logs', lambda *a, **kw: logs_output())
    monkeypatch.setitem(module.TOOLS, 'read_file', lambda *a, **kw: source_output())
    failed = investigate(active, task(active), Sequence([
        action('read_logs', {}), ModelFailure('model_timeout', 'Request timed out.', True)]))
    final = report('ROOT_CAUSE_IDENTIFIED', evidence=[
        evidence(1, '/data/entries/0/message', 'connection refused to port 9001'),
        evidence(2, '/data/lines/0/text', 'configured_port = 9000'),
    ])
    resumed = investigate(active, None, Sequence([
        action('read_file', {'repository': active.repository.source, 'file_path': 'app/main.py'}),
        finish(final)]), resume_run_id=failed['summary']['run_id'])
    assert resumed['final']['status'] == 'ROOT_CAUSE_IDENTIFIED'
    assert resumed['summary']['tools_used'] == ['read_logs', 'read_file']
    assert resumed['summary']['provider_failures'] == 1

def test_root_cause_cannot_use_unattached_evidence(active, monkeypatch):
    import traceroot.agents.investigator as module
    monkeypatch.setitem(module.TOOLS, 'read_logs', lambda *a, **kw: logs_output())
    monkeypatch.setitem(module.TOOLS, 'read_file', lambda *a, **kw: source_output())
    final = report('ROOT_CAUSE_IDENTIFIED', evidence=[
        evidence(1, '/data/entries/0/message', 'connection refused to port 9001'),
        evidence(2, '/data/lines/0/text', 'configured_port = 9000'),
    ])
    h = {'id': 'H1', 'claim': final['root_cause'], 'status': 'supported', 'confidence': 'high',
         'evidence': final['evidence'][:1], 'missing_evidence': []}
    first = {**action('read_file', {'repository': active.repository.source, 'file_path': 'app/main.py'}),
             'hypotheses': [h]}
    bad = {**finish(final), 'hypotheses': [h]}
    result = investigate(active, task(active), Sequence([action('read_logs', {}), first, bad, finish(report())]))
    assert result['final']['status'] == 'INSUFFICIENT_EVIDENCE'
    assert result['summary']['invalid_decisions'] == 1

def test_generation_schema_does_not_weaken_local_limits():
    from copy import deepcopy
    from traceroot.agents.schemas import DECISION_SCHEMA, validate
    from traceroot.llms.provider import generation_schema
    original = deepcopy(DECISION_SCHEMA)
    generated = generation_schema(original)
    assert original == DECISION_SCHEMA
    assert 'maxLength' not in generated['properties']['hypothesis_summary']
    assert generated['properties']['hypotheses']['items']['properties']['status']['enum'] == ['proposed', 'supported', 'rejected']
    value = {**finish(report()), 'reviewed_step': 0, 'hypotheses': [], 'hypothesis_summary': 'x' * 301}
    with pytest.raises(ValueError):
        validate(value, DECISION_SCHEMA)


@pytest.mark.parametrize('pointer', ['/data/lines/-1/text', '/data/lines/00/text'])
def test_evidence_requires_canonical_json_array_indices(pointer):
    from traceroot.agents.investigator import pointer_value
    with pytest.raises(ValueError):
        pointer_value(source_output().to_dict(), pointer)

def test_proposed_hypothesis_can_be_refined_without_losing_history(active, monkeypatch):
    import traceroot.agents.investigator as module
    monkeypatch.setitem(module.TOOLS, 'read_logs', lambda *a, **kw: logs_output())
    original = {'id': 'H1', 'claim': 'A dependency may reject the request.', 'status': 'proposed',
                'confidence': 'low', 'evidence': [], 'missing_evidence': ['Runtime error.']}
    refined = {**original, 'claim': 'The database rejects a connection on port 9001.',
               'status': 'supported', 'confidence': 'medium',
               'evidence': [evidence(1, '/data/entries/0/message', 'connection refused to port 9001')],
               'missing_evidence': []}
    first = {**action('read_logs', {}), 'hypotheses': [original]}
    second = {**finish(report()), 'hypotheses': [refined]}
    result = investigate(active, task(active), Sequence([first, second]))
    assert result['summary']['hypotheses'] == [refined]
