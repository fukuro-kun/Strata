# SESSION_PLAN — adamant sm_86 Early-Validation auf eris (Solo-Nachtsession 2026-11-19)

> Lokal, nicht committen. Zweck: persistente Planungsdatei für die Solo-Session.

## Session-Ziel

Auf eris (RTX 3080 16 GiB, sm_86) validieren ob adamant (Basalt-Fork,
Qwen3.8-Flash-Next-Inferenz, `.basalt`-Packs) baut und läuft — Smoke + kurzer
Decode-Vergleich gegen die produktive Strata + Sanity-Output-Check.
Ergebnis ist eine Entscheidungsgrundlage, kein Produktiv-Ersatz.

## Entscheidungen (Interview-Protokoll, 2026-11-19 ~01:35)

| Frage | Entscheidung | Begründung |
|---|---|---|
| Testtiefe | Smoke + Perf + Sanity | User-Wahl (empfohlene Option) |
| Quant-Konfounder (UD-IQ2_XS vs GSQ-RCO-IQ2_XS) | Messen + Caveat dokumentieren; zusätzlich `tools/convert` same-quant versuchen wenn ~1–2 h machbar | User-Freitext |
| Fehlerbudget | 4–8 h harte Obergrenze, dann Report; kein künstliches Vertrödeln; Ideal = vollständige Testsuite für relevante Quants | User-Freitext |
| Setup-Verbleib | adamant-Setup bleibt auf eris (kein systemd), Doku vollständig; Strata danach wieder wie zuvor lauffähig | User-Freitext |
| Strata während Test | Komplett gestoppt (User: "ist doch klar") | GPU-Exklusivität |
| Pack-Archiv | Nach Verify auf ganymed `/titan/topas/modelle/` sichern | User-Vorgabe |
| WAN2.2 | Auf ganymed verifiziert-archiviert → auf eris gelöscht (184 G frei, jetzt ~296 G) | User-Vorgabe |

## Schritte

| # | Schritt | Status |
|---|---------|--------|
| 1 | CUDA-Runfile fertig → `~/cuda-13.1` Userspace-Toolkit | ✅ (libxml2-Blocker → `--noexec`-Pfad ungenügend → Payload ab Byte 14769 `tail\|gunzip\|tar` extrahiert + Komponenten-Merge; glibc-Konflikt `rsqrt` noexcept-Patch) |
| 2 | Pack-DL fertig (74,37 GiB) → sha256 `ae1b92ab…` → rsync nach ganymed | ✅ DL+Hash; rsync läuft |
| 3 | sm_86-Build `CMAKE_CUDA_ARCHITECTURES=86` | ✅ sauber gebaut (basalt/-probe/-bench) |
| 4 | Strata gestoppt → adamant Smoke | ✅ läuft + 'Paris'; ⚠️ host_agent-reconcile.timer killte basalt + restarted strata → Timer+Service für Testfenster gestoppt (WIEDER AN am Ende!) |
| 5 | Perf-Vergleich (upstream-Fixture-Protokoll, corpus sha `189f851f`) | ✅ Strata 15.5 tok/s wall median; adamant spec=0 ~10; **spec=8 crasht: verify timeout 20s/Layer unter File-Tier-Streaming (5/5 repro)** — kleine Prompts ok; route-tail-skip hilft nicht |
| 6 | same-quant convert | ✅ `gsq-rco-iq2xs.basalt` (66.4 G, 756 s) — **Befund:** GGUF-Quant-Typen 29/42 → `fallback: glue off` → CPU-Fallback → verify-timeout trotz Voll-Residenz; `--sections-from`-Graft scheitert an mtp/dense-SHA (eigener Drafter im GGUF) |
| 7 | Strata + reconcile.timer wieder an + Health | ✅ 'Paris'-Smoke grün |
| 7b | Test-Suites | ✅ CPU 76/76, GPU 103/104 — **1 Fail `prefill_hc_up_mix_test`** (8-bit-copy T=129, Bit-Diffs) |
| 8 | Doku: LOKAL.md ✅, TTT, Trilium; Abschlussbericht | ⏳ |

## Verifikations-Strategie

- Build: Binary existiert, `--version`/Startbanner OK.
- Smoke: health-Endpoint + Chat-Completion antwortet kohärent.
- Perf: gleiche Prompts/max_tokens wie Tail-Skip-Runs (JSONL mitprotokollieren);
  Vergleichsanker Strata Decode ~47 t/s (=7), ~35 t/s (=0) aus A/B-Run.
- Sanity: faktische Kernfragen (Paris etc.) + keine offensichtlichen
  Artefakte/Endlosschleifen; finish_reason prüfen.
- Restore: eris-strata ready + bekannter Smoke-Request ok.

## Live-Verifikations-Szenario

Kein Code-Change am Fork — Live-Verifikation = adamant-Engine auf sm_86
tatsächlich inferiert (mehrere Requests, plausible Outputs) + Strata-Restore
smoke-grün. N/A für Subagent-User-Test.

## Defaults

- Port für adamant-Test: 18090 (frei, nicht im Konflikt mit eris-strata/chat).
- API-Key: keiner (localhost-only Test).
- Bei adamant-CLI-Divergenz: `serve`-Pfad aus building.md/README folgen,
  `--help` konsultieren.
- `--route-tail-skip`: zuerst OFF (adamant-Default, accuracy-first);
  falls Zeit: optionaler Arm mit Skip an.

## Recherche-Fallbacks

| Problem | Reaktion |
|---|---|
| CUDA-Runfile-Install schlägt fehl | `--help` lesen, Alternativen: conda-Toolkit `nvidia/cuda-toolkit` userspace, oder deb-Pakete einzeln entpacken |
| nvcc 13.1 vs. gcc-13 Konflikt | `CUDAHOSTCXX`/`CMAKE_CUDA_HOST_COMPILER` setzen; ggf. gcc-12 prüfen |
| Build-Fehler sm_86 | Compile-Log sichern, betroffene Datei/Kern isolieren, Issues/Upstream-Basalt-Diffs recherchieren |
| Pack läuft nicht (RAM/VRAM) | `--resident`-/Expert-Cache-Flags prüfen; strata-Referenz: 12 GiB resident budget streamt OK |
| Server-API anders als erwartet | `--help`, serve/-Quelltext lesen |
| Convert-Pfad braucht >2 h | Zeitbudget dokumentieren, abbrechen, Befund + nächste Schritte |

## Offene Fragen

- Ob `tools/convert` unsere GSQ-RCO-GGUF akzeptiert (Format/Eingänge) — wird
  im Lauf beantwortet.
- Ob sm_86-Lauf performant oder nur funktional ist — Kernfrage der Session.

## Folge-Plan

Nach Abschluss: Ergebnis-Report → je nach Befund
`SESSION_PLAN_adamant_fortsetzung_01.md` (z.B. same-quant-Vergleich,
Dauer-Stabilität, `--route-tail-skip`-Arm, uranus-sm_89-Gegenprobe sobald Host
wieder da).
