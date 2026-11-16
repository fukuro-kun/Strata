# ROADMAP — eigener, upstream-naher Strata-Fork

Kanonischer Plan für diesen Fork. Private Umgebungsdetails (Pfade, Hosts, IDs)
stehen in `LOKAL.md` (lokal, nicht versioniert). Arbeitsregeln: `AGENTS.md`.

## Ziel

Aktueller Integrations-Abgleich und Laufzeitstand: **`docs/UPSTREAM_SYNC_STATUS.md`**
(2026-11-02: beide Hosts auf Kandidatenstand, Abnahme teiloffen).

- Eigener Strata-Fork, der **nah an upstream** bleibt (geringe, reviewbare Divergenz).
- **Vollständig erhaltene Historie** — kein Shallow-Clone, keine gekürzte Vorgeschichte.
- **Pruefziel ist der auszuliefernde Stand samt Lieferkette**, nicht jede
  historische Dateiversion (Nutzerentscheidung 2026-11-01). Nicht eingesetzte
  Bereiche getrennt ausweisen; Details: `docs/UPSTREAM_SYNC.md`.
- **Linux ist die Zielplattform.** Keine Apple-/Windows-Builds oder
  umfangreichen Plattformtests; nur Linux-relevante Vertrauensgrenzen
  und gemeinsam verwendete Komponenten pruefen.
- **Keine ungeprüften Release-Binaries** — Builds aus geprüften Quellen mit lokaler Toolchain.
- **Kein Docker-Erfordernis** für Build, Start oder Kalibrierung.

## Aktueller Status

**Freigabe erteilt 2026-10-17 (Entscheidungs-Interview):** Phasen P0–P4
werden **vollständig autonom** in einer Solo-Session durchgearbeitet; P5 wird
vorbereitend evaluiert (Evaluierungs-Dokument, keine Implementierung).
Zusätzlich freigegeben: **Umstellung bestehender Strata-Deployments im LAN
auf diesen Fork** nach Abschluss von P4 — mit Rollback-Bereitstellung — sowie
die Festlegung dieser Deployment-Regel in allen Deploy-Dokus und
Trilium-Notes.

Einzelheiten: `docs/SOLO_SESSION_OVERVIEW.md` und die verketteten
`docs/SOLO_SESSION_*.md`-Pläne.

- **Gepinnte Baseline (P0 verifiziert):**
  `296b59d2f73c8f04a805df29c2fa97655adace78` — Tree-Diff gegen den unabhängigen
  Audit-Checkout identisch; Stichproben-Review bestätigt; ein laufender
  Produktiv-Checkout steht auf derselben SHA. Nachweis: `docs/INVENTAR.md`.
  Früherer Audit-Bezug war dieselbe SHA, Robert-Snapshot `b124b59`; daraus folgt
  **keine** automatische Freigabe des jeweils aktuellen Default-Heads.

## Begriffe

- **Kontrollierte Online-Beschaffung**: bewusster, dokumentierter Bezug von
  Quelltext und Abhängigkeiten (Clone, reviewed Fetches, exakt gepinnte Wheels).
- **Offline-Build/Start/Kalibrierung**: alle Schritte danach laufen ohne
  Netzwerkzugriff — kein Auto-Download, kein stiller Fallback.

## Phasen

### P0 — Inventar und Baseline-Freeze — **ERLEDIGT 2026-10-18**

- [x] Quell-Inventar: `src/`, `include/`, `serve/`, `tools/`, `cmake/`, `CMakeLists.txt` → `docs/INVENTAR.md` §1
- [x] Abhängigkeits-Inventar: `requirements.txt`, externe/eingebettete Deps → §2
- [x] Lizenz-Inventar aller Komponenten → §3
- [x] Toolchain-Inventar: Compiler, CUDA/HIP-Versionen, Python-Version → §4 (4 Hosts gemessen)
- [x] Provenienz von Modell, Pack, Draft-Modell und Projektor (Herkunft + Hashes) → §5
- [x] Reviewte SHA einfrieren und als Pin dokumentieren → `296b59d2…`, §0

**Akzeptanz erfüllt:** `docs/INVENTAR.md` mit Herkunft/Hash je Quelle; eingefrorene,
reviewte SHA dokumentiert. Host-Details und Hash-Rohdateien: `LOKAL.md` + lokale
Evidenz-Ablage (Bewusst nicht committed — Repo-Regel).

### P1 — Isolierter Offline-Build-Einstieg — **ERLEDIGT 2026-10-18**

- [x] Build-Einstieg: `tools/offline/build_engine.sh` (fail-closed, keine Netz-Aufrufe)
- [x] Vendored ggml/llama-Bäume (`strata-ggml`, `strata-llama`, `strata-gguf-py`)
      @ `3cf03257…`, per-Datei-verifiziert via `tools/check_vendored.py`;
      Voll-Checkout optional via `tools/offline/fetch_llamacpp.sh` (nur
      `STRATA_GGML_DIR`-Override-Builds)
      (LAN-Kopie, byte-identisch zu zwei Produktiv-Bäumen verifiziert)
- [x] Fail closed: **kein** FetchContent-Pfad mehr — leeres `STRATA_GGML_DIR`
      resolve-t auf vendored `third_party/strata-ggml` (Netz-Beschaffung zur
      Configure-Zeit strukturell unmöglich); Skript bricht bei fehlendem
      Input/Pin-Mismatch ab — live getestet
- [x] Eigene Engine aus Quellen: `engine/strata` + `strata-vision` +
      `libstrata_kq.so` auf hydra gebaut (CUDA 13.4, sm_86), Smoke-Test ok

**Akzeptanz erfüllt:** Build lief komplett ohne Netz-Fetch (Configure-Log
fetch-frei); fehlender Input → kontrollierter Abbruch. Doku: `docs/OFFLINE_BUILD.md`.

### P2 — Python-Abhängigkeiten lokal bereitstellen — **ERLEDIGT 2026-10-18**

- [x] Exakte Wheels mit Hashes lokal bereitstellen: `wheelhouse/` (gitignored)
      + `wheelhouse/MANIFEST.sha256` (committed); Beschaffung via
      `tools/offline/fetch_wheels.sh` (cp312 + cp314 + CUDA-13/12-Runtime-Wheels)
- [x] `serve/` vorerst unverändert beibehalten
- [x] `setup.py` aus unseren Build-/Start-/Update-/Kalibrierungspfaden entfernt:
      `tools/offline/make_venv.sh` (--no-index, Manifest-Verify vor Install),
      `run_server.sh` (Config-Validierung, fail closed), `calibrate.sh`,
      `make_config.py` (minimaler Config-Writer)
- [x] Kein Auto-Fallback/Auto-Download in eigenen Pfaden
- [x] Upstream-Engine und MultiGPU-Funktionalität möglichst unverändert lassen

**Akzeptanz erfüllt:** venv-Install lief mit `--no-index` rein aus dem
Wheelhouse; Mock-Server-Start via `run_server.sh` ok; kaputte Config bricht
mit Klartext ab. Doku: `docs/OFFLINE_BUILD.md` (Python-Deps-Abschnitt).

### P3 — Manifeste und kontrolliertes Deployment — **ERLEDIGT 2026-10-18**

- [x] Immutables Build-/Modell-Manifest: `tools/offline/make_manifest.py`
      (fork_sha, baseline_sha, fork_files/-commits, llama_cpp-Pin, toolchain,
      deps, artifacts, build, models, created, host; dirty tree → Abbruch)
- [x] Toolchain-, Versions- und Dependency-Hashes im Manifest
- [x] Binary-Hashes der erzeugten Artefakte (artifacts{sha256,size})
- [x] Kontrolliertes systemd-Deployment mit Rollback: `deploy_local.sh`
      (versioniertes `strata-deploy/<id>/`, atomarer `current`-Symlink-Swap,
      `previous`-Tracking, User-Unit `strata-fork.service`),
      `rollback.sh` (verifiziert Ziel-Manifest vor dem Swap)
- [x] **Kein Produktiv-Deploy ohne separate Freigabe** — diese Session
      stellt nur den Mechanismus, LAN-Umstellung folgt in Session 006

**Akzeptanz erfüllt:** Manifest verifizierbar (`--verify` re-hasht Artifacts
+ fork_sha + deps); Rollback-Pfad lokal auf dem Build-Host getestet
(deploy v1 → v2 → rollback auf v1). Doku: `docs/DEPLOYMENT.md`.

### P4 — Upstream-Sync-Disziplin — **ERLEDIGT 2026-10-18**

- [x] Upstream-Fetch nur bewusst angestoßen: erster Fetch 2026-10-17,
      `upstream/main` = `296b59d2…` (exakt P0-Baseline, Tag v0.1.44.1)
- [x] Diff-Review: 0 Commits Drift — Bericht
      `docs/upstream-reviews/REVIEW_2026-10-17_296b59d2.md`
- [x] Tests vor Promotion: Prozess in `docs/UPSTREAM_SYNC.md` verankert
      (kein Merge nötig — keine Divergenz)
- [x] Kein Auto-Pull/Auto-Update; `upstream`-Push bleibt `PUSH_DISABLED`
- [x] **Push-Gate** (2026-10-17, mit Server-Mirror verschärft): unreviewter
      Upstream-Stand wird **nie** auf einen `origin`-Branch gepusht — der
      Mirror macht ihn sofort öffentlich. Clean-Verdict-Kriterien in
      `docs/UPSTREAM_SYNC.md` §Push-Gate

**Akzeptanz erfüllt:** Prozess-Doku + erster dokumentierter Review vorhanden;
keine automatische Synchronisation eingerichtet.

**Sync-Stand 2026-10-22:** Option-C-Fixpaket gemergt als `2a45eb38` und auf
beiden Produktiv-Hosts deployed (Rollback über `previous` scharf): 6
Upstream-Fixes (spec_pos-Sentinel, `STRATA_SPEC_WATCH`-Stall-Diagnose,
NaN-Retry, HTTP 503 bei Engine-Startfail, Tool-Call-Envelopes +
deklarierte-Tools-Filter, Vision-Workfolder-Recreation) plus 2
Fork-Korrekturen aus der Gegenprüfung (Watchdog-Done-Flag `ccf4d0a1`,
Vision-Cache-Lock `6ef6931a`). Review:
`docs/upstream-reviews/REVIEW_2026-10-22_6ef6931adba1.md` (SAUBER).

**Sync-Stand 2026-11-16:** Vollmerge `baf16363b` (v0.2.14 / engine 0.1.60,
2.132 Commits) als `a146dfdf7` + Fixes bis `b53b531bf` auf `main`
und auf eris+uranus deployed. Radar-Delta `13eedf55..baf16363b` damit
vollständig integriert. Report:
`docs/upstream-reviews/INTEGRATION_2026-11-16_strata-v0214-merge.md`.

**Neuer Rückstand (selber Tag):** Upstream taggte **v0.2.15**
(`c77572806`, Control 0.1.61, Engine unverändert 0.1.60) — 45 Commits,
121 Dateien. Kein Engine-Delta; produktionsrelevant sind zwei kleine
serve-Fixes (bool-Tool-Args #5979, stop-drain #6055), Rest ist
App-/Launch-/Install-Territorium. Kurz-Radar:
`docs/upstream-reviews/RADAR_2026-11-16_v0215.md`. Eigener
Integrationsauftrag beim nächsten Sync-Fenster.

### P5 — Frontend — **ENTSCIEDEN 2026-10-17: No-Go für Robert**

Evaluierung in `docs/P5_ROBERT_FRONTEND_EVAL.md`; fukuro hat die
**No-Go-Empfehlung bestätigt**. Befund: Roberts Frontend lehnt Multi-GPU
und `--vision` aktiv ab, hat kein `/slots` → InferenzQuelle-Live-Admission
würde `live_check_failed` liefern, keine Anthropic-Endpoints. Robert
adressiert Einzelmaschine/eine GPU ohne Router — nicht unser Profil.

**Festgelegte Linie:** Der Python-Server (`serve/server.py`) bleibt das
Frontend. Falls langfristig ein Rewrite nötig wird (Footprint, Dienst-
Robustheit), dann als **separates Projekt in Rust** — nicht C++: die
Engine-Anbindung ist das Pipe-Protokoll (`strata --serve`), kein
Speicher-Linking; Rust bietet für einen Langläufer-Netzdienst
Speichersicherheit, `tokio`-SSE/Disconnect-Handling und fail-closed-
Fehlerbehandlung. Tokenizer/Template wären über `tokenizers`+`minijinja`
gedeckt, Vision über das `strata-vision`-Kind. Kein Import von Roberts
Qwen3.6-/Kernel-Divergenz — das bleibt verbindlich.

Checkboxen obsolet — Phase damit abgeschlossen:

- [x] ~~Nur nach **expliziter Entscheidung**: Frontend als separate
      Komponente~~ → entschieden: kein Robert-Frontend
- [x] Kein Import der gesamten Qwen3.6-/Kernel-Divergenz
- [x] InferenzQuelle: Live-Slot-Admission bleibt unverändert aktiv

**Akzeptanz erfüllt** durch dokumentierte Entscheidung statt Go.

### LAN-Umstellung auf den Fork (Session 006) — **uranus LIVE 2026-10-17**

- [x] Deploy-Matrix über alle Hosts; produktive Strata-Endpunkte:
      uranus :18086 (InferenzQuelle `uranus-swift15`, System-Unit
      `strata-swift-uranus.service`) und eris :8080 (manuell, keine Unit)
- [x] Fork-Checkout + P1-Engine-Build + P2-Venv + P3-Deploy auf uranus
      (sm_89/CUDA-13.0) und eris (sm_86/CUDA-12.4) — Manifest verifiziert,
      `current`-Symlink gesetzt
- [x] **uranus umgestellt und abgenommen:** System-Unit läuft auf
      `~/strata-deploy/current/run.sh`; `/slots` + echte Chat-Completion
      verifiziert, janus-Router meldet `uranus-swift15` healthy; Rollback
      auf den alten Stack real geübt und zurückgewechselt
- [x] **eris LIVE 2026-10-17 ~23:48 MESZ** — `eris-chat` abgeschaltet
      (inactive+disabled), danach startete `eris-strata.service`
      (IQ-Profil-Unit, ExecStart `~/strata-deploy/current/run.sh`
      :8080) sauber durch: `/health` loaded, Modell
      `qwen38-flashnext-swift15-standard-iq2_xs`, 262144 ctx,
      echte Completion 400 Tokens @ 41,7 tok/s. Früherer
      `strata-fork`-Unit-Versuch scheiterte fail-closed an
      `cudaMalloc` (eris-chat belegte 15,6/16 GiB) — mit GPU-Freigabe
      aufgelöst; die überflüssige Test-Unit wurde entfernt
- [x] ganymed: kein Strata-Dienst (Modellarchiv) — nichts umzustellen

Details und Switch-Runbook: `docs/SOLO_SESSION_006_lan_umstellung.md`,
`docs/DEPLOYMENT.md`.

## Umgesetzte Fork-Fixes

### Engine-Auto-Recovery (`engine_auto_restart`) — Branch `feat/engine-auto-recovery`, lokal implementiert 2026-10-18

**Root Cause:** Stirbt der Engine-Kindprozess zwischen Requests (z. B. vom
internen `ERR verify: timed out`-Pfad per `proc.terminate()`), bleibt der
Python-Server äußerlich gesund: `/slots` liefert `[]`, `/v1/status` meldet
`loaded:false`. Ein nachgelagerter fail-closed Router nimmt den Endpunkt
dann aus der Rotation, sodass nie wieder ein Request ankommt, der
`auto_load` auslösen könnte — Deadlock. `Restart=on-failure` greift nicht,
weil die Unit (Python-Server) lebt.

**Fix:** Opt-in-Config `"engine_auto_restart": true` (strikt bool, Default
`false`). Ein Watchdog-Thread in `serve/server.py` (1 s Poll) startet eine
tote native `StrataEngine` über denselben `ensure_loaded`-Pfad wie ein
Request (`before_load`, `min_free_vram_mib`, Vision). Budget: max. 3
Versuche in 900 s rollendem Fenster, ≥15 s Abstand; Recovery-Versuche
laufen mit `restart(tries=1, start_retries=0)`, d. h. auch die inneren
transienten Konstruktor-Retries sind deaktiviert — maximal ein nativer
Spawn pro Autoversuch (auch eine Load-Hook-/VRAM-Verweigerung verbraucht
den Versuch ohne Spawn). Manuelle `/load`-/Request-Loads behalten die
bisherigen Engine-Retries. Bewusst entladene
(`POST /unload`, Idle-Unload, nie geladen), lebende, busy/queued/draining
oder startende Engines bleiben unberührt; der ausgefallene Request wird nie
wiederholt; `/slots` bleibt bis READY `[]`. Status additiv unter
`engine_recovery` in `/health` und `/v1/status`. Shutdown: Worker stoppt
und joint vor `engine.close()`; ein bereits laufender Start darf zu Ende
laufen — die Bereitschaftswarte (`ENGINE_READY_S`, Default 900 s) begrenzt
nur das Warten auf READY, Hooks und Cleanup laufen zusätzlich.

**Status:** Auf den main-Stand portiert und mit CPU-Fakeprozess- und
Server-Regressionstests geprueft; der abschliessende Server-Testlauf
umfasste 404 Tests (ein Skip wegen optional fehlendem `jsonschema`).
**Freigabe 2026-10-31 (User):** gezielter produktiver Rollout **nur auf
dem lokal dokumentierten Produktionshost** — einschließlich Dienst-Neustart und gezieltem Beenden
**ausschließlich** des laufenden Engine-Kindprozesses bei freiem Slot
als Live-Nachweis. Andere Hosts sind weiterhin **nicht** freigegeben —
Configs und Ressourcen-Tuning dort unverändert. **Umgesetzt 2026-10-31: auf dem
freigegebenen Produktionshost deployt und live abgenommen** — kontrollierter
Kindtod bei freiem Slot, autonomer Watchdog-Neustart beginnt nach 0,94 s, Engine
ready nach 17,7 s, wartender Request wurde mit 200 bedient (Details nur in
`LOKAL.md`). Der Fix heilt den Recovery-Deadlock nach Kindtod — die
ursprüngliche Stall-Ursache (Ressourcen-/I/O-Druck, plausibel) bleibt offen.
Details:
`docs/DETAILS.md` (GPU-Sharing-Abschnitt, `"engine_auto_restart"`).

### Aktueller Integrations-Abgleich — `docs/UPSTREAM_SYNC_STATUS.md`

Stand 2026-11-02 (Merge `aa3e61fa`, Deploy-Quelle `fa225161`): Abgleich,
Laufzeit-Evidenz, A/B-Beobachtungen (keine Abnahme), Cache-Tuning-Stand
und die gewuenschte taegliche Integrations-Pipeline sind im Statusdokument
gebuendelt. Beide Laufzeitstaende sind kohaerent; offen bleiben die
Leistungsabnahme und der vollstaendige Rollback-Nachweis.

Nachtrag 2026-11-11: Der Pillow-Sicherheitsstand `22c64d47` lief bei der
letzten Abnahme auf beiden Zielsystemen. Die `previous`-Manifeste
scheitern dort an abweichendem Checkout und Venv-Paketstand; ein
vollstaendiger Rollback ist weder automatisch noch geuebt. Die fruehere
Formulierung "Rollback ueber previous scharf" belegt nur den Zeiger,
nicht die Wiederherstellung von Checkout und Venv.

### Pre-existing: flaky Sampler-Test (`test_responses.NoLeakedSampler`) — gefixt 2026-10-18

Der Test zählte global alle Threads mit Namen `*(_loop)` (before/after),
während `Telemetry.close()` nur das Stop-Event setzt und fremde, gerade
auslaufende Sampler-Threads anderer Tests zwischen den Messungen enden —
Assertions wie `1 != 2` ohne Produktionsbug. Der Test identifiziert jetzt
den eigenen Sampler-Thread an seiner `svc.telemetry`-Instanz und joint ihn
nach `server_close()`. Reine Test-Änderung, kein Lifecycle-Change.

## Zurückgestellt / Nicht-Ziele

- **Auth/Host/Key-Berechtigungen**: zurückgestellt gemäß isoliertem
  LAN-Bedrohungsmodell. Es wird jetzt **keine** Auth-Regression eingeführt;
  bestehende Konfiguration bleibt unverändert.
- **Vertrauensgrenze**: Source-Build reduziert das Prebuilt-Risiko, eliminiert
  aber **nicht** das Quell-/Toolchain-/Dependency-Vertrauen — P0-Inventar bleibt Pflicht.
- **Forgejo-Mirror**: optionaler Zukunftsschritt. Die kanonische Remote-Rolle
  muss **vor** einem Wechsel entschieden werden.

## Sektorierte Freigabe 2026-10-31 (nur dieser Sync)

Der Nutzer hat **für diese eine Integration** (`c62d5e3a` auf
`feat/eris-engine-recovery`-Basis) freigegeben: sequentielle Testfenster und
— nach bestandenen Gates — das Deployment auf den zwei lokal benannten
Produktionshosts, **ein Host nach dem anderen**. Keine generelle oder
zukünftige Freigabe. Host-Zuordnung und Privatdetails bleiben in
`LOKAL.md`. Die historische Eris-Recovery-Freigabe wird dadurch **nicht**
auf Aktivierung von Recovery-Flags auf anderen Hosts ausgeweitet.

## Bestätigter Memory-Safety-Fix (Verifikation offen)

- **PGroup-Fenster-OOB unter `--batch-mtp` + `--batch-groups`**: `slots_in_windows`
  klemmte bei `batch_mtp` nicht auf `kVerifyMaxT`; ein piped-Fenster schrieb GS
  Token-/Pos-Zeilen ueber die Verifier-Grenze hinaus (Host-OOB bei `kVerifyMaxT=8`
  ab GS 9, bei Wide-Build 16 ab GS 17). Fix: neuer reiner Helper
  `batch_groups::group_window_fits()` + zweiter fail-closed Guard vor der PGroup-
  Konstruktion (refuse, kein Clamping). Serial-Pfad unveraendert; Default-Profile
  (kein --batch, kein Layer-Split-Pipelining; MTP selbst ist in
  beiden eingefrorenen Produktions-Profilen vorhanden und unbetroffen) unbetroffen.
- **Verifikationsstand**: statisch bestaetigt (Review-Kette, kein GPU-Repro);
  `batch_groups_test` inkl. der neuen Checks lokal gruen (kein GPU, kein
  Modelllauf); `generate.cpp` als geaenderte TU kompiliert unter den Build-Flags
  einzeln (`STRATA_VERIFY_MAX_T=8` und `=16` separat) — kein vollstaendig gelinkter
  Engine-Nachweis. HIP/SYCL/Metal nutzen dieselbe Quelle — Backend-
  Validierung bleibt offen (Gate, nicht "gruen"). Das eingefrorene `ec02`-Binary
  bleibt nur Referenz, kein Kandidaten-Artefakt mehr.
- **User-Entscheide**: voller Git-Merge (kein Source-Snapshot);
  keine automatische CI im Fork — `.github/workflows` bleiben als manuelle
  Upstream-Referenz (`on:` nur `workflow_dispatch`, Jobs zusätzlich
  repository-guarded).
- **P2-Befund (Updater-Test-Start)**: `default_test_start` entfernte
  `STRATA_API_KEY` innerhalb von `_patched_environ`, ohne ihn in der
  Env-Map zu erfassen — der Eltern-Key ging nach dem Kontext verloren
  (nur expliziter Update-Smoke-Pfad, kein Produktionspfad; der
  Produktions-Updater ist ohnehin Default-Deny). Fix: `'STRATA_API_KEY': ''`
  in der Env-Map (eine Zeile). AST-Unit-Test 4/4 gruen im Clean-Env
  (`integration/narrow/updater-env-cleanenv/`, Negativbeleg 2 fail /
  Positivlauf 4 pass). Die unabhaengige Gegenpruefung bleibt offen.
- **P2-Befund (Komponenten-Installationspfad)**: `ComponentStore.install`
  setzte `into = staging / artifact.unpack_to` ohne Pruefung — ein
  Manifest konnte die Stage verlassen (`..`, absolute Pfade, Drives, UNC,
  Symlink-Umgehung). Bibliothekspfad, kein Produktions-Caller belegt
  (der gepruefte CLI-Manifestplan `_components_plan` ist read-only); statisch
  bestaetigt, nicht als RCE bewiesen. Fix am Schreibpunkt: `unpack_to`
  gegen `_check_member_within` (lexikalisch + aufgeloest) geprueft;
  `None`/`''`/`'.'`/`'./'` explizit als Stage-Root akzeptiert, Nicht-Strings
  als ComponentError. Test 7/7 gruen im Clean-Env
  (`integration/narrow/component-dest-cleanenv/`, Negativbeleg 2 Tests /
  7 subTests fail, Positivlauf alle ok). Die unabhaengige Gegenpruefung
  bleibt offen.
- **P2-Befund (DSV41-Beschaffungs-Gate)**: Die lokale Paketinstallation
  `install_package` und die Remote-HEAD-Probe `source_reachable` hatten
  kein Beschaffungs-Gate. Eine vorhandene
  DeepSeek-Installation erreichte den Feed-HEAD auch mit
  `STRATA_NO_ACQUIRE`, ein lokales signiertes Upstream-Paket umging
  die Beschaffungskontrolle. Statisch bestaetigter Policy-Gap, kein
  Produktions-Angriffspfad; der aktuelle Qwen-Offline-Starter ist nicht betroffen.
  `install`/`upgrade` hatten bereits ein indirektes Feed-Gate; die neuen
  Eingangsguards verhindern dort nun auch vorgelagerte lokale Nebeneffekte.
  Fix: ein Top-Import + 4 Guards (`acquisition.require(...)` je erste
  ausfuehrbare Zeile bzw. vor `urlsplit` nach dem lokalen Zweig).
  Test 7/7 Methoden / 16 subTests gruen im Clean-Env
  (`integration/narrow/dsv41-gate-cleanenv/`, Negativbeleg 1 fail,
  Positivlauf alle ok; lokale Probe bleibt ohne Acquisition erlaubt,
  getestet). Die unabhaengige Gegenpruefung bleibt offen.
- **P2 Mac-Plan-Expertenzahl**: Die Anzeige-Rundung auf 0.1 GB wurde vor
  der Expertenzaehlung angewandt. Synthetische Plaene konnten dadurch mehr
  als die vorhandenen 15360 Experten oder zu wenige bei Vollresidenz
  melden. `_plan_mac` zaehlt jetzt aus ungerundetem Budget und behandelt
  Vollresidenz exakt. Drei isolierte Testmethoden bestehen; dieselben
  Tests hatten vorher 16 Subtest-Fehler. Nur Plan-Metadaten, kein
  GPU-/Produktionsnachweis. Gesamt-Gegenpruefung, Lieferkette und A/B
  weiterhin offen.
- **P2-Befund (MCP-Installations-Gate)**: `Tools.launch_install` und
  `install_job` in `tools/strata_mcp.py` schrieben State/Spec und
  starteten den Installer-Kindprozess ohne Acquisition-Gate; im
  Control-Zweig wurde `STRATA_NO_ACQUIRE` fuer das Kind sogar entfernt
  (bei geerbtem Allow konnte so der Beschaffungsstopp im Kind verloren
  gehen). Statisch belegte Kette, kein realer Installerlauf, kein
  Qwen-Produktionscaller. Fix:
  sys.path-Guard + Gate als erste Zeile beider Primitive, `env.pop`
  entfernt, `main --install-job` ueber `main_guard` (Exit 5 statt
  Traceback). MCP-Modellinstaller und Hintergrundjob brauchen vor
  State-/Spec-/Venv-Zugriff das Fork-Beschaffungs-Gate. STRATA_NO_ACQUIRE
  wird nicht mehr fuer CONTROL-Kinder entfernt; Allow ueberstimmt diesen
  Stopp weiterhin nicht. Nur isolierte Mock-/AST-Belege, keine echte
  Installation (8/8 Methoden gruen inkl. Bootstrap-AST-Test,
  Negativbeleg: beide Primitive erreichten ungated lokale Sentinels).
  Die unabhaengige Gesamt-Gegenpruefung bleibt offen.
- **P2-Befund (CUDA-12-Treiberfloor-Feed)**: Die
  CUDA-12-Treiberfloor-Abfrage konnte den signierten Feed ueber einen
  eigenen Thread ohne Fork-Allow-Gate lesen (`from_feed` in
  `driver_floor.py`; `setup.py` pruefte nur `is_forbidden`). `from_feed`
  prueft jetzt vor dem Threadstart; lokale installierte Metadaten und
  der konstante Fallback bleiben ohne Beschaffung erlaubt. Isolierte
  Mock-Belege, kein realer Download (7/7 Methoden gruen, Negativbeleg
  1 fail: Mock-Thread ungated erreicht). Die unabhaengige
  Gesamt-Gegenpruefung bleibt offen.
- **P2-Befund (Windows-HIP-Hardwareprobe)**: `hip_devices` kopierte vor
  `--list-devices` Runtime-DLLs in den Engine-Ordner. Auch die
  Planungs-Hardwareabfrage erreichte diesen Helfer. Die Probe repariert
  jetzt nicht mehr; `hip_card` repariert weiterhin vor der expliziten
  Installationspruefung. Sechs isolierte AST-/Mock-Testmethoden bestehen,
  am ungefixten Stand schlagen fuenf unabhaengige Subtest-Assertions
  wegen der DLL-Schreibzugriffe fehl. Kein Windows-/HIP-Hardwaretest,
  kein Nachweis fuer vollstaendig schreibfreies `--plan`; weitere
  Nebenwirkungen und die unabhaengige Gesamt-Gegenpruefung bleiben offen.
- **P2-Befund (Metal-/SYCL-Build-Gates)**: Die Metal-Buildhelfer
  starteten CMake/Ninja direkt; mit schon vorhandenen Quellen, Headern
  und Werkzeugen konnte das Beschaffungs-Gate entfallen. Engine- und
  Bildleser-Build pruefen jetzt vor den Build-Vorbereitungen. Der
  SYCL-Bildleser prueft vor der oneAPI-Umgebung, nicht erst in CMake;
  die Verweigerung wird nicht mehr als normaler Buildfehler geschluckt.
  Vorhandene gueltige Artefakte bleiben ohne Allow wiederverwendbar.
  Beide Backend-Einstiege behandeln Verweigerungen mit Exit 5 statt
  Traceback. Dreizehn isolierte AST-/Mock-Methoden bestehen; identische
  Tests am Original belegen zwoelf Gate-Verletzungen und vier fehlende
  Fehlerbehandlungen. Keine echte Backend-Kompilation oder Installation;
  unabhaengige Gesamt-Gegenpruefung und Backend-Nachweise bleiben offen.
- **P2-Befund (Standalone-MTP-Beschaffung)**: `tools/mtp_fetch.py`
  konnte direkt per CLI oder Helfer HEAD-/GET-Anfragen ohne Fork-Gate
  senden. Der normale Root-Setup-Aufruf war bereits durch `run`
  geschuetzt; kein neuer Produktions-Bypass daraus. Metadaten-, Fetch-
  und Range-Primitiven sowie CLI pruefen jetzt vor Netz-, Thread- oder
  Lock-Vorbereitung. `verify` bleibt offline ohne Allow nutzbar
  (einschliesslich seines lokalen Verifikationscaches). Verweigerungen
  werden mit Exit 5 gemeldet. Dreizehn isolierte Gate-/Mock-Methoden
  und drei selektierte bestehende Range-Tests bestehen; identische
  Gate-Tests am Original belegen 24 negative Subtests und zwei fehlende
  Guard-Behandlungen. Keine echten Downloads, Threads oder Modelle;
  unabhaengige Gesamt-Gegenpruefung weiterhin offen.
- **P2-Befund (Supply-Chain-Gate, lokale Paketinstallation)**:
  `strata_cli/update_cmd.py` verzweigte `install-file` VOR dem
  Acquisition-Gate; `updater.install_engine_file` hatte keines — ein
  explizites lokales signiertes Upstream-Paket umging die
  Fork-Beschaffungskontrolle (kein Netz-/RCE-Befund, kein
  Produktionspfad). Fix: eine Zeile `require_acquisition("the local engine
  package")` als erste ausfuehrbare Zeile. Test 5/5 gruen im Clean-Env
  (`integration/narrow/local-engine-gate-cleanenv/`, Negativbeleg 1 fail,
  Positivlauf alle ok). Die unabhaengige Gegenpruefung bleibt offen.

## Weiterhin verboten (trotz Freigabe P0–P4)

- Keine Auto-Downloads oder Fallback-Beschaffung in eigenen Pfaden —
  Beschaffung nur bewusst, dokumentiert, gepinnt
- Keine Modifikation von Upstream-Engine-Code über die Roadmap-Ziele hinaus
  (`serve/` und Engine bleiben upstream-nah)
- Taegliche **eigene** Upstream-Integration ist gewuenscht (Nutzer 2026-11-01): bewusster Fetch -> Pin -> Review -> isolierter Merge -> Offline-Regressionen -> Bericht; Konflikt/Gate-Fail = Quarantaene + Meldung. Ziel, NICHT implementiert; keine fremden Workflows, kein unreviewtes Veroeffentlichen, kein Prod-Auto-Deploy. Bestehender `daily`-Radar ist nur Beobachtung. Details `docs/UPSTREAM_SYNC_STATUS.md`
- Kein Push nach `upstream` (Remote bleibt push-gesperrt)
- Keine Produktiv-Umstellung vor Abschluss der jeweiligen Phase bzw. vor P4
  für die LAN-Umstellung; jede Umstellung mit dokumentiertem Rollback-Pfad
- Keine Auth-/Host-/Key-Änderungen (zurückgestellt, siehe oben)
