import json
import time

from .prompts import ROOT

MODEL = "Qwen/Qwen3-8B"
REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
MODEL_14B = "Qwen/Qwen3-14B"
REVISION_14B = "40c069824f4251a91eefaf281ebe4c544efd3e18"
MODEL_CODER = "Qwen/Qwen2.5-Coder-14B-Instruct"
REVISION_CODER = "aedcc2d42b622764e023cf882b6652e646b95671"
MODEL_REVISIONS = {MODEL: REVISION, MODEL_14B: REVISION_14B, MODEL_CODER: REVISION_CODER}


def model_identity(config=None):
    config = config or {}
    model = config.get("model", MODEL)
    revision = config.get("model_revision", MODEL_REVISIONS.get(model))
    if model not in MODEL_REVISIONS or revision != MODEL_REVISIONS[model]:
        raise ValueError("Use a supported Qwen model with its pinned revision")
    return model, revision


def prepare_model(model=MODEL, revision=REVISION):
    """Download regular files into persistent shared storage, without symlinks."""
    from huggingface_hub import snapshot_download
    model_identity({"model": model, "model_revision": revision})
    destination = ROOT / ".cluster/models" / model.split("/")[-1] / revision
    snapshot_download(repo_id=model, revision=revision,
                      local_dir=str(destination), max_workers=1)
    index = destination / "model.safetensors.index.json"
    with index.open(encoding="utf-8") as stream:
        shards = set(json.load(stream)["weight_map"].values())
    required = {"config.json", "tokenizer.json", "tokenizer_config.json",
                "model.safetensors.index.json"} | shards
    for name in required:
        path = destination / name
        if (not path.resolve().is_relative_to(destination.resolve()) or path.is_symlink()
                or not path.is_file() or path.stat().st_size == 0):
            raise RuntimeError(f"Incomplete model download or invalid local model file: {path}")
    return str(destination)


def extract_code(text, thinking):
    """Qwen's assistant prefix may already contain the opening think token."""
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    elif thinking:
        return ""  # An unfinished reasoning block is never a program.
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[0] in ("```", "```rust", "```verus", "```rs"):
            text = "\n".join(lines[1:-1])
    return text.strip()


class LocalVLLM:
    def __init__(self, config=None):
        from vllm import LLM
        config = config or {}
        local_model = prepare_model(*model_identity(config))
        engine_options = {key: config[key] for key in (
            "rope_scaling", "cpu_offload_gb", "enable_chunked_prefill", "max_num_batched_tokens")
                          if key in config}
        self.engine = LLM(model=local_model, tokenizer=local_model,
                          dtype="bfloat16", tensor_parallel_size=1, seed=20261018,
                          max_model_len=config.get("max_model_len", 32768),
                          gpu_memory_utilization=config.get("gpu_memory_utilization", 0.90),
                          max_num_seqs=config.get("max_num_seqs", 256),
                          generation_config="vllm", enforce_eager=True, **engine_options)
        self.tokenizer = self.engine.get_tokenizer()

    def generate(self, messages, config, seed):
        from vllm import SamplingParams
        template_options = {} if config["mode"] == "instruct" else {"enable_thinking": config["enable_thinking"]}
        prompt = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
            **template_options)
        params = SamplingParams(temperature=config["temperature"], top_p=config["top_p"],
                                top_k=20, min_p=0.0, max_tokens=config["max_tokens"],
                                seed=seed, n=1)
        started = time.perf_counter()
        result = self.engine.generate([prompt], params, use_tqdm=False)[0]
        elapsed = time.perf_counter() - started
        output = result.outputs[0]
        ids = list(output.token_ids)
        end_id = (self.tokenizer.convert_tokens_to_ids("</think>")
                  if config["mode"] != "instruct" else None)
        split = ids.index(end_id) if end_id in ids else None
        if split is not None:
            reasoning, final = split, len(ids) - split - 1
        elif config["enable_thinking"]:
            reasoning, final = len(ids), 0
        else:
            reasoning, final = 0, len(ids)
        return {"text": output.text, "rendered_prompt": prompt, "token_ids": ids,
                "input_tokens": len(result.prompt_token_ids), "output_tokens": len(ids),
                "reasoning_tokens": reasoning, "final_tokens": final,
                "token_count_method": "Qwen token IDs split at </think>; delimiter excluded",
                "finish_reason": output.finish_reason, "truncated": output.finish_reason == "length",
                "inference_seconds": elapsed, "seed": seed}
