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

- [ ] 1. Branch `feat/p0-inventar` von `main` (= `296b59d2`)
- [ ] 2. SHA-Verifikation: `git diff` Repo-Checkout vs. `/tmp/strata-src`
       (identisch erwartet, Doku-Commit `da00a7e0` ausgenommen — der liegt
       nur auf feat/offline-roadmap, nicht main); Stichproben-Review
       `setup.py:3261-3378`, `:1967-2005`, `CMakeLists.txt:1300-1320`
- [ ] 3. Host-Erhebung (SSH): ganymed, uranus, eris — GPU/VRAM, Treiber,
       CUDA/ROCm, gcc/clang, cmake, python3, RAM, Disk; hydra lokal
- [ ] 4. Modell-Artefakt-Suche auf denselben Hosts: `*.gguf`, `packs/`,
       `mmproj*`, MTP, `native_experts*`, `draft_vocab*`, Strata-Datenverz.
       → Funde mit sha256 (gguf-shards ggf. gestreamt hashen)
- [ ] 5. Trilium-Kontext: `yWi63z5N6vXc` (Modellpfade), `s60i74CjMyxH`
       (GPU-Profile), `gpw3xvFxRc8q` (Betrieb), `NhvWTRYMEvjy` (ERIS),
       `5Ec9sW4aCN6S` (Uranus A/B), `bf6qS9vQRJXl`, `Lpouldo4Bw77`
- [ ] 6. `docs/INVENTAR.md` schreiben: Quell-Tree, Deps, Lizenzen,
       Toolchain (4 Hosts), Modell-Provenienz (Repo-Rev + SHA256-Tabellen
       aus setup.py extrahiert), Netzwerk-Endpunkte, Offline-Lücken,
       Pin-Eintrag
- [ ] 7. AGENTS.md Doku-Tabelle: INVENTAR.md + SOLO_SESSION_* eintragen;
       ROADMAP P0-Checkboxen abhaken
- [ ] 8. Trilium-Verweis-Note unter `TaWve7nWU3kF` ("Inventar & Baseline-Pin
       → docs/INVENTAR.md", kurze Verweis-Note, kein Content-Duplikat)
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
