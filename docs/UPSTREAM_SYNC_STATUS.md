# UPSTREAM_SYNC_STATUS — Integrations-Abgleich 2026-11-02

> Kanonischer Abgleichsbericht des aktuellen Integrationskandidaten.
> Plattform: **nur Linux** (Zielarchitekturen sm86, sm89; Apple/Windows
> keine Zielplattformen). Privatdetails (Hosts, Ports, Deploy-Pfade,
> Kennungen) liegen in `LOKAL.md` und privaten Notizen — hier nicht.

## Herkunft

- Vorheriger Option-C-Deployment-Stand: Merge `2a45eb38` (2026-10-22).
- Aktueller voller Merge: `aa3e61fa` (2026-11-01) des gepinnten
  Upstream-Stands `c62d5e3a15b40ea51c96aae9e8d36928965f53ab`.
- Deploy-Quellstand: `fa225161`; Referenz-Doku-Stand `3f3768dd`
  (vor diesem Abgleich, nicht der aktuelle Tip).
- Abstand zur vorigen Integration: zehn Kalendertage. Voller aktueller
  Merge statt des vorigen selektiven Paket-Uebernahmewegs.
- Die historische P0-Baseline bleibt historisch gekennzeichnet, sie ist
  keine aktuelle Bezugsbasis.

## Laufzeitstand (nach Evidenz, nicht als Abnahme)

- Beide nativen Linux-Engines sind deployt und per Health geladen
  (CPU-Vision; Wheels certifi/truststore lokal verifiziert).
- **sm86-Host**: Dienst startet `current/run.sh` → Kandidaten-Python und
  Kandidaten-Engine. `engine_recovery` meldet aktiv/idle; frueherer
  Live-Nachweis Kill→ready ~20 s protokolliert.
- **sm89-Host**: Zwischenbefund (Service-ExecStart startete
  Baseline-Python + Kandidaten-Engine) wurde 2026-11-02 korrigiert:
  Drop-in auf `current/run.sh`, kontrollierter Neustart nach Idle-
  Preflight (3 Idle-Polls) am 2026-11-02 00:07Z
  (UTC) mit neuem MainPID. Laufender Prozess: gepinntes
  Kandidaten-Checkout (serve/server.py) + `fa225161`-Engine +
  `fa225161`-Config. Gezielte Live-Pruefung bestanden: Health loaded,
  Auth-401s, 512-Token-Decode, Tool-Call mit JSON-Args, Cancel->idle->
  Followup, `engine_recovery` Feld mit `enabled:false` + 409-Verweis-
  Vertrag (Recovery bleibt aus). Nebenlast (Flux) unveraendert.
- **sm89-Alternativprofile**: Nachbefund am selben Tag: das aktive
  Ein-GPU-Profil war korrigiert, aber die inaktiven Q-/R-Startpfade
  waren noch uneinheitlich. Beide Units erhielten eigene Drop-ins auf
  den Kandidaten-`run_server.sh`; die Q-Config wurde zusaetzlich auf
  Engine/Vision/CWD unter `strata-deploy/current` umgestellt. Alle drei
  Uranus-Units zeigen jetzt auf denselben Kandidaten-Stack. Statisch
  verifiziert (`systemctl`, JSON-/Pfadpruefung); ein Laufzeittest der
  inaktiven Dual-GPU-Profile steht wegen GPU-Exklusivitaet noch aus.
- **Damit ist "vollstaendig ausgerollt und auf beiden abgenommen"
  weiterhin falsch**, aber nicht mehr wegen Mischlaufzeit: beide Hosts
  laufen nun koharent auf dem Kandidaten-Stand. Offen bleiben die
  A/B-Protokoll-Vorbehalte und der fehlende manifest-verifizierte
  Rollback-Nachweis.

## A/B-Messungen — Beobachtungen, keine Protokollabnahme

Zehn vollendete Arm-Laeufe je Host (fuenf A, fuenf B): alle Requests
HTTP 200, Hash ok, keine Abbrueche, Decode jeweils 512 Tokens.
Vorbehalte der aelteren Benchmark-Reihe (belegt): gemeinsamer Server
ueber Subtests statt frischem Prozess je Subtest; SSE-/Tool-Argumente
nicht persistiert (Tool-
finish_reason allein ist kein Tool-Call-Beweis); Temperatur-/Takt-
Telemetrie fehlt; eingefrorener Plan nannte 8 MiB memlock, Dienst
zeigt infinity; manifest-verifizierte Rollback-Uebung nicht
durchgefuehrt (previous-Symlinks/Artefakte existieren, aber kein
"rollback bereit/getestet"-Versprechen); die Vollstaendigkeit der
Belege frueher Fehlversuche ist nicht nachgewiesen. Das Functest-
Skript wertet 400/404/409/200/202 als pass und Slots-nach-Cancel nur
HTTP 200 (nicht idle) — Smoke, kein strenger Cancel-/Recovery-Vertrag.

## Mediane (nur erste zehn Laeufe, keine Diagnose-Extras)

| Host | Metrik | A→B | Delta |
|---|---|---|---|
| sm86 | decode wall | 13.622→15.058 s | +10,54 % |
| sm86 | engine predicted t/s | 45,9→41,1 | −10,46 % (R. 43,6–49 / 40,1–45,6) |
| sm86 | prompt_ms | 2019,8→2323,7 ms | — |
| sm86 | MTP-Accept | 68,42 %→60,00 % | −8,42 pp |
| sm89 | decode wall | 10,381→11,029 s | +6,24 % |
| sm89 | engine predicted t/s | 54,4→52,1 | −4,23 % |
| sm89 | prompt_ms | 963,9→1188 ms | +23,25 % |
| sm89 | MTP-Accept | 70,97 %→68,29 % | −2,68 pp |

sm89 `prompt_ms`: Verbesserung beim Vertauschen der Arme 18,86 %,
ueber dem Rauschmass der Serie (10,07 %) — Regressionssignal fuer diese
Metrik; die
Serie ist insgesamt keine Abnahme. Prefill-Waende stark verrauscht
(sm86 long A-Spanne 43–82 s; Werte siehe private Analyse).
Kein "kein Regress", kein "steady equal", keine Kausalitaetsbehauptung.

## Cache-Tuning (Begruendung + offene Messung)

- `generate.cpp` `auto_cache_slots` (~Z. 6948–6953) reserviert nun
  256 MiB fuer spaete cuBLAS/CUDA-Allokationen; sm86-Logs zeigen
  gecachte Experten 4950→4731. Sicherheitsreserve, nicht "freies RAM
  vollnutzen".
- `STRATA_DEFAULTS=026` rollt mehrere Defaults zurueck, nicht nur den
  Cache; n=3-Diagnose-Laeufe (Median 15,070 s) sind kein paarweiser
  Vergleich gegen Standard-B (15,058 s) — kein nachgewiesener Fix.
- `--expert-cache 4950` war nur vorbereitet, unvermessen und
  sm86-spezifisch — keine universelle sm89-Empfehlung.
- Naechster Schritt: kontrollierte host-spezifische Cache-Sweep mit
  denselben tatsaechlichen Memory-/Prozess-Limits, MinFree-/Load-/
  Cancel-/Long-Context-Checks, Sicherheitsreserve erhalten, jeweils
  eine Aenderung pro Lauf. **Kein Service-/Config-Tuning jetzt.**

## Taegliche eigenstaendige Upstream-Integration (Ziel, nicht aktiv)

Nutzerwunsch 2026-11-01: taeglicher **eigener** Integrationslauf fuer
kleine Diffs, damit kein Rueckstand entsteht — ersetzt die pauschale
"keine eigene Automatik"-Regel nur fuer diesen Zweck. **Kein** Einver-
staendnis fuer fremde Workflows, unreviewtes Veroeffentlichen oder
unbedingtes Produktiv-Auto-Deploy.

Ziel-Pipeline (nicht implementiert durch diesen Dokumentations-Task):
taeglicher Fetch als bewusste Online-Phase → Pin → statisches/
Sicherheitsreview (Instruktionen, Buildskripte, Deps) → lokaler
isolierter Kandidaten-Merge bei Konfliktfreiheit → relevante Offline-
Regressionen + Linux-Builds → paarweise Leistung/Funktest falls
laufzeitrelevant → aufbewahrter Bericht. Konflikt, riskanter Pin,
neuer Download-Pfad oder Gate-Fehlschlag → Quarantaene + Meldung.
Lock verhindert Ueberlappung; Produktiv bleibt stets die letzte
akzeptierte Stufe. **Der bestehende `daily`-Radar ist nur Beobachtung
und implementiert diesen Wunsch nicht.** Runner, Zeitplan, Host,
Zeitpunkt, Benachrichtigung und Ausfuehrungs-Sandbox brauchen eine
eigene Umsetzung mit Entscheidungen.

## Offen

- sm89: manifest-verifizierte Rollback-Uebung; Recovery bleibt dort
  per Policy aus (409-Vertrag belegt).
- Strengeres Cancel-/Recovery-/Slots-Vertragsprotokoll auf sm86
  (sm89 bereits streng belegt); SSE-/Tool-Argument-Evidenz und
  Telemetrie fuer kuenftige Benchmark-Reihen.
- Host-spezifische Cache-Sweeps (sm86/sm89 getrennt, je eine Aenderung).
- Umsetzung der taeglichen Integrations-Pipeline (separate Aufgabe).
