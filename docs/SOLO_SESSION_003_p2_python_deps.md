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

- [ ] 1. Branch `feat/p2-python-deps` von `feat/p1-offline-build`
- [ ] 2. `tools/offline/fetch_wheels.sh`: `pip download --dest wheelhouse/`
       aus `requirements.txt` + CUDA-Wheels; danach `sha256sum` →
       `wheelhouse/MANIFEST.sha256` (committed)
- [ ] 3. `tools/offline/make_venv.sh`: venv erstellen + `pip install
       --no-index --find-links wheelhouse/ -r requirements.txt`
       (**--no-index = fail closed**, kein PyPI-Fallback)
- [ ] 4. `tools/offline/run_server.sh`: venv-Python + `serve/server.py`
       mit lokalem Engine-Binary; env `STRATA_*` nur lokal; klare
       Fehlermeldungen bei fehlendem Binary/Modell/venv
- [ ] 5. `tools/offline/calibrate.sh` (falls anwendbar): Offline-Aufruf
       der Pack-/Kalibrierungs-Tools ohne setup.py — prüfen welche
       `tools/`-Skripte der "Kalibrierungspfad" tatsächlich nutzt
- [ ] 6. Import-Resolutions-Test: venv ohne Netz → `python -c "import
       numpy, jinja2, requests, ..."` + Server-Start-Probe
- [ ] 7. Doku: OFFLINE_BUILD.md erweitern (Deps-Kapitel) + ROADMAP P2 ✓
- [ ] 8. Review → Commit → Push

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
- [ ] `make_venv.sh` läuft komplett ohne PyPI-Zugriff durch
- [ ] `run_server.sh` startet Server ODER bricht mit klarer
      "Engine/Modell fehlt"-Meldung ab (nie Download)
- [ ] `pip list` im venv entspricht MANIFEST-Hashes

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
