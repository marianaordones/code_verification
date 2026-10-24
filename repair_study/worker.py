"""Replay with a bounded ranked reservoir: late source events can replace early prelude events."""
import argparse
import json
from pathlib import Path
import time

from baseline.storage import read_json, write_json, write_text
from diagnostics.z3_internals import identity
from diagnostics.z3_probe import head, snapshots
from .relevance import rank, qids


def worker(query, context, output, max_instances_per_group=4):
    output.mkdir(parents=True, exist_ok=True)
    report = {'status': 'unavailable', 'timeout_ms': 5000, 'instantiations_observed': 0,
              'callback_errors': 0, 'oversized_events': 0, 'per_qid_observed': {},
              'max_instances_per_group': max_instances_per_group}
    groups = {}
    try:
        report['z3'] = identity()
        import z3
        checks = list(snapshots(query.read_text(encoding='utf-8')))
        if len(checks) != 1 or head(checks[0][1]) != 'check-sat':
            raise ValueError('Replay requires a single plain check-sat')
        solver = z3.Solver()
        solver.from_string(checks[0][0])
        solver.set(timeout=5000)

        def on_clause(hint, dependencies, clause):
            try:
                if not z3.is_app(hint) or str(hint.decl().name()) != 'inst':
                    return
                report['instantiations_observed'] += 1
                quantifier = hint.arg(0)
                if not z3.is_quantifier(quantifier):
                    return
                formula = quantifier.sexpr()
                for qid in qids(formula):
                    report['per_qid_observed'][qid] = report['per_qid_observed'].get(qid, 0) + 1
                score, category = rank(formula, context)
                if formula not in groups:
                    if len(groups) >= 128:
                        worst = max(groups, key=lambda f: groups[f]['rank'])
                        if score >= groups[worst]['rank']:
                            return
                        del groups[worst]
                    groups[formula] = {'rank': score, 'category': category, 'events': []}
                events = groups[formula]['events']
                if len(events) >= max_instances_per_group:
                    return
                event = {'quantifier_smt': formula,
                         'binding_terms_callback_order': [a.sexpr() for c in hint.children()
                            if z3.is_app(c) and str(c.decl().name()) == 'bind' for a in c.children()],
                         'clause_literals_smt': [a.sexpr() for a in clause]}
                if len(json.dumps(event)) > 64000:
                    report['oversized_events'] += 1
                elif event not in events:
                    events.append(event)
            except Exception:
                report['callback_errors'] += 1

        callback = z3.OnClause(solver, on_clause)
        start = time.perf_counter()
        result = solver.check()
        report.update(status='completed', result=str(result),
                      reason_unknown=solver.reason_unknown() if result == z3.unknown else None,
                      check_seconds=time.perf_counter() - start,
                      statistics={key: value for key, value in solver.statistics()})
        assert callback is not None
    except Exception as error:
        report['error'] = str(error)
    events = [e for group in sorted(groups.values(), key=lambda g: g['rank']) for e in group['events']]
    report['instantiations_saved'] = len(events)
    write_text(output / 'instantiations.jsonl', ''.join(json.dumps(e) + '\n' for e in events))
    write_json(output / 'report.json', report)
    return 0 if report['status'] == 'completed' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--query', type=Path, required=True)
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-instances-per-group', type=int, default=4)
    args = parser.parse_args()
    if args.max_instances_per_group < 1:
        parser.error('max-instances-per-group must be positive')
    raise SystemExit(worker(args.query, read_json(args.context), args.output, args.max_instances_per_group))
