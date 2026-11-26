"""
speiseplan_core/cli.py — Kommandozeilen-Oberfläche (CLI) & Terminal-Ausgabe.

Verarbeitet Terminal-Aufrufe wie:
- `./speiseplan.py` / `heute` / `morgen` / `woche` / `donnerstag`
- `./speiseplan.py update`
- `./speiseplan.py search "Schnitzel"`
- `./speiseplan.py stats [--demo] [--json]`
- `./speiseplan.py watch add/list/remove ...`
- `./speiseplan.py alert` (stummer Check für Cronjobs)
"""

import argparse
from datetime import datetime, timedelta
import json
import os
import sys

from .analytics import CanteenAnalytics, generate_demo_archive, render_ascii_bar
from .config import (
    BOLD,
    BG_YELLOW,
    CYAN,
    DEFAULT_URL,
    DIM,
    GREEN,
    RED,
    RESET,
    WEEKDAYS_DE,
    WHITE,
    YELLOW,
    cmd_install_help,
    ensure_data_dirs,
    find_tesseract_binary,
    print_missing_tesseract_help,
)
from .models import DayMenu, WeekMenu
from .parser import parse_menu_file, parse_menu_image
from .scraper import fetch_latest_menu_image, fetch_latest_menu_source
from .storage import (
    find_latest_local_week,
    get_week_csv_path,
    load_archive_dishes,
    load_week_csv,
    save_week_csv,
    search_archive,
    update_archive_csv,
)
from .watchlist import WatchlistManager


def print_footer_hint():
    """Gibt einen dezenten Hinweis auf die Hilfeseite (`-h`) am Ende interaktiver Ausgaben aus."""
    script = os.path.basename(sys.argv[0])
    print(f"{DIM}💡 Tipp: Für alle weiteren Optionen und Beispiele: ./{script} -h{RESET}\n")


def ensure_week_menu(force_update: bool = False, offline: bool = False) -> WeekMenu:
    """
    Stellt sicher, dass der Wochenplan der aktuellen Kalenderwoche geladen ist:
    1. Prüft den lokalen Cache (`data/kwXX_YYYY.csv`).
    2. Falls nicht vorhanden (oder `force_update=True`), wird das aktuelle PDF
       (bzw. Bild mit OCR-Fallback) geladen und geparst.
    3. Speichert die neue Wochen-CSV und aktualisiert `data/archive.csv`.
    """
    ensure_data_dirs()
    now = datetime.now()
    cur_kw, cur_year = now.isocalendar()[1], now.isocalendar()[0]
    expected_csv = get_week_csv_path(cur_kw, cur_year)

    if not force_update and os.path.exists(expected_csv):
        return load_week_csv(expected_csv)

    if offline:
        latest = find_latest_local_week()
        if latest:
            return latest
        raise RuntimeError("Kein lokaler Speiseplan vorhanden und --offline aktiv.")

    print(f"{CYAN}ℹ Lade aktuellen Speiseplan von {DEFAULT_URL} herunter...{RESET}", file=sys.stderr)
    menu_path = fetch_latest_menu_source(prefer_pdf=True)
    if menu_path.lower().endswith(".pdf"):
        print(f"{CYAN}ℹ Extrahiere Speiseplan aus PDF ({os.path.basename(menu_path)})...{RESET}", file=sys.stderr)
        try:
            menu = parse_menu_file(menu_path)
        except FileNotFoundError:
            print(f"{YELLOW}⚠ Poppler (pdftoppm) nicht gefunden – weiche auf Bild-Vorschau + OCR aus...{RESET}", file=sys.stderr)
            if not find_tesseract_binary():
                print_missing_tesseract_help()
                sys.exit(1)
            img_path = fetch_latest_menu_image()
            menu = parse_menu_image(img_path)
    else:
        if not find_tesseract_binary():
            print_missing_tesseract_help()
            sys.exit(1)
        print(f"{CYAN}ℹ Führe OCR-Tabellenanalyse durch...{RESET}", file=sys.stderr)
        menu = parse_menu_file(menu_path)
    csv_file = save_week_csv(menu)
    total = update_archive_csv(menu)
    print(f"{GREEN}✓ KW {menu.kw} gespeichert ({csv_file}, {total} Gerichte im Archiv).{RESET}\n", file=sys.stderr)
    return menu


def print_banner_alerts(menu: WeekMenu, wm: WatchlistManager):
    """Prüft die Watchlist und gibt bei Treffern ein auffälliges Alarm-Banner aus."""
    hits = wm.check_menu(menu)
    if hits:
        print(f"\n{BG_YELLOW}{BOLD}{WHITE} 🔔 LIEBLINGSGERICHT-ALARM! {RESET}")
        for alert in wm.format_alerts(hits, detailed=True):
            print(f"  {YELLOW}👉 {BOLD}{alert}{RESET}")
        print()


def print_day_menu(dm: DayMenu, is_today: bool = False):
    """Gibt das Tagesangebot mit Preisen (MA/Gäste), Kalorien und Siegeln strukturiert aus."""
    today = f" {GREEN}(Heute){RESET}" if is_today else ""
    print(f"{BOLD}{CYAN}══════════════════════════════════════════════════════════════════{RESET}")
    print(f" {BOLD}{dm.wochentag}{RESET}, {dm.datum}{today}")
    print(f"{BOLD}{CYAN}══════════════════════════════════════════════════════════════════{RESET}")
    for dish in dm.dishes:
        badge = f" {GREEN}[VEGAN]{RESET}" if dish.eigenschaften == "Vegan" else (
            f" {YELLOW}[VEGETARISCH]{RESET}" if dish.eigenschaften == "Vegetarisch" else ""
        )
        price = f" {DIM}(MA: {dish.preis_mitarbeiter} | Gäste: {dish.preis_gaeste}){RESET}" if dish.preis_mitarbeiter else ""
        cal = f" {DIM}[{dish.kalorien}]{RESET}" if dish.kalorien else ""
        print(f"  {BOLD}• {dish.kategorie}:{RESET} {dish.gericht}{badge}{price}{cal}")
    print()


def cmd_show(args, wm: WatchlistManager):
    """CLI-Handler für Tages- und Wochenanzeigen (`heute`, `morgen`, `woche` oder Wochentag)."""
    menu = ensure_week_menu(force_update=args.update, offline=args.offline)
    now = datetime.now()
    cur_wday = WEEKDAYS_DE[now.weekday()]

    if not args.no_alert:
        print_banner_alerts(menu, wm)

    target = args.target.strip().lower() if args.target else "heute"

    if target in ["heute", "today"]:
        if cur_wday in ["Samstag", "Sonntag"]:
            print(f"{YELLOW}Heute ist {cur_wday} – am Wochenende hat die Kantine geschlossen.{RESET}")
            for w in ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]:
                dm = menu.get_day(w)
                if dm:
                    print_day_menu(dm, is_today=False)
        else:
            dm = menu.get_day(cur_wday)
            if dm:
                print_day_menu(dm, is_today=True)

    elif target in ["morgen", "tomorrow"]:
        tm = now + timedelta(days=1)
        tm_wday = WEEKDAYS_DE[tm.weekday()]
        if tm_wday in ["Samstag", "Sonntag"]:
            print(f"{YELLOW}Morgen ist {tm_wday} – die Kantine hat geschlossen.{RESET}")
        else:
            dm = menu.get_day(tm_wday)
            if dm:
                print_day_menu(dm, is_today=False)

    elif target in ["woche", "week", "alle"]:
        print(f"\n{BOLD}SPEISEPLAN KW {menu.kw} ({menu.start_date} bis {menu.end_date}) - HessenTreff (Kaiberg Kitchen){RESET}\n")
        for w in ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]:
            dm = menu.get_day(w)
            if dm:
                print_day_menu(dm, is_today=(w == cur_wday))

    else:
        matched = next((w for w in ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"] if w.lower().startswith(target)), None)
        if matched:
            dm = menu.get_day(matched)
            if dm:
                print_day_menu(dm, is_today=(matched == cur_wday))
        else:
            print(f"{RED}Unbekannter Wochentag: '{args.target}'. Erlaubt: heute, morgen, woche, montag..freitag.{RESET}")


def cmd_search(args):
    """CLI-Handler für die Archivsuche: findet Termine und Details zu früheren Gerichten."""
    q = args.query.strip()
    if not q:
        print(f"{RED}Suchbegriff angeben: ./{os.path.basename(sys.argv[0])} search <Begriff>{RESET}")
        return
    results = search_archive(q)
    if not results:
        print(f"{YELLOW}Keine Einträge für '{q}' im Archiv gefunden.{RESET}")
        return

    print(f"\n{BOLD}{CYAN}Suchergebnisse im Archiv für '{q}':{RESET} ({len(results)} Treffer)\n")
    latest = results[0]
    print(f"{GREEN}⭐ Zuletzt im Angebot:{RESET}")
    print(f"  {BOLD}Datum:{RESET}       {latest.wochentag}, {latest.datum} (KW {latest.kw}/{latest.jahr})")
    print(f"  {BOLD}Kategorie:{RESET}   {latest.kategorie}")
    print(f"  {BOLD}Gericht:{RESET}     {latest.gericht}")
    if latest.preis_mitarbeiter:
        print(f"  {BOLD}Preise:{RESET}      Mitarbeiter {latest.preis_mitarbeiter} / Gäste {latest.preis_gaeste}")
    print()

    if len(results) > 1:
        print(f"{BOLD}Frühere Termine:{RESET}")
        for r in results[1:8]:
            print(f"  • {r.datum} ({r.wochentag[:2]}, KW {r.kw}): {r.gericht}")
    print()


def cmd_watch(args, wm: WatchlistManager):
    """CLI-Handler für die Verwaltung der Lieblingsgerichte (Watchlist)."""
    action = args.watch_action
    if action == "list":
        items = wm.list_keywords()
        print(f"\n{BOLD}{CYAN}Watchlist für Lieblingsgerichte:{RESET}")
        if not items:
            print(f"  {DIM}(leer – hinzufügen mit: ./{os.path.basename(sys.argv[0])} watch add \"Burger\"){RESET}\n")
        else:
            for it in items:
                print(f"  • {GREEN}{it}{RESET}")
            print()
    elif action == "add":
        if wm.add(args.keyword):
            print(f"{GREEN}✓ '{args.keyword}' zur Watchlist hinzugefügt.{RESET}")
        else:
            print(f"{YELLOW}ℹ Bereits vorhanden oder ungültig.{RESET}")
    elif action in ["remove", "del", "rm"]:
        if wm.remove(args.keyword):
            print(f"{GREEN}✓ '{args.keyword}' aus Watchlist entfernt.{RESET}")
        else:
            print(f"{YELLOW}ℹ Nicht gefunden.{RESET}")


def cmd_alert_silent(args, wm: WatchlistManager):
    """Silent-Check für Cronjobs: gibt nur etwas aus, wenn ein Lieblingsgericht auf der Karte steht."""
    try:
        menu = ensure_week_menu(force_update=args.update, offline=args.offline)
    except Exception:
        sys.exit(0)
    hits = wm.check_menu(menu)
    if hits:
        for alert in wm.format_alerts(hits, detailed=False):
            print(alert)
    sys.exit(0)


def cmd_stats(args):
    """CLI-Handler für statistische Auswertungen des Archivs."""
    dishes = generate_demo_archive(20) if getattr(args, "demo", False) else load_archive_dishes()
    src_label = (
        f"{YELLOW}(DEMO: 20 Wochen / {len(dishes)} Gerichte){RESET}"
        if getattr(args, "demo", False)
        else f"{CYAN}(Echtes Archiv: {len(dishes)} Gerichte){RESET}"
    )

    if not dishes:
        print(f"{YELLOW}Archiv leer. Erst './speiseplan.py update' ausführen oder '--demo' nutzen.{RESET}")
        return

    ca = CanteenAnalytics(dishes)
    mode = getattr(args, "mode", "overview") or "overview"
    as_json = getattr(args, "json", False)

    if mode in ["overview", "dashboard"]:
        ov = ca.get_overview()
        if as_json:
            print(json.dumps(ov, ensure_ascii=False, indent=2))
            return
        print(f"\n{BOLD}{CYAN}══════════════════════════════════════════════════════════════════{RESET}")
        print(f" {BOLD}KANTINEN-ANALYSE & DASHBOARD{RESET} {src_label}")
        print(f"{BOLD}{CYAN}══════════════════════════════════════════════════════════════════{RESET}")
        print(f"  • Erfasste Speisen:       {BOLD}{ov['total_dishes']}{RESET} Gerichte ({ov['total_weeks']} Wochen)")
        print(f"  • Zeitraum:               {ov['date_start']} bis {ov['date_end']}")
        print(f"  • Ø Preis Hauptgerichte:  {BOLD}{ov['avg_price_employee']:.2f} €{RESET}\n")

        print(f"{BOLD}🥩 Fleischarten & Proteinquellen (Hauptgerichte):{RESET}")
        m_dist = ov["meat_distribution"]
        m_max = max(m_dist.values()) if m_dist else 1
        m_total = sum(m_dist.values()) if m_dist else 1
        for meat, cnt in sorted(m_dist.items(), key=lambda x: x[1], reverse=True):
            pct = (cnt / m_total) * 100
            bar = render_ascii_bar(cnt, m_max, 14)
            print(f"  {meat:26s} {CYAN}{bar}{RESET} {BOLD}{cnt:2d}x{RESET} ({pct:4.1f}%)")
        print()

        print(f"{BOLD}⭐ Häufigste Gerichte:{RESET}")
        for dish, cnt in ov["top_dishes"]:
            print(f"  • {BOLD}{cnt}x{RESET}: {dish}")
        print()
        print(f"{BOLD}🔄 Lebenszyklus:{RESET} {ov['staples_count']} Klassiker (≥ 3x), {ov['one_hit_wonders_count']} Eintagsfliegen (nur 1x).")
        print(f"  {DIM}(Details mit: ./{os.path.basename(sys.argv[0])} stats lifecycle){RESET}\n")

    elif mode in ["dish", "gericht"]:
        q = " ".join(getattr(args, "param", []))
        if not q:
            print(f"{RED}Gericht angeben: ./{os.path.basename(sys.argv[0])} stats dish <Name>{RESET}")
            return
        res = ca.analyze_dish(q)
        if as_json:
            print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
            return
        if not res["found"]:
            print(f"{YELLOW}Keine Treffer für '{q}'.{RESET}")
            return
        print(f"\n{BOLD}{CYAN}Wochentags-Muster für '{q}'{RESET} {src_label}")
        print(f"  • Gesamthäufigkeit: {BOLD}{res['count']}x{RESET} (Zuletzt: {res['latest_weekday']}, {res['latest_date']})")
        m_cnt = max(res["weekday_distribution"].values()) if res["weekday_distribution"] else 1
        for w in ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]:
            cnt = res["weekday_distribution"].get(w, 0)
            if cnt > 0:
                print(f"  {w:12s} {CYAN}{render_ascii_bar(cnt, m_cnt, 14)}{RESET} {BOLD}{cnt:2d}x{RESET}")
        print()

    elif mode in ["combos", "sauce", "beilagen"]:
        q = " ".join(getattr(args, "param", []))
        if not q:
            print(f"{RED}Gericht angeben: ./{os.path.basename(sys.argv[0])} stats combos <Name>{RESET}")
            return
        res = ca.analyze_combos(q)
        if as_json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return
        if not res["found"]:
            print(f"{YELLOW}Keine Treffer für '{q}'.{RESET}")
            return
        print(f"\n{BOLD}{CYAN}Soßen & Beilagen zu '{q}'{RESET} {src_label}")
        if res["top_sauces"]:
            print(f"{BOLD}🥣 Häufigste Soßen:{RESET}")
            m_s = res["top_sauces"][0][1]
            for s, c in res["top_sauces"]:
                print(f"  • {s:30s} {CYAN}{render_ascii_bar(c, m_s, 12)}{RESET} {BOLD}{c:2d}x{RESET}")
            print()
        if res["top_sides"]:
            print(f"{BOLD}🥔 Häufigste Beilagen:{RESET}")
            m_b = res["top_sides"][0][1]
            for b, c in res["top_sides"]:
                print(f"  • {b:30s} {CYAN}{render_ascii_bar(c, m_b, 12)}{RESET} {BOLD}{c:2d}x{RESET}")
            print()

    elif mode in ["weekday", "tag"]:
        p = " ".join(getattr(args, "param", [])) or "Freitag"
        res = ca.analyze_weekday(p)
        if as_json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return
        print(f"\n{BOLD}{CYAN}Charakteristik am {res['weekday']}{RESET} {src_label}")
        if res["fish_dishes_count"] > 0:
            print(f"  • 🐟 Fischgerichte: {BOLD}{res['fish_dishes_count']}x{RESET}")
        print(f"{BOLD}Top-Gerichte:{RESET}")
        for d, c in res["top_dishes"][:5]:
            print(f"  • {BOLD}{c:2d}x{RESET}: {d}")
        print()

    elif mode in ["lifecycle", "klassiker"]:
        res = ca.get_lifecycle()
        if as_json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return
        print(f"\n{BOLD}{CYAN}Klassiker vs. Eintagsfliegen{RESET} {src_label}\n")
        print(f"{BOLD}🏆 Dauerbrenner (≥ 3x serviert):{RESET}")
        for d, c in res["staples"]:
            print(f"  • {BOLD}{c:2d}x{RESET}: {d}")
        print(f"\n{BOLD}🌟 Eintagsfliegen ({res['one_hit_total']} Gerichte nur genau 1x):{RESET}")
        for d in res["one_hit_wonders"][:8]:
            print(f"  • {d}")
        print()


DOC_DESCRIPTION = f"""{BOLD}Speiseplan CLI - HessenTreff (Kaiberg Kitchen){RESET}
Lädt den wöchentlichen Speiseplan (PDF direkt, mit OCR-Fallback für Bilder) von der
Webseite herunter, speichert ihn in CSV-Dateien (pro KW und Langzeitarchiv) und bietet
Tagesabfragen, Archivsuche, Statistiken sowie Lieblingsgericht-Benachrichtigungen.

Kompatibel mit Linux, macOS und Windows 11."""

HELP_EPILOG = f"""
{BOLD}{CYAN}══════════════════════════════════════════════════════════════════════════════{RESET}
 {BOLD}BEFEHLE & ECHTE BEISPIELE ZUM AUSPROBIEREN{RESET}
{BOLD}{CYAN}══════════════════════════════════════════════════════════════════════════════{RESET}

{BOLD}📅 1. TAGES- & WOCHENABFRAGEN:{RESET}
  {GREEN}./speiseplan.py{RESET}                          Zeigt das heutige Menü (inkl. Alarm-Banner)
  {GREEN}./speiseplan.py heute{RESET}                    Heutiges Angebot im HessenTreff
  {GREEN}./speiseplan.py morgen{RESET}                   Angebot für morgen
  {GREEN}./speiseplan.py donnerstag{RESET}               Menü für Donnerstag (Montag - Freitag)
  {GREEN}./speiseplan.py woche{RESET}                    Komplette Wochenübersicht (Mo-Fr)
  {GREEN}./speiseplan.py update{RESET}                   Aktuellen Plan live von Website neu laden

{BOLD}🔎 2. HISTORISCHE ARCHIVSUCHE:{RESET}
  {GREEN}./speiseplan.py search "Burger"{RESET}           Wann gab es zuletzt Burger und wie oft?
  {GREEN}./speiseplan.py search "Schnitzel"{RESET}        Findet alle Termine für Schnitzel
  {GREEN}./speiseplan.py search "Pizza"{RESET}            Historische Termine für Pizza

{BOLD}📊 3. STATISTIKEN & AUSWERTUNGEN (mit ASCII-Diagrammen):{RESET}
  {GREEN}./speiseplan.py stats{RESET}                          Dashboard (Fleischarten, Top-Gerichte, Ø Preis)
  {GREEN}./speiseplan.py stats --demo{RESET}                   20-Wochen-Historie mit 500 Gerichten testen
  {GREEN}./speiseplan.py stats dish "Pizza" --demo{RESET}         An welchem Tag gab es meistens Pizza?
  {GREEN}./speiseplan.py stats combos "Schnitzel" --demo{RESET}     Häufigste Soßen & beliebteste Beilagen
  {GREEN}./speiseplan.py stats weekday freitag --demo{RESET}      Tagescharakteristik (z.B. Fisch am Freitag)
  {GREEN}./speiseplan.py stats lifecycle --demo{RESET}          Klassiker (≥ 3x) vs. Eintagsfliegen (1x)
  {GREEN}./speiseplan.py stats --demo --json{RESET}            Ergebnisse als strukturiertes JSON

{BOLD}🔔 4. WATCHLIST FÜR LIEBLINGSGERICHTE:{RESET}
  {GREEN}./speiseplan.py watch add "Burger"{RESET}            'Burger' zur Überwachung hinzufügen
  {GREEN}./speiseplan.py watch list{RESET}                    Gespeicherte Lieblingsgerichte anzeigen
  {GREEN}./speiseplan.py watch remove "Burger"{RESET}         'Burger' aus der Watchlist entfernen

{BOLD}🤖 5. SILENT-CHECK (für Cronjobs & Shell-Skripte):{RESET}
  {GREEN}./speiseplan.py alert{RESET}                         Bleibt völlig stumm (0 Zeichen), außer ein
                                                beobachtetes Gericht steht diese Woche auf
                                                der Karte (z. B. 'hey, Donnerstag gibt es Burger!').

{BOLD}ℹ️  6. SYSTEMDIAGNOSE & HILFE:{RESET}
  {GREEN}./speiseplan.py hilfe{RESET}                         Zeigt diese Hilfeseite (auch mit -h oder --help)
  {GREEN}./speiseplan.py --install-help{RESET}                Tesseract-Status & Installationsanleitung für alle OS
  {GREEN}./speiseplan.py install-help{RESET}                  (Alternative ohne Bindestriche)
"""


def main():
    """Haupteinstiegspunkt: parst Befehlszeilenargumente und delegiert an CLI-Handler."""
    wm = WatchlistManager()
    first_arg = (sys.argv[1].lower() if len(sys.argv) > 1 else "").strip()

    if first_arg in ["install-help", "install-info", "doctor", "--install-help", "-i"]:
        cmd_install_help()
        return

    if first_arg in ["hilfe", "help"]:
        parser = argparse.ArgumentParser(
            description=DOC_DESCRIPTION,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=HELP_EPILOG,
        )
        parser.add_argument("target", nargs="?", default="heute", help="heute, morgen, woche, montag, dienstag, hilfe...")
        parser.add_argument("--update", "-u", action="store_true", help="Erzwingt Aktualisierung von der Webseite")
        parser.add_argument("--offline", action="store_true", help="Keine Netzwerkverbindung aufbauen")
        parser.add_argument("--no-alert", action="store_true", help="Kein Alarm-Banner anzeigen")
        parser.add_argument("--install-help", "-i", action="store_true", help="Zeigt Tesseract-Status und Installationshilfe")
        parser.print_help()
        return

    if first_arg == "search":
        parser = argparse.ArgumentParser(description="Archiv nach Gerichten durchsuchen")
        parser.add_argument("subcmd")
        parser.add_argument("query", nargs="*", help="Suchbegriff im Archiv")
        args = parser.parse_args()
        args.query = " ".join(args.query)
        cmd_search(args)
        print_footer_hint()
        return

    elif first_arg in ["stats", "analyse"]:
        parser = argparse.ArgumentParser(description="Statistiken und Auswertungen")
        parser.add_argument("subcmd")
        parser.add_argument(
            "mode",
            nargs="?",
            default="overview",
            choices=["overview", "dashboard", "dish", "combos", "weekday", "lifecycle"],
        )
        parser.add_argument("param", nargs="*", help="Gericht oder Wochentag")
        parser.add_argument("--demo", action="store_true", help="20-Wochen-Demodatensatz nutzen")
        parser.add_argument("--json", action="store_true", help="JSON-Ausgabe")
        args = parser.parse_args()
        cmd_stats(args)
        if not getattr(args, "json", False):
            print_footer_hint()
        return

    elif first_arg == "watch":
        parser = argparse.ArgumentParser(description="Watchlist verwalten")
        parser.add_argument("subcmd")
        parser.add_argument("watch_action", nargs="?", choices=["list", "add", "remove", "del", "rm"], default="list")
        parser.add_argument("keyword", nargs="*", help="Suchbegriff")
        args = parser.parse_args()
        args.keyword = " ".join(args.keyword)
        cmd_watch(args, wm)
        print_footer_hint()
        return

    elif first_arg == "alert":
        parser = argparse.ArgumentParser(description="Silent-Check für Cronjobs")
        parser.add_argument("subcmd")
        parser.add_argument("--update", "-u", action="store_true")
        parser.add_argument("--offline", action="store_true")
        args = parser.parse_args()
        cmd_alert_silent(args, wm)
        return

    elif first_arg == "update":
        parser = argparse.ArgumentParser(description="Speiseplan neu laden")
        parser.add_argument("subcmd")
        parser.parse_args()
        menu = ensure_week_menu(force_update=True, offline=False)
        print(f"{GREEN}✓ KW {menu.kw} erfolgreich aktualisiert!{RESET}")
        print_footer_hint()
        return

    parser = argparse.ArgumentParser(
        description=DOC_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=HELP_EPILOG,
    )
    parser.add_argument("target", nargs="?", default="heute", help="heute, morgen, woche, montag, dienstag...")
    parser.add_argument("--update", "-u", action="store_true", help="Erzwingt Aktualisierung von der Webseite")
    parser.add_argument("--offline", action="store_true", help="Keine Netzwerkverbindung aufbauen")
    parser.add_argument("--no-alert", action="store_true", help="Kein Alarm-Banner anzeigen")
    parser.add_argument("--install-help", "-i", action="store_true", help="Zeigt Tesseract-Status und Installationshilfe")

    args = parser.parse_args()
    if args.install_help:
        cmd_install_help()
        return
    if args.target.lower() in ["hilfe", "help"]:
        parser.print_help()
        return
    cmd_show(args, wm)
    print_footer_hint()
