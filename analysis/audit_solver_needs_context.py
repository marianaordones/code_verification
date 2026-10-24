"""Read saved ZIP artifacts only: no inference, solver calls or input changes."""
import argparse
from collections import Counter
import copy
import csv
import json
from pathlib import Path
import statistics
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / '.cluster/audit-python'))
from tokenizers import Tokenizer
from repair_study.relevance import rank, qids


def distribution(values):
    return {'min': min(values), 'median': statistics.median(values),
            'mean': statistics.mean(values), 'max': max(values)} if values else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'analysis/solver-needs-100-context-audit')
    args = parser.parse_args()
    tokenizer = Tokenizer.from_file(str(ROOT / '.cluster/audit-python/qwen-coder-tokenizer.json'))
    length = lambda text: len(tokenizer.encode(text, add_special_tokens=False).ids)
    details, prompt_rows, query_rows = [], [], []
    omitted_categories, sent_categories, available_categories = Counter(), Counter(), Counter()
    with zipfile.ZipFile(args.archive) as archive:
        names = set(archive.namelist())
        read = lambda name: json.loads(archive.read(name))
        manifest_path = next(n for n in names if n.endswith('/manifest.json'))
        base = manifest_path[:-len('manifest.json')]
        manifest = read(manifest_path)
        config = manifest['config']
        labels = {c['id']: c['paper_label'] for c in manifest['cases']}
        requests = sorted(n for n in names if n.endswith('/request.json'))
        for count, name in enumerate(requests):
            folder = name[:-len('request.json')]
            arm, task, attempt = folder[len(base):].strip('/').split('/')
            req, response = read(name), read(folder + 'response.json')
            measured = length(response['rendered_prompt'])
            prompt_rows.append({'arm': arm, 'id': task, 'attempt': attempt,
                'input_tokens': response['input_tokens'], 'tokenizer_tokens': measured,
                'headroom_after_output_reserve': config['max_model_len'] - config['max_tokens'] - response['input_tokens'],
                'truncated': response['truncated'], 'exposed': req['internals_exposed']})
            if arm != 'with_internals':
                continue
            exposure = read(folder + 'exposure.json')
            payload, context = exposure['payload'], exposure['context']
            index = int(attempt.split('_')[1])
            origin = base + f'inputs/{task}/' if index == 1 else base + f'{arm}/{task}/attempt_{index - 1:02}/'
            capture = read(origin + 'solver/report.json')
            failing = [q for q in capture['queries'] if q['result'] in ('sat', 'unknown')]
            sent = {}
            for q in (payload or {}).get('queries', []):
                for group in q['quantifiers']:
                    sent[(q['id'], group['quantifier_smt'])] = group
            available, raw_groups, mismatches, replay_failures, oversized = {}, 0, 0, 0, 0
            for query in failing[:config['max_queries']]:
                path = origin + 'internals/' + query['id'] + '/'
                if path + 'report.json' not in names:
                    replay_failures += 1
                    continue
                report = read(path + 'report.json')
                oversized += report.get('oversized_events', 0)
                if report.get('status') != 'completed':
                    replay_failures += 1
                    continue
                if report.get('result') != query['result']:
                    mismatches += 1
                    continue
                events = []
                if path + 'instantiations.jsonl' in names:
                    events = [json.loads(line) for line in archive.read(path + 'instantiations.jsonl').decode().splitlines() if line]
                local_groups = {e['quantifier_smt'] for e in events}
                saved_qids = {qid for formula in local_groups for qid in qids(formula)}
                observed_qids = set(report.get('per_qid_observed', {}))
                query_rows.append({'id': task, 'attempt': attempt, 'query': query['id'],
                    'saved_groups': len(local_groups), 'observed_events': report.get('instantiations_observed', 0),
                    'saved_events': len(events), 'observed_qids': len(observed_qids),
                    'observed_source_qids_not_saved': sorted(q for q in observed_qids - saved_qids if 'candidate' in q),
                    'oversized_events': report.get('oversized_events', 0), 'callback_errors': report.get('callback_errors', 0)})
                for event in events:
                    key = query['id'], event['quantifier_smt']
                    if key not in available:
                        score, category = rank(event['quantifier_smt'], context)
                        available[key] = {'category': category, 'events': []}
                    if event not in available[key]['events']:
                        available[key]['events'].append(event)
            local_omitted = Counter()
            reasons = Counter()
            sent_counts = Counter(group['selection_category'] for group in sent.values())
            available_counts = Counter(group['category'] for group in available.values())
            source_budget_examples = []
            payload_tokens = length(json.dumps(payload, ensure_ascii=False, indent=2)) if payload else 0
            for key, group in available.items():
                if key in sent:
                    continue
                category = group['category']
                local_omitted[category] += 1
                if category in ('representation', 'other_background') and sent_counts[category] >= 2:
                    reasons['background_quota_applies'] += 1
                elif len(sent) >= config['max_quantifiers']:
                    reasons['group_cap_applies'] += 1
                elif payload:
                    trial = copy.deepcopy(payload)
                    query = next(q for q in trial['queries'] if q['id'] == key[0])
                    event = group['events'][0]
                    query['quantifiers'].append({'selection_category': category, 'quantifier_smt': key[1],
                        'instances': [{k: event[k] for k in ('binding_terms_callback_order', 'clause_literals_smt')}]})
                    trial_text = json.dumps(trial, ensure_ascii=False, indent=2)
                    if length(trial_text) > config['internals_token_budget']:
                        reasons['adding_one_exceeds_internal_budget'] += 1
                        if category.startswith('candidate'):
                            source_budget_examples.append({'query': key[0], 'qids': qids(key[1])})
                    else:
                        original_text = json.dumps(payload, ensure_ascii=False, indent=2)
                        trial_prompt = response['rendered_prompt'].replace('<solver_internals>\n' + original_text + '\n</solver_internals>',
                            '<solver_internals>\n' + trial_text + '\n</solver_internals>')
                        if length(trial_prompt) + config['max_tokens'] > config['max_model_len']:
                            reasons['adding_one_exceeds_total_context'] += 1
                        else:
                            reasons['fits_at_end_but_not_selected'] += 1
                else:
                    reasons['no_payload'] += 1
            omitted_categories.update(local_omitted)
            sent_categories.update(sent_counts)
            available_categories.update(available_counts)
            details.append({'id': task, 'label': labels[task], 'attempt': attempt,
                'input_tokens': response['input_tokens'], 'internals_tokens': payload_tokens,
                'exposed': req['internals_exposed'], 'failed_queries': len(failing),
                'queries_exposed': len((payload or {}).get('queries', [])),
                'queries_not_replayed_due_to_cap': max(0, len(failing) - config['max_queries']),
                'replay_mismatches': mismatches, 'replay_failures': replay_failures,
                'available_groups': len(available), 'sent_groups': len(sent),
                'available_instances': sum(len(g['events']) for g in available.values()),
                'sent_instances': sum(len(g['instances']) for g in sent.values()),
                'available_categories': dict(available_counts), 'sent_categories': dict(sent_counts),
                'omitted_categories': dict(local_omitted), 'omission_tests_on_final_payload': dict(reasons),
                'source_budget_examples': source_budget_examples, 'oversized_events': oversized})
            if len(details) % 50 == 0:
                print('Audited with-internals prompts:', len(details), flush=True)
        summary = {'archive': args.archive.name, 'tasks': len(manifest['cases']), 'config': config,
            'prompt_counts': dict(Counter(p['arm'] for p in prompt_rows)),
            'input_tokens': {arm: distribution([p['input_tokens'] for p in prompt_rows if p['arm'] == arm])
                             for arm in ('with_internals', 'without_internals')},
            'tokenizer_count_mismatches': sum(p['input_tokens'] != p['tokenizer_tokens'] for p in prompt_rows),
            'minimum_headroom_with_output_reserved': min(p['headroom_after_output_reserve'] for p in prompt_rows),
            'truncated_responses': sum(p['truncated'] for p in prompt_rows),
            'exposed_prompts': sum(d['exposed'] for d in details),
            'internals_tokens_exposed': distribution([d['internals_tokens'] for d in details if d['exposed']]),
            'sent_groups_exposed': distribution([d['sent_groups'] for d in details if d['exposed']]),
            'prompts_at_20_group_cap': sum(d['sent_groups'] == config['max_quantifiers'] for d in details),
            'prompts_with_any_groups_omitted': sum(bool(d['omitted_categories']) for d in details),
            'prompts_with_candidate_groups_omitted': sum(any(c.startswith('candidate') for c in d['omitted_categories']) for d in details),
            'available_categories': dict(available_categories), 'sent_categories': dict(sent_categories),
            'omitted_categories': dict(omitted_categories),
            'omission_tests_on_final_payload': dict(sum((Counter(d['omission_tests_on_final_payload']) for d in details), Counter())),
            'prompts_with_source_budget_examples': sum(bool(d['source_budget_examples']) for d in details),
            'failed_queries_not_replayed_due_to_cap': sum(d['queries_not_replayed_due_to_cap'] for d in details),
            'prompts_over_three_failed_queries': sum(d['failed_queries'] > 3 for d in details),
            'diagnostic_query_reports': len(query_rows),
            'queries_with_observed_source_qids_not_saved': sum(bool(q['observed_source_qids_not_saved']) for q in query_rows),
            'queries_at_128_saved_groups': sum(q['saved_groups'] >= 128 for q in query_rows),
            'callback_errors': sum(q['callback_errors'] for q in query_rows),
            'replay_failures': sum(d['replay_failures'] for d in details),
            'replay_mismatches': sum(d['replay_mismatches'] for d in details),
            'scope': 'Actually sent prompts only; availability means saved events of outcome-concordant replays; omission causes are marginal tests on final payload, not reconstructed chronological decisions.'}
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in [('summary', summary), ('feedbacks', details), ('queries', query_rows), ('prompts', prompt_rows)]:
        (args.output / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
