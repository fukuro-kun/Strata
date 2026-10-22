"""Refines the path categories of a captured radar snapshot in place.

Reads snapshot.json produced by radar_capture.py, applies the second-pass
rules (top-level installer apps, repo metadata, root-level tools) and writes
classification-v2.json next to it. Fails on unexpected input instead of
asserting, so a different run does not die on a hardcoded path count.

Example:
  python3 tools/upstream/radar_classify.py \
    --snapshot .git/strata-upstream-audit/<ts>/snapshot.json
"""

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path


TOP_INSTALLER_DIRS = {"apps", "strata_control", "strata_cli",
                      "integrations", "bin"}
REPO_METADATA = {".gitattributes", ".gitignore"}
ROOT_TOOLS = {"BENCH.bat", "bench.sh", "conftest.py"}


def fail(msg):
    sys.exit(f"error: {msg}")


def refine(path, current):
    if path.split("/")[0] in TOP_INSTALLER_DIRS or path == "strata.py":
        return "Installer_App_Packaging"
    if path in REPO_METADATA:
        return "Repo_Metadaten"
    if path in ROOT_TOOLS:
        return "Doku_Tests_Tools"
    return current


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", type=Path, required=True,
                    help="snapshot.json aus radar_capture.py")
    ap.add_argument("--out", type=Path, default=None,
                    help="Ausgabe-Datei (Standard: <snapshot-dir>/classification-v2.json)")
    args = ap.parse_args()

    source = args.snapshot
    if not source.is_file():
        fail(f"snapshot not found: {source}")
    data = json.loads(source.read_text())
    files = data.get("files")
    if not isinstance(files, list):
        fail("snapshot has no 'files' list")
    reclassified = []
    for entry in files:
        row = dict(entry)
        row["category"] = refine(row["path"], row["category"])
        reclassified.append(row)
    result = {
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "categories": dict(sorted(collections.Counter(
            row["category"] for row in reclassified).items())),
        "uncategorized": [row["path"] for row in reclassified
                          if row["category"] == "Weitere_einzeln_zu_pruefen"],
        "files": reclassified,
    }
    total = sum(result["categories"].values())
    if total != data.get("changed_paths"):
        fail(f"category total {total} != changed_paths "
             f"{data.get('changed_paths')}")
    out = args.out or (source.parent / "classification-v2.json")
    if out.exists():
        fail(f"output exists: {out} (refusing to overwrite)")
    with out.open("x") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k != "files"},
                     indent=2))


if __name__ == "__main__":
    main()
