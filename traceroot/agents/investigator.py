from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import signal
from time import monotonic
from uuid import uuid4

from ..contracts import ToolResult, ToolError, utc_now
from ..llms.provider import ModelFailure
from ..tools import TOOLS
from .prompt import SYSTEM_PROMPT
from .schemas import CATALOG, DECISION_SCHEMA, FINAL_SCHEMA, TASK_SCHEMA, TOOL_INPUTS, output_schema, validate

class DeadlineExpired(BaseException):
    pass

@contextmanager
def deadline(seconds: float):
    if seconds <= 0:
        raise DeadlineExpired()
    def expire(signum, frame):
        raise DeadlineExpired()
    previous = signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)

@dataclass(frozen=True)
class Budget:
    max_tool_calls: int = 15
    max_seconds: int = 300
    model_timeout: int = 60

    def __post_init__(self):
        if type(self.max_tool_calls) is not int or not 1 <= self.max_tool_calls <= 15:
            raise ValueError("Tool-call budget must be between 1 and 15.")
        if type(self.max_seconds) is not int or not 1 <= self.max_seconds <= 900:
            raise ValueError("Time budget must be between 1 and 900 seconds.")
        if type(self.model_timeout) is not int or not 1 <= self.model_timeout <= 120:
            raise ValueError("Model timeout must be between 1 and 120 seconds.")

ALLOWED_CONSTRAINTS = {
    "read-only investigation", "benchmark folder forbidden", "no code changes", "no database changes",
    "benchmark ground truth inaccessible", "no modifications",
}

def validate_task(task, context):
    validate(task, TASK_SCHEMA)
    context.repository.validate(task["repository"])
    if not task["constraints"] or any(c not in ALLOWED_CONSTRAINTS for c in task["constraints"]):
        raise ValueError("Unsupported constraints; mandatory restrictions cannot be relaxed.")
    if not context.config.get("active"):
        raise ValueError("Prepare an active disposable environment first.")

def reproduction_status(steps):
    reproductions = [s for s in steps if s["tool"] == "run_reproduction"]
    for step in steps:
        data = step["result"].get("data") or {}
        if step["result"]["status"] == "ok" and (
            data.get("reproduced") is True or
            any(o["expected"] != o["observed"] for o in data.get("http_observations", []))
        ):
            return "CONFIRMED"
    if any((s["result"].get("data") or {}).get("reproduced") is False for s in reproductions):
        return "NOT_REPRODUCED"
    return "UNAVAILABLE" if reproductions else "NOT_ATTEMPTED"

def pointer_value(document, pointer):
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError("Evidence requires a JSON pointer.")
    value = document
    try:
        for key in pointer[1:].split("/"):
            key = key.replace("~1", "/").replace("~0", "~")
            if isinstance(value, list):
                if not key.isascii() or not key.isdecimal() or (len(key) > 1 and key.startswith('0')):
                    raise ValueError('Invalid array index.')
                value = value[int(key)]
            else:
                value = value[key]
    except (ValueError, KeyError, TypeError, IndexError):
        raise ValueError("Evidence pointer does not identify an observation.") from None
    return value

def validate_final(report, steps):
    validate(report, FINAL_SCHEMA)
    if report["reproduction_status"] != reproduction_status(steps):
        raise ValueError("Reproduction status must agree with actual observations.")
    by_step = {step["step"]: step for step in steps}
    groups = set()
    families = {"run_reproduction": "execution", "run_tests": "execution",
                "search_code": "source", "read_file": "source",
                "read_logs": "runtime", "inspect_database": "database"}
    for item in report["evidence"]:
        step = by_step.get(item["step"])
        if not step or step["result"]["status"] != "ok":
            raise ValueError("Evidence must reference a successful tool observation.")
        if not item["pointer"].startswith("/data/"):
            raise ValueError("Evidence must cite tool data, not metadata.")
        value = pointer_value(step["result"], item["pointer"])
        rendered = value if isinstance(value, str) else json.dumps(value, sort_keys=True, ensure_ascii=False)
        if item["quote"] not in rendered:
            raise ValueError("Evidence excerpt does not match its cited observation.")
        groups.add(families[step["tool"]])
    for hypothesis in report["rejected_hypotheses"]:
        if not hypothesis["evidence_steps"] or any(
            i not in by_step or by_step[i]["result"]["status"] != "ok" for i in hypothesis["evidence_steps"]
        ):
            raise ValueError("Rejected hypotheses need observed evidence.")
    if report["status"] == "ROOT_CAUSE_IDENTIFIED":
        if not report["root_cause"] or len(groups) < 2 or groups <= {"source"}:
            raise ValueError("Root cause requires independent evidence families, not suspicious code alone.")
        if report["reproduction_status"] != "CONFIRMED" and not report["limitations"]:
            raise ValueError("Unconfirmed reproduction must be acknowledged as a limitation.")
    elif report["root_cause"] is not None:
        raise ValueError("Unestablished root causes must remain null.")

def fallback(task, steps, status, limitation):
    return {
        "status": status, "symptom": task["bug_report"], "reproduction_status": reproduction_status(steps),
        "root_cause": None, "root_cause_category": None, "affected_subsystem": None,
        "evidence": [], "rejected_hypotheses": [], "confidence": "low",
        "recommended_next_action": "Review the recorded observations and resolve the stated limitation before continuing.",
        "limitations": [limitation],
    }

def observation_view(result, max_chars=24000):
    # No silent context loss: preserve structure and advertise any field truncation.
    changes = []
    def shrink(value, path=""):
        if isinstance(value, str) and len(value) > 4500:
            changes.append(path)
            return value[:4500] + " [truncated for model]"
        if isinstance(value, dict):
            return {k: shrink(v, path + "/" + k) for k, v in value.items()}
        if isinstance(value, list):
            if len(value) > 30:
                changes.append(path)
            return [shrink(v, path + "/" + str(i)) for i, v in enumerate(value[:30])]
        return value
    view = shrink(result)
    if len(json.dumps(view)) > max_chars:
        return {"status": result["status"], "data": None,
                "error": {"code": "observation_too_large", "message": "Request a narrower result to inspect evidence."},
                "metadata": result["metadata"], "view_truncated": True}
    if changes:
        view["view_truncated"] = True
        view["truncated_paths"] = changes
    return view

def validate_hypotheses(hypotheses, previous, steps):
    ids = [h['id'] for h in hypotheses]
    if len(set(ids)) != len(ids):
        raise ValueError('Hypothesis IDs must be unique.')
    by_id = {h['id']: h for h in hypotheses}
    for old in previous:
        current = by_id.get(old['id'])
        if current is None:
            raise ValueError('Keep existing hypotheses; reject them instead of deleting them.')
        # Proposed claims may become more precise. Supported or rejected claims are history.
        if old['status'] != 'proposed' and current['claim'] != old['claim']:
            raise ValueError('Supported or rejected hypothesis claims are immutable.')
    if any(s['result']['status'] == 'ok' and s['result'].get('data') for s in steps) and not hypotheses:
        raise ValueError('Review the observations and maintain at least one hypothesis.')
    for hypothesis in hypotheses:
        if hypothesis['status'] != 'proposed' and not hypothesis['evidence']:
            raise ValueError('Supporting or rejecting a hypothesis requires cited evidence.')
        check = fallback({'bug_report': ''}, steps, 'INSUFFICIENT_EVIDENCE', '')
        check['evidence'] = hypothesis['evidence']
        validate_final(check, steps)


def investigate(context, task, provider, budget=Budget(), progress=None, *, resume_run_id=None):
    from .state import session_lock
    with session_lock(context):
        return _investigate(context, task, provider, budget, progress, resume_run_id)


def _investigate(context, task, provider, budget, progress, resume_run_id):
    from .state import atomic_json, load_state, run_directory, STATE_SCHEMA
    from time import sleep
    if set(TOOLS) != set(TOOL_INPUTS):
        raise ValueError('Only the six approved tools may be registered.')
    fingerprint = hashlib.sha256(json.dumps(
        {'prompt': SYSTEM_PROMPT, 'catalog': CATALOG, 'decision': DECISION_SCHEMA}, sort_keys=True).encode()).hexdigest()
    model_config = asdict(provider.config)
    if resume_run_id:
        state = load_state(context, resume_run_id)
        initial = state['initial']
        if task is not None and task != initial['task']:
            raise ValueError('Resume cannot change the original task.')
        task = initial['task']
        if (initial['snapshot_id'] != context.repository.snapshot_id or
                initial['prompt_contract_sha256'] != fingerprint or initial['model'] != model_config):
            raise ValueError('Snapshot, model, or contract differs from this checkpoint.')
        budget = Budget(**initial['budget'])
    else:
        validate_task(task, context)
        initial = {'task': task, 'model': model_config, 'budget': asdict(budget),
                   'prompt_contract_sha256': fingerprint, 'snapshot_id': context.repository.snapshot_id}
        state = {
            'version': 1, 'run_id': uuid4().hex, 'session_id': context.config['id'], 'initial': initial,
            'phase': 'running', 'steps': [], 'hypotheses': [], 'reviewed_step': 0,
            'pending_action': None, 'pending_model': False, 'transcript': [], 'events': [], 'provider_failures': [], 'tool_failures': [],
            'turns': 0, 'decisions': 0, 'invalid': 0, 'consecutive_invalid': 0, 'resume_count': 0,
            'elapsed_seconds': 0.0, 'usage': {'input_tokens': 0, 'output_tokens': 0, 'thinking_tokens': 0},
            'final': None, 'stopping_reason': None, 'updated_at': utc_now(),
        }
    directory = run_directory(context, state['run_id'])
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    start = monotonic()
    previous_elapsed = state['elapsed_seconds']
    end = start + max(0, budget.max_seconds - previous_elapsed)
    steps = state['steps']

    def checkpoint():
        state['elapsed_seconds'] = previous_elapsed + monotonic() - start
        state['updated_at'] = utc_now()
        validate(state, STATE_SCHEMA)
        atomic_json(directory / 'state.json', state)

    def emit(event):
        event = {'sequence': len(state['events']) + 1, 'at': utc_now(), **event}
        state['events'].append(event)
        checkpoint()
        # state.json is authoritative; JSONL is a derived human-readable view.
        with (directory / 'trajectory.jsonl').open('w', encoding='utf-8') as stream:
            for recorded in state['events']:
                stream.write(json.dumps(recorded, ensure_ascii=False) + '\n')
        if progress:
            progress({k: event[k] for k in ('event', 'run_id', 'step', 'tool', 'status', 'code') if k in event})

    def result():
        final = state['final']
        summary = {
            'run_id': state['run_id'], 'model': provider.config.model_name,
            'status': final['status'], 'stopping_reason': state['stopping_reason'],
            'tool_calls': len(steps), 'model_turns': state['turns'],
            'tools_used': [s['tool'] for s in steps],
            'incorrect_calls': sum(s['result']['status'] != 'ok' for s in steps),
            'invalid_decisions': state['invalid'], 'duration_ms': round(state['elapsed_seconds'] * 1000, 2),
            'usage': state['usage'], 'budget': asdict(budget), 'prompt_contract_sha256': fingerprint,
            'snapshot_id': context.repository.snapshot_id, 'artifacts': str(directory),
            'phase': state['phase'], 'resumable': state['phase'] == 'paused',
            'resume_count': state['resume_count'], 'provider_failures': len(state['provider_failures']),
            'tool_failures': len(state['tool_failures']), 'hypotheses': state['hypotheses'],
        }
        atomic_json(directory / 'final.json', final)
        atomic_json(directory / 'summary.json', summary)
        return {'final': final, 'summary': summary}

    if resume_run_id:
        for i, step in enumerate(steps, 1):
            if step['step'] != i or step['tool'] not in TOOLS:
                raise ValueError('Invalid checkpoint step sequence.')
            validate(step['arguments'], TOOL_INPUTS[step['tool']])
            validate(step['result'], output_schema(step['tool']))
        validate_hypotheses(state['hypotheses'], [], steps[:state['reviewed_step']])
        if state['phase'] in {'finished', 'interrupted_tool'}:
            return result()
        validate_task(task, context)
        for relative in context.repository.manifest:
            context.repository.read(relative)
        state['resume_count'] += 1
        if state['pending_action']:
            state['phase'] = 'interrupted_tool'
            state['stopping_reason'] = 'tool_outcome_unknown'
            state['final'] = fallback(task, steps, 'TOOL_FAILURE',
                'Process stopped during a tool call. Its outcome is unknown; automatic replay is forbidden.')
            state['tool_failures'].append({'code': 'tool_outcome_unknown', 'action': state['pending_action']})
            emit({'event': 'tool_interrupted', 'status': 'TOOL_FAILURE'})
            return result()
        if state['pending_model']:
            failure = {'code': 'model_interrupted', 'message': 'Process stopped during a model request.',
                       'retryable': True, 'after_step': len(steps)}
            state['provider_failures'].append(failure)
            state['pending_model'] = False
            emit({'event': 'provider_failure', 'status': 'TOOL_FAILURE', **failure})
        state['phase'], state['final'], state['stopping_reason'] = 'running', None, None
        state['consecutive_invalid'] = 0
        emit({'event': 'resumed', 'step': len(steps), 'status': 'running'})
    else:
        atomic_json(directory / 'initial.json', initial)
        emit({'event': 'investigation_started', 'run_id': state['run_id'], 'status': 'running'})

    stopping_reason = None
    while state['decisions'] < budget.max_tool_calls + 3 and state['turns'] < 60:
        remaining = end - monotonic()
        if remaining <= 0:
            stopping_reason = 'time_budget'
            break
        request = [{'role': 'user', 'text': json.dumps({'task': task, 'tools': CATALOG})},
                   *state['transcript'], {'role': 'user', 'text': json.dumps({
            'state': {'hypotheses': state['hypotheses'], 'latest_tool_step': len(steps),
                      'reproduction_status': reproduction_status(steps)},
            'budget': {'tool_calls_remaining': budget.max_tool_calls - len(steps),
                       'seconds_remaining': round(remaining, 1)},
            'instruction': 'Review the latest observation, update the hypothesis registry, then choose one action or finish.',
        })}]
        if sum(len(m['text']) for m in request) > 240000:
            stopping_reason = 'context_budget'
            break
        reply = None
        for attempt in range(provider.config.max_transient_retries + 1):
            remaining = end - monotonic()
            if remaining <= 0 or state['turns'] >= 60:
                stopping_reason = 'time_budget' if remaining <= 0 else 'model_turn_budget'
                break
            state['turns'] += 1
            state['pending_model'] = True
            # Reserve the full attempt before dispatch so abrupt death cannot reset budgets.
            checkpoint()
            reserved = state['elapsed_seconds']
            state['elapsed_seconds'] += min(budget.model_timeout, remaining)
            atomic_json(directory / 'state.json', state)
            state['elapsed_seconds'] = reserved
            try:
                with deadline(min(budget.model_timeout, remaining)):
                    reply = provider.generate(SYSTEM_PROMPT, request, DECISION_SCHEMA,
                                              min(budget.model_timeout, remaining))
                state['pending_model'] = False
                for key in state['usage']:
                    state['usage'][key] += reply.usage.get(key, 0)
                break
            except DeadlineExpired:
                failure = ModelFailure('model_timeout', 'Model request exceeded its deadline.', retryable=True)
            except ModelFailure as exc:
                failure = exc
            state['pending_model'] = False
            event = {'code': failure.code, 'message': failure.message,
                     'retryable': failure.retryable, 'attempt': attempt + 1, 'after_step': len(steps)}
            state['provider_failures'].append(event)
            emit({'event': 'provider_failure', 'status': 'TOOL_FAILURE', **event})
            stopping_reason = 'time_budget' if monotonic() >= end else failure.code
            if not failure.retryable or attempt >= provider.config.max_transient_retries:
                break
            delay = min(0.5 * 2 ** attempt, 4.0)
            if end - monotonic() <= delay:
                stopping_reason = 'time_budget'
                break
            emit({'event': 'provider_retry', 'delay_seconds': delay, 'status': 'retrying'})
            sleep(delay)
        if reply is None:
            break
        stopping_reason = None
        state['decisions'] += 1
        try:
            decision = reply.decision
            validate(decision, DECISION_SCHEMA)
            if (decision['action'] is None) == (decision['final_report'] is None):
                raise ValueError('Choose exactly one action or final report.')
            if decision['reviewed_step'] != len(steps):
                raise ValueError('reviewed_step must equal the latest tool step.')
            validate_hypotheses(decision['hypotheses'], state['hypotheses'], steps)
            if decision['final_report'] is not None:
                final = decision['final_report']
                if final['status'] != 'ROOT_CAUSE_IDENTIFIED' and not final['limitations']:
                    raise ValueError('An incomplete investigation needs an explicit limitation.')
                validate_final(final, steps)
                if final['status'] == 'ROOT_CAUSE_IDENTIFIED':
                    matching = [h for h in decision['hypotheses'] if h['status'] == 'supported'
                                and h['claim'] == final['root_cause']]
                    if not matching or not any(all(e in h['evidence'] for e in final['evidence']) for h in matching):
                        raise ValueError('Root cause must match a supported hypothesis and its concrete evidence links.')
                if final['status'] == 'REPRODUCTION_FAILED' and reproduction_status(steps) not in {'UNAVAILABLE', 'NOT_REPRODUCED'}:
                    raise ValueError('Reproduction failure must be observed.')
                if final['status'] == 'MAX_STEPS_REACHED' and len(steps) < budget.max_tool_calls:
                    raise ValueError('The tool-call budget has not been reached.')
                if final['status'] == 'TOOL_FAILURE' and not state['tool_failures']:
                    raise ValueError('A tool failure must be observed.')
            elif decision['action']['name'] == 'run_reproduction' and any(
                    s['tool'] == 'run_reproduction' and s['result']['status'] == 'ok' for s in steps):
                raise ValueError('Use the checkpointed reproduction; use targeted tests for further evidence.')
        except ValueError as exc:
            state['invalid'] += 1
            state['consecutive_invalid'] += 1
            state['transcript'].append({'role': 'user', 'text': json.dumps({
                'decision_error': str(exc)[:300], 'instruction': 'Correct the contract or gather missing evidence.'})})
            emit({'event': 'decision_rejected', 'status': 'rejected', 'message': str(exc)[:300]})
            if state['consecutive_invalid'] >= 3:
                stopping_reason = 'invalid_decisions'
                break
            continue
        state['consecutive_invalid'] = 0
        state['hypotheses'] = decision['hypotheses']
        state['reviewed_step'] = decision['reviewed_step']
        # Store only public concise summaries; the registry is supplied separately next turn.
        state['transcript'].append({'role': 'model', 'text': json.dumps({
            'hypothesis_summary': decision['hypothesis_summary'], 'evidence_summary': decision['evidence_summary'],
            'action': decision['action'], 'final_report': decision['final_report']})})
        emit({'event': 'hypotheses_updated', 'step': len(steps), 'hypotheses': state['hypotheses'], 'status': 'reviewed'})
        if decision['final_report'] is not None:
            state['final'] = decision['final_report']
            stopping_reason = 'model_finished'
            break
        if len(steps) >= budget.max_tool_calls:
            stopping_reason = 'tool_call_budget'
            break
        action = decision['action']
        name, arguments = action['name'], action['arguments']
        step_number = len(steps) + 1
        state['pending_action'] = {'step': step_number, **action}
        emit({'event': 'tool_selected', 'step': step_number, 'tool': name, 'arguments': arguments,
              'hypothesis_summary': decision['hypothesis_summary'], 'evidence_summary': decision['evidence_summary'],
              'status': 'running'})
        # Unfinished tools conservatively consume all remaining active time on process death.
        reserved = state['elapsed_seconds']
        state['elapsed_seconds'] = float(budget.max_seconds)
        atomic_json(directory / 'state.json', state)
        state['elapsed_seconds'] = reserved
        try:
            context.operation_deadline = end
            with deadline(end - monotonic()):
                tool_result = TOOLS[name](context, **arguments).to_dict()
            validate(tool_result, output_schema(name))
        except DeadlineExpired:
            tool_result = ToolResult('timeout', error=ToolError('investigation_timeout', 'Investigation deadline reached.')).to_dict()
        except ValueError:
            tool_result = ToolResult('error', error=ToolError('output_contract_failed', 'Tool output violated its contract.')).to_dict()
        except Exception:
            tool_result = ToolResult('error', error=ToolError('tool_exception', 'Tool failed unexpectedly.')).to_dict()
        finally:
            context.operation_deadline = None
        step = {'step': step_number, 'tool': name, 'arguments': arguments, 'result': tool_result}
        steps.append(step)
        state['pending_action'] = None
        if tool_result['status'] != 'ok':
            state['tool_failures'].append({'step': step_number, 'tool': name, 'error': tool_result['error']})
        state['transcript'].append({'role': 'user', 'text': json.dumps({
            'tool_step': step_number, 'tool': name, 'result': observation_view(tool_result)})})
        emit({'event': 'tool_result', **step, 'status': tool_result['status']})
        if name == 'run_reproduction' and tool_result['status'] == 'unavailable':
            state['final'] = fallback(task, steps, 'REPRODUCTION_FAILED', 'Public reproduction is unavailable.')
            stopping_reason = 'reproduction_unavailable'
            break
    stopping_reason = stopping_reason or 'model_turn_budget'
    state['stopping_reason'] = stopping_reason
    if state['final'] is None:
        exhausted = stopping_reason in {'time_budget', 'tool_call_budget', 'model_turn_budget', 'context_budget'}
        state['final'] = fallback(task, steps, 'MAX_STEPS_REACHED' if exhausted else 'TOOL_FAILURE', stopping_reason)
        state['phase'] = 'finished' if exhausted or stopping_reason == 'invalid_decisions' else 'paused'
    else:
        state['phase'] = 'finished'
    validate(state['final'], FINAL_SCHEMA)
    emit({'event': 'final', 'status': state['final']['status'], 'stopping_reason': stopping_reason})
    return result()
