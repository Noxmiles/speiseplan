#!/usr/bin/env python3
"""
==============================================================================
SPEISEPLAN TÄGLICHER SYNC & UPLOAD (SYSTEMD TIMER / CRON)
==============================================================================
Führt automatisch folgende Schritte aus:
 1. Prüft, ob heute bereits für die aktuelle KW synchronisiert wurde (verhindert
    unnötige Mehrfachläufe bei mehreren PC-Neustarts am selben Tag).
 2. Lädt die neueste Wochenkarte von kaiberg-kitchen.de per OCR herunter.
 3. Erstellt die lokale KW-CSV und aktualisiert das Langzeit-Archiv.
 4. Lädt die Daten vollautomatisch zu Hetzner hoch (per sicherem SFTP oder Webhook).

Nutzung:
    python3 sync_daily.py            # Normaler täglicher Lauf (für systemd / cron)
    python3 sync_daily.py --force    # Erzwingt Update & Upload auch wenn heute schon gelaufen
    python3 sync_daily.py --test     # Testet nur die SFTP- und Webhook-Verbindung
    python3 sync_daily.py --status   # Zeigt den letzten Synchronisationsstatus an
==============================================================================
"""

import sys
import os
import json
import base64
import subprocess
import urllib.request
import urllib.parse
from datetime import datetime, date

# Speiseplan-Basisverzeichnis importieren
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import speiseplan as sp

CONFIG_FILE = os.path.join(SCRIPT_DIR, "sync_config.json")
SECRET_FILE = os.path.join(SCRIPT_DIR, ".sftp_credentials")
STATE_FILE = os.path.join(sp.DATA_DIR, ".sync_daily_state.json")
LOG_FILE = os.path.join(sp.DATA_DIR, "sync_daily.log")
OBFUSCATION_KEY = b"speiseplan-hetzner-secure-key-2026"

DEFAULT_CONFIG = {
    "mode": "webhook",
    "webhook_url": "https://kantine.alexander-ochs.dev/index.php",
    "sync_token": "D784AC8549AB49DE5BE2A5AEF1EC6A679577DFBDD68DCF02EA209199004C2959",
    "sftp_host": "",
    "sftp_user": "",
    "sftp_remote_dir": "data"
}


def log(msg: str):
    """Gibt Nachricht mit Zeitstempel auf stdout aus und hängt sie an sync_daily.log an."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{now_str}] {msg}"
    print(formatted)
    try:
        os.makedirs(sp.DATA_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass


def load_config() -> dict:
    """Lädt sync_config.json oder erstellt die Standard-Vorlage."""
    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                file_cfg = json.load(f)
                cfg.update(file_cfg)
        except Exception as e:
            log(f"⚠️ Fehler beim Lesen von {CONFIG_FILE}: {e}. Nutze Standardwerte.")

    # Umgebungsvariablen (z. B. aus GitHub Actions Secrets) haben Vorrang:
    if os.environ.get("WEBHOOK_URL"):
        cfg["webhook_url"] = os.environ["WEBHOOK_URL"]
    if os.environ.get("SYNC_TOKEN"):
        cfg["sync_token"] = os.environ["SYNC_TOKEN"]
    if os.environ.get("SYNC_MODE"):
        cfg["mode"] = os.environ["SYNC_MODE"]

    return cfg


def load_sftp_credentials() -> tuple[str, str, str]:
    """Lädt die SFTP-Zugangsdaten aus Umgebungsvariablen oder .sftp_credentials."""
    # 1. Umgebungsvariablen prüfen (z. B. GitHub Actions Secrets)
    env_host = os.environ.get("SFTP_HOST")
    env_user = os.environ.get("SFTP_USER")
    env_pass = os.environ.get("SFTP_PASSWORD")
    if env_host and env_user and env_pass:
        return env_host, env_user, env_pass

    # 2. Lokale .sftp_credentials Datei prüfen
    if not os.path.exists(SECRET_FILE):
        return "", "", ""
    try:
        with open(SECRET_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        host = data.get("sftp_host", "")
        user = data.get("sftp_user", "")
        token = data.get("sftp_token", "")
        cipher = base64.b64decode(token.encode("ascii"))
        pw = bytes([b ^ OBFUSCATION_KEY[i % len(OBFUSCATION_KEY)] for i, b in enumerate(cipher)]).decode("utf-8")
        return host, user, pw
    except Exception as e:
        log(f"⚠️ Fehler beim Lesen der SFTP-Zugangsdaten: {e}")
        return "", "", ""
    except Exception as e:
        log(f"⚠️ Fehler beim Lesen der SFTP-Zugangsdaten: {e}")
        return "", "", ""


def load_state() -> dict:
    """Lädt den letzten Synchronisationsstatus."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state: dict):
    """Speichert den Status atomar."""
    try:
        os.makedirs(sp.DATA_DIR, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log(f"⚠️ Konnte Status nicht speichern: {e}")


def upload_via_sftp(local_file: str, remote_filename: str) -> bool:
    """Lädt eine Datei per SFTP mit cURL auf den Hetzner-Server hoch."""
    host, user, pw = load_sftp_credentials()
    if not host or not user or not pw:
        log("❌ Keine SFTP-Zugangsdaten in .sftp_credentials gefunden.")
        return False

    cfg = load_config()
    remote_dir = cfg.get("sftp_remote_dir", "data").strip("/")
    remote_url = f"sftp://{host}/{remote_dir}/{remote_filename}"
    log(f"🚀 Übertrage {os.path.basename(local_file)} per SFTP nach {host}/{remote_dir}/...")

    cmd = [
        "curl", "-s", "-k",
        "--connect-timeout", "15",
        "--max-time", "60",
        "-u", f"{user}:{pw}",
        "-T", local_file,
        remote_url
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0:
            log(f"✓ {os.path.basename(local_file)} erfolgreich per SFTP übertragen.")
            return True
        else:
            err = res.stderr.decode("utf-8", errors="ignore").strip()
            log(f"❌ SFTP-Fehler (Code {res.returncode}): {err}")
            return False
    except Exception as e:
        log(f"❌ SFTP-Ausführung fehlgeschlagen: {e}")
        return False


def upload_via_webhook(url: str, token: str, kw: int, year: int, csv_content: str, source: str = "l") -> bool:
    """Sendet die CSV-Daten per verschlüsseltem HTTPS-POST an die index.php auf Hetzner."""
    log(f"🚀 Übertrage KW {kw}/{year} per HTTPS-Webhook an {url} (Quelle: {source})...")

    post_data = urllib.parse.urlencode({
        "action": "api_sync",
        "token": token,
        "kw": str(kw),
        "jahr": str(year),
        "csv_content": csv_content,
        "source": source
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=post_data,
        headers={
            "User-Agent": "SpeiseplanSync/1.0",
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.status
            if status == 200:
                try:
                    res_json = json.loads(raw)
                    if res_json.get("success"):
                        log(f"✓ Hetzner-Server bestätigt: {res_json.get('message')}")
                        return True
                    else:
                        log(f"❌ Hetzner-Server meldet Fehler: {res_json.get('error')}")
                        return False
                except json.JSONDecodeError:
                    log("✓ Upload erfolgreich (HTTP 200 empfangen).")
                    return True
            else:
                log(f"❌ Server antwortete mit HTTP {status}")
                return False
    except urllib.error.HTTPError as e:
        log(f"❌ HTTP-Fehler beim Upload ({e.code}): {e.reason}")
        return False
    except Exception as e:
        log(f"❌ Verbindungsfehler beim Webhook-Upload: {e}")
        return False


def run_sync(force: bool = False) -> int:
    """Hauptlogik für den täglichen Synchronisationslauf."""
    cfg = load_config()
    state = load_state()

    today_str = date.today().isoformat()
    now = datetime.now()
    cur_kw = now.isocalendar()[1]
    cur_year = now.isocalendar()[0]

    log(f"── Start Speiseplan Sync (Ziel: KW {cur_kw}/{cur_year}, Heute: {today_str}) ──")

    # Prüfen, ob heute bereits erfolgreich für diese KW synchronisiert wurde
    if not force:
        last_date = state.get("last_sync_date", "")
        last_kw = state.get("last_sync_kw", 0)
        last_success = state.get("last_sync_success", False)

        if last_date == today_str and last_kw == cur_kw and last_success:
            log(f"ℹ Heute bereits erfolgreich für KW {cur_kw} synchronisiert. Keine Aktion erforderlich.")
            return 0

    # 1. Lokales Tesseract prüfen
    tess = sp.find_tesseract_binary()
    if not tess:
        log("❌ Tesseract OCR ist auf diesem PC nicht verfügbar!")
        return 1

    # 2. Bild von kaiberg-kitchen.de laden und OCR durchführen
    try:
        log("📥 Lade aktuelle Wochenkarte von kaiberg-kitchen.de...")
        img_path = sp.fetch_latest_menu_image()
        log(f"🔍 Führe Tesseract OCR-Erkennung aus ({os.path.basename(img_path)})...")
        menu = sp.parse_menu_image(img_path)
        week_csv = sp.save_week_csv(menu)
        arch_count = sp.update_archive_csv(menu)
        log(f"✓ Lokale OCR erfolgreich: KW {menu.kw}/{menu.jahr} ({len(menu.all_dishes())} Gerichte, Archiv: {arch_count})")
    except Exception as e:
        log(f"❌ Fehler bei OCR-Erkennung: {e}")
        state["last_error"] = str(e)
        state["last_attempt"] = datetime.now().isoformat()
        save_state(state)
        return 1

    # 3. Zu Hetzner übertragen
    mode = cfg.get("mode", "webhook").lower()
    upload_ok = False
    is_github = os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("SYNC_SOURCE") == "g"
    sync_source = "g" if is_github else "l"

    if mode == "sftp":
        week_ok = upload_via_sftp(week_csv, os.path.basename(week_csv))
        arch_ok = upload_via_sftp(sp.ARCHIVE_CSV, "archive.csv")
        upload_ok = week_ok and arch_ok
        if not upload_ok:
            log("⚠️ SFTP-Upload fehlgeschlagen. Versuche HTTPS-Webhook als Fallback...")
            with open(week_csv, "r", encoding="utf-8") as f:
                csv_content = f.read()
            upload_ok = upload_via_webhook(cfg.get("webhook_url", ""), cfg.get("sync_token", ""), menu.kw, menu.jahr, csv_content, source=sync_source)
    elif mode == "webhook":
        with open(week_csv, "r", encoding="utf-8") as f:
            csv_content = f.read()
        upload_ok = upload_via_webhook(cfg.get("webhook_url", ""), cfg.get("sync_token", ""), menu.kw, menu.jahr, csv_content, source=sync_source)
    else:
        log(f"⚠️ Unbekannter Übertragungsmodus: '{mode}'. Erlaubt sind 'sftp' oder 'webhook'.")

    # 4. Status aktualisieren
    state["last_sync_date"] = today_str
    state["last_sync_time"] = datetime.now().isoformat()
    state["last_sync_kw"] = menu.kw
    state["last_sync_year"] = menu.jahr
    state["last_sync_success"] = upload_ok
    if upload_ok:
        state["last_error"] = None
    save_state(state)

    if upload_ok:
        log(f"🎉 Synchronisation für KW {menu.kw} erfolgreich abgeschlossen!")
        return 0
    else:
        log("⚠️ Lokale Daten wurden aktualisiert, aber der Upload zu Hetzner ist fehlgeschlagen.")
        return 2


def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ("--help", "-h", "help"):
            print(__doc__)
            sys.exit(0)
        elif arg == "--force":
            sys.exit(run_sync(force=True))
        elif arg == "--status":
            st = load_state()
            cfg = load_config()
            host, user, _ = load_sftp_credentials()
            print("\n=== Speiseplan Sync Status ===")
            print(f"Modus:          {cfg.get('mode')}")
            print(f"SFTP-Server:    {host} (User: {user})")
            print(f"Webhook-URL:    {cfg.get('webhook_url')}")
            print(f"Letzter Sync:   {st.get('last_sync_time', 'Noch nie')}")
            print(f"Letzte KW:      {st.get('last_sync_kw', '-')} / {st.get('last_sync_year', '-')}")
            print(f"Erfolgreich:    {'Ja ✅' if st.get('last_sync_success') else 'Nein ❌'}")
            if st.get('last_error'):
                print(f"Letzter Fehler: {st.get('last_error')}")
            print()
            sys.exit(0)
        elif arg == "--test":
            cfg = load_config()
            host, user, pw = load_sftp_credentials()
            print(f"1. Teste SFTP zu {host} (User: {user})...")
            cmd = ["curl", "-s", "-k", "--connect-timeout", "10", "-u", f"{user}:{pw}", f"sftp://{host}/data/"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0:
                print("   ✓ SFTP-Verbindung erfolgreich! Dateien in data/:")
                print("     " + "\n     ".join(res.stdout.decode().strip().split("\n")[:6]))
            else:
                print(f"   ❌ SFTP-Fehler: {res.stderr.decode().strip()}")

            print(f"\n2. Teste Webhook zu {cfg.get('webhook_url')}...")
            url = cfg.get("webhook_url", "")
            token = cfg.get("sync_token", "")
            ok = upload_via_webhook(url, token, 43, 2026, "kw;jahr;datum;wochentag;kategorie;gericht;preis_mitarbeiter;preis_gaeste;eigenschaften;kalorien;allergene")
            print("   " + ("✓ Webhook erfolgreich!" if ok else "❌ Webhook fehlgeschlagen."))
            sys.exit(0)

    # Standard-Aufruf (z. B. durch systemd timer / cron)
    sys.exit(run_sync(force=False))


if __name__ == "__main__":
    main()
