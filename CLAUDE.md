# CLAUDE.md – content

Dieses Repo ist die offene Microlearning-Datenbank von Scrollzoll. Es enthält nur Daten, Schema und Prüfskripte, keinen App-Code.

## Wichtig
- Format jeder Einheit: `schema/learning-unit.schema.json`. Schema-Änderungen nur mit Erhöhung von `schema_version` und Migration aller Einheiten.
- Nach jeder Änderung an Einheiten oder Schema: `python scripts/validate.py` muss mit 0 Fehlern enden.
- Regeln für Inhalte: `CONTRIBUTING.md`. Vor allem: jede Aussage mit Quelle, eigene Worte, Deutsch und Englisch gleich aufgebaut.
- Neue Einheiten immer mit `status: "review"`, nie direkt `approved`.
- Lizenz der Daten: CC BY-SA 4.0. Nichts aus Quellen mit NC- oder unklarer Lizenz übernehmen.

## Beim Erstellen von Einheiten
- Fakten nur aus Quellen, die du tatsächlich geöffnet hast. Unsicheres weglassen.
- Zahlen, Jahreszahlen und Namen gegen die Quelle prüfen.
- Quizfragen: genau eine richtige Antwort, `answer_index` zählt ab 0.
- Dateiname = `id` + `.json`, Ordner = erste Ebene von `topic`.
