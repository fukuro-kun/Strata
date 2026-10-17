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

- Erworbener Stand (Inventar-Baseline): `296b59d2f73c8f04a805df29c2fa97655adace78`
  auf Default-Branch `main` zum Klon-Zeitpunkt.
- Diese SHA ist **Inventar-Baseline, kein freigegebener Deployment-Pin.**
  Früherer Audit-Bezug war `296b59d2f73c8f04a805df29c2fa97655adace78` und der
  Robert-Snapshot `b124b59`; daraus folgt **keine** automatische Freigabe des
  jeweils aktuellen Default-Heads. Eine Pin-Entscheidung fällt erst in P0 nach Review.

## Begriffe

- **Kontrollierte Online-Beschaffung**: bewusster, dokumentierter Bezug von
  Quelltext und Abhängigkeiten (Clone, reviewed Fetches, exakt gepinnte Wheels).
- **Offline-Build/Start/Kalibrierung**: alle Schritte danach laufen ohne
  Netzwerkzugriff — kein Auto-Download, kein stiller Fallback.

## Phasen

### P0 — Inventar und Baseline-Freeze

- [ ] Quell-Inventar: `src/`, `include/`, `serve/`, `tools/`, `cmake/`, `CMakeLists.txt`
- [ ] Abhängigkeits-Inventar: `requirements.txt`, externe/eingebettete Deps
- [ ] Lizenz-Inventar aller Komponenten
- [ ] Toolchain-Inventar: Compiler, CUDA/HIP-Versionen, Python-Version
- [ ] Provenienz von Modell, Pack, Draft-Modell und Projektor (Herkunft + Hashes)
- [ ] Reviewte SHA einfrieren und als Pin dokumentieren

**Akzeptanz:** Schriftliches Inventar mit Herkunft/Hash je Quelle; eingefrorene,
reviewte SHA dokumentiert.

### P1 — Isolierter Offline-Build-Einstieg

- [ ] Build-Einstieg definieren, der ausschließlich lokale, gepinnte Inputs nutzt
- [ ] Lokales, gepinntes llama.cpp über die vorhandene `STRATA_GGML_DIR`-Nahtstelle anbinden
- [ ] Fehlende Inputs → **fail closed** (klarer Abbruch), niemals Download/Fallback
- [ ] Eigene Engine aus Quellen bauen (kein Prebuilt)

**Akzeptanz:** Build läuft vollständig offline aus lokalen Quellen; fehlender
Input führt zu kontrolliertem Abbruch, nie zu stiller Netz-Beschaffung.

### P2 — Python-Abhängigkeiten lokal bereitstellen

- [ ] Exakte Wheels mit Hashes lokal bereitstellen
- [ ] `serve/` vorerst unverändert beibehalten
- [ ] `setup.py` aus unseren Build-/Start-/Update-/Kalibrierungspfaden entfernen
- [ ] Kein Auto-Fallback/Auto-Download in eigenen Pfaden
- [ ] Upstream-Engine und MultiGPU-Funktionalität möglichst unverändert lassen

**Akzeptanz:** Start/Kalibrierung laufen ohne `setup.py` und ohne Netz; Imports
resolven nur gegen lokale Wheels mit verifizierten Hashes.

### P3 — Manifeste und kontrolliertes Deployment

- [ ] Immutables Build-/Modell-Manifest: Quell- und Submodule-Hashes, angewandte Patches
- [ ] Toolchain-, Versions- und Dependency-Hashes im Manifest
- [ ] Binary-Hashes der erzeugten Artefakte
- [ ] Kontrolliertes systemd-Deployment mit Rollback auf konfig-/datenkompatible Manifeste
- [ ] **Kein Produktiv-Deploy ohne separate Freigabe**

**Akzeptanz:** Manifest reproduzierbar und verifizierbar; Rollback-Pfad getestet;
Deployment erfolgt nur nach separater Freigabe.

### P4 — Upstream-Sync-Disziplin

- [ ] Upstream-Fetch nur bewusst angestoßen, auf eigenem Integrations-Branch
- [ ] Diff-Review von `src/`, `include/`, `serve/`, Build-Dateien, Abhängigkeiten
      **und** Agenten-Anweisungen (alle relevanten Bereiche, nicht nur Installer)
- [ ] Tests vor Promotion
- [ ] Kein Auto-Pull/Auto-Update

**Akzeptanz:** Jede Upstream-Übernahme hat dokumentiertes Diff-Review und
Testlauf; keine automatische Synchronisation. Remote `upstream` ist angelegt,
aber bis dahin un-gefetched.

### P5 — OPTIONAL: Robert-C++-Frontend

- [ ] Nur nach **expliziter Entscheidung**: Frontend als separate Komponente auf
      upstream-naher Engine wiederverwenden
- [ ] Kein Import der gesamten Qwen3.6-/Kernel-Divergenz
- [ ] Tests: MultiGPU, Swift, Vision, Tools, Langcontext, SSE, Disconnect,
      echte `/slots`-Readiness/Drain
- [ ] InferenzQuelle: aktuelle Live-Slot-Admission darf **nicht** global
      deaktiviert werden

**Akzeptanz:** Nur nach explizitem Go; alle genannten Testbereiche grün;
Frontend bleibt eine separat ersetzbare Komponente.

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
