# INVENTAR — Fork-Baseline P0

**Stand:** 2026-10-18 (Erhebung 2026-10-17/18). Erstellt in Solo-Session P0 gemäß
`SOLO_SESSION_001_p0_inventar.md`. Ergänzt die Doku-Tabelle in `AGENTS.md`.

**Pinned Baseline:** `296b59d2f73c8f04a805df29c2fa97655adace78` — Version `0.1.44.1`.
Verifikation: Tree-Diff gegen den unabhängigen Audit-Checkout (gleiche SHA) ergab
**keine inhaltlichen Differenzen**; einzige Abweichungen sind Fork-eigene Dateien
(`ROADMAP.md`, `docs/SOLO_SESSION_*`, `AGENTS.md`, diese Datei). Ein bereits laufender
Upstream-Produktiv-Checkout im LAN steht exakt auf dieser SHA. Stichproben
(HF-Revisions-Pins, `LLAMA_CPP_COMMIT`, FetchContent-Pfad) gegen Audit-Behauptungen:
**bestätigt**.

Status-Labels: **[gemessen]** = auf realen Hosts verifiziert, **[Code]** = aus
Quelltext belegt, **[Beleg]** = externer Hash-/Prüfbeleg existiert, **[Lücke]** = offen.

**Privatsphäre:** Hostnamen, LAN-Pfade, Service-Details und lokale Hash-Manifeste
stehen bewusst **nicht** in dieser committed Datei — sie liegen in `LOKAL.md`
(gitignored) und den referenzierten internen Notizen. Hier steht alles, was für
Reproduktion und Review öffentlich sein darf: Quellen, Pins, Hashes der öffentlichen
Artefakte, Toolchain-Anforderungen, gemessene Toolchain-Versionen (anonymisiert nach
Rolle) und die Offline-Lücken.

---

## 1. Quell-Inventar

Komplett-Clone (nicht shallow), keine Submodules, keine CI-Workflows
(`.github/` enthält keine Actions). C++20, CMake ≥ 3.24.

| Pfad | Inhalt |
|---|---|
| `src/` | Engine-Implementierung inkl. `*_test.cpp` Inline-Tests |
| `include/` | Öffentliche Header |
| `cmake/` | Find-Module/Optionen |
| `sycl/`, `metal/` | Intel-SYCL- bzw. experimentelles Apple-Metal-Backend |
| `serve/` | Python-Server (OpenAI- + Anthropic-kompatible API), `serve/web/` statisches Frontend |
| `tools/` | Build-/Pack-/Kalibrier-Tools (`iq_pack.py`, `mtp_fetch.py`, …) |
| `tests/` | Native Test-Suite |
| `data/` | Eingecheckte Binärdaten: `expert-profile{,-coder,-sycl}.bin`, `draft_vocab*.bin`, `gguf_fingerprints.json`, `quant_quality/v1/` Testsätze, `experimental-speed-projection/` (**Qwen Community License, nicht MIT**) |
| `third_party/ggml/` | **Kein** vollständiger llama.cpp-Checkout — nur Lizenz-/Versionsmetadaten + `ggml-common.h` |

Build-Targets: `strata`, `strata-vision`, `strata_core`, `strata_kernels`,
`strata_prefill`, `strata_engine`, Qwen35- und Utility/Test-Targets.

**Offline-Nahtstelle:** `-DSTRATA_GGML_DIR=<lokaler llama.cpp-Checkout>`
umgeht `FetchContent` (sonst Download zur Configure-Zeit). llama.cpp-Pin:
`LLAMA_CPP_COMMIT` in `setup.py`; Hash des Commit-Strings bildet den
Verzeichnisnamen im Cache. **[gemessen/Code]**

---

## 2. Abhängigkeits-Inventar

### 2.1 Python (`requirements.txt`, für `.venv`, Python ≥ 3.10)

```
numpy==2.5.3 (py>=3.12) | 2.4.6 (py3.11) | 2.2.6 (<3.11)
jinja2==3.1.6  regex==2026.9.10  pyyaml==6.0.3  tqdm==4.70.1
requests==2.34.2  cmake==4.4.3  ninja==1.13.2  pillow==12.3.0  psutil==7.2.2
markupsafe==3.0.3  certifi==2026.7.22  charset-normalizer==3.5.1
idna==3.20  urllib3==2.8.0  colorama==0.4.6 (win32)
```

Keine Hash-Pins in der Datei — pip resolved nur nach Version. **[Code]**
→ P2-Wheelhouse pinnt zusätzlich SHA256.

### 2.2 Build-System-/Compiler-Abhängigkeiten

C++20-Compiler (gcc ≥ 11 / clang / MSVC), CMake ≥ 3.24, Ninja, Python ≥ 3.10,
CUDA-Toolkit (NVIDIA-Pfad), HIP/ROCm (AMD), oneAPI/SYCL (Intel),
Vulkan-SDK optional (Version + SHA256 gepinnt in `setup.py`).

### 2.3 Vendored/gestreamte Komponenten

- **llama.cpp** via FetchContent/`STRATA_GGML_DIR`, Commit-Pin `LLAMA_CPP_COMMIT`
  in `setup.py`.
- **Engine-Prebuilt-Archive** via GitHub-Releases (Digest über Runtime-API-Aufruf;
  `STRATA_SKIP_SHA256=1` umgeht den Check komplett; Digest-Fetch-Fehler → Warnung
  statt Abbruch = **Fail-open**). **[Code]**
- **`data/expert-profile*.bin`, `draft_vocab*.bin`**: eingecheckt, versioniert.

---

## 3. Lizenz-Inventar

| Komponente | Lizenz |
|---|---|
| Projekt-Root | MIT |
| `third_party/ggml` | MIT |
| `data/experimental-speed-projection/` | **Qwen Community License 1.0** (kein MIT!) |
| Outfit-Font (`serve/web/`) | SIL OFL 1.1 |
| Modell Qwen3.8-Flash-Next / NVFP4-GPTQ-Pack | Qwen Community License 1.0 |
| NVFP4-NVIDIA-Pack | NVIDIA Open Model License + Qwen CL 1.0 |
| Swift 1.5 (ukisai, SC117-Ableitungen) | Swift Open License 1.0 |
| Qwen3.6-35B-A3B | Apache 2.0 |

---

## 4. Toolchain-Inventar **[gemessen, 2026-10-17]**

Vier LAN-Hosts wurden erhoben; Rollen anonymisiert (Details + Hostnamen: `LOKAL.md`).

| | Build/Dev-Host | Inferenz-Host A | Inferenz-Host B | Archiv-Host |
|---|---|---|---|---|
| OS | Ubuntu 26.04.1 | Ubuntu 24.04.5 | Ubuntu 26.04.1 | Debian 11 |
| CPU | i7-12700H | i7-9700K | i9-11900H | Intel N100 |
| RAM | 62 GiB | 125 GiB | 31 GiB | 4 GiB |
| GPU | RTX 3070 Laptop 8 GiB (sm_86) | **2× RTX 4060 Ti 16 GiB** (sm_89) | RTX 3080 Laptop 16 GiB (sm_86) | — |
| Treiber | 595.91.07 | 595.99.02 | 595.91.07 | — |
| gcc/g++ | 13.4.0 | 13.3.0 (+ clang 20.1.2) | 15.2.0 | 10.2.1 |
| cmake | 3.31.10 | 3.28.3 | 4.2.3 | — |
| ninja | 1.13.2 | 1.11.1 | — | — |
| python3 | 3.14.4 | 3.12.3 | 3.14.4 | 3.9.2 |
| CUDA-Toolkit | 13.4 | 12.0 (PATH), 13.0 + 13.2 unter `/usr/local/` | 12.4 | — |
| HIP | nein | nein | nein | — |
| Storage frei | ~254 GiB | ~20 TiB | ~105 GiB (89% belegt) | ~726 GiB (ZFS-Archiv) |

Befund: Der Build/Dev-Host liegt unter der 12-GiB-VRAM-Mindestanforderung →
kein Inferenz-Ziel. Der Archiv-Host ist zu schwach für Builds → reines
Cold-Storage. Produktive Inferenz läuft auf Host A (2×16 GiB, Multi-GPU) und
Host B (1×16 GiB). Engine-Binaries auf beiden Inferenz-Hosts sind **bereits
lokal gebaut** (`engine/BUILD.json: "source": "local"`, archs 89 bzw. 86,
Version 0.1.44.1) — kein Prebuilt-Download im Produktiveinsatz. **[gemessen]**

---

## 5. Provenienz — Modelle & Artefakte

### 5.1 Upstream-Pins **[Code]**

| Artefakt | HF-Repo | Revision-Pin | Per-File-SHA256 in `setup.py`? |
|---|---|---|---|
| ISTA-DASLab GSQ-RCO | `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF` | gepinnt (`hf()`-Helper) | **nein** — nur Repo-Rev + Größe |
| Swift 1.5 (ukisai) | `ukisai/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF` | gepinnt | **nein** |
| Coder | `ISTA-DASLab/...-GSQ-RCO-Coder-GGUF` | gepinnt | **nein** |
| Unsloth-Shards (UD-*, Q8_0) | `unsloth/Qwen3.8-Flash-Next-GGUF` | gepinnt | **ja** (`UNSLOTH_*_SHARDS`, setup.py:312–370) |
| NVFP4-Packs (sergqwer, NVIDIA) | je eigene Revision (`640a1db9…`, `cca8f7fe…`) | gepinnt | **ja** (`NVFP4_REPOS`, setup.py:222–239) |
| Qwen3.6-35B-A3B | `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` | gepinnt | **ja** (`QWEN36_FILES`, setup.py:432–437) |
| MTP-Draft-Tensoren | `Qwen/Qwen3.8-Flash-Next` | `de4b8e4d…` (`PINNED_REVISION`, `tools/mtp_fetch.py:32`) | **ja**, pro Tensor |

→ **Lücke:** ISTA-DASLab GSQ-RCO, Swift (ukisai **und** SC117-Ableitungen) und
Coder haben **keine** per-File-SHA256 — nur Repo-Revision + Größe. Genau diese
Gruppe läuft produktiv. Das P3-Manifest muss sie mit eigenen Hashes schließen.
**[Lücke]**

### 5.2 Vorhandene externe Hash-Belege **[Beleg]**

Lokal existieren frühere Verifikations-Artefakte (Ablageort: `LOKAL.md`):
HF-verifizierte SHA256-Manifeste für die SC117-Quants IQ2_XS/IQ3_XXS/Q2_0
(21 LFS-Hashes + 24 Größen-/Blob-Checks, Revision
`2b89cf3f7f2d9cb84275439e2c0cda83db15d32f`), je ein Expected-Manifest für
drei Hosts, HF-Tree-Snapshot, Coder-IQ1_M-Verifikation + Release-Manifest,
Storage-Probe mit 9-Shard-Hashgleichheit gegen HF-Belege.

### 5.3 Frisch gehashte Aktiv-Artefakte **[gemessen]**

SHA256SUMS-Läufe über alle auf den Inferenz-Hosts aktiven GGUF-Sets, Pack-
Verzeichnisse, MTP-Runtime-Daten, `expert-profile.bin` und die Engine-Binaries.
Ergebnis-Dateien: lokale Evidenz-Ablage (Pfad in `LOKAL.md`); die daraus
abgeleitete Artefakt-Tabelle (Dateiname→SHA256, hostneutral) wird in P3 in das
committed Modell-Manifest übernommen. Das ~586-GB-Cold-Storage-Archiv wurde nicht
erneut gehasht — HF-verifizierte Belege existieren (5.2).

### 5.4 Artefakt-Rollen

- **Produktiv-GGUFs:** SC117-abliterated Swift 1.5 (IQ3_S, IQ2_XS), UkisAI
  Swift 1.5 (IQ3_S, IQ2_XS); je 2 Shards + BF16-mmproj + `strata/rt` MTP-Laufzeit.
- **Packs:** lokal via `tools/iq_pack.py` gebaute Expert-Caches
  (pro Quant ein Pack-Verzeichnis).
- **Archiv-Bestand:** ISTA-DASLab GSQ-RCO (mehrere Quants), SC117-abliterated
  (IQ2_XS/IQ3_XXS/IQ3_S/Q2_0), UkisAI, Coder-IQ1_M, Unsloth UD-IQ4_XS + MTP.
- **`data/expert-profile*.bin`**: im Repo eingecheckt (kalibriertes Expert-Profil).

---

## 6. Netzwerk-Endpunkte (Referenz für P1/P2-Offline-Guard)

| Endpunkt | Zweck | Fork-Pfad-Status |
|---|---|---|
| `github.com`/`codeload` | llama.cpp-Zip/Clone, Engine-Release-Assets, Release-API (Digest) | **blocken** |
| `huggingface.co` (+`HF_ENDPOINT`-Mirror, `cdn-lfs*`) | GGUFs, mmproj, MTP-Tensoren | **blocken** |
| `www.modelscope.cn` (`STRATA_SOURCE`) | Alternative Modellquelle | **blocken** |
| `pypi.org` + Wheel-Indexe (inkl. torch CUDA/ROCm) | Python-Deps | **blocken** |
| `developer.download.nvidia.com` | CUDA-Toolkit | manuelle Beschaffung |
| `sdk.lunarg.com` | Vulkan-SDK (gepinnt + gehasht) | manuelle Beschaffung |
| `python.org`, `apt`, `winget` | Runtime/OS-Pakete | manuelle Beschaffung |

Fork-Pfade (P1/P2) dürfen **keinen** dieser Endpunkte automatisch aufrufen —
Beschaffung nur via dokumentiertem, gepinntem Beschaffungs-Lauf.

---

## 7. Bestands-Deployments im LAN **[gemessen — Details: `LOKAL.md`]**

- **Inferenz-Host A (Produktiv, 2 GPU):** Upstream-Checkout auf Baseline-SHA,
  lokal gebaute Engine (sm_89). Aktiv: SC117-Swift IQ3_S, 262144 ctx,
  `--kv int8 --ple-io ram --kv-resident 32768 --vision --spec 4 --spec-min-p 0.7`
  + adaptive Prefill-Tuning-Flags, systemd-Unit + zusätzlicher Test-Service und
  **laufender Quant-Eval** → Umstellung erst nach Eval-Ende.
- **Inferenz-Host B (Produktiv, 1 GPU):** Upstream-Checkout, lokal gebaute
  Engine (sm_86). Aktiv: UkisAI Swift IQ2_XS, 65536 ctx, `--kv int8
  --resident-budget-gib 12 --vision`, manueller Prozess (kein systemd),
  loopback-only.
- **Archiv-Host:** ~586 GiB verifiziertes Modell-Archiv (Cold-Storage).
- **Build/Dev-Host:** dieser Fork-Checkout; Build-Kandidat für P1.
- Weitere LAN-Hosts (Router u. a.) — Prüfliste in `LOKAL.md` / Session-006-Plan.

Kein Deployment nutzt `setup.py`-geladene Prebuilt-Binaries; alle Engines sind
`"source": "local"`. Das macht die P1-Migration sauber: gleiche Baseline-SHA,
gleiche Version, andere Provenienz-Kette.

---

## 8. Offline-Lücken → was P1/P2 schließt

1. `FetchContent`-Default lädt llama.cpp zur Configure-Zeit → P1 pinnt
   `STRATA_GGML_DIR` + fail-closed wenn leer.
2. Engine-Prebuilt-Pfad: Digest via Laufzeit-API, `STRATA_SKIP_SHA256=1`-Bypass,
   Download-Fehler → Warnung statt Abbruch (fail-open) → Fork baut **immer**
   aus Quellen; Prebuilt-Pfad in Fork-Workflows entfernen/blockieren.
3. `setup.py`/`setup.sh`/`START-HERE.bat`/`update.sh`/`docker-entrypoint.sh`:
   pip/apt/winget/python.org-Downloads — aus allen Fork-Pfaden entfernen (P2),
   Wheelhouse + Hashes stattdessen.
4. GSQ-RCO/Swift/Coder ohne per-File-SHA256 → P3-Manifest schließt mit eigenen
   Hashes (5.2/5.3).
5. Keine CI → keine Upstream-Absicherung; eigene Verifikation Pflicht.

## 9. Referenzen

- Private Ergänzung (Hosts, Pfade, Services, Beleg-Pfade): **`LOKAL.md`** (lokal).
- Interne Wissensbasis: Deployment-/Betriebs-/Audit-Notizen sind in `LOKAL.md`
  verlinkt (Note-IDs).
- Phase-P0-Plan: `docs/SOLO_SESSION_001_p0_inventar.md`.

**P0-Akzeptanz:** Baseline-SHA verifiziert + dokumentiert ✓ · Quell-/Dep-/
Lizenz-/Toolchain-/Provenienz-Inventar vollständig ✓ · LAN-Bestand erfasst ✓ ·
Hash-Manifeste erhoben (Ablage: `LOKAL.md`) ✓
