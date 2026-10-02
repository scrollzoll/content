#!/usr/bin/env python3
"""Prüft alle Lerneinheiten unter units/ gegen das Schema und gegen inhaltliche Regeln.

Aufruf:  python scripts/validate.py            (alle Einheiten)
         python scripts/validate.py pfad.json   (einzelne Dateien)
Exit-Code 0 = alles in Ordnung, 1 = Fehler gefunden. Warnungen brechen nicht ab.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema" / "learning-unit.schema.json"
TAXONOMY_PATH = ROOT / "topics" / "taxonomy.yaml"
TARGET_LOCALES = {"de", "en"}


def load_units(paths: list[str]) -> list[Path]:
    if paths:
        return [Path(p).resolve() for p in paths]
    return sorted((ROOT / "units").rglob("*.json"))


def check_unit(path: Path, data: dict, validator: Draft202012Validator, top_topics: set[str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        errors.append(f"Schema: {loc}: {err.message}")
    if errors:
        return errors, warnings  # Folgeprüfungen setzen ein gültiges Schema voraus

    if path.stem != data["id"]:
        errors.append(f"Dateiname '{path.name}' passt nicht zur id '{data['id']}'")

    top = data["topic"].split("/")[0]
    if top_topics and top not in top_topics:
        errors.append(f"Thema '{top}' fehlt in topics/taxonomy.yaml")

    source_ids = [s["id"] for s in data["sources"]]
    if len(source_ids) != len(set(source_ids)):
        errors.append("Doppelte Quellen-IDs")

    missing = TARGET_LOCALES - set(data["locales"])
    if missing:
        warnings.append(f"Sprache fehlt: {', '.join(sorted(missing))}")

    fmt = data["format"]
    used_sources: set[str] = set()
    for lang, loc in data["locales"].items():
        facts, quiz, cards = loc.get("facts", []), loc.get("quiz", []), loc.get("cards", [])
        if fmt == "facts_quiz" and not (facts and quiz):
            errors.append(f"[{lang}] facts_quiz braucht facts und quiz")
        if fmt == "flashcards" and not cards:
            errors.append(f"[{lang}] flashcards braucht cards")
        if fmt == "single_fact" and len(facts) != 1:
            errors.append(f"[{lang}] single_fact braucht genau einen Fakt")
        for i, fact in enumerate(facts):
            for sid in fact["source_ids"]:
                used_sources.add(sid)
                if sid not in source_ids:
                    errors.append(f"[{lang}] facts[{i}] verweist auf unbekannte Quelle '{sid}'")
        for i, q in enumerate(quiz):
            if q["answer_index"] >= len(q["options"]):
                errors.append(f"[{lang}] quiz[{i}] answer_index außerhalb der Optionen")

    # Sprachfassungen sollen gleich aufgebaut sein
    shapes = {lang: (len(l.get("facts", [])), len(l.get("quiz", [])), len(l.get("cards", []))) for lang, l in data["locales"].items()}
    if len(set(shapes.values())) > 1:
        warnings.append(f"Sprachfassungen unterschiedlich lang: {shapes}")

    if fmt == "facts_quiz":
        unused = set(source_ids) - used_sources
        if unused:
            warnings.append(f"Quellen ohne Verwendung: {', '.join(sorted(unused))}")

    return errors, warnings


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    top_topics: set[str] = set()
    if TAXONOMY_PATH.exists():
        top_topics = set((yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8")) or {}).get("topics", {}).keys())

    paths = load_units(sys.argv[1:])
    if not paths:
        print("Keine Einheiten gefunden.")
        return 0

    seen_ids: dict[str, Path] = {}
    total_errors = 0
    for path in paths:
        rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"FEHLER {rel}: kein gültiges JSON ({exc})")
            total_errors += 1
            continue

        errors, warnings = check_unit(path, data, validator, top_topics)
        uid = data.get("id")
        if uid in seen_ids:
            errors.append(f"id '{uid}' doppelt (auch in {seen_ids[uid].name})")
        elif uid:
            seen_ids[uid] = path

        for w in warnings:
            print(f"WARNUNG {rel}: {w}")
        for e in errors:
            print(f"FEHLER  {rel}: {e}")
        if not errors:
            print(f"OK      {rel}")
        total_errors += len(errors)

    print(f"\n{len(paths)} Einheit(en) geprüft, {total_errors} Fehler.")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
