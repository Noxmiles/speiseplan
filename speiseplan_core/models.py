"""
speiseplan_core/models.py — Datenmodelle für Gerichte, Tages- und Wochenpläne.

Diese drei Datenklassen bilden das Grundgerüst des gesamten Projekts:
- `Dish`: Ein einzelnes Gericht (z. B. Montag, Leibspeise 1, Titel, Preis, Siegel).
- `DayMenu`: Alle Gerichte eines Wochentags.
- `WeekMenu`: Eine komplette Kalenderwoche (Montag bis Freitag).

Wer das System in einer anderen Sprache (z. B. Java) nachbaut, kann sich direkt an
den Feldern von `Dish` orientieren — sie entsprechen 1:1 den Spalten der CSV-Dateien.
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from .text_cleaning import fix_dangling_components, normalize_ocr_text


@dataclass
class Dish:
    """Repräsentiert ein einzelnes Gericht auf dem Speiseplan."""

    kw: int                         # Kalenderwoche (1..53)
    jahr: int                       # ISO-Jahr der Woche (z. B. 2026)
    datum: str                      # ISO-Datum im Format YYYY-MM-DD (z. B. "2026-11-19")
    wochentag: str                  # "Montag" .. "Freitag"
    kategorie: str                  # "Suppe", "Leibspeise 1", "Leibspeise 2", "Leibspeise 3", "Salatbar"
    gericht: str                    # Bereinigter Name/Beschreibung des Gerichts
    preis_mitarbeiter: str = ""     # z. B. "4,60 €"
    preis_gaeste: str = ""          # z. B. "7,90 €"
    eigenschaften: str = ""         # "Vegan", "Vegetarisch" oder leer ""
    kalorien: str = ""              # z. B. "230 kcal*"
    allergene: str = ""             # Optional (wird aktuell bewusst leer gelassen)

    def to_dict(self) -> dict:
        """Wandelt das Gericht für den CSV-/JSON-Export in ein Dictionary um."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Dish":
        """Erstellt ein `Dish`-Objekt aus einer gelesenen CSV-Zeile und bereinigt Altlasten."""
        return cls(
            kw=int(data["kw"]),
            jahr=int(data["jahr"]),
            datum=str(data["datum"]),
            wochentag=str(data["wochentag"]),
            kategorie=str(data["kategorie"]),
            gericht=fix_dangling_components(normalize_ocr_text(str(data.get("gericht", "")))),
            preis_mitarbeiter=str(data.get("preis_mitarbeiter", "")),
            preis_gaeste=str(data.get("preis_gaeste", "")),
            eigenschaften=str(data.get("eigenschaften", "")),
            kalorien=str(data.get("kalorien", "")),
            allergene=str(data.get("allergene", "")),
        )


@dataclass
class DayMenu:
    """Bündelt alle Gerichte eines einzelnen Tages."""

    wochentag: str
    datum: str
    dishes: List[Dish] = field(default_factory=list)


@dataclass
class WeekMenu:
    """Repräsentiert den gesamten Wochenplan (Montag bis Freitag) einer Kalenderwoche."""

    kw: int
    jahr: int
    start_date: str                 # Datum des Montags (YYYY-MM-DD)
    end_date: str                   # Datum des Freitags (YYYY-MM-DD)
    days: Dict[str, DayMenu] = field(default_factory=dict)

    def all_dishes(self) -> List[Dish]:
        """Gibt eine flache Liste aller Gerichte dieser Woche zurück."""
        res = []
        for d in self.days.values():
            res.extend(d.dishes)
        return res

    def get_day(self, weekday_name: str) -> Optional[DayMenu]:
        """Sucht das Tagesmenü anhand des Wochentags (Groß-/Kleinschreibung egal)."""
        name = weekday_name.strip().lower()
        for k, v in self.days.items():
            if k.lower() == name:
                return v
        return None
