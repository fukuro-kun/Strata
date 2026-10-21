# P5-Evaluierung: Robert-C++-Frontend (`robertkarl/UnbiasedStrata`)

Evaluierungs-Dokument — **keine Implementierung**. Quelle: lokaler
Audit-Checkout `/tmp/unbiased-strata-src` @ `b124b59` (letzter Commit
2026-10-13; Stand der Erhebung 2026-10-17).

## 1. Was Robert ist

Ein Fork von Strata @ `6f32ec07` (Engine 0.1.39 — **älter** als unsere
Baseline `296b59d2`/v0.1.44.1) mit drei Eingriffen:

- **Entfernt:** Python-Server + Web-App, Installer (`setup.py`,
  `setup.sh`, `START-HERE.bat`), SYCL-Port, Docker, Test-Suite, die
  meisten Docs.
- **Hinzugefügt:** `frontend/` (9 Dateien, +1495 Zeilen) — ein C++-HTTP-
  Frontend: Tokenizer + Chat-Template + Output-Parser + Server aus
  llama.cpp-Code (`httplib`, `mtmd`). Die Engine wird mit umbenanntem
  `main` (`strata_engine_main`) in dieselbe Binary kompiliert und als
  Kindprozess (`argv --engine`) über stdin/stdout-Pipes gefahren.
- **Engine-Delta ggü. seinem Importsnapshot:** 58 Dateien,
  +5976/−1059 — davon ~11 Dateien Parity-/Bench-Tests (~3,3k Zeilen),
  der Rest Qwen3.6-Support (`model_geometry.hpp` +262, `vram_plan.hpp`
  +178, `qsa_decode_attn.cu` ~550 Rework, `prefill.cpp` +551), die
  Slow-Store-Trias (`robust_read.hpp`, `expert_source.cpp`, `ngram.cpp`)
  und `generate.cpp` +586.

**Korrektur zum UPSTREAM.md-Wording:** „three changes" trifft nur auf die
Slow-Store-Motivik zu — der gemessene Engine-Diff ist deutlich größer
(Qwen3.6-Arbeit auf 0.1.39-Basis). Ehrlicher Befund: Die Readme zählt nur
die Lade-Pfade, nicht die Qwen3.6-Portierung.

## 2. Architektur des Frontends

- Child-Prozess-Modell: `frontend/engine_entry.cpp` bindet
  `src/program/generate.cpp` via `#define main strata_engine_main` ein;
  `engine.hpp` öffnet Pipe-Paare und wartet auf `READY <ctx> stop`.
- **Das Pipe-Protokoll ist upstream-eigen:** unser `serve/server.py`
  spricht exakt dieselben Zeilen (`READY`, `GEN <max_new> <ids>`,
  `GENI`, `STOP`, `STATS`, Batch-Varianten `BGEN`/`BSTOP`) gegen
  `strata --serve`. Robert hat das Protokoll nicht erfunden, sondern
  wiederverwendet — ein Port auf unsere Engine ist mechanisch trivial
  (`fork+exec engine/strata --serve` statt eingebettetem Kind).
- HTTP-Fläche (`main.cpp:740–786`): `GET /health` (inkl. `tiers`-
  Statistik + `busy`), `GET /v1/models`, `POST /v1/chat/completions`
  (SSE-Streaming). **Das war's.**
- Vision: `vision.hpp` decodiert base64 `data:image`-URLs, schreibt
  Embedding-Dateien via `mtmd` (llama.cpp-Mechanismus), nicht über das
  `strata-vision`-Binary.

## 3. Feature-Matrix gegen unsere Anforderungen

| Bedarf | Robert-Stand | Fundstelle |
|---|---|---|
| Multi-GPU (`--gpus`, `--layer-split`) | **aktiv abgelehnt** (exit 2) | `main.cpp:633` |
| `--vision`-Flag / strata-vision-Kind | **aktiv abgelehnt** | `main.cpp:633` |
| Vision überhaupt | ja, aber mtmd-Pfad (anderer Mechanismus) | `vision.hpp` |
| `/slots` (Readiness/Drain) | **nicht vorhanden** | Endpoint-Liste oben |
| Anthropic-kompatible Endpunkte | **nicht vorhanden** | nur `/v1/chat/completions` |
| `/metrics`, `/load`, `/unload`, `/props` | nicht vorhanden | — |
| `--remote-expert`, `--peer-*`, `--batch` | **aktiv abgelehnt** | `main.cpp:633` |
| SSE-Streaming | ja | `main.cpp` completions-Handler |
| Disconnect-Verhalten | Teilprotokoll (`STOP`) vorhanden | `engine.hpp:97` |

**Zwei harte Blocker für unser LAN:**

1. **InferenzQuelle-Admission lebt von `/slots`.**
   `router/admission.py` vergibt Router-Slots erst nach Live-Abfrage von
   `/slots` bei den Backends; ohne Antwort → `live_check_failed` → 503.
   Ein Robert-Frontend hinter dem Router wäre nicht routbar, ohne die
   Admission zu verbiegen — Roadmap-P5 verbietet genau das
   („Live-Slot-Admission darf nicht global deaktiviert werden").
2. **Uranus braucht Multi-GPU.** Profil Q/R fährt GPU 0+1 mit
   `--layer-split auto`; der Frontend-Parser lehnt die Flags kategorisch
   ab. Single-GPU ist Roberts bewusstes Scope-Limit.

## 4. Portierungs-Optionen

**(a) Roberts Engine-Delta auf unsere Baseline portieren** — 58 Dateien
inkl. Kernel-Rework, auf einer *älteren* Basis (0.1.39) entwickelt;
upstream hat sich seitdem weiterbewegt. Aufwand: hoch (Rebase über zwei
Divergenzachsen), Ertrag: keiner für unsere Ziele (Qwen3.6 ist nicht
unser Deployment-Modell). **Klares Nein.**

**(b) Nur das Frontend auf unsere Engine setzen** — Protokoll kompatibel
(s.o.), aber: Arg-Parser müsste Multi-GPU/Vision-Flags wieder zulassen,
HTTP-Fläche um `/slots` (+ Drain-Semantik), Anthropic-Endpoints,
`/metrics` erweitert werden — also genau die Dienste nachbauen, die
`serve/server.py` schon korrekt liefert. Effektiv ein neuer C++-Dienst
mit divergierender Vertragslogik. Aufwand: mittel–hoch; Divergenz-
Kosten: dauerhaft. **Nicht zu empfehlen** — kauft kein Feature, das der
Python-Server nicht schon hat.

**(c) Nicht portieren — Python-Server beibehalten** — erfüllt alle
Anforderungen heute, upstream-nah, null Divergenz.

## 5. Empfehlung

**No-Go für den LAN-Einsatz** (Stand 0.1.44.1 + InferenzQuelle-Vertrag).
Roberts Frontend adressiert ein anderes Einsatzprofil: Einzelmaschine,
eine GPU, Direktzugriff ohne Router — dafür ist es schlank und sauber.
Unsere Deployments brauchen `/slots`-Admission, Multi-GPU und die
volle Endpoint-Fläche; ein Port würde diese Verträge in C++ duplizieren
müssen — genau die Feature-Divergenz, die dieser Fork vermeiden will.

**Wenn fukuro später doch ein C++-Frontend will:** der richtige Weg ist
nicht „Robert portieren", sondern eine kleine `/slots`-fähige
Serve-Schicht gegen `strata --serve` (das Pipe-Protokoll ist stabil und
upstream-eigen) — als separates Projekt außerhalb der Engine.

**Watch-Punkt:** Robert wird aktiv gepflegt (letzte Commits 2026-10-13,
Qwen3.6-Linie). Sollte dort je `/slots` + Multi-GPU kommen, lohnt eine
Neubewertung.

## 6. Test-Plan (nur für den Go-Fall — Referenz)

Wäre ein Go dennoch beschlossen, Mindestabnahme pro Host-Typ:
`/slots` antwortet InferenzQuelle-konform; Chat-Completion e2e;
Multi-GPU-Profil R auf uranus; Vision über den vorhandenen mmproj-Pfad
(mit strata-vision-Vergleichstest); Disconnect/STOP-Verhalten;
Rollback über den P3-Mechanismus. Keiner dieser Punkte ist heute im
Frontend belegt — siehe Matrix.
