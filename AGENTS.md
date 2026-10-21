# AGENTS.md

Strata runs the Qwen3.8-Flash-Next mixture-of-experts model (and its Coder, Swift 1.5 and Unsloth variants) on a
normal PC: one NVIDIA or AMD graphics card plus system RAM, on Windows or Linux. It has a C++/CUDA/HIP engine
(`src/`, `include/`), a Python server with an OpenAI- and Anthropic-compatible API and a web app (`serve/`), and a
one-click installer (`setup.py`, started by `START-HERE.bat` / `setup.sh`).

## Installing Strata for a user

Follow **[docs/AI_SETUP.md](docs/AI_SETUP.md)**: check the PC, pick the model by RAM, run setup non-interactively,
start and verify the server, and connect the user's apps. Never expose the server beyond `127.0.0.1` without
`--api-key`. As an alternative to shell commands, Strata's MCP server ([docs/MCP_SERVER.md](docs/MCP_SERVER.md))
offers the same steps as tools.

## Working on the code

- How the engine works, every measured number, the API and all settings: [docs/DETAILS.md](docs/DETAILS.md) and
  the [paper](docs/paper/Strata-Paper.pdf).
- AMD (HIP) build and validation: [docs/AMD_HIP.md](docs/AMD_HIP.md); multi-GPU: [docs/MULTI_GPU.md](docs/MULTI_GPU.md).
- Setup's own tests run without a GPU or downloads: `python tools/test_setup_<name>.py` (for example
  `tools/test_setup_amd.py`, `tools/test_setup_choices.py`).
- Keep the docs' style: plain words, measured numbers with what they were measured on, no claims without a
  measurement.

## Contributing a change or report

- Search the open issues and pull requests first, and add to a thread that already covers your point.
- Open an issue with the form that fits (bug report, feature request or question).
- One change per pull request. Say what it changes and what it leaves alone.
- A new feature is opt-in, and the default path stays byte-identical to the last release. Say how you checked.
- Build every backend a file touches (CUDA, HIP, SYCL) before asking for review.
- Change a default only where you measured it faster, and show the numbers with what they were measured on.
- A report from hardware the maintainers do not have is welcome. Follow
  [docs/COMMUNITY_BENCHMARKS.md](docs/COMMUNITY_BENCHMARKS.md), compare against a same-day run of the build you are
  testing, and say what you did not test.
- Open test requests and the hardware that is wanted are listed in [docs/TEST_REQUESTS.md](docs/TEST_REQUESTS.md).

## Fork-Workflow (dieser Fork — übersteuert die Installer-Anleitung oben)

- **Nicht** `docs/AI_SETUP.md`, `setup.py`, `setup.sh` oder `START-HERE.bat` ausführen: kein
  Installer-Lauf, kein Auto-Download, kein Server-Start aus dieser Doku heraus.
- Kanonischer Plan: **[ROADMAP.md](ROADMAP.md)** (deutsch, Phasen P0–P5). Aktueller Stand:
  nur Vorbereitung und Dokumentation — Implementierung braucht separate Freigabe.
- Remotes: `origin` = dieser Fork auf dem Forgejo im LAN (`europa`, kanonisch);
  `github` = fukuro-kun/Strata als reiner Mirror (serverseitiger Push-Mirror
  auf europa spiegelt jeden Push — nichts direkt auf `github` pushen);
  `upstream` = Niko1221/Strata als reine Lese-Referenz (Push deaktiviert —
  Sync nur über den P4-Prozess). **Push-Gate:** unreviewter Upstream-Stand
  wird niemals auf einen `origin`-Branch gepusht — der Mirror macht ihn
  sofort öffentlich; Regeln in `docs/UPSTREAM_SYNC.md` §Push-Gate.
- Private Umgebungsdetails (Pfade, Hosts, IDs) gehören in `LOKAL.md` — lokal gehalten,
  niemals committen.

### Kanonische Doku-Dateien

| Datei | Zweck | Aktualisieren wenn |
|---|---|---|
| `ROADMAP.md` | Phasenplan P0–P5, Status, Freigaben | Phasenfortschritt, Freigaben, Planänderungen |
| `AGENTS.md` | Arbeitsregeln für Agenten in diesem Repo | Workflow- oder Regeländerungen |
| `LOKAL.md` | Private Umgebungsdetails (nicht versioniert) | Änderungen an Umgebung, Remotes oder Stand |
| `docs/INVENTAR.md` | P0-Baseline-Inventar: Quellen, Deps, Lizenzen, Toolchain, Provenienz, Offline-Lücken | Bei Baseline-Wechsel oder neuen Artefakten |
| `docs/SOLO_SESSION_OVERVIEW.md` | Verkettung der Session-Pläne P0–P5 + LAN-Umstellung | Planänderungen, Session-Abgrenzung |
| `docs/SOLO_SESSION_00*.md` | Je Phase ein ausführbarer Session-Plan (Entscheidungen, Schritte, Verifikation) | Vor/nach jeder Session-Phase |
