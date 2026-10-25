"""One refreshed initial replay pool, shared by the 80x3 and 50x5 variants."""
from baseline.__main__ import run_lock
from baseline.prompts import ROOT
from baseline.storage import digest, read_json, write_json
from .actions import EMPTY
from .feedback import internals
from .reuse import contained


def ensure_pool(folder, origin, config, context, tokenizer):
    report = read_json(origin / 'solver/report.json')
    failed = [q for q in report['queries'] if q['result'] in ('sat', 'unknown')][:config['max_queries']]
    names = ['task.json', 'candidate.rs', 'verification.json', 'solver/report.json']
    names += ['solver/' + q['file'] for q in failed]
    source_bytes = {name: contained(origin, name).read_bytes() for name in names}
    plan = {'source_sha256': {name: digest(value) for name, value in source_bytes.items()},
            'collect_inventory': bool(config.get('collect_inventory')),
            'inventory_implementation': digest((ROOT / 'diagnostics/z3_feedback_pilot.py').read_bytes()) if config.get('collect_inventory') else None,
            'context': context, 'max_queries': config['max_queries'], 'max_instances_per_group': 5,
            'worker_sha256': digest((ROOT / 'repair_study/worker.py').read_bytes()),
            'ranking_sha256': digest((ROOT / 'repair_study/relevance.py').read_bytes()),
            'system_prompt_sha256': digest(config['system_prompt_text'].encode())}
    with run_lock(folder):
        manifest_path = folder / 'pool.json'
        if manifest_path.exists():
            manifest = read_json(manifest_path)
            if manifest['plan'] != plan:
                raise ValueError('Shared pool inputs or collector changed; use another pool directory')
            for name, expected in manifest['files'].items():
                if digest(contained(folder, name).read_bytes()) != expected:
                    raise ValueError('Shared replay evidence changed: ' + name)
            return folder
        if (folder / 'plan.json').exists() and read_json(folder / 'plan.json') != plan:
            raise ValueError('Partial shared pool has different inputs; use another pool directory')
        write_json(folder / 'plan.json', plan)
        for name, value in source_bytes.items():
            target = contained(folder, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)
        # The packaging here is incidental: both variants read the raw saved events.
        collection_config = {**config, 'max_quantifiers': 80, 'max_instances_each': 5,
                             'replay_max_instances': 5}
        internals(folder, source_bytes['candidate.rs'].decode('utf-8'),
                  read_json(folder / 'verification.json'), EMPTY, [], tokenizer,
                  collection_config, replay=True, saved_context=context)
        files = {str(p.relative_to(folder)): digest(p.read_bytes()) for p in folder.rglob('*')
                 if p.is_file() and p.name not in ('.lock', 'pool.json')}
        write_json(manifest_path, {'plan': plan, 'files': files,
            'scope': 'new diagnostic replays of original captured queries; common initial evidence for both variants'})
    return folder
