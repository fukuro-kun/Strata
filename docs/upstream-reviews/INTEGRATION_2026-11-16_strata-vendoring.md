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

## Gates vor Promotion (unverändertes Modell)

- [ ] Unabhängiges Review des Diffs (CMake-/Tooling-Edits sind Fork-Code)
- [ ] Engine-Build auf eris (g++-13-Pflicht!) + Smoke-Inferenz
- [ ] A/B-Benchmark (erwartbar NO_SIGNAL — Inhalte identisch, nur Layout)
- [ ] Rollback-Bereitschaft (`previous`-Symlink)
- [ ] Uranus-Rollout (CUDA-13.0-Pfad explizit!) + Smoke beider Hosts
- [ ] Doku: UPSTREAM_SYNC_STATUS Rückstand, LOKAL.md, TTT, Trilium
