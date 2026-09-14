"""Generate release_manifest.sha256 for the FieldServiceBench tree.

Usage: python3 release.py
Covers source files + harbor task packages; excludes run artifacts
(runs/, harbor/jobs/, __pycache__, FINAL-RUN.md is included).
"""

import hashlib
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
EXCLUDE_DIRS = {"runs", "jobs", "__pycache__", ".git"}
MANIFEST = "release_manifest.sha256"


def main():
    entries = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)
        for fn in sorted(filenames):
            if fn == MANIFEST:
                continue
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, ROOT)
            with open(p, "rb") as f:
                entries.append((hashlib.sha256(f.read()).hexdigest(), rel))
    entries.sort(key=lambda e: e[1])
    out = os.path.join(ROOT, MANIFEST)
    with open(out, "w", encoding="utf-8") as f:
        for digest, rel in entries:
            f.write(f"{digest}  {rel}\n")
    print(f"wrote {out} ({len(entries)} files)")


if __name__ == "__main__":
    main()
