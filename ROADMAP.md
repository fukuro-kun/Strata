# ROADMAP — eigener, upstream-naher Strata-Fork

Kanonischer Plan für diesen Fork. Private Umgebungsdetails (Pfade, Hosts, IDs)
stehen in `LOKAL.md` (lokal, nicht versioniert). Arbeitsregeln: `AGENTS.md`.

## Ziel

- Eigener Strata-Fork, der **nah an upstream** bleibt (geringe, reviewbare Divergenz).
- **Vollständig erhaltene Historie** — kein Shallow-Clone, keine gekürzte Vorgeschichte.
- **Keine ungeprüften Release-Binaries** — Builds aus geprüften Quellen mit lokaler Toolchain.
- **Kein Docker-Erfordernis** für Build, Start oder Kalibrierung.

## Aktueller Status

**Freigabe erteilt 2026-10-17 (Entscheidungs-Interview):** Phasen P0–P4
werden **vollständig autonom** in einer Solo-Session durchgearbeitet; P5 wird
vorbereitend evaluiert (Evaluierungs-Dokument, keine Implementierung).
Zusätzlich freigegeben: **Umstellung bestehender Strata-Deployments im LAN
auf diesen Fork** nach Abschluss von P4 — mit Rollback-Bereitstellung — sowie
die Festlegung dieser Deployment-Regel in allen Deploy-Dokus und
Trilium-Notes.

Einzelheiten: `docs/SOLO_SESSION_OVERVIEW.md` und die verketteten
`docs/SOLO_SESSION_*.md`-Pläne.

- **Gepinnte Baseline (P0 verifiziert):**
  `296b59d2f73c8f04a805df29c2fa97655adace78` — Tree-Diff gegen den unabhängigen
  Audit-Checkout identisch; Stichproben-Review bestätigt; ein laufender
  Produktiv-Checkout steht auf derselben SHA. Nachweis: `docs/INVENTAR.md`.
  Früherer Audit-Bezug war dieselbe SHA, Robert-Snapshot `b124b59`; daraus folgt
  **keine** automatische Freigabe des jeweils aktuellen Default-Heads.

## Begriffe

- **Kontrollierte Online-Beschaffung**: bewusster, dokumentierter Bezug von
  Quelltext und Abhängigkeiten (Clone, reviewed Fetches, exakt gepinnte Wheels).
- **Offline-Build/Start/Kalibrierung**: alle Schritte danach laufen ohne
  Netzwerkzugriff — kein Auto-Download, kein stiller Fallback.

## Phasen

### P0 — Inventar und Baseline-Freeze — **ERLEDIGT 2026-10-18**

- [x] Quell-Inventar: `src/`, `include/`, `serve/`, `tools/`, `cmake/`, `CMakeLists.txt` → `docs/INVENTAR.md` §1
- [x] Abhängigkeits-Inventar: `requirements.txt`, externe/eingebettete Deps → §2
- [x] Lizenz-Inventar aller Komponenten → §3
- [x] Toolchain-Inventar: Compiler, CUDA/HIP-Versionen, Python-Version → §4 (4 Hosts gemessen)
- [x] Provenienz von Modell, Pack, Draft-Modell und Projektor (Herkunft + Hashes) → §5
- [x] Reviewte SHA einfrieren und als Pin dokumentieren → `296b59d2…`, §0

**Akzeptanz erfüllt:** `docs/INVENTAR.md` mit Herkunft/Hash je Quelle; eingefrorene,
reviewte SHA dokumentiert. Host-Details und Hash-Rohdateien: `LOKAL.md` + lokale
Evidenz-Ablage (Bewusst nicht committed — Repo-Regel).

### P1 — Isolierter Offline-Build-Einstieg — **ERLEDIGT 2026-10-18**

- [x] Build-Einstieg: `tools/offline/build_engine.sh` (fail-closed, keine Netz-Aufrufe)
- [x] Lokales llama.cpp via `STRATA_GGML_DIR`: `third_party/llama.cpp` @
      `3cf03257…` + `.strata-pin`; Bezug via `tools/offline/fetch_llamacpp.sh`
      (LAN-Kopie, byte-identisch zu zwei Produktiv-Bäumen verifiziert)
- [x] Fail closed: CMake `FATAL_ERROR` bei leerem `STRATA_GGML_DIR` (Escape:
      `-DSTRATA_ALLOW_GGML_FETCH=ON`); Skript bricht bei fehlendem Input/Pin-
      Mismatch ab — live getestet
- [x] Eigene Engine aus Quellen: `engine/strata` + `strata-vision` +
      `libstrata_kq.so` auf hydra gebaut (CUDA 13.4, sm_86), Smoke-Test ok

**Akzeptanz erfüllt:** Build lief komplett ohne Netz-Fetch (Configure-Log
fetch-frei); fehlender Input → kontrollierter Abbruch. Doku: `docs/OFFLINE_BUILD.md`.

### P2 — Python-Abhängigkeiten lokal bereitstellen — **ERLEDIGT 2026-10-18**

- [x] Exakte Wheels mit Hashes lokal bereitstellen: `wheelhouse/` (gitignored)
      + `wheelhouse/MANIFEST.sha256` (committed); Beschaffung via
      `tools/offline/fetch_wheels.sh` (cp312 + cp314 + CUDA-13/12-Runtime-Wheels)
- [x] `serve/` vorerst unverändert beibehalten
- [x] `setup.py` aus unseren Build-/Start-/Update-/Kalibrierungspfaden entfernt:
      `tools/offline/make_venv.sh` (--no-index, Manifest-Verify vor Install),
      `run_server.sh` (Config-Validierung, fail closed), `calibrate.sh`,
      `make_config.py` (minimaler Config-Writer)
- [x] Kein Auto-Fallback/Auto-Download in eigenen Pfaden
- [x] Upstream-Engine und MultiGPU-Funktionalität möglichst unverändert lassen

**Akzeptanz erfüllt:** venv-Install lief mit `--no-index` rein aus dem
Wheelhouse; Mock-Server-Start via `run_server.sh` ok; kaputte Config bricht
mit Klartext ab. Doku: `docs/OFFLINE_BUILD.md` (Python-Deps-Abschnitt).

### P3 — Manifeste und kontrolliertes Deployment — **ERLEDIGT 2026-10-18**

- [x] Immutables Build-/Modell-Manifest: `tools/offline/make_manifest.py`
      (fork_sha, baseline_sha, fork_files/-commits, llama_cpp-Pin, toolchain,
      deps, artifacts, build, models, created, host; dirty tree → Abbruch)
- [x] Toolchain-, Versions- und Dependency-Hashes im Manifest
- [x] Binary-Hashes der erzeugten Artefakte (artifacts{sha256,size})
- [x] Kontrolliertes systemd-Deployment mit Rollback: `deploy_local.sh`
      (versioniertes `strata-deploy/<id>/`, atomarer `current`-Symlink-Swap,
      `previous`-Tracking, User-Unit `strata-fork.service`),
      `rollback.sh` (verifiziert Ziel-Manifest vor dem Swap)
- [x] **Kein Produktiv-Deploy ohne separate Freigabe** — diese Session
      stellt nur den Mechanismus, LAN-Umstellung folgt in Session 006

**Akzeptanz erfüllt:** Manifest verifizierbar (`--verify` re-hasht Artifacts
+ fork_sha + deps); Rollback-Pfad lokal auf dem Build-Host getestet
(deploy v1 → v2 → rollback auf v1). Doku: `docs/DEPLOYMENT.md`.

### P4 — Upstream-Sync-Disziplin — **ERLEDIGT 2026-10-18**

- [x] Upstream-Fetch nur bewusst angestoßen: erster Fetch 2026-10-17,
      `upstream/main` = `296b59d2…` (exakt P0-Baseline, Tag v0.1.44.1)
- [x] Diff-Review: 0 Commits Drift — Bericht
      `docs/upstream-reviews/REVIEW_2026-10-17_296b59d2.md`
- [x] Tests vor Promotion: Prozess in `docs/UPSTREAM_SYNC.md` verankert
      (kein Merge nötig — keine Divergenz)
- [x] Kein Auto-Pull/Auto-Update; `upstream`-Push bleibt `PUSH_DISABLED`

**Akzeptanz erfüllt:** Prozess-Doku + erster dokumentierter Review vorhanden;
keine automatische Synchronisation eingerichtet.

### P5 — OPTIONAL: Robert-C++-Frontend — **EVALUIERT 2026-10-17**

Evaluierung abgeschlossen: `docs/P5_ROBERT_FRONTEND_EVAL.md` —
**Empfehlung No-Go für den LAN-Einsatz** (Frontend lehnt Multi-GPU und
`--vision` aktiv ab, hat kein `/slots` → InferenzQuelle-Live-Admission
würde `live_check_failed` liefern, keine Anthropic-Endpoints). Robert
adressiert Einzelmaschine/eine GPU ohne Router — nicht unser Profil.
Entscheidung bleibt fukuros; Checkboxen unten bleiben bewusst offen.

- [ ] Nur nach **expliziter Entscheidung**: Frontend als separate Komponente auf
      upstream-naher Engine wiederverwenden
- [ ] Kein Import der gesamten Qwen3.6-/Kernel-Divergenz
- [ ] Tests: MultiGPU, Swift, Vision, Tools, Langcontext, SSE, Disconnect,
      echte `/slots`-Readiness/Drain
- [ ] InferenzQuelle: aktuelle Live-Slot-Admission darf **nicht** global
      deaktiviert werden

**Akzeptanz:** Nur nach explizitem Go; alle genannten Testbereiche grün;
Frontend bleibt eine separat ersetzbare Komponente.

### LAN-Umstellung auf den Fork (Session 006) — **uranus LIVE 2026-10-17**

- [x] Deploy-Matrix über alle Hosts; produktive Strata-Endpunkte:
      uranus :18086 (InferenzQuelle `uranus-swift15`, System-Unit
      `strata-swift-uranus.service`) und eris :8080 (manuell, keine Unit)
- [x] Fork-Checkout + P1-Engine-Build + P2-Venv + P3-Deploy auf uranus
      (sm_89/CUDA-13.0) und eris (sm_86/CUDA-12.4) — Manifest verifiziert,
      `current`-Symlink gesetzt
- [x] **uranus umgestellt und abgenommen:** System-Unit läuft auf
      `~/strata-deploy/current/run.sh`; `/slots` + echte Chat-Completion
      verifiziert, janus-Router meldet `uranus-swift15` healthy; Rollback
      auf den alten Stack real geübt und zurückgewechselt
- [ ] **eris offen** — SC117-Eval :8081 lief bis zuletzt; nach Eval-Ende:
      `systemctl --user enable --now strata-fork`, dieselbe Abnahme +
      Rollback-Übung (Runbook `docs/DEPLOYMENT.md`)
- [ ] ganymed: kein Strata-Dienst (Modellarchiv) — nichts umzustellen

Details und Switch-Runbook: `docs/SOLO_SESSION_006_lan_umstellung.md`,
`docs/DEPLOYMENT.md`.

## Zurückgestellt / Nicht-Ziele

- **Auth/Host/Key-Berechtigungen**: zurückgestellt gemäß isoliertem
  LAN-Bedrohungsmodell. Es wird jetzt **keine** Auth-Regression eingeführt;
  bestehende Konfiguration bleibt unverändert.
- **Vertrauensgrenze**: Source-Build reduziert das Prebuilt-Risiko, eliminiert
  aber **nicht** das Quell-/Toolchain-/Dependency-Vertrauen — P0-Inventar bleibt Pflicht.
- **Forgejo-Mirror**: optionaler Zukunftsschritt. Die kanonische Remote-Rolle
  muss **vor** einem Wechsel entschieden werden.

## Weiterhin verboten (trotz Freigabe P0–P4)

- Keine Auto-Downloads oder Fallback-Beschaffung in eigenen Pfaden —
  Beschaffung nur bewusst, dokumentiert, gepinnt
- Keine Modifikation von Upstream-Engine-Code über die Roadmap-Ziele hinaus
  (`serve/` und Engine bleiben upstream-nah)
- Kein automatischer Upstream-Sync (Cron/Timer) — nur bewusst angestoßen (P4)
- Kein Push nach `upstream` (Remote bleibt push-gesperrt)
- Keine Produktiv-Umstellung vor Abschluss der jeweiligen Phase bzw. vor P4
  für die LAN-Umstellung; jede Umstellung mit dokumentiertem Rollback-Pfad
- Keine Auth-/Host-/Key-Änderungen (zurückgestellt, siehe oben)
