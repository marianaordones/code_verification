import copy
import json
import sys

from baseline.internals import STATISTICS
from baseline.prompts import ROOT
from baseline.storage import digest, read_json, write_json, write_text
from baseline.verifier import execute
from diagnostics.z3_internals import api_env
from repair_study.relevance import rank, source_context
from .data import upstream

ARMS = ('with_internals', 'without_internals')


def messages(code, verification, action, context, payload, history, config=None, complement=None):
    _, laws = upstream()
    system = (config or {}).get('system_prompt_text')
    if system is None:
        system = (ROOT / 'prompts/solver-needs/system.txt').read_text(encoding='utf-8')
    if (config or {}).get('complement_token_budget'):
        system += '\n' + (ROOT / 'prompts/solver-needs/complement.txt').read_text(encoding='utf-8')
    # Same complete catalogue for every task and every arm; no successful probe IDs.
    catalogue = '\n'.join(f'LAW {name}\n{body.strip()}' for name, body in laws.LAWS.items())
    user = ('Repair the proof hint at REPAIR_SLOT_BEGIN/END.\n'
            '<current_program>\n' + code + '\n</current_program>\n'
            '<current_action>\n' + json.dumps(action, ensure_ascii=False) + '\n</current_action>\n'
            '<verus_diagnostics>\n' + verification['stdout'] + '\n' + verification['stderr'] + '\n</verus_diagnostics>\n'
            '<source_failure_context>\n' + json.dumps(context, ensure_ascii=False, indent=2) + '\n</source_failure_context>\n'
            '<attempt_history>\n' + json.dumps(history, ensure_ascii=False) + '\n</attempt_history>\n'
            '<checked_law_catalogue>\n' + catalogue + '\n</checked_law_catalogue>\n')
    if payload and payload.get('queries'):
        user += '<solver_internals>\n' + json.dumps(payload, ensure_ascii=False, indent=2) + '\n</solver_internals>\n'
    if complement:
        user += '<complementary_internals>\n' + json.dumps(complement, ensure_ascii=False, indent=2) + '\n</complementary_internals>\n'
    user += 'Return only the four-field JSON action. Supply a complete replacement for the current slot/settings.'
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]


def fits(code, verification, action, context, payload, history, tokenizer, config, complement=None):
    if payload:
        block = json.dumps(payload, ensure_ascii=False, indent=2)
        if len(tokenizer.encode(block, add_special_tokens=False)) > config['internals_token_budget']:
            return False
    if complement and len(tokenizer.encode(json.dumps(complement, ensure_ascii=False, indent=2),
            add_special_tokens=False)) > config['complement_token_budget']:
        return False
    prompt = messages(code, verification, action, context, payload, history, config=config, complement=complement)
    return len(tokenizer.apply_chat_template(prompt, tokenize=True, add_generation_prompt=True)) + config['max_tokens'] <= config['max_model_len']


def internals(folder, code, verification, action, history, tokenizer, config, replay=True, saved_context=None):
    destination = folder / 'feedback.json'
    if destination.exists():
        return read_json(destination)
    report = read_json(folder / 'solver/report.json')
    context = saved_context if saved_context is not None else source_context(code, verification)
    write_json(folder / 'source-context.json', context)
    failed = [q for q in report['queries'] if q['result'] in ('sat', 'unknown')]
    payload = {'scope': 'diagnostic_replays_not_original_search',
               'query_to_source_alignment': 'not established',
               'captured_failing_queries': len(failed), 'query_limit': config['max_queries'],
               'queries': []}
    events = []
    for query in failed[:config['max_queries']]:
        output = folder / 'internals' / query['id']
        if replay:
            command = [sys.executable, '-m', 'repair_study.worker', '--query',
                            str((folder / 'solver' / query['file']).resolve()), '--context',
                            str((folder / 'source-context.json').resolve()), '--output', str(output.resolve())]
            if config.get('replay_max_instances') is not None:
                command += ['--max-instances-per-group', str(config['replay_max_instances'])]
            if config.get('collect_inventory'):
                command += ['--collect-inventory']
            call = execute(command, 20, env=api_env())
            write_json(output / 'process.json', call)
        else:
            if not (output / 'process.json').exists():
                raise ValueError('Missing saved replay process record: ' + str(output))
            call = read_json(output / 'process.json')
        if call['returncode'] != 0 or call['timed_out'] or not (output / 'report.json').exists():
            continue
        replay_report = read_json(output / 'report.json')
        if replay_report.get('status') != 'completed' or replay_report.get('result') != query['result']:
            continue
        payload['queries'].append({'id': query['id'], 'query_sha256': digest((folder / 'solver' / query['file']).read_bytes()),
            'original_result': query['result'], 'replay_result': replay_report['result'],
            'reason_unknown': replay_report.get('reason_unknown'), 'diagnostic_timeout_ms': 5000,
            'statistics': {key: replay_report.get('statistics', {}).get(key) for key in STATISTICS},
            'observed_instances': replay_report.get('instantiations_observed'),
            'saved_instances': replay_report.get('instantiations_saved'),
            'callback_errors': replay_report.get('callback_errors'), 'quantifiers': []})
        if (output / 'instantiations.jsonl').exists():
            for line in (output / 'instantiations.jsonl').read_text(encoding='utf-8').splitlines():
                if line:
                    events.append((query['id'], json.loads(line)))
    if not fits(code, verification, action, context, payload, history, tokenizer, config):
        raise ValueError('Base prompt or replay statistics exceed context; no program/diagnostic truncation')
    grouped = {}
    for query_id, event in events:
        key = (query_id, event['quantifier_smt'])
        if key not in grouped:
            score, category = rank(event['quantifier_smt'], context)
            grouped[key] = {'rank': score, 'category': category, 'events': []}
        if event not in grouped[key]['events']:
            grouped[key]['events'].append(event)
    selected, background = set(), {}
    for depth in range(config['max_instances_each']):
        for (query_id, formula), group in sorted(grouped.items(), key=lambda item: item[1]['rank']):
            key = (query_id, formula)
            if depth >= len(group['events']):
                continue
            category = group['category']
            if key not in selected and (len(selected) >= config['max_quantifiers'] or
                    category in ('representation', 'other_background') and background.get(category, 0) >= 2):
                continue
            trial = copy.deepcopy(payload)
            query = next(q for q in trial['queries'] if q['id'] == query_id)
            item = next((q for q in query['quantifiers'] if q['quantifier_smt'] == formula), None)
            if item is None:
                item = {'selection_category': category, 'quantifier_smt': formula, 'instances': []}
                query['quantifiers'].append(item)
            item['instances'].append({k: group['events'][depth][k]
                                     for k in ('binding_terms_callback_order', 'clause_literals_smt')})
            if fits(code, verification, action, context, trial, history, tokenizer, config):
                payload = trial
                if key not in selected:
                    selected.add(key)
                    background[category] = background.get(category, 0) + 1
    value = {'context': context, 'internals': payload if payload['queries'] else None,
             'availability': 'available' if payload['queries'] else 'unavailable',
             'capture_errors': report['capture_errors'],
             'policy': 'first up to three SAT/UNKNOWN queries; only outcome-concordant replays; bounded relevance-ranked events'}
    if config.get('complement_token_budget'):
        from .complement import build
        value['complement'] = build(folder, context, value['internals'], tokenizer, config,
            lambda extra: fits(code, verification, action, context, value['internals'], history,
                               tokenizer, config, complement=extra))
        value['token_counts'] = {name: len(tokenizer.encode(json.dumps(value[name], ensure_ascii=False,
            indent=2), add_special_tokens=False)) if value.get(name) else 0 for name in ('internals', 'complement')}
    write_json(destination, value)
    return value


def control_feedback(code, verification):
    return {'context': source_context(code, verification), 'internals': None,
            'availability': 'withheld_by_design'}
