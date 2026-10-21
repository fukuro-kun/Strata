# SOLO_SESSION_003 — P2: Python-Abhängigkeiten lokal bereitstellen

## Session-Ziel

Start/Kalibrierung laufen **ohne `setup.py` und ohne Netz**: exakte Wheels
mit Hashes liegen lokal, Imports resolven nur gegen sie; eigene Build-/Start-
/Update-/Kalibrierungspfade nutzen `setup.py` nicht mehr. `serve/` bleibt
unverändert, Upstream-Engine und MultiGPU unverändert. Branch:
`feat/p2-python-deps`.

## Entscheidungen

| Frage | Entscheidung |
|---|---|
| Wheelhouse-Ablage | `wheelhouse/` im Repo-Root, **gitignored** (Binaries nicht committen); `wheelhouse/MANIFEST.sha256` committed — Auditierbarkeit ohne Repo-Bloat |
| Beschaffung | Einmalig `pip download` gepinnter `requirements.txt` + CUDA-Wheels (`nvidia-cublas==13.0.2.14`, `nvidia-cuda-runtime==13.0.96`) — kontrollierte Beschaffung, Hashes ins Manifest |
| Start-Pfad | `tools/offline/run_server.sh`: startet `serve/server.py` (so heißt der Entry per Voranalyse) mit lokalem venv aus Wheelhouse; Engine-Pfad wird aus lokalem Build (P1) gelesen |
| `setup.py`-Entfernung | Nicht löschen (upstream-nah!), sondern unsere Pfade rufen es nie auf; `docs/OFFLINE_BUILD.md` + Start-Skripte sind die eigenen Pfade |
| Kalibrierung | `tools/`-Skripte (iq_pack/strata_pack/native_experts) laufen direkt aus venv — dokumentierter Offline-Aufruf |

## Schritte

- [x] 1. Branch `feat/p2-python-deps` von `feat/p1-offline-build`
- [x] 2. `tools/offline/fetch_wheels.sh`: `pip download --dest wheelhouse/`
       aus `requirements.txt` + CUDA-Wheels (Pins aus setup.py gelesen);
       danach `sha256sum` → `wheelhouse/MANIFEST.sha256` (committed).
       **Real:** cp314-Satz (hydra/eris) + cp312-Satz (uranus,
       `--for-python 3.12 --only-binary`) + cu13- und cu12-Runtime-Sätze —
       25 Wheels, 1,1 GB
- [x] 3. `tools/offline/make_venv.sh`: venv `.venv-offline` + `pip install
       --no-index --find-links wheelhouse/` (**fail closed**), verifiziert
       `MANIFEST.sha256` vor der Installation, `--cuda auto|13|12|none`
       installiert die setup.py-gepinnten Runtime-Wheels
- [x] 4. `tools/offline/run_server.sh`: venv-Python + `serve/server.py`
       mit Config-Validierung (exe/args-Pfade/vocab.json), `--mock`-Modus
       für API-Smoke ohne Engine
- [x] 5. `tools/offline/calibrate.sh`: dünner Wrapper um upstream
       `tools/calibrate.py <config>` (misst --pcie-frac/--spec-min-p/
       --pool-workers; setup.py --calibrate speichert zusätzlich —
       Fork-Weg: Werte bewusst ins Config übernehmen)
- [x] 6. Import-Test: venv → `import numpy, jinja2, requests, yaml, tqdm,
       PIL, psutil, regex` ok; Mock-Server auf :18123 startet und
       antwortet (`ready: http://127.0.0.1:18123/v1`); kaputte Config →
       Klartext-Abbruch; `make_config.py` schreibt valide strata-*.json
- [x] 7. Doku: OFFLINE_BUILD.md Python-Deps-Abschnitt + ROADMAP P2 ✓
- [x] 8. Review → Commit → Push

**Review-Nachlauf (review-swe):** 4 echte Befunde gefunden und gefixt:
- `run_server.sh`-Validator: `--mtp <count>` (own-path qwen36-Configs)
  wurde fälschlich als Datei geprüft → numerische Werte übersprungen;
  weitere Datei-Flags ergänzt (`--native-dense-gguf`, `--embd-gguf`,
  `--expert-profile`, `--draft`, `--control-vector-scaled` file:scale);
  Tokenizer prüft jetzt vocab.json+merges.txt+token_type.json;
  relative Pfade resolven wie die echten Consumer (exe/args → cfg[cwd],
  tokenizer → Server-cwd)
- `calibrate.sh`: relative Config-Pfade brachen nach `cd` → absolut
  aufgelöst
- `make_venv.sh`: leerer CUDA-Wheel-Parse fiel *offen* aus (venv ohne
  libcublas, Runtime-Crash später) → jetzt fail closed; `--cuda auto`
  mappt nur echte 12/13-nvcc, sonst none
- Wheelhouse-Provenienz: Manifest hasht jetzt auch sdists
  (.tar.gz/.zip — --find-links würde sie installieren); `make_venv.sh`
  lehnt Dateien ab, die NICHT im Manifest stehen (planted/stale wheels)
- Host-Eigenheit dokumentiert: `/usr/local/bin/find` ist ein Wrapper,
  der `find .` kappt (doppelter `.`-Startpfad) → Skripte nutzen Globbing
  statt `find .`

## Verifikations-Strategie

| Schritt | Verifikation |
|---|---|
| 2 | MANIFEST.sha256 deckt jede .whl ab; `pip download` Output enthält exakt die gepinnten Versionen |
| 3 | venv entsteht mit `--no-index` (beweisbar offline); `pip list` == requirements |
| 4/6 | Server-Start-Probe: `run_server.sh` ohne Netz → Port 8080 antwortet auf `/health` oder dokumentierter Fehler wenn Engine/Modell fehlt (fail-closed-Verhalten = Erfolg, kein Fallback!) |
| 5 | Kalibrierungs-Skript läuft im venv ohne setup.py |

## Live-Verifikations-Szenario

**Szenario:** Frisches venv + Server-Start in Netz-loser Umgebung
(`unshare -n` falls verfügbar, sonst dokumentierte Offline-Annahme via
`--no-index` + kein Netz-Code-Pfad)
**Akzeptanzkriterien:**
- [x] `make_venv.sh` läuft komplett ohne PyPI-Zugriff durch
      (`--no-index` — strukturell kein PyPI-Pfad; `unshare -n` auf dem
      Build-Host nicht erlaubt → dokumentierte Offline-Annahme)
- [x] `run_server.sh` startet Server (Mock-Modus, :18123 antwortet) ODER
      bricht mit klarer "fehlt"-Meldung ab — beides live gezeigt
- [x] `pip list` im venv entspricht MANIFEST-Hashes (Manifest-Verify vor
      jeder Installation)

## Defaults

- venv-Pfad `.venv-offline/` (neben upstreams `.venv`, kein Konflikt)
- Python 3.12 bevorzugt (setup.py-Default), vorhandene System-Version
  nutzen wenn ≥3.10
- Keine Web-UI-Deps nötig (serve/web ist dependency-frei statisch)
- Fehlende Plattform-Wheels (nvidia-* auf AMD-Host): Host-Filter im
  Fetch-Skript (`--platform`/`--only-binary` oder pro-Host-Requirement-Datei)

## Recherche-Strategien

| Problemtyp | Strategie |
|---|---|
| Wheel für Plattform fehlt | `pip download --platform` Varianten; als Host-spezifisches Manifest |
| serve/server.py Entry-Args unklar | `read serve/server.py` argparse-Abschnitt |
| setup.py-interne Config-Erzeugung | Lesen was `strata-*.json` enthält; eigenen minimalen Config-Writer oder vorhandene Config kopieren |

## Recherche-Fallbacks

| Block | Problem | Fallback |
|---|---|---|
| pip download | Wheel nicht auf PyPI für Plattform | Dokumentieren + alternativ `--no-binary` Quellbuild ins Manifest |
| server.py | Startet ohne setup.py nicht (fehlende Config) | Minimale Config-Erzeugung in run_server.sh; INVENTAR-Eintrag |
| nvidia-* Wheels | hydra-CUDA vs. Host-CUDA unterschiedlich | Pro-Host-Manifest-Variante, im Manifest benannt |

## Offene Fragen

- Ob `serve/` Laufzeit-Config (`strata-*.json`) ohne setup.py erzeugt werden
  muss — klärt sich beim Server-Start-Test; Minimal-Writer ist der Fallback

## Folge-Plan

→ `SOLO_SESSION_004_p3_manifeste.md`
