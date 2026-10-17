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

## Schritte

- [ ] 1. LAN-Discovery abschließen (P0 begonnen): `ssh <host>` auf ganymed,
       uranus, eris — `systemctl --user list-units | grep -i strata`,
       `systemctl list-units | grep -i strata`, `ps aux | grep -i
       strata/serve`, lauschende Ports (ss -tlnp), Strata-Verzeichnisse,
       Modellpfade, InferenzQuelle-Config (welche Endpunkte zeigen auf
       Strata?)
- [ ] 2. Trilium-Notes konsolidieren: `yWi63z5N6vXc` Modellpfade,
       `NhvWTRYMEvjy` ERIS-STRATA, `5Ec9sW4aCN6S` Uranus-Testplan,
       `gpw3xvFxRc8q` Betrieb, `fvflya8lFkbH` InferenzQuelle,
       `bf6qS9vQRJXl` Eris, `Lpouldo4Bw77` Uranus, `s60i74CjMyxH` GPU-Profile
       → Deploy-Matrix (Host | Dienst | Engine-Stand | Modell | Verbraucher)
- [ ] 3. Pro Zielhost: Fork-Checkout/Artefakt-Bereitstellung — entweder
       Build auf dem Host (P1-Pfad) oder Artefakt-Transfer vom Build-Host
       mit Manifest-Verifikation (sha256 vor Ort prüfen)
- [ ] 4. Deploy-Pfad pro Host: versioniertes Verzeichnis + Unit-Anpassung
       (Pfadwechsel auf Fork-Stand), **Rollback-Symlink bleibt auf altem
       Stand** bis Smoke-Test grün
- [ ] 5. Abnahme pro Host: `/slots`- oder health-Endpunkt + eine echte
       Chat-Completions-Anfrage (kurz); InferenzQuelle-Router-Sicht prüfen
       wenn konfiguriert (admission akzeptiert Slot-Liste)
- [ ] 6. Rollback-Verifikation einmal pro Host-Typ: `rollback.sh` → alter
       Stand antwortet wieder → zurück auf Fork (dokumentierter Pfad)
- [ ] 7. Doku-Reglementierung: Trilium-Notes (Betrieb, ERIS-STRATA,
       Uranus, InferenzQuelle, Modellpfade, ggf. Host-Notes) +
       DEPLOYMENT.md um Regel ergänzen; ROADMAP-Status aktualisieren
- [ ] 8. Review → Commit → Push; Ergebnis-Tabelle Host→Stand im Bericht

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
