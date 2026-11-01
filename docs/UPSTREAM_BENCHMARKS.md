# Upstream-Uebernahme: Sicherheits- und Leistungsnachweis

## Zweck und Status

Vor einer Uebernahme in die freigegebene Fork-Linie werden LAN-Nutzen,
Sicherheit und Leistung gemeinsam bewertet. Ziel ist ein upstream-naher,
schneller Fork mit kontrollierter Versorgungskette, nicht maximale
Eigenentwicklung und auch nicht ein erzwungener täglicher Merge.

Dieses Dokument definiert das **Messprotokoll**, noch keinen fertigen
automatischen Benchmark-Runner. Ohne eingefrorene Testdaten, geprüften
Runner, geeignete Isolation und freigegebenen Testhost bleibt das Gate offen.
Der lokale Skill `.devin/skills/strata-upstream/SKILL.md` wendet es an.
Die Push-/Review-Regeln stehen in `UPSTREAM_SYNC.md`, Deployment separat
in `DEPLOYMENT.md`.

## Reihenfolge und Vertrauensgrenze

1. Hypothese festhalten: welcher Upstream-Patch verbessert was auf unserer
   Hardware? Sicherheits-/Kompatibilitätsnutzen getrennt benennen.
2. Patch samt benötigtem Code, Dependencies und Build-Pfad statisch prüfen.
   Ungeprüfte Tests oder Build-Skripte nicht zur Sicherheitsprüfung starten.
3. A = fixierter geprüfter Fork-Stand, B = lokaler Testkandidat auf derselben
   Basis mit genau dem zu bewertenden Patch oder zusammenhängenden Paket.
   B ist noch kein Merge nach `main` und kein produktives Deployment.
4. Beide Arme aus Quellen mit derselben gepinnten lokalen Toolchain und
   denselben geprüften Dependencies bauen. Keine Release-Binaries laden.
   Build und Messung ohne LAN-/Internetzugriff, Secrets, SSH-Agent oder
   Zugriff auf produktive Daten. Nur die Test-API auf isoliertem internem
   Loopback ist erlaubt, kein Host-Netzwerk und keine Router-Anbindung.
   Geprüfte Modell-/Quell-/Dependency-Inputs nur lesbar bereitstellen,
   Schreibzugriff auf dedizierte Testausgaben begrenzen; keine Host-Sockets
   oder Home-Verzeichnisse in die Testumgebung durchreichen.
5. Funktionale Regressionstests und die drei folgenden Leistungstests
   durchführen. Erst danach Nutzenentscheidung und Promotionsfreigabe.

Die geänderte Code-Stelle muss im Test nachweislich aktiv sein. Ein
grüner Test, der nur den unveränderten Fallback durchläuft, ist kein
Korrektheitsbeleg für den Kandidaten. Dispatch-/Kernel-Auswahl in A/B
prüfen und protokollieren: ein stiller Fallback oder eine andere Variante
darf nicht als Wirkung des zu messenden Patches ausgegeben werden.

Ein Worktree ist keine Sandbox. Das Messprotokoll erteilt keine Erlaubnis,
Isolation einzurichten, produktive Dienste zu stoppen oder Hosts zu belegen.
Host, Testfenster und Ressourcengrenzen vorher freigeben lassen. Insbesondere
keine Tests auf produktivem uranus ohne ausdrückliche Erlaubnis.

## Eingefrorener Messplan

Vor dem ersten Lauf `plan.json` und alle Request-Payloads lokal archivieren,
mit SHA-256 versehen und im Review-Bericht referenzieren. Nicht zwischen A
und B neu erzeugen oder nach einem schlechten Ergebnis selektiv ändern.
Ein Planwechsel beginnt einen neuen Vergleich für beide Arme.

Der Plan enthält:

- Vollständige SHAs von A/B, Patchliste, Runner-/Quellhashes, Build-Befehle,
  Compiler, Flags und Hashes beider lokal erzeugten Binaries.
- Derselbe eingefrorene, geprüfte Messclient für beide Arme, außerhalb
  ihrer Quellbäume. Server-Aenderungen müssen auch den jeweiligen A/B-
  Server starten, nicht nur die Engine tauschen. Keine Auswahl der
  "neuesten" Config, kein Anschluss an einen bereits laufenden Dienst.
- Host/GPU, Treiber, CPU/RAM, Modell/Pack/Tokenizer/Template, Vision-/Draft-
  Assets mit Hashes; private Pfade nur in lokalen Belegen.
- Identische Produktionsprofil-Parameter: Kontext, KV-Typ, GPU-Aufteilung,
  RAM-/VRAM-Budgets, Expert-Cache, I/O, MTP, Threads und Environment.
  Kein Auto-Tuning im Vergleich; neue Defaults separat nach dem identischen
  Konfigurationsvergleich messen und Unterschiede kenntlich machen.
- Sampler vollständig explizit: für diesen Qwen-Performancevergleich
  `temperature=0`, `top_p=1`, `min_p=0`, `seed=7`,
  `reasoning_effort=none`, `chat_template_kwargs.enable_thinking=false`.
  Nur von beiden Armen unterstützte Parameter verwenden; eine Abweichung
  vorab begründen und für beide Arme neu einfrieren, nie still ignorieren.
- Exakte JSON-Payloads, erwartete Funktionsergebnisse, tokenisierte
  Eingabelängen und Ausgabelimits; Test-ID und Reihenfolge.
- Identische Cache-Vorbedingungen: frischer Prozess/Session für einen
  kalten Prefix, gleiche Aufwärmung; bewusst warme Folgeturns nur in T3.
  OS-Dateicache nicht mit Prefix-/KV-/Expert-Cache gleichsetzen.
- Timeout pro Request vorab: 1800 s, kein automatischer Retry. Ressourcen-
  und Temperatur-/Taktgrenzen passend zum freigegebenen Host vorab notieren.
  Mindestens Abbruch bei zweiter konkurrierender Model-Engine oder
  `MemAvailable < 2 GiB` für drei Messpunkte im Abstand von einer Sekunde.

Produktionsgleiche Prozesslimits (insbesondere MEMLOCK) nachweisen. Beide
Arme nie gleichzeitig GPU/RAM belegen lassen. Server direkt mit bekannter
PID starten, keinen `timeout`-Wrapper für den Server verwenden. Vor dem
nächsten Arm sauberes Ende seiner Kinder und Freigabe des Speichers prüfen.
Nur selbst gestartete Testprozesse beenden; keine globalen Cache-Drops.

## Drei standardisierte Tests

### T1 - Prefill und Zeit bis zum ersten Token

- Zwei feste lange Textrequests mit etwa 4K und 16K Eingabetokens; aus
  vorhandenem, geprüftem lokalen Korpus erstellen und **einmal** als
  Payloads einfrieren. Tatsächliche Tokenzahlen für A/B prüfen, Wortzahl
  nicht als Tokenzahl ausgeben. Reicht das freigegebene Kontextbudget nicht,
  kleinere Größen vorher für beide Arme festlegen.
- Ein Client, keine Prefix-Wiederverwendung; `max_tokens=64`, Thinking aus.
  Frischer Prozess pro Teiltest verhindert Wiederverwendung der Aufwärmung.
- Primär: Prefill-tok/s aus denselben tatsächlich neu verarbeiteten Tokens.
  Zusätzlich clientseitige TTFT bis zum ersten nichtleeren Content-Token.
  Keepalives und Reasoning sind keine Content-Token. TTFT umfasst mehr als
  Prefill; beide Zahlen getrennt ausweisen.
- Fehlende oder geänderte Engine-Timing-Semantik ist ein Messproblem:
  nicht unbemerkt andere Zähler vergleichen oder TTFT als Prefill ausgeben.

### T2 - Decode bei identischer Konfiguration

- Ein fester kurzer Request, `max_tokens=512`, ein Client, Thinking aus.
  Beispiel für den einzufrierenden User-Text:
  "Schreibe eine nummerierte Liste von 1 bis 80. Erkläre in jeder Zeile
  in einem ganzen Satz eine praktische Maßnahme zur Wartung eines
  Linux-Servers. Keine Einleitung."
  Die Aufgabe ist bewusst größer als das Token-Budget: `finish_reason:
  length` ist das erwartete Ergebnis, kein Fehlschlag. Bewertet wird nur
  der >=128-Token-Präfix als Decode-Metrik, nicht die Vollständigkeit.
- Primär: Decode-tok/s, dazu tatsächliche Ausgabe-Tokenzahl, Decode-Zeit,
  gesamte Request-Zeit, Finish-Grund und vollständiger Content.
- Mindestens 128 generierte Tokens für eine Decode-Aussage. Frühes EOS
  oder Fehler nicht als schnellen Erfolg werten, sondern als Messgrenze/
  Funktionsbefund protokollieren. Bei ungleichen Arbeitsmengen ist kein
  direkter Geschwindigkeitsgewinn belegt; Payload für beide Arme überarbeiten
  und den gesamten Vergleich neu beginnen.
- Kein Gewinn durch leeren Content, repetitive Entartung, kaputtes Format,
  veränderte Sampling-/Thinking-Einstellung oder reduzierte Arbeitsmenge.

### T3 - API-/Mehrturn-Betrieb mit funktionaler Abnahme

- Fünf vorab gespeicherte Request-Payloads einer repräsentativen
  Coding-/Tool-Konversation, jeweils `max_tokens=256`, ein Client.
  Historie und Tool-Ergebnisse fest vorgeben, nicht aus den unterschiedlichen
  A/B-Antworten den nächsten Request erzeugen. Keine echten Tools ausführen.
- Gleicher frischer Sessionstart pro Arm, danach geplante warme
  Prefix-Wiederverwendung. Reale Cache-Treffer und neu verarbeitete Tokens
  dokumentieren; Cache-Verbesserung als solche benennen.
- Primär: clientseitige Gesamtlatenz pro festem Turn und TTFT, zusätzlich
  Output-Tokens und Delivery. Bei Tool-Turns ist ein schema-/argumentgültiger
  erwarteter Tool-Call eine Delivery; bei Text-Turns nichtleerer passender
  Content. Leerer Content allein beweist also keinen Tool-Call-Fehler.
- Vor/nach der Folge `/health` und `/slots` prüfen; Bereitschaft und
  Belegung müssen dem Vertrag entsprechen. OpenAI-/Anthropic-Pfade und
  Streaming prüfen, soweit der Patch sie betrifft. Auth-Verweigerung und
  fail-closed Verhalten durch dedizierte Regressionstests nachweisen.
- Eine erwartete strukturierte Ausgabe/Tool-Auswahl gegen die vorab
  gespeicherten Assertions prüfen. HTTP 200 allein ist kein Erfolg.
  Fünf Turns sind keine breite Qualitäts- oder Zuverlässigkeitskampagne.

## Wiederholungen, Rohdaten und Auswertung

- Erst einen Probelauf je Arm für Funktion und Messbarkeit; dessen Daten
  behalten, nicht in die Performancemediane aufnehmen.
- Danach **fünf gepaarte Runden** in Reihenfolge AB, BA, AB, BA, AB.
  Pro Arm und Teiltest frischen Prozess starten und denselben separaten
  kurzen Warmup-Request senden. Warmup nicht in die Messwerte aufnehmen.
  T3 hält nur für seine fünf Turns denselben Prozess.
- Alle Rohrequests, Antworten, monotone Clientzeiten, Engine-Timings,
  Tokenzahlen, Exit-/Fehlergründe und Telemetrie (Temperatur, Takt,
  RAM/VRAM, Cache) unverändert im lokalen Evidence-Archiv behalten.
  Fehlversuche nicht entfernen; korrigierte Wiederholungen kennzeichnen.
- Mediane und Min/Max pro Test/Teiltest/Turn separat berichten. Kein
  Gesamtscore und keine p95-Behauptung aus fünf Beobachtungen.
- Für eine positive Metrik mit Werten A/B:
  `Rauschen = 100 * max((max(A)-min(A))/median(A),
  (max(B)-min(B))/median(B))`.
  Bei Durchsatz `Gewinn = 100 * (median(B)/median(A)-1)`;
  bei Latenz `Gewinn = 100 * (1-median(B)/median(A))`.
  Nur vollständige, gültige Messreihen mit positiven Medianen auswerten.
- Ein Leistungssignal verlangt `Gewinn > max(3, Rauschen)` in der **vorab**
  als primär benannten Zielmetrik; das ist eine konservative Betriebsregel,
  kein statistischer Signifikanznachweis. Ein einzelner Bestlauf reicht nicht.
  Gegenrichtung analog prüfen: für Regression A/B vertauschen. Jede so
  erkannte relevante Regression blockiert die gewöhnliche Uebernahme.
- Unklare/instabile Messung = KEIN NACHWEIS, keine nachträglich abgesenkte
  Schwelle. Thermik-, Cache- oder Lastunterschiede erst beheben und neu messen.

## Entscheidung und Ausnahmen

Leistungsupdates benötigen ein klares Signal in ihrer angekündigten
Zielmetrik, keine relevante Regression in den anderen Tests, keine
funktionalen Fehler und bestandene Sicherheits-/Versorgungsketten-Gates.
Neue sichere Defaults nur für tatsächlich gemessene Hardware freigeben.
Tests auf einer sm_86-GPU belegen keinen Vorteil auf sm_89 oder HIP.

Sicherheits-, Korrektheits- und Kompatibilitätsfixes können ohne
Geschwindigkeitsgewinn sinnvoll sein. Nutzen samt Regressionstest und
Performanceauswirkung offen dokumentieren und **separat freigeben lassen**.
Dokumentationsänderungen erhalten keinen erfundenen Performancegewinn;
Nichtanwendbarkeit des Leistungs-Gates ausdrücklich begründen.

Die drei Tests sind ein Mindestvergleich, kein Beweis für Modellqualität,
Schadcodefreiheit oder fehlerfreien Langzeitbetrieb. Numerische Kernel-,
Quantisierungs-, Vision- und Kontextänderungen benötigen zusätzliche
fachliche Korrektheits-/Qualitätstests passend zum Patch.

Der Review-Bericht nennt A/B-SHAs, eingefrorenen Plan, Messreihen, Grenzen,
abgelehnte Kandidaten, Nutzenentscheidung und unabhängige Gegenprüfung.
Fehlende Belege bedeuten OFFEN/BLOCKIERT. Kein automatischer Merge oder
Deployment aufgrund einer Benchmark-Zahl; P4 und Deployment-Freigabe bleiben.
