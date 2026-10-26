"""Read-only inventory of requested Claude experiment outcomes (no model imports)."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def attempts(folder):
    rows = []
    for p in sorted(folder.glob('attempt_*')):
        response = (p / 'response.json').exists()
        if not response:
            raw = p / 'claude-stdout.jsonl'
            if raw.exists():
                for line in raw.read_text(encoding='utf-8').splitlines():
                    try:
                        response |= json.loads(line).get('type') == 'assistant'
                    except json.JSONDecodeError:
                        pass
        if response:
            rows.append({'attempt': int(p.name.removeprefix('attempt_')), 'result': read(p / 'result.json')})
    return rows


def branch(root, arm, task_id):
    folder = root / arm / task_id
    summary = read(folder / 'task.json')
    actual = attempts(folder)
    if summary:
        if summary.get('initially_verified'):
            return {'code': 'IV', 'tested': False, 'attempts': actual}
        if summary.get('success'):
            winners = [a['attempt'] for a in summary.get('attempts', []) if a.get('success')]
            return {'code': 'S' + str(min(winners)) if winners else 'S', 'tested': bool(actual), 'attempts': actual}
        return {'code': 'F', 'tested': bool(actual), 'attempts': actual}
    return {'code': 'P' if actual else '—', 'tested': bool(actual), 'attempts': actual}


def collect(results, groups):
    requested = [id for values in groups.values() for id in values]
    records = {id: [] for id in requested}
    studies = []
    for path in sorted(results.glob('*/manifest.json')):
        manifest = read(path)
        cfg = manifest['config']
        if not cfg.get('model', '').startswith('claude-'):
            continue
        root = path.parent
        selected = {c['id']: c for c in manifest.get('cases', manifest.get('selection', []))}
        is_shared = (root / 'shared').exists()
        studies.append({'study': root.name, 'model': cfg['model'], 'effort': cfg.get('effort'),
                        'shared_first': is_shared})
        for id in requested:
            if id not in selected:
                continue
            row = {'study': root.name, 'model': cfg['model'], 'effort': cfg.get('effort'),
                   'shared_first': is_shared, 'paper_label': selected[id].get('paper_label')}
            if is_shared:
                shared = root / 'shared' / id
                summary = read(shared / 'task.json')
                actual = attempts(shared)
                row['shared_attempts'] = actual
                row['first_failed'] = bool(summary and not summary.get('success') and not summary.get('initially_verified'))
                if summary and summary.get('success'):
                    row['with'], row['without'] = 'C1', 'C1'
                elif summary and summary.get('initially_verified'):
                    row['with'], row['without'] = 'IV', 'IV'
                elif not summary:
                    row['with'] = row['without'] = 'P1' if actual else '—'
                else:
                    row['with'] = branch(root, 'with_internals', id)['code']
                    row['without'] = branch(root, 'without_internals', id)['code']
                row['tested'] = bool(actual)
                row['details'] = {a: branch(root, a, id) for a in ('with_internals', 'without_internals')}
            else:
                a, b = branch(root, 'with_internals', id), branch(root, 'without_internals', id)
                row['with'], row['without'] = a['code'], b['code']
                row['tested'] = a['tested'] or b['tested']
                row['details'] = {'with_internals': a, 'without_internals': b}
            records[id].append(row)
    return {'generated_utc': datetime.now(timezone.utc).isoformat(), 'groups': groups,
            'studies': studies, 'records': records}


def markdown(report):
    lines = ['# IDs solicitados: resultados locais com Claude', '',
        'S1/S2/S3 = sucesso nessa proposta; F = falha final; C1 = sucesso na primeira proposta comum, sem testar reparos;',
        'P/P1 = resposta recebida, avaliação ainda incompleta; — = sem resposta do modelo registrada; IV = já verificava sem modelo.', '',
        'Pares nas tabelas: **com internals / sem internals**. Dados de preparação sem geração não contam como teste.', '']
    labels = {'claude-local-expanded60-low-v2': 'Opus 5.5 Low / 60',
              'claude-local-pilot6-format-v2': 'Opus 5.5 Medium / 6',
              'claude-local-smoke': 'Opus 5.5 Medium / smoke antigo',
              'missing-opus48-low-shared20-50x3-v1': 'Opus 4.8 Low / primeira comum',
              'verusbench-claude5-low-v2': 'Opus 5.5 Low / 5',
              'verusbench-sonnet5-low-v1': 'Sonnet 5.5 Low / 5',
              'verusbench-sonnet20-low-v2': 'Sonnet 5.5 Low / 20',
              'verusbench-shared20-sonnet-low-v1': 'Sonnet 5.5 Low / primeira comum'}
    for group, ids in report['groups'].items():
        tested = [id for id in ids if any(r['tested'] for r in report['records'][id])]
        lines += ['## ' + group, '', f'Testados: {len(tested)}/{len(ids)}.', '',
                  '| Problema | Configuração | Com / sem |', '|---|---|---|']
        for id in tested:
            for row in report['records'][id]:
                if row['tested']:
                    label = labels.get(row['study'], row['study'])
                    lines.append(f"| {id} | {label} | {row['with']} / {row['without']} |")
        untested = [id for id in ids if id not in tested]
        lines += ['', '**Sem resposta registrada em nenhuma configuração:** ' + (', '.join(untested) or 'nenhum') + '.', '']
        selected_only = [id for id in untested if report['records'][id]]
        if selected_only:
            lines += ['Desses, apenas selecionados/preparados: ' + ', '.join(selected_only) + '.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--queries', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = collect(args.results, read(args.queries))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    text = markdown(report)
    (args.output / 'report.md').write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
