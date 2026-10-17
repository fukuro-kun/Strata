# SOLO_SESSION_005 — P4: Upstream-Sync-Disziplin

## Session-Ziel

Die Upstream-Sync-Disziplin ist **etabliert und einmal angewendet**:
bewusster Fetch auf eigenem Integrations-Branch, dokumentiertes Diff-Review
aller relevanten Bereiche, Testlauf, kein Auto-Pull. Ergebnis:
`docs/UPSTREAM_SYNC.md` (Prozess) + erster Review-Bericht. Branch:
`feat/p4-upstream-sync`.

## Entscheidungen

| Frage | Entscheidung |
|---|---|
| Integrations-Branch | `upstream-review` (vom aktuellen `main`-Pin abzweigend); upstream-Fetch landet als `upstream/main`-Tracking-Ref, nie direkt in `main` |
| Erstanwendung | Einmaliger bewusster `git fetch upstream` — Begründung: jetzt ist der bewusste Zeitpunkt (Baseline-Abgleich), dokumentiert als erste Anwendung der Disziplin |
| Review-Umfang | `src/`, `include/`, `serve/`, `tools/`, `cmake/`, `CMakeLists.txt`, `requirements.txt`, `setup.py`, **Agenten-Anweisungen** (`AGENTS.md`, `docs/AI_SETUP.md`, `.github/`), plus alles Neue im Diff |
| Promotion | Merge nach `main` NUR nach Review-Bericht + Tests; diese Session erzeugt Review + Empfehlung, kein Blind-Merge |
| Kein Auto-Pull | `update.sh` bleibt aus unseren Pfaden entfernt; cron/systemd-Timer für Sync wird nicht eingerichtet |

## Schritte

- [x] 1. Branch `feat/p4-upstream-sync` von `feat/p3-manifeste`
- [x] 2. `git fetch upstream` — **Ergebnis: no drift**;
       `upstream/main` = `296b59d2…` = P0-Baseline = Tag `v0.1.44.1`
       (HEAD-Merge vom 2026-10-14). Wir sitzen auf dem neuesten
       Upstream-Stand; Tags vollständig gefetcht
- [x] 3. Diff-Review `296b59d2..upstream/main`: `git log` → **0 Commits**,
       nichts zu kategorisieren — Bericht dokumentiert das pro Bereich
- [x] 4. Review-Bericht: `docs/upstream-reviews/REVIEW_2026-10-17_296b59d2.md`
       (no-drift, Prozess-Nachweis, Verifikations-Kommandos)
- [x] 5. `docs/UPSTREAM_SYNC.md`: Prozess Fetch → Integrations-Branch →
       Kategorien-Review → Tests → Promotion; Verbote (kein Auto-Pull,
       kein upstream-Push, kein Pin-Wechsel ohne Bericht)
- [x] 6. Tests: n/a — keine Divergenz zu mergen (Integrations-Branch-
       Lauf entfällt bei 0 Commits; beim ersten realen Sync Pflicht)
- [x] 7. ROADMAP P4 abgehakt
- [x] 8. Review → Commit → Push

## Verifikations-Strategie

| Schritt | Verifikation |
|---|---|
| 2 | `git log --oneline 296b59d2..upstream/main` zeigt überschaubare, aufgelistete Commits |
| 3 | Jede geänderte Datei im Diff ist im Bericht kategorisiert (kein ungeprüfter Rest) |
| 6 | `python tools/test_setup_<name>.py` (GPU-frei laut AGENTS.md) grün auf Integrations-Branch |

## Live-Verifikations-Szenario

N/A — Disziplin + Review, keine Code-Änderung im eigentlichen Sinn.
Verifikation = Review-Bericht deckt 100 % des Diffs ab + Testlauf.

## Defaults

- Upstream hat sich seit 296b59d2 nicht bewegt → Bericht dokumentiert
  "no drift", Prozess trotzdem etabliert
- Bewegter Upstream mit großen Diffs → Kategorisierung + Empfehlung,
  kein Merge in dieser Session bei P1-Änderungen ohne User-Sichtung der
  Liste (Bericht bleibt Freigabe-Eingang)
- `upstream`-Push bleibt `PUSH_DISABLED` — nie ändern

## Recherche-Strategien

| Problemtyp | Strategie |
|---|---|
| Großer Diff | Subagent gruppiert Dateien; Main-Agent reviewt sicherheitsrelevante (setup.py, CMake, serve/auth) |
| Commit-Kontext | `git log --format=full` + GitHub-PR-Nummern aus Commit-Messages |

## Recherche-Fallbacks

| Block | Problem | Fallback |
|---|---|---|
| Fetch | Netz/Auth-Fehler | Prozess-Doku trotzdem schreiben; Fetch als "ausstehend" markieren |
| Diff | Umfang >500 Dateien | Kategorien-Ebene reviewen + Top-Risiko-Dateien einzeln; Rest als "Massen-Diff, Liste im Bericht" |
| Tests | setup-Tests brauchen GPU | AGENTS.md sagt GPU-frei — bei Fehlschlag Fehler dokumentieren, nicht fixen am upstream-Code |

## Offene Fragen

- Forgejo-Mirror-Rolle bleibt zurückgestellt (Roadmap-Nicht-Ziel jetzt);
  Bericht vermerkt es als ausstehende Entscheidung

## Folge-Plan

→ `SOLO_SESSION_006_lan_umstellung.md`
