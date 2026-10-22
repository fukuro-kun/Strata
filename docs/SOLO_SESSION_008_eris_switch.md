# SOLO_SESSION_008 — eris-Switch + Migrations-Abschluss

## Session-Ziel

Der letzte verbleibende Strata-Dienst im LAN läuft auf dem Fork:
eris-Switch nach Eval-Ende + alle Abnahmen + Restarbeiten aus den
früheren Sessions. Branch: `feat/p6-lan-umstellung` (fortsetzen).

## Historischer Stand 2026-10-17 ~15:00 — GPU-Blocker (spaeter behoben)

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
- Dieser Startversuch scheiterte, weil `eris-chat` 15,6 GiB von 16 GiB
  VRAM belegte. Das war ein echter damaliger Blocker; der spaetere Start
  nach Freigabe des GPU-Speichers ist unten dokumentiert.

## Aktueller Stand — Eris live auf dem Fork

Read-only auf dem Host geprueft am 2026-10-18; keine Unit wurde dabei
gestartet oder veraendert:

- `eris-strata.service` ist **active (running)**, User-Unit, seit
  2026-10-17 23:48 CEST. Sie ist `disabled` (nicht beim Boot aktiviert);
  Lifecycle erfolgt profil-/policy-gesteuert.
- Prozessbaum nutzt den Fork-Checkout fuer `.venv-offline` und
  `serve/server.py`; Engine und Vision werden aus dem versionierten
  Deploy-Verzeichnis ueber `strata-deploy/current/run.sh` gestartet.
- `current` zeigt auf Deploy `d18e7fea-20261017T033934Z`; dies ist das
  einzige Deploy-Verzeichnis, also ist kein `previous`-Symlink vorhanden.
- Manifest: Fork-SHA `d18e7fea65f2d16626f69c4010ac457cb7ca7d77`,
  Baseline `296b59d2f73c8f04a805df29c2fa97655adace78`, Host `eris`.
  BUILD: Strata 0.1.44.1, sm_86, CUDA 12.4, lokaler Fork-Source-Hash
  `b5006933b295d641`, Vision CPU, llama.cpp-Pin `3cf03257…`.
- `/health` meldete `status=ok`, `loaded=true`, das Swift-1.5-IQ2_XS-
  Modell und Vision aktiv. Eine erfolgreiche 400-Token-Completion mit
  41,7 t/s steht im Servicejournal. Eine frische `/slots`-Anfrage ohne
  Bearer-Key erhielt erwartungsgemaess 401; das bestaetigt nicht selbst
  die authentifizierte Slot-Antwort. Die bestehende InferenzQuelle-
  Dokumentation berichtet den Endpunkt als angebunden/healthy.
- `eris-chat.service` war beim Check inactive; die GPU belegte
  14955/16384 MiB. Der fruehere `cudaMalloc`-Fehler passt zum damaligen
  VRAM-Konflikt und ist durch das spaetere Freigeben des GPU-Speichers
  ueberwunden.
- **Rollback-Frage entschieden (keine Uebung):** Ein "zurueck" setzt ein
  Produktiv-"davor" voraus — auf Eris gab es keines: der alte manuelle
  Stack war nie der InferenzQuelle-Endpunkt und ist kein Rollback-Ziel,
  sondern ein anderer Betriebsmodus. Fallback-Kette: Unit stoppen →
  Alias laeuft fail-closed ueber uranus (vor dem Switch der
  Normalzustand); eris-chat bleibt lokaler Safe-Default.
  `previous`/`rollback.sh` entsteht erst mit dem zweiten Deploy und
  wird dort verifiziert (Mechanik P3-getestet, auf uranus geuebt).

## Abschluss- und Restschritte

- [x] 1. Fork-Deploy und Eris-Profil-Unit live: `eris-strata.service`
       nutzt den Deploy-Stand `d18e7fea-20261017T033934Z` auf Port 8080.
- [x] 2. Funktionsabnahme: Health loaded und erfolgreiche 400-Token-
       Completion (41,7 t/s) im Servicejournal; InferenzQuelle-Changelog
       dokumentiert den Router-Endpunkt als healthy. Fresh unauthenticated
       `/slots`-Probe liefert 401; kein Geheimnis wurde ausgelesen.
- [x] 3. Rollback-Frage entschieden: keine separate Eris-Uebung — kein
       Produktiv-"davor" (Details oben); `previous`-Verify gehoert zum
       naechsten Deploy.
- [x] 4. Deploy-Stand und LIVE-Status in `LOKAL.md` und der bestehenden
       ERIS-STRATA-Trilium-Note dokumentiert; acht Fork-Config-Varianten
       liegen hostlokal.
- [x] 5. Fork-LAN-Status in `ROADMAP.md` aktualisiert; Rollback-Frage
       dort entschieden (Fallback-Kette statt Uebung).

## Nebenaufgaben (Gate zu oder danach)

- [x] N1. `make_manifest.py` liest bei gesetztem
       `CMAKE_CUDA_COMPILER`-Override den effektiven Compiler aus
       `engine/BUILD.json.cuda_dirs`; auf Uranus verifiziert.
- [x] N2. Die Ninja-Probe beruecksichtigt `.venv-offline/bin`, sodass
       das lokal bereitgestellte Ninja auf Eris im Manifest erkannt wird.
- [ ] N3. Eval-Reste prüfen: auf uranus `sc117-test-q2_0.service`
       deaktiviert lassen/deinstallieren dokumentieren; Eval-Ergebnisse
       gehören in Trilium-Eval-Note (fukuro-Seite — nur verlinken).
- [ ] N4. `strata-fork.service` auf hydra-Testdeploy aufgeräumt lassen
       (/tmp/strata-deploy aufräumen falls noch vorhanden).

N3 (Eval-Reste) und N4 (Hydra-Testdeploy-Aufraeumung) sind in dieser
Hostpruefung nicht neu verifiziert; Status daher unveraendert/offen.

## Betriebsgrenzen

- Kein Unit-Neustart, GPU-Test oder Rollback im Rahmen der Doku-Pflege.
- Die User-Unit bleibt policy-gesteuert und wird nicht fuer den Boot
  enabled.
- Der alte manuelle Startpfad wird nicht als Rollback-Ziel gepflegt;
  beim zweiten eris-Deploy `rollback.sh`-Verify und Symlink-Swap
  mitverifizieren.

## Risiken

- Eval-Neustart auf eris während des Switches → vor Unit-Start erneut
  `pgrep` prüfen
- eris `/` war zu ~89 % belegt → kein zusätzlicher Datenballast;
  Deploy-Dir ist klein (~90 MB), unkritisch

## Folge

Die Eris-Umstellung ist live; die Rollback-Frage ist entschieden (keine
Uebung — Fallback-Kette dokumentiert, `previous`-Verify beim zweiten
Deploy). Offen bleibt die erneute Klaerung von N3/N4. P5-Robert ist laut
Roadmap No-Go; ein moeglicher spaeterer Rust-Rewrite waere ein separates
Projekt und kein Teil dieser Fork-Migration.
