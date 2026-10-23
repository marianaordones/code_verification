"""Install the same Z3 selected by the pinned Verus checkout, without unzip."""
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

VERSION = "4.12.5"
PACKAGE = f"z3-{VERSION}-x64-glibc-2.31"
URL = f"https://github.com/Z3Prover/z3/releases/download/z3-{VERSION}/{PACKAGE}.zip"


def unpack_binary(archive, destination):
    destination = Path(destination)
    with zipfile.ZipFile(archive) as bundle:
        # Read one exact entry; do not extract archive paths into the filesystem.
        binary = bundle.read(f"{PACKAGE}/bin/z3")
    temporary = destination.with_name(destination.name + ".partial")
    temporary.write_bytes(binary)
    temporary.chmod(0o755)
    temporary.replace(destination)


def main():
    destination = Path(sys.argv[1]).resolve()
    print(f"Downloading Z3 {VERSION}: {URL}", flush=True)
    with tempfile.TemporaryDirectory() as directory:
        archive = Path(directory) / "z3.zip"
        with urllib.request.urlopen(URL, timeout=60) as response, archive.open("wb") as output:
            import shutil
            shutil.copyfileobj(response, output)
        unpack_binary(archive, destination)
    result = subprocess.run([str(destination), "--version"], capture_output=True, text=True, check=True)
    if f"Z3 version {VERSION}" not in result.stdout:
        raise RuntimeError(f"Unexpected Z3 version: {result.stdout} {result.stderr}")
    print(result.stdout.strip(), flush=True)


if __name__ == "__main__":
    main()
