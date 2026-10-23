from pathlib import Path
import random

from .storage import digest, read_json, write_json

CATEGORIES = {"CloverBench": 11, "Diffy": 38, "MBPP": 78, "Misc": 23}
ALLOCATION = {"CloverBench": 2, "Diffy": 4, "MBPP": 7, "Misc": 2}
SEED = 20261018
BENCHMARK_COMMIT = "cbf9c0c6337b224fd8e5b7cb4e01ae65c0f98bc1"


def load_tasks(manifest):
    manifest = Path(manifest)
    data = read_json(manifest)
    if data["benchmark_commit"] != BENCHMARK_COMMIT:
        raise ValueError("Unexpected benchmark revision")
    tasks = data["tasks"]
    ids = [t["id"] for t in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate task IDs")
    for task in tasks:
        path = (manifest.parent / task["path"]).resolve()
        if not path.is_relative_to(manifest.parent.resolve()) or "unverified" not in path.parts:
            raise ValueError("Only local unverified inputs are permitted")
        if digest(path.read_bytes()) != task["sha256"]:
            raise ValueError(f"Input changed: {task['id']}")
        if task["category"] not in CATEGORIES:
            raise ValueError("Unknown benchmark category")
        task["file"] = str(path)
    return tasks


def select_pilot(manifest, output):
    tasks = load_tasks(manifest)
    if {c: sum(t["category"] == c for t in tasks) for c in CATEGORIES} != CATEGORIES:
        raise ValueError("Expected the official 150-task inventory")
    rng = random.Random(SEED)
    selected = []
    for category, count in ALLOCATION.items():
        pool = sorted((t["id"] for t in tasks if t["category"] == category))
        selected.extend(rng.sample(pool, count))
    value = {"seed": SEED, "allocation": ALLOCATION,
             "manifest_sha256": digest(Path(manifest).read_bytes()), "task_ids": sorted(selected)}
    if Path(output).exists() and read_json(output) != value:
        raise ValueError("Refusing to overwrite a different pilot selection")
    write_json(output, value)
    return value


def pilot10_selection(manifest, previous_selection):
    """First ten IDs in the pre-existing pilot order, without new sampling."""
    previous_selection = Path(previous_selection)
    previous = read_json(previous_selection)
    manifest_hash = digest(Path(manifest).read_bytes())
    if previous["manifest_sha256"] != manifest_hash or len(previous["task_ids"]) != 15:
        raise ValueError("The original pilot selection/benchmark changed")
    return {"seed": SEED, "method": "first_10_in_original_pilot_order",
            "source_selection_sha256": digest(previous_selection.read_bytes()),
            "manifest_sha256": manifest_hash, "task_ids": previous["task_ids"][:10]}


def pilot50_selection(manifest):
    """Fixed arbitrary subset: uniform sampling, no difficulty/performance filter."""
    tasks = load_tasks(manifest)
    if len(tasks) != 150:
        raise ValueError("Expected all 150 official inputs before selecting 50")
    pool = sorted(task["id"] for task in tasks)
    selected = sorted(random.Random(SEED).sample(pool, 50))
    return {"seed": SEED, "method": "uniform_sample_without_replacement",
            "population_order": "task_id_ascending", "execution_order": "task_id_ascending",
            "manifest_sha256": digest(Path(manifest).read_bytes()),
            "task_ids": selected,
            "category_counts": {category: sum(task["category"] == category and task["id"] in selected
                                              for task in tasks) for category in CATEGORIES}}


def coder100_selection(manifest):
    """Uniform arbitrary sample of 100 official inputs, fixed before inference."""
    tasks = load_tasks(manifest)
    if len(tasks) != 150:
        raise ValueError("Expected all 150 official inputs")
    selected = sorted(random.Random(SEED).sample(sorted(t["id"] for t in tasks), 100))
    return {"seed": SEED, "method": "uniform_sample_without_replacement",
            "population_order": "task_id_ascending", "execution_order": "task_id_ascending",
            "manifest_sha256": digest(Path(manifest).read_bytes()), "task_ids": selected,
            "category_counts": {c: sum(t["category"] == c and t["id"] in selected
                                       for t in tasks) for c in CATEGORIES}}
