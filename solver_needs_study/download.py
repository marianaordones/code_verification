"""Download pinned public data and the separate Verus release; no source builds."""
import argparse
import io
import json
from pathlib import Path, PurePosixPath
import stat
import urllib.request
import zipfile

from baseline.prompts import ROOT
from baseline.storage import digest, read_json, write_json

REVISION = 'f32c274b053c372aa35c9d8a7e12c1df35bda20d'
SOURCE_SHA = 'd3073e04bd3454059938ee5e179fc8cec2d3ddec9c89094ee93b02d6c65bb279'
VERUS_VERSION = '0.2026.02.22.2c9a6a0'
VERUS_SHA = '5b2d7230370c441b81e1ff4c7b4c921a9a5f2ccef354eb5d50feab1943f6ab3e'
SOURCE = ROOT / '.cluster/solver-needs-source' / REVISION
CACHE = ROOT / '.cluster/solver-needs-downloads'


def fetch(url, path, expected):
    if path.exists():
        if digest(path.read_bytes()) != expected:
            raise ValueError('Cached download has wrong hash: ' + str(path))
        return path.read_bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={'User-Agent': 'solver-needs-research-pilot'})
    with urllib.request.urlopen(request, timeout=180) as response:
        data = response.read()
    if digest(data) != expected:
        raise ValueError('Downloaded archive has wrong hash: ' + url)
    temporary = path.with_suffix('.part')
    temporary.write_bytes(data)
    temporary.replace(path)
    return data


def extract(data, destination, keep=lambda name: True):
    """Strip the single archive root, reject path traversal and symlinks."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        roots = {PurePosixPath(n).parts[0] for n in archive.namelist()}
        if len(roots) != 1:
            raise ValueError('Expected one archive root')
        files = {}
        for info in archive.infolist():
            path = PurePosixPath(info.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in info.filename or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('Unsafe archive member: ' + info.filename)
            relative = PurePosixPath(*path.parts[1:])
            if info.is_dir() or str(relative) == '.' or not keep(str(relative)):
                continue
            target = destination.joinpath(*relative.parts)
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError('Archive member escapes destination')
            target.parent.mkdir(parents=True, exist_ok=True)
            contents = archive.read(info)
            target.write_bytes(contents)
            if info.external_attr >> 16 & 0o111:
                target.chmod(0o755)
            files[str(relative)] = digest(contents)
    return files


def source():
    receipt = SOURCE / 'download-receipt.json'
    if receipt.exists():
        for name, expected in read_json(receipt)['files'].items():
            if digest((SOURCE / name).read_bytes()) != expected:
                raise ValueError('Pinned upstream source changed: ' + name)
        return SOURCE
    data = fetch('https://codeload.github.com/knutsa/solver-needs/zip/' + REVISION,
                 CACHE / 'solver-needs.zip', SOURCE_SHA)
    def keep(name):
        return (name in ('README.md', 'LICENSE', 'LICENSE-DATA', 'data/corpora/README.md',
                         'data/essential/essential_verus_z3.json', 'data/benchmark_sets/verus_tasks.json',
                         'results/verus_z3/labels.json', 'results/verus_z3/probes.json')
                or name.startswith(('data/corpora/CF-V/', 'data/corpora/VB/', 'solver_needs/')))
    files = extract(data, SOURCE, keep)
    write_json(receipt, {'repository': 'https://github.com/knutsa/solver-needs', 'revision': REVISION,
                         'archive_sha256': SOURCE_SHA, 'files': files})
    return SOURCE


def tools(destination):
    name = f'verus-{VERUS_VERSION}-x86-linux.zip'
    data = fetch(f'https://github.com/verus-lang/verus/releases/download/release/{VERUS_VERSION}/{name}',
                 CACHE / name, VERUS_SHA)
    extract(data, destination)
    for name in ('verus', 'z3', 'rust_verify'):
        (destination / name).chmod(0o755)
    version = read_json(destination / 'version.json')['verus']
    if version['version'] != VERUS_VERSION or version['toolchain'] != '1.93.0-x86_64-unknown-linux-gnu':
        raise ValueError('Unexpected Verus distribution')
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('data', 'tools'))
    parser.add_argument('--destination', type=Path)
    args = parser.parse_args()
    if args.command == 'data':
        print(source())
    elif args.destination:
        print(tools(args.destination))
    else:
        parser.error('tools requires --destination')


if __name__ == '__main__':
    main()
