"""Single-GPU QLoRA, enriched SAFE only. No silent truncation; assistant-only loss."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def encode(tokenizer, messages, max_length):
    if messages[-1]['role'] != 'assistant':
        raise ValueError('Expected one final assistant target')
    prompt = tokenizer.apply_chat_template(messages[:-1], tokenize=True, add_generation_prompt=True)
    full = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=False)
    if full[:len(prompt)] != prompt:
        raise ValueError('Chat template prefix mismatch; cannot safely mask assistant loss')
    if len(full) > max_length:
        raise ValueError(f'Example has {len(full)} tokens > {max_length}; no truncation allowed')
    if len(full) <= len(prompt):
        raise ValueError('Empty assistant target')
    return {'input_ids': full, 'attention_mask': [1] * len(full),
            'labels': [-100] * len(prompt) + full[len(prompt):]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', type=Path, default=Path('data/safe/sft-enriched-v1'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--smoke', action='store_true', help='Two optimizer steps on longest training example; not a scientific training run')
    p.add_argument('--resume', type=Path)
    p.add_argument('--epochs', type=float, default=1.)
    args = p.parse_args()
    import torch
    from torch.utils.data import Dataset
    from torch.utils.checkpoint import checkpoint
    from transformers import (AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig,
                              Trainer, TrainingArguments, set_seed)
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError('A CUDA GPU with BF16 support is required')
    if int(os.environ.get('WORLD_SIZE', '1')) != 1:
        raise ValueError('This implementation supports one GPU only')
    model_id = 'Qwen/Qwen2.5-Coder-14B-Instruct'
    revision = 'aedcc2d42b622764e023cf882b6652e646b95671'
    from baseline.inference import prepare_model
    local_model = prepare_model(model_id, revision)
    set_seed(20261018)
    manifest = json.loads((args.data / 'manifest.json').read_text())
    tokenizer = AutoTokenizer.from_pretrained(local_model)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = 'right'
    class Rows(Dataset):
        def __init__(self, split):
            path = args.data / f'{split}.jsonl'
            if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['files_sha256'][path.name]:
                raise ValueError('Dataset changed after preparation: ' + str(path))
            self.rows = []
            self.families = set()
            for line in path.read_text(encoding='utf-8').splitlines():
                row = json.loads(line)
                self.rows.append(encode(tokenizer, row['messages'], 32768))
                self.families.add(row['family_id'])
        def __len__(self):
            return len(self.rows)
        def __getitem__(self, index):
            return self.rows[index]
    train, validation = Rows('train'), Rows('validation')
    if not len(train) or not len(validation) or train.families & validation.families:
        raise ValueError('Empty split or family leakage')
    if args.smoke:
        longest = max(train.rows, key=lambda x: len(x['input_ids']))
        train.rows = [longest, longest]
        validation.rows = [max(validation.rows, key=lambda x: len(x['input_ids']))]
    args.output.mkdir(parents=True, exist_ok=True)
    if list(args.output.iterdir()) and not args.resume:
        raise ValueError('Output must be empty, or explicitly resume a checkpoint')
    provenance = {
        'model': model_id, 'revision': revision, 'dataset_manifest': manifest,
        'smoke': args.smoke, 'epochs': args.epochs, 'max_length': 32768,
        'gpu': torch.cuda.get_device_name(), 'torch': torch.__version__,
        'training_code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'loss': 'assistant tokens only; chunked exact cross entropy; no packing/truncation'}
    provenance_path = args.output / 'training-provenance.json'
    if args.resume:
        previous = json.loads(provenance_path.read_text())
        for key in ('model', 'revision', 'dataset_manifest', 'smoke', 'epochs', 'max_length', 'training_code_sha256'):
            if previous[key] != provenance[key]:
                raise ValueError('Resume provenance changed: ' + key)
    else:
        provenance_path.write_text(json.dumps(provenance, indent=2))
    model = AutoModelForCausalLM.from_pretrained(local_model,
        quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
            bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16),
        torch_dtype=torch.bfloat16, device_map={'': 0}, attn_implementation='sdpa')
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True,
                                           gradient_checkpointing_kwargs={'use_reentrant': False})
    model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=.05,
                                           target_modules='all-linear', task_type='CAUSAL_LM'))
    model.print_trainable_parameters()
    def collate(rows):
        width = max(len(r['input_ids']) for r in rows)
        return {k: torch.tensor([r[k] + [pad] * (width - len(r[k])) for r in rows])
                for k, pad in [('input_ids', tokenizer.pad_token_id), ('attention_mask', 0), ('labels', -100)]}
    class ChunkedTrainer(Trainer):
        # Qwen's large vocabulary otherwise creates a full [length,vocab] logits tensor.
        # Checkpoint each supervised chunk, preserving exact next-token loss.
        def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
            labels = inputs.pop('labels')[:, 1:]
            base = model.get_base_model()
            hidden = base.model(**inputs, use_cache=False, return_dict=True).last_hidden_state[:, :-1]
            mask = labels != -100
            selected, targets = hidden[mask], labels[mask]
            if not targets.numel():
                raise ValueError('No supervised tokens')
            def loss_chunk(h, y):
                logits = base.lm_head(h).float()
                return torch.nn.functional.cross_entropy(logits, y, reduction='sum')
            total = sum(checkpoint(loss_chunk, selected[i:i+128], targets[i:i+128], use_reentrant=False)
                        for i in range(0, len(targets), 128)) / len(targets)
            return (total, {'loss': total}) if return_outputs else total
    config = TrainingArguments(output_dir=str(args.output), num_train_epochs=args.epochs,
        max_steps=2 if args.smoke else -1, per_device_train_batch_size=1, per_device_eval_batch_size=1,
        gradient_accumulation_steps=1 if args.smoke else 16, learning_rate=1e-4,
        lr_scheduler_type='cosine', warmup_ratio=.03, bf16=True,
        gradient_checkpointing=True, gradient_checkpointing_kwargs={'use_reentrant': False},
        optim='paged_adamw_8bit', logging_steps=1 if args.smoke else 10,
        save_steps=100, save_total_limit=2, eval_strategy='no' if args.smoke else 'steps',
        eval_steps=100, prediction_loss_only=True, report_to=[], remove_unused_columns=False,
        seed=20261018, data_seed=20261018)
    trainer = ChunkedTrainer(model=model, args=config, train_dataset=train,
                             eval_dataset=validation, data_collator=collate)
    # This custom loss is averaged per example, not normalized by Trainer's
    # optional global num_items_in_batch. Retain normal accumulation scaling.
    trainer.model_accepts_loss_kwargs = False
    trainer.train(resume_from_checkpoint=str(args.resume) if args.resume else None)
    trainer.save_model(str(args.output / 'adapter'))
    tokenizer.save_pretrained(args.output / 'adapter')
    metrics = trainer.evaluate()
    metrics['peak_gpu_allocated_bytes'] = torch.cuda.max_memory_allocated()
    (args.output / 'metrics.json').write_text(json.dumps(metrics, indent=2))


if __name__ == '__main__':
    main()
