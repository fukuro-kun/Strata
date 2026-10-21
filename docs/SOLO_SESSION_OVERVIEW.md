# SOLO_SESSION_OVERVIEW — Offline-Fork-Umsetzung (P0–P5)

Aggregations-Index für die Solo-Session-Pläne zur Umsetzung der
[ROADMAP.md](../ROADMAP.md) Phasen P0–P4 (vollständig) plus LAN-Umstellung
und P5-Vorbereitung.

**Freigabe:** 2026-10-17 durch fukuro (Entscheidungs-Interview). Umfang:
P0–P4 vollständig autonom; danach LAN-Strata-Deployments auf diesen Fork
umstellen (mit Rollback); P5 vorbereitend evaluieren. Deploy-Dokus und
Trilium-Notes werden auf die Fork-Regel festgelegt.

## Interview-Protokoll (Entscheidungen)

| Frage | Entscheidung | Begründung |
|---|---|---|
| Inventar-Ablage | `docs/INVENTAR.md` committed + Trilium-Verweis | Versioniert, reviewbar, P3-Manifeste referenzierbar |
| SHA-Pin | Agent verifiziert (Diff vs. `/tmp/strata-src`-Audit-Checkout + Stichproben) und pinnt `296b59d2` dokumentiert | Audit-Bezug existiert bereits (Trilium `AI37SV8cD2P4`, 2026-10-17) |
| Modell-Artefakte | Agent sucht selbst auf hydra/ganymed/uranus/eris; Vorhandenes wird gehasht | Bestand unbekannt, Multi-Host-Suche |
| Toolchain-Scope | hydra + ganymed + uranus + eris | LAN-Flotte ist Build-/Deployment-Ziel |
| Commit-Kadenz | Pro Phase `feat/`-Branch, fortlaufend committen, Push nach Code-Review | Git-Regeln: Feature-Push = Normalfall, Crash-Sicherheit |
| Deployment-Umstellung | Umstellen sobald P3-Mechanik steht, alter Stand bleibt Rollback | Explizite Freigabe, Dienst-Restart akzeptiert |
| Session-Typ | Solo-Session (diese Pläne ersetzen interaktive Arbeit) | User-Request |

## Kontext-Anker (für alle Sessions)

- **Audit-Note:** Trilium `AI37SV8cD2P4` (Sicherheitsaudit 2026-10-17,
  beide Stände geprüft). Projekt-Hauptnote: `TaWve7nWU3kF`.
- **Audit-Checkouts:** `/tmp/strata-src` = Upstream @ `296b59d2`;
  `/tmp/unbiased-strata-src` = `robertkarl/UnbiasedStrata` @ `b124b59`
  ("Robert"-Frontend, Basis Strata `6f32ec0`/0.1.39, kein Multi-GPU, keine
  `/slots`-Endpunkte).
- **Kritische Offline-Stellen:** `CMakeLists.txt:1306` FetchContent
  llama.cpp (Default wenn `STRATA_GGML_DIR` leer); `setup.py` Prebuilt-
  Engine mit weichem Digest-Fallback; llama.cpp-Zip ohne Hash;
  pip/winget/apt in Startern. Modell-Pins gut: HF-Repo-Revisions +
  SHA256-Tabellen (Unsloth/NVFP4/Qwen3.6/MTP); GSQ-RCO/Swift/Coder nur
  Repo-Revision (Lücke dokumentieren).
- **InferenzQuelle-Abhängigkeit:** `router/admission.py` fordert echte
  `/slots`-Readiness/Drain — Deployment-Umstellung muss diesen Vertrag
  erhalten.
- **hydra:** RTX 3070 Laptop (8 GB, sm_86, Treiber 595.91.07) — Build-
  Host, kein Inferenz-Ziel.
- **Bekannte Deployment-Hinweise:** Trilium `NhvWTRYMEvjy` (ERIS-STRATA),
  `5Ec9sW4aCN6S` (A/B-Testplan Uranus), `yWi63z5N6vXc` (Modellpfade),
  `s60i74CjMyxH` (GPU-Profile), `gpw3xvFxRc8q` (Betrieb/Kalibrierung).

## Wellen-Übersicht

Strikt sequenziell (Abhängigkeitskette), eine Session pro Welle:

| Welle | Session-Plan | Phase | Items |
|---|---|---|---|
| 1 | `SOLO_SESSION_001_p0_inventar.md` | P0 Inventar + Pin | 8 |
| 2 | `SOLO_SESSION_002_p1_offline_build.md` | P1 Offline-Build | 5 |
| 3 | `SOLO_SESSION_003_p2_python_deps.md` | P2 Python-Deps lokal | 5 |
| 4 | `SOLO_SESSION_004_p3_manifeste.md` | P3 Manifeste + Deployment-Mechanik | 5 |
| 5 | `SOLO_SESSION_005_p4_upstream_sync.md` | P4 Sync-Disziplin | 5 |
| 6 | `SOLO_SESSION_006_lan_umstellung.md` | LAN-Deployments umstellen | 4 |
| 7 | `SOLO_SESSION_007_p5_vorbereitung.md` | P5 Evaluierung Robert-Frontend | 4 |

## Abhängigkeits-Graph

```
001 (P0) ──► 002 (P1) ──► 003 (P2) ──► 004 (P3) ──► 006 (LAN)
   │              │                                    ▲
   │              └────────► 005 (P4) ────────────────┘
   │                                                   │
   └──────────────────► 007 (P5-Vorbereitung) ──────────┘ (Ende)
```

- 002 braucht 001 (Toolchain-Fakten, llama.cpp-Pin, Quell-Inventar)
- 003 braucht 002 (Build-Pfad existiert; Wheel-Bedarfe aus dem Build bekannt)
- 004 braucht 002+003 (Manifest erfasst Build- und Dep-Artefakte)
- 006 braucht 004 (Deployment-Mechanik) und fukuros Vorgabe "nach P4" → läuft nach 005
- 005 ist technisch unabhängig von 002–004, bleibt aber in Roadmap-Reihenfolge
- 007 ist Dokumentations-Evaluierung, unabhängig, zuletzt (Priorität nach Produktivnutzen)

## Item-Abdeckung (Vollständigkeits-Check)

ROADMAP-Checkboxen: P0=6, P1=4, P2=5, P3=5, P4=4, P5=4 → 28.
Zusatz-Items des Users: LAN-Discovery, Umstellung, Doku-Reglementierung,
P5-Vorbereitung → +4. **Gesamt: 32 Items.**

| Session | Abgedeckte Items |
|---|---|
| 001 | P0: alle 6 Checkboxen + Host-/Modell-Discovery (Zusatz) + Doku-Tabelle = 8 |
| 002 | P1: alle 4 + Build-Skripte/Nahtstellen-Doku = 5 |
| 003 | P2: alle 5 = 5 |
| 004 | P3: alle 5 = 5 |
| 005 | P4: alle 4 + Erstanwendung (kontrollierter Fetch + Diff-Review) = 5 |
| 006 | Zusatz: Discovery-Abschluss, Umstellung, Rollback-Verifikation, Doku/Trilium-Reglementierung = 4 |
| 007 | P5: Eval-Dokument zu allen 4 Checkboxen (keine Implementierung — Freigabe explizit nur Vorbereitung) = 4 |

**Summe: 36 Zeilen-Abdeckung für 32 Items** (P0/P1-Teilschritte aufgeteilt,
P5-Items nur evaluiert — Umsetzung bleibt freigabegebunden). Kein Item
ohne Platz in der Kette.

## Ausführung

- Start: Session 001 sofort (Solo-Modus, User abwesend).
- Reihenfolge verbindlich: 001 → 002 → 003 → 004 → 005 → 006 → 007.
- Jede Session endet mit: Plan-Update, Commit (Code-Review vor Push),
  nahtlosem Übergang zur nächsten Session (Auto-Fortsetzung).
- Abschluss der Kette: `solo-session-bericht` + TTT-Eintrag.

## Regeln für alle Sessions

- `trilium.sh` für alle Trilium-Zugriffe, keine direkten curl-Aufrufe.
- Keine Secrets im Klartext; Secret-Dateien nur blind prüfen.
- Max 2 Subagents parallel; Subagents committen nie selbst.
- Fehlende Inputs → fail closed, niemals stiller Download.
- `setup.py`/`setup.sh`/`START-HERE.bat`/`update.sh` **nicht ausführen**
  (AGENTS.md Fork-Workflow).
