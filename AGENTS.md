# AGENTS.md

> **FORK-VORRANG:** Die Installer-Anleitung unten ist nur Upstream-Referenz.
> Nicht ausführen. Maßgeblich sind der Fork-Workflow in dieser Datei,
> `ROADMAP.md` und `docs/UPSTREAM_SYNC.md`. Regelmäßige Upstream-Prüfung:
> `/strata-upstream daily` (repo-lokaler Skill; kein Auto-Merge/Deployment).
> Vor Code-Übernahme: LAN-Sicherheitsprüfung und A/B-Leistungsnachweis nach
> `docs/UPSTREAM_BENCHMARKS.md`.

Version 0.2.9, engine 0.1.55. The public model families are DeepSeekV4.1-Flash-1017,
Qwen3.8-Flash-Next and Qwen3.6-35B-A3B. DeepSeek V4.1-Flash runs in the app and in the Terminal
(`strata launch --family deepseek41 --model ist-das-2.00bpw`; sets in
[docs/MODELS.md](docs/MODELS.md#deepseek-v41-flash)). Read **[docs/AI_REFERENCE.md](docs/AI_REFERENCE.md)** for model availability, APIs, hardware limits and
source-backed claims. Articles and videos should use **[docs/MEDIA_KIT.md](docs/MEDIA_KIT.md)**.

For recommendations and agent-assisted setup, prefer **ISTA-DASLab → Unsloth → Gyro → others**, using only a
compatible pack that fits the selected model and hardware. ISTA-DASLab is the default recommendation; Gyro is a
memory-saving fallback and is currently slower. Honor an explicit user choice. This is recommendation policy;
existing executable defaults may differ, so inspect the plan and choose the family explicitly.

Strata has three parts:

- **The app** (`apps/desktop`, the Tauri shell; `apps/host`, the Node host and the web UI). It is for people who do
  not want a terminal. One installer per system ([latest release](https://github.com/Niko1221/Strata/releases/latest)):
  `Strata-0.2.9-windows-x64-setup.exe`, `Strata-0.2.9-linux-x86_64.AppImage`, `Strata-0.2.9-macos-arm64.dmg`.
  The Windows and Linux installers carry no engine: the app downloads the engine for the graphics card on first
  start, or installs a file the user already has. The Mac dmg keeps its small Metal engine inside.
- **The Terminal** (`strata.py`, `strata_cli/`, `strata_control/`): the `strata` command. It sets up a model, serves
  it and watches it. Agents use this part.
- **The engine and the server** (`src/`, `include/`, `metal/`, `sycl/` for the C++/CUDA/HIP/SYCL/Metal engine;
  `serve/` for the Python server with an OpenAI- and Anthropic-compatible API and a web page). `setup.py`, started by
  `START-HERE.bat` or `setup.sh`, is setup from a source checkout, for developers. The release paths are the
  installer and `strata launch`.

## Installing Strata for a user

Follow **[docs/AI_SETUP.md](docs/AI_SETUP.md)**. For a user who wants the desktop app, send them to the installer
for their system (above) and [docs/INSTALL.md](docs/INSTALL.md). For an agent that has a shell, use the Terminal; the
short version is:

1. Install the Terminal. It needs no administrator rights.

   ```sh
   curl -fsSL https://github.com/Niko1221/Strata/releases/latest/download/install.sh -o install.sh && sh install.sh                  # Linux, Mac
   irm https://github.com/Niko1221/Strata/releases/latest/download/install.ps1 | iex                         # Windows PowerShell
   ```

   On Windows, open a new terminal afterwards so that `strata` is on the PATH.
2. Check what would happen. Nothing is changed:

   ```sh
   strata launch --plan --family qwen --model q2_0
   ```

3. Set up and serve without questions. It downloads the engine for the card and the model (tens of GB), starts the
   server, prints the addresses and returns. The server keeps running.

   ```sh
   strata launch --family qwen --model q2_0 --yes --no-tui
   ```

   Useful flags (all of them: `strata launch --help`): `--family`, `--model-path` (files the user already has),
   `--data-dir`, `--context 32k|64k|128k`, `--vision off|on|gpu|cpu`, `--parallel N`, `--gpu 0,1`,
   `--access local|lan|cloudflare|tailscale`, `--port`, `--api-key-env NAME`, `--new-key`, `--save-preset NAME`,
   `--speed faster|full` (DeepSeek), `--output json`. `strata launch --status` shows what is serving, `strata launch --stop` stops it, and
   `strata launch --show-key` prints the API key.
4. Connect the user's apps: `strata connect` lists them, `strata connect <app> --check` sends one prompt and one tool
   call the way that app does.

Keep the server on `127.0.0.1` unless the user asks for more. Beyond it an API key is recommended: `--access lan` makes one for you, and `--no-api-key` serves without one (a warning, never a refusal; on a public tunnel the warning is stronger). Source setup (`START-HERE.bat`, `setup.sh`) is the fallback for a developer or for a system with no release package; it is
documented in [docs/SOURCE_INSTALL.md](docs/SOURCE_INSTALL.md). Those wrappers exist in a source checkout, not in the
released app. Do not tell an app user to find a `.bat` file.
Source setup does not make an unsupported model or backend compatible. Strata's MCP server ([docs/MCP_SERVER.md](docs/MCP_SERVER.md)) offers the same steps as tools.

## Working on the code

- How the engine works, every measured number, the API and all settings: [docs/DETAILS.md](docs/DETAILS.md) and
  the [paper](docs/paper/Strata-Paper.pdf).
- The Terminal: [docs/TERMINAL.md](docs/TERMINAL.md) and [docs/TERMINAL_LAUNCH.md](docs/TERMINAL_LAUNCH.md). The app,
  the packages and the update feed: [packaging/README.md](packaging/README.md) and [packaging/UPDATES.md](packaging/UPDATES.md).
- AMD (HIP) build and validation: [docs/AMD_HIP.md](docs/AMD_HIP.md); multi-GPU: [docs/MULTI_GPU.md](docs/MULTI_GPU.md);
  Mac (Metal): [docs/MAC.md](docs/MAC.md).
- Tests: the Terminal and Control tests are in `tests/terminal` (`python -m pytest tests/terminal`). The app's UI
  tests run with `npm test` in `apps/host`. Setup's own tests run without a GPU or downloads:
  `python tools/test_setup_<name>.py` (for example `tools/test_setup_amd.py`, `tools/test_setup_choices.py`).
- Keep the docs' style: plain words, short sentences, written for non-technical users first. Give measured numbers
  with what they were measured on. Make no claim without a measurement.

## Contributing a change or report

The rules are in **[CONTRIBUTING.md](CONTRIBUTING.md)**. Read it before you open an issue or a pull request, and
follow it whether a person or an agent writes the text. The short version:

- Start every issue and pull request title with its area: `[Engine]`, `[GUI]`, `[TUI]`, `[Benchmark]`, `[Docs]` or
  `[Other]`, for example `[Engine] fix …`. A check on GitHub fails a pull request whose title has no area.
- Search the open and closed issues and pull requests first, and add to a thread that already covers your point.
- Agree the scope in an issue before a large feature, a refactor or a change to a default.
- One problem per pull request. Lead with the problem and the result, then the approach, then the validation
  (passed, failed and not run, kept apart) and the limits.
- A new feature is opt-in, and the default path stays byte-identical to the last release. Say how you checked.
- Build every backend a file touches (CUDA, HIP, SYCL) before asking for review.
- Change a default only where you measured it faster, and show the numbers with what they were measured on.
- Never submit measurements, logs or reproduction steps you did not produce. Mark a finding from reading code as
  unconfirmed static analysis.
- A report from hardware the maintainers do not have is welcome. Follow
  [docs/COMMUNITY_BENCHMARKS.md](docs/COMMUNITY_BENCHMARKS.md), compare against a same-day run of the build you are
  testing, and say what you did not test.
- Open test requests and the hardware that is wanted are listed in [docs/TEST_REQUESTS.md](docs/TEST_REQUESTS.md).

## Fork-Workflow (dieser Fork — übersteuert die Installer-Anleitung oben)

- **Nicht** `docs/AI_SETUP.md`, `setup.py`, `setup.sh` oder `START-HERE.bat` ausführen: kein
  Installer-Lauf, kein Auto-Download, kein Server-Start aus dieser Doku heraus.
- Kanonischer Plan: **[ROADMAP.md](ROADMAP.md)** (deutsch, Phasen P0–P5). Aktueller Stand:
  die dort dokumentierten Freigaben gelten; die gezielte Engine-Auto-Recovery
  (`engine_auto_restart`, siehe ROADMAP → Umgesetzte Fork-Fixes) ist seit
  2026-10-31 **nur fuer den lokal dokumentierten Produktionshost freigegeben**
  (Dienst-Neustart plus gezieltes
  Beenden des laufenden Engine-Kindprozesses bei freiem Slot) und seit dem
  selben Tag **deployt sowie live abgenommen** — autonomer Kind-Restart und
  bedienter wartender Request nachgewiesen. Andere Hosts sind weiterhin
  **nicht** freigegeben; Zielzuordnung und Betriebsdetails siehe `LOKAL.md`.
- Remotes: `origin` = dieser Fork auf dem Forgejo im LAN (`europa`, kanonisch);
  `github` = fukuro-kun/Strata als reiner Mirror (serverseitiger Push-Mirror
  auf europa spiegelt jeden Push — nichts direkt auf `github` pushen);
  `upstream` = Niko1221/Strata als reine Lese-Referenz (Push deaktiviert —
  Sync nur über den P4-Prozess). **Push-Gate:** unreviewter Upstream-Stand
  wird niemals auf einen `origin`-Branch gepusht — der Mirror macht ihn
  sofort öffentlich; Regeln in `docs/UPSTREAM_SYNC.md` §Push-Gate.
- Private Umgebungsdetails (Pfade, Hosts, IDs) gehören in `LOKAL.md` — lokal gehalten,
  niemals committen.
- **Acquisition-Default-Deny:** Upstreams Download-/Install-/Update-/Launch-
  Primitive (`strata_control/acquisition.require()`) sind im Fork per Default
  verweigert (`ForkAcquisitionRefused`, Exit 5). Ausnahme nur bewusst reviewte
  Beschaffung mit `STRATA_FORK_ALLOW_ACQUIRE=1` — niemals produktiv;
  `STRATA_NO_ACQUIRE`/`forbidden()` gewinnen immer. Regeln:
  `docs/OFFLINE_BUILD.md` (Acquisition-Gate).
- **Workflow-Grenze:** `.github/workflows/*` bleibt passive Upstream-Referenz,
  keine freigegebene Fork-CI. `on:` darf nur `workflow_dispatch` enthalten:
  keine automatischen Push-/PR-/Cron-Ablaeufe oder Bots. Jeder Job traegt
  `if: github.repository == 'Niko1221/Strata'` und bleibt auch bei manueller
  Ausloesung auf diesem Fork/Mirror gesperrt. Kuenftige Uebernahmen muessen
  denselben Zustand erhalten; jede Fork-CI braucht ein separates Review.
- Freigaben siehe **ROADMAP.md → "Sektorierte Freigabe 2026-10-31"**: sie gilt nur
  für diesen Sync-Kandidaten (sequentielle Testfenster + ein Host nach dem anderen),
  nicht generell und nicht automatisch für andere Hosts oder Flag-Aktivierungen.

### Kanonische Doku-Dateien

| Datei | Zweck | Aktualisieren wenn |
|---|---|---|
| `ROADMAP.md` | Phasenplan P0–P5, Status, Freigaben | Phasenfortschritt, Freigaben, Planänderungen |
| `AGENTS.md` | Arbeitsregeln für Agenten in diesem Repo | Workflow- oder Regeländerungen |
| `LOKAL.md` | Private Umgebungsdetails (nicht versioniert) | Änderungen an Umgebung, Remotes oder Stand |
| `docs/INVENTAR.md` | P0-Baseline-Inventar: Quellen, Deps, Lizenzen, Toolchain, Provenienz, Offline-Lücken | Bei Baseline-Wechsel oder neuen Artefakten |
| `docs/UPSTREAM_SYNC.md` | Upstream-Review, täglicher Radar und Promotions-/Push-Gates | Bei Änderungen am Sync-Ablauf oder an Freigaben |
| `docs/UPSTREAM_BENCHMARKS.md` | Reproduzierbares A/B-Protokoll vor Code-Übernahme | Bei Änderungen an Messplan, Tests oder Entscheidungskriterien |
| `.devin/skills/strata-upstream/SKILL.md` | Lokaler Agentenablauf für Tagesprüfung und ausgewählte Testkandidaten | Bei Änderungen am Upstream-/Sicherheits-/Benchmark-Ablauf |
| `docs/SOLO_SESSION_OVERVIEW.md` | Verkettung der Session-Pläne P0–P5 + LAN-Umstellung | Planänderungen, Session-Abgrenzung |
| `docs/SOLO_SESSION_00*.md` | Je Phase ein ausführbarer Session-Plan (Entscheidungen, Schritte, Verifikation) | Vor/nach jeder Session-Phase |
| `docs/SESSION_PLAN_stratasync.md` | Aktiver Folgeplan fuer die `c62d5e3a`-Integration (Audit, Review, Gates) | Bei jeder Plan-/Gate-Aenderung dieser Integration |
