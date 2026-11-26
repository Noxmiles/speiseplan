"""
speiseplan_core/storage.py — CSV-Speicherung, Wochen-Cache & Langzeitarchiv.

Speichert jeden eingelesenen Wochenplan zweifach:
1. `data/kwXX_YYYY.csv`: Aktuelle Woche für schnellen Abruf ohne erneuten Download.
2. `data/archive.csv`: Kumuliertes Langzeitarchiv aller Wochen, automatisch
   dedupliziert über `(datum, kategorie)`.

Alle CSV-Dateien verwenden Semikolon (`;`) als Trennzeichen und UTF-8-Kodierung,
damit sie auch in Excel auf Deutsch problemlos geöffnet werden können.
"""

import csv
import os
import re
from typing import List, Optional, Tuple

from .config import CSV_COLUMNS, DATA_DIR
from .models import DayMenu, Dish, WeekMenu


def get_week_csv_path(kw: int, jahr: int, data_dir: str = DATA_DIR) -> str:
    """Erzeugt den Dateipfad `data/kwXX_YYYY.csv` für eine Kalenderwoche."""
    return os.path.join(data_dir, f"kw{kw:02d}_{jahr}.csv")


def save_week_csv(menu: WeekMenu, data_dir: str = DATA_DIR) -> str:
    """Speichert eine `WeekMenu`-Woche als Semikolon-CSV (ohne Platzhalter 'Tagesgericht')."""
    os.makedirs(data_dir, exist_ok=True)
    target = get_week_csv_path(menu.kw, menu.jahr, data_dir)
    with open(target, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, delimiter=";")
        writer.writeheader()
        for dish in menu.all_dishes():
            norm_g = re.sub(r"^[\d\s,.*+-]+|[\d\s,.*+-]+$", "", dish.gericht).strip().lower()
            if not norm_g or norm_g == "tagesgericht":
                continue
            writer.writerow(dish.to_dict())
    return target


def load_week_csv(csv_path: str) -> WeekMenu:
    """Lädt eine Wochen-CSV-Datei wieder als vollständiges `WeekMenu`-Objekt."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Datei {csv_path} existiert nicht.")
    dishes = []
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            dishes.append(Dish.from_dict(row))
    if not dishes:
        raise ValueError(f"Keine Einträge in {csv_path}")

    days = {}
    for d in dishes:
        if d.wochentag not in days:
            days[d.wochentag] = DayMenu(wochentag=d.wochentag, datum=d.datum, dishes=[])
        days[d.wochentag].dishes.append(d)

    sorted_dates = sorted([d.datum for d in dishes])
    return WeekMenu(
        kw=dishes[0].kw,
        jahr=dishes[0].jahr,
        start_date=sorted_dates[0],
        end_date=sorted_dates[-1],
        days=days,
    )


def update_archive_csv(menu: WeekMenu, data_dir: str = DATA_DIR) -> int:
    """Fügt Gerichte der Woche in `archive.csv` ein (aktualisiert bei gleichem Datum/Kategorie)."""
    os.makedirs(data_dir, exist_ok=True)
    archive_path = os.path.join(data_dir, "archive.csv")
    existing = {}

    if os.path.exists(archive_path):
        with open(archive_path, "r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter=";"):
                try:
                    d = Dish.from_dict(row)
                    norm_g = re.sub(r"^[\d\s,.*+-]+|[\d\s,.*+-]+$", "", d.gericht).strip().lower()
                    if not norm_g or norm_g == "tagesgericht":
                        continue
                    norm_cat = re.sub(r"\s+", "", d.kategorie.lower())
                    existing[(d.datum, norm_cat)] = d
                except Exception:
                    pass

    for dish in menu.all_dishes():
        norm_g = re.sub(r"^[\d\s,.*+-]+|[\d\s,.*+-]+$", "", dish.gericht).strip().lower()
        if not norm_g or norm_g == "tagesgericht":
            continue
        norm_cat = re.sub(r"\s+", "", dish.kategorie.lower())
        existing[(dish.datum, norm_cat)] = dish

    sorted_dishes = sorted(
        existing.values(),
        key=lambda x: (x.datum, re.sub(r"\s+", "", x.kategorie.lower())),
        reverse=True,
    )
    with open(archive_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, delimiter=";")
        writer.writeheader()
        for dish in sorted_dishes:
            writer.writerow(dish.to_dict())
    return len(sorted_dishes)


def search_archive(query: str, data_dir: str = DATA_DIR) -> List[Dish]:
    """Sucht nach Gerichten im Langzeitarchiv (neueste Treffer zuerst)."""
    archive_path = os.path.join(data_dir, "archive.csv")
    if not os.path.exists(archive_path):
        return []
    q = query.strip().lower()
    matches = []
    with open(archive_path, "r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter=";"):
            try:
                d = Dish.from_dict(row)
                if q in d.gericht.lower() or q in d.kategorie.lower():
                    matches.append(d)
            except Exception:
                pass
    matches.sort(key=lambda x: x.datum, reverse=True)
    return matches


def load_archive_dishes(data_dir: str = DATA_DIR) -> List[Dish]:
    """Lädt alle gespeicherten Gerichte aus `archive.csv`."""
    archive_path = os.path.join(data_dir, "archive.csv")
    if not os.path.exists(archive_path):
        return []
    res = []
    with open(archive_path, "r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter=";"):
            try:
                res.append(Dish.from_dict(row))
            except Exception:
                pass
    return res


def find_latest_local_week(data_dir: str = DATA_DIR) -> Optional[WeekMenu]:
    """Findet und lädt die neueste lokal gespeicherte `kwXX_YYYY.csv`."""
    if not os.path.exists(data_dir):
        return None
    files = [f for f in os.listdir(data_dir) if f.startswith("kw") and f.endswith(".csv")]
    if not files:
        return None

    def week_key(filename: str) -> Tuple[int, int]:
        m = re.search(r"kw(\d+)_(\d+)\.csv", filename)
        return (int(m.group(2)), int(m.group(1))) if m else (0, 0)

    files.sort(key=week_key, reverse=True)
    return load_week_csv(os.path.join(data_dir, files[0]))
