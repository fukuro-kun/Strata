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

**A/B-Versuch vom 12.11.: ungueltig, Freigabe blockiert.** Der
Produktivarm verwendete einen laufenden Prozess mit Cache und einen anderen
Config-Pfad als der frisch gestartete Kandidat `5269b4a1`. Der aktuelle
Config-Vergleich zeigt unterschiedliche GPU-Zuordnungen; Config-Hashes
aus dem Testzeitpunkt fehlen. Im Kandidatenlog scheiterte `mlock`. Der
Host-Agent versuchte im Testfenster, einen als fremd betrachteten
GPU-Prozess mit SIGTERM zu beenden und die Produktiv-Unit neu zu
starten; der Port war bereits belegt. Die Zuordnung der protokollierten
PID zur Kandidaten-Engine ist nicht sicher belegt. Der zuvor behauptete
Lifecycle-Fehler ist damit nicht nachgewiesen. Die verfuegbaren Rohlogs
und Nachtraege liegen im privaten A/B-Evidenzarchiv; der Messclient und
die vollstaendigen Request-Payloads wurden nicht archiviert. Ein isolierter
Wiederholungsversuch und alle weiteren Freigabegates sind offen.
Die noch nicht veroeffentlichten Zwischencommits mit internen
Konfigurationsdetails benoetigen vor einem Push eine gesondert
freigegebene Historienbereinigung.

**Diagnosekorrektur:** Die bereits in der Basis enthaltene allgemeine
RAM-Vermutung war bei SIGTERM irrefuehrend. Die Meldung benennt jetzt
das Signal und laesst dessen Quelle offen; Lifecycle und Recovery sind
unveraendert. Der nachfolgende Serve-Volltest bestand mit 1.432 Tests
(17 uebersprungen) in Bubblewrap ohne externes Netz. Nach einem
zusaetzlichen Fix zweier vorbestehender offener KFD-Topologiedateien
bestanden 100 gezielte Tests, darunter 512 Tokens ohne Signal, externes
SIGTERM nach 432 Tokens und ein nativer Fatal-Fehler. Der Volltest wurde
nach dem KFD-Fix nicht wiederholt. Weitere ResourceWarnings zu Sockets,
Pipes und HTTP-Fehlerobjekten bleiben ungeklärt; kein GPU- oder
A/B-Nachweis.

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

## Telemetrie: ResourceWarnings lokal behoben

Der separate Fork-Fix `6565930474890f7c6857e05ad7bc4bcf215c5892`
schliesst die bisher offenen CPU-/RAM- und Topologie-Dateien. Nicht
lesbare oder unvollstaendige Messwerte bleiben unbekannt statt den
Serverstart mit einer Exception abzubrechen. 19 Telemetrie-/Monitor-
und 6 Topologie-Tests bestanden in Bubblewrap ohne Netz; die
Negativkontrolle mit dem frueheren offenen `/proc/stat`-Read schlug
wie erwartet fehl. Die unabhaengige Gegenpruefung fand keine
kritischen oder wichtigen Befunde. Private Rohlogs SHA-256:
`d7462cb243b8feb1ba9586d9de037e068c900b3f66fc99b71eb36f076bacc641`
(Tests) und
`6f77c6a2140ddf4cbe0957d0f272fdf4c7d4992d28d8c1fbad687ccdef195887`
(Negativkontrolle). Kein Deploy, Paketfreigabe bleibt offen.

## Start-Race-Prüfung (abgeschlossen)

Der Upstream-Kandidat `0d922698f2a44e0d5e7bef8516c620bec0bba097` ist als
Fork-Fix `ec8f6e45` umgesetzt: Das Prozessobjekt wird schon beim Spawn
lokal gehalten (der Upstream-Patch erfasst es erst nach der Zuweisung)
und `restart()` dereferenziert ein zwischenzeitlich freigegebenes
`self.proc` nicht mehr. Deterministische Negativtests belegten drei
`AttributeError` vor dem Fix; danach 80 isolierte Tests grün
(inkl. Auto-Recovery und Restart-Waiter). Unabhängige Gegenprüfung:
ship-ready, keine P1.

Verbleibende Technical Debt (P2, nur über den fifo-losen
Shutdown-Closer erreichbar, Kindprozesse werden von
`lifeline.end_children`/PDEATHSIG eingeholt): `close()` dereferenziert
`self.proc` noch nicht atomar, `exit_code()` hat ein TOCTOU-Fenster,
einzelne stdin-Schreiber fangen `AttributeError` nicht, ein
`ValueError` aus `popen` hinterlässt Narrator und Log-Handle, und das
Post-READY-Fenster kann `ended=False` gegen ein interleavendes
`close()` setzen. Kein Deployment-Blocker, aber Kandidat für einen
eigenen Folge-Fix.

## Stabilitätspaket (Cherry-Picks aus `dbb2d168`, Stand 11.11.)

Neun Upstream-Fixes als selektive Picks integriert, einzeln mit
Konfliktauflösung gegen die Fork-Basis:

| Pick | Upstream | Inhalt |
|---|---|---|
| `5627d0f1` | `c08fd2ec` | Streaming-Write-Timeout: stoppender Client gibt die Engine-Runde frei (#4271) |
| `1ef07c22` | `9aea047e` | ERR/DONE-Synchronisation: trailing DONE nach NaN-Stop wird nicht vom nächsten Request gelesen |
| `1a3cdc17` | `c30aa647` | Activity-Lease für serve.py-Start, Update-Default = Checkout-Store, Orphan-Encoder bei toter Engine |
| `9babfe65` | `a8767488` | Fehlendes End-Event beendet die Engine nur bei Prozess-/Turn-Identität (#3961) |
| `1d02d1fe` | `4cce1ee4` | Vision-READY-Pipe: eine Deadline, Stray-Lines gehalten, kein Kill bei nur druckendem Reader |
| `7349e8a2` | `78eaaf1b` | Vision-No-Room-Diagnose + `childenv.py`/`reader_room.py` vendored |
| `c1c6635c` | `c53e45a3` | Vision-CPU-Fallback in allen Modi (NVIDIA gleiche Binary ohne `--gpu`) |
| `010a7926` | `7e8206b5` | Gemeldeter Bedarf = Gesamtbedarf am Image-Limit, nicht die gescheiterte Allokation |
| `78acbc8c` | — | Merge-Fixes: `lines_q`→`self.lines`, Busy-vor-Dead-Reihenfolge in `unload()`; `split_engine.py` vendored, `VRAM_STOP_NEXT` nachgezogen. Der damalige `getattr`-Lock-Fallback wird im aktuellen Arbeitsstand wieder entfernt. |
| `09cd5a16` | `75acfca3` | Opt-in `undeclared_tool_calls=call` mit Parser-Backport; Default bleibt `text` |

**Bewusst NICHT übernommen:** upstreams `apply_vision_defaults` /
`vision_on_demand_by_default` (Default-Änderung `vision.elastic`=on,
wird im Fork nicht aufgerufen; Elastic bleibt konfigurationsgesteuert).
`f1fd753d` bereits durch `00eb572a` abgedeckt (Code + beide
Upstream-Tests vorhanden).

**Korrigierter Teststand:** Fuer einen frueheren Paketstand wurden
1423 Serve-Tests (14 uebersprungen) in Bubblewrap ohne Netz mit
entpackten Wheel-Abhaengigkeiten gemeldet. Die 35 Terminal-Tests liefen
hingegen **nicht** in Bubblewrap; die fruehere Aussage oben war falsch.
Von vier FAILs des ersten Laufs waren mindestens zwei echte
Integrationsfehler bei der Unload-Reihenfolge, keine blossen Last-Flakes.
Der nachtraegliche Parser-Pick und die noch uncommittierten Korrekturen
sind durch diesen historischen Lauf nicht abgenommen.

Die unabhängige Gegenprüfung des Gesamtpakets wurde durch Rate-Limits
abgebrochen und ist **offen**. Eine erneute Auswertung ist nur fuer den
tatsaechlich endgueltigen Code- und Abhaengigkeitsstand gueltig.

**Lokaler Arbeitsstand nach `09cd5a16`:**

- Eine versehentlich mit der Vision-Diagnose uebernommene Aenderung der
  VRAM-Kontextplanung wurde ausgegrenzt. Der bestehende Planungsanteil
  entspricht wieder der Basis vor dem Vision-Paket; der explizite
  Kontext bleibt dabei wie bisher geschuetzt. Die Entscheidung ueber
  eine spaetere Upstream-Aenderung der Defaults ist separat offen.
- `Vision` nutzt beim Wiederherstellen seines Arbeitsverzeichnisses den
  Cache-Lock auch in Tests. Die Dead-Engine-Bereinigung entlaedt einen
  noch laufenden Encoder nur einmal. Die Terminaldiagnose nutzt die
  vorhandene VRAM-Telemetrie statt ein neues Programm ueber `PATH`
  aufzurufen. Die ungenutzte Vendordatei `split_engine.py` wurde in `b11b6776`
  wieder entfernt — nach der `card_free_mib`-Umstellung importierte
  nichts mehr das Modul; eine Uebernahme folgt erst mit dem
  Split-Engine-Feature selbst und dessen Review.
- 162 gezielte Tests und danach 1427 Serve-Tests (17 uebersprungen)
  bestanden in Bubblewrap mit eigenem Netzwerk-Namespace und lokalem
  Loopback. Die Abhaengigkeiten wurden in eine echte Venv aus einzeln
  hashgeprueften lokalen Wheels installiert. Der nachtraegliche
  `tool_choice=none`-Test bestand separat in 18 Tool-Choice-Tests.
  Rohlogs SHA-256:
  `d3ecc4d791b8ec893fd96a72f83210edd9d1178ca13f7385cea7feee1f827b90`
  (gezielt) und
  `b995aa37a7c3fe81da9aea90a01a996083bb165d64faabd640f93d35e84d89ce`
  (Serve-Suite); die Logs liegen lokal und sind keine GPU-Abnahme.
- Der unabhaengig gepruefte Decoder-Test aus `c4680b8a` fehlte auf dem
  Stabilitaetszweig und wurde in `f22bedb9` uebernommen. 28
  Bild-/EXIF-Tests bestanden danach isoliert mit Pillow 13. Der grosse
  Serve-Lauf fand vor dieser Testanpassung statt.
- `undeclared_tool_calls=call` bleibt Opt-in. Bei ausdruecklichem
  `tool_choice=none` bleibt der Aufruf Text; bei ganz ohne deklarierte
  Tools greift die Option derzeit ebenfalls nicht. Letzteres ist auch
  im uebernommenen Upstream-Code so und vor einer Nutzung zu klaeren.
- Die fruehere Diagnose eines fehlenden `ensurepip`-Bundles war falsch:
  Die Distribution liefert das pip-Wheel getrennt; die Sandbox brauchte
  fuer dessen Bootstrap eine lesbare System-CA-Datei. Python und dieses
  OS-pip sind zusaetzliche, lokal bereitgestellte Vertrauensanker.
- Der Offline-Venv-Installer wurde gegen manipulierte Umgebung, fremde
  pip-Quellen, direkte Requirements- und Metadaten-Links sowie
  Veraenderungen von Wheels und Manifest waehrend der Installation
  gehaertet. 16 isolierte Tests bestanden; Negativkontrollen am jeweils
  frueheren Stand belegten die Fehler. Der echte Installer erzeugte in
  Bubblewrap Venvs aus dem vorhandenen Wheelhouse mit Python 3.14 und
  ohne CUDA bzw. mit CUDA-12-/CUDA-13-Wheels; `pip check` und Imports
  bestanden. Der abschliessende atomare Venv-Anlagepfad wurde dabei mit
  CUDA 13 erneut durchlaufen. Python 3.12, ein GPU-Build und die
  unabhaengige Pruefung dieses Installers bleiben offen.

**Radar:** Der separate lokale Rohdaten-Radar bestand 19 netzlose
Tests mit synthetischen Git-Repositories. HTTPS, Timer, Zustellung und
Host-/Zeitpunktfreigabe sind nicht geprueft oder aktiviert; der Digest
ersetzt keinen vollstaendigen Tagesbericht. Der lokal bekannte
Upstream-Tip `dbb2d168cffa8cf793d9325358809d5263c7c6b0` ist der
Beobachtungsstand vom 2026-11-10, kein Nachweis der heutigen Aktualitaet.

**Grosssync-Entscheidung:** Bis ein vollstaendiger Zieldiff und seine
Lieferkette sowie der geforderte A/B-Vergleich vorliegen, ist eine
Volluebernahme nicht freigabefaehig. Vorlaeufig bleiben kleine,
zusammenhaengende Picks der risikoaermere Arbeitsweg; auch diese sind
erst nach den gleichen relevanten Gates freizugeben. Das ist keine
endgueltige Entscheidung gegen einen spaeteren Vollsync.

**Offen:** A/B-Nachweis und rollback-/Promotions-Gates.
Nicht gepusht, nicht deployt. Der einzige C++-Hunk (`nan_stop`-Guard
in `src/dsv41/ds4_main.cpp`) wurde in `b33f30e7` zurueckgenommen, weil
die Variable zu Upstreams NaN-Stop-Pfad gehoert, den diese Basis nicht
enthaelt — er waere ein Kompilierfehler geworden. Damit braucht der
Kandidat keinen Engine-Neubau; die serverseitige Schutzschicht
`_swallow_trailing_done` bleibt aktiv.

## Stand 2026-11-16: Integration `baf16363b` (v0.2.14 / engine 0.1.60)

Zweiter Vollmerge seit `c62d5e3a`: **2.132 Upstream-Commits, ~50 Konflikt-Pfade**
manuell aufgelöst, Branch `feat/sync-2026-11-16-merge-v0214`, Merge-Commit
`a146dfdf7` mit Review-Fixes bis `fea002cf3`. Die Radar-Kandidaten K2–K4
(Prefill/q36, serve/-Lifecycle, Restbestand) gingen in einem atomaren Merge
zusammen durch; die Gate-Kette gilt einmal für den Gesamtstand.

**Gehaltene Fork-Divergenzen:** Acquisition-Default-Deny an allen Netz-
Primitive; MMQ-Marge mit voller Row-Space-Bound (`T*K`, `(Rt,Rt)`, `(ne,ne)`)
an allen Callsites — Upstreams engere `max_rows <= T`-Semantik bewusst
nicht übernommen; Engine-Auto-Recovery vollständig (upstream hat kein
Äquivalent); DSV41-Stack mit Upstream entfernt (Fork ist Qwen-only);
kein FetchContent im Default-Build-Pfad.

**Gates (alle bestanden):** statische Prüfung (keine Marker/Doppel-Defs/
ds_pictures-Referenzen/FetchContent-Default), Python serve-Suite komplett
grün (inkl. Fork-Recovery- und Telemetrie-Fixes), `tools.test_setup_engine_hash`
30/30 (pre-existing Acquisition-Fix), `mmq_ids_margin_test` ok, hydra-Build
0.1.60.1 (CUDA 13.5, ggml-Pin `3cf03257`), 25/25 Merge-relevante C++/CUDA-
Tests, `cuda_spill_guard` grün (3 neue dflash2-Instanzen exakt gemessen in
die sm_86-Baseline aufgenommen), eris-Build (g++-13, CUDA 12.4) grün,
eris-Deploy `e6cdef3a-*` (Manifest `--verify` all match), Smoke ok.

**A/B (eris, 5 gepaarte Runden + Probeläufe, eingefrorener Plan/Payloads):
NO_SIGNAL** — t1_4k B +38.9 % unter Rauschen 53 %, t1_16k −3.3 % unter
Rauschen 27.7 %, t2_decode −9.5 % unter Rauschen 46.9 %; T3-Delivery 25/25
auf beiden Armen inkl. Tool-Call-Assertion. Hohe Varianz ist Befund, kein
Fehler: Prefill ist auf dieser Config expert-I/O-bound, der erste große
Prompt nach Restart dominiert die Streuung. Kein Regressions-Signal → keine
Promotions-Sperre.

**Review:** unabhängig in drei Runden — R1 (P1 Publish-Doppelblock +
loopback/`urlopen` + Guards gefixt in `78bd00cc1`), R2 (P1 Degenerate-
Testfall korrigiert in `2eb4d055b`, Rest ship-ready), Tail-Review
`b95c3372e`+`e6cdef3af` ship-ready mit P3-Nachzug `fea002cf3`.

**Offen/Nachzug:** uranus (sm_89) ausgeschaltet — kontrollierter Nachzug
beim Wiederanlauf mit CUDA 13.0/sm_89-Build; dort kann `cuda_spill_guard`
die drei neuen dflash2-Instanzen erstmalig messen (sm_89-Allowance deckt
die Familie nur mit 8 B, gemessen wurden 16 B auf sm_86). Promotion auf
`main` und Deploy-Abschluss siehe `INTEGRATION_2026-11-16_strata-v0214-merge.md`.
