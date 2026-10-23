import copy
import json

from baseline.prompts import ROOT
from baseline.storage import read_json, write_json
from repair_study.feedback import build_payload
from repair_study.regions import regions
from repair_study.relevance import source_context

ARMS = ('with_internals', 'without_internals')


def system_prompt():
    guide = (ROOT / 'prompts/repair-study/solver-info.txt').read_text(encoding='utf-8')
    guide = guide.replace(
        'In the first repair both arms start from the same saved candidate and receive the same internals; subsequent failures may differ.',
        'Solver data, if supplied, describes this candidate; subsequent failures may differ.')
    return '\n\n'.join([
        (ROOT / 'prompts/v4/system.txt').read_text(encoding='utf-8'), guide,
        (ROOT / 'prompts/local-ablation/common.txt').read_text(encoding='utf-8'),
        (ROOT / 'prompts/repair-study/local.txt').read_text(encoding='utf-8')])


def exposed_payload(arm, payload):
    if arm not in ARMS:
        raise ValueError('Unknown ablation arm')
    # The control contains no results/reasons, statistics, formulas or sampling metadata.
    if arm == 'without_internals':
        return {'availability': 'withheld_by_design', 'source_context': payload['source_context']}
    return copy.deepcopy(payload)


def messages(original, candidate, verification, integrity, exposed, progress=''):
    try:
        sites = regions(candidate)
    except ValueError:
        sites = []
    data = ('Repair the saved failed candidate. Make a concrete permitted proof change.\n'
            '<original_program>\n' + original + '\n</original_program>\n'
            '<current_candidate>\n' + candidate + '\n</current_candidate>\n'
            '<verus_diagnostics>\n' + verification['stdout'] + '\n' + verification['stderr'] + '\n</verus_diagnostics>\n'
            '<integrity_diagnostics>\n' + json.dumps(integrity, ensure_ascii=False) + '\n</integrity_diagnostics>\n'
            '<progress>\n' + progress + '\n</progress>\n'
            '<source_failure_context>\n' + json.dumps(exposed['source_context'], ensure_ascii=False, indent=2) + '\n</source_failure_context>\n')
    # Unavailable replay data is omitted in both arms, giving identical control prompts.
    if exposed['availability'] == 'available':
        solver = {k: v for k, v in exposed.items() if k != 'source_context'}
        data += '<solver_internals>\n' + json.dumps(solver, ensure_ascii=False, indent=2) + '\n</solver_internals>\n'
    data += '<editable_sites>\n' + json.dumps(sites, ensure_ascii=False, indent=2) + '\n</editable_sites>\n'
    data += 'Address the source failure. Do not return an unchanged candidate. Follow your output contract.'
    return [{'role': 'system', 'content': system_prompt()}, {'role': 'user', 'content': data}]


def fit_payload(payload, original, candidate, verification, integrity, tokenizer, config, progress=''):
    """Keep whole formulas, fitting the actual ablation prompt rather than the old template."""
    value = copy.deepcopy(payload)
    while True:
        prompt = messages(original, candidate, verification, integrity, value, progress)
        count = len(tokenizer.apply_chat_template(prompt, tokenize=True, add_generation_prompt=True))
        if count + config['max_tokens'] <= config['max_model_len']:
            return value
        groups = value.get('quantifiers', [])
        if value['availability'] != 'available' or not groups:
            raise ValueError('Base localized prompt exceeds context; no source truncation applied')
        # Lowest-ranked groups are last. Never cut a formula in the middle.
        groups[-1]['instances'].pop()
        if not groups[-1]['instances']:
            groups.pop()
        value['sampling']['selected_groups'] = len(groups)
        value['sampling']['selected_instances'] = sum(len(q['instances']) for q in groups)


def next_payload(arm, folder, original, candidate, verification, integrity, tokenizer, config, progress):
    path = folder / 'next-feedback.json'
    if path.exists():
        return read_json(path)
    if arm == 'without_internals':
        value = {'availability': 'withheld_by_design', 'source_context': source_context(candidate, verification)}
    else:
        value = build_payload(folder, original, candidate, verification, integrity, tokenizer, config, progress)
        value = fit_payload(value, original, candidate, verification, integrity, tokenizer, config, progress)
    write_json(path, value)
    return value
