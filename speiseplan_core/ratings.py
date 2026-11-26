"""
speiseplan_core/ratings.py — Bewertungslogik (Sterne, Zeitfenster, Limits & Undo).

Regeln für faire Community-Bewertungen:
1. **Strikte Zuordnung pro Datum + Gericht (`make_rating_key`):**
   Ein Schnitzel von letzter Woche und ein Schnitzel von dieser Woche werden
   strikt getrennt bewertet – so verfälscht eine schlechte Soße gestern nicht den
   Schnitt eines älteren Gerichts.
2. **Zeitfenster (`is_rating_open`):**
   - Heutige Gerichte: ab **11:30 Uhr** bewertbar.
   - Gestrige Gerichte: ganztägig bewertbar (außer montags für Sonntag).
   - Vorgestrige Gerichte: noch bis **11:29:59 Uhr** bewertbar (außer Mo/Di für Sa/So).
   - Zukünftige oder ältere Gerichte: gesperrt.
3. **Limit pro Tag & Gerät:**
   Maximal 1 Hauptgericht und 1 Suppe pro Tag (`normalize_category_type`).
   Salatbar/Dessert sind nicht bewertbar.
4. **8-Sekunden-Undo (`undo_rating`):**
   Versehentliche Klicks können innerhalb von 8 Sekunden (+3 s Netzwerkpuffer)
   zurückgezogen werden.
"""

from datetime import datetime, timedelta
import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional

from .config import RATINGS_FILE
from .text_cleaning import get_canonical_dish


class RatingManager:
    """Verwaltet Community-Bewertungen (1–5 Sterne), Zeitfenster und Tageslimits."""

    def __init__(self, filepath: str = RATINGS_FILE):
        self.filepath = filepath
        os.makedirs(os.path.dirname(os.path.abspath(self.filepath)), exist_ok=True)
        if not os.path.exists(self.filepath):
            self.save_data({"ratings": [], "device_votes": {}})

    def load_data(self) -> Dict[str, Any]:
        """Lädt `ratings.json` mit robuster Struktur-Initialisierung."""
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, dict):
                    if "ratings" not in d or not isinstance(d["ratings"], list):
                        d["ratings"] = []
                    if "device_votes" not in d or not isinstance(d["device_votes"], dict):
                        d["device_votes"] = {}
                    return d
        except Exception:
            pass
        return {"ratings": [], "device_votes": {}}

    def save_data(self, data: Dict[str, Any]) -> bool:
        """Speichert Bewertungsdaten formatiert als JSON."""
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    @staticmethod
    def normalize_dish_name(dish_title: str) -> str:
        """Bereinigt mehrfache Leerzeichen für eindeutigen Abgleich."""
        return re.sub(r"\s+", " ", (dish_title or "")).strip()

    @staticmethod
    def make_rating_key(dish_date: str, dish_title: str) -> str:
        """Eindeutiger Schlüssel aus `YYYY-MM-DD|Gerichtsname`."""
        return f"{dish_date.strip()}|{RatingManager.normalize_dish_name(dish_title)}"

    @staticmethod
    def hash_device_token(token: str, user_agent: str = "") -> str:
        """Hasht das Geräte-Token zusammen mit dem User-Agent (datensparsame ID)."""
        s = f"{token.strip()}|{user_agent.strip()}"
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    @staticmethod
    def normalize_category_type(kategorie: str) -> Optional[str]:
        """Ordnet Kategorien in `'suppe'`, `'hauptgericht'` oder `None` (nicht bewertbar) ein."""
        cat = kategorie.strip().lower()
        if "salat" in cat or "dessert" in cat or "buffet" in cat:
            return None
        if "suppe" in cat:
            return "suppe"
        return "hauptgericht"

    @staticmethod
    def is_rating_open(dish_date: str, current_dt: Optional[datetime] = None) -> Dict[str, Any]:
        """Prüft anhand des Datums und der Uhrzeit (`Europe/Berlin`), ob abgestimmt werden darf."""
        if current_dt is None:
            try:
                from zoneinfo import ZoneInfo

                now = datetime.now(ZoneInfo("Europe/Berlin"))
            except Exception:
                now = datetime.now()
        else:
            now = current_dt

        today_date = now.strftime("%Y-%m-%d")
        current_time = now.strftime("%H:%M")
        day_of_week = now.isoweekday()  # 1 = Montag, 7 = Sonntag

        if dish_date == today_date:
            if current_time >= "11:30":
                return {"open": True, "reason": "open"}
            return {"open": False, "reason": "not_yet"}

        if dish_date > today_date:
            return {"open": False, "reason": "future"}

        yesterday_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        if dish_date == yesterday_date:
            if day_of_week == 1:
                return {"open": False, "reason": "expired"}
            return {"open": True, "reason": "open"}

        before_yesterday_date = (now - timedelta(days=2)).strftime("%Y-%m-%d")
        if dish_date == before_yesterday_date:
            if day_of_week in (1, 2):
                return {"open": False, "reason": "expired"}
            if current_time < "11:30":
                return {"open": True, "reason": "open"}
            return {"open": False, "reason": "expired"}

        return {"open": False, "reason": "expired"}

    def get_user_vote(self, dish_date: str, category_type: str, device_hash: str) -> Optional[Dict[str, Any]]:
        """Gibt die gespeicherte Wertung eines Geräts für Tag & Kategorie zurück."""
        data = self.load_data()
        return data.get("device_votes", {}).get(device_hash, {}).get(dish_date, {}).get(category_type)

    def add_rating(
        self,
        dish_date: str,
        kategorie: str,
        dish_title: str,
        stars: int,
        device_hash: str,
        current_dt: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Speichert eine 1–5-Sterne-Bewertung nach Prüfung von Zeitfenster und Tageslimit."""
        if stars < 1 or stars > 5:
            return {"success": False, "error": "Ungültige Sterne-Bewertung (1-5)."}

        cat_type = self.normalize_category_type(kategorie)
        if cat_type is None:
            return {"success": False, "error": "Diese Kategorie kann nicht bewertet werden."}

        time_check = self.is_rating_open(dish_date, current_dt)
        if not time_check["open"]:
            if time_check["reason"] == "future":
                w_map = {
                    1: "Montag", 2: "Dienstag", 3: "Mittwoch", 4: "Donnerstag",
                    5: "Freitag", 6: "Samstag", 7: "Sonntag",
                }
                try:
                    w_day = w_map.get(datetime.strptime(dish_date, "%Y-%m-%d").isoweekday(), "dem Tag")
                except Exception:
                    w_day = "dem Tag"
                return {"success": False, "error": f"Bewertungen sind erst ab {w_day} um 11:30 Uhr möglich."}
            msg = (
                "Bewertung ab 11:30 Uhr."
                if time_check["reason"] == "not_yet"
                else "Das Zeitfenster für Bewertungen dieses Gerichts ist abgelaufen."
            )
            return {"success": False, "error": msg}

        data = self.load_data()
        if cat_type in data.get("device_votes", {}).get(device_hash, {}).get(dish_date, {}):
            label = "eine Suppe" if cat_type == "suppe" else "ein Hauptgericht"
            return {"success": False, "error": f"Du hast für diesen Tag bereits {label} bewertet."}

        canonical = get_canonical_dish(dish_title)
        now_dt = current_dt or datetime.now()
        now_iso = now_dt.isoformat()
        rating_id = f"rat_{hashlib.md5(f'{device_hash}_{dish_date}_{cat_type}_{now_iso}'.encode()).hexdigest()[:12]}"

        entry = {
            "id": rating_id,
            "device_hash": device_hash,
            "datum": dish_date,
            "kategorie_typ": cat_type,
            "dish_raw": dish_title,
            "dish_canonical": canonical,
            "stars": stars,
            "created_at": now_iso,
        }

        data["ratings"].append(entry)
        data.setdefault("device_votes", {}).setdefault(device_hash, {}).setdefault(dish_date, {})[cat_type] = {
            "stars": stars,
            "dish_canonical": canonical,
            "dish_raw": dish_title,
            "created_at": now_iso,
        }

        self.save_data(data)
        summary = self.get_dish_summary(dish_date, dish_title, data)
        return {
            "success": True,
            "stars": stars,
            "dish_canonical": canonical,
            "summary": summary,
        }

    def undo_rating(
        self,
        dish_date: str,
        kategorie: str,
        dish_title: str,
        device_hash: str,
        current_dt: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Zieht eine abgegebene Bewertung innerhalb von 8 Sekunden (+3 s Kulanz) zurück."""
        cat_type = self.normalize_category_type(kategorie)
        if cat_type is None:
            return {"success": False, "error": "Ungültige Kategorie."}

        data = self.load_data()
        existing = data.get("device_votes", {}).get(device_hash, {}).get(dish_date, {}).get(cat_type)
        if not existing:
            return {"success": False, "error": "Keine Wertung zum Zurückziehen gefunden."}

        now_dt = current_dt or datetime.now()
        created_at_str = existing.get("created_at")
        age_seconds = 9999
        if created_at_str:
            try:
                prev_dt = datetime.fromisoformat(created_at_str)
                age_seconds = (now_dt - prev_dt).total_seconds()
            except Exception:
                pass

        if age_seconds > 11:
            return {"success": False, "error": "Das 8-Sekunden-Zeitfenster zum Zurückziehen ist abgelaufen."}

        data["ratings"] = [
            r for r in data.get("ratings", [])
            if not (
                r.get("device_hash") == device_hash
                and r.get("datum") == dish_date
                and r.get("kategorie_typ") == cat_type
            )
        ]

        if (
            device_hash in data.get("device_votes", {})
            and dish_date in data["device_votes"][device_hash]
            and cat_type in data["device_votes"][device_hash][dish_date]
        ):
            del data["device_votes"][device_hash][dish_date][cat_type]
            if not data["device_votes"][device_hash][dish_date]:
                del data["device_votes"][device_hash][dish_date]
            if not data["device_votes"][device_hash]:
                del data["device_votes"][device_hash]

        self.save_data(data)
        canonical = get_canonical_dish(dish_title)
        summary = self.get_dish_summary(dish_date, dish_title, data)
        return {
            "success": True,
            "undone": True,
            "dish_canonical": canonical,
            "summary": summary,
        }

    def get_dish_summary(
        self, dish_date: str, dish_title: str, data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Berechnet Durchschnitt & Stimmenzahl exakt für `(dish_date, dish_title)`."""
        if data is None:
            data = self.load_data()
        target_date = dish_date.strip()
        target_dish = self.normalize_dish_name(dish_title)

        matching_stars = [
            int(r["stars"])
            for r in data.get("ratings", [])
            if (r.get("datum") or "").strip() == target_date
            and self.normalize_dish_name(r.get("dish_raw", "")) == target_dish
        ]
        count = len(matching_stars)
        if count == 0:
            return {"avg": 0.0, "count": 0, "formatted": "–"}
        avg = round(sum(matching_stars) / count, 1)
        return {"avg": avg, "count": count, "formatted": f"{avg:.1f}".replace(".", ",")}

    def get_all_summaries(self) -> Dict[str, Dict[str, Any]]:
        """Gruppiert alle Bewertungen strikt nach `YYYY-MM-DD|Gerichtsname`."""
        data = self.load_data()
        grouped: Dict[str, List[int]] = {}
        meta: Dict[str, tuple[str, str]] = {}
        for r in data.get("ratings", []):
            r_date = (r.get("datum") or "").strip()
            r_raw = self.normalize_dish_name(r.get("dish_raw") or r.get("dish_canonical") or "")
            if not r_date or not r_raw:
                continue
            key = self.make_rating_key(r_date, r_raw)
            if key not in meta:
                meta[key] = (r_date, r_raw)
            grouped.setdefault(key, []).append(int(r.get("stars", 0)))

        summaries = {}
        for key, stars_list in grouped.items():
            cnt = len(stars_list)
            avg = round(sum(stars_list) / cnt, 1)
            r_date, r_raw = meta[key]
            summaries[key] = {
                "datum": r_date,
                "dish": r_raw,
                "avg": avg,
                "count": cnt,
                "formatted": f"{avg:.1f}".replace(".", ","),
            }
        return summaries

    def get_top_rated_dishes(self, min_votes: int = 1, limit: int = 10) -> List[Dict[str, Any]]:
        """Gibt die am besten bewerteten Gerichte (pro Datum + Gericht) sortiert zurück."""
        summaries = self.get_all_summaries()
        filtered = [
            {
                "dish": info["dish"],
                "datum": info["datum"],
                "avg": info["avg"],
                "count": info["count"],
                "formatted": info["formatted"],
            }
            for info in summaries.values()
            if info["count"] >= min_votes
        ]
        filtered.sort(key=lambda x: (x["avg"], x["count"]), reverse=True)
        return filtered[:limit]
