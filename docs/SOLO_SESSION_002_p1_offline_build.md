# SOLO_SESSION_002 — P1: Isolierter Offline-Build-Einstieg

## Session-Ziel

Ein Build-Einstieg existiert, der **ausschließlich lokale, gepinnte Inputs**
nutzt: lokaler llama.cpp-Checkout über `STRATA_GGML_DIR`, eigene Engine aus
Quellen gebaut (kein Prebuilt), fehlende Inputs → klarer Abbruch (fail
closed). Auf hydra nachgewiesen. Branch: `feat/p1-offline-build`.

## Entscheidungen

| Frage | Entscheidung |
|---|---|
| llama.cpp-Bezug | Kontrollierte Online-Beschaffung: einmalig gepinnter Commit `3cf03257f219afbe7334045ff7c6a06ac68c627d` (aus `third_party/ggml/VERSION.txt` + `CMakeLists.txt:1309`) → `third_party/llama.cpp` (gitignored, reservierter Pfad) |
| Build-Ort | hydra; CUDA-Backend falls Toolchain aus P0 vorhanden, sonst CPU-only (Akzeptanz = offline, nicht GPU) |
| Skript-Ablage | `tools/offline/` (neu): `fetch_llamacpp.sh` (Beschaffung), `build_engine.sh` (offline-only) — getrennt, weil Beschaffung ≠ Build |
| Konfiguration | Defaults aus CMake; Arch `native`-kompatibel zum Host (sm_86 auf hydra); Portables Binary nicht nötig (pro-Host-Builds via P3-Manifest) |

## Schritte

- [ ] 1. Branch `feat/p1-offline-build` von `feat/p0-inventar` (oder main
       falls 001 noch offen — dann main)
- [ ] 2. `tools/offline/fetch_llamacpp.sh`: git clone/fetch von
       github.com/ggml-org/llama.cpp, exakter Commit-Checkout, Integrität
       via `git rev-parse` == Pin prüfen; **bewusst einmalig ausführen**
       (kontrollierte Beschaffung, im Manifest dokumentieren)
- [ ] 3. `tools/offline/build_engine.sh`: prüft `STRATA_GGML_DIR`
       (Default `third_party/llama.cpp`) existiert + richtiger HEAD →
       `cmake -DSTRATA_GGML_DIR=... -DSTRATA_ENABLE_CUDA=ON/OFF ...` +
       `cmake --build`. **Jeder fehlende Input → Abbruch mit Klartext-
       Fehler.** Kein pip, kein Download, kein apt im Skript.
- [ ] 4. Offline-Beweis: Build mit Netz-Namespace-Trennung ODER
       zumindest ohne dass das Skript Netz-Calls enthält + CMake-Configure-
       Log prüfen (kein FetchContent-Download weil STRATA_GGML_DIR gesetzt).
       Dokumentierte Prüfung: `cmake -LA` Ausgabe + Abwesenheit von
       `_deps/strata_llamacpp`-Fetch im Log.
- [ ] 5. Smoke-Test: gebautes `strata`-Binary `--help`/Versionsausgabe +
       `ldd`/`ldd`-Äquivalent prüfen (keine unerwarteten Laufzeit-Deps)
- [ ] 6. Doku: `docs/OFFLINE_BUILD.md` (Voraussetzungen, Beschaffung,
       Build, Fehlerbilder) + INVENTAR/ROADMAP-Update (P1-Checkboxen)
- [ ] 7. Review → Commit → Push

## Verifikations-Strategie

| Schritt | Verifikation | Metrik Vorher/Nachher |
|---|---|---|
| 2 | `git -C third_party/llama.cpp rev-parse HEAD` == Pin | Vorher: Pfad leer / Nachher: gepinnter Checkout |
| 3-4 | Configure-Log enthält keinen `Cloning`/`Fetching`-Eintrag für llama.cpp; Build-Artefakt existiert | Vorher: kein Binary / Nachher: `strata` Binary + Größe |
| 5 | Binary startet, Exit-Code 0 bei `--help` | — |

## Live-Verifikations-Szenario

**Szenario:** Frischer Offline-Build-Lauf
**Akzeptanzkriterien:**
- [ ] `fetch_llamacpp.sh` bricht ab wenn Pin-Checkout fehlschlägt (nicht "best effort")
- [ ] `build_engine.sh` bricht mit klarem Fehler ab wenn `third_party/llama.cpp` fehlt
- [ ] Mit vorhandenem Checkout: Build läuft ohne Netz-Pflicht durch, Binary entsteht
- [ ] `strata --version`-äquivalente Ausgabe zeigt Version 0.1.44.1

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
