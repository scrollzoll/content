# Beitragen

Danke, dass du mithilfst! Gute Lerneinheiten sind kurz, stimmen nachweislich und sind in eigenen Worten geschrieben.

## Regeln für jede Einheit

1. **Jeder Fakt hat mindestens eine Quelle** (`source_ids`). Bevorzugt Primärquellen: Standards (RFC, ISO, NIST), offizielle Dokumentation, Fachbücher, Wikipedia nur ergänzend.
2. **Eigene Worte.** Keine Sätze aus Quellen kopieren. Ausnahme: kurze Begriffe und Fachausdrücke.
3. **Deutsch und Englisch**, inhaltlich gleich aufgebaut (gleiche Anzahl Fakten, Fragen, Karten).
4. **Kurz:** Fakten bis 280 Zeichen, Bearbeitungszeit 30 Sekunden bis 5 Minuten.
5. **Quiz fair:** eine eindeutig richtige Antwort, plausible falsche Optionen, Erklärung zur richtigen Antwort.
6. **Keine NC-Quellen übernehmen.** Inhalte aus Quellen mit „nicht kommerziell“ oder ohne klare Lizenz dürfen nur als Beleg dienen, nie übernommen werden.
7. **Keine Gesundheitsratschläge, keine Inhalte für Kinder**, solange diese Themen auf `later` stehen.
8. **KI-Unterstützung angeben:** `provenance.created_by` = `ai` oder `ai_human_edited` und `provenance.model`.

## Ablauf

1. Thema aus `topics/queue.yaml` wählen (oder neues vorschlagen).
2. Datei `units/<hauptthema>/<id>.json` anlegen, `status: "review"`.
3. `python scripts/validate.py` lokal ausführen.
4. Pull Request öffnen. Die automatische Prüfung läuft, danach folgt die Zweitprüfung der Fakten.

## Fehler melden

Falsche Einheit gefunden? Am schnellsten in der App über „Als falsch melden“, sonst per Issue mit der Vorlage „Fehler in einer Einheit“.
