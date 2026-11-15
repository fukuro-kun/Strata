# ANALYSIS — Upstream `strata-*`-Vendoring (RADAR_2026-11-15, Strukturbruch Punkt 1)

**Status: statische Analyse auf gefetchten Objekten (`baf16363b`), kein
Checkout, kein Import. Kein Merge, kein Deploy.**

## Was Upstream vendored hat

| Baum | Zweck | Inhalt | Pin |
|---|---|---|---|
| `third_party/strata-llama` | **Vision** (`strata-vision`/mtmd) | llama.cpp-Untermenge: `src`,`include`,`tools/mtmd`,vendor-bits,volles `ggml` (cpu/cuda/hip/sycl/metal/blas),cmake,Lizenzen — ~900 Dateien | `3cf03257` byte-rein, keine Edits |
| `third_party/strata-ggml` | **Engine** | ggml-Untermenge: ggml-base + ggml-cpu + ggml-cuda-MMQ + `ggml-cuda-tq/` (Trellis-Typen eingefaltet) + getrimmtes CMake + `strata-quant-common.h` — ~600 Dateien | `3cf03257` + dokumentierte Strata-Edits |
| `third_party/strata-gguf-py` | Pack-/Konvertier-Tools | gguf.py-Konverter — ~80 Dateien | `3cf03257` |
| `third_party/ggml` | **Pin-Anker** | nur `VERSION.txt` (= `3cf03257`), LICENSE, 2 Header | — |
| `tools/check_vendored.py` | **Pin-/Edit-Wächter** | verifiziert jede Datei gegen `UPSTREAM.md`-Manifest (`upstream/edited/added/copy/patched`, LF-SHA256) | — |

**Gelöscht:** `third_party/llama.cpp`, `third_party/ggml-tq`,
`third_party/project-maya`. `-DSTRATA_GGML_DIR=<checkout>` und
`-DLLAMA_DIR=<checkout>` bleiben als Override (2 Releases, dann weg).

## Verifizierter Befund: identischer Pin

`strata-ggml/ggml/src/ggml-cuda/mmq.cuh` SHA-256 =
`50db23f5...` = **byte-identisch** zu unserem gepinnten
`third_party/llama.cpp/ggml/src/ggml-cuda/mmq.cuh`. Der vendored Inhalt
ist dasselbe llama.cpp `3cf03257`, das wir heute bauen — die
Material-Frage ist also nicht „neue Quelle", sondern **Layout +
Trimming + Upstream-Edits**.

## Vergleich mit unserem Pin-Prozess

| Aspekt | Unser Fork heute | Upstream neu |
|---|---|---|
| Quelle | `third_party/llama.cpp` (voller Baum, `.strata-pin`) | `strata-llama` + `strata-ggml` (2 getrimmte Untermengen) |
| Pin-Nachweis | `.strata-pin` + `ggml/VERSION.txt`, geprüft von `fetch_llamacpp.sh`/`make_manifest.py` | `UPSTREAM.md` je Baum + `check_vendored.py` (per-Datei-Manifest, Hash-Klassen inkl. „patched = jede Gegenstück-Zeile noch da") |
| Trellis-TQ | `third_party/ggml-tq/` + Configure-Overlay (`strata_ggml_tq_overlay.cmake` schreibt gepatchte Header in den Build-Baum) | **eingefaltet** als echte Dateien in `ggml-cuda-tq/` + `patched`-Header |
| Fetch-Verhalten | `STRATA_GGML_DIR` Pflicht, FetchContent fail-closed OFF | vendored (kein Fetch nötig), Override optional |
| Engine-Inputs | llama.cpp `ggml/`-Teilbaum + Overlay-Ausgabe | `strata-ggml` (gleiche Quellen, Trimming dokumentiert) |

Upstream ist unserem Modell konvergiert: **gepinnter, offline-baubarer,
manifestierte Third-party-Stand** — mit einem stärkeren Verifikator
(`check_vendored.py` hasht jede Datei einzeln und prüft, dass
`patched`-Dateien nur Additiv sind).

## Was das für uns bedeutet

**Übernahme der Layout ist sinnvoll** (Divergenz-Ziel: nah an Upstream,
weniger Baum zu pflegen, stärkerer Verifikator) — aber drei Punkte sind
Vorbedingungen, keine Details:

1. **Review der Upstream-Edits in `strata-ggml`.** Der Baum ist NICHT
   byte-rein: getrimmtes `ggml/CMakeLists.txt` + `ggml/src/CMakeLists.txt`,
   `patched`-Header (`ggml.h`, `mmq.cuh`, `mmq-load-tiles.cuh`,
   `mmq-config-*.cuh` — TQ-Enumeratoren/Routings), `added`
   (`tq.cuh`, `tq-mmq-tiles.cuh`, `mmq-instance-*.cu` — aus dem
   agentionai-Fork, MIT), `strata-quant-common.h` (1 Metal-Edit).
   `check_vendored.py` bescheinigt nur Struktur, nicht Semantik — die
   `edited`/`patched`/`added`-Zeilen brauchen Diff-Review gegen unser
   Overlay-Ergebnis und den agentionai-Ursprung.
2. **Unsere Tooling-Anbindung umbauen.** `fetch_llamacpp.sh`,
   `make_manifest.py` (`.strata-pin`-Check), `deploy_local.sh`
   (Pin-Nachweis) und `build_engine.sh` (`STRATA_GGML_DIR`-Pflicht)
   zeigen heute auf `third_party/llama.cpp`; bei Übernahme zeigen sie
   auf die `UPSTREAM.md`-Pins bzw. rufen `check_vendored.py`.
   Fail-closed-Verhalten muss erhalten bleiben.
3. **Vision-Build-Äquivalenz.** Unser `strata-vision` kommt heute aus
   demselben Pin — `strata-llama` ist byte-rein, aber die
   `tools/vision/CMakeLists.txt`-Verdrahtung (`LLAMA_DIR`-Default)
   braucht Abgleich mit unserem Build-Aufruf.

**Offen (nicht Teil dieser Analyse):** Inhalt aller ~600 Dateien von
`strata-ggml` (nur `mmq.cuh` + Manifest-Struktur geprüft), alle Edits in
`edited`/`patched`/`added`-Klassen, `strata-gguf-py`-Nutzung,
ob `check_vendored.py` in unserem Build/CI-Aufruf eingehängt wird,
MMQ-Tab-Mirror-Referenz (`moe_mmq_tab.cuh`) gegen den unveränderten
Scheduler-Block.

## Empfehlung

Übernahme des Vendoring-Layouts in einem eigenen `integrate`-Schritt:
(1) `check_vendored.py`-Lauf gegen unseren Pin als Byte-Beleg,
(2) Diff-Review der `edited/patched/added`-Klassen,
(3) Tooling-Umbau (fetch→verify, deploy-pin→UPSTREAM.md),
(4) Engine-Build-Vergleich alt-vs-neu (Binary-Diff/Funktionsprobe),
(5) erst dann `third_party/llama.cpp`+`ggml-tq`+Overlay entfernen.
Vorab keine Übernahme in `main`; die Analyse ist Beobachtung.
