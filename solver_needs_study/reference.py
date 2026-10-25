"""Freeze settings and system prompt from the original completed 24k experiment."""
import json

from baseline.storage import digest, read_json
from .actions import EMPTY
from .data import SELECTION
from .download import REVISION
from .feedback import messages


def reference_settings(reference, config):
    manifest = read_json(reference / 'manifest.json')
    ids = [case['id'] for case in manifest['cases']]
    if manifest['revision'] != REVISION or ids != read_json(SELECTION)['ids']:
        raise ValueError('Settings reference must be the original fixed 100-task experiment')
    old = manifest['config']
    if old.get('internals_token_budget') != 24576 or old.get('max_quantifiers') != 50 or old.get('max_instances_each') != 3:
        raise ValueError('Expected the original 24k, 50x3 configuration')
    if {k: v for k, v in old.items() if k != 'system_prompt_text'} != {
            k: v for k, v in config.items() if k != 'system_prompt_text'}:
        raise ValueError('Local configuration differs from the original 24k experiment')
    for key in ids:
        for arm in ('with_internals', 'without_internals'):
            if not (reference / arm / key / 'task.json').exists():
                raise ValueError('Original 100-task experiment is incomplete: ' + arm + '/' + key)
    request_path = reference / 'without_internals' / ids[0] / 'attempt_01/request.json'
    request = read_json(request_path)
    if request['messages'][0]['role'] != 'system':
        raise ValueError('Original system prompt is missing')
    frozen = {**old, 'system_prompt_text': request['messages'][0]['content']}
    return frozen, {'path': str(reference), 'ids': ids,
        'manifest_sha256': digest((reference / 'manifest.json').read_bytes()),
        'first_control_request_sha256': digest(request_path.read_bytes()),
        'system_prompt_sha256': digest(frozen['system_prompt_text'].encode()),
        'max_attempts': old['max_attempts']}


def check_reference_prompt(reference, config, key):
    folder = reference / 'inputs' / key
    code = (folder / 'candidate.rs').read_text(encoding='utf-8')
    verification = read_json(folder / 'verification.json')
    context = read_json(folder / 'feedback.json')['context']
    current = messages(code, verification, EMPTY, context, None, [], config=config)
    saved = read_json(reference / 'without_internals' / key / 'attempt_01/request.json')
    if saved['messages'] != current:
        raise ValueError('Current common prompt/catalogue differs from the original 24k experiment')
    if saved['common_messages_sha256'] != digest(json.dumps(current, sort_keys=True).encode()):
        raise ValueError('Original common prompt hash mismatch')
