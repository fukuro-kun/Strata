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
| eris-Build (g++-13, CUDA 12.4) | _läuft_ |
| eris-Deploy + Smoke + A/B | _offen_ |
| Promotion + Doku-Abschluss | _offen_ |

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
  Nachzug (CUDA 13.0, sm_89, Manifest+Smoke) nötig.
