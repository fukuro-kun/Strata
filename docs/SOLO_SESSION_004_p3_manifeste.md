# SOLO_SESSION_004 — P3: Manifeste und kontrolliertes Deployment

## Session-Ziel

Ein **immutables Build-/Modell-Manifest** existiert (Quell-/Submodule-Hashes,
angewandte Patches, Toolchain-/Versions-/Dependency-Hashes, Binary-Hashes der
Artefakte) plus ein **kontrolliertes systemd-Deployment mit Rollback-Pfad**.
Produktiv-Umstellung selbst läuft in Session 006 (Freigabe für LAN-Umstellung
erteilt, aber erst nach P4). Branch: `feat/p3-manifeste`.

## Entscheidungen

| Frage | Entscheidung |
|---|---|
| Manifest-Format | `MANIFEST.json` pro Deployment-Stand: `{fork_sha, llama_cpp_sha, patches[], toolchain{...}, deps{wheel:sha256}, artifacts{binary:sha256}, models{name:sha256|quelle}, created, host}` |
| Manifest-Erzeugung | `tools/offline/make_manifest.py` — sammelt alle Hashes, schreibt MANIFEST.json neben den Artefakten |
| Deployment-Layout | Versioniertes Artefakt-Verzeichnis `strata-deploy/<manifest-id>/` (engine-binary + venv-ref + config) — Rollback = Zeiger zurück auf altes Verzeichnis |
| systemd | `systemd --user`-Units bevorzugt (kein sudo nötig); falls produktive Units root-seitig existieren → in 006 dokumentiert und mit sudo nur falls bereits eingerichtet |
| Rollback | `strata-deploy/current` Symlink; Umstellung = Symlink-Swap + `systemctl restart`; Rollback-Skript `tools/offline/rollback.sh` |

## Schritte

- [x] 1. Branch `feat/p3-manifeste` von `feat/p2-python-deps`
- [x] 2. `tools/offline/make_manifest.py` schreiben + auf P1/P2-Artefakte
       anwenden → erste MANIFEST.json (fork_sha, baseline_diff, llama-Pin,
       toolchain, deps, artifacts, build, venv-pip-freeze, models)
- [x] 3. `tools/offline/deploy_local.sh`: legt versioniertes
       Artefakt-Verzeichnis an, kopiert Engine+Config (exe/cwd umgebogen),
       setzt `current`-Symlink atomar; Wheelhouse-Manifest-Verify vorab
- [x] 4. `tools/offline/rollback.sh`: verifiziert Ziel-Manifest VOR dem
       Swap (driftendes Ziel → Abbruch), Symlink zurück + Service-Restart
- [x] 5. systemd-Unit: von `deploy_local.sh` generiert nach
       `~/.config/systemd/user/strata-fork.service`
       (ExecStart=`current/run.sh` — Restart folgt dem Zeiger)
- [x] 6. Rollback-Test lokal: deploy 17e1512d → cad9670b → cad9670b':
       Rollback auf **anderen** fork_sha → korrekt ABGELEHNT (Manifest-
       Verify: "fork_sha manifest 17e1512d, checkout cad9670b");
       Rollback auf **gleichen** SHA → verifiziert + geswappt;
       User-Unit sichtbar via `systemctl --user cat` (nicht gestartet —
       kein Modell auf hydra, plangemäß)
- [x] 7. Doku: `docs/DEPLOYMENT.md` geschrieben + ROADMAP P3 ✓
- [x] 8. Review → Commit → Push

**Review-Nachlauf (review-swe):** 7 echte Befunde, alle gefixt:
- `--verify`-Fallback auf Repo-Artefakte maskierte fehlende Deploy-Dateien
  (Rollback hätte auf unvollständiges Verzeichnis geswappt) → Artefakte
  müssen NEBEN dem Manifest liegen
- `run()` schluckte git-Fehler → stille Provenienz-Lügen; jetzt Abbruch
- fehlender `.strata-pin` schrieb Manifest mit `pin_ok:false` → jetzt
  fail-closed (sonst wäre der Stand im Rollback unbenutzbar)
- `deploy_local.sh` verifiziert jetzt das Wheelhouse-Manifest vorab
- Config-Rewrite: staged-File-Existenz für exe/vision.exe geprüft
- venv-Drift erfassbar: `venv.pip_freeze_sha256` im Manifest + Verify
- Deploy-ID-Kollision, Orphan-DEST (trap), `ln -sfnT`, `--deploy-root`
  für rollback, `--service`-Suffix-Normalisierung, positional-Guards

## Verifikations-Strategie

| Schritt | Verifikation |
|---|---|
| 2 | MANIFEST.json reproduzierbar: zweimal erzeugt → identisch (bis auf created-Timestamp); alle Hashes verifizierbar per `sha256sum -c`-äquivalent |
| 3-4 | Symlink-Swap ist atomar (`ln -sfn` + mv-Trick); Service-Restart greift neue Version |
| 6 | Rollback beweisbar: Port-Antwort vor/nach dem Swap auf Versionen unterscheidbar (Version-String/Header) |

## Live-Verifikations-Szenario

**Szenario:** Lokaler Deploy-Zyklus auf hydra mit User-Unit
**Akzeptanzkriterien:**
- [ ] `make_manifest.py` erzeugt valides JSON mit allen Pflichtfeldern
- [ ] `deploy_local.sh` + `rollback.sh` zweimal ausgeführt → `current` zeigt
      nach Rollback auf ursprüngliches Manifest
- [ ] Unit `systemctl --user status strata` nach Deploy aktiv (oder
      dokumentierter Grund: kein Modell → Service definiert aber nicht
      gestartet)
- [ ] Kein Schreibzugriff außerhalb `strata-deploy/` + `~/.config/systemd/user/`

## Defaults

- Manifest-ID = `<fork-sha-short>-<yyyymmddTHHMMSS>`
- Artefakt-Ablage `~/strata-deploy/` (pro Host, außerhalb des Repos)
- Fehlende Felder → Manifest-Erzeugung bricht ab (fail closed), nie
  "unbekannt" still eintragen — außer explizit `null` mit Kommentar

## Recherche-Strategien

| Problemtyp | Strategie |
|---|---|
| systemd-Varianten pro Host | P0-Erhebung; `systemctl --user` vs root je Host dokumentieren |
| InferenzQuelle-Vertrag | `router/admission.py`-Anforderungen aus Audit-Note; Endpunkte `/slots`-Äquivalenz prüfen im serve/-Code |
| Config-Format `strata-*.json` | serve/runconfig.py lesen |

## Recherche-Fallbacks

| Block | Problem | Fallback |
|---|---|---|
| systemd --user | lingus/dbus fehlt auf Remote | Unit-File ausliefern + manuellen Start dokumentieren; in 006 pro Host entscheiden |
| Rollback-Test | Kein Modell auf hydra → Dienst startet nicht | Deploy-/Rollback-Mechanik mit Dummy-Binary verifizieren; Modell-Bezug ist 006-Thema |
| Manifest-Reproduzierbarkeit | Timestamps/flüchtige Werte | created-Feld isolieren; Rest deterministisch |

## Offene Fragen

- Soll das Manifest die Modell-Hashes als Pflicht enthalten (sie sind ~70 GB)
  — Default: ja mit einmaligem Hashing aus P0-Befund, Referenz auf
  Provenienz-Tabelle bei identischem Inhalt

## Folge-Plan

→ `SOLO_SESSION_005_p4_upstream_sync.md`
