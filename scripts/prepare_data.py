"""Copy ONLY official unverified inputs and freeze hashes, before inference."""
import argparse
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from baseline.benchmark import BENCHMARK_COMMIT, CATEGORIES, select_pilot
from baseline.prompts import ROOT
from baseline.storage import digest, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args()
    actual = subprocess.check_output(["git", "-C", str(args.checkout), "rev-parse", "HEAD"], text=True).strip()
    if actual != BENCHMARK_COMMIT:
        raise SystemExit("Benchmark checkout must match " + BENCHMARK_COMMIT)
    tasks = []
    for category, count in CATEGORIES.items():
        relative = Path("benchmarks/Verus-Bench") / category / "unverified"
        files = sorted((args.checkout / relative).glob("*.rs"))
        if len(files) != count:
            raise SystemExit(f"{category}: expected {count}, found {len(files)}")
        for source in files:
            # Read the git blob, avoiding Windows checkout newline conversion.
            git_path = (relative / source.name).as_posix()
            content = subprocess.check_output(["git", "-C", str(args.checkout), "show", f"HEAD:{git_path}"])
            if digest(source.read_bytes().replace(b"\r\n", b"\n")) != digest(content):
                raise SystemExit("Modified benchmark input: " + git_path)
            path = Path("unverified") / category / source.name
            target = ROOT / "data" / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            tasks.append({"id": category.lower() + "_" + source.stem, "category": category,
                          "path": path.as_posix(), "sha256": digest(content)})
    write_json(ROOT / "data/manifest.json", {"benchmark_commit": actual, "tasks": sorted(tasks, key=lambda t: t["id"])})
    select_pilot(ROOT / "data/manifest.json", ROOT / "data/pilot.json")
    print("Frozen 150 official inputs and the 15-task pilot selection.")


if __name__ == "__main__":
    main()
