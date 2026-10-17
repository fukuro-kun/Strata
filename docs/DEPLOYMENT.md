# DEPLOYMENT — kontrolliertes Deployment (P3)

Wie ein Fork-Build kontrolliert auf einen Host kommt und wieder zurück kann.
**Kein** Produktiv-Deploy ohne separate Freigabe; der Mechanismus hier ist
die Voraussetzung für die LAN-Umstellung (Session 006).

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

Default ist `systemd --user` (kein sudo). Bestehende produktive Units,
die root-seitig oder system-weit laufen, werden in Session 006 pro Host
dokumentiert und nur dort umgestellt — diese Session ändert keine
Produktiv-Units.
