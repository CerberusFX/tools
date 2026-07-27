#!/usr/bin/env python3
"""
CerberusFX — Typefully → Telegram Auto-Poster
================================================

Was das Skript tut:
  1. Fragt Typefully nach den zuletzt VERÖFFENTLICHTEN Drafts (nicht "scheduled" —
     erst wenn der Thread wirklich live auf X ist, wird er weitergegeben).
  2. Für jeden Draft, den es noch nicht kennt (siehe posted_ids.json), baut es
     eine Telegram-Nachricht: den kompletten Thread-Text (alle Tweets zu einer
     Nachricht zusammengefügt) + das Thumbnail-Bild aus Tweet 1, falls vorhanden.
  3. Postet das 1:1 in deinen Telegram-Kanal.
  4. Merkt sich die draft_id in posted_ids.json, damit nichts doppelt gepostet wird.

Warum nicht direkt von X lesen?
  X hat keine stabile kostenlose API mehr für Drittanbieter. Typefully hat den
  kompletten Thread-Inhalt aber ohnehin schon vorher lokal vorliegen — das ist
  die zuverlässigere Quelle.

Voraussetzungen:
  pip install requests

Umgebungsvariablen (siehe .env.example):
  TYPEFULLY_API_KEY   -> Typefully API-Key (Settings -> Integrations -> API)
  TYPEFULLY_SOCIAL_SET_ID -> deine Social-Set-ID (bei dir: 322773)
  TELEGRAM_BOT_TOKEN  -> Bot-Token von @BotFather
  TELEGRAM_CHAT_ID    -> deine Kanal-ID, z.B. "@CerberusFXTrading" oder "-100xxxxxxxxxx"

Einrichtung (einmalig):
  1. Bot bei @BotFather in Telegram anlegen -> Token kopieren
  2. Bot als Admin in deinen Kanal t.me/CerberusFXTrading einladen
     (er braucht "Nachrichten senden"-Rechte)
  3. Kanal-Chat-ID herausfinden: einfach @-Handle verwenden, z.B. "@CerberusFXTrading"
     (klappt nur bei öffentlichen Kanälen; sonst numerische ID über
     https://api.telegram.org/bot<TOKEN>/getUpdates ermitteln, nachdem der Bot
     eine Testnachricht im Kanal bekommen hat)
  4. .env Datei ausfüllen (siehe .env.example)
  5. Einmal manuell testen:  python typefully_to_telegram.py --dry-run
  6. Wenn alles passt, per Cron/Task Scheduler alle 15-30 Min laufen lassen:
       */15 * * * * cd /pfad/zum/skript && python3 typefully_to_telegram.py

Cron-Beispiel (Linux/Mac, crontab -e):
  */15 * * * * cd /home/user/cerberusfx-bot && /usr/bin/python3 typefully_to_telegram.py >> run.log 2>&1

Windows Task Scheduler:
  Trigger: alle 15 Minuten
  Aktion:  python.exe C:\\pfad\\typefully_to_telegram.py
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_FILE = SCRIPT_DIR / "posted_ids.json"

TYPEFULLY_API_BASE = "https://api.typefully.com/v2"
TELEGRAM_API_BASE = "https://api.telegram.org"

# Wie viele zuletzt veröffentlichte Drafts pro Lauf geprüft werden.
CHECK_LIMIT = 10


def load_config():
    """Liest Konfiguration aus Umgebungsvariablen (per .env oder System)."""
    # Optional: .env Datei laden, falls python-dotenv installiert ist.
    try:
        from dotenv import load_dotenv
        load_dotenv(SCRIPT_DIR / ".env")
    except ImportError:
        pass

    cfg = {
        "typefully_api_key": os.environ.get("TYPEFULLY_API_KEY"),
        "social_set_id": os.environ.get("TYPEFULLY_SOCIAL_SET_ID"),
        "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN"),
        "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID"),
    }

    missing = [k for k, v in cfg.items() if not v]
    if missing:
        print(f"FEHLER: Fehlende Umgebungsvariablen: {', '.join(missing)}")
        print("Siehe .env.example fuer die noetigen Werte.")
        sys.exit(1)

    return cfg


def load_posted_ids():
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text()))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def save_posted_ids(ids):
    STATE_FILE.write_text(json.dumps(sorted(ids), indent=2))


# ---------------------------------------------------------------------------
# Typefully
# ---------------------------------------------------------------------------

def typefully_headers(cfg):
    return {
        "X-API-Key": cfg["typefully_api_key"],
        "Content-Type": "application/json",
    }


def get_recent_published_drafts(cfg):
    """Holt die zuletzt veroeffentlichten Drafts fuer das Social Set."""
    url = f"{TYPEFULLY_API_BASE}/social-sets/{cfg['social_set_id']}/drafts"
    params = {
        "status": "published",
        "order_by": "-published_at",
        "limit": CHECK_LIMIT,
    }
    resp = requests.get(url, headers=typefully_headers(cfg), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_draft_detail(cfg, draft_id):
    """Holt den vollen Draft-Inhalt inkl. aller Tweet-Texte."""
    url = f"{TYPEFULLY_API_BASE}/social-sets/{cfg['social_set_id']}/drafts/{draft_id}"
    params = {"exclude_comment_markers": "true"}
    resp = requests.get(url, headers=typefully_headers(cfg), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_media_url(cfg, media_id):
    """Holt die oeffentliche Bild-URL zu einer media_id (fuer Thumbnails)."""
    url = f"{TYPEFULLY_API_BASE}/social-sets/{cfg['social_set_id']}/media/{media_id}"
    resp = requests.get(url, headers=typefully_headers(cfg), timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("media_urls", {}).get("large") or data.get("media_urls", {}).get("original")


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def telegram_send_photo(cfg, photo_url, caption):
    """Sendet ein Bild mit Bildunterschrift (max. 1024 Zeichen Caption)."""
    url = f"{TELEGRAM_API_BASE}/bot{cfg['telegram_bot_token']}/sendPhoto"
    payload = {
        "chat_id": cfg["telegram_chat_id"],
        "photo": photo_url,
        "caption": caption[:1024],
        "parse_mode": "HTML",
    }
    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def telegram_send_message(cfg, text):
    """Sendet reinen Text (Telegram-Limit: 4096 Zeichen pro Nachricht)."""
    url = f"{TELEGRAM_API_BASE}/bot{cfg['telegram_bot_token']}/sendMessage"
    payload = {
        "chat_id": cfg["telegram_chat_id"],
        "text": text[:4096],
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Thread -> Telegram-Nachricht zusammenbauen
# ---------------------------------------------------------------------------

def escape_html(text):
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build_telegram_text(draft):
    """
    Baut aus allen X-Posts eines Drafts einen zusammenhaengenden Text fuer
    Telegram. Jeder Tweet wird durch eine Leerzeile getrennt, damit die
    Struktur des Threads erkennbar bleibt.
    """
    posts = draft.get("platforms", {}).get("x", {}).get("posts", [])
    parts = []
    for post in posts:
        text = post.get("text", "").strip()
        if text:
            parts.append(escape_html(text))
    body = "\n\n\u2014\u2014\u2014\n\n".join(parts)

    title = draft.get("draft_title") or "Neuer Thread"
    header = f"<b>{escape_html(title)}</b>\n\n"

    published_url = (
        draft.get("x_published_url")
        or ""
    )
    footer = ""
    if published_url:
        footer = f"\n\n\U0001F517 Ganzer Thread auf X: {published_url}"

    return header + body + footer


def find_first_media_id(draft):
    posts = draft.get("platforms", {}).get("x", {}).get("posts", [])
    for post in posts:
        media_ids = post.get("media_ids") or []
        if media_ids:
            return media_ids[0]
    return None


# ---------------------------------------------------------------------------
# Hauptlogik
# ---------------------------------------------------------------------------

def run(dry_run=False):
    cfg = load_config()
    posted_ids = load_posted_ids()

    print("Pruefe Typefully auf neu veroeffentlichte Threads ...")
    drafts = get_recent_published_drafts(cfg)

    # API-Antwortform kann {"drafts": [...]} oder direkt eine Liste sein --
    # beide Faelle abfangen.
    draft_list = drafts.get("drafts", drafts) if isinstance(drafts, dict) else drafts

    new_count = 0
    for item in draft_list:
        draft_id = item.get("id") or item.get("draft_id")
        if draft_id is None:
            continue
        if str(draft_id) in posted_ids:
            continue

        print(f"  -> Neuer veroeffentlichter Thread gefunden: {draft_id}")
        detail = get_draft_detail(cfg, draft_id)

        # Nur tatsaechlich veroeffentlichte X-Posts weitergeben.
        if detail.get("status") != "published":
            continue

        text = build_telegram_text(detail)
        media_id = find_first_media_id(detail)

        if dry_run:
            print("  [DRY RUN] Wuerde folgendes an Telegram senden:")
            print("  " + "-" * 60)
            print(text)
            print("  " + "-" * 60)
            if media_id:
                print(f"  [DRY RUN] + Bild (media_id={media_id})")
        else:
            try:
                if media_id:
                    photo_url = get_media_url(cfg, media_id)
                    if photo_url:
                        telegram_send_photo(cfg, photo_url, text)
                    else:
                        telegram_send_message(cfg, text)
                else:
                    telegram_send_message(cfg, text)
                print(f"  OK: Draft {draft_id} an Telegram gesendet.")
            except requests.HTTPError as e:
                print(f"  FEHLER beim Senden von Draft {draft_id}: {e}")
                print(f"  Response: {e.response.text if e.response is not None else 'n/a'}")
                continue

        posted_ids.add(str(draft_id))
        new_count += 1

        # Kleine Pause zwischen mehreren Nachrichten, um Telegram-Rate-Limits
        # nicht zu triggern.
        time.sleep(2)

    if not dry_run:
        save_posted_ids(posted_ids)

    if new_count == 0:
        print("Keine neuen veroeffentlichten Threads seit dem letzten Lauf.")
    else:
        print(f"Fertig. {new_count} neue Thread(s) verarbeitet.")


def main():
    parser = argparse.ArgumentParser(description="Typefully -> Telegram Auto-Poster")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Zeigt nur an, was gepostet wuerde, ohne wirklich an Telegram zu senden.",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
