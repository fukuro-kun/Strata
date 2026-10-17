# SOLO_SESSION_001 — P0: Inventar und Baseline-Freeze

## Session-Ziel

`docs/INVENTAR.md` steht: vollständiges schriftliches Inventar (Quellen,
Abhängigkeiten, Lizenzen, Toolchain, Modell-Provenienz mit Herkunft+Hashes)
sowie die verifizierte, dokumentierte Baseline-SHA. ROADMAP P0-Checkboxen
alle abgehakt. Branch: `feat/p0-inventar`.

## Entscheidungen

| Frage | Entscheidung |
|---|---|
| Ablage | `docs/INVENTAR.md` committed + Trilium-Verweis-Note unter `TaWve7nWU3kF` |
| Pin | `296b59d2f73c8f04a805df29c2fa97655adace78` nach Verifikation (Diff vs. `/tmp/strata-src` @ gleichem SHA + Stichproben-Review der Audit-Fundstellen) |
| Modell-Artefakte | Suche auf hydra/ganymed/uranus/eris; Funde → sha256 |
| Toolchain | Live-Erhebung auf denselben 4 Hosts via SSH |
| Branch/Push | `feat/p0-inventar`, Push nach Selbst-Review (Doku-only) |

## Schritte

- [x] 1. Branch `feat/p0-inventar` (von `feat/offline-roadmap`, enthält Doku-Commit `3f85e883`)
- [x] 2. SHA-Verifikation: Tree-Diff vs. `/tmp/strata-src` **identisch**
       (nur Fork-Dateien abweichend); Stichproben `setup.py` HF-Revisions,
       `LLAMA_CPP_COMMIT=3cf03257…`, FetchContent-Pfad bestätigt
- [x] 3. Host-Erhebung: alle 4 Hosts erreicht + vollständig inventarisiert
       (hydra lokal; ganymed/uranus/eris via SSH) → `LOKAL.md` Detailtabelle
- [x] 4. Modell-Artefakt-Suche: alle Fundorte kartiert (ganymed-Archiv 586G,
       uranus raid5+strata-active, eris hf-swift+strata-active, packs).
       Frische SHA256-Läufe auf eris+uranus gestartet (Hintergrund); SC117/
       Coder bereits durch HF-verifizierte Belege abgedeckt
- [x] 5. Trilium-Kontext: alle sieben Notes gelesen; bestätigen Produktiv-
       Topologie (Profil R aktiv uranus, Profil Q Rollback, eris B12 manuell)
- [x] 6. `docs/INVENTAR.md` geschrieben — **committed-fähig**: Hostnamen/Pfade
       abstrahiert (Repo-Regel „keine Host-Details in Commits"), volle Details
       in `LOKAL.md`
- [x] 7. AGENTS.md Doku-Tabelle erweitert; ROADMAP P0 als ERLEDIGT markiert,
       Status-Absatz auf verifizierte Pin-Doku umgeschrieben
- [x] 8. Trilium-Verweis-Note `dfPCN7ricKlc` unter `TaWve7nWU3kF` angelegt
- [ ] 9. Review → Commit → Push `feat/p0-inventar`

## Verifikations-Strategie

| Schritt | Verifikation |
|---|---|
| 2 | `diff -r`/`git diff --stat` zeigt identischen Baum; Fundstellen-Stichprobe bestätigt Audit-Befunde |
| 3-4 | SSH-Befehle protokolliert; jeder Host liefert Tabelle oder dokumentierten Grund (nicht erreichbar = Blocker-Eintrag, kein Überspringen) |
| 6 | INVENTAR.md enthält je Quelle Herkunft+Hash; Akzeptanzkriterium ROADMAP P0 wörtlich erfüllt |

## Live-Verifikations-Szenario

N/A — reine Inventar-/Doku-Arbeit ohne Code-Änderung. Verifikation =
Akzeptanzkriterium P0 (schriftliches Inventar + dokumentierter Pin).

## Defaults

- Host nicht erreichbar → dokumentieren + weiter (Hardware-Blocker ist legitim)
- GPU auf Host vorhanden aber Toolchain fehlt → als P1-Bedarf ins Inventar
- Modell-Datei >10 GB → sha256 trotzdem vollständig (einmalig, nötig für Manifest)
- Uneindeutige Lizenz (kein Header) → "Root-MIT erbrecht" + Fundstelle

## Recherche-Strategien

| Problemtyp | Strategie |
|---|---|
| Host-Details | SSH + Trilium-Host-Notes |
| Unklare Code-Fundstelle | grep + read, im Repo |
| HF-Repo-Details | `setup.py`-Pins extrahieren (kein Web-Abruf nötig) |

## Recherche-Fallbacks

| Block | Problem | Fallback |
|---|---|---|
| SSH | Host down/auth fail | Dokumentieren, nächster Host; kein User-Blocker |
| Trilium | Token/Netzwerk-Fehler | LOKAL.md-Notiz, Inventar trotzdem schreiben |
| Hashing | >100 GB Artefakte | Priorität: Modell+Packs+mmproj+MTP; Bench-Archive nur als Pfadliste |

## Offene Fragen

- Ob ganymed/uranus/eris systemd-User oder root-Units nutzen (klärt sich
  bei Erhebung; für P3 relevant, nicht P0-blockierend)

## Folge-Plan

→ `SOLO_SESSION_002_p1_offline_build.md`
