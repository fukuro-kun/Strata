# SOLO_SESSION_006 — LAN-Deployment-Umstellung auf den Fork

## Session-Ziel

Alle im LAN laufenden Strata-Deployments sind identifiziert und auf den
eigenen Fork umgestellt (P3-Mechanik: Manifest + versioniertes Deploy +
Rollback). Die Umstellung ist in allen Deploy-Dokus und Trilium-Notes als
Regel festgelegt. Branch: `feat/p3-manifeste` (deploy-seitig;
Doku-Änderungen dort oder `feat/lan-umstellung`).

**Voraussetzung:** 004 (P3) und 005 (P4) abgeschlossen — fukuros Vorgabe.

## Entscheidungen

| Frage | Entscheidung |
|---|---|
| Umstellung | Sobald Mechanik steht, pro Host umstellen; alter Stand bleibt als Rollback-Verzeichnis liegen |
| Reihenfolge | Erst beobachten/inventarisieren, dann Test-Host zuerst (kleinste Kritikalität), dann InferenzQuelle-relevante Hosts |
| InferenzQuelle-Vertrag | `/slots`-Readiness/Drain-Endpunkte müssen nach Umstellung weiter liefern — Abnahme pro Host: `/slots` antwortet + Chat-Completions-Probe |
| Was wird umgestellt | Engine-Build (Fork, eigenes Binary), Server-Start-Pfad (unser run_server.sh statt setup.py), Config bleibt kompatibel (strata-*.json Inhalt unverändert wo möglich) |
| Doku-Regel | "Deployments laufen auf fukuro-kun/Strata (upstream-naher Fork, gepinnte SHA), nicht auf Upstream-Installer" — in Trilium-Notes + LOKAL.md + DEPLOYMENT.md |

## Ergebnis 2026-10-17 (Stand: Deploys vorbereitet, Switch eval-blockiert)

### Deploy-Matrix (LAN-Discovery abgeschlossen)

| Host | Dienst / Prozess | Port | Modell | Verbraucher | Umstellung |
|---|---|---|---|---|---|
| uranus | `sc117-test-q2_0.service` (user, **aktiv — Eval läuft**) | 18087 | sc117-abliterated-q2_0 | eval.py | bleibt bis Eval-Ende auf altem Checkout |
| uranus | `strata-swift-uranus.service` (System-Unit, disabled, zuletzt 16.10.) | 18086 (0.0.0.0) | swift-1.5-iq3_s | InferenzQuelle janus `uranus-swift15` (tier 0, Alias `swift15-flash-next`) | Fork-Deploy staged; Unit-Update vorbereitet (IQ-Repo `feat/strata-fork-deploy`), Installation beim Switch |
| eris | Eval-Prozesse (manuell/nohup, **aktiv**) | 8081 | sc117-iq2_xs | eval.py | bleibt bis Eval-Ende |
| eris | Produktiv-Configs `strata-swift-iq2_xs.json`, `strata-coder-iq1_m*.json` (keine Unit — manueller Start) | 8080 | swift-1.5-iq2_xs / coder-iq1_m | lokale Nutzung | `.fork.json`-Varianten erzeugt; Fork-Deploy staged |
| eris | `eris-chat.service`, ERIS-CODE :18082 | — | — | llama-server/InferenzQuelle | **kein Strata** — außerhalb Scope |
| ganymed | kein laufendes Strata | — | — | Cold-Storage/Modellarchiv | nichts zu tun |
| hydra | kein produktiver Strata-Dienst | — | — | Build-Host | nichts zu tun |

### Geliefert (beide Hosts, identische Mechanik)

- Fork-Checkout `~/git/strata-fork` @ `feat/p6-lan-umstellung` (`d18e7fea`),
  via `git bundle` über LAN gebracht; `origin` zeigt auf den Fork
  (GitHub-SSH-Auth auf beiden Hosts vorhanden, `git pull` verifiziert)
- `third_party/llama.cpp` via `fetch_llamacpp.sh --from-dir
  ~/git/strata/third_party/llama.cpp --allow-unverified` (Byte-Identität
  der Bäume war P0-Evidenz; pin `3cf03257`)
- Engine lokal gebaut (P1-Pfad): uranus sm_89 mit CUDA 13.0 (effektiver
  Compiler `/usr/local/cuda-13.0/bin/nvcc`, CMakeCache verifiziert),
  eris sm_86/CUDA 12.4, `--vision cpu` = Produktiv-Vokabular
- `.venv-offline` via `make_venv.sh` (uranus `--cuda 13` explizit —
  PATH-nvcc ist 12.0; eris `--cuda 12`, Python 3.14)
- `.fork.json`-Config-Varianten unter `~/strata-fork-configs/` (host-lokal,
  enthalten Host-Pfade → nicht committed)
- P3-Deploys: uranus `~/strata-deploy/d18e7fea-20261017T033913Z`,
  eris `…/d18e7fea-20261017T033934Z`; `current`-Symlinks gesetzt,
  Manifest-Verifikation vor Swap bestanden, alle config-referenzierten
  Pfade (exe, vision, pack, native, ple, mtp, expert-profile, tokenizer)
  auf Existenz geprüft — keine fehlenden Inputs
- User-Unit `strata-fork.service` installiert, **nicht gestartet**

### uranus: **UMGESTELLT + VERIFIZIERT** (Eval war beendet, GPUs frei)

Der SC117-Eval auf uranus endete während der Session; der Switch wurde
ausgeführt und vollständig abgenommen:

- `strata-swift-uranus.service` (System-Unit, Fork-Fassung aus
  InferenzQuelle `feat/strata-fork-deploy`) installiert →
  `ExecStart=~/strata-deploy/current/run.sh --host 0.0.0.0 --port 18086`
- `/slots` antwortet InferenzQuelle-konform (1 Slot, ctx 262144, idle)
- Echte Chat-Completion: „Ja, der Fork läuft." (finish=stop)
- janus-Router `:8010/endpoints`: `uranus-swift15` **healthy: true**
- Prozess läuft aus `~/strata-deploy/…` — kein stiller Fallback auf den
  Upstream-Checkout
- **Rollback real geübt:** alte Unit zurückgespielt → alter Stack
  (`~/git/strata`) antwortete wieder auf :18086 → wieder auf Fork
  gewechselt und erneut verifiziert. Der Dienst bleibt `disabled` +
  läuft manuell wie zuvor (On-Demand-Host; Lifecycle via Host-Agent).

**Fund bei der Rollback-Übung:** die alte Unit trug `--no-browser` —
ein Flag, das das heutige `serve/server.py` nicht mehr kennt (Browser
öffnet nur noch mit `--open`). Der Rollback-Pfad wäre genau daran
gescheitert; bereinigt in der archivierten Fassung.

### eris: weiterhin eval-blockiert

Eval auf :8081 läuft noch. Nach Eval-Ende:
`systemctl --user enable --now strata-fork` (Config-Port 8080) +
dieselbe Abnahme (`/slots` + Completion) + Rollback-Übung.
Runbook: `docs/DEPLOYMENT.md`.

### Fixes unterwegs (auf `feat/p6-lan-umstellung`)

- `find_tool` suchte ninja nicht in `.venv-offline/bin` (eris hatte nur
  dort eins); lieferte außerdem relative Pfade — CMake-TryCompile
  scheiterte; `-x` traf das repo-eigene `cmake/`-Verzeichnis
- `--cmake-def CMAKE_CUDA_COMPILER=…` wurde an cmake durchgereicht, aber
  der BUILD.json-Stamp (`cuda_dirs`) blieb auf PATH-nvcc → falsche
  Provenienz; Override gewinnt jetzt vor dem Stamp

## Schritte

- [x] 1. LAN-Discovery abschließen (s. Matrix oben)
- [x] 2. Trilium-Notes konsolidiert → Matrix
- [x] 3. Fork-Artefakte pro Host: lokaler P1-Build (uranus sm_89/CUDA-13.0,
       eris sm_86/CUDA-12.4), Manifest-Verifikation beim Deploy bestanden
- [x] 4. Deploy-Pfad: versioniertes Verzeichnis + current-Symlink;
       uranus-System-Unit als Fork-Variante in InferenzQuelle-Repo
       vorbereitet (`feat/strata-fork-deploy`)
- [x] 5. Abnahme `/slots` + Chat-Completion — **uranus bestanden**
       (echte Antwort, Router healthy); eris nach Eval-Ende
- [x] 6. Rollback-Verifikation — **uranus real geübt** (Unit-Rollback auf
       alten Checkout-Stack, verifiziert, zurück auf Fork); eris offen
- [x] 7. Doku: InferenzQuelle-Unit + Trilium-Updates + DEPLOYMENT.md/LOKAL.md
- [x] 8. Review → Commit → Push (`feat/p6-lan-umstellung`)

## Verifikations-Strategie

| Schritt | Verifikation |
|---|---|
| 1-2 | Deploy-Matrix vollständig: jeder gefundene Strata-Prozess hat Zeile; jede Trilium-Erwähnung ist einem Host zugeordnet |
| 3 | Manifest-Hashes auf Zielhost verifiziert (`sha256sum -c` über Artefakte) |
| 5 | Pro Host: HTTP 200 auf health/slots + eine erfolgreiche completions-Antwort (Token > 0) |
| 6 | Rollback-Pfad einmal real ausgeführt (nicht nur Code-Review) |

## Live-Verifikations-Szenario

**Szenario:** Produktiver Host (aus Matrix) auf Fork umgestellt
**Akzeptanzkriterien:**
- [ ] Dienst läuft unter neuem Pfad/Fork-Binary (prozess-Liste / Manifest-ID)
- [ ] `/slots` bzw. vom Verbraucher genutzte Endpunkte antworten wie vorher
- [ ] Eine echte Inferenz-Antwort kommt (≥1 Token, sinnvoller Text)
- [ ] Rollback-Anleitung getestet und im Host-Doku-Eintrag
- [ ] Kein stiller Fallback auf upstream-Binary (prozess-cmdline zeigt
      Fork-Pfad)

## Defaults

- Host nicht erreichbar → dokumentieren, nächster Host; Gesamt-Blocker-Liste
  im Bericht statt Session-Abbruch
- Kein sudo auf Remote-Host → User-Level-Units oder dokumentierter
  manueller Start-Pfad; nie im Stillen `sudo -n` probieren und scheitern
- Modell-Dateien auf Host vorhanden → weiterverwenden (Pfade aus
  Discovery); **kein** 70-GB-Neu-Download in dieser Session
- InferenzQuelle selbst wird nicht umgebaut — nur die Strata-Endpunkte
  hinter ihr

## Recherche-Strategien

| Problemtyp | Strategie |
|---|---|
| Wo läuft Strata | SSH ps/systemctl/ss + Trilium-Notes + InferenzQuelle-Config-Dateien |
| Unit-Details | `systemctl cat <unit>` auf dem Host |
| Modellpfade | bestehende `strata-*.json`-Configs auf dem Host lesen |

## Recherche-Fallbacks

| Block | Problem | Fallback |
|---|---|---|
| Discovery | Host ohne Strata-Befund | "kein Strata-Dienst" in Matrix = valides Ergebnis |
| Umstellung | Fork-Build passt nicht zur Host-GPU (z.B. AMD) | P1-Pfad auf dem Host selbst bauen; wenn Toolchain fehlt → dokumentiert + Host bleibt vorerst auf altem Stand mit TODO |
| InferenzQuelle | Erwartet Endpunkt den Fork-serve nicht liefert | STOP-Analyse: liegt es am Start-Pfad oder echter Feature-Gap? → Bericht + ggf. P5-Relevanz |

## Offene Fragen

- Ob auf den Inferenz-Hosts systemd --user oder root-Units laufen
- Ob InferenzQuelle-Endpunkte hart auf Pfade/Versionen zeigen
  (entsteht in Discovery)

## Folge-Plan

→ `SOLO_SESSION_007_p5_vorbereitung.md`
