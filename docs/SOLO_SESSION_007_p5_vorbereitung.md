# SOLO_SESSION_007 — P5-Vorbereitung: Robert-C++-Frontend-Evaluierung

## Session-Ziel

Ein **Evaluierungs-Dokument** (`docs/P5_ROBERT_FRONTEND_EVAL.md`) liegt vor:
was das UnbiasedStrata-C++-Frontend (`robertkarl/UnbiasedStrata @ b124b59`)
ist, was ein Port auf unsere upstream-nahe Engine kosten würde, welche
Test-Abnahmen die Roadmap fordert, und eine fundierte Go/No-Go-Empfehlung.
**Keine Implementierung** — Freigabe gilt nur für Vorbereitung. Branch:
`feat/p5-eval`.

## Entscheidungen

| Frage | Entscheidung |
|---|---|
| Quelle | `/tmp/unbiased-strata-src` (lokal, Audit-Checkout b124b59) — kein Remote-Fetch nötig; falls gelöscht: bewusster Clone von github.com/robertkarl/UnbiasedStrata (kontrollierte Beschaffung) |
| Grundlage der Bewertung | Audit-Note `AI37SV8cD2P4` "Vertiefung"-Abschnitt + eigener Diff-/Lese-Abgleich |
| Ergebnis-Form | Eval-Doc mit: Frontend-Architektur, Engine-Diff-Umfang, Feature-Matrix vs. unsere Anforderungen (MultiGPU, Swift, Vision, Tools, Langkontext, SSE, Disconnect, /slots), Portierungs-Aufwand, Test-Plan, Empfehlung |
| Empfehlung | Faktenbasiert; "Go" nur wenn Test-Abnahme-Rahmen realistisch planbar |

## Schritte

- [ ] 1. Branch `feat/p5-eval` von `feat/lan-umstellung` (oder main)
- [ ] 2. Frontend-Analyse: `frontend/` (9 Dateien, ~1495 Zeilen) lesen —
       `main.cpp`, `engine_entry.cpp`, Pipe-Protokoll (READY/GEN/GENI/
       STOP/STATS), Tokenizer/Template-Quellen (llama.cpp-Bibs)
- [ ] 3. Engine-Diff quantifizieren: `git -C /tmp/unbiased-strata-src diff
       12a7825..b124b59 -- src/ include/` (Audit sagt: 58 Dateien,
       +5976/−1059) — aufschlüsseln: was davon ist Frontend-Support vs.
       echte Engine-Divergenz (MTP, Prefill, Attention, Geometrie, Runner)
- [ ] 4. Feature-Matrix: pro Roadmap-P5-Testbereich (MultiGPU `--gpus`/
       `--layer-split`, Swift-Profile, Vision CPU-Encoder, Tool-Calls,
       Langkontext, SSE-Streaming, Disconnect-Verhalten, `/slots`-Readiness/
       Drain) — Stand in UnbiasedStrata vs. Bedarf (InferenzQuelle!)
- [ ] 5. Portierungs-Optionen: (a) Frontend-Tree auf unseren Pin portieren,
       (b) nur Pipe-Protokoll + engine_entry-Pattern nachbauen,
       (c) nicht portieren — Python-Server reicht. Aufwand je Option.
- [ ] 6. Test-Plan-Entwurf für den Go-Fall: konkrete Abnahme-Schritte
       pro Feature-Bereich (messbar, wie 006-Abnahme)
- [ ] 7. `docs/P5_ROBERT_FRONTEND_EVAL.md` schreiben + ROADMAP P5 als
       "vorbereitet" markieren (Checkboxen bleiben technisch offen —
       Entscheidung ausstehend, klar vermerkt)
- [ ] 8. Trilium: Kurz-Verweis im Audit-Note-Kontext (Update-Abschnitt in
       `AI37SV8cD2P4` oder neue Unter-Note unter `TaWve7nWU3kF`)
- [ ] 9. Review → Commit → Push

## Verifikations-Strategie

| Schritt | Verifikation |
|---|---|
| 2-3 | Zahlen im Eval-Doc mit `git diff --stat`/Dateilisten belegt, nicht aus dem Audit übernommen ohne Abgleich |
| 4 | Feature-Matrix hat Fundstelle (Datei:Zeile) pro "nicht vorhanden"-Aussage — Audit-Befunde verifiziert, nicht wiederholt |
| 6 | Test-Plan ist mit der Infrastruktur aus 004/006 ausführbar gedacht (echte Slots, echte Inferenz) |

## Live-Verifikations-Szenario

N/A — Evaluierungs-Dokument, keine Code-Änderung. (Explizit KEINE
Implementierung/kein Build des Frontends — P5 ist freigabegebunden.)

## Defaults

- `/tmp/unbiased-strata-src` gelöscht → kontrollierter Clone des Repos an
  dokumentierter Stelle außerhalb des Fork-Repos (nicht als Remote!)
- Eval-Empfehlung bei Unsicherheit → "Go nur nach X-Klärungs-Test" statt
  pauschalem Nein; Entscheidung bleibt fukuros
- Audit-Aussagen, die sich nicht verifizieren lassen → als Diskrepanz
  markiert (ehrlicher Befund)

## Recherche-Strategien

| Problemtyp | Strategie |
|---|---|
| Frontend-Code-Details | read frontend/*, git log/diff im lokalen Checkout |
| UPSTREAM.md-Abweichung | Diff gegen `12a7825`-Importsnapshot selbst rechnen |
| InferenzQuelle-Anforderungen | Audit-Note + ggf. InferenzQuelle-Repo auf hydra (`router/admission.py`, `shared/llm_client.py` Fundstellen) |

## Recherche-Fallbacks

| Block | Problem | Fallback |
|---|---|---|
| Checkout | /tmp-Quelle weg | Clone nach /tmp; dokumentieren |
| Diff-Basis | `12a7825` im flachen Checkout nicht erreichbar | Diff gegen Fork-Pin `296b59d2` als Ersatz-Basis + Einschränkung dokumentieren (Audit nannte Merge-Basis nicht nachgewiesen) |
| Aufwand-Schätzung | Zu viele Unbekannte | Schätzung als Bereich mit Annahmen-Liste — keine Zahl ohne Annahme |

## Offene Fragen

- Ob Robert-Upstream selbst weiter gepflegt wird (für Sync-Relevanz der
  Frontend-Quelle — im Bericht vermerken falls Commit-Datum ersichtlich)

## Folge-Plan

→ **Kettenende.** Nach dieser Session: Abschlussbericht via
`solo-session-bericht` + TTT-Eintrag + nächste Schritte-Empfehlung
(P5-Entscheidung offen bei fukuro).
