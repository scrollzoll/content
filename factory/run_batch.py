#!/usr/bin/env python3
"""Content-Fabrik: erzeugt per Claude Code neue Lerneinheiten und öffnet einen Pull Request.

Läuft auf dem VPS per systemd-Timer (siehe factory/README.md). Ein Lauf:
  1. holt den aktuellen Stand von main, bricht ab, wenn factory/PAUSE existiert
  2. wählt UNITS_PER_RUN offene Themen aus topics/queue.yaml
  3. startet `claude -p` mit dem Skill einheiten-erstellen und eng begrenzten Werkzeugen
  4. übernimmt nur gültige, neue Dateien unter units/, prüft sie mit scripts/validate.py
  5. entfernt erledigte Themen aus der Warteliste, committet, pusht, öffnet einen PR
     und schaltet ihn auf Auto-Merge (wenn AUTO_MERGE=1)

Git und GitHub erledigt ausschließlich dieses Skript; Claude bekommt keinen Shell-Zugriff
außer auf das Prüfskript.

Einstellungen per Umgebungsvariable (Standardwerte in Klammern):
  UNITS_PER_RUN (4)  MAX_RUNS_PER_DAY (4)  CLAUDE_BIN (claude)  CLAUDE_MODEL (leer = Standard)
  CLAUDE_TIMEOUT_MIN (75)  MAX_TURNS (200)  AUTO_MERGE (1)  BASE_BRANCH (main)  DRY_RUN (0)
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
STATE_DIR = Path(os.environ.get("FACTORY_STATE_DIR", Path.home() / ".cache" / "scrollzoll-factory"))
STATE_FILE = STATE_DIR / "state.json"
LOG_FILE = STATE_DIR / "factory.log"
RUN_LOG_DIR = STATE_DIR / "runs"

UNITS_PER_RUN = int(os.environ.get("UNITS_PER_RUN", "4"))
MAX_RUNS_PER_DAY = int(os.environ.get("MAX_RUNS_PER_DAY", "4"))
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "").strip()
CLAUDE_TIMEOUT_MIN = int(os.environ.get("CLAUDE_TIMEOUT_MIN", "75"))
MAX_TURNS = int(os.environ.get("MAX_TURNS", "200"))
AUTO_MERGE = os.environ.get("AUTO_MERGE", "1") == "1"
BASE_BRANCH = os.environ.get("BASE_BRANCH", "main")
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"

RESERVATION_DAYS = 30       # Themen offener PRs nicht erneut vergeben, bis sie in main sind
MAX_REJECTIONS = 2          # danach wird ein Thema übersprungen
FAILURE_PAUSE_AFTER = 3     # so viele Fehlläufe in Folge ...
FAILURE_PAUSE_HOURS = 12    # ... führen zu einer automatischen Pause

ALLOWED_TOOLS = ",".join([
    "Read", "Glob", "Grep", "WebSearch", "WebFetch", "Agent", "Skill",
    "Edit(units/**)", "Write(units/**)",
    "Bash(python3 scripts/validate.py *)",
])
DISALLOWED_TOOLS = ",".join(["Bash(git *)", "Bash(gh *)", "Bash(rm *)", "Bash(curl *)", "Bash(wget *)"])

LIMIT_PATTERNS = re.compile(r"hit your .{0,40}limit|usage limit|rate limit|\(429\)", re.IGNORECASE)


# ---------------------------------------------------------------- Hilfsfunktionen


def interleave(queue):
    """Nach Priorität sortieren, innerhalb gleicher Priorität reihum über die Hauptthemen mischen."""
    from collections import OrderedDict
    out = []
    for prio in sorted({t.get("priority", 3) for t in queue}):
        buckets = OrderedDict()
        for t in queue:
            if t.get("priority", 3) == prio:
                buckets.setdefault(t["topic"].split("/")[0], []).append(t)
        lists = list(buckets.values())
        i = 0
        while any(lists):
            for lst in lists:
                if len(lst) > i:
                    out.append(lst[i])
            i += 1
            if all(len(lst) <= i for lst in lists):
                break
    return out

def log(msg: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def sh(*args: str, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=REPO, check=check, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.STDOUT if capture else None)


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE_FILE)


def existing_unit_ids() -> set[str]:
    return {p.stem for p in (REPO / "units").rglob("*.json")}


def load_queue() -> list[dict]:
    data = yaml.safe_load((REPO / "topics" / "queue.yaml").read_text(encoding="utf-8")) or {}
    return data.get("queue") or []


def remove_from_queue(ids: set[str]) -> None:
    """Entfernt Einträge zeilenbasiert, damit Kommentare und Format erhalten bleiben."""
    path = REPO / "topics" / "queue.yaml"
    out, skip = [], False
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        m = re.match(r"^  - id:\s*(\S+)", line)
        if m:
            skip = m.group(1) in ids
        elif skip and not line.startswith("    ") and line.strip():
            skip = False
        if not skip:
            out.append(line)
    path.write_text("".join(out), encoding="utf-8")


def build_prompt(topics: list[dict]) -> str:
    lines = [
        "/einheiten-erstellen",
        "",
        "Nutze den Skill einheiten-erstellen und erstelle je eine Lerneinheit für diese Themen.",
        f"Heutiges Datum: {date.today().isoformat()}.",
        "",
    ]
    for t in topics:
        lines.append(f"- id: {t['id']} | topic: {t['topic']} | format: {t['format']} | hint: {t.get('hint', '')}")
    lines += ["", "Schreibe nur Dateien unter units/. Beende mit der Liste ERSTELLT/VERWORFEN."]
    return "\n".join(lines)


def gh_available() -> bool:
    return shutil.which("gh") is not None


# ---------------------------------------------------------------- Hauptablauf

def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = open(STATE_DIR / "lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("übersprungen: ein anderer Lauf ist noch aktiv")
        return 0

    state = load_state()
    today = date.today().isoformat()
    now = time.time()

    paused_until = state.get("paused_until", 0)
    if paused_until > now:
        log(f"übersprungen: automatische Pause bis {datetime.fromtimestamp(paused_until):%d.%m. %H:%M}")
        return 0

    runs_today = state.get("runs", {}).get(today, 0)
    if runs_today >= MAX_RUNS_PER_DAY:
        log(f"übersprungen: Tageslimit erreicht ({runs_today}/{MAX_RUNS_PER_DAY})")
        return 0

    if not DRY_RUN and not os.environ.get("GH_TOKEN"):
        log("Fehler: GH_TOKEN fehlt (siehe factory/README.md, Schritt 3)")
        return 1

    # 1. Stand von main holen
    if not DRY_RUN:
        sh("git", "fetch", "--quiet", "origin", BASE_BRANCH)
        sh("git", "checkout", "--quiet", BASE_BRANCH)
        sh("git", "reset", "--quiet", "--hard", f"origin/{BASE_BRANCH}")
        sh("git", "clean", "-fdq", "units", "topics")
    if (REPO / "factory" / "PAUSE").exists():
        log("übersprungen: factory/PAUSE ist gesetzt")
        return 0

    # 2. Themen wählen
    have = existing_unit_ids()
    reserved = {k for k, v in state.get("reserved", {}).items() if v > now and k not in have}
    rejected = {k for k, v in state.get("rejections", {}).items() if v >= MAX_REJECTIONS}
    queue = [t for t in load_queue() if t["id"] not in have | reserved | rejected]
    topics = interleave(queue)[:UNITS_PER_RUN]
    if not topics:
        log("nichts zu tun: Warteliste leer oder alle Themen vergeben")
        return 0
    ids = [t["id"] for t in topics]
    log(f"starte Lauf {runs_today + 1}/{MAX_RUNS_PER_DAY}: {', '.join(ids)}")

    prompt = build_prompt(topics)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    branch = f"gen/{stamp}"
    if DRY_RUN:
        log("DRY_RUN: Prompt folgt, Claude wird nicht gestartet")
        print(prompt)
        return 0

    sh("git", "checkout", "--quiet", "-b", branch)
    state.setdefault("runs", {})[today] = runs_today + 1
    state["runs"] = {k: v for k, v in state["runs"].items() if k >= (date.today() - timedelta(days=14)).isoformat()}
    save_state(state)

    # 3. Claude starten
    cmd = [CLAUDE_BIN, "-p", prompt, "--output-format", "json", "--max-turns", str(MAX_TURNS),
           "--allowedTools", ALLOWED_TOOLS, "--disallowedTools", DISALLOWED_TOOLS]
    if CLAUDE_MODEL:
        cmd += ["--model", CLAUDE_MODEL]
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    run_log = RUN_LOG_DIR / f"{stamp}.json"
    try:
        proc = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True, timeout=CLAUDE_TIMEOUT_MIN * 60)
        output, code = (proc.stdout or "") + (proc.stderr or ""), proc.returncode
    except subprocess.TimeoutExpired as exc:
        output, code = f"TIMEOUT nach {CLAUDE_TIMEOUT_MIN} min\n{exc.stdout or ''}", -1
    run_log.write_text(output, encoding="utf-8")

    if code != 0 and LIMIT_PATTERNS.search(output):
        log(f"Nutzungslimit erreicht, Lauf beendet ohne Fehler (Details: {run_log.name})")
        state["runs"][today] = runs_today  # zählt nicht
        save_state(state)
        cleanup(branch)
        return 0

    # 4. Ergebnis übernehmen – nur erwartete Dateien
    changed = [l[3:].strip() for l in sh("git", "status", "--porcelain", "--untracked-files=all").stdout.splitlines()]
    accepted: list[str] = []
    for path in changed:
        p = REPO / path
        ok_path = path.startswith("units/") and path.endswith(".json") and p.stem in ids
        if not ok_path:
            log(f"WARNUNG: unerwartete Änderung verworfen: {path}")
            continue
        if not unit_is_valid(p):
            log(f"verworfen (Prüfung fehlgeschlagen): {path}")
            p.unlink(missing_ok=True)
            continue
        accepted.append(path)

    # Alles außer den übernommenen Dateien zurücksetzen
    for path in changed:
        if path in accepted:
            continue
        if tracked(path):
            sh("git", "checkout", "--quiet", "--", path, check=False)
        else:
            (REPO / path).unlink(missing_ok=True)

    done = {Path(p).stem for p in accepted}
    for t in ids:
        if t not in done:
            state.setdefault("rejections", {})[t] = state.get("rejections", {}).get(t, 0) + 1

    if not accepted:
        fails = state.get("consecutive_failures", 0) + 1
        state["consecutive_failures"] = fails
        log(f"keine gültige Einheit erzeugt (Exit {code}, Fehlläufe in Folge: {fails}, Details: {run_log.name})")
        if fails >= FAILURE_PAUSE_AFTER:
            state["paused_until"] = now + FAILURE_PAUSE_HOURS * 3600
            log(f"automatische Pause für {FAILURE_PAUSE_HOURS} h")
        save_state(state)
        cleanup(branch)
        return 1

    # 5. Warteliste, Commit, Push, PR
    remove_from_queue(done)
    sh("git", "add", "--", *accepted, "topics/queue.yaml")
    body_ids = "\n".join(f"- `{d}`" for d in sorted(done))
    rejected_now = sorted(set(ids) - done)
    msg = f"Neue Lerneinheiten: {', '.join(sorted(done))}\n\nErzeugt von der Content-Fabrik ({stamp})."
    sh("git", "commit", "--quiet", "-m", msg)
    sh("git", "push", "--quiet", "-u", "origin", branch)

    if gh_available():
        body = (f"Automatisch erzeugt von der Content-Fabrik.\n\n**Neu ({len(done)}):**\n{body_ids}\n\n"
                + (f"**Verworfen:** {', '.join(rejected_now)}\n\n" if rejected_now else "")
                + "Alle Einheiten haben Status `review` und erscheinen erst nach Freigabe in der App.")
        pr = sh("gh", "pr", "create", "--base", BASE_BRANCH, "--head", branch,
                "--title", f"Neue Lerneinheiten ({len(done)}) – {stamp}", "--body", body, check=False)
        log(f"PR: {pr.stdout.strip().splitlines()[-1] if pr.stdout else 'Fehler'}")
        if AUTO_MERGE and pr.returncode == 0:
            m = sh("gh", "pr", "merge", branch, "--auto", "--squash", "--delete-branch", check=False)
            if m.returncode != 0:
                log(f"WARNUNG: Auto-Merge nicht möglich: {m.stdout.strip()[:200]}")
    else:
        log("WARNUNG: gh nicht installiert, Branch gepusht ohne PR")

    state.setdefault("reserved", {}).update({d: now + RESERVATION_DAYS * 86400 for d in done})
    state["reserved"] = {k: v for k, v in state["reserved"].items() if v > now}
    state["consecutive_failures"] = 0
    save_state(state)
    sh("git", "checkout", "--quiet", BASE_BRANCH)
    log(f"fertig: {len(done)} neu, {len(rejected_now)} verworfen")
    return 0


def tracked(path: str) -> bool:
    return sh("git", "ls-files", "--error-unmatch", path, check=False).returncode == 0


def unit_is_valid(p: Path) -> bool:
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if set(data.get("locales", {})) != {"de", "en"} or data.get("status") != "review":
        return False
    res = subprocess.run([sys.executable, "scripts/validate.py", str(p)], cwd=REPO, text=True, capture_output=True)
    return res.returncode == 0


def cleanup(branch: str) -> None:
    sh("git", "checkout", "--quiet", "--", ".", check=False)
    sh("git", "clean", "-fdq", "units", check=False)
    sh("git", "checkout", "--quiet", BASE_BRANCH, check=False)
    sh("git", "branch", "-D", branch, check=False)


if __name__ == "__main__":
    sys.exit(main())
