# SOLO_SESSION_008 — eris-Switch + Migrations-Abschluss

## Session-Ziel

Der letzte verbleibende Strata-Dienst im LAN läuft auf dem Fork:
eris-Switch nach Eval-Ende + alle Abnahmen + Restarbeiten aus den
früheren Sessions. Branch: `feat/p6-lan-umstellung` (fortsetzen).

## Stand 2026-10-17 ~15:00 — teilweise erledigt, GPU-Blocker

- [x] Gate: eris-Eval beendet (keine eval.py/server/strata-Prozesse mehr)
- [x] `systemctl --user enable --now strata-fork` ausgeführt → Engine
      startete aus dem Deploy-Dir, scheiterte dann **fail-closed**:
      `cudaMalloc` für die Weight-Arena (1,47 GiB) — llama-server
      (`eris-chat.service`, :18080) belegt 15,6 GiB der 16 GiB.
      → Dienst bewusst gestoppt + disabled (kein Retry-Loop);
      Unit bleibt installiert, Start wartet auf ein GPU-Fenster ohne
      eris-chat (Vorher-Nebeneinander gab es nie — B12 lief nur, wenn
      llama-server aus war).
- [x] N1+N2 erledigt (`5b0b6371`): `toolchain.nvcc` liest jetzt den
      effektiven Compiler aus `BUILD.json.cuda_dirs`; ninja-Probe deckt
      `.venv-offline/bin` ab — auf hydra verifiziert (`nvcc 13.4 +
      nvcc_path`), auf den Host-Checkouts per `git pull` verteilt.
- [ ] Verbleibend: eris `/slots`- + Completion-Abnahme wenn GPU frei
      (eris-chat pausiert/suspendiert oder nach Policy-Fenster);
      eris-Rollback-Übung (= alter manueller Pfad, dokumentiert)
- [ ] `~/strata-fork-configs/` + LOKAL/Trilium-Finalisierung eris → LIVE
      (erst nach erfolgreicher Abnahme)

## Schritte (Gate offen)

- [ ] 1. eris: `systemctl --user enable --now strata-fork`
       (Deploy `~/strata-deploy/d18e7fea-20261017T033934Z`,
       Config `strata-swift-iq2_xs.fork.json`, Port 8080)
- [ ] 2. Abnahme: `curl 127.0.0.1:8080/slots` (Slot-Liste + ctx),
       echte Chat-Completion (`max_tokens >= 500` — Thinking-Modell!),
       API-Key aus Prozess-Env/alter Config ermitteln falls gesetzt
- [ ] 3. Rollback-Übung eris: alten manuellen Start-Pfad dokumentieren
       (eris hatte keine Unit — Rollback = alter `server.py`-Aufruf aus
       Shell-History/Eval-Skript; kurz halten, dann zurück auf User-Unit)
- [ ] 4. `~/strata-fork-configs/` und deploy-Stand in Host-Notizen
       (Trilium `bf6qS9vQRJXl` + `Jm2JpHPKuZH6`) finalisieren;
       LOKAL.md-Tabelle eris → LIVE
- [ ] 5. ROADMAP LAN-Abschnitt: eris abhaken

## Nebenaufgaben (Gate zu oder danach)

- [ ] N1. Provenienz-Wart `toolchain.nvcc`: `make_manifest.py` soll bei
       `--cmake-def CMAKE_CUDA_COMPILER`-Override den effektiven
       Compiler aus `engine/BUILD.json.cuda_dirs` lesen statt PATH-nvcc.
       Klein (eine Datei), verifizieren mit erneutem Manifest-Lauf auf
       uranus-Checkout (erwartet „13.0" statt „12.0").
- [ ] N2. `toolchain.ninja=null` auf eris: manifest-Probe sollte
       `.venv-offline/bin` mit einbeziehen (gleiche Stelle wie N1).
- [ ] N3. Eval-Reste prüfen: auf uranus `sc117-test-q2_0.service`
       deaktiviert lassen/deinstallieren dokumentieren; Eval-Ergebnisse
       gehören in Trilium-Eval-Note (fukuro-Seite — nur verlinken).
- [ ] N4. `strata-fork.service` auf hydra-Testdeploy aufgeräumt lassen
       (/tmp/strata-deploy aufräumen falls noch vorhanden).

## Defaults

- eris-Eval läuft noch → NUR Nebenaufgaben, kein GPU-Start
- eris hat kein sudo → User-Unit ist die Endfassung (kein System-Unit)
- `--no-browser`-Lektion: bei eris-Rollback-Probe dieselbe Falle in
  alten Start-Kommandos suchen (Eval-Skripte nutzen kein --no-browser,
  aber prüfen schadet nicht)

## Risiken

- Eval-Neustart auf eris während des Switches → vor Unit-Start erneut
  `pgrep` prüfen
- eris `/` war zu ~89 % belegt → kein zusätzlicher Datenballast;
  Deploy-Dir ist klein (~90 MB), unkritisch

## Folge-Plan

→ Kettenende der Migrations-Arbeit. Danach regulärer Betrieb:
P4-Sync-Reviews bei Bedarf, P5-Entscheidung bei fukuro.
