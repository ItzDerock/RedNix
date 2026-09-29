#!/usr/bin/env python3
"""Quick, read-only first look at a challenge file. Standard library only."""

import hashlib
import pathlib
import subprocess
import sys


def run(*args: str) -> str:
    try:
        result = subprocess.run(args, check=False, capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "(tool missing or timed out)"
    return (result.stdout or result.stderr).strip() or f"(exit {result.returncode})"


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: python3 {pathlib.Path(sys.argv[0]).name} FILE", file=sys.stderr)
        return 2
    path = pathlib.Path(sys.argv[1])
    if not path.is_file():
        print(f"not a file: {path}", file=sys.stderr)
        return 2

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)

    print(f"FILE   {path}")
    print(f"SIZE   {path.stat().st_size} bytes")
    print(f"SHA256 {digest.hexdigest()}")
    print("TYPE")
    print(run("file", str(path)))
    print("STRINGS (first 60)")
    try:
        strings = subprocess.run(
            ["strings", "-a", "-n", "6", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        print("\n".join(strings.stdout.splitlines()[:60]) or "(none found)")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("(strings missing or timed out)")
    print("\nNEXT: try exiftool FILE, binwalk FILE, and a format-specific parser.")
    print("Treat output as a lead. Do not run unknown files on the host.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
