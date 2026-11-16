# INTEGRATION 2026-11-16 — Upstream `baf16363b` (v0.2.14 / engine 0.1.60) auf Fork-Basis

Branch `feat/sync-2026-11-16-merge-v0214`, Merge-Commit `a146dfdf7` (+ Review-Fixes `78bd00cc1`,
`2eb4d055b`, `b95c3372e`). Basis `main` (`0c652caad`). Merge-Base `c62d5e3a`.

**Umfang:** 2.132 Upstream-Commits, 3.344 Dateien Delta seit `c62d5e3a` — davon ~473 Dateien
mit Fork-/Upstream-Konflikten, ~50 Konflikt-Pfade manuell aufgelöst. Die Radar-Kandidaten
K2 (Prefill/q36), K3 (serve/-Lifecycle) und K4 (Prompt-Loan, STOP/conv-cache, Diagnose)
laufen hier in **einem** Merge, weil git-Merges atomar sind und die Konflikte verzahnt waren;
die Gate-Kette (Review → Build → Tests → Deploy → A/B → Promotion) gilt einmal für den
Gesamtstand.

## Bewusste Fork-Divergenzen (behalten, dokumentiert)

| Bereich | Entscheidung | Grund |
|---|---|---|
| **Acquisition-Default-Deny** | `acquisition.require()` vor jedem Netz-Zugriff bleibt; `netpolicy.open_url` übernommen | Fork-Kernprinzip: kein ungeprüfter Download/Ausführung |
| **MMQ-Marge** | Volle Row-Space als max_rows-Bound an allen Callsites (`mmq_prompt_ids_table_rows(T,K)`, `(rows,rows)`, `(Rt,Rt)`, `(ne,ne)` in prefill.cpp/q36_engine.cu) | Upstreams `max_rows <= T` ist sanitizer-widerlegt (111 OOB-Reads auf Layer-Major-Routing) — bewusste Divergenz, kein Merge-Versehen |
| **Engine-Auto-Recovery** | `engine_auto_restart`, `_recovery_*`, `ensure_loaded(restart_tries)` komplett erhalten; Upstream-`retry_args`/`retry_vram_args` dazu gemergt | Produktiv live (`engine_recovery` im /health); Upstream hat kein Äquivalent |
| **DSV41-Stack** | Entfernt (src/dsv41, serve/ds_pictures, packaging, verwaiste Fork-Tests/Skripte) | Upstream hat ihn gestrichen; Fork-Produktion ist Qwen-only |
| **FetchContent** | Kein FetchContent/GIT_REPOSITORY im eigenen Build-Pfad; vendored third_party-Bäume enthalten Upstreams Opt-in-Fetch-Pfade (CCCL/KleidiAI/LLVM) nur hinter nicht-default Optionen | Configure kann strukturell nicht ins Netz (Default-Pfad) |

## Konflikt-Auflösung (Auswahl, begründet)

- **`serve/server.py` (31 Hunks):** Upstream-Basis übernommen (Fatal-GPU-Reporting #4350,
  `errors="replace"` #5044, retry_args/retry_vram_args, nonblocking console, Waiter-Fixes
  #4738, `ended→restarts`-Semantik, Vision-Elastic); Fork-Recovery/Request-Priorität/
  proc-Race-Fixes re-mergiert. `StrataEngine.__init__` trägt alle drei Parameter
  (`_start_retries`, `retry_args`, `retry_vram_args`); rekursive Aufrufe positional korrekt.
- **`serve/telemetry.py`:** Upstreams `sysinfo`-Umbau + Fork-Guards re-integriert
  (IndexError/OSError/partition in `_cpu_name`/`_times`/`ram`).
- **`tools/mtp_fetch.py`:** Upstream `netpolicy` übernommen; alle 5 `acquisition.require`
  + `main_guard` erhalten.
- **`setup.py`:** Upstreams `_urlopen`→`netpolicy.urlopen`; `acquisition.require` bleibt
  davor. `get_prebuilt` (Signed-Feed-Pfad) gated.
- **Tests manuell kombiniert:** `test_serve_robustness.py` (Fork-Waiter + Upstream-Adds),
  `test_vision_ready_pipe.py` (Upstream-Pipe + Fork-Lock/Cache-Fixture),
  `test_vision_cpu_fallback.py`/`test_vision_no_room.py` (Upstream + `v.lock`/`v.cache`),
  `test_server.py` (Fork `tool_choice_none`-Test behalten + Upstream `lost_run`-Tests),
  `test_telemetry_files.py` (`sysinfo.processor` statt `platform.processor` gemockt).
- **`tools/test_setup_engine_hash.py`:** Pre-existing-Failure behoben — Tests laufen jetzt
  unter `STRATA_FORK_ALLOW_ACQUIRE=1` (Fork-Konvention, gemocktes Netz).

## Review-Historie

| Runde | Reviewer | Ergebnis | Fixes |
|---|---|---|---|
| R1 | review-swe | **not-ship-ready:** P1 doppelt gemergter ready_publish/notify-Block in `main()` (Publish+Notify vor try-Schirm; Fehlerpfad umging `finally`: kein `finished.set`, `remove_if_owned`, notify stopped) + P1/P2 rohes `urlopen` in runner.py (pre-existing) + P3s | `78bd00cc1`: Block A entfernt (Block B + finally decken Recovery-Stop/SIGTERM ab); `loopback.urlopen`; `START_RETRIES` ValueError-Guard; `mmq_prompt_ids_table_rows`-Äquivalenz-Test; bench-Bound-Kommentar |
| R2 | review-swe | **needs-fixes:** P1 falscher Degenerate-CHECK in mmq_margin_test (`prompt(0,0)==0` vs `table(0,0)==128`); Rest verifiziert ship-ready (Publish-Block, loopback, Guards, Recovery, Retry-Signatur, Acquisition, DSV41, MMQ-Callsites) | `2eb4d055b`: CHECK korrigiert, Host-Build+Lauf grün |

## Gates

| Gate | Ergebnis |
|---|---|
| Statische Prüfung | Keine Konfliktmarker, keine Doppel-Defs (AST scoped), keine `ds_pictures`/`dsv41_engine`-Referenzen, kein FetchContent im Default-Pfad |
| Python serve-Suite | 116 Dateien: alle grün (nach telemetry/test_setup_engine_hash-Fixes; 12 SDK-Skips) |
| `tools.test_setup_engine_hash` | 30/30 (unter Fork-Acquire-Flag) |
| `mmq_ids_margin_test` | ok (Host-Build + ctest) |
| hydra-Build | `strata` 0.1.60.1 + `strata-vision`, CUDA 13.5 native, `ggml_commit=3cf03257`, `check_vendored: ok` |
| Merge-relevante C++/CUDA-Tests (25) | **alle grün** (~42 Min): prefill_plan, q36_context_fit, q36_prompt_route, routed_stream, mmq_ids_margin, gp100_prompt_default, prefill_fused_{moe,iq,q36}+Varianten (sm75/ws arch-Skips) |
| `cuda_spill_guard` | grün — 3 neue dflash2-Kernel-Instanzen in sm_86-Baseline aufgenommen (gemessen: 8/16/16 B stack; `_SM89_ALLOWED` deckt Familie, sm_86-Instanzen dokumentiert) |
| eris-Build (g++-13, CUDA 12.4) | **grün** — `strata` + `strata-vision` (290 Schritte), `ggml_commit=3cf03257`, `check_vendored: ok` |
| eris-Deploy | `e6cdef3a-20261116T181951Z`, Manifest `--verify`: 3 Artefakte + 29 Deps all match, `run.sh` kanonisch (`strata-fork-sync`), `previous`→`36e6ab40` |
| Smoke (eris, produktiv) | „Paris", `stop`; prompt 57.5 t/s, decode 41.1 t/s, Draft-Acc 26/33; `engine_recovery` aktiv |
| A/B (eris, 5 gepaarte Runden + Probe je Arm) | **NO_SIGNAL** — t1_4k 115.6 vs 83.2 t/s (Rauschen 53 %), t1_16k 223.5 vs 231.1 (−3.3 %), t2 35.2 vs 38.9 (−9.5 %); T3 25/25 Turns OK beide Arme inkl. Tool-Call-Assertion; hohe Varianz: Prefill ist expert-I/O-bound, erster großer Prompt nach Restart dominiert |
| Tail-Review (`b95c3372e`, `e6cdef3af`) | **ship-ready** (review-swe): Baseline-Einträge schema-/instanzexakt, kein Over-Coverage; P3-Fix `fea002cf3` (Instanzenzahl 16→19 in `measured_with`) |
| Promotion | `main` → `7527614b4` (+ Fork-Gate-Fix `b53b531bf`, Guard-Test `1c125e609`, Docs `005a3c615`) gepusht |
| uranus-Nachzug | **grün** — Build `fork-sync`@`7527614b4` (sm_89, CUDA 13.0 explizit, vision cpu) → Deploy `7527614b-20261116T192152Z`, Manifest all match, `previous`→`36e6ab40`; System-Unit `strata-swift-uranus-r` restart, ready 40 s, Smoke „Paris"/stop (98.2/54.2 t/s); `engine_recovery` dort per Config disabled (Soll). `test_fork_workflows` 5/5 auch auf uranus |

## Merge-Nachzug (post-Promotion): Workflow-Fork-Gate

Vier mit dem Merge neu eingezogene Workflow-Dateien (`backends.yml`, `check.yml`,
`docs.yml`, `snapshot.yml`) trugen Upstreams `push:`/`pull_request:`-Trigger **ohne**
`Niko1221/Strata`-Repo-Gate — Verstoß gegen die Fork-Workflow-Grenze; auf dem
öffentlichen Mirror hätten sie ungeprüfte Upstream-CI bei jedem Push gestartet.
Befund durch nachträglichen Sweep, **nicht** durch die Merge-Prüfung (Lücke:
Workflow-Dateien gingen konfliktfrei durch, kein Gate-Scan im Prozess).
Fix `b53b531bf`: alle vier auf `workflow_dispatch` reduziert + `if:
github.repository == 'Niko1221/Strata'` je Job; Voll-Sweep über alle 12
Workflows verifiziert konform. **Prozess-Nachzug:** künftige Merges brauchen
einen expliziten `.github/workflows`-Gate-Scan vor Promotion.

## Hinweise / Restpunkte

- Vendored FetchContent-Pfade (CCCL `GGML_CUDA_CUB_3DOT2`, KleidiAI, `GGML_OPENMP_FETCH`,
  LLVM-Installer) sind **Upstream-Original** (check_vendored-Hash-gesichert) und hinter
  nicht-default Optionen — Default-Build offline-rein. Dokumentiert, kein Fork-Verstoß.
- `mmq_expert_bench.cpp` nutzt bewusst engere Bound `(T,R)` — echtes per-expert-Maximum
  bekannt; Kommentar ergänzt.
- Stale `src/dsv41`-Kommentare in `iq_avx*.hpp`, `metal_compat/*.h` — Doc-Rot upstreams, harmlos.
- `tests/terminal/test_no_acquisition.py::_sources()` globbt nicht-rekursiv —
  `strata_cli/launch/*.py` wird nicht gescannt; als Beobachtung vermerkt (Fork-Netz-Guard
  selbst greift zur Laufzeit; Scan-Lücke kosmetisch).
- Uranus bleibt ausgeschaltet → kein Deploy/Test dort; beim Wiederanlauf kontrollierter
  Nachzug (CUDA 13.0, sm_89, Manifest+Smoke) nötig. **Hinweis (Tail-Review):** die drei
  neuen dflash2-Instanzen sind in `_SM89_ALLOWED` nur mit 8 B Familien-Allowance
  bedacht, auf sm_86 wurden 16 B gemessen — falls der Merge die sm_89-Stack-Werte
  verändert hat, schlägt `cuda_spill_guard` auf sm_89 fehl und die Instanzen sind
  dort ebenfalls gemessen einzutragen.
- Arm-A-Verifikation nebenbei belegt: die 0.1.55-Engine (`previous`-Deploy) startet
  unter serve@`e6cdef3af` sauber (ready 21 s, `engine_recovery` aktiv) — die
  Rollback-Konfiguration ist funktional.
- A/B-Methodik: beide Arme liefen unter identischem serve-Stand `e6cdef3af`
  (fork-sync-Checkout) — wie ein realer Rollback; Engine-Binary isoliert.
  Evidence: `/tmp/ab_v0214_results.jsonl` + `ab_plan.json`/`ab_payloads.py`
  (SHA eingefroren) auf eris.
