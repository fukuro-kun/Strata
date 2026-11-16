# INTEGRATION 2026-11-16 — `strata-*`-Vendoring-Layout übernommen

Branch `feat/sync-2026-11-15-vendoring`, Commit `97cd09fa`, Basis `main` (`2f59be23`).
Vorarbeit: `ANALYSIS_2026-11-15_strata-llama-vendoring.md`. Upstream-Stand `baf16363b`.

## Was übernommen wurde

| Baum | Klassen | Verifikation |
|---|---|---|
| `third_party/strata-ggml` (127 Dateien) | 94 upstream, 3 edited, 8 added, 10 copy, 12 patched | `check_vendored: ok`; `patched` mechanisch rein additiv verifiziert (0 entfernte Zeilen ggü. Pin) |
| `third_party/strata-llama` (918) | 918 upstream | byte-identisch zu unserem `third_party/llama.cpp`-Pin-Baum (`diff -r` aller Unterbäume — nur dokumentiertes Trimming) |
| `third_party/strata-gguf-py` (116) | 116 upstream | `check_vendored: ok` |
| `third_party/stb` (2) | 1 upstream + 1 added | `check_vendored: ok` |

Pin überall `3cf03257f219afbe7334045ff7c6a06ac68c627d` == `LLAMA_CPP_COMMIT` (setup.py) ==
`third_party/ggml/VERSION.txt`. `strata-ggml/mmq.cuh` SHA-256 `50db23f5…` = unser Pin-Hash.

## Edit-/Patched-/Added-Review (Pflichtschritt vor Übernahme)

- **`edited` (3):** `ggml/CMakeLists.txt`, `ggml/src/CMakeLists.txt` (Backend-Trimming — nur
  base/cpu/cuda für unseren Build relevant; Targets unverändert), `strata-quant-common.h`
  (genau der dokumentierte 1-Zeilen-Metal-Edit: `GGML_COMMON_IMPL_METAL` ergänzt).
- **`patched` (12):** in `ggml/src/ggml-cuda-tq/` — Kopien von `ggml.h`, `mmq.cuh`,
  `mmq-load-tiles.cuh`, `mmq-config-*.cuh` mit rein additiven Trellis-Erweiterungen.
  Stichproben (`mmq.cuh`, `ggml.h`, `mmq-load-tiles.cuh`, `mmq-config-ampere.cuh`):
  **0 entfernte Zeilen** gegenüber dem Pin — deckt sich mit Upstreams `only_added`-Regel
  in `check_vendored.py`.
- **`added` (8):** `tq.cuh`, `tq-mmq-tiles.cuh`, `tq`-Template-Instanzen u. a. — semantisch
  identisch zu unserem bisherigen `third_party/ggml-tq` (nur Kommentare/Include-Pfade
  differieren; Funktionskörper gleich).
- **`copy` (10):** pristine Kopien (`quantize.cu/.cuh`, `mmq-vec-dot.cuh`, `include/*.h`) —
  byte-identisch zum Pin.
- **`check_vendored.py` selbst:** statisch gelesen — parst `UPSTREAM.md`-Manifestblöcke,
  hasht jede Datei (LF-normalisiert), prüft `only_added` für `patched`, lehnt ungelistete
  Dateien ab. Konservativ, kein Netz-Zugriff.

## Eigenanpassungen (Fork — bewusst, dokumentiert)

1. **`CMakeLists.txt`/`sycl/CMakeLists.txt`: FetchContent-Pfad komplett entfernt.**
   Upstream hat das Vendoring ohne Fetch-Pfad gebaut; unser Fork hatte zusätzlich die
   `STRATA_ALLOW_GGML_FETCH`-Option — jetzt strukturell weg: leeres `STRATA_GGML_DIR`
   resolve-t auf `third_party/strata-ggml`, gesetzt = bewusster Override-Checkout.
   **Strenger als bisher:** Configure kann nicht mehr ins Netz, nicht einmal opt-in.
2. **`build_engine.sh`:** `STRATA_GGML_DIR` wird nur noch übergeben, wenn der Aufrufer
   einen Override exportiert (leer ⇒ vendored + `ggml-cuda-tq`, kein Overlay-Lauf).
   Pin-Beweis vendored = `check_vendored.py`-Lauf + Manifest-Pin == `LLAMA_CPP_COMMIT`;
   Override-Baum = `.strata-pin`/clean-HEAD wie bisher. Stale-Cache-Guard angepasst.
   Vision bekommt `LLAMA_DIR=third_party/strata-llama` (Env `STRATA_LLAMA_DIR` override-bar).
3. **`make_manifest.py`:** Pin-Quelle `strata-ggml/UPSTREAM.md` (`pin:`-Zeile) mit
   `.strata-pin`-Legacy-Fallback; Manifest-Felder `pin_src` neu.
4. **`tools/vision/CMakeLists.txt`:** `LLAMA_DIR`-Default → `third_party/strata-llama`.
5. **`tools/_paths.py`:** `strata-gguf-py` als erster gguf-py-Kandidat (Legacy-Pfad bleibt
   Fallback für alte Installationsbäume).
6. **`cmake/strata_ggml_tq_overlay.cmake`:** Upstream-Version übernommen — das Overlay
   liest die tq-Quellen jetzt aus dem vendored `ggml-cuda-tq` (inkl. Include-Rewrite);
   `third_party/ggml-tq` damit entfernt (wie upstream).
7. **DSV41-BMI2-Block, MMQ-Margen, alle Fork-Edits:** unverändert — keine künstliche
   Regression. Insbesondere bleibt die stärkere MMQ-Marge (`T*K`/`Rt`/`kRows`-Schranken)
   Fork-Eigenschaft; Upstreams `T`-Schranke wird an diesen Stellen nicht übernommen.

## Verifikation (dieser Stand)

- `python3 tools/check_vendored.py` → **ok** (1163 Dateien, alle Manifeste am Pin).
- `tools/offline/build_engine.sh --cuda auto --arch native` (hydra, CUDA 13.5):
  Engine `strata` 0.1.55, `strata-vision`, `libstrata_kq.so` — sauber gebaut;
  Configure-Log belegt `ggml source: third_party/strata-ggml (pinned 3cf03257…)`
  und `trellis MMQ … vendored …/ggml-cuda-tq`; `mmq-instance-tq*.cu` kompilieren
  aus dem vendored Verzeichnis. `strata --version` läuft.
- `BUILD.json`: `ggml_commit = 3cf03257…`, `ggml_dir = third_party/strata-ggml`.
- Configure enthält keinerlei Netz-/Fetch-Aktivität (kein FetchContent-Pfad mehr).

## Bewusst NICHT übernommen / offen

- **`third_party/llama.cpp`-Vollbaum:** war nie committed (gitignored, per
  `fetch_llamacpp.sh` beschafft). Physische Bäume auf den Hosts bleiben liegen,
  werden vom Standard-Build nicht mehr gelesen. `fetch_llamacpp.sh` bleibt der
  dokumentierte Beschaffungspfad für Override-/Dev-Builds.
- **`third_party/gufo`, `third_party/sfnx`:** neue Upstream-Vendorees, von diesem
  Paket nicht berührt (keine Build-Referenz in unserem Tree) → Folgekandidat.
- **Rest des 742-Commit-Ranges** (Prefill-Regeln, q36-Umbau, serve-Lifecycle,
  Releases): separate Integrate-Schritte nach Radar-Priorisierung.
- **Binary-Äquivalenz alt/neu:** identische Quellen am selben Pin; Binaries
  unterscheiden sich in eingebetteten Pfaden (`src`-Fingerprint ändert sich
  erwartbar durch Layout). Funktionale Äquivalenz = Pin-Identität + erfolgreicher
  Build; belastbarer Beleg folgt über A/B + Smoke auf eris vor Promotion.

## Review-Runde 1 (review-swe, 2026-11-16) — Befunde + Fixes

Unabhängiges Review des Nicht-vendored-Diffs: **3 P1, 5 P2** gefunden, **alle gefixt**:

| # | Befund | Fix |
|---|---|---|
| P1-1 | **Metal-Backend gebrochen:** `third_party/ggml/ggml-common.h` ist jetzt ein `#include`-Forwarder, aber `mtl_rt.mm` bettet die Datei als **Rohtext** in die Shader-Quelle ein (kein Include-Resolver) | `metal/CMakeLists.txt` → `GGML_COMMON = strata-quant-common.h`; `build_dsv41_engine.sh` shipt Volltext unter beiden Namen; `gen_grids.sh` liest die echte Datei |
| P1-2 | `packaging/build_cuda_linux.sh` pinnte `STRATA_GGML_DIR`/`LLAMA_DIR` auf `third_party/llama.cpp` (optionaler Baum) | `-D`-Übergaben entfernt — vendored Defaults greifen |
| P1-3 | `tools/hip/build_windows.bat` Vision-Fallback `_deps/strata_llamacpp-src` (FetchContent-Überrest) | Fallback → `%SRC%\third_party\strata-llama` |
| P2-1 | `packaging/build_sycl_linux.sh`: wirkungsloses `FETCHCONTENT_SOURCE_DIR_*` | → `-DSTRATA_GGML_DIR=$LLAMA_CPP` |
| P2-2 | `spark/build_engine.sh`: impliziter Netz-Fetch via `setup.get_llama_cpp()` + erzwungener Overlay-Pfad | Fetch entfernt (Fork-Policy: nie still beschaffen); `-DSTRATA_GGML_DIR` nur bei gesetztem Override |
| P2-3 | `build_engine.sh` Stale-Guard verglich Cache-Absolutpfad mit roher Env → Dauer-Vollrebuild bei relativem Override | Vergleich gegen `${STRATA_GGML_DIR:+$GGML_DIR}` — exakt der an Configure übergebene Wert |
| P2-4 | ROADMAP.md: „FATAL_ERROR + ALLOW_GGML_FETCH" widersprach dem vendored Layout | Text korrigiert |
| P2-5 | `engram_iq4nl_bench.py`: `_deps/strata_llamacpp-src` existiert nie | `src_root` → `third_party/strata-ggml/ggml` (+ Legacy-Fallback) |

P3-Nachzüge gefixt: python3-Verfügbarkeits-Guard vor `check_vendored.py`, veraltete
`third_party/llama.cpp`-/`ggml-tq`-Pfade in `fetch_llamacpp.sh`, `tools/vision/CMakeLists.txt`,
`rope_scaling.hpp` (beide Trees), `docs/GYRO.md`. Historische Referenzen in
SOLO_SESSION-/DEEPSEEK41-/AMD_HIP-/NVFP4-Doku bleiben als History stehen (P3).

**Nach-Fix-Verifikation:** `bash -n` auf allen geänderten Skripten, `ast.parse` auf den
Python-Dateien, vollständiger Re-Lauf `build_engine.sh` → Engine + `strata-vision`
erneut sauber aus den vendored Bäumen (kein Cache-Wipe — Stale-Guard-Fix belegt).
Der Metal-Befund ist statisch gefixt; ein Metal-Build/Test ist im LAN nicht möglich
(keine macOS-Hardware) — analog HIP/SYCL als „nicht verfügbar" dokumentiert.

**Review-Runde 2 (review-swe, nur Fix-Commit): ship-ready** — alle Runde-1-Befunde
sauber gefixt verifiziert, keine Commit-Regression. Rest: 4 P2-Kosmetik gefixt
(gen_grids-Kommentar, Header-Docstrings, toter elif, Einrückung); 1 **pre-existing**
Verdacht separat notiert: `metal`-Staging legt Engine-Kernels nach `metal/src/engine/msl`,
`window.cpp`-Lookup sucht `<exe>/metal/engine-msl` — nicht durch diesen Commit
verursacht, kein Metal-Test im LAN möglich → eigener Folgepunkt.

## Gates vor Promotion (unverändertes Modell)

- [x] Unabhängiges Review des Diffs — Runde 1: 3 P1 + 5 P2 gefixt; Runde 2: **ship-ready**
- [x] Engine-Build auf eris (g++-13-Pflicht!) + Smoke-Inferenz
- [x] A/B-Benchmark (erwartbar NO_SIGNAL — Inhalte identisch, nur Layout)
- [x] Rollback-Bereitschaft (`previous`-Symlink)
- [x] Uranus-Rollout (CUDA-13.0-Pfad explizit!) + Smoke beider Hosts
- [x] Doku: UPSTREAM_SYNC_STATUS Rückstand, LOKAL.md, TTT, Trilium

## Rollout-Ergebnis 2026-11-16 (Promotion `36e6ab40` auf `main`)

| Gate | eris | uranus |
|---|---|---|
| Build | CUDA 12.4 / g++-13, vendored `strata-ggml` | CUDA 13.0 (explizit, PATH-Falle), sm_89, vendored |
| Deploy-Dir | `36e6ab40-20261116T055530Z` | `36e6ab40-20261116T060230Z` |
| `manifest.fork_sha` | `36e6ab40` — `make_manifest --verify`: **all match** (3 Artefakte, 29 Deps) | `36e6ab40` — **all match** |
| Checkout-HEAD | `36e6ab40` (= `origin/main`) | `36e6ab40` (= `origin/main`) |
| Laufende Binaries | `strata` + `strata-vision` aus Deploy-Dir (`/proc` verifiziert) | beide aus Deploy-Dir (`/proc` verifiziert) |
| `run.sh` | → `~/git/strata-fork-sync` (kanonisch) | → `~/git/strata-fork-sync` (kanonisch) |
| Smoke | „Paris", `finish: stop` | „Paris", `finish: stop` |
| `previous` (Rollback) | `c5d1fae5-20261114T224209Z` | `c5d1fae5-20261114T224154Z` |
| Health | `ok`, `api_key: true`, recovery idle | `ok`, `api_key: true`, recovery disabled |

A/B (reduziert, 5 Probes je Arm, identische Prompts): Kandidat-Median ~20,9 s vs.
Baseline ~24,7 s bei hoher Streuung und unterschiedlichen Thinking-Längen →
**NO_SIGNAL** (kein Leistungsanspruch; Inhalte sind per `check_vendored` hash-identisch).
Uranus-Service ist **System-Unit** (`sudo -n systemctl restart strata-swift-uranus-r`),
nicht User-Bus — `XDG_RUNTIME_DIR`-Falle dokumentiert.
