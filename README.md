# Scrollzoll Content

Offene Microlearning-Datenbank: kurze Lerneinheiten (Fakten + Quiz, Karteikarten, Einzelfakten) auf Deutsch und Englisch, jede mit Quellen. Die Einheiten speisen die App Scrollzoll und stehen allen offen, auch für eigene Projekte und KI-Agents.

## Lizenz

- **Lerneinheiten (`units/`) und Themenlisten (`topics/`):** [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/deed.de). Namensnennung: „Scrollzoll Content-Beitragende“ mit Link auf dieses Repo.
- **Schema und Skripte (`schema/`, `scripts/`):** MIT.

Den vollständigen Lizenztext legst du beim Anlegen des Repos über GitHubs Lizenzauswahl an (siehe `LICENSE.md`).

## Aufbau

```
schema/learning-unit.schema.json   Format einer Lerneinheit (JSON Schema)
units/<thema>/<id>.json            eine Datei pro Einheit
topics/taxonomy.yaml               erlaubte Hauptthemen
topics/queue.yaml                  Warteliste offener Themen für Beitragende
scripts/validate.py                Prüft Schema, Quellen, Quiz-Logik, IDs
factory/                           Content-Fabrik: automatische Erstellung per Claude Code (siehe factory/README.md)
.claude/skills/einheiten-erstellen Skill zum Erstellen von Einheiten
```

## Prüfen

```bash
pip install -r requirements.txt
python scripts/validate.py
```

Jeder Pull Request wird automatisch geprüft. Fehler blockieren, Warnungen nicht.

## Mitmachen

Siehe [CONTRIBUTING.md](CONTRIBUTING.md). Der einfachste Weg ist das Spenden-Plugin für die Claude-App (Repo `plugin`): Es erstellt Einheiten aus der Warteliste und reicht sie automatisch ein.

## Status einer Einheit

| Status | Bedeutung |
| --- | --- |
| `draft` | in Arbeit |
| `review` | wartet auf Prüfung |
| `approved` | freigegeben, erscheint in der App |
| `flagged` | in der App als falsch gemeldet, ausgeblendet bis zur erneuten Prüfung |
| `retired` | zurückgezogen |
