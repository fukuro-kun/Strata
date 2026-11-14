# Solo-Plan: MMQ-Speichermargen

## Ziel und Ausgangslage

Die ausgewaehlten Upstream-Aenderungen fuer MMQ-Zeilentabellen auf ihren
Sicherheitsnutzen und ihre Anwendbarkeit pruefen. Einen geeigneten Kandidaten
nur lokal auf der freigegebenen Fork-Basis vorbereiten; Produktion, Push und
Rollout sind nicht Teil dieses Auftrags.

- Fork-Basis: `7d58d42c4b0d0292e4e010c5700a96dea45175f4`
- Radar-Stand: `13eedf552417a6a791a7d13c6597e24300ee3a09`
- Ausgewaehlt: `d7f7d9677b9eb0f2895a1bc2f23fe18651408ad6`,
  `14dd746f6ac1c799e91150a9506dc1e4e37236e8`,
  `697b6d67a7d3cde6c78d0122841c6b241cdc0da3`
- Zusaetzlich entdeckte Voraussetzung: Prompt-MMQ-Fix
  `f225844d19eec380cab7c3083cc644ec37e972c5`. Dieser war nicht Gegenstand
  des letzten Tagesdeltas und erfordert einen eigenen vollstaendigen Review.

## Entscheidungen und sichere Defaults

| Frage | Entscheidung und Grund |
|---|---|
| Basis | Ausgelieferter `main`-Stand, eigener lokaler Worktree. |
| Umfang | Nur zusammenhaengende MMQ-Sicherheitskorrekturen und deren Tests. |
| Ausfuehrung | Nur statisch gepruefte Quellen in nachgewiesener Sandbox ohne Netz oder private Daten. |
| Unbekannte Hardware | Nicht als bestanden werten; fehlende Backends und reale Modelle als Gate erfassen. |
| Review | Eigene Pruefung ersetzt keine unabhaengige Gegenpruefung. |
| Produktion | Weder Dienste, Timer, Modelle noch Deployments anfassen. |
| Veroeffentlichung | Kein Push, keine Promotion und kein Rollout. |

## Schritte und Verifikation

| Status | Schritt | Nachweis |
|---|---|---|
| Erledigt | Basis, Historie, Regeln und Sandbox-Vorprobe | Git-SHAs; isolierter Netzwerk-Namespace, nur Loopback, Home/Run verdeckt |
| Erledigt | Patches, Abhaengigkeiten, Speicherarithmetik und Aufrufpfade pruefen | Gepinnter GGML-Kernel verglichen; Layer-Major braucht groessere Marge als Upstream |
| Erledigt | Minimalen Kandidaten vorbereiten | Isolierter Worktree `feat/sync-2026-11-13-mmq`; Produktiv-, Test- und Benchmark-Aufrufstellen angepasst |
| Erledigt | Gezielt testen und lokal offline bauen | CPU-Grenztest ASan/UBSan gruen; Pin-Sperren gruen; CUDA-Build `[171/171]` vollstaendig |
| Erledigt | Synthetische GPU-Verifikation | `prefill_mmq_ids_test`: positiv 0 Sanitizer-Fehler; Negativkontrollen 50/111 Fehler; scatter/kquant/fused-MoE/fused-IQ gruen |
| Erledigt | Unabhaengige Gegenpruefung Runde 1 | `review-glm`: 0 P0, **1 P1** (q36-Margin setzte implizit `maxr <= T` voraus), 6 P2 — Details im Reviewbericht |
| Erledigt | P1-Fix + P2-Uebernahmen | q36 margint jetzt `ne` statt `T` (invariantenfrei); `kMmqTileColsMin`-Konstante; Kommentare |
| Erledigt | Rebuild + Regression nach Fix | `strata` neu gelinkt `[12/12]`; `mmq_ids_margin_test` ok; `prefill_mmq_ids_test` gepolstert numerisch gruen |
| Erledigt | Review-Runde 2 ueber geaenderten Diff | `review-swe`: P1-Fix bestaetigt, neuer P2-1 (`set_peer`-Margin `T_max` statt `Rt`) -> gefixt; P2-2 SYCL als Folge-Gate |
| Erledigt | Review-Runde 3 ueber P2-1-Fix | `review-swe`: **ship-ready**, 0 P0/P1/P2; zwei P3-Notizen dokumentiert |
| Erledigt | Status und naechste Gates dokumentieren | Reviewbericht, TTT und thematische Projektnotiz aktualisiert |
| Erledigt | Kandidaten-Engine auf eris ausgerollt | Engine auf eris aus `f64b0f8f` gebaut (sm_86, g++-13); Deploy `f64b0f8f-20261114T193311Z`; `current` umgeschaltet, `previous` zeigt auf den alten Stand |
| Erledigt | Produktive Probe-Inferenz (Swift-Modell) | Chat-Probe `stop` mit korrekter Antwort; Prefill-Probe 1568 Tokens frisch (`cached=0`), 32 Tokens erzeugt; keine Fehler im Journal |

## Nach dem eris-Rollout

- eris laeuft auf dem Kandidaten (`eris-strata.service`, `current` ->
  `f64b0f8f-...`); Rollback = `previous`-Symlink zurueck + Restart.
- uranus bleibt unveraendert auf `7d58d42c`.

## Gate-Block 2026-11-14 abends — erledigt

- **Rollback-Uebung:** `current` -> `previous` (22c64d47-Deploy),
  Restart, Health+Smoke ok; Rueckflip auf Kandidat, Restart, ok.
  Rollback-Pfad live abgenommen.
- **A/B-Probe (reduzierter Umfang):** Baseline- vs Kandidaten-Engine
  auf eris, cold-prefill-Probes mit Unique-Nonce: Kurz 490pt median
  2785 vs 2851 ms (+2,4 %, in Streuung) → **NO_SIGNAL**; Lang-Probes
  Expert-Cache-rauschend. Kein Geschwindigkeitsgewinn erwartbar —
  Sicherheitsfix.
- **SYCL-Folgeaufgabe:** Port aller Spiegelstellen committed;
  unabhaengiges Review (review-swe) fand 1 P1 (fehlender
  Early-Guard in `carve`, behoben) + P3-Nachzuege (hc<=0, Kommentar,
  cstdint) → ship-ready. Befund: SYCL-MMQ ist heute toter Code
  (`STRATA_PREFILL_MMQ` undefiniert, `moe_mmq.dp.cpp` nicht in den
  Quellen) — Port ist Paritaets-Vorbereitung. Kein icpx/dpcpp →
  Build-Gate offen.
- **HIP-Gate:** formal geschlossen als "nicht verfuegbar" — keine
  HIP-Toolchain im LAN (alle Hosts geprueft).
- **Toolchain-Fakten:** eris CUDA 12.4 → zwingend g++-13; uranus
  PATH-nvcc 12.0 ist irrefuehrend — installiert 13.0/13.2, produktiv
  mit 13.0 (sm_89) gebaut; Uranus-Builds muessen den Toolkit-Pfad
  explizit waehlen. Folgepunkt: `build_engine.sh` soll nvcc→Host-
  Compiler pruefen und fail-closed abbrechen.
- Verbleibend vor Promotion auf `main`: Nutzer-Freigabe, dann
  Promotion + uranus-Rollout.

## Test- und Fehlerstrategie

- Vor der Ausfuehrung Testcode, Buildpfad und gepinnte Inputs statisch pruefen.
- Grenzfaelle fuer Tabellenlaenge, Ueberlauf, Allokation und Iota abdecken;
  negative Kontrollen muessen die alte Fehlannahme sichtbar machen.
- Fuer jede betroffene GPU-Variante Build und Hardwarepruefung getrennt
  ausweisen. Falls Isolation, Hardware, Modell oder Ressourcen fehlen,
  nicht ausweichen und das jeweilige Gate offen lassen.
- Ein Produktions-A/B-Vergleich ist ohne freigegebenes Testfenster, lokal
  gebaute Arme und Nachweis des aktiven Pfads nicht durchfuehrbar.
- Bei Unerwartetem Arbeit sichern, Ursache analysieren und den Scope nicht
  still erweitern. Die vorhandenen Arbeitsbaeume bleiben unangetastet.

## Offene Gates und Folgearbeit

Unabhaengige Gegenpruefung, Builds und Hardwaretests aller betroffenen
Backends, sichere A/B-Messung, Rollback-Nachweis und separate Produktivfreigabe
bleiben bis zu konkreten Belegen offen. Ein Folgeplan ist nur bei zusaetzlich
entdeckten, fuer diesen Kandidaten notwendigen Arbeitsschritten erforderlich.
Die lokale GPU wird derzeit von anderen Prozessen genutzt; keine konkurrierende
Kernel- oder Sanitizer-Messung ohne ein sicheres Ressourcenfenster.
