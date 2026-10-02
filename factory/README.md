# Content-Fabrik

Erzeugt auf dem VPS automatisch neue Lerneinheiten mit Claude Code (über dein Claude-Abo) und reicht sie als Pull Request ein.

```
Timer (4×/Tag) → run_batch.py → claude -p + Skill einheiten-erstellen → Prüfung → PR → Auto-Merge bei grüner CI
```

- Claude darf nur recherchieren, lesen, Dateien unter `units/` schreiben und das Prüfskript ausführen. Git und GitHub macht nur `run_batch.py`.
- Jede Einheit wird von einem zweiten Agenten mit frischem Kontext gegen die Quellen geprüft und danach mit `scripts/validate.py` validiert.
- Neue Einheiten haben Status `review` und erscheinen erst nach Freigabe in der App.
- Sicherungen: Tageslimit, Sperre gegen Doppelläufe, automatische 12-h-Pause nach 3 Fehlläufen, Pausenschalter `factory/PAUSE`, Stopp bei erreichtem Nutzungslimit.

## Einrichtung auf dem VPS (Ubuntu, einmalig)

### 1. Voraussetzungen

```bash
sudo apt update && sudo apt install -y git python3 python3-yaml python3-jsonschema gh
claude --version            # Claude Code installiert und mit deinem Abo angemeldet?
claude -p "Antworte nur mit: ok"   # muss ohne Rückfrage "ok" liefern
```

Falls `gh` im Ubuntu-Paket fehlt oder veraltet ist: Installationsanleitung unter https://github.com/cli/cli/blob/trunk/docs/install_linux.md.

### 2. GitHub-Zugang nur für dieses Repo (ohne bestehende Logins zu ändern)

Die Fabrik bekommt einen **eigenen** Token, der nur in ihrer Konfigurationsdatei liegt. Ein bereits eingerichteter `gh`- oder Git-Login auf dem VPS (z. B. ein anderer GitHub-Nutzer für deine Coding-Sessions) bleibt unverändert. Also **kein** `gh auth login` und kein `gh auth setup-git` für die Fabrik.

Auf github.com mit dem Konto, dem die Organisation `scrollzoll` gehört: Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token

- Resource owner: **scrollzoll**
- Expiration: 60 Tage (deckt den Urlaub ab)
- Repository access: **Only select repositories** → `content`
- Permissions: **Contents: Read and write**, **Pull requests: Read and write** (Metadata: Read wird automatisch gesetzt)

### 3. Repo klonen und Fabrik konfigurieren (eigener Ordner nur für die Fabrik)

```bash
mkdir -p ~/scrollzoll && cd ~/scrollzoll
git clone https://github.com/scrollzoll/content.git       # öffentlich, braucht keinen Login
python3 -m venv venv && venv/bin/pip install -r content/requirements.txt
cp content/factory/factory.env.example factory.env
chmod 600 factory.env
nano factory.env      # Token bei GH_TOKEN= eintragen, speichern
```

Git im Fabrik-Ordner so einstellen, dass es nur hier den Token aus `GH_TOKEN` nutzt und unter deinem Namen committet:

```bash
cd ~/scrollzoll/content
git config --local credential.helper ""
git config --local --add credential.helper '!f() { echo username=x-access-token; echo "password=$GH_TOKEN"; }; f'
git config --local user.name "Seb"
git config --local user.email "DEINE-MAIL"
```

`gh` liest `GH_TOKEN` automatisch und ignoriert dann den globalen Login. In diesem Ordner nicht von Hand arbeiten: Die Fabrik setzt ihn vor jedem Lauf auf den Stand von `main` zurück.

### 4. Repo-Einstellungen auf GitHub (`scrollzoll/content`)

- Settings → General → Pull Requests: **Allow auto-merge** aktivieren, **Automatically delete head branches** aktivieren.
- Settings → Rules → Ruleset für `main`: Pull Request erforderlich, **0** Freigaben, Status-Check **`validate`** (Quelle GitHub Actions) erforderlich, „Repository admin“ in der Bypass-Liste. Mit 0 Freigaben läuft Auto-Merge ohne dich durch, sobald die Prüfung grün ist.

### 5. Testen

Für Läufe von Hand die Konfiguration in die Shell laden:

```bash
cd ~/scrollzoll/content
set -a; . ~/scrollzoll/factory.env; set +a
GH_TOKEN="$GH_TOKEN" gh api repos/scrollzoll/content --jq .full_name    # Token funktioniert?
DRY_RUN=1 ../venv/bin/python factory/run_batch.py                       # zeigt nur Themen und Prompt
UNITS_PER_RUN=1 MAX_RUNS_PER_DAY=99 ../venv/bin/python factory/run_batch.py   # ein echter Lauf mit einem Thema
```

Danach sollte auf GitHub ein Pull Request „Neue Lerneinheiten (1) …“ stehen und nach grüner Prüfung automatisch gemergt werden.

### 6. Zeitplan aktivieren

```bash
mkdir -p ~/.config/systemd/user
cp ~/scrollzoll/content/factory/systemd/scrollzoll-factory.* ~/.config/systemd/user/
which claude    # liegt der Ordner nicht im PATH der .service-Datei, dort unter Environment=PATH ergänzen
systemctl --user daemon-reload
systemctl --user enable --now scrollzoll-factory.timer
sudo loginctl enable-linger "$USER"     # Timer laufen auch ohne eingeloggte Sitzung
systemctl --user list-timers | grep scrollzoll
systemctl --user start scrollzoll-factory.service && journalctl --user -u scrollzoll-factory -n 30 --no-pager
```

## Coding-Sessions auf demselben VPS

Für die Arbeit an `scrollzoll/app` mit Claude Code gibt es zwei saubere Wege, ohne den Fabrik-Token zu berühren:

- **Dein vorhandener GitHub-Nutzer** bekommt Zugriff auf die Organisation `scrollzoll` (Organisation → People → Invite member). Dann funktioniert alles wie bei deinen anderen Repos.
- **Zweites Konto in `gh`**: `gh auth login` erneut ausführen und das Konto hinzufügen, mit `gh auth switch` wechseln (ab gh 2.40).

## Im Urlaub

| Was | Wie |
| --- | --- |
| Fortschritt sehen | Pull Requests in `scrollzoll/content` (GitHub-App aufs Handy) |
| Pausieren | Im Repo die Datei `factory/PAUSE` anlegen (GitHub-App: Add file); wieder löschen zum Fortsetzen |
| Hart stoppen | per SSH: `systemctl --user disable --now scrollzoll-factory.timer` |
| Protokoll | `~/.cache/scrollzoll-factory/factory.log`, Claude-Ausgaben in `~/.cache/scrollzoll-factory/runs/` |
| Menge anpassen | `~/scrollzoll/factory.env` (`UNITS_PER_RUN`, `MAX_RUNS_PER_DAY`, `CLAUDE_MODEL`) |

## Mengengerüst (Max 5x)

Standard: 4 Läufe × 4 Einheiten = bis zu 16 Einheiten pro Tag. Die Warteliste (rund 470 Themen, gemischt aus Technologie, Sprachen, Allgemeinwissen und Geschichte) reicht damit mehrere Wochen; verworfene Themen verlängern das. Wird das Nutzungslimit erreicht, pausiert die Fabrik bis zum nächsten Termin, ohne Kosten.

## Hinweise zum Abo

- Die Fabrik nutzt `claude -p`, also automatisierte Nutzung deines Abos. Beobachte in den ersten Tagen die Auslastung in den Claude-Einstellungen unter Nutzung und passe `UNITS_PER_RUN` an.
- Prüfe, dass in deinem Konto keine bezahlte Zusatznutzung aktiv ist, damit die Fabrik bei erreichtem Limit stoppt statt Kosten zu verursachen.
- Ist das Limit erreicht, beendet sich der Lauf sauber; der nächste Timer-Termin versucht es erneut.
