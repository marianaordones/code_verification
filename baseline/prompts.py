from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parents[1]


def prompt_directory(version="v1"):
    if version not in ("v1", "v2", "v3", "v4", "v4-internals"):
        raise ValueError("Unknown prompt version")
    return ROOT / "prompts" if version == "v1" else ROOT / "prompts" / version


def build_messages(code, feedback=None, version="v1", original=None):
    name = "initial.txt" if feedback is None else "repair.txt"
    directory = prompt_directory(version)
    template = (directory / name).read_text(encoding="utf-8")
    system = (directory / "system.txt").read_text(encoding="utf-8")
    if version == "v4-internals":
        system += "\n\n" + (directory / "solver-info.txt").read_text(encoding="utf-8")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": Template(template).substitute(code=code, feedback=feedback or "", original=original or code)},
    ]
