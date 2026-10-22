"""Frozen static inventory of an upstream diff range for the RADAR workflow.

Reads a git repo locally, verifies ancestry, classifies every changed path and
writes an evidence directory (snapshot.json, numstat.z, raw-diff.z,
commit-subjects.txt, SHA256.json). No network, no checkout, no test execution.

Example:
  python3 tools/upstream/radar_capture.py \
    --repo /home/fukuro/git/Strata \
    --base 296b59d2f73c8f04a805df29c2fa97655adace78 \
    --tip  cbfd5b926b794b356195d3cb600191b0c3567540 \
    --fork-base 3ac2c3010c095db134efe9fdb3ae7b8589e59724 \
    --observed-before <sha-or-empty> \
    --out .git/strata-upstream-audit/<UTC-timestamp>
"""

import argparse
import collections
import datetime
import hashlib
import json
import os
import pathlib
import subprocess
import sys


def fail(msg):
    sys.exit(f"error: {msg}")


def category(path):
    if path in ("AGENTS.md", "CLAUDE.md") or path.startswith(
        (".github/", ".devin/", ".agents/", ".cursor/", ".windsurf/")
    ) or path in ("docs/AI_SETUP.md", "docs/INSTALL.md"):
        return "Agenten_CI"
    if path == "setup.py" or path.startswith(
        ("setup.", "START-", "UPDATE", "update.", "app/", "terminal/", "control/")
    ) or "Docker" in path or path.startswith(("docker", "packaging/")):
        return "Installer_App_Packaging"
    if path.startswith(("src/", "include/", "metal/", "sycl/")):
        if "CMakeLists" not in path and "/cmake/" not in path:
            return "Engine_Backends"
    if path.startswith("serve/"):
        return "Server_API"
    if "CMakeLists" in path or path.startswith(
        ("cmake/", "requirements", "third_party/", "wheelhouse/", "flake.")
    ):
        return "Build_Dependencies"
    if path.startswith(("models/", "packs/", "mtp/", "engine/", "data/")):
        return "Modelle_Artefakte"
    if path.startswith(("docs/", "tests/", "bench/", "tools/")) or path.endswith(
        (".md", ".txt")
    ):
        return "Doku_Tests_Tools"
    return "Weitere_einzeln_zu_pruefen"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", type=pathlib.Path, required=True)
    ap.add_argument("--base", required=True, help="freigegebene Baseline-SHA")
    ap.add_argument("--tip", required=True, help="beobachtete Upstream-SHA")
    ap.add_argument("--fork-base", required=True, help="geprüfter Fork-Commit")
    ap.add_argument("--observed-before", default="",
                    help="letzte Beobachtungs-SHA (leer beim ersten Lauf)")
    ap.add_argument("--previous-radar", default=None,
                    help="Pfad des letzten RADAR-Berichts (optional)")
    ap.add_argument("--out", type=pathlib.Path, required=True,
                    help="Evidenz-Verzeichnis (muss nicht existieren)")
    args = ap.parse_args()

    root = args.repo.resolve()
    env = dict(os.environ, GIT_NO_REPLACE_OBJECTS="1", GIT_TERMINAL_PROMPT="0")

    def git(*git_args):
        try:
            return subprocess.check_output(
                ["git", "--no-pager", "-c", "core.hooksPath=/dev/null", *git_args],
                cwd=root, env=env,
            )
        except subprocess.CalledProcessError as exc:
            fail(f"git {' '.join(git_args)} failed (rc={exc.returncode})")

    for label, sha in (("base", args.base), ("tip", args.tip),
                       ("fork_base", args.fork_base)):
        got = git("rev-parse", "--verify", sha + "^{commit}").strip().decode()
        if got != sha:
            fail(f"{label}: {sha} resolves to {got}")
    if git("rev-parse", "--is-shallow-repository").strip() != b"false":
        fail("shallow repository — vollständige Historie erforderlich")
    if subprocess.run(["git", "merge-base", "--is-ancestor", args.base,
                       args.tip], cwd=root).returncode != 0:
        fail(f"base {args.base} is not an ancestor of tip {args.tip}")
    if args.observed_before:
        if subprocess.run(["git", "merge-base", "--is-ancestor",
                           args.observed_before, args.tip],
                          cwd=root).returncode != 0:
            fail(f"observed_before {args.observed_before} not ancestor of tip "
                 "(non-forward history — stop, separate review required)")
    if subprocess.run(["git", "merge-base", "--is-ancestor", args.base,
                       args.fork_base], cwd=root).returncode != 0:
        fail(f"fork_base {args.fork_base} does not descend from base")

    if args.out.exists():
        fail(f"output dir already exists: {args.out} (idempotent by design)")
    args.out.mkdir(parents=True)

    records = git("diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                  "--name-status", "-z", args.base, args.tip).split(b"\0")
    if records.pop() != b"" or len(records) % 2 != 0:
        fail("unexpected --name-status -z record layout")
    files = []
    for pos in range(0, len(records), 2):
        status = records[pos].decode("ascii")
        path = os.fsdecode(records[pos + 1])
        files.append({"path": path, "change": status,
                      "category": category(path), "review": "OFFEN"})
    numstat = git("diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                  "--numstat", "-z", args.base, args.tip)
    added = removed = binaries = count = 0
    for row in numstat.split(b"\0"):
        if not row:
            continue
        parts = row.split(b"\t", 2)
        if len(parts) != 3:
            fail("unexpected --numstat row layout")
        a, d, _ = parts
        count += 1
        if a == b"-":
            binaries += 1
        else:
            added += int(a)
            removed += int(d)
    if count != len(files):
        fail(f"numstat rows {count} != name-status paths {len(files)}")
    commits = git("rev-list", args.base + ".." + args.tip).decode().splitlines()
    if len(commits) != int(git("rev-list", "--count",
                             args.base + ".." + args.tip)):
        fail("rev-list count mismatch")
    fetch_delta = 0
    if args.observed_before:
        fetch_delta = int(git("rev-list", "--count",
                              args.observed_before + ".." + args.tip))
    payload = {
        "captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "https://github.com/Niko1221/Strata.git",
        "baseline": args.base, "observed_before": args.observed_before or None,
        "observed_after": args.tip, "fork_base": args.fork_base,
        "previous_radar": args.previous_radar,
        "fetch_delta_commits": fetch_delta, "backlog_commits": len(commits),
        "changed_paths": len(files), "added_lines": added,
        "removed_lines": removed, "binary_numstat_paths": binaries,
        "categories": dict(sorted(collections.Counter(
            row["category"] for row in files).items())),
        "changes": dict(sorted(collections.Counter(
            row["change"] for row in files).items())),
        "files": files,
        "commits": [{"sha": sha, "review": "OFFEN"} for sha in commits],
        "clean_verdict": False,
    }
    (args.out / "snapshot.json").write_text(json.dumps(payload, indent=2) + "\n")
    (args.out / "numstat.z").write_bytes(numstat)
    (args.out / "raw-diff.z").write_bytes(git(
        "diff", "--no-ext-diff", "--no-textconv", "--no-renames",
        "--raw", "-z", args.base, args.tip))
    (args.out / "commit-subjects.txt").write_bytes(git(
        "log", "--format=%H %s", args.base + ".." + args.tip))
    self_copy = pathlib.Path(__file__).resolve()
    (args.out / "capture.py").write_bytes(self_copy.read_bytes())
    manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(args.out.iterdir())}
    (args.out / "SHA256.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: v for k, v in payload.items()
                      if k not in ("files", "commits")}, indent=2))
    print("evidence:", args.out)


if __name__ == "__main__":
    main()
