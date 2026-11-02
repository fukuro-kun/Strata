# SESSION_PLAN — Vollstaendiger Strata-Upstream-Abgleich

## Ziel und Status

Den freigegebenen vollstaendigen Git-Merge des gepinnten Upstream-Stands
`c62d5e3a15b40ea51c96aae9e8d36928965f53ab` vorbereiten, pruefen und nur bei
bestandenen Gates promovieren. Kein Quellen-Snapshot als Ersatz.

**Status: DEPLOY-KOHAERENZ HERGESTELLT, ABNAHME TEILOFFEN.**
Merge `aa3e61fa` + `fa225161` gepusht; beide Hosts laufen seit
2026-11-02 00:07Z auf dem vollen Kandidaten-Stand (sm89:
Drop-in + kontrollierter Neustart nach Idle-Preflight und bestandene
gezielte Live-Pruefung). Auf sm89 wurden danach auch die inaktiven
Q-/R-Profil-Startpfade auf denselben Kandidaten-Stack korrigiert und
kontrolliert live getestet (strenger Probe + Vision jeweils bestanden,
Rueckkehr zu T/Flux verifiziert). Zehn A/B-Arm-Laeufe je Host sind
Beobachtungen — keine vollstaendige Abnahme; Regressionssignal sm89
prompt_ms dokumentiert.
Kanonischer Abgleich: `UPSTREAM_SYNC_STATUS.md`; Gates:
`UPSTREAM_SYNC.md`, `UPSTREAM_BENCHMARKS.md`, `../ROADMAP.md`.

Die frueheren `SOLO_SESSION_001` bis `008` dokumentieren vorherige Phasen.
Ein dortiger historischer No-Drift-Befund oder Massen-Diff-Kurzweg ist
keine Freigabe fuer diesen Merge.

## Entscheidungen

| Frage | Entscheidung | Begruendung |
|---|---|---|
| Umfang | Voller Git-Merge samt Historie | Ausdruecklicher Nutzerwunsch, wenig Upstream-Drift |
| Basis | Dokumentierter neuerer Recovery-Fork-Stand | Recovery-Schutz nicht durch veraltetes main verlieren |
| Bezugsweg | Eigener Fork, lokale Source-Builds | Kontrollierte Versorgungskette |
| Workflows | Nur workflow_dispatch; alle Jobs auf Niko1221/Strata begrenzt | Keine fremden automatischen Ablaeufe auf Fork/Mirror |
| Tests/Rollout | Sequentielle Testfenster, danach nur bei erfuellten Gates ein Host nach dem anderen | Anderen Endpunkt verfuegbar und Rollback bereit halten |
| Benchmark-Profil | Je Host tatsaechliches eingefrorenes aktives Profil | Kein Vergleich mit veralteter Dual-GPU-Dokumentation |
| Unklare Befunde | Aufrufkette belegen; Hypothesen nicht zu Tatsachen machen | Keine falschen Freigaben oder unnoetigen Eingriffe |
| Fehlende Gates | Lokal quarantiniert weiterarbeiten | Kein Push zur blossen Sicherung |
| Pruefumfang | Auszuliefernder Stand und verwendete Lieferkette; keine historische Vollpruefung | Nutzerentscheidung 2026-11-01: zuverlaessiger, moderner und leistungsfaehiger Betrieb |
| Plattformen | Linux; Apple und Windows ohne Build-/Funktionsabnahme | Nur Linux-Ausfuehrung, gemeinsame Komponenten und Malware-Risiko relevant |

## Schritte und Verifikation

| Schritt | Status | Verifikation |
|---|---|---|
| Fork-Basis, Deployment-Vertrag und Umfang feststellen | Erledigt | Gepinnte SHAs, vorhandene Review-Belege und lokale Evidenz |
| Gesamtmerge vorbereiten; Konflikte/Pins korrigieren | Erledigt, noch keine Freigabe | Vollstaendige Konfliktnaht-Diffs; gezielte Offline-Tests |
| Workflow-Trigger und Job-Guards absichern | Erledigt | Fuenf netzlose Workflow-Regressionstests; keine Actions ausfuehren |
| Betriebs- und Lieferkettenreview abschliessen | In Arbeit | Zieldiff, Fork-Anpassungen, verwendete Komponenten und erreichbare Nebenpfade; andere Bereiche als nicht abgenommen ausweisen |
| PGroup-Fensterueberlauf absichern | Implementiert, Gegenpruefung offen | Fail-closed vor PGroup; CPU-Grenzen und TU-Uebersetzung jeweils 8/16 |
| Lokale Engine-Pakete und DeepSeek-Beschaffungsprobe absichern | Implementiert, Gegenpruefung offen | Fuenf / sieben isolierte Testmethoden; gemockte Nebenwirkungen, keine echten Updates |
| MCP-Modellinstaller und Hintergrundjob vorab absichern | Implementiert, Gesamt-Gegenpruefung offen | Acht isolierte AST-/Mock-Methoden, Negativbeleg vor lokalen Zugriffen; kein Installerlauf |
| CUDA-12-Treiberfloor-Feed vor Threadstart absichern | Implementiert, Gesamt-Gegenpruefung offen | Sieben Gate-Tests und sechs selektierte Upstream-Methoden isoliert; lokale Metadaten bleiben erlaubt |
| Implizite DLL-Reparatur aus HIP-Hardwareprobe entfernen | Implementiert, Gesamt-Gegenpruefung offen | Sechs isolierte AST-/Mock-Methoden; fuenf negative Subtest-Assertions am Original; explizite Installation repariert weiter |
| Direkte Metal-/SYCL-Buildpfade und Backend-Exitcodes absichern | Implementiert, Gesamt-Gegenpruefung offen | Dreizehn isolierte AST-/Mock-Methoden; Original: zwoelf Gate-Fails und vier unbehandelte Verweigerungen; keine reale Kompilation |
| Eigenstaendige MTP-Beschaffung absichern | Implementiert, Gesamt-Gegenpruefung offen | Dreizehn isolierte Gate-/Mock-Methoden und drei bestehende Range-Methoden; Offline-verify bleibt erlaubt; keine Downloads |
| Uebrige bestaetigte Fehler beheben oder explizites Technical Debt abstimmen | Offen | Reproduzierbarer Beleg, minimaler Fix, passende Regressionstests |
| Unabhaengige Gegenpruefung | Erledigt, 1 P1 behoben | review-swe frischer Kontext: bereit fuer isoliertes Host-A/B; P1 LOKAL.md vs. Dirty-Tree-Gate per .gitignore geschlossen |
| Messclient bereitstellen | Erledigt | `ab_client.py` gefroren (sha 063f4ba0), SSE+TTFT+Engine-Timings, Abbruch bei Fremd-GPU/RAM-Not |
| Beide Vergleichsarme offline aus lokalen Quellen bauen | Erledigt | Kandidat aa3e61fa pro Host nativ gebaut (sm86 gcc-13/nvcc-12.4, sm89); aktuelles Manifest verifiziert (fork_sha fa225161, 3 Artefakte + 27 Deps); Rollback-Artefakte existieren, Uebung nicht bewiesen |
| Host-spezifischen Messplan und Payloads einfrieren | In Arbeit | Payloads v3 (disjunkte Prefill-Slices, 4300/15176 Tokens), plan.json nach Artefakt-Hashes |
| Freigegebene A/B-Messungen ausfuehren | Beide abgeschlossen (Beobachtung) | 10 Arm-Laeufe je Host (5A+5B), alle 200/hash_ok, Decode 512 — Beobachtungen ohne Protokoll-Abnahme: Shared-Server, keine SSE-/Tool-Args-Persistenz, keine Temp-/Takt-Telemetrie, memlock-Abweichung, kein manifest-verifiziertes Rollback; Vorbehalte und Mediane `UPSTREAM_SYNC_STATUS.md` |
| Messergebnisse und Nutzen selbst beurteilen | Wiederoffen | Zehn Arm-Laeufe/Host sind Beobachtungen, kein Protokoll (Shared-Server, keine SSE-/Tool-Args, keine Telemetrie); sm86 Decode +10,5 %, MTP −8,4 pp; sm89 prompt_ms +23 % mit 18,9 %-Rueckwaerts-Signal > Rauschen — Regressionssignal, keine Abnahme; Details `UPSTREAM_SYNC_STATUS.md` |
| Finalen REVIEW-Bericht und Provenienz abschliessen | In Arbeit | sm89-Laufzeit kohaerent seit 2026-11-02 00:07Z (Drop-in+Neustart); strenge Live-Pruefung auf sm89 bestanden (Auth-401s, Decode, Tool-JSON-Args, Cancel->idle->Followup, Recovery-409) — das beweist Cancel/Recovery-Vertrag nur dort, nicht beidseitig; offen: manifest-verifizierte Rollback-Uebung, Protokoll-Vorbehalte der aelteren Benchmark-Reihe |
| Promotion und Forgejo-Push | origin-Push erfolgt, weitere Promotion gesperrt | Branch + Merge-Stand bereits auf origin gespiegelt (Push-Mirror); weitere Promotion/Merge-Gates bleiben offen — kein direkter Upstream-/Mirror-Push |
| Kontrollierter Rollout mit Rollback | Teilweise | sm86 + sm89 laufen beide auf Kandidatenstand (sm89 nach Korrektur-Neustart + strenger Live-Pruefung bestanden); sm89-Q/R-Startpfade korrigiert und live getestet (strenger Probe + Vision, Rueckkehr zu T/Flux verifiziert); Functest = Smoke, kein strenger Vertrag; manifest-verifizierte Rollback-Uebung ausstehend — `previous`-Symlinks existieren, 'bereit/getestet' nicht versprochen |

## Audit-Zwischenstand

- HTTP-Server und Owner-/Runtime-Control sind vollstaendig gelesen.
- `generate.cpp` ist nach der Abschlussregion bis Dateiende vollstaendig
  gelesen; das allein deckt nicht alle aufgerufenen Engine-Abhaengigkeiten.
- Neuer PGroup-Guard verweigert zu breite Pipeline-Gruppen gegen die
  effektive Verifier-Grenze. Serielles Batch-MTP bleibt unveraendert.
- CPU-Grenztests und einzelne Host-C++-Uebersetzungen bestehen fuer acht
  und 16 Fensterzeilen. Kein gelinkter Engine-/GPU-Nachweis daraus.
- Feed-/Signatur-/Transfer-/Updater-/Komponentenmodule sind vollstaendig
  statisch gelesen. API-Key-Wiederherstellung im Update-Teststart und
  Stage-Grenze fuer `unpack_to` minimal korrigiert; vier beziehungsweise
  sieben isolierte Unit-Testmethoden bestehen. Kein realer Updaterlauf.
- Auch fuer diese beiden Control-Korrekturen bleibt die unabhaengige
  Gegenpruefung offen; die gruenen Tests sind keine Promotionsfreigabe.
- Explizite lokale Engine-Pakete brauchen jetzt dasselbe Beschaffungs-
  Gate wie Downloads. DeepSeek-Remote-HEAD sowie lokale Pakete sind
  ebenfalls vorgeschuetzt; Install/Upgrade verweigern vor lokalen
  Vorbereitungen. Fuenf beziehungsweise sieben isolierte Methoden
  bestehen mit Negativbelegen. Keine echten Pakete installiert.
- Komponentenresolver, Draft-/Vision-/HIP-Helfer, lokales Modellpreview
  und Terminal-Einstiege sind weiter statisch durchgesehen. Dynamische
  Setup-/MCP-Imports der Katalog-/Preview-Helfer bleiben eine explizit
  zu pruefende Abhaengigkeit; nicht als reine Literal-Lektuere ausfuehren.
- Das zuvor gebaute Engine-Artefakt beschreibt nicht den neuen C++-Stand.
- `setup.py` ist bis Dateiende statisch durchgesehen, ohne Modulimport
  oder Installerlauf. Aufgerufene Hilfsmodule und Backend-Setup-Skripte
  bleiben separate Review-Flaechen; keine Gesamtfreigabe daraus.
- Metal-/SYCL-Setup-Skripte sind ebenfalls vollstaendig statisch
  gelesen. Direkte Buildpfade sind minimal nachgeschuetzt; reine
  Wiederverwendung vorhandener Artefakte bleibt erlaubt.
- `tools/image/qimage.py`, dessen Installationswrapper und
  `tools/mtp_fetch.py` sind statisch gelesen. Der eigenstaendige
  MTP-Downloader ist nachgeschuetzt; Modellvorbereitung, Repack und
  weitere transitive Helfer bleiben separate offene Review-Flaechen.
- Offen: weitere Control-/CLI-Module, Engine-Implementierungen und Glue,
  verwendete Backends/Abhaengigkeiten und finale Gates; historische
  Zwischenversionen nur bei konkretem Anlass.
- Apple-/Windows-spezifische Restpruefungen und Backend-Buildnachweise
  sind keine Aufgaben dieser Integration, ausser bei Linux-relevanter
  Ausfuehrung oder gemeinsam verwendeten Abhaengigkeiten. Bereits
  abgeschlossene isolierte Fix-Nachweise bleiben dokumentiert.
- Detaillierte private Belege und laufendes Lesedeckungs-Ledger liegen
  ausschliesslich im lokalen Evidenzarchiv; keine privaten Pfade hier.

## Live-Verifikations-Szenario

Nach geschlossenem statischem Gate und Offline-Build beide Arme auf
isoliertem internem Loopback nach `UPSTREAM_BENCHMARKS.md` pruefen:
Prefill/Content-TTFT, mindestens 128 Decode-Tokens, fuenf eingefrorene
Coding-/Tool-Turns ohne echte Tool-Ausfuehrung. Health und Slots vor/nach
der Folge, Streaming-Abbruch, Auth-Verweigerung und Recovery-Vertrag
gesondert abnehmen. Modell-/Tokenizer-/Profil-Identitaet vorher belegen.

Produktionsrollout ist ein nachgelagerter Schritt, kein Testersatz.
Keine fremden Prozesse beenden; keine ungeprueften Downloads/Installer.

## Defaults und Recherche-Fallbacks

| Situation | Vorgehen |
|---|---|
| Fehlender lokaler Input | Abbruch, keine Fetch-/Installer-Ausweichroute |
| Test-Isolation unvollstaendig | Kein Gate-Pass; konkret fehlende Grenze schliessen |
| Nur finales Tree-Diff sauber | Verwendete Lieferkette, Build-/Startwege und Betriebsnachweise ebenfalls pruefen |
| Angeblicher P1 ohne erreichbare Aufrufkette | Hypothese dokumentieren und diskriminierenden Beleg suchen |
| Bestaetigter Speicherfehler in Opt-in-Pfad | Vor Nutzung korrigieren, nicht wegen aktuellem Profil ignorieren |
| Nicht verfuegbarer Backend-Nachweis | Backend nicht abnehmen; Deployment nur blockieren, wenn dessen Build/Betrieb betroffen ist |
| Langwieriger Architektur-Blocker | Nach drei erfolglosen Versuchen gezielte Tiefenrecherche |
| Unklare/instabile A/B-Reihe | Kein Leistungssignal; Ursachen klaeren, beide Arme neu einfrieren |

## Offene Fragen und Folge-Plan

Keine offene Entscheidung ueber Merge-Strategie oder Workflow-Automatik:
beides hat der Nutzer bereits festgelegt. Offene Nachweise sind in der
Schritttabelle aufgefuehrt und bleiben Teil dieses Plans.

Dieser Plan fuehrt bis zum kontrollierten Rollout; ein neuer Kandidaten-Pin,
eine neue Zielbasis oder geaenderte Payloads brauchen einen expliziten
Planwechsel mit erneuter betroffener Verifikation.


## Nachtrag: bestaetigte P2-Fixe dieser Integration

- **P2 Mac-Plan-Expertenzahl**: Die Anzeige-Rundung auf 0.1 GB wurde vor
  der Expertenzaehlung angewandt. Synthetische Plaene konnten dadurch mehr
  als die vorhandenen 15360 Experten oder zu wenige bei Vollresidenz
  melden. `_plan_mac` zaehlt jetzt aus ungerundetem Budget und behandelt
  Vollresidenz exakt. Drei isolierte Testmethoden bestehen; dieselben
  Tests hatten vorher 16 Subtest-Fehler. Nur Plan-Metadaten, kein
  GPU-/Produktionsnachweis. Gesamt-Gegenpruefung, Lieferkette und A/B
  weiterhin offen.
