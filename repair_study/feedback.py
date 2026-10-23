import copy
import json
import sys

from baseline.internals import STATISTICS
from baseline.prompts import ROOT
from baseline.storage import read_json, write_json
from baseline.verifier import execute
from diagnostics.z3_internals import api_env
from .regions import regions
from .relevance import rank, source_context

PROMPTS = ROOT / 'prompts/repair-study'


def messages(mode, original, candidate, verification, integrity, payload, progress=''):
    try:
        sites = regions(candidate)
    except ValueError:
        sites = []  # Full-file repair can still fix syntax; localized availability is explicit.
    system = (ROOT / 'prompts/v4/system.txt').read_text(encoding='utf-8')
    system += '\n\n' + (PROMPTS / 'solver-info.txt').read_text(encoding='utf-8')
    system += '\n\n' + (PROMPTS / f'{mode}.txt').read_text(encoding='utf-8')
    diagnostics = verification['stdout'] + '\n' + verification['stderr']
    data = ('Repair the saved failed candidate. Make a concrete proof change addressing a reported failure.\n'
            '<original_program>\n' + original + '\n</original_program>\n'
            '<current_candidate>\n' + candidate + '\n</current_candidate>\n'
            '<verus_diagnostics>\n' + diagnostics + '\n</verus_diagnostics>\n'
            '<integrity_diagnostics>\n' + json.dumps(integrity, ensure_ascii=False) + '\n</integrity_diagnostics>\n'
            '<progress>\n' + progress + '\n</progress>\n'
            '<solver_internals>\n' + json.dumps(payload, ensure_ascii=False, indent=2) + '\n</solver_internals>\n')
    if mode == 'local':
        data += '<editable_sites>\n' + json.dumps(sites, ensure_ascii=False, indent=2) + '\n</editable_sites>\n'
    data += '\nAddress the source failure first. Do not return an unchanged candidate. Follow your output contract.'
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': data}]


def build_payload(folder, original, candidate, verification, integrity, tokenizer, config, progress=''):
    report = read_json(folder / 'solver/report.json')
    context = source_context(candidate, verification)
    write_json(folder / 'source-context.json', context)
    selected = next((q for q in report['queries'] if q['result'] in ('sat', 'unknown')), None)
    replay_report = {'status': 'not_run'}
    replay_folder = folder / 'relevant-replay'
    if selected:
        call = execute([sys.executable, '-m', 'repair_study.worker',
                        '--query', str((folder / 'solver' / selected['file']).resolve()),
                        '--context', str((folder / 'source-context.json').resolve()),
                        '--output', str(replay_folder.resolve())], 20, env=api_env())
        write_json(replay_folder / 'process.json', call)
        if call.get('returncode') == 0 and not call.get('timed_out') and (replay_folder / 'report.json').exists():
            replay_report = read_json(replay_folder / 'report.json')
        else:
            replay_report = {'status': 'unavailable', 'error': 'worker did not finish'}
    concordant = selected is not None and replay_report.get('status') == 'completed' and replay_report.get('result') == selected['result']
    payload = {'schema': 'relevant-internals-v1', 'scope': 'diagnostic_replay_not_original_search',
               'availability': 'available' if concordant else 'unavailable',
               'original_result': selected['result'] if selected else None,
               'replay_result': replay_report.get('result'),
               'reason_unknown': replay_report.get('reason_unknown'),
               'unavailability_reason': None if concordant else 'no_query_replay_failure_or_result_mismatch',
               'source_context': context,
               'statistics': {k: replay_report.get('statistics', {}).get(k) if concordant else None for k in STATISTICS},
               'sampling': {'policy': 'relevance-ranked; diversity before repeated instances; heuristic qid categories',
                            'max_quantifiers': 24, 'max_instances_each': 4,
                            'observed_instances': replay_report.get('instantiations_observed'),
                            'saved_instances': replay_report.get('instantiations_saved'),
                            'callback_errors': replay_report.get('callback_errors'),
                            'selected_groups': 0, 'selected_instances': 0}, 'quantifiers': []}

    def fits(value):
        extra = '<solver_internals>\n' + json.dumps(value, ensure_ascii=False, indent=2) + '\n</solver_internals>'
        if len(tokenizer.encode(extra, add_special_tokens=False)) > config['internals_token_budget']:
            return False
        # Conservative shared fit policy: BOTH output contracts must fit.
        return all(len(tokenizer.apply_chat_template(
            messages(mode, original, candidate, verification, integrity, value, progress),
            tokenize=True, add_generation_prompt=True)) + config['max_tokens'] <= config['max_model_len']
                   for mode in ('full', 'local'))

    if not fits(payload):
        raise ValueError('Base prompt/source diagnostics do not fit the shared context; no truncation applied')
    events = []
    if concordant and (replay_folder / 'instantiations.jsonl').exists():
        events = [json.loads(line) for line in (replay_folder / 'instantiations.jsonl').read_text(encoding='utf-8').splitlines() if line]
    groups = {}
    for event in events:
        formula = event['quantifier_smt']
        if formula not in groups:
            score, category = rank(formula, context)
            groups[formula] = {'rank': score, 'category': category, 'events': []}
        if event not in groups[formula]['events']:
            groups[formula]['events'].append(event)
    ordered = sorted(groups.items(), key=lambda item: item[1]['rank'])
    chosen, categories = {}, {}
    for depth in range(4):
        for formula, group in ordered:
            if depth >= len(group['events']):
                continue
            existing = chosen.get(formula)
            category = group['category']
            if existing is None and (len(chosen) >= 24 or
                    category in ('representation', 'other_background') and categories.get(category, 0) >= 2):
                continue
            trial = copy.deepcopy(payload)
            current = next((q for q in trial['quantifiers'] if q['quantifier_smt'] == formula), None)
            if current is None:
                current = {'id': f'Q{len(chosen) + 1}', 'selection_category': category,
                           'quantifier_smt': formula, 'instances': []}
                trial['quantifiers'].append(current)
            event = group['events'][depth]
            current['instances'].append({k: event[k] for k in ('binding_terms_callback_order', 'clause_literals_smt')})
            trial['sampling']['selected_groups'] = len(trial['quantifiers'])
            trial['sampling']['selected_instances'] = sum(len(q['instances']) for q in trial['quantifiers'])
            if fits(trial):
                payload = trial
                if existing is None:
                    chosen[formula] = True
                    categories[category] = categories.get(category, 0) + 1
    write_json(folder / 'payload.json', payload)
    return payload
