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
  Engine/Vision/CWD unter `strata-deploy/current` umgestellt. Die
  Host-Agent-Aktivierungen R und Q liefen danach kontrolliert durch;
  der strenge Live-Probe (Health, Auth-401s, Decode, Tool-JSON-Args,
  Cancel->idle->Followup, Recovery-409) und eine Vision-Anfrage
  bestanden auf beiden Profilen. Anschliessend wurde T wiederhergestellt;
  gleicher Probe, Vision-Anfrage und Flux-/Host-Agent-Health bestanden.
  Alle drei Uranus-Strata-Units zeigen auf denselben Kandidaten-Stack.
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

## Beobachtungsstand 2026-11-10

- Neuer Upstream-Tip `dbb2d168cffa8cf793d9325358809d5263c7c6b0`
  (App 0.2.13 / Engine 0.1.59.1; +1.318 Commits seit `c62d5e3a`)
  im RADAR `upstream-reviews/RADAR_2026-11-10T202129Z_dbb2d168cffa.md`
  dokumentiert — nur Bestandsaufnahme, kein Clean-Verdict.
- Nutzer-freigegebener Folgeplan (Masterplan): (1) Security-Paket
  Pillow/Vision (`8181522f`, GHSA-78g4-xqwv-q3g8, Allowlist +
  Pillow-13-Wheels mit Hash-Nachweis), (2) Stabilitätspaket
  Server-Lifecycle/Vision, (3) Schliessen der offenen Gates hier oben
  samt Regressions-Diagnose, (4) Grosssync-Entscheidung, (5) taeglicher
  Radar-Timer (nur Beobachtung). Deploy-Reihenfolge nach
  Expositions-Befund.
- Seitenaeste ausserhalb dieser Linie (kein Handeln, separate
  Entscheidung): `feat/deploy-config-guard` (required-args/deploy-guard
  `8483495e`, Radar-Doc `b501b7f4`), `feat/native-stall-safety`
  (eris-recovery-Worktree).

## Phase-1-Ergebnis 2026-11-11: Security-Deploy, Rollback offen

- **Befund:** Bei der letzten Live-Abfrage verwendeten beide Dienste
  Pillow 12.3.0 mit verfuegbarem JPEG-2000-Decoder und aktiver Vision.
  Der Requestpfad zum Decoder wurde statisch nachvollzogen; ein Angriff
  oder praepariertes Bild wurde nicht live durch den Dienst getestet.
- **Kandidat:** `feat/sync-2026-11-10-pillow-sec` @ `22c64d47` (auf
  `6c0edb8b`): Cherry-Pick `8181522f` upstream-identisch (range-diff),
  `PICTURE_FORMATS`-Allowlist an allen drei `Image.open`-Stellen,
  Pillow-Split-Pin (13.0.0 py>=3.11 / 12.3.0 py<3.11), Wheelhouse-
  Manifest +2 Hashes (cp312 `42d63be3`, cp314 `e91c2b1c`),
  INVENTAR-Pin nachgezogen. cp312 stimmt mit Upstream-Lock und PyPI
  ueberein; cp314 mit PyPI-Metadaten und heruntergeladenen Bytes.
  Letzteres sind keine zwei unabhaengigen Bezugsquellen.
- **Gates:** 37 isolierte Tests gruen (Podman, Netz aus, py3.12):
  ds_pictures 19 / exif 9 / pins 9 sowie JP2-Ablehnung und PNG-
  Passthrough. Der Test zum Decoderaufruf ist laut Gegenpruefung
  zirkulaer; der separate Spy prueft die uebergebenen Formatlisten.
  Details: `upstream-reviews/REVIEW_2026-11-11_1b387a65b3e4.md`
  auf dem Security-Branch. Der Dateiname enthaelt nicht die korrekte
  12-stellige SHA; der gepruefte Code-Commit ist
  `1b387a653d90dfbb144312eada49db2a7fc1ced0`.
- **Lokaler Nachtest:** Auf Python 3.14/Pillow 13 bestanden 37 Tests
  in einer netzlosen Bubblewrap-Umgebung. Der separat gepruefte
  Test-Commit `c4680b8a` auf dem Follow-up-Branch schlug bei
  absichtlich geoeffneter Formatliste fuer beide Dekoderpfade fehl;
  er ist nicht Teil dieses Stabilitaets-Commits.
- **Deploy:** Laut damaliger Abnahme liefen beide Dienste auf
  `22c64d47` mit Pillow 13.0.0 und beantworteten einen Textrequest;
  Health meldete Vision aktiviert. Ein produktiver Bildrequest wurde
  dabei nicht nachgewiesen.
- **Manifest-Grenze:** `--verify` prueft Engine-Bytes, Checkout-SHA,
  Pin, deklarierte Wheel-Hashwerte und den Paketstand per `pip freeze`.
  Es hasht weder die Wheel-Dateien noch die installierten Venv-Dateien
  erneut. Die Wheel-Dateien wurden damals separat mit `sha256sum -c`
  geprueft; das ist kein Byte-Nachweis fuer die installierte Venv.
- **Rollback-Gate OFFEN:** `previous` verweist auf den alten Deploy,
  aber `rollback.sh` stellt weder den gemeinsam genutzten Checkout
  noch die Venv wieder her. Bei abweichender Checkout-SHA oder Venv
  verweigert die Manifestpruefung den Wechsel. Ein vollstaendiger,
  manifest-verifizierter Rollback ist weder automatisch noch geuebt.
  Kein weiterer produktiver Wechsel, bevor ein passender Rueckweg
  vorbereitet und getestet ist.
- **Live-Nachpruefung:** Auf beiden Zielsystemen bestand die
  Manifestpruefung von `current`; die von `previous` scheiterte
  reproduzierbar an `fork_sha` und `venv pip_freeze drifted`. Beide
  Dienste waren aktiv. Die Pruefung aenderte weder Symlinks noch
  Dienste; sie ist keine Rollback-Uebung.

## Phase 2: Stabilitaetskandidaten, lokal und nicht deployt

**Lokaler Zwischenstand:** `00eb572a8e9de617aeaa938f7276ec4b8659dc66`
adaptiert den Control-Line-Wakeup `f1fd753d` und den ConvCacheLog-Lock
`3f6960f1`. Der Condition-Check wurde an den vorhandenen Fork und
seine Admission-/Recovery-Logik angepasst, kein unveraenderter
Cherry-Pick behauptet. Die unabhaengige Gegenpruefung des Diffs und
der ergaenzten Tests fand zuletzt keine kritischen oder wichtigen
Befunde. Ein zunaechst vermuteter mehrsekundiger Blocker durch
`Popen.poll()` wurde nach Pruefung der tatsaechlichen Python-3.12- und
3.14-Implementierungen zurueckgezogen.

**Testnachweis:** 72 Tests (`test_serve_robustness`, `test_admit_order`,
`test_engine_recovery`, `test_monitor`) bestanden unter Python 3.14 in
Bubblewrap ohne Netzwerk und ohne Produktionsdaten. Die Venv verwendete
das gepruefte lokale Wheelhouse. Bei einer Negativkontrolle ohne den
Cache-Lock schlug der betreffende Test wie erwartet fehl; der echte
Code wurde dafuer nicht geaendert. SHA-256 der privaten Rohlogs:
`7489e11619df411da4d40903c23fd10d25e2a445853eef61d6328f6dbce83a5a`
(Tests) und
`f656b62c581a67a0e046e5bd4eace0a49ac3dff085d16a789f2fafd7effb5ecb`
(Negativkontrolle). Die Logs liegen im lokalen Evidenzarchiv.

**Offen:** Formeller paketbezogener Review-Bericht und begruendeter
A/B-Nachweis oder Ausnahme, alle weiteren Kandidaten, vollstaendiger
Rollback und produktive Abnahme. Der Commit ist weder gepusht noch
promoted oder deployt und keine Freigabe fuer das Gesamtpaket.

Weitere Quellen fuer eine Einzelpruefung aus `dbb2d168`:
Streaming-Disconnect `c08fd2ec`, Startfail-Popen-Race `0d922698`,
Lost-End-Event `a8767488`, Abort-DONE-Swallow `9aea047e`,
Lifecycle-Bundle `c30aa647`, Vision-READY-Pipe `4cce1ee4`,
Vision-CPU-Fallback `c53e45a3` + Reporting `78eaaf1b`/`7e8206b5`.
**Pflicht-Interaktionspruefung:** fork `engine_auto_restart` (im
Deploy-Stack) + Vision-Lock-Fix `6ef6931a` + die neuen
`formats=`-Zeilen. Regressionstests pro Fix, review-swe vor Commit,
REVIEW-Bericht, Deploy nur nach Gates.
