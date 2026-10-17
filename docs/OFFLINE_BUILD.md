# OFFLINE_BUILD — Fork-Build-Pfad (P1)

Kanonischer Build-Einstieg dieses Forks. **Niemals** `setup.py`, `setup.sh`,
`START-HERE.bat`, `update.sh` oder `docker-entrypoint.sh` verwenden — die Fork-
Pfade laufen komplett offline; Beschaffung ist ein separater, dokumentierter
Schritt.

## Prinzip

1. **Beschaffung** (einmalig, bewusst, dokumentiert): `tools/offline/fetch_llamacpp.sh`
   legt `third_party/llama.cpp` am gepinnten Commit an (`LLAMA_CPP_COMMIT` aus
   `setup.py`, aktuell `3cf03257f219afbe7334045ff7c6a06ac68c627d`) und markiert
   es mit `.strata-pin`.
2. **Build** (offline, fail closed): `tools/offline/build_engine.sh` prüft alle
   Inputs *vor* dem Start; fehlt etwas → Abbruch mit Klartext, niemals Download.

## Beschaffung (Quellen, Präferenzreihenfolge)

```bash
# A) Vorhandener Baum (z. B. per rsync vom LAN-Host). Pin-Nachweis nötig:
#    .strata-pin der Quelle ODER sauberer git-Checkout am Pin; andernfalls
#    bricht das Skript ab — bewusste Ausnahme per --allow-unverified.
tools/offline/fetch_llamacpp.sh --from-dir /pfad/zu/llama.cpp

# B) Lokaler git-Clone, der den Pin-Commit enthält (kein Fetch —
#    GIT_NO_LAZY_FETCH=1 lässt Partial-Clones failen statt still nachzuladen):
tools/offline/fetch_llamacpp.sh --from-git /pfad/zu/clone

# C) Klonen von upstream — bewusste Netz-Beschaffung, einmalig:
tools/offline/fetch_llamacpp.sh --clone
```

Jeder Modus verifiziert danach `ggml/CMakeLists.txt`, `gguf-py/` und schreibt
`.strata-pin` mit dem erwarteten Commit. Pin-Nachweise werden **vor** dem
Kopieren geprüft; ein bestehendes `third_party/llama.cpp` wird nie still
ersetzt. `build_engine.sh` lehnt Bäume ohne Pin-Beweis ab — und bei einem
echten git-Checkout zusätzlich einen *dirty tree* (Checkout am Pin mit lokalen
Änderungen baut unverifizierten Code → Abbruch).

**Historischer Beleg:** die Produktiv-`third_party/llama.cpp`-Bäume zweier
unabhängig eingerichteter Hosts sind byte-identisch (2824 Dateien, einzig
`__pycache__` unterscheidet sich je nach Python-Version) — siehe P0-Inventar.

## Build

```bash
tools/offline/build_engine.sh                    # CUDA auto-detect, Vision cpu
tools/offline/build_engine.sh --cuda off         # reiner CPU-Build
tools/offline/build_engine.sh --arch 89 --vision gpu   # GPU-Vision statt cpu/off
```

Was das Skript tut:

- Prüft `.strata-pin` bzw. `git rev-parse HEAD` + sauberen Tree des ggml-Baums
  gegen den Pin — **Abbruch bei Mismatch oder fehlendem Beweis**.
- Konfiguriert exakt wie der Upstream-Local-Build (`cmake -G Ninja
  -DSTRATA_ENABLE_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=<sm> -DSTRATA_GGML_DIR=…`),
  plus `-DCUDAToolkit_ROOT` wenn nvcc nicht unter `/usr` liegt.
- Baut `strata` (ein Retry wie upstream bei CUDA-13-ptxas-Flake), danach
  `strata-vision` aus `tools/vision` (eigener CMake-Baum, `LLAMA_DIR`-basiert —
  ohnehin fetch-frei).
- Staged nach `engine/` (`strata`, ggf. `libstrata_kq.so`, `strata-vision`) und
  schreibt `engine/BUILD.json` im Upstream-Format + Fork-Felder
  (`source: "local-fork"`, `ggml_commit`, `ggml_dir`).

## Fail-closed-Garantien

- `CMakeLists.txt` + `sycl/CMakeLists.txt`: leeres `STRATA_GGML_DIR` →
  `FATAL_ERROR` statt `FetchContent`-Download. Escape nur über
  `-DSTRATA_ALLOW_GGML_FETCH=ON` (für P4-Review-Builds gedacht).
- `tools/vision/CMakeLists.txt` hat keinen Fetch-Pfad (`LLAMA_DIR` default
  `third_party/llama.cpp`) — fehlender Baum bricht nativ ab.
- Das Skript enthält keinerlei Netz-Aufrufe (kein pip, kein curl, kein apt).
- Ein alter Build-Cache mit abweichenden Optionen (`CMAKE_CUDA_COMPILER`,
  `STRATA_GGML_DIR`, `STRATA_ENABLE_CUDA`) wird erkannt und entfernt — sonst
  würde CMake den Cache mitten im Configure verwerfen und die `-D`-Flags im
  Re-Run verlieren (beobachtet: `STRATA_GGML_DIR` leer → Fail-closed-Fehler).

## Verifikation (Nachweis 2026-10-18, Build/Dev-Host)

- Configure-Log enthält **keinen** `Cloning`/`Fetching`-Eintrag; ggml aus dem
  lokalen Baum (`ggml version 0.24.0`). Achtung: die Log-Zeile `ggml commit:
  14dcd1d3` zeigt bei einem entpackten (nicht-git) Baum irreführend den
  HEAD des *Parent-Repos* — maßgeblich ist `.strata-pin`/`BUILD.json`.
- Engine-Binaries der Produktiv-Hosts tragen `engine/BUILD.json src =
  7dfd34378bd2d32a` / `vision_src = 13d9deaf827f14ef` — identisch mit dem
  `source_hash()`-Fingerprint des auditierten Baseline-Baums: bestehende
  Engines sind kryptografisch an den gepinnten Quellbaum gebunden.
- Fork-Build `src = b5006933b295d641` (abweichend erwartbar — die
  Fail-closed-CMake-Patches gehören zum gehashten Fork-Source), `vision_src`
  identisch `13d9deaf827f14ef`.
