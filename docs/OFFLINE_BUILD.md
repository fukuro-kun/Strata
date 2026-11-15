# OFFLINE_BUILD — Fork-Build-Pfad (P1)

Kanonischer Build-Einstieg dieses Forks. **Niemals** `setup.py`, `setup.sh`,
`START-HERE.bat`, `update.sh` oder `docker-entrypoint.sh` verwenden — die Fork-
Pfade laufen komplett offline; Beschaffung ist ein separater, dokumentierter
Schritt.

**Acquisition-Gate (Fork):** Upstreams Terminal-/App-Primitiven (Download,
Update, Launch-Acquisition, pip, Compile) laufen allesamt über
`strata_control/acquisition.require()`. Der Fork verweigert jede davon per
Default (`ForkAcquisitionRefused`, Exit 5) — Ausnahme nur für bewusst
reviewte Beschaffung mit `STRATA_FORK_ALLOW_ACQUIRE=1` (exakter String),
niemals produktiv. `STRATA_NO_ACQUIRE` und der `forbidden()`-Kontext
gewinnen immer. `run_server.sh` exportiert `STRATA_NO_ACQUIRE=1` und
`STRATA_NO_HANDOVER=1`.

Das Gate gilt auch für eine **lokale Paketinstallation**
(`updater.install_engine_file`, das explizite CLI-Paket): ein signiertes
Upstream-Engine-Paket auf Disk ist trotzdem Beschaffung — die Signatur
prüft Integrität, keine Freigabe. Die Fork-Build-Skripte
(`tools/offline/…`) bleiben davon separat: sie sind Shell-Verträge
außerhalb der Python-Umgebung und laufen ohne das Env-Gate.
Die Offline-Skripte `fetch_llamacpp.sh` / `fetch_wheels.sh` bleiben der
dokumentierte Beschaffungspfad; sie nutzen keine Terminal-Download-Primitiven.
Der DSV41-Pfad folgt demselben Gate: lokale Paketinstallation,
Remote-Download/Upgrade und die Remote-Erreichbarkeitsprobe laufen ueber
`acquisition.require()`; die lokale Read-Only-Probe (existierende Datei/Ordner)
bleibt davon frei. Der MCP-Modellinstaller und sein Hintergrundjob
brauchen vor State-/Spec-/Venv-Zugriff dasselbe Gate; `STRATA_NO_ACQUIRE`
wird fuer Control-Kinder nicht mehr entfernt — Allow ueberstimmt den
Stopp weiterhin nicht. Auch die CUDA-12-Treiberfloor-Abfrage
(`driver_floor.from_feed`) liest den signierten Feed nur noch nach dem
Gate; installierte lokale Metadaten und der konstante Fallback brauchen
kein Allow.

Die Windows-HIP-Geraeteprobe `hip_devices` repariert den Engine-Ordner
nicht mehr nebenbei. Die explizite Installationspruefung `hip_card`
kopiert die benoetigten lokalen Runtime-DLLs weiterhin vor der Probe.
Das ist kein Beleg, dass die gesamte Terminal-Planung schreibfrei ist;
andere Settings-/Datei-Nebenwirkungen werden getrennt geprueft.

Auch die direkten Metal-Buildhelfer pruefen vor Build-Vorbereitungen
das Beschaffungs-Gate. Beim SYCL-Bildleser liegt es bereits vor dem
Laden der oneAPI-Umgebung. Gueltige vorhandene Backend-Artefakte koennen
ohne Neubau weiterverwendet werden. Die Backend-Einstiege melden eine
Beschaffungsverweigerung mit Exit 5 statt einem Traceback.

Der eigenstaendige Helfer `tools/mtp_fetch.py` prueft Metadaten- und
Tensorbeschaffung ebenfalls am Fork-Gate, auch bei direktem CLI-Aufruf.
Sein `verify` bleibt offline ohne Allow nutzbar; er kann dabei den
lokalen Verifikationscache schreiben. Der Root-Setup-Aufruf war schon
vor dieser Absicherung durch dessen `run`-Gate geschuetzt.

## Prinzip

1. **Vendored Quellen** (im Repo, kein Download nötig): die llama.cpp-Quellen
   liegen seit dem `strata-*`-Layout in getrennten, per-Manifest verifizierten
   Bäumen am selben Pin (`LLAMA_CPP_COMMIT` aus `setup.py`, aktuell
   `3cf03257f219afbe7334045ff7c6a06ac68c627d`):

   | Baum | Zweck |
   |---|---|
   | `third_party/strata-ggml` | Engine-ggml (base/cpu/cuda) + `ggml-cuda-tq` (Trellis-Typen, patched/additive Kopien) |
   | `third_party/strata-llama` | llama.cpp-Untermenge für `strata-vision` (`LLAMA_DIR`-Default) |
   | `third_party/strata-gguf-py` | gguf-py für Pack-/Konverter-Tools (`tools/_paths.py`) |
   | `third_party/ggml`, `third_party/stb` | schlanke Header-/Pin-Referenzen |

   `tools/check_vendored.py` hasht **jede** Datei gegen das UPSTREAM.md-Manifest
   (Klassen `upstream/edited/added/copy/patched`; `patched` muss rein additiv
   sein) und lehnt ungelistete Dateien ab. Das ist strenger als der frühere
   `.strata-pin`-Marker: ein ausgetauschtes oder hinzugefügtes File fällt sofort auf.

   `tools/offline/fetch_llamacpp.sh` bleibt der dokumentierte Beschaffungspfad
   für einen **vollständigen** llama.cpp-Checkout — nur noch nötig für
   `-DSTRATA_GGML_DIR=<checkout>`-Override-Builds (Review-/Vergleichsbuilds).

2. **Build** (offline, fail closed): `tools/offline/build_engine.sh` prüft alle
   Inputs *vor* dem Start; fehlt etwas → Abbruch mit Klartext, niemals Download.

## Beschaffung (nur für Override-/Dev-Builds)

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
ersetzt. `build_engine.sh` lehnt einen Override-Baum ohne Pin-Beweis ab — und
bei einem echten git-Checkout zusätzlich einen *dirty tree* (Checkout am Pin mit
lokalen Änderungen baut unverifizierten Code → Abbruch).

## Build

```bash
tools/offline/build_engine.sh                    # CUDA auto-detect, Vision cpu
tools/offline/build_engine.sh --cuda off         # reiner CPU-Build
tools/offline/build_engine.sh --arch 89 --vision gpu   # GPU-Vision statt cpu/off
```

Was das Skript tut:

- Pin-Beweis des ggml-Baums: vendored `third_party/strata-ggml` →
  `tools/check_vendored.py` (per-Datei-Hashes + Manifest-Pin == `LLAMA_CPP_COMMIT`);
  Override-Baum → `.strata-pin` bzw. `git rev-parse HEAD` + sauberer Tree —
  **Abbruch bei Mismatch oder fehlendem Beweis**.
- Konfiguriert exakt wie der Upstream-Local-Build (`cmake -G Ninja
  -DSTRATA_ENABLE_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=<sm>`); `STRATA_GGML_DIR`
  wird nur gesetzt, wenn der Aufrufer einen Override exportiert — leer
  bedeutet vendored Baum (und dessen `ggml-cuda-tq`, nicht das Overlay).
  Plus `-DCUDAToolkit_ROOT` wenn nvcc nicht unter `/usr` liegt.
- Baut `strata` (ein Retry wie upstream bei CUDA-13-ptxas-Flake), danach
  `strata-vision` aus `tools/vision` (eigener CMake-Baum, `LLAMA_DIR`-basiert —
  ohnehin fetch-frei).
- Staged nach `engine/` (`strata`, ggf. `libstrata_kq.so`, `strata-vision`) und
  schreibt `engine/BUILD.json` im Upstream-Format + Fork-Felder
  (`source: "local-fork"`, `ggml_commit`, `ggml_dir`).

## Python-Abhängigkeiten (P2)

Die Server-/Toolchain-Python-Deps laufen aus einem lokalen Wheelhouse —
`setup.py` wird nie aufgerufen, PyPI wird nie kontaktiert.

```bash
# Beschaffung (bewusst, einmalig; ggf. je Interpreter-Version einmal):
tools/offline/fetch_wheels.sh                      # für dieses Python
tools/offline/fetch_wheels.sh --for-python 3.12    # für ein anderes (binary-only)

# venv aus dem geprueften Wheelhouse:
tools/offline/make_venv.sh                         # CUDA-Wheels auto nach nvcc
tools/offline/make_venv.sh --cuda 12|none          # oder explizit

# Start ohne setup.py:
tools/offline/run_server.sh strata-<modell>.json [--port N]
tools/offline/run_server.sh --mock --port N        # API-Smoke ohne Engine
# Kalibrierung:
tools/offline/calibrate.sh strata-<modell>.json
# Neue Run-Config auf einem frischen Host:
python3 tools/offline/make_config.py NAME --pack DIR --native GGUF ...
```

- `wheelhouse/*.whl` sind gitignored (LAN-Kopie via rsync/Netzlaufwerk);
  `wheelhouse/MANIFEST.sha256` ist committed — `make_venv.sh` verifiziert das
  Wheelhouse gegen eine private Kopie des Manifests **vor** der Installation.
  Eine daraus erzeugte Pin-/Hashliste bindet jedes installierte Wheel auch
  bei der Installation an diese Kopie. Nicht aufgefuehrte Archive und
  manipulierte Wheels werden abgelehnt.
- Python laeuft mit bereinigter Umgebung und `-I`; pip nutzt `--isolated`,
  `--no-index`, `--no-deps`, `--only-binary` und `--require-hashes`.
  Direkte URLs, weitere Quellen und nicht exakt gepinnte Requirements
  werden abgelehnt. Nach Installation prueft `pip check` die vorhandenen
  Abhaengigkeiten, ohne weitere Pakete aufzulösen oder nachzuladen.
- Der Lock-Generator akzeptiert nur feste `==`-Pins und die derzeit
  verwendeten einfachen `python_version`-/`sys_platform`-Marker.
  Andere Requirements-Syntax muss vor einer Erweiterung geprueft werden.
  Die kleinen Manifest- und Lockdateien bleiben als Installationsnachweis
  in einem privaten Temporaerverzeichnis und nach Erfolg auch in der Venv;
  sie werden weder als `PYTHONPATH` noch als ausfuehrbarer Code verwendet.
- Das Manifest, die Requirements, Python, `ensurepip`/pip und die
  Systembibliotheken sind Vertrauensanker. Hashgleichheit beweist nicht
  deren Herkunft; gepruefte, vor gleichzeitigen Schreibzugriffen
  geschuetzte Inputs und eine isolierte Testumgebung bleiben erforderlich.
  Eine Venv und `--no-index` sind keine Netzwerk-Sandbox.
- Die Python-Pins stehen in `requirements.txt` und
  `requirements-build.txt`; die CUDA-Laufzeit-Pins (`nvidia-cublas`/
  `nvidia-cuda-runtime`, cu13 und cu12) liest das Skript aus `setup.py`,
  ohne dessen Installer zu starten. Auto-Erkennung sucht `nvcc` nur auf
  dem begrenzten Werkzeugpfad; bei anderem CUDA-Installationsort
  `--cuda 12` oder `--cuda 13` ausdruecklich setzen.
- `run_server.sh` validiert die Config (exe existiert, Datei-Flags in args
  wie `--pack`/`--native`/`--mtp` geprüft — `--mtp <n>` für own-path-Modelle
  wird korrekt übersprungen, tokenizer mit vocab/merges/token_type) und
  bricht bei fehlendem Input mit Klartext ab — nie ein Fallback auf
  setup.py.

## Fail-closed-Garantien

- `CMakeLists.txt` hat **keinen** FetchContent-Pfad mehr: leeres
  `STRATA_GGML_DIR` resolve-t auf den vendored In-Repo-Baum
  (`third_party/strata-ggml`); der frühere `STRATA_ALLOW_GGML_FETCH`-Escape
  ist entfernt — Netz-Beschaffung zur Configure-Zeit ist strukturell
  unmöglich, nicht nur abgeschaltet. `sycl/CMakeLists.txt` analog.
- `tools/vision/CMakeLists.txt` hat keinen Fetch-Pfad (`LLAMA_DIR` default
  `third_party/strata-llama`) — fehlender Baum bricht nativ ab.
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
