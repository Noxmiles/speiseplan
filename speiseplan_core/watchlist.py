"""
speiseplan_core/watchlist.py — Persönliche Lieblingsgerichte & Alarm-Meldungen.

Verwaltet Suchbegriffe (z. B. "Burger", "Schnitzel") in `data/watchlist.json`
und prüft einen geladenen Wochenplan (`WeekMenu`) auf Treffer.
"""

import json
import os
from typing import List, Tuple

from .config import WATCHLIST_FILE
from .models import Dish, WeekMenu


class WatchlistManager:
    """Verwaltet Lieblingsgerichte in `watchlist.json` und prüft Speisepläne."""

    def __init__(self, filepath: str = WATCHLIST_FILE):
        self.filepath = filepath
        os.makedirs(os.path.dirname(os.path.abspath(self.filepath)), exist_ok=True)
        if not os.path.exists(self.filepath):
            self.save([])

    def load(self) -> List[str]:
        """Lädt alle gespeicherten Suchbegriffe aus der JSON-Datei."""
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                d = json.load(f)
                return [str(x).strip() for x in d if str(x).strip()] if isinstance(d, list) else []
        except Exception:
            return []

    def save(self, items: List[str]):
        """Speichert die Suchbegriffe alphabetisch sortiert und ohne Duplikate."""
        cleaned = sorted(list({x.strip() for x in items if x.strip()}), key=lambda s: s.lower())
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)

    def add(self, keyword: str) -> bool:
        """Fügt ein neues Schlüsselwort hinzu (False falls leer oder bereits vorhanden)."""
        kw = keyword.strip()
        if not kw or any(kw.lower() == item.lower() for item in self.load()):
            return False
        items = self.load()
        items.append(kw)
        self.save(items)
        return True

    def remove(self, keyword: str) -> bool:
        """Entfernt ein Schlüsselwort (Groß-/Kleinschreibung egal)."""
        kw = keyword.strip().lower()
        items = self.load()
        filtered = [x for x in items if x.lower() != kw]
        if len(filtered) == len(items):
            return False
        self.save(filtered)
        return True

    def list_keywords(self) -> List[str]:
        """Gibt alle aktuell überwachten Begriffe zurück."""
        return self.load()

    def check_menu(self, menu: WeekMenu) -> List[Tuple[str, Dish]]:
        """Prüft alle Gerichte einer Woche auf Watchlist-Treffer."""
        keywords = self.load()
        if not keywords:
            return []
        hits = []
        for dish in menu.all_dishes():
            text = dish.gericht.lower()
            for kw in keywords:
                if kw.lower() in text:
                    hits.append((kw, dish))
        return hits

    @staticmethod
    def format_alerts(hits: List[Tuple[str, Dish]], detailed: bool = False) -> List[str]:
        """Formatiert Treffer wahlweise als kompakte Cron-Zeile oder ausführlichen Banner-Text."""
        msgs = []
        for kw, dish in hits:
            if detailed:
                diet = f" [{dish.eigenschaften}]" if dish.eigenschaften else ""
                msgs.append(f"hey, {dish.wochentag} gibt es {kw}! ({dish.kategorie}: {dish.gericht}{diet})")
            else:
                msgs.append(f"hey, {dish.wochentag} gibt es {kw}!")
        return msgs
