"""
speiseplan_core/analytics.py — Statistische Auswertungen & Demo-Datengenerator.

Wertet gespeicherte Speisepläne (`archive.csv`) aus nach:
- Fleischarten & Ernährungsformen (`get_meat_distribution`)
- Häufigsten Klassikern (`get_overview`, `get_lifecycle`)
- Wochentags-Mustern eines Gerichts (`analyze_dish`, `analyze_weekday`)
- Häufigsten Soßen und Beilagen (`analyze_combos`)
"""

from collections import Counter
from datetime import datetime, timedelta
import re
from typing import Any, Dict, List

from .models import Dish
from .text_cleaning import get_canonical_dish

SAUCE_KEYWORDS = ["soße", "sauce", "dipp", "dip", "pesto", "salsa", "creme", "dressing", "schmand", "jus"]
SIDE_KEYWORDS = [
    "pommes", "kartoffel", "wedges", "reis", "drillinge", "nudeln", "spaghetti",
    "couscous", "salat", "kroketten", "spätzle", "knödel", "püree", "pasta", "gnocchi", "gemüse",
]


def render_ascii_bar(count: int, max_val: int, bar_length: int = 16) -> str:
    """Erzeugt einen einfachen ASCII-Fortschrittsbalken für Terminal-Statistiken."""
    if max_val <= 0:
        return ""
    filled = int(round((count / max_val) * bar_length))
    return "▇" * filled + "░" * (bar_length - filled)


def split_components(dish_text: str) -> List[str]:
    """Zerlegt einen Gerichtsnamen anhand Trennzeichen und Füllwörtern in Einzelbestandteile."""
    parts = [p.strip() for p in dish_text.split("|") if p.strip()]
    res = []
    for p in parts:
        for sp in re.split(r"\b(?:mit|an|auf|dazu)\b", p, flags=re.I):
            clean = re.sub(r"^[\s,\.-]+|[\s,\.-]+$", "", sp.strip())
            if len(clean) > 1:
                res.append(clean)
    return res


class CanteenAnalytics:
    """Berechnet Statistiken, Wochentagsmuster, Soßen & Fleischarten."""

    def __init__(self, dishes: List[Dish]):
        self.dishes = dishes

    def get_overview(self) -> Dict[str, Any]:
        """Berechnet Gesamtkennzahlen über alle gespeicherten Gerichte."""
        if not self.dishes:
            return {"total_dishes": 0}

        dates = sorted({d.datum for d in self.dishes if d.datum})
        kws = sorted({(d.kw, d.jahr) for d in self.dishes})
        diet_counter = Counter(d.eigenschaften if d.eigenschaften else "Fleisch / Klassisch" for d in self.dishes)

        filtered = [get_canonical_dish(d.gericht) for d in self.dishes if d.gericht.lower() not in ["salatbar", "tagesgericht", ""]]
        counts = Counter(filtered)
        # Klassiker müssen mindestens 2x serviert worden sein
        top_dishes = [(dish, cnt) for dish, cnt in counts.most_common(10) if cnt >= 2]

        # Durchschnittspreis nur für echte Hauptgerichte (Leibspeisen)
        prices_ma = [
            float(re.search(r"(\d+[,.]\d{2})", d.preis_mitarbeiter).group(1).replace(",", "."))
            for d in self.dishes
            if "leibspeise" in d.kategorie.lower() and re.search(r"(\d+[,.]\d{2})", d.preis_mitarbeiter)
        ]
        avg_price = (sum(prices_ma) / len(prices_ma)) if prices_ma else 0.0

        return {
            "total_dishes": len(self.dishes),
            "total_weeks": len(kws),
            "date_start": dates[0] if dates else "",
            "date_end": dates[-1] if dates else "",
            "diet_distribution": dict(diet_counter),
            "top_dishes": top_dishes,
            "one_hit_wonders_count": sum(1 for c in counts.values() if c == 1),
            "staples_count": sum(1 for c in counts.values() if c >= 3),
            "avg_price_employee": avg_price,
            "meat_distribution": self.get_meat_distribution(),
        }

    def get_meat_distribution(self) -> Dict[str, int]:
        """Klassifiziert Hauptgerichte nach Fleischarten und Ernährungsformen (ohne Tagesgericht/Salatbar)."""
        counter = Counter()
        for d in self.dishes:
            if "leibspeise" in d.kategorie.lower():
                text = d.gericht.lower().strip()
                if not text or text in ["tagesgericht", "salatbar"]:
                    continue
                diet = d.eigenschaften.lower()
                if "vegan" in diet or "vegan" in text:
                    counter["Vegan"] += 1
                elif "vegetarisch" in diet or "vegetarisch" in text:
                    counter["Vegetarisch"] += 1
                elif any(k in text for k in ["fisch", "lachs", "scholle", "seelachs", "kabeljau", "knusperfisch", "pangasius"]):
                    counter["Fisch / Meeresfrüchte"] += 1
                elif any(k in text for k in ["hähnchen", "hahnchen", "huhn", "pute", "chicken", "geflügel"]):
                    counter["Geflügel (Huhn / Pute)"] += 1
                elif any(k in text for k in ["schwein", "schnitzel", "leberkäse", "leberkase", "kotelett", "schinken", "speck", "cevapcici"]):
                    counter["Schwein"] += 1
                elif any(k in text for k in ["rind", "rinder", "beef", "hackfleisch", "roulade", "gulasch"]):
                    counter["Rind / Kalb"] += 1
                else:
                    counter["Sonstiges / nicht explizit genannt"] += 1
        return dict(counter)

    def analyze_dish(self, query: str) -> Dict[str, Any]:
        """Untersucht, wie oft und an welchen Wochentagen ein Gericht vorkam."""
        q = query.strip().lower()
        matches = [d for d in self.dishes if q in d.gericht.lower()]
        if not matches:
            return {"query": query, "found": False, "count": 0}

        wday_cnt = Counter(d.wochentag for d in matches)
        sorted_m = sorted(matches, key=lambda x: x.datum, reverse=True)
        return {
            "query": query,
            "found": True,
            "count": len(matches),
            "latest_date": sorted_m[0].datum,
            "latest_dish": sorted_m[0].gericht,
            "latest_weekday": sorted_m[0].wochentag,
            "weekday_distribution": {
                w: wday_cnt[w]
                for w in ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]
                if wday_cnt[w] > 0
            },
        }

    def analyze_combos(self, query: str) -> Dict[str, Any]:
        """Ermittelt typische Soßen und Beilagen zu einem Suchbegriff."""
        q = query.strip().lower()
        matches = [d for d in self.dishes if q in d.gericht.lower()]
        if not matches:
            return {"query": query, "found": False, "count": 0}

        sauces, sides = [], []
        for dish in matches:
            for c in split_components(dish.gericht):
                low = c.lower()
                if q in low and len(low.replace(q, "").strip()) < 4:
                    continue
                if any(k in low for k in SAUCE_KEYWORDS):
                    sauces.append(c)
                elif any(k in low for k in SIDE_KEYWORDS):
                    sides.append(c)

        return {
            "query": query,
            "found": True,
            "count": len(matches),
            "top_sauces": Counter(sauces).most_common(8),
            "top_sides": Counter(sides).most_common(8),
        }

    def analyze_weekday(self, weekday: str) -> Dict[str, Any]:
        """Analysiert typische Gerichte und Fisch-Anteil eines bestimmten Wochentags."""
        wday_norm = weekday.strip().capitalize()
        day_dishes = [d for d in self.dishes if d.wochentag.lower() == weekday.strip().lower()]
        if not day_dishes:
            return {"weekday": wday_norm, "count": 0}

        filtered = [d.gericht for d in day_dishes if d.gericht.lower() not in ["salatbar", "tagesgericht", ""]]
        fish = sum(1 for d in day_dishes if any(k in d.gericht.lower() for k in ["fisch", "lachs", "scholle", "knusperfisch"]))
        soups = [d.gericht for d in day_dishes if "suppe" in d.kategorie.lower()]

        return {
            "weekday": wday_norm,
            "count": len(day_dishes),
            "top_dishes": Counter(filtered).most_common(6),
            "top_soups": Counter(soups).most_common(5),
            "fish_dishes_count": fish,
        }

    def get_lifecycle(self) -> Dict[str, Any]:
        """Unterscheidet Dauerbrenner (>= 3x serviert) von Eintagsfliegen (1x)."""
        filtered = [get_canonical_dish(d.gericht) for d in self.dishes if d.gericht.lower() not in ["salatbar", "tagesgericht", ""]]
        counts = Counter(filtered)
        return {
            "staples": [(dish, cnt) for dish, cnt in counts.most_common() if cnt >= 3][:10],
            "one_hit_wonders": [dish for dish, cnt in counts.items() if cnt == 1][:12],
            "one_hit_total": sum(1 for cnt in counts.values() if cnt == 1),
        }


def generate_demo_archive(num_weeks: int = 20) -> List[Dish]:
    """Erzeugt einen synthetischen 20-Wochen-Datensatz zum Ausprobieren von `stats --demo`."""
    dishes = []
    base_monday = datetime(2026, 5, 25)
    soups = [
        "Erbsensuppe mit Speck", "Kürbissuppe mit Kokosmilch", "Toskanische Bohnensuppe",
        "Kartoffelcremesuppe mit Croutons", "Tomaten-Parmesan-Suppe",
    ]
    schnitzels = [
        "Paniertes Schnitzel | Paprikarahmsoße | Pommes frites",
        "Paniertes Schnitzel vom Hähnchen | Jägersoße | Pommes frites",
        "Paniertes Schweineschnitzel | Champignonrahmsoße | Bratkartoffeln",
    ]
    pizzas = ["Pizza Speciale | Schinken | Champignons", "Pizza Margherita | Basilikum", "Pizza Diavolo | Salami"]
    fish = ["Knusperfisch | Remouladensauce | Petersilienkartoffeln", "Gebratenes Lachsfilet | Wildreis"]
    veggies = [
        ("Moroccan Bowl | Harissa-Süßkartoffeln | Couscous", "Vegan"),
        ("Champignon-Pfanne | Knoblauch-Dipp | Drillinge", "Vegetarisch"),
        ("Spaghetti in 7 Kräuterpesto | Kirschtomaten", "Vegan"),
    ]
    one_hits = ["Hirschgulasch aus heimischer Jagd | Butterspätzle", "Trüffel-Tagliatelle | frischer Sommertrüffel"]

    for w_idx in range(num_weeks):
        monday = base_monday + timedelta(weeks=w_idx)
        kw, year = monday.isocalendar()[1], monday.isocalendar()[0]
        for d_idx, wday in enumerate(["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]):
            dt = (monday + timedelta(days=d_idx)).strftime("%Y-%m-%d")
            dishes.append(Dish(
                kw=kw, jahr=year, datum=dt, wochentag=wday, kategorie="Suppe",
                gericht=soups[(w_idx * 5 + d_idx) % len(soups)], preis_mitarbeiter="2,80 €", preis_gaeste="4,60 €",
            ))
            if wday == "Donnerstag":
                ls1 = schnitzels[w_idx % len(schnitzels)]
            elif wday == "Freitag":
                ls1 = fish[w_idx % len(fish)]
            elif w_idx == 4 and d_idx == 1:
                ls1 = one_hits[0]
            elif w_idx == 8 and d_idx == 2:
                ls1 = one_hits[1]
            else:
                ls1 = "Saftiges Kotelett | Schmorzwiebel | Bratkartoffeln" if d_idx % 2 == 0 else "Dönerteller vom Hähnchen | Pommes"
            dishes.append(Dish(
                kw=kw, jahr=year, datum=dt, wochentag=wday, kategorie="Leibspeise 1",
                gericht=ls1, preis_mitarbeiter="4,60 €", preis_gaeste="7,90 €",
            ))
            v_dish, v_diet = veggies[(w_idx * 5 + d_idx) % len(veggies)]
            dishes.append(Dish(
                kw=kw, jahr=year, datum=dt, wochentag=wday, kategorie="Leibspeise 2",
                gericht=v_dish, preis_mitarbeiter="4,60 €", preis_gaeste="7,90 €", eigenschaften=v_diet,
            ))
            ls3 = pizzas[w_idx % len(pizzas)] if wday == "Donnerstag" else "Tagesgericht"
            dishes.append(Dish(
                kw=kw, jahr=year, datum=dt, wochentag=wday, kategorie="Leibspeise 3",
                gericht=ls3, preis_mitarbeiter="4,60 €", preis_gaeste="7,90 €",
            ))
            dishes.append(Dish(
                kw=kw, jahr=year, datum=dt, wochentag=wday, kategorie="Salatbar",
                gericht="Salatbar", preis_mitarbeiter="4,60 €", preis_gaeste="3,00 € / 5,80 €",
            ))
    return dishes
