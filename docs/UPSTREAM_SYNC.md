# UPSTREAM_SYNC — die Sync-Disziplin des Forks (P4)

Der Fork bleibt nah an upstream (`Niko1221/Strata`), aber es gibt **keinen**
Auto-Pull, keinen Cron, keinen stillen Merge. Jede Synchronisation ist ein
bewusster, dokumentierter Vorgang.

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
2. **Integrations-Branch** — der Review läuft auf `upstream-review` (oder
   `feat/sync-<datum>`), niemals direkt auf `main`.
3. **Diff-Review** — `git log` + `git diff <baseline>..upstream/main`;
   jede geänderte Datei wird kategorisiert: engine (`src/`, `include/`),
   server (`serve/`), build (`CMakeLists.txt`, `cmake/`, `setup.py`,
   `requirements.txt`), **Agenten-Anweisungen** (`AGENTS.md`,
   `docs/AI_SETUP.md`, `.github/`), Modell-Pins (`setup.py`-Tabellen).
   Kein ungeprüfter Rest im Bericht.
4. **Review-Bericht** — `docs/upstream-reviews/REVIEW_<datum>_<sha>.md`:
   Kategorien, Risiko-Einschätzung, Promotions-Empfehlung. Der Bericht ist
   die Freigabe-Eingangstüre, kein Merge-Automatismus.
5. **Tests vor Promotion** — `tools/test_setup_*.py` (GPU-frei) laufen
   gegen den reviewed Stand auf dem Integrations-Branch. Bei späteren
   Builds gilt zusätzlich: `tools/offline/build_engine.sh` muss den
   neuen Stand bauen (ggml-Pin-Wechsel → `fetch_llamacpp.sh` zuerst).
6. **Promotion** — Merge nach `main` nur nach Review + Tests, als
   dokumentierter Schritt. Ein `llama.cpp`-Pin-Wechsel ist nie "nur ein
   Detail": der Pin ist Engine-Input und wandert ins P3-Manifest.

## Push-Gate: upstream-Code wird erst nach Review öffentlich

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
  - vollständiger Diff — keine unreviewten Dateien, kein Rest unter
    „sonstiges"
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
- Fällt das Clean-Verdict negativ aus: Stand verwerfen (`git reset`),
  Befund im Review-Bericht festhalten, **kein Push**. Teilübernahme nur
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
