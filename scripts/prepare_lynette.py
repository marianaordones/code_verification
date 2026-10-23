"""Vendor pinned parser sources, preserving license, and close unchecked tails."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from baseline.benchmark import BENCHMARK_COMMIT
from baseline.prompts import ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args()
    revision = subprocess.check_output(["git", "-C", str(args.checkout), "rev-parse", "HEAD"], text=True).strip()
    if revision != BENCHMARK_COMMIT:
        raise SystemExit("Unexpected Lynette source revision")
    prefix = "utils/lynette/source/"
    files = subprocess.check_output(["git", "-C", str(args.checkout), "ls-tree", "-r", "--name-only", "HEAD", prefix], text=True).splitlines()
    for name in files:
        if "/tests/" in name:
            continue
        target = ROOT / "tools/lynette/source" / name.removeprefix(prefix)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output(["git", "-C", str(args.checkout), "show", "HEAD:" + name]))
    shutil.copyfile(args.checkout / "LICENSE", ROOT / "tools/lynette/LICENSE")
    source = ROOT / "tools/lynette/source/lynette/src/additions.rs"
    text = source.read_text(encoding="utf-8")
    old = "return idx_orig == original_items.len();"
    if text.count(old) != 3:
        raise SystemExit("Upstream changed: review the tail-check patch")
    # Upstream stops when all original items were consumed. Every trailing item
    # must also be checked: only new proof/spec functions with bodies may remain.
    for item_type in ("ImplItem", "TraitItem", "Item"):
        body = "f.default.is_some()" if item_type == "TraitItem" else "f.semi_token.is_none()"
        replacement = f'''return idx_orig == original_items.len()
        && changed_items[idx_changed..].iter().all(|item| match item {{
            syn_verus::{item_type}::Fn(f) => matches!(f.sig.mode, Proof(_) | Spec(_) | SpecChecked(_)) && {body},
            _ => false,
        }});'''
        text = text.replace(old, replacement, 1)
    # Existing termination clauses are part of the original contract. Permit
    # adding one when absent, but never remove/change a pre-existing one.
    text = text.replace("orig_spec.decreases = None;", "if original.spec.decreases.is_none() { orig_spec.decreases = None; }")
    text = text.replace("changed_spec.decreases = None;", "if original.spec.decreases.is_none() { changed_spec.decreases = None; }")
    text = text.replace("orig_spec.invariants = None;", "")
    text = text.replace("changed_spec.invariants = None;", "")
    source.write_text(text, encoding="utf-8", newline="\n")
    print("Pinned Lynette sources copied; all three unchecked item tails patched.")


if __name__ == "__main__":
    main()
