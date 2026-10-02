# Content-Fabrik

Erzeugt auf dem VPS automatisch neue Lerneinheiten mit Claude Code (über dein Claude-Abo) und reicht sie als Pull Request ein.

```
Timer (3×/Tag) → run_batch.py → claude -p + Skill einheiten-erstellen → Prüfung → PR → Auto-Merge bei grüner CI
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

### 2. GitHub-Zugang nur für dieses Repo

Auf github.com: Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token

- Resource owner: **scrollzoll**
- Expiration: 60 Tage (deckt den Urlaub ab)
- Repository access: **Only select repositories** → `content`
- Permissions: **Contents: Read and write**, **Pull requests: Read and write** (Metadata: Read wird automatisch gesetzt)

Den Token nur im Terminal des VPS eingeben, nirgends sonst:

```bash
gh auth login --with-token     # Token einfügen, Enter, Strg+D
gh auth setup-git
git config --global user.name "Seb"
git config --global user.email "DEINE-MAIL"
```

### 3. Repo klonen (eigener Ordner nur für die Fabrik)

```bash
mkdir -p ~/scrollzoll && cd ~/scrollzoll
gh repo clone scrollzoll/content
cp content/factory/factory.env.example factory.env
```

In diesem Ordner nicht von Hand arbeiten: Die Fabrik setzt ihn vor jedem Lauf auf den Stand von `main` zurück.

### 4. Repo-Einstellungen auf GitHub (`scrollzoll/content`)

- Settings → General → Pull Requests: **Allow auto-merge** aktivieren, **Automatically delete head branches** aktivieren.
- Settings → Branches (oder Rules) → Regel für `main`: Pull Request erforderlich, **0** Freigaben, Status-Check **Validate units** erforderlich. Mit 0 Freigaben läuft Auto-Merge ohne dich durch, sobald die Prüfung grün ist.

### 5. Testen

```bash
cd ~/scrollzoll/content
DRY_RUN=1 python3 factory/run_batch.py                 # zeigt nur die Themen und den Prompt
UNITS_PER_RUN=1 MAX_RUNS_PER_DAY=99 python3 factory/run_batch.py   # ein echter Lauf mit einem Thema
```

Danach sollte auf GitHub ein Pull Request „Neue Lerneinheiten (1) …“ stehen und nach grüner Prüfung automatisch gemergt werden.

### 6. Zeitplan aktivieren

```bash
mkdir -p ~/.config/systemd/user
cp ~/scrollzoll/content/factory/systemd/scrollzoll-factory.* ~/.config/systemd/user/
which claude    # Pfad prüfen; ggf. in der .service-Datei unter Environment=PATH ergänzen
systemctl --user daemon-reload
systemctl --user enable --now scrollzoll-factory.timer
sudo loginctl enable-linger "$USER"     # Timer laufen auch ohne eingeloggte Sitzung
systemctl --user list-timers | grep scrollzoll
```

## Im Urlaub

| Was | Wie |
| --- | --- |
| Fortschritt sehen | Pull Requests in `scrollzoll/content` (GitHub-App aufs Handy) |
| Pausieren | Im Repo die Datei `factory/PAUSE` anlegen (GitHub-App: Add file); wieder löschen zum Fortsetzen |
| Hart stoppen | per SSH: `systemctl --user disable --now scrollzoll-factory.timer` |
| Protokoll | `~/.cache/scrollzoll-factory/factory.log`, Claude-Ausgaben in `~/.cache/scrollzoll-factory/runs/` |
| Menge anpassen | `~/scrollzoll/factory.env` (`UNITS_PER_RUN`, `MAX_RUNS_PER_DAY`, `CLAUDE_MODEL`) |

## Hinweise zum Abo

- Die Fabrik nutzt `claude -p`, also automatisierte Nutzung deines Abos. Beobachte in den ersten Tagen die Auslastung in den Claude-Einstellungen unter Nutzung und passe `UNITS_PER_RUN` an.
- Prüfe, dass in deinem Konto keine bezahlte Zusatznutzung aktiv ist, damit die Fabrik bei erreichtem Limit stoppt statt Kosten zu verursachen.
- Ist das Limit erreicht, beendet sich der Lauf sauber; der nächste Timer-Termin versucht es erneut.
