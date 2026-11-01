# UPSTREAM_SYNC — die Sync-Disziplin des Forks (P4)

Der Fork bleibt nah an upstream (`Niko1221/Strata`), aber es gibt **keinen**
Auto-Pull, keinen Cron, keinen stillen Merge. Jede Synchronisation ist ein
bewusster, dokumentierter Vorgang.

## Ziel und täglicher Einstieg

Primär schützen wir unseren LAN-Betrieb: möglichst upstream-nahe, leistungsfähige
Software aus nachvollziehbaren lokalen Source-Builds, keine ungeprüften Binaries
oder nachgeladenen Codebestandteile, gepinnte Inputs und sichere Offline-Pfade.
Die Veröffentlichung über den Mirror ist nachrangig; das bestehende Push-Gate
bleibt trotzdem verbindlich und ersetzt keine LAN-Sicherheitsprüfung.

Der repo-lokale Skill `.devin/skills/strata-upstream/SKILL.md` setzt diesen
Prozess um. Aufruf im Agenten: `/strata-upstream daily`. Dieser Aufruf prüft
neue Änderungen, dokumentiert Kandidaten und führt den offenen Review-Bestand
weiter. Er ändert keinen Engine-/Server-Code und startet keine Tests.
Ein RADAR-Bericht ist keine Freigabe.

`/strata-upstream integrate <bericht> <vollständige-commit-shas>` bereitet
ausdrücklich ausgewählte Kandidaten in einem separaten lokalen Test-Worktree
vor. Vor Übernahme in die freigegebene Fork-Linie gelten Sicherheitsreview,
Regressionstests und die drei standardisierten A/B-Tests aus
[UPSTREAM_BENCHMARKS.md](UPSTREAM_BENCHMARKS.md): Prefill/TTFT, Decode und
API-/Mehrturn-Betrieb. Beide Arme werden lokal aus Quellen gebaut. Ein
Testkandidat ist noch keine Promotion oder Deployment-Freigabe.
Für reine Sicherheits-/Korrektheits-/Kompatibilitätsfixes ohne Speed-Gewinn
ist eine gesondert begründete Freigabe möglich, kein erfundener Leistungsbeleg.

Täglich beobachten heißt nicht täglich mergen. Ungeprüfter Rückstand bleibt
sichtbar, auch bei Tagesdelta 0. Kleine zusammenhängende Upstream-Änderungen
werden bevorzugt unverändert übernommen; größere Pakete benötigen entsprechend
vollständige Prüfung, keine pauschale Versionsfreigabe.

Der Skill ist angelegt, **kein Scheduler aktiviert**. Ein zeitgesteuerter
Beobachtungslauf benötigt eine separate Freigabe für Host, Zeit/Zeitzone,
Netzwerkzugriff, Lauf-Sperre, Agentenrechte und Ergebniszustellung. Bis dahin
bleibt jeder Fetch bewusst einzeln angestoßen. Auch eine spätere Zeitplan-
Freigabe autorisiert keinen Merge, Push oder Produktiv-Rollout.

## Pruefumfang (Nutzerentscheidung 2026-11-01)

Ziel ist ein zuverlaessiges, moeglichst leistungsfaehiges und modernes
Produktivsystem aus vertrauenswuerdigen, geprueften Komponenten.
Die volle Git-Historie bleibt erhalten. Eine Volltextpruefung jeder
historischen Dateiversion ist kein Freigabe-Gate.

Geprueft werden der konkrete auszuliefernde Stand, die relevanten
Aenderungen zur freigegebenen Basis, unsere Fork-Anpassungen sowie die
tatsaechlich verwendeten Komponenten, Build-, Installations- und
Startwege. Ausfuehrbare Agentenregeln und automatische Workflows bleiben
Teil der Vertrauensgrenze. Herkunft, Pins und Artefakte muessen
nachvollziehbar sein. Historische Zwischenstaende werden nur bei einem
konkreten Verdacht oder zur Fehler- und Herkunftsklaerung untersucht.

Nicht eingesetzte Plattformen/Funktionen werden ausdruecklich als nicht
abgenommen ausgewiesen; sie sind kein pauschales Hindernis fuer ein
klar abgegrenztes Deployment, sofern sie dessen Build/Start/Betrieb
nicht beeinflussen. Geteilte Komponenten und erreichbare Nebenpfade
bleiben im Pruefumfang. Bekannte Fehler werden nicht still uebergangen.

Apple/macOS und Windows sind keine Zielplattformen dieses Fork-Betriebs
(Nutzerentscheidung 2026-11-01). Keine Builds, Funktionsabnahmen oder
umfangreichen Laufzeittests fuer diese Plattformen. Rein dort genutzter
Code wird nur insoweit geprueft, wie er unter Linux ausgefuehrt,
importiert, in Builds eingebunden oder durch Werkzeuge geladen werden
koennte. Geteilte Linux-relevante Komponenten bleiben im Scope.

Ein reduzierter Arbeitscheckout ist einer dauerhaften Loeschung aus dem
Fork vorzuziehen, sofern Linux-Build, Start und Provenienz erhalten
bleiben. Sparse Checkout entfernt keine historischen Git-Objekte.
Den laufenden, geaenderten Integrationscheckout nicht dafuer umbauen;
Ausschlussmuster erst an einem separaten sauberen Checkout festlegen.

Die Betriebsfreigabe braucht passende Regressionstests, unabhaengige
Gegenpruefung, Offline-Build-/Provenienzbelege, den vorgesehenen
Leistungsvergleich und Live-Abnahme mit Rollback. Ein gruener Unit-Test
oder blosse Upstream-Herkunft ersetzt diese Nachweise nicht. Das
Push-Gate bezieht sich auf diesen dokumentierten Pruefumfang; es
fordert keinen pauschalen Clean-Verdict fuer die gesamte Git-Historie.

## Remotes

- `origin` = `git@europa:fukuro/Strata.git` (unser Fork auf dem LAN-Forgejo,
  pushfähig; ein serverseitiger Push-Mirror auf europa spiegelt jeden Push
  nach `github` = `git@github.com:fukuro-kun/Strata.git` — reiner Mirror,
  nichts direkt pushen)
- `upstream` = `https://github.com/Niko1221/Strata.git` (read-only Referenz;
  Push-URL ist `PUSH_DISABLED` — **nie ändern**)

## Prozess

1. **Bewusster Fetch** — nie automatisch:
   `git fetch upstream` auf Anlass (Release-Note, bekannter Fix, geplanter
   Sync), nicht auf Timer. Vorher/Nachher-HEAD von `upstream/main` notieren.
2. **Integrations-Branch** — der Review läuft auf
   `feat/sync-<YYYY-MM-DD>-<kurz-id>` (Datum + Kandidaten-Kurz-ID), niemals
   direkt auf `main`. (`upstream-review` war der historische Name des
   ersten Integrations-Branches — kein aktuelles Namensmuster.)
3. **Diff-Review** — `git log` + `git diff <baseline>..upstream/main`;
   jede geänderte Datei wird kategorisiert: engine (`src/`, `include/`),
   server (`serve/`), build (`CMakeLists.txt`, `cmake/`, `setup.py`,
   `requirements.txt`), **Agenten-Anweisungen** (`AGENTS.md`,
   `docs/AI_SETUP.md`, `.github/`), Modell-Pins (`setup.py`-Tabellen).
   Alle Pfade im Bericht einordnen; pruefpflichtige Betriebs-/Build-Pfade
   und nicht eingesetzte, nicht abgenommene Bereiche unterscheiden.
4. **Review-Bericht** — `docs/upstream-reviews/REVIEW_<datum>_<sha>.md`:
   Kategorien, Risiko-Einschätzung, Promotions-Empfehlung. Der Bericht ist
   die Freigabe-Eingangstüre, kein Merge-Automatismus.
5. **Tests vor Promotion** — `tools/test_setup_*.py` (GPU-frei) laufen
   nach statischer Prüfung des ausführbaren Test-/Build-Codes in einer
   isolierten Umgebung ohne Secrets und ohne LAN-/Internetzugriff gegen den reviewed
   Stand auf dem Integrations-Branch. Vor einer Code-Übernahme zusätzlich
   A/B-Leistungsnachweis nach `docs/UPSTREAM_BENCHMARKS.md`; fehlende
   Messungen sind ein offenes Gate. Bei späteren
   Builds gilt zusätzlich: `tools/offline/build_engine.sh` muss den
   neuen Stand bauen (ggml-Pin-Wechsel → `fetch_llamacpp.sh` zuerst).
6. **Promotion** — Merge nach `main` nur nach Review + Tests, als
   dokumentierter Schritt. Ein `llama.cpp`-Pin-Wechsel ist nie "nur ein
   Detail": der Pin ist Engine-Input und wandert ins P3-Manifest.

## Push-Gate: upstream-Code wird erst nach Review öffentlich

**CI-Begrenzung:** Alle mit dem Upstream-Stand eingehenden GitHub-Workflows (`.github/workflows/*.yml`) sind upstream-Referenz und tragen je Job den Fork-Guard `if: github.repository == 'Niko1221/Strata'` — auf europa und dem GitHub-Mirror (anderer Repositoryname) skippen sämtliche Jobs. Zusätzlich ist `on:` überall auf **nur `workflow_dispatch`** reduziert (User-Entscheid: keine automatischen Abläufe — kein Push-/PR-/Cron-Trigger, keine PR-Bots); die Dateien bleiben als manuelle Upstream-Referenz erhalten. Jede künftige Workflow-Übernahme muss denselben Endzustand zeigen. Regressionstest: `tools/test_fork_workflows.py`.

Der Push-Mirror auf europa spiegelt **jeden** Push sofort nach GitHub —
ein unreviewter Upstream-Stand wäre damit sofort öffentlich und später
aus öffentlichen Refs nicht mehr sauber zu tilgen. Deshalb gilt:

- Code aus `upstream` (Fetch- oder Merge-Stand) wird **niemals auf einen
  `origin`-Branch gepusht, solange er unreviewed ist** — auch nicht „nur
  zur Sicherung" auf `wip/*` oder `feat/sync-*`. Der Integrations-Branch
  bleibt bis zum Clean-Verdict **lokal**.
- Review (Schritte 3–4) läuft lokal; erst nach dokumentiertem
  **Clean-Verdict** im Review-Bericht darf der Stand über den
  Promotion-Merge auf `main`/`feat/*` gepusht werden.
- **Mindestkriterien des Clean-Verdicts** (im Bericht ausdrücklich
  bestätigt, nicht implizit):
  - vollstaendig eingeordneter Zieldiff und gepruefte Lieferkette im
    dokumentierten Betriebsumfang; keine ungeprueften ausfuehrbaren
    Abhaengigkeiten in Build, Start oder Betrieb
  - keine Secrets/Tokens/Keys im Diff (auch keine kommentierten oder
    in Tests eingebetteten)
  - keine neuen Download-/Phone-home-/Auto-Update-Pfade: `FetchContent`,
    `setup.py`-Installer-Logik, `.github/workflows`, `docs/AI_SETUP.md`,
    Starters (`setup.sh`, `START-HERE.bat`)
  - geänderte Agenten-Anweisungen (`AGENTS.md`, `CLAUDE.md`, `.cursor/`,
    `.devin/`, sonstige AI-Anleitungen) gesondert geprüft — sie steuern
    künftige Agenten-Läufe und sind klassischer Injektionsvektor
  - Pin-Änderungen (`LLAMA_CPP_COMMIT`, HF-Revisions, Wheel-Pins) nur mit
    eigenem Berichtsabschnitt + Provenienz-Beleg
- Fällt das Clean-Verdict negativ aus: nicht promovieren, lokal quarantiniert
  belassen, Befund im Review-Bericht festhalten, **kein Push**.
  Keine automatischen Resets oder Löschungen. Teilübernahme nur
  als bewusster Cherry-Pick einzelner reviewed Commits — nie als Merge
  des Gesamtstands.

## Was niemals passiert

- `git pull upstream` / Merge ohne Review-Bericht
- Push eines unreviewten Upstream-Stands auf **irgendeinen**
  `origin`-Branch — der Server-Mirror macht ihn sofort öffentlich
- `update.sh`-Artige Selbst-Updates
- Push nach `upstream`
- Upstream-Fetch in Deployment-/Start-Pfaden
- Ein Pin-Wechsel (`LLAMA_CPP_COMMIT`, HF-Revisions, Wheel-Pins) ohne
  eigenen Berichtsabschnitt und neuen Provenienz-Beleg

## Erstanwendung

`docs/upstream-reviews/REVIEW_2026-10-17_296b59d2.md` — erster Fetch:
upstream/main identisch mit der P0-Baseline (`296b59d2`), kein Drift.
