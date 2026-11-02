import json
from pathlib import Path
import time

from baseline.inference import MODEL_CODER, REVISION_CODER, prepare_model
from baseline.storage import digest, read_json


def adapter_identity(adapter):
    adapter = Path(adapter).resolve()
    config = read_json(adapter / 'adapter_config.json')
    if config.get('peft_type') != 'LORA' or config.get('task_type') != 'CAUSAL_LM' or config.get('r') != 16:
        raise ValueError('Expected the rank-16 causal SAFE LoRA adapter')
    if config.get('modules_to_save'):
        raise ValueError('Unexpected saved full modules; this evaluator expects LoRA-only weights')
    provenance = read_json(adapter.parent / 'training-provenance.json')
    if provenance['model'] != MODEL_CODER or provenance['revision'] != REVISION_CODER or provenance['smoke']:
        raise ValueError('Not the completed full SAFE coder training run')
    files = [adapter / 'adapter_config.json', adapter / 'adapter_model.safetensors',
             adapter.parent / 'training-provenance.json']
    return {'files': {p.name: digest(p.read_bytes()) for p in files}, 'provenance': provenance}


class Engine:
    def __init__(self, adapter):
        from vllm import LLM
        from vllm.lora.request import LoRARequest
        adapter_identity(adapter)
        local = prepare_model(MODEL_CODER, REVISION_CODER)
        self.engine = LLM(model=local, tokenizer=local, dtype='bfloat16',
            tensor_parallel_size=1, max_model_len=32768, max_num_seqs=1,
            gpu_memory_utilization=.90, enforce_eager=True, enable_chunked_prefill=True,
            max_num_batched_tokens=2048, enable_lora=True, max_loras=1, max_lora_rank=16,
            seed=20261018, generation_config='vllm')
        self.request = LoRARequest('safe-enriched', 1, str(Path(adapter).resolve()))
        self.tokenizer = self.engine.get_tokenizer()

    def generate(self, messages, seed):
        from vllm import SamplingParams
        rendered = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        if len(self.tokenizer.encode(rendered, add_special_tokens=False)) + 4096 > 32768:
            raise ValueError('Prompt exceeds context reservation; no truncation')
        started = time.perf_counter()
        item = self.engine.generate([rendered], SamplingParams(temperature=.7, top_p=.8,
            top_k=20, min_p=0., max_tokens=4096, seed=seed), lora_request=self.request, use_tqdm=False)[0]
        value = item.outputs[0]
        return {'text': value.text, 'input_tokens': len(item.prompt_token_ids),
                'output_tokens': len(value.token_ids), 'finish_reason': value.finish_reason,
                'truncated': value.finish_reason == 'length', 'seed': seed,
                'inference_seconds': time.perf_counter() - started, 'adapter_applied': True}
