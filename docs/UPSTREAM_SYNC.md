# UPSTREAM_SYNC — die Sync-Disziplin des Forks (P4)

Der Fork bleibt nah an upstream (`Niko1221/Strata`), aber es gibt **keinen**
Auto-Pull, keinen Cron, keinen stillen Merge. Jede Synchronisation ist ein
bewusster, dokumentierter Vorgang.

## Remotes

- `origin` = `git@github.com:fukuro-kun/Strata.git` (unser Fork, pushfähig)
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

## Was niemals passiert

- `git pull upstream` / Merge ohne Review-Bericht
- `update.sh`-Artige Selbst-Updates
- Push nach `upstream`
- Upstream-Fetch in Deployment-/Start-Pfaden
- Ein Pin-Wechsel (`LLAMA_CPP_COMMIT`, HF-Revisions, Wheel-Pins) ohne
  eigenen Berichtsabschnitt und neuen Provenienz-Beleg

## Erstanwendung

`docs/upstream-reviews/REVIEW_2026-10-17_296b59d2.md` — erster Fetch:
upstream/main identisch mit der P0-Baseline (`296b59d2`), kein Drift.
