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

- [ ] 1. Branch `feat/p3-manifeste` von `feat/p2-python-deps`
- [ ] 2. `tools/offline/make_manifest.py` schreiben + auf P1/P2-Artefakte
       anwenden → erste MANIFEST.json
- [ ] 3. `tools/offline/deploy_local.sh`: legt versioniertes
       Artefakt-Verzeichnis an, kopiert Engine+venv-Ref+Config, setzt
       `current`-Symlink atomar
- [ ] 4. `tools/offline/rollback.sh`: Symlink zurück auf vorheriges
       Manifest-Verzeichnis + Service-Restart
- [ ] 5. systemd-Unit-Template `tools/offline/strata.service.in`
       (%h-fähig, ExecStart=run_server.sh-Pfad aus Manifest)
- [ ] 6. Rollback-Test lokal: deploy v1 → deploy v2 (Dummy-Artefakt oder
       Re-Deploy) → rollback → Dienst zeigt v1-Stand
- [ ] 7. Doku: `docs/DEPLOYMENT.md` (Manifest-Format, Deploy-Pfad,
       Rollback, Regel: Fork-only-Deployments) + ROADMAP P3 ✓
- [ ] 8. Review → Commit → Push

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
