"""Run one pending task in a separate resource-controlled study snapshot."""
import argparse
from pathlib import Path
import shutil

from baseline.storage import read_json, write_json
from scripts.claude_bounded import BoundedClaude, POLICY
from scripts.resume_sonnet46_remaining import pending_tasks, provenance
from verusbench_sonnet46 import __main__ as study


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'status'))
    parser.add_argument('--task', default='misc_bubble')
    parser.add_argument('--source', type=Path, default=study.DEFAULT)
    parser.add_argument('--output', type=Path, default=study.ROOT / 'results/verusbench-sonnet46-bounded-misc-bubble-v1')
    args = parser.parse_args()
    root, source = args.output.resolve(), args.source.resolve()
    if root == source or root.is_relative_to(source) or source.is_relative_to(root):
        raise ValueError('Use a separate output directory')
    if args.command == 'prepare':
        with study.vb.run_lock(source):
            manifest = study.validate(source)
            if args.task not in [t['id'] for _, t in pending_tasks(source, manifest)]:
                raise ValueError('Task is not pending in the original study')
            if root.exists():
                raise ValueError('Output already exists; use status or run')
            root.mkdir(parents=True)
            shutil.copy2(source / 'manifest.json', root / 'manifest.json')
            shutil.copytree(source / 'inputs', root / 'inputs')
            write_json(root / 'bounded-plan.json', {'policy': POLICY, 'task': args.task,
                'source': str(source), 'old_calls_not_reused': True,
                'source_runtime': read_json(source / 'runtime.json') if (source / 'runtime.json').exists() else None})
            study.validate(root)
        print('Prepared:', root, '\nNo Claude requests. Old results are unchanged.')
        return
    with study.vb.run_lock(root):
        manifest = study.validate(root)
        plan = read_json(root / 'bounded-plan.json')
        if plan['policy'] != POLICY or plan['task'] != args.task:
            raise ValueError('Policy/task changed; use a new output directory')
        index, task = next((i, t) for i, t in enumerate(manifest['selection']) if t['id'] == args.task)
        if args.command == 'run':
            runtime = study.vb.tools()
            if study.vb.identity(runtime) != manifest['tools']:
                raise ValueError('Verifier toolchain changed')
            current = provenance()
            if plan['source_runtime'] and current != plan['source_runtime']:
                raise ValueError('CLI/runtime changed from source study')
            inference = BoundedClaude(study.load_tokenizer({'provider': 'claude_code'}))
            verifier, guard = study.vb.verify_tools(runtime, manifest['config'])
            order = study.vb.ARMS if index % 2 == 0 else study.vb.ARMS[::-1]
            study.run_task(root, task, manifest['config'], inference, verifier, guard, order)
        paths = [('shared', root / 'shared' / args.task / 'task.json')]
        paths += [(a, root / a / args.task / 'task.json') for a in study.vb.ARMS]
        summary = {name: read_json(p) if p.exists() else None for name, p in paths}
        summary['task'] = args.task
        summary['policy'] = POLICY
        summary['calls'] = [{ 'path': str(p.parent.relative_to(root)), **read_json(p)}
                            for a in ('shared', *study.vb.ARMS)
                            for p in (root / a / args.task).glob('attempt_*/claude-call.json')]
        write_json(root / 'bounded-summary.json', summary)
        for name, p in paths:
            print(name, read_json(p) if p.exists() else 'not run / unnecessary if shared succeeded')
        print('Summary:', root / 'bounded-summary.json')


if __name__ == '__main__':
    main()
