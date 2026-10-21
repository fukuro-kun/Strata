# DEPLOYMENT — kontrolliertes Deployment (P3)

Wie ein Fork-Build kontrolliert auf einen Host kommt und wieder zurück kann.
**Kein** Produktiv-Deploy ohne separate Freigabe.

## LAN-Regel (festgelegt 2026-10-17)

Alle Strata-Deployments im LAN laufen aus einem Fork-Checkout +
P3-Deploy-Verzeichnis — **nicht** mehr direkt aus einem
Upstream-Checkout (`~/git/strata`) und schon gar nicht über
`setup.py`-erzeugte Pfade. Konkret:

- Fork-Checkout pro Host (Stand Session 006: `~/git/strata-fork`,
  Branch `feat/p6-lan-umstellung`), beschafft via `git bundle`/`pull`
  von `origin` = `git@europa.eulenhorst.lan:fukuro/Strata.git`
  (LAN-Forgejo, kanonisch; `github`-Remote = Mirror-Fallback).
- Dienst-Start immer über `<deploy-root>/current/run.sh` bzw.
  `tools/offline/run_server.sh` — nie direkt `.venv/bin/python
  serve/server.py` aus einem unbearbeiteten Checkout.
- Configs mit Host-Pfad auf den Fork zeigen als `*.fork.json` unter
  `~/strata-fork-configs/` (host-lokal, nicht committed — enthalten
  private Pfade).
- System-Units (z.B. `strata-swift-uranus.service`) werden so
  umgeschrieben, dass `ExecStart` auf `~/strata-deploy/current/run.sh`
  zeigt; die gepflegte Fassung liegt im InferenzQuelle-Repo.
- Eine neue Instanz wird **nie** parallel zu einer laufenden
  Eval/Inferenz auf denselben GPUs gestartet (VRAM-Konflikt) — der
  Switch wartet auf ein freies GPU-Fenster. Auf eris schließt sich
  Strata sogar mit dem Dauer-`eris-chat` (llama-server ~15,6 GiB von
  16 GiB) kapazitiv aus: Start erst wenn eris-chat per Policy unten ist.

## Begriffe

- **MANIFEST.json** — unveränderlicher Fingerabdruck eines Deploy-Stands:
  `fork_sha`, `baseline_sha`, `fork_files`/`fork_commits` (Divergenz zum
  reviewed Baseline-Pin), `llama_cpp` (Pin + `.strata-pin`-Status),
  `toolchain`, `deps` (Wheel-Hashes), `artifacts` (Binary-SHA256),
  `build` (BUILD.json), `models`, `created`, `host`.
  Erzeugt/verifiziert von `tools/offline/make_manifest.py` — bricht bei
  dirty tree, fehlendem BUILD.json oder fehlendem `.strata-pin`-Beweis ab;
  `--verify` re-hasht Artefakte + prüft fork_sha, sauberen Tree, Pin und
  Deps (driftendes Ziel wird beim Rollback abgelehnt).
- **strata-deploy/\<id\>/** — versioniertes Deploy-Verzeichnis
  (Default `~/strata-deploy/`, `STRATA_DEPLOY_ROOT` übersteuerbar).
  Enthält Engine-Binaries, die Run-Config (exe/cwd zeigen **in** das
  Verzeichnis → ein Release ist in sich abgeschlossen), MANIFEST.json und
  ein generiertes `run.sh`.
- **`current`/`previous`-Symlinks** — der Zeiger ist der Deploy-Stand;
  Swap ist atomar (`ln -sfn` + `mv -T`).

## Ablauf

```bash
# Voraussetzungen (P1+P2): engine/ gebaut, .venv-offline vorhanden,
# Wheelhouse-Manifest verifiziert. Alles davon prüft deploy_local fail-closed.
tools/offline/deploy_local.sh strata-<modell>.json          # + User-Unit
tools/offline/deploy_local.sh strata-<modell>.json --no-unit

systemctl --user restart strata-fork     # bewusster, getrennter Schritt
systemctl --user status  strata-fork
```

`deploy_local.sh` erzeugt dabei die MANIFEST.json frisch aus dem Checkout
(dirty tree → Abbruch: ein Manifest beschreibt committed Stand) und
schreibt `~/.config/systemd/user/strata-fork.service`
(`ExecStart=<deploy-root>/current/run.sh` — Restart folgt dem Zeiger).

## Rollback

```bash
tools/offline/rollback.sh                 # -> previous
tools/offline/rollback.sh <deploy-id>     # explizit
tools/offline/rollback.sh --no-restart    # nur Symlink-Swap
```

Rollback **verifiziert** das Ziel erst (`make_manifest.py --verify`:
Artifact-Hashes, fork_sha, Deps) — auf einen driftenden Stand wird nicht
zurückgeschwenkt. Der Dienst wird per Default neu gestartet.

## Provenienz-Regeln

- Ein Deployment ist reproduzierbar: gleicher Checkout + gleiches Wheelhouse
  + gleicher ggml-Baum → gleiche Hashes (bis auf `created`/`host`).
- Modelldaten werden **nicht** ins Deploy-Verzeichnis kopiert (Größe) —
  ihre Provenienz steht im Manifest (`--model name=pfad|sha256`).
- Der Server-Code kommt aus dem Repo-Checkout (`fork_sha`); ein Rollback
  auf ein anderes `fork_sha` gehört zusätzlich zu `git checkout` — das
  Manifest macht die Diskrepanz sichtbar. Gleiches gilt für das **venv**:
  es ist shared (`.venv-offline`), nicht versioniert — das Manifest hält
  `venv.pip_freeze_sha256`, und Verify meldet einen neu gebauten venv
  als Drift.

## systemd-Varianten

Default ist `systemd --user` (kein sudo). System-Units (produktiv, mit
sudo) werden beim Switch durch die Fork-Fassung ersetzt — die Datei
liegt im InferenzQuelle-Repo (`services/uranus/strata-swift-uranus.service`,
Branch `feat/strata-fork-deploy`). Auf Hosts ohne produktive Unit
(eris) genügt die generierte User-Unit `strata-fork.service`.

### Switch-Runbook (pro Host, nach Eval-/GPU-Fenster)

```bash
# uranus (System-Unit; sudo nötig):
sudo cp <inferenzquelle>/services/uranus/strata-swift-uranus.service \
        /etc/systemd/system/ && sudo systemctl daemon-reload
sudo systemctl enable --now strata-swift-uranus   # startet current/run.sh :18086
curl -s 127.0.0.1:18086/slots | head    # readiness
# Chat-Completion-Probe, dann InferenzQuelle-Router-Sicht (janus :8010)

# eris (User-Unit, kein sudo):
systemctl --user enable --now strata-fork   # Config-Port 8080
curl -s 127.0.0.1:8080/slots | head

# Rollback (beide):
~/git/strata-fork/tools/offline/rollback.sh --deploy-root ~/strata-deploy
```

Vor dem ersten produktiven Start eines Hosts einmalig das Rollback
real üben (deploy → rollback → redeploy).
