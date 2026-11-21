#!/usr/bin/env python3
"""make_manifest.py — write the immutable build/model manifest for a deploy
state (P3).

Collects every hash that defines this deployment: fork commit + diff vs the
reviewed baseline, the pinned llama.cpp source, toolchain versions, wheel
hashes, engine binary hashes, and model/pack provenance. Output:
MANIFEST.json next to the staged artifacts.

  python3 tools/offline/make_manifest.py --out terminal/engine/MANIFEST.json
      [--model name=path_or_hash ...] [--baseline SHA]

  --verify FILE   check the checkout, staged binaries, BUILD.json, wheel bytes
                  and the venv's package metadata, files and Python binary
                  without executing it (exit 1 on drift). Sealed deployments
                  also bind config-selected model inputs. External runtime
                  libraries are not checked.

Fields: fork_sha, baseline_sha, fork_files[], llama_cpp{commit,pin_ok},
toolchain{gcc,cmake,ninja,nvcc,python}, deps{filename: sha256},
artifacts{file: {sha256,size}}, build{BUILD.json}, models{},
deploy{config{name,sha256},run_sh,model_inputs} (sealed deploy dirs only), created (UTC),
host.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import platform
import re
import stat
import subprocess
import sys
from datetime import datetime, timezone
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "296b59d2f73c8f04a805df29c2fa97655adace78"   # P0-reviewed pin

os.environ.setdefault("GIT_NO_LAZY_FETCH", "1")   # git commands must never lazy-fetch (partial clones)


def sha256_fd(fd: int) -> str:
    h = hashlib.sha256()
    with os.fdopen(fd, "rb") as f:
        before = os.fstat(f.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise OSError("not a regular file")
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
        after = os.fstat(f.fileno())
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise OSError("file changed while hashing")
    return h.hexdigest()


def sha256_file(p: Path) -> str:
    return sha256_fd(os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK))


MODEL_FLAGS = {
    "--pack", "--native", "--model", "--ple-gguf", "--native-dense-gguf",
    "--native-head-gguf", "--embd-gguf", "--expert-profile", "--draft-model",
    "--mtp", "--mtp-draft-vocab", "--control-vector", "--control-vector-scaled",
    "--tokens-file", "--spec-oracle", "--spec-follow",
}
GGUF_SHARD = re.compile(r"(.+)-([0-9]{5})-of-([0-9]{5})\.gguf")


def model_snapshot(cfg_file: Path, expected_config_sha: str) -> dict:
    """Bind path-selected inputs from the final staged config, not the caller's config."""
    fd = os.open(cfg_file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("deploy config is not a regular file")
        data = stream.read((1 << 20) + 1)
    if len(data) > 1 << 20 or hashlib.sha256(data).hexdigest() != expected_config_sha:
        raise ValueError("deploy config changed or is too large")
    cfg = json.loads(data)
    if not isinstance(cfg, dict):
        raise ValueError("deploy config is not an object")
    if cfg.get("split_fallback"):
        raise ValueError("split_fallback is not supported in sealed deployments")
    if cfg.get("images"):
        raise ValueError("image generation is not supported in sealed deployments")
    paths: set[Path] = set()

    def add(value: str) -> None:
        p = Path(value)
        if not p.is_absolute() or ".." in p.parts or p == Path(p.anchor):
            raise ValueError("model inputs must use absolute, non-root paths")
        paths.add(p)

    for key in ("args", "user_args"):
        args = cfg.get(key, [])
        if not isinstance(args, list) or any(not isinstance(arg, str) for arg in args):
            raise ValueError(f"deploy {key} must be an array of strings")
        for i, arg in enumerate(args):
            if arg not in MODEL_FLAGS:
                continue
            if i + 1 == len(args) or not args[i + 1] or args[i + 1].startswith("--"):
                raise ValueError(f"missing model input for {arg}")
            value = args[i + 1]
            if arg == "--mtp" and re.fullmatch(r"-?[0-9]+", value):
                continue
            if arg == "--control-vector-scaled":
                for item in value.split(","):
                    file, sep, scale = item.rpartition(":")
                    if not sep or not file or not scale:
                        raise ValueError("expected FILE:SCALE for --control-vector-scaled")
                    add(file)
            else:
                add(value)
    if cfg.get("tokenizer"):
        add(cfg["tokenizer"])
    vision = cfg.get("vision")
    if isinstance(vision, dict):
        for key in ("model", "mmproj"):
            if vision.get(key):
                add(vision[key])

    files: set[Path] = set()

    def walk(p: Path) -> None:
        mode = p.lstat().st_mode
        if stat.S_ISDIR(mode):
            children = sorted(p.iterdir())
            if not children:
                raise ValueError("empty model input directory")
            for child in children:
                walk(child)
        elif stat.S_ISREG(mode):
            files.add(p)
        else:
            raise ValueError("model input must be a regular file or directory, not a link")

    for path in sorted(paths):
        if any(parent.is_symlink() for parent in path.parents):
            raise ValueError("model input parents must not be symlinks")
        shard = GGUF_SHARD.fullmatch(path.name)
        if shard:
            prefix, index, count = shard.groups()
            if not 1 <= int(index) <= int(count) <= 1024:
                raise ValueError("invalid GGUF shard numbering")
            for i in range(1, int(count) + 1):
                walk(path.with_name(f"{prefix}-{i:05d}-of-{count}.gguf"))
        else:
            walk(path)
    return {str(p): {"size": p.stat().st_size, "sha256": sha256_file(p)} for p in sorted(files)}


def git_dirs() -> tuple[Path, Path]:
    """(gitdir, common dir) — resolves .git files (worktrees) and `commondir`."""
    marker = ROOT / ".git"
    try:
        if marker.is_dir() and not marker.is_symlink():
            gitdir = marker
        else:
            text = marker.read_text(encoding="ascii").strip()
            if not text.startswith("gitdir:"):
                raise OSError("not a gitdir pointer")
            gitdir = Path(text.split(":", 1)[1].strip())
            if not gitdir.is_absolute():
                gitdir = (ROOT / gitdir).resolve()
        common = gitdir
        commondir = gitdir / "commondir"
        if commondir.is_file() and not commondir.is_symlink():
            common = (gitdir / commondir.read_text(encoding="ascii").strip()).resolve()
    except (OSError, UnicodeError):
        sys.exit("ERROR: .git marker is unreadable")
    return gitdir, common


def is_backup(entry: Path) -> bool:
    """Config backups from reapply_required_args: <name>.bak-<8 digits>-<6 digits>[-n].
    Only a regular file may ride the exemption — a symlink or directory of
    that name is an unrecorded entry."""
    return (re.fullmatch(r".*\.bak-[0-9]+-[0-9]+(-[0-9]+)?", entry.name) is not None
            and entry.is_file() and not entry.is_symlink())


def file_stamp(p: Path):
    try:
        st = p.lstat()
    except OSError:
        return None
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def git_config_stamps() -> dict:
    gitdir, common = git_dirs()
    return {p: file_stamp(p) for p in (gitdir / "config", gitdir / "config.worktree", common / "config")}


def ensure_object_integrity() -> None:
    """Grafts/alternates rewrite parents or swap the object store — both are
    unreviewed inputs to merge-base/diff/rev-list provenance. Checked on
    every git call: a mid-process plant must not slip through."""
    gitdir, common = git_dirs()
    for p in (gitdir / "info" / "grafts", common / "info" / "grafts",
              common / "objects" / "info" / "alternates"):
        if os.path.lexists(p):
            sys.exit("ERROR: git grafts or alternates are not allowed")


def run(cmd: list[str]) -> str:
    if not cmd or cmd[0] != "git":
        sys.exit("ERROR: unsupported provenance command")
    args = ["/usr/bin/git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
            "-c", "core.attributesFile=/dev/null", "-c", "maintenance.auto=false", "-c", "gc.auto=0",
            "-c", "status.showUntrackedFiles=all", "-c", "status.ignoreSubmodules=none"]
    env = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LC_ALL": "C",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0",
           "GIT_NO_LAZY_FETCH": "1", "GIT_NO_REPLACE_OBJECTS": "1", "GIT_OPTIONAL_LOCKS": "0"}

    def invoke(arguments: list[str]) -> str:
        ensure_object_integrity()
        stamps = git_config_stamps()
        try:
            r = subprocess.run([*args, *arguments], capture_output=True, text=True, cwd=ROOT, env=env, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            sys.exit("ERROR: git provenance command could not be completed")
        if r.returncode != 0 or git_config_stamps() != stamps:
            sys.exit("ERROR: git provenance command failed")
        return r.stdout.strip()

    def config_names(scope: str) -> list[str]:
        names = invoke(["config", scope, "--no-includes", "--null", "--name-only", "--list"]).split("\0")
        lowered = [name.lower() for name in names if name]
        if any(name.startswith(("filter.", "include.", "includeif.")) for name in lowered):
            sys.exit("ERROR: git filters or config includes are not allowed")
        return lowered

    local = config_names("--local")
    if "extensions.worktreeconfig" in local:
        enabled = invoke(["config", "--local", "--no-includes", "--bool", "--get", "extensions.worktreeConfig"])
        if enabled == "true":
            config_names("--worktree")
    return invoke(cmd[1:])


def tool_ver(cmd: list[str], pat: str = r"[0-9]+\.[0-9]+[0-9.]*") -> str | None:
    try:
        binary = Path(cmd[0])
        if not binary.is_absolute():
            return None
        binary = binary.resolve(strict=True)
        if not binary.is_relative_to(Path("/usr")) or not binary.is_file() or not os.access(binary, os.X_OK):
            return None
        env = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LC_ALL": "C"}
        out = subprocess.run([str(binary), *cmd[1:]], capture_output=True, text=True, timeout=10, env=env)
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        return None
    m = re.search(pat, (out.stdout or "") + (out.stderr or ""))
    return (m.group(1) if m.groups() else m.group(0)) if m else None


def venv_tree_hash(root: Path, python_target: Path) -> str:
    h = hashlib.sha256(b"strata-venv-v1\0")

    def record(*parts: bytes):
        for part in parts:
            h.update(len(part).to_bytes(8, "big"))
            h.update(part)

    def descend(directory_fd: int, directory: Path):
        with os.scandir(directory_fd) as entries:
            names = sorted((entry.name for entry in entries), key=os.fsencode)
        for name in names:
            relative_path = directory / name
            relative = os.fsencode(str(relative_path))
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            mode = str(stat.S_IMODE(info.st_mode)).encode("ascii")
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(name, dir_fd=directory_fd)
                resolved = (root / relative_path).resolve(strict=True)
                external_python = relative_path.parent == Path("bin") and resolved == python_target
                if not resolved.is_relative_to(root) and not external_python:
                    raise ValueError("venv symlink leaves the venv")
                after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if (info.st_dev, info.st_ino, info.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_ctime_ns):
                    raise ValueError("venv symlink changed while hashing")
                record(b"link", relative, mode, os.fsencode(target))
            elif stat.S_ISDIR(info.st_mode):
                fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
                try:
                    current = os.fstat(fd)
                    if (info.st_dev, info.st_ino) != (current.st_dev, current.st_ino):
                        raise ValueError("venv directory changed while hashing")
                    record(b"dir", relative, mode)
                    descend(fd, relative_path)
                finally:
                    os.close(fd)
            elif stat.S_ISREG(info.st_mode):
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
                with os.fdopen(fd, "rb") as stream:
                    before = os.fstat(stream.fileno())
                    if not stat.S_ISREG(before.st_mode) or (info.st_dev, info.st_ino) != (before.st_dev, before.st_ino):
                        raise ValueError("venv entry changed type")
                    file_hash = hashlib.sha256()
                    for chunk in iter(lambda: stream.read(1 << 20), b""):
                        file_hash.update(chunk)
                    after = os.fstat(stream.fileno())
                if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    raise ValueError("venv file changed while hashing")
                record(b"file", relative, mode, str(before.st_size).encode("ascii"), file_hash.digest())
            else:
                raise ValueError("venv contains a special file")
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        descend(root_fd, Path())
    finally:
        os.close(root_fd)
    return h.hexdigest()


def read_regular_at(directory_fd: int, name: str, limit: int) -> bytes:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("metadata is not a bounded regular file")
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("metadata exceeds its size limit")
        return data


def read_repo_file(relative: tuple[str, ...], limit: int) -> bytes:
    with contextlib.ExitStack() as stack:
        directory_fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stack.callback(os.close, directory_fd)
        for component in relative[:-1]:
            directory_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
            stack.callback(os.close, directory_fd)
        return read_regular_at(directory_fd, relative[-1], limit)


def wheelhouse_snapshot() -> dict[str, str]:
    with contextlib.ExitStack() as stack:
        root_fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stack.callback(os.close, root_fd)
        wh_fd = os.open("wheelhouse", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        stack.callback(os.close, wh_fd)
        text = read_regular_at(wh_fd, "MANIFEST.sha256", 8 * 1024 * 1024).decode("ascii")
        deps = {}
        for line in text.splitlines():
            parts = line.split(None, 1)
            if len(parts) != 2:
                raise ValueError("invalid wheelhouse manifest")
            h, name = parts[0], parts[1].lstrip("*").strip()
            if (not re.fullmatch(r"[0-9a-f]{64}", h) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", name)
                    or not name.endswith((".whl", ".tar.gz", ".zip")) or name in deps):
                raise ValueError("invalid wheelhouse entry")
            deps[name] = h
        if not deps:
            raise ValueError("wheelhouse manifest is empty")
        with os.scandir(wh_fd) as entries:
            present = {entry.name for entry in entries if entry.name.endswith((".whl", ".tar.gz", ".zip"))}
        if present != deps.keys():
            raise ValueError("wheelhouse files do not match the manifest")
        for name, expected in deps.items():
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=wh_fd)
            if sha256_fd(fd) != expected:
                raise ValueError("wheelhouse hash mismatch")
        return deps


def source_pin() -> str:
    """The pinned llama.cpp commit, read from the COMMITTED terminal/setup.py —
    not the worktree file, so a post-status swap cannot change what is anchored."""
    text = run(["git", "show", "HEAD:terminal/setup.py"])
    pins = re.findall(r'(?m)^LLAMA_CPP_COMMIT[ \t]*=[ \t]*"([0-9a-f]{40})"[ \t]*(?:\#.*)?$', text)
    if len(pins) != 1:
        raise ValueError("source pin is missing or ambiguous")
    return pins[0]


def vendored_pin() -> str:
    """Der gepinnte Commit des vendored ggml-Baums, gelesen aus
    engine/third_party/strata-ggml/UPSTREAM.md."""
    data = read_repo_file(("engine", "third_party", "strata-ggml", "UPSTREAM.md"), 16384).decode("utf-8")
    pins = re.findall(r"(?m)^pin:[ \t]*([0-9a-f]{40})[ \t]*$", data)
    if len(pins) != 1:
        raise ValueError("vendored pin is missing or ambiguous")
    return pins[0]


def venv_snapshot(python: Path) -> dict:
    root = python.parent.parent
    if root.is_symlink() or not root.is_dir():
        raise ValueError("venv root is missing or is a symlink")
    root = root.resolve(strict=True)
    python = root / "bin" / "python"
    python_target = python.resolve(strict=True)
    trusted_bins = (Path("/usr/bin").resolve(), Path("/usr/local/bin").resolve())
    if (not python_target.is_file()
            or not (python_target.is_relative_to(root) or any(python_target.is_relative_to(p) for p in trusted_bins))):
        raise ValueError("venv Python is not a regular file")
    with contextlib.ExitStack() as stack:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stack.callback(os.close, root_fd)
        values = {}
        for line in read_regular_at(root_fd, "pyvenv.cfg", 65536).decode("utf-8").splitlines():
            key, sep, value = line.partition("=")
            key = key.strip().lower()
            if not sep or not key or key in values:
                raise ValueError("venv configuration is malformed")
            values[key] = value.strip()
        version = values.get("version", "")
        match = re.fullmatch(r"([0-9]+)\.([0-9]+)\.[0-9]+[A-Za-z0-9.+-]*", version)
        if not match or values.get("include-system-site-packages", "").lower() != "false":
            raise ValueError("venv Python version or site-packages policy is invalid")
        site_fd = root_fd
        for component in ("lib", f"python{match.group(1)}.{match.group(2)}", "site-packages"):
            site_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=site_fd)
            stack.callback(os.close, site_fd)
        with os.scandir(site_fd) as entries:
            dist_names = sorted(entry.name for entry in entries)
        packages, names = [], set()
        for dist_name in dist_names:
            if dist_name.endswith((".egg-info", ".egg-link")):
                raise ValueError("legacy or editable packages are not supported")
            if not dist_name.endswith(".dist-info"):
                continue
            dist_fd = os.open(dist_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=site_fd)
            try:
                try:
                    os.stat("direct_url.json", dir_fd=dist_fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise ValueError("direct URL packages are not supported")
                data = read_regular_at(dist_fd, "METADATA", 2 * 1024 * 1024)
            finally:
                os.close(dist_fd)
            package = BytesParser().parsebytes(data, headersonly=True)
            name, package_version = package.get("Name"), package.get("Version")
            if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name)
                    or not isinstance(package_version, str)
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.!+_-]*", package_version)):
                raise ValueError("package name or version is invalid")
            canonical = re.sub(r"[-_.]+", "-", name).lower()
            if canonical in names:
                raise ValueError("duplicate package metadata")
            names.add(canonical)
            packages.append(f"{name}=={package_version}")
    if not packages:
        raise ValueError("venv contains no package metadata")
    packages.sort()
    return {"python": version, "pip_freeze_sha256": hashlib.sha256("\n".join(packages).encode()).hexdigest(),
            "pip_freeze_count": len(packages), "python_executable_sha256": sha256_file(python_target),
            "tree_sha256": venv_tree_hash(root, python_target), "packages": packages}


# Packages every venv carries without a requirements pin (venv seeding, not supply chain).
AUTO_PACKAGES = {"pip", "setuptools", "wheel"}
REQ_FILES = ("requirements.txt", "requirements-build.txt")


def canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def declared_packages(python_version: str) -> dict[str, list[str]]:
    """Die Menge `name==version`, die requirements.txt, requirements-build.txt und die CUDA-Listen in
    setup.py fuer diese Python-Version unter Linux deklarieren — gegen was das venv gebaut worden sein
    soll (Provenienz), nicht nur was darin liegt (Zustand). Marker werden ausgewertet: `python_version`
    gegen die venv-Version, `sys_platform == "win32"` ist unter Linux inaktiv, andere Marker schlagen
    fehl statt geraten zu werden."""
    pyver = tuple(int(x) for x in python_version.split(".")[:2])

    def marker_ok(marker: str) -> bool:
        m = re.fullmatch(r"\s*(python_version|sys_platform)\s*(==|!=|>=|<=|>|<)\s*\"([0-9.]+|[A-Za-z0-9_]+)\"\s*",
                         marker)
        if not m:
            raise ValueError(f"unsupported requirement marker: {marker!r}")
        var, op, raw = m.group(1), m.group(2), m.group(3)
        val = pyver if var == "python_version" else "linux"
        want = tuple(int(x) for x in raw.split(".")) if var == "python_version" else raw
        return {"==": val == want, "!=": val != want, ">=": val >= want,
                "<=": val <= want, ">": val > want, "<": val < want}[op]

    pins = set()
    files = {}
    for rel in REQ_FILES:
        data = read_repo_file(("terminal", rel), 256 * 1024)
        files[rel] = hashlib.sha256(data).hexdigest()
        for line in data.decode("utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            spec, _, marker = line.partition(";")
            if marker.strip() and not marker_ok(marker.strip()):
                continue
            pin = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([A-Za-z0-9][A-Za-z0-9.!+_-]*)",
                               spec.strip())
            if not pin:
                raise ValueError(f"unpinned or unsupported requirement line: {line!r}")
            pins.add(f"{pin.group(1)}=={pin.group(2)}")
    setup = read_repo_file(("terminal", "setup.py"), 4 * 1024 * 1024).decode("utf-8")
    cuda = {}
    for var, tag in (("CUDA12_WHEELS", "12"), ("CUDA_WHEELS", "13")):
        block = re.search(rf"{var}\s*=\s*\[([^\]]+)\]", setup)
        if not block:
            raise ValueError(f"{var} not found in setup.py")
        cuda[tag] = set(re.findall(r'"([^"]+)"', block.group(1)))
    return {"pins": pins, "files": files, "cuda": cuda}


def env_attestation(packages: list[str], python_version: str) -> dict:
    """Provenienz der venv: sie muss GENAU die Pakete enthalten, die requirements.txt,
    requirements-build.txt und die passende setup.py-CUDA-Liste deklarieren (plus das
    Venv-Seed-Trio). Ein aus fremden Wheels gebautes venv zeigt sich als `undeclared`,
    ein fehlender Pin als `missing`, eine falsche Version als `version_mismatch` —
    jeweils fail-closed, weil dann Zustand und Herkunft auseinanderlaufen."""
    decl = declared_packages(python_version)
    freeze = {canonical_name(p.split("==", 1)[0]): p for p in packages}
    if len(freeze) != len(packages):
        raise ValueError("duplicate package names in venv freeze")
    if canonical_name("nvidia-cublas-cu12") in freeze:
        variant = "12"
    elif canonical_name("nvidia-cublas") in freeze:
        variant = "13"
    else:
        variant = "none"
    expected = {canonical_name(p.split("==", 1)[0]): p for p in decl["pins"]}
    if variant != "none":
        expected.update({canonical_name(p.split("==", 1)[0]): p for p in decl["cuda"][variant]})
    undeclared = sorted(freeze[k] for k in freeze.keys() - expected.keys() - AUTO_PACKAGES)
    missing = sorted(expected[k] for k in expected.keys() - freeze.keys())
    mismatch = sorted(f"{freeze[k]} (declared {expected[k]})" for k in expected.keys() & freeze.keys()
                      if freeze[k].split("==", 1)[1] != expected[k].split("==", 1)[1])
    problems = (f"undeclared {undeclared}" if undeclared else "")
    if missing:
        problems += f" missing {missing}"
    if mismatch:
        problems += f" version_mismatch {mismatch}"
    if problems:
        raise ValueError("venv does not match declared requirements:" + problems)
    return {"requirements_sha256": decl["files"], "cuda_wheels": variant,
            "declared_pins_sha256": hashlib.sha256(
                "\n".join(sorted(expected.values())).encode()).hexdigest()}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", help="output path (default <repo>/terminal/engine/MANIFEST.json)")
    p.add_argument("--model", action="append", default=[],
                   help="name=path → hash the file; name=hash → record a pre-verified sha256")
    p.add_argument("--baseline", default=BASELINE, help="reviewed baseline SHA (default: P0 pin)")
    p.add_argument("--verify", metavar="MANIFEST", help="verify an existing manifest instead of writing one")
    p.add_argument("--deploy-dir", type=Path,
                   help="seal mode: artifacts, config and run.sh are hashed from this deploy dir")
    p.add_argument("--config", help="staged config file name inside --deploy-dir (required with it)")
    p.add_argument("--print-head-sha", action="store_true",
                   help="print the hardened git HEAD sha and exit")
    a = p.parse_args()

    if a.print_head_sha:
        head = run(["git", "rev-parse", "HEAD"])
        if not re.fullmatch(r"[0-9a-f]{40}", head):
            sys.exit("ERROR: git rev-parse HEAD failed — not a checkout?")
        print(head)
        return 0
    if a.verify:
        return verify(Path(a.verify))
    if not re.fullmatch(r"[0-9a-f]{40}", a.baseline):
        sys.exit("ERROR: baseline must be a full commit SHA")
    deploy_dir = Path(a.deploy_dir) if a.deploy_dir else None
    if deploy_dir and (deploy_dir.is_symlink() or not deploy_dir.is_dir()):
        sys.exit("ERROR: --deploy-dir must be an existing directory")
    deploy_dir = deploy_dir.resolve() if deploy_dir else None
    if bool(deploy_dir) != bool(a.config):
        sys.exit("ERROR: --deploy-dir and --config must be given together")
    if a.config and (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.json", a.config)
                     or a.config in {"MANIFEST.json", "BUILD.json"}):
        sys.exit("ERROR: --config must be a plain staged *.json file name")

    m: dict = {"schema": 2, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "host": platform.node()}

    # --- source state ---
    head = run(["git", "rev-parse", "HEAD"])
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        sys.exit("ERROR: git rev-parse HEAD failed — not a checkout?")
    m["fork_sha"] = head
    m["baseline_sha"] = a.baseline
    dirty = run(["git", "status", "--porcelain"])
    if dirty:
        sys.exit("ERROR: working tree is dirty — commit first, manifests describe committed state\n" + dirty)
    # fork divergence vs the reviewed baseline = the "applied patches" list
    run(["git", "merge-base", "--is-ancestor", a.baseline, "HEAD"])
    diff = run(["git", "diff", "--no-ext-diff", "--no-textconv", "--name-only", a.baseline, "HEAD"])
    m["fork_files"] = [f for f in diff.splitlines() if f]
    m["fork_commits"] = [c for c in run(["git", "rev-list", "--reverse", f"{a.baseline}..HEAD"]).splitlines() if c] \
        if a.baseline else []

    # --- llama.cpp pin ---
    try:
        commit = source_pin()
        pin = vendored_pin()
    except (OSError, UnicodeError, ValueError):
        sys.exit("ERROR: llama.cpp pin proof missing or malformed")
    m["llama_cpp"] = {"commit": commit, "pin_file": pin, "pin_ok": pin == commit}
    if pin != commit:
        sys.exit("ERROR: llama.cpp pin proof differs from terminal/setup.py")

    # --- toolchain ---
    # BUILD.json is an input to attest, not authority to execute tools.
    artifact_root = deploy_dir if deploy_dir else ROOT / "terminal" / "engine"
    build_json = {}
    bj_path = artifact_root / "BUILD.json"
    if bj_path.exists():
        try:
            build_json = json.loads(bj_path.read_text())
        except Exception:
            build_json = {}
    m["toolchain"] = {
        "python": platform.python_version(),
        "gcc": tool_ver(["/usr/bin/gcc", "--version"], r"gcc \S+ ([0-9.]+)")
               or tool_ver(["/usr/bin/gcc", "-dumpfullversion"]),
        "cmake": tool_ver(["/usr/bin/cmake", "--version"], r"version ([0-9.]+)"),
        "ninja": tool_ver(["/usr/bin/ninja", "--version"], r"[0-9.]+"),
        "nvcc": build_json.get("cuda_compiler_version"),
        "nvcc_path": build_json.get("cuda_compiler"),
    }

    # --- deps (wheelhouse manifest) ---
    try:
        deps = wheelhouse_snapshot()
    except (OSError, UnicodeError, ValueError):
        sys.exit("ERROR: wheelhouse verification failed")
    m["deps"] = deps

    # --- venv state (shared, not versioned — record what it is right now) ---
    vpy = ROOT / ".venv-offline" / "bin" / "python"
    venv = {"path": str(ROOT / ".venv-offline")}
    if vpy.exists():
        try:
            venv.update(venv_snapshot(vpy))
            m["toolchain"]["python"] = venv["python"]
        except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
            sys.exit(f"ERROR: offline venv inspection failed ({type(exc).__name__})")
    else:
        sys.exit("ERROR: offline venv is missing")
    try:
        m["env"] = env_attestation(venv["packages"], venv["python"])
    except ValueError as exc:
        sys.exit(f"ERROR: env provenance failed — {exc}")
    m["venv"] = venv

    # --- artifacts ---
    artifacts = {}
    for name in ("strata", "strata-vision"):
        f = artifact_root / name
        if f.exists():
            artifacts[name] = {"sha256": sha256_file(f), "size": f.stat().st_size}
    if not artifacts:
        sys.exit("ERROR: no terminal/engine/ artifacts — run tools/offline/build_engine.sh first")
    if deploy_dir and ("strata" not in artifacts
                       or not os.access(artifact_root / "strata", os.X_OK)):
        sys.exit("ERROR: deploy dir has no executable strata engine")
    m["artifacts"] = artifacts
    m["build"] = build_json if build_json else None
    if m["build"] is None:
        sys.exit("ERROR: BUILD.json missing — build stamp required (build_engine.sh writes it)")

    if deploy_dir:
        # Seal the deploy dir: every launch-relevant file is attested, and
        # nothing unrecorded may sit next to it (config backups made by
        # reapply_required_args are the only sanctioned extras).
        cfg_file = deploy_dir / a.config
        run_sh = deploy_dir / "run.sh"
        if cfg_file.is_symlink() or not cfg_file.is_file():
            sys.exit("ERROR: staged config missing in deploy dir")
        if run_sh.is_symlink() or not run_sh.is_file():
            sys.exit("ERROR: staged run.sh missing in deploy dir")
        allowed = set(artifacts) | {"BUILD.json", "run.sh", a.config, "MANIFEST.json"}
        extras = [entry.name for entry in deploy_dir.iterdir()
                  if entry.name not in allowed and not is_backup(entry)]
        if extras:
            sys.exit("ERROR: unrecorded files in deploy dir: " + ", ".join(sorted(extras)))
        try:
            m["deploy"] = {"config": {"name": a.config, "sha256": sha256_file(cfg_file)},
                           "run_sh": sha256_file(run_sh)}
            m["deploy"]["model_inputs"] = model_snapshot(cfg_file, m["deploy"]["config"]["sha256"])
        except (OSError, ValueError, TypeError) as exc:
            sys.exit(f"ERROR: unable to seal staged config, launcher or model inputs: {exc}")

    # --- models ---
    models = {}
    for spec in a.model:
        if "=" not in spec:
            sys.exit(f"ERROR: --model expects name=path_or_sha256, got {spec!r}")
        name, val = spec.split("=", 1)
        path = ROOT / val
        p2 = Path(val)
        cand = p2 if p2.is_absolute() else path
        if cand.exists() and cand.is_file():
            models[name] = {"sha256": sha256_file(cand), "size": cand.stat().st_size,
                            "path": str(cand), "hashed": "now"}
        elif re.fullmatch(r"[0-9a-f]{64}", val):
            models[name] = {"sha256": val, "hashed": "pre-verified"}
        else:
            sys.exit(f"ERROR: --model {name}: neither an existing file nor a sha256 ({val!r})")
    m["models"] = models

    out = Path(a.out or ROOT / "terminal" / "engine" / "MANIFEST.json")
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(m, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, out)
    print(f"wrote {out}")
    print(json.dumps({k: m[k] for k in ("fork_sha", "baseline_sha", "llama_cpp", "toolchain")}, indent=1))
    print(f"artifacts: {list(artifacts)}, deps: {len(deps)}, models: {list(models)}, fork_files: {len(m['fork_files'])}")
    return 0


def verify(path: Path) -> int:
    try:
        m = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        print("MANIFEST VERIFY FAILED: manifest cannot be read")
        return 1
    if not isinstance(m, dict):
        print("MANIFEST VERIFY FAILED: manifest is not an object")
        return 1
    base = path.parent
    bad = []

    def matches(value, pattern):
        return isinstance(value, str) and re.fullmatch(pattern, value) is not None

    if type(m.get("schema")) is not int or m["schema"] != 2:
        bad.append("unsupported or missing schema")
    if not matches(m.get("fork_sha"), r"[0-9a-f]{40}"):
        bad.append("missing fork_sha")
    if not matches(m.get("baseline_sha"), r"[0-9a-f]{40}"):
        bad.append("missing baseline_sha")
    if (not isinstance(m.get("fork_files"), list)
            or not all(isinstance(name, str) for name in m["fork_files"])):
        bad.append("missing or invalid fork_files")
    if (not isinstance(m.get("fork_commits"), list)
            or not all(matches(commit, r"[0-9a-f]{40}") for commit in m["fork_commits"])):
        bad.append("missing or invalid fork_commits")
    artifacts = m.get("artifacts")
    allowed_artifacts = {"strata", "strata-vision"}
    if not isinstance(artifacts, dict) or "strata" not in artifacts:
        bad.append("missing engine artifacts")
    else:
        for name, rec in artifacts.items():
            if (name not in allowed_artifacts or not isinstance(rec, dict)
                    or not matches(rec.get("sha256"), r"[0-9a-f]{64}")
                    or type(rec.get("size")) is not int or rec["size"] <= 0):
                bad.append("invalid artifact entry")
    deps = m.get("deps")
    if not isinstance(deps, dict) or not deps:
        bad.append("missing dependency hashes")
    else:
        for name, value in deps.items():
            if not matches(name, r"[A-Za-z0-9][A-Za-z0-9._+-]*") or not matches(value, r"[0-9a-f]{64}"):
                bad.append("invalid dependency entry")
    pin = m.get("llama_cpp")
    if (not isinstance(pin, dict) or not matches(pin.get("commit"), r"[0-9a-f]{40}")
            or pin.get("pin_file") != pin.get("commit") or pin.get("pin_ok") is not True):
        bad.append("missing or invalid llama_cpp pin")
    venv = m.get("venv")
    if (not isinstance(venv, dict) or not isinstance(venv.get("path"), str)
            or not isinstance(venv.get("python"), str) or not venv["python"]
            or not matches(venv.get("pip_freeze_sha256"), r"[0-9a-f]{64}")
            or type(venv.get("pip_freeze_count")) is not int or venv["pip_freeze_count"] <= 0
            or not matches(venv.get("python_executable_sha256"), r"[0-9a-f]{64}")
            or not matches(venv.get("tree_sha256"), r"[0-9a-f]{64}")):
        bad.append("missing or invalid venv state")
    if not isinstance(m.get("build"), dict) or not m["build"]:
        bad.append("missing build metadata")
    if bad:
        print("MANIFEST VERIFY FAILED:", ", ".join(bad))
        return 1

    # Artifacts must sit NEXT TO the manifest (deploy dir or engine/) — a
    # missing one is drift, not a reason to look elsewhere (that would pass
    # a partial deploy dir because the repo copy has the same hash).
    for name, rec in artifacts.items():
        f = base / name
        try:
            ok = (not f.is_symlink() and f.is_file() and f.stat().st_size == rec["size"]
                  and os.access(f, os.X_OK) and sha256_file(f) == rec["sha256"])
        except OSError:
            ok = False
        if not ok:
            bad.append(f"artifact {name}")
    for name in allowed_artifacts - artifacts.keys():
        f = base / name
        if f.exists() or f.is_symlink():
            bad.append(f"unrecorded artifact {name}")
    build_file = base / "BUILD.json"
    try:
        if build_file.is_symlink() or json.loads(build_file.read_text(encoding="utf-8")) != m["build"]:
            bad.append("BUILD.json drifted")
    except (OSError, UnicodeError, json.JSONDecodeError):
        bad.append("BUILD.json missing or unreadable")

    # Launch files: a deploy dir must have its run.sh and run config attested
    # in `deploy`, and nothing else may sit next to them. A manifest without
    # `deploy` is only acceptable where no launch files exist (engine/).
    deploy = m.get("deploy")
    has_run_sh = (base / "run.sh").is_symlink() or (base / "run.sh").exists()
    staged_jsons = {entry.name for entry in base.iterdir()
                    if entry.name.endswith(".json")
                    and entry.name not in {"BUILD.json", path.name}
                    and not is_backup(entry)}
    if deploy is None:
        if has_run_sh or staged_jsons:
            bad.append("deploy launch files are not recorded")
    else:
        cfg = deploy.get("config") if isinstance(deploy, dict) else None
        name = cfg.get("name") if isinstance(cfg, dict) else None
        if (not isinstance(deploy, dict) or not isinstance(cfg, dict)
                or not matches(name, r"[A-Za-z0-9][A-Za-z0-9._-]*\.json")
                or name in {"BUILD.json", path.name}
                or not matches(cfg.get("sha256"), r"[0-9a-f]{64}")
                or not matches(deploy.get("run_sh"), r"[0-9a-f]{64}")
                or not isinstance(deploy.get("model_inputs"), dict)
                or set(deploy) != {"config", "run_sh", "model_inputs"}):
            bad.append("invalid deploy section")
        else:
            for rel, h in ((name, cfg["sha256"]), ("run.sh", deploy["run_sh"])):
                f = base / rel
                try:
                    good = not f.is_symlink() and f.is_file() and sha256_file(f) == h
                except OSError:
                    good = False
                if not good:
                    bad.append(f"deploy file {rel}")
            if not bad:
                try:
                    if model_snapshot(base / name, cfg["sha256"]) != deploy["model_inputs"]:
                        bad.append("model inputs drifted")
                except (OSError, ValueError, TypeError):
                    bad.append("model inputs missing, invalid or unreadable")
            if staged_jsons != {name}:
                bad.append("unrecorded config files in deploy dir")
            allowed = set(artifacts) | {"BUILD.json", "run.sh", path.name, name}
            for entry in base.iterdir():
                if entry.name not in allowed and not is_backup(entry):
                    bad.append(f"unrecorded deploy entry {entry.name}")

    try:
        head = run(["git", "rev-parse", "HEAD"])
        if head != m["fork_sha"]:
            bad.append(f"fork_sha (manifest {m['fork_sha']}, checkout {head})")
        if run(["git", "status", "--porcelain"]):
            bad.append("working tree dirty (serve/ runs from the checkout)")
        run(["git", "merge-base", "--is-ancestor", m["baseline_sha"], "HEAD"])
        files = run(["git", "diff", "--no-ext-diff", "--no-textconv", "--name-only",
                     m["baseline_sha"], "HEAD"]).splitlines()
        commits = run(["git", "rev-list", "--reverse", f"{m['baseline_sha']}..HEAD"]).splitlines()
        if files != m["fork_files"] or commits != m["fork_commits"]:
            bad.append("fork provenance drifted")
    except SystemExit:
        bad.append("git provenance unavailable")
    try:
        local_pin = vendored_pin()
        if local_pin != pin["commit"] or source_pin() != pin["commit"]:
            bad.append("llama_cpp vendored pin mismatch/missing now")
    except (OSError, UnicodeError, ValueError, SystemExit):
        bad.append("llama_cpp vendored pin mismatch/missing now")

    try:
        have = wheelhouse_snapshot()
    except (OSError, UnicodeError, ValueError):
        have = {}
        bad.append("wheelhouse files or MANIFEST.sha256 invalid")
    if have != deps:
        bad.append("wheelhouse MANIFEST.sha256 entries drifted")

    venv_root = ROOT / ".venv-offline"
    vpy = venv_root / "bin" / "python"
    if (venv_root.is_symlink() or not venv_root.is_dir()
            or Path(venv["path"]).absolute() != venv_root.absolute() or not vpy.exists()):
        bad.append("venv missing or path drifted")
    else:
        try:
            current = venv_snapshot(vpy)
            if current["python"] != venv["python"]:
                bad.append("venv Python version drifted")
            if (current["pip_freeze_sha256"] != venv["pip_freeze_sha256"]
                    or current["pip_freeze_count"] != venv["pip_freeze_count"]):
                bad.append("venv pip_freeze drifted (venv rebuilt since deploy)")
            if current["python_executable_sha256"] != venv["python_executable_sha256"]:
                bad.append("venv Python executable drifted")
            if current["tree_sha256"] != venv["tree_sha256"]:
                bad.append("venv files drifted")
            env = m.get("env")
            if env is None:
                print("note: manifest has no env section — venv provenance not attested")
            elif (not isinstance(env, dict)
                    or set(env) != {"requirements_sha256", "cuda_wheels", "declared_pins_sha256"}
                    or env.get("cuda_wheels") not in {"12", "13", "none"}
                    or not isinstance(env.get("requirements_sha256"), dict)
                    or set(env["requirements_sha256"]) != set(REQ_FILES)
                    or not all(matches(v, r"[0-9a-f]{64}") for v in env["requirements_sha256"].values())
                    or not matches(env.get("declared_pins_sha256"), r"[0-9a-f]{64}")):
                bad.append("invalid env section")
            else:
                try:
                    if env_attestation(current["packages"], current["python"]) != env:
                        bad.append("env provenance drifted (venv or requirements differ from declared inputs)")
                except (OSError, UnicodeError, ValueError, RuntimeError):
                    bad.append("env provenance check failed")
        except (OSError, UnicodeError, ValueError, RuntimeError):
            bad.append("venv inspection failed")
    if bad:
        print("MANIFEST VERIFY FAILED:", ", ".join(bad))
        return 1
    print(f"manifest verified: fork_sha {m['fork_sha'][:8]}, {len(artifacts)} artifacts, "
          f"{len(deps)} wheel files and venv bytes; external runtime libraries not checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
