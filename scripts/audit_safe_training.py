"""Read-only SAFE training inventory. Missing/running batches remain pending."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def category(row, capture):
    eligible = row.get('training_eligibility', {}).get('eligible') is True
    if not eligible:
        return 'excluded_or_pending_validation'
    if row['status'] == 'internals_available':
        return 'eligible_with_internals'
    if (row.get('input_error_type') in ('syntax', 'compilation')
            and row['status'] == 'no_captured_failing_queries'
            and capture is not None and not capture.get('queries')
            and not capture.get('capture_errors')):
        return 'eligible_frontend_error_without_internals'
    return 'eligible_other_without_internals'


def audit(dataset, first, second, remaining, output):
    source_sha = hashlib.sha256(dataset.read_bytes()).hexdigest()
    source = load(dataset)
    repair_indices = {i for i, r in enumerate(source)
                      if 'provided Verus code contains errors' in r.get('prompt', '')}
    generation = [f'safe-{i:05d}' for i in range(len(source)) if i not in repair_indices]
    batches = [('first1000', first, 'pilot1000'), ('second1000', second, 'second1000')]
    batches += [('remaining-' + b, remaining / b / 'seed-20261018', 'remaining-' + b) for b in 'abcd']
    warnings, pending, inventories, stats, seen = [], [], defaultdict(list), {}, set()
    health, reasons, packages = Counter(), Counter(), defaultdict(list)
    for name, folder, selection in batches:
        frozen = load(ROOT / 'configs' / f'safe-repair-{selection}.json')
        if frozen['dataset_sha256'] != source_sha:
            raise ValueError('Dataset SHA mismatch: ' + name)
        manifest = folder / 'manifest.json'
        if manifest.exists():
            value = load(manifest)
            if value['selection']['cases'] != frozen['cases'] or value['dataset_sha256'] != source_sha:
                raise ValueError('Manifest selection mismatch: ' + name)
        counts = Counter({'completed': 0})
        for case in frozen['cases']:
            key = case['id']
            if key in seen or case['index'] not in repair_indices or key != f"safe-{case['index']:05d}":
                raise ValueError('Invalid/overlapping selection: ' + key)
            seen.add(key)
            base = folder / 'examples' / key
            path = base / 'result.json'
            if not path.exists():
                pending.append(key)
                continue
            try:
                row = load(path)
                if row['id'] != key:
                    raise ValueError('Result ID mismatch')
                capture_path = base / 'solver/report.json'
                capture = load(capture_path) if capture_path.exists() else None
                group = category(row, capture)
                if row.get('training_eligibility', {}).get('eligible') and (
                        row.get('target_success') is not True or row.get('preservation_status') != 'valid'):
                    warnings.append({'id': key, 'issue': 'eligibility contradicts target/preservation'})
                    group = 'excluded_or_pending_validation'
                inventories[group].append(key)
                counts[group] += 1
                counts['completed'] += 1
                reasons.update(row.get('training_eligibility', {}).get('reasons', []))
                health['capture_reports_missing'] += capture is None
                if capture is not None:
                    health['capture_errors'] += len(capture.get('capture_errors', []))
                    for q in capture.get('queries', []):
                        health['query_' + str(q['result'])] += 1
                collection_path = base / 'collection.json'
                if collection_path.exists():
                    collection = load(collection_path)
                    for q in collection.get('queries', []):
                        health['replays'] += 1
                        health['discordant_replays'] += not q.get('concordant', False)
                        health['replay_wall_timeouts'] += bool(q.get('wall_timeout'))
                        health['callback_errors'] += q.get('callback_errors') or 0
                else:
                    health['collection_files_missing'] += 1
                for package, p in row.get('packages', {}).items():
                    health['packet_budget_violations'] += p['block_tokens'] > p['budget']
                    health['context_reservation_violations'] += not p['fits_collection_context_with_reserve']
                    if group in ('eligible_with_internals', 'eligible_frontend_error_without_internals'):
                        packages[package].append(p)
                    if group == 'eligible_with_internals' and p.get('availability') != 'available':
                        health['eligible_internal_rows_missing_package_' + package] += 1
                if group == 'eligible_frontend_error_without_internals':
                    verification = load(base / 'verification.json')
                    if not (verification.get('stdout', '').strip() or verification.get('stderr', '').strip()):
                        warnings.append({'id': key, 'issue': 'frontend example has no saved Verus diagnostic'})
            except (OSError, ValueError, KeyError, TypeError) as error:
                warnings.append({'id': key, 'issue': 'read/schema error: ' + str(error)})
        stats[name] = {'path': str(folder), 'expected': len(frozen['cases']), **counts,
                       'pending_or_unreadable': len(frozen['cases']) - counts['completed']}
    if seen != {f'safe-{i:05d}' for i in repair_indices}:
        raise ValueError('Selections do not cover all repair rows')
    lengths = {name: {'measured': len(rows),
                     'max_full_training_tokens': max((p['full_training_tokens'] for p in rows), default=0),
                     'over_32k': sum(p['full_training_tokens'] > 32768 for p in rows),
                     'over_48k': sum(p['full_training_tokens'] > 49152 for p in rows)}
               for name, rows in packages.items()}
    result = {'dataset_sha256': source_sha, 'repair_expected': len(seen),
              'repair_completed': sum(s['completed'] for s in stats.values()),
              'categories': {k: len(v) for k, v in inventories.items()},
              'generation_original_unverified': len(generation),
              'generation_note': 'Original non-debugging rows; not verified by this collection or this audit.',
              'batches': stats, 'health': dict(health), 'exclusion_reasons_overlapping': dict(reasons),
              'training_lengths_selected_repairs': lengths, 'warnings': warnings,
              'pending_ids': pending, 'category_ids': dict(inventories), 'generation_ids': generation,
              'scope': 'Saved records only; no solver, model, export changes or current-code hash validation. '
                       'Not a training export. Generation requires separate validation; family/benchmark overlap checks remain.'}
    result['complete'] = result['repair_completed'] == len(seen) and not warnings
    output.mkdir(parents=True, exist_ok=True)
    (output / 'audit.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    lines = ['# SAFE training inventory', '', '| Batch | Completed | With internals | Frontend without internals | Other eligible |',
             '|---|---|---|---|---|']
    for name, s in stats.items():
        lines.append(f"| {name} | {s['completed']}/{s['expected']} | {s.get('eligible_with_internals', 0)} | "
                     f"{s.get('eligible_frontend_error_without_internals', 0)} | {s.get('eligible_other_without_internals', 0)} |")
    lines += ['', f"Repair records read: {result['repair_completed']}/{len(seen)}.",
              f"Training categories: {result['categories']}",
              f'Original generation rows: {len(generation)} (not verified here).',
              'Frontend repairs still require a verified, preserved, assume-free target. Their future prompt must include the saved Verus error and explicitly state that no SMT internals were obtained.',
              f'Collection health: {dict(health)}', f'Warnings: {len(warnings)} (details in audit.json).',
              f'Eligible repair lengths: {lengths}',
              'Missing batches and partially running batches are allowed. Counts are a snapshot; rerun after collection completes.',
              'Do not treat generation rows as verified positives yet. Do not use unfiltered exports for training. Split by family and check benchmark overlap before training.']
    (output / 'audit.md').write_text('\n\n'.join(lines[:1]) + '\n\n' + '\n'.join(lines[2:]) + '\n', encoding='utf-8')
    print(output / 'audit.md')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'data/safe/sft_safe_25k.json')
    parser.add_argument('--first', type=Path, default=ROOT / 'results/safe-internals-pilot1000-attrs-v2/seed-20261018')
    parser.add_argument('--second', type=Path, default=ROOT / 'results/safe-internals-second1000-attrs-v2/seed-20261018')
    parser.add_argument('--remaining', type=Path, default=ROOT / 'results/safe-internals-remaining-attrs-v2')
    parser.add_argument('--output', type=Path, default=ROOT / 'analysis/safe-training-audit')
    args = parser.parse_args()
    audit(args.dataset, args.first, args.second, args.remaining, args.output)
