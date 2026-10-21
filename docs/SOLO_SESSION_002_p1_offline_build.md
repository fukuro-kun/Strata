# SOLO_SESSION_002 — P1: Isolierter Offline-Build-Einstieg

## Session-Ziel

Ein Build-Einstieg existiert, der **ausschließlich lokale, gepinnte Inputs**
nutzt: lokaler llama.cpp-Checkout über `STRATA_GGML_DIR`, eigene Engine aus
Quellen gebaut (kein Prebuilt), fehlende Inputs → klarer Abbruch (fail
closed). Auf hydra nachgewiesen. Branch: `feat/p1-offline-build`.

## Entscheidungen

| Frage | Entscheidung |
|---|---|
| llama.cpp-Bezug | **LAN-Beschaffung** (kein externer Fetch nötig): uranus `~/git/llama-upstream` enthält Pin-Commit `3cf03257f219afbe7334045ff7c6a06ac68c627d`; zusätzlich existieren auf uranus+eris entpackte `third_party/llama.cpp/` aus dem Produktiv-Aufbau. Bevorzugt: rsync des entpackten Baums + SHA256-Vergleich beider Host-Kopien (zwei unabhängige Downloads = Integritätsbeweis). Alternativ `git archive` auf uranus (Achtung: blob:none-Partial-Clone kann Blobs nachladen → externer Fetch, nur als Fallback). Pin-Verifikation via `git ls-tree`-Vergleich bleibt Pflicht |
| Build-Ort | hydra; CUDA-Backend vorhanden (nvcc 13.4, RTX 3070 sm_86) → CUDA-Build möglich; Akzeptanz bleibt „offline", nicht „GPU-Performant" |
| Skript-Ablage | `tools/offline/` (neu): `fetch_llamacpp.sh` (Beschaffung), `build_engine.sh` (offline-only) — getrennt, weil Beschaffung ≠ Build |
| Fail-closed-CMake | Zusätzlich zu `STRATA_GGML_DIR`-Pflicht im Skript: minimaler Patch in `CMakeLists.txt` else-Zweig (FetchContent) → `FATAL_ERROR` mit Klartext statt stiller Download (Fork-Policy, bewusste kleine Divergenz) |
| Konfiguration | Defaults aus CMake; Arch `native`-kompatibel zum Host (sm_86 auf hydra); Portables Binary nicht nötig (pro-Host-Builds via P3-Manifest) |

**Befunde aus Session 001 (P0):**
- `CMakeLists.txt:1263` `STRATA_GGML_DIR` Cache-Var; `:1303` add_subdirectory-Pfad;
  `:1306-1315` FetchContent else-Zweig (GIT_REPOSITORY github → fail-closed-Patch hier)
- `STRATA_ORACLE_SOURCE_DIR`/`STRATA_ORACLE_BUILD_DIR` (`:456-457`) für Parity-Tests —
  dokumentieren, nicht setzen
- `setup.py:1967-2005` `get_llama_cpp()`: bei vorhandenem `third_party/llama.cpp/{ggml/CMakeLists.txt,gguf-py}` **kein** Download — der gepackte Pfadname ist `third_party/llama.cpp` selbst (Fork-Convention: gleicher Pfad)

## Schritte

- [x] 1. Branch `feat/p1-offline-build` von `feat/p0-inventar`
- [x] 2. `tools/offline/fetch_llamacpp.sh`: drei Modi (`--from-dir`,
       `--from-git` ohne Fetch, `--clone` als bewusster Netz-Fallback),
       `.strata-pin`-Marker + Versionsabgleich gegen `VERSION.txt`.
       **Beschaffung real via LAN:** rsync des verifizierten Baums von
       uranus (byte-identisch zu eris — 2824 Dateien, nur `__pycache__`
       abweichend); Skript-Pfad mit `--from-dir` e2e getestet
- [x] 3. `tools/offline/build_engine.sh`: fail-closed Input-Prüfung
       (.strata-pin/git-HEAD == `LLAMA_CPP_COMMIT`), exakt die
       Upstream-Local-Build-Flags aus `setup.py:cmake_build`, Staging nach
       `engine/` + `BUILD.json` (`source: local-fork`)
- [x] 4. Offline-Beweis: Configure-Log ohne `Cloning`/`Fetching` (5.9s,
       ggml aus lokalem Baum); **zusätzlich** CMake-Patch: leeres
       `STRATA_GGML_DIR` → `FATAL_ERROR` (live getestet — Configure bricht
       mit Klartext ab), Escape `-DSTRATA_ALLOW_GGML_FETCH=ON`
- [x] 5. Smoke-Test: `engine/strata --help` läuft, `engine=0.1.44.1`
       eingebettet, `ldd` sauber (CUDA 13.4 + libc); 153 Targets +
       Vision-Build (131 Targets) fehlerfrei
- [x] 6. `docs/OFFLINE_BUILD.md` geschrieben; ROADMAP P1 abgehakt
- [x] 7. Review → Commit → Push

**Review-Nachlauf (review-swe):** 4 echte Befunde gefunden und gefixt:
- `sha256sum` auf nicht gebaute Artefakte (CPU-Build ohne `libstrata_kq.so`)
  → Skript endete mit Exit 1 *nach* erfolgreichem Build; jetzt nur
  existierende Dateien hashen
- `--from-git` konnte bei Partial-Clones still lazy-fetchen →
  `GIT_NO_LAZY_FETCH=1` (fail closed statt Netz)
- Pin-Beweis-Lücke: `--from-dir` stempelte unbewiesene Bäume →
  Pin-Nachweis (`.strata-pin` oder sauberer git-Checkout am Pin) jetzt
  **vor** dem Kopieren, sonst `--allow-unverified` nötig; `build_engine.sh`
  lehnt dirty Checkouts am Pin ab
- `--arch native`-Crash im BUILD.json-Stamp (int-Parse) + Stale-Cache-Bug:
  CMake-Auto-Cache-Reset verlor `-D`-Flags im Re-Run (beobachtet:
  `STRATA_GGML_DIR` leer → Fail-closed-Fehler trotz Flag) → Cache-Konflikt
  wird vorab erkannt und der Cache entfernt
- Parent-Repo-Falle: `git -C third_party/llama.cpp rev-parse` löste auf den
  Strata-Checkout auf (kein `.git` im entpackten Baum) → Pin-Prüfung nur bei
  `.git` direkt im Baum

**Bonus-Nachweis:** Produktiv-BUILD.json `src=7dfd34378bd2d32a` /
`vision_src=13d9deaf827f14ef` reproduziert aus `/tmp/strata-src`
(`source_hash()` nachgerechnet) → bisherige Engines sind kryptografisch an
den auditierten Baum gebunden. Fork-Build zeigt `src=b5006933b295d641`
(erwartbar wegen CMake-Patch), `vision_src` identisch.

## Verifikations-Strategie

| Schritt | Verifikation | Metrik Vorher/Nachher |
|---|---|---|
| 2 | `git -C third_party/llama.cpp rev-parse HEAD` == Pin | Vorher: Pfad leer / Nachher: gepinnter Checkout |
| 3-4 | Configure-Log enthält keinen `Cloning`/`Fetching`-Eintrag für llama.cpp; Build-Artefakt existiert | Vorher: kein Binary / Nachher: `strata` Binary + Größe |
| 5 | Binary startet, Exit-Code 0 bei `--help` | — |

## Live-Verifikations-Szenario

**Szenario:** Frischer Offline-Build-Lauf
**Akzeptanzkriterien:**
- [x] `fetch_llamacpp.sh` bricht ab wenn Pin-Checkout fehlschlägt (nicht "best effort")
- [x] `build_engine.sh` bricht mit klarem Fehler ab wenn `third_party/llama.cpp` fehlt
- [x] Mit vorhandenem Checkout: Build läuft ohne Netz-Pflicht durch, Binary entsteht
- [x] `strata --version`-äquivalente Ausgabe zeigt Version 0.1.44.1

## Defaults

- CUDA-Toolkit fehlt auf hydra → CPU-only-Build für den Offline-Beweis;
  GPU-Build auf Zielhost dokumentiert (P3/P6 übernehmen)
- CMake-Cache-Verzeichnis `build/` (gitignored), kein In-Source-Build
- Warnings ≠ Fehler; nur `-Werror` nicht forcieren

## Recherche-Strategien

| Problemtyp | Strategie |
|---|---|
| CMake-Option unklar | `grep` CMakeLists + `cmake -LH` Probe |
| Compile-Fehler | Fehlermeldung → Source-Kontext → minimaler Fix nur in eigenen Skripten, nie Engine-Code patchen ohne Befund |
| llama.cpp API-Drift | Pin ist von upstream getestet — niemals Commit ändern, sondern Fund dokumentieren |

## Recherche-Fallbacks

| Block | Problem | Fallback |
|---|---|---|
| llama.cpp-Fetch | github nicht erreichbar | `/tmp/strata-src` hat `.git`? — nein (nur Worktree); Alternate: dokumentieren + CPU-Build-Pfad offen lassen, Beschaffung nachholen wenn Netz da |
| CUDA | Toolkit fehlt/nvcc zu alt | CPU-only-Build, GPU-Toolchain-Bedarf ins Inventar/P3 |
| Build-Zeit | >30min | Hintergrund-Build, Parallelarbeit an Doku |

## Offene Fragen

- Ob TheRock/ROCm-Build auf AMD-Hosts später eigene Fetch-Strategie braucht
  (P3/P6 klären; Inventar liefert Fakten)

## Folge-Plan

→ `SOLO_SESSION_003_p2_python_deps.md`
