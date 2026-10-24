"""Analyze saved Solver Needs runs. Read-only; no model, solver or hash validation."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
ARMS = ('with_internals', 'without_internals')


def default_paths(root=ROOT):
    previous = root.parent / 'code_verification'
    return {'initial': [previous / 'results/solver-needs-qwen14b-100/seed-20261018',
                        previous / 'results/solver-needs-qwen14b-remaining362/seed-20261018'],
            'expanded': root / 'results/solver-needs-qwen14b-100-internals24k/seed-20261018'}


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def distribution(values):
    return {'n': len(values), 'min': min(values), 'median': statistics.median(values),
            'max': max(values)} if values else {'n': 0, 'min': None, 'median': None, 'max': None}


def tokenizer_for(config, explicit=None):
    relative = Path('.cluster/models') / config['model'].split('/')[-1] / config['model_revision'] / 'tokenizer.json'
    candidates = [ROOT / relative, ROOT.parent / 'code_verification' / relative]
    path = explicit or next((p for p in candidates if p.exists()), candidates[0])
    try:
        from tokenizers import Tokenizer
        tokenizer = Tokenizer.from_file(str(path))
        return lambda text: len(tokenizer.encode(text, add_special_tokens=False).ids), str(path)
    except Exception as error:
        return None, str(error)


def analyze_group(paths, tokenizer_path=None):
    cases, issues, configs, token_rows, error_rows = [], [], [], [], []
    seen = set()
    for root in paths:
        if not (root / 'manifest.json').exists():
            issues.append({'path': str(root), 'error': 'manifest missing; run not analyzed'})
            continue
        manifest = load(root / 'manifest.json')
        config = manifest['config']
        configs.append(config)
        encode, tokenizer_info = tokenizer_for(config, tokenizer_path)
        for case in manifest['cases']:
            key = case['id']
            if key in seen:
                raise ValueError('Duplicate task across merged runs: ' + key)
            seen.add(key)
            folder = root / 'inputs' / key
            initial = load(folder / 'verification.json') if (folder / 'verification.json').exists() else {}
            row = {'id': key, 'study': str(root), 'label': case.get('paper_label'),
                   'initially_verified': bool(initial.get('success')), 'arms': {}}
            for arm in ARMS:
                arm_folder = root / arm / key
                summary = load(arm_folder / 'task.json') if (arm_folder / 'task.json').exists() else None
                attempts = {int(a['attempt']): a for a in (summary or {}).get('attempts', [])}
                for attempt_folder in sorted(arm_folder.glob('attempt_*')):
                    result_path = attempt_folder / 'result.json'
                    if result_path.exists():
                        result = load(result_path)
                        index = int(result['attempt'])
                        if index in attempts and attempts[index]['success'] != result['success']:
                            issues.append({'id': key, 'arm': arm, 'error': 'task/result success mismatch'})
                        attempts[index] = result
                    response_path, request_path = attempt_folder / 'response.json', attempt_folder / 'request.json'
                    if not response_path.exists():
                        continue
                    response = load(response_path)
                    request = load(request_path) if request_path.exists() else {}
                    parameters = request.get('parameters', config)
                    maximum, reserve = parameters['max_model_len'], parameters['max_tokens']
                    input_tokens, output_tokens = response.get('input_tokens'), response.get('output_tokens')
                    token_row = {'study': str(root), 'id': key, 'arm': arm, 'attempt': attempt_folder.name,
                        'input_tokens': input_tokens, 'output_tokens': output_tokens,
                        'context_limit': maximum, 'output_reserve': reserve,
                        'headroom': maximum - reserve - input_tokens if input_tokens is not None else None,
                        'input_plus_reserve_exceeded': input_tokens + reserve > maximum if input_tokens is not None else None,
                        'actual_input_output_exceeded': input_tokens + output_tokens > maximum if input_tokens is not None and output_tokens is not None else None,
                        'truncated': response.get('truncated', response.get('finish_reason') == 'length'),
                        'internals_tokens': None, 'internals_budget': parameters.get('internals_token_budget'),
                        'internals_budget_exceeded': None, 'groups': None, 'max_instances_in_group': None,
                        'internals_exposed': request.get('internals_exposed'), 'tokenizer_count_matches': None}
                    exposure_path = attempt_folder / 'exposure.json'
                    if exposure_path.exists():
                        payload = load(exposure_path).get('payload')
                        groups = [g for q in (payload or {}).get('queries', []) for g in q.get('quantifiers', [])]
                        token_row['groups'] = len(groups)
                        token_row['max_instances_in_group'] = max((len(g['instances']) for g in groups), default=0)
                        if not payload:
                            token_row['internals_tokens'] = 0
                        elif encode:
                            token_row['internals_tokens'] = encode(json.dumps(payload, ensure_ascii=False, indent=2))
                        if token_row['internals_tokens'] is not None and token_row['internals_budget'] is not None:
                            token_row['internals_budget_exceeded'] = token_row['internals_tokens'] > token_row['internals_budget']
                    if encode and response.get('rendered_prompt') is not None and input_tokens is not None:
                        token_row['tokenizer_count_matches'] = encode(response['rendered_prompt']) == input_tokens
                    token_rows.append(token_row)
                if (arm_folder / 'error.json').exists():
                    error_rows.append({'study': str(root), 'id': key, 'arm': arm,
                        'stale_if_completed': summary is not None, 'details': load(arm_folder / 'error.json')})
                successes = [i for i, a in attempts.items() if a.get('success')]
                row['arms'][arm] = {'completed': summary is not None,
                    'first_success_attempt': min(successes) if successes else None,
                    'attempts_observed': sorted(attempts)}
            cases.append(row)
        issues.append({'path': str(root), 'tokenizer_available': encode is not None, 'tokenizer': tokenizer_info})
    eligible = [r for r in cases if not r['initially_verified']]
    paired = [r for r in eligible if all(r['arms'][arm]['completed'] for arm in ARMS)]
    max_attempts = max((c['max_attempts'] for c in configs), default=4)

    def curve(rows):
        result = []
        for k in range(1, max_attempts + 1):
            item = {'attempt_budget': k, 'denominator': len(rows)}
            for arm in ARMS:
                successes = [r['arms'][arm]['first_success_attempt'] for r in rows]
                solved = sum(i is not None and i <= k for i in successes)
                item[arm] = {'cumulative_solved': solved,
                    'new_solved': sum(i == k for i in successes),
                    'success_rate': solved / len(rows) if rows else None}
            item['difference'] = item[ARMS[0]]['cumulative_solved'] - item[ARMS[1]]['cumulative_solved']
            result.append(item)
        return result

    context_patterns = ('exceeds context', 'context length', 'maximum context', 'max_model_len',
                        'exceed context', 'exceed the context', 'exceeding', 'exceed the maximum',
                        'exceed the remaining', 'exceed the token', 'exceed token')
    context_errors = [e for e in error_rows if any(p in json.dumps(e['details']).lower() for p in context_patterns)]
    tokens = {'responses_audited': len(token_rows),
        'input_tokens_by_arm': {a: distribution([r['input_tokens'] for r in token_rows if r['arm'] == a and r['input_tokens'] is not None]) for a in ARMS},
        'headroom_after_reserving_output': distribution([r['headroom'] for r in token_rows if r['headroom'] is not None]),
        'input_plus_reserve_violations': sum(r['input_plus_reserve_exceeded'] is True for r in token_rows),
        'actual_input_output_violations': sum(r['actual_input_output_exceeded'] is True for r in token_rows),
        'truncated_outputs': sum(bool(r['truncated']) for r in token_rows),
        'internals_tokens_exposed': distribution([r['internals_tokens'] for r in token_rows if r['internals_exposed'] and r['internals_tokens'] is not None]),
        'exposed_payloads_without_token_measurement': sum(bool(r['internals_exposed']) and r['internals_tokens'] is None for r in token_rows),
        'internals_budget_violations': sum(r['internals_budget_exceeded'] is True for r in token_rows),
        'tokenizer_count_mismatches': sum(r['tokenizer_count_matches'] is False for r in token_rows),
        'context_related_error_records': context_errors,
        'scope': 'Saved responses and error.json only. Context rejection before a response is detected through saved errors when available. Output truncation is separate from context overflow. Internal payload token counts require an offline tokenizer.'}
    return {'selected': len(cases), 'repair_denominator': len(eligible),
        'initially_verified': len(cases) - len(eligible), 'paired_completed': len(paired),
        'complete': bool(cases) and len(configs) == len(paths) and len(paired) == len(eligible),
        'configs_identical_within_group': all(c == configs[0] for c in configs),
        'completed_by_arm': {a: sum(r['arms'][a]['completed'] for r in eligible) for a in ARMS},
        'missing_by_arm': {a: [r['id'] for r in eligible if not r['arms'][a]['completed']] for a in ARMS},
        'all_selected_curve': curve(eligible), 'paired_completed_curve': curve(paired),
        'categories': {label: curve([r for r in eligible if r['label'] == label]) for label in sorted({r['label'] for r in eligible if r['label']})},
        'token_audit': tokens, 'issues': issues, 'errors': error_rows, 'cases': cases, 'token_rows': token_rows}


def write_reports(groups, output):
    output.mkdir(parents=True, exist_ok=True)
    lines = ['# Solver Needs: sucessos por proposta e contexto', '',
             'Leitura de arquivos salvos; sem inferência, solver ou alteração dos resultados.',
             'Proposta 1 = primeira resposta do modelo; propostas 2–4 = reparos seguintes.',
             'Taxas sobre todos os casos selecionados elegíveis; pendentes não são sucessos conhecidos.', '']
    csv_rows = []
    for name, report in groups.items():
        (output / f'{name}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        lines += [f'## {name}', '', f"Selecionadas: {report['selected']}; denominador de reparos: {report['repair_denominator']}; pares concluídos: {report['paired_completed']}; completo: {report['complete']}.",
            f"Configurações iguais entre lotes agregados: {report['configs_identical_within_group']}.", '',
            '| Até a proposta | Com internals | Novos | Sem internals | Novos | Diferença |',
            '|---|---|---|---|---|---|']
        for scope in ('all_selected_curve', 'paired_completed_curve'):
            for row in report[scope]:
                for arm in ARMS:
                    csv_rows.append({'experiment': name, 'scope': scope, 'attempt_budget': row['attempt_budget'],
                        'denominator': row['denominator'], 'arm': arm, **row[arm]})
                if scope == 'all_selected_curve':
                    a, b = row[ARMS[0]], row[ARMS[1]]
                    fmt = lambda v: f"{v['cumulative_solved']} ({v['success_rate']:.1%})" if v['success_rate'] is not None else 'N/A'
                    lines.append(f"| {row['attempt_budget']} | {fmt(a)} | {a['new_solved']} | {fmt(b)} | {b['new_solved']} | {row['difference']:+} |")
        audit = report['token_audit']
        lines += ['', f"Respostas auditadas: {audit['responses_audited']}; violações entrada + reserva: {audit['input_plus_reserve_violations']}; violações entrada + saída real: {audit['actual_input_output_violations']}.",
            f"Menor folga após reserva: {audit['headroom_after_reserving_output']['min']}; saídas truncadas: {audit['truncated_outputs']}.",
            f"Bloco interno: {audit['internals_tokens_exposed']}; violações do orçamento interno: {audit['internals_budget_violations']}.",
            f"Payloads expostos sem medição interna: {audit['exposed_payloads_without_token_measurement']}; erros salvos relacionados a contexto: {len(audit['context_related_error_records'])}.",
            'Pendências, curva somente dos pares concluídos, categorias e detalhes constam no JSON.', '']
    with (output / 'success_by_attempt.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['experiment', 'scope', 'attempt_budget', 'denominator', 'arm', 'cumulative_solved', 'new_solved', 'success_rate'])
        writer.writeheader()
        writer.writerows(csv_rows)
    (output / 'report.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    defaults = default_paths()
    parser.add_argument('--initial', nargs='+', type=Path, default=defaults['initial'])
    parser.add_argument('--expanded', type=Path, default=defaults['expanded'])
    parser.add_argument('--tokenizer', type=Path, help='Optional offline tokenizer.json from the pinned Qwen revision')
    parser.add_argument('--output', type=Path, default=ROOT / 'analysis/solver-needs-attempts')
    args = parser.parse_args()
    paths = [p.resolve() for p in [*args.initial, args.expanded]]
    out = args.output.resolve()
    if any(out == p or out.is_relative_to(p) for p in paths):
        parser.error('Output must be outside saved study directories')
    groups = {'initial': analyze_group(args.initial, args.tokenizer),
              'internals24k': analyze_group([args.expanded], args.tokenizer)}
    write_reports(groups, args.output)
    print((args.output / 'report.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    main()
