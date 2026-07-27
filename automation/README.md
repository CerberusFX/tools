# Typefully -> Telegram Auto-Poster

Postet jeden auf X veröffentlichten Thread automatisch (Text + Titelbild) in deinen Telegram-Kanal `t.me/CerberusFXTrading`.

## Warum so und nicht über X direkt?

X hat keine stabile kostenlose API mehr für Drittanbieter-Automatisierung. Typefully hat den kompletten Thread-Inhalt aber ohnehin schon vorliegen, bevor/während er auf X veröffentlicht wird — das Skript liest also von dort, nicht von X selbst.

## Setup (einmalig, ca. 10 Minuten)

### 1. Python-Pakete installieren
```bash
pip install requests python-dotenv
```

### 2. Telegram-Bot anlegen
1. In Telegram den Account **@BotFather** öffnen
2. `/newbot` senden, Namen vergeben
3. Den zurückgegebenen **Bot-Token** kopieren (sieht aus wie `123456789:AAE...`)

### 3. Bot in den Kanal einladen
1. In deinem Kanal `t.me/CerberusFXTrading` → Kanal-Einstellungen → Administratoren
2. Den neuen Bot als Admin hinzufügen
3. Mindestens die Berechtigung **"Nachrichten senden"** aktivieren

### 4. Typefully API-Key holen
1. In Typefully: Settings → Integrations → API
2. Key erzeugen/kopieren

### 5. Konfiguration eintragen
```bash
cp .env.example .env
```
Dann `.env` öffnen und die vier Werte eintragen:
- `TYPEFULLY_API_KEY`
- `TYPEFULLY_SOCIAL_SET_ID` (bei dir: `322773`)
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID` (bei öffentlichen Kanälen reicht `@CerberusFXTrading`)

### 6. Testlauf (schickt noch nichts an Telegram, zeigt nur an was passieren würde)
```bash
python typefully_to_telegram.py --dry-run
```

Wenn die Ausgabe passt, einen echten Lauf machen:
```bash
python typefully_to_telegram.py
```

Danach in deinem Telegram-Kanal nachschauen, ob die Nachricht angekommen ist.

## Automatisch laufen lassen

Das Skript muss regelmäßig ausgeführt werden, damit neu veröffentlichte Threads zeitnah übertragen werden. Alle 15–30 Minuten reicht völlig.

### Linux / Mac (Cron)
```bash
crontab -e
```
Zeile hinzufügen:
```
*/15 * * * * cd /pfad/zu/diesem/ordner && /usr/bin/python3 typefully_to_telegram.py >> run.log 2>&1
```

### Windows (Task Scheduler)
1. Task-Planer öffnen → "Aufgabe erstellen"
2. Trigger: alle 15 Minuten wiederholen
3. Aktion: Programm starten → `python.exe`, Argument: `C:\pfad\typefully_to_telegram.py`
4. Starten in: der Ordner, in dem das Skript liegt

## Wie es funktioniert

1. Fragt Typefully nach den zuletzt **veröffentlichten** Drafts (nicht "geplant" — erst wenn der Thread wirklich live ist)
2. Für jeden noch unbekannten Thread: baut eine Telegram-Nachricht aus allen Tweet-Texten (durch Trennlinien verbunden) + hängt das Titelbild aus Tweet 1 an, falls vorhanden
3. Sendet das an den Kanal
4. Merkt sich die `draft_id` in `posted_ids.json`, damit nichts doppelt gepostet wird

## Wichtige Grenzen (ehrlich, nicht schöngeredet)

- **Kein Hintergrunddienst inklusive**: Das Skript muss auf deinem eigenen Rechner/Server per Cron oder Task Scheduler laufen. Es läuft nicht "von selbst" ohne einen Rechner, der eingeschaltet ist.
- **Verzögerung**: Bei 15-Minuten-Takt kann die Telegram-Nachricht bis zu 15 Minuten nach der X-Veröffentlichung kommen — kein Problem für deinen Use-Case, aber kein Echtzeit-Mirror.
- **Telegram-Zeichenlimit**: Nachrichten mit Bild sind auf 1024 Zeichen Caption begrenzt, ohne Bild auf 4096 Zeichen. Bei sehr langen 9-10-Tweet-Threads mit Bild wird die Caption ggf. gekürzt (`text[:1024]`) — reiner Text ohne Bild passt praktisch immer komplett rein.
- **posted_ids.json nicht löschen**: Sonst postet das Skript beim nächsten Lauf alle zuletzt veröffentlichten Threads erneut.
