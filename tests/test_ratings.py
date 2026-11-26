import unittest
import os
import sys
import tempfile
import shutil
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from speiseplan import RatingManager, CanteenAnalytics


class TestRatingManagerTiming(unittest.TestCase):
    """Prüft die Zeitfenster-Regeln für heutige und gestrige Gerichte."""

    def test_today_before_1130_is_not_yet(self):
        # Dienstag, 27.10.2026, 11:15 Uhr
        dt = datetime(2026, 10, 27, 11, 15, 0)
        res = RatingManager.is_rating_open("2026-10-27", current_dt=dt)
        self.assertFalse(res["open"])
        self.assertEqual(res["reason"], "not_yet")

    def test_today_at_1130_is_open(self):
        # Dienstag, 27.10.2026, 11:30 Uhr
        dt = datetime(2026, 10, 27, 11, 30, 0)
        res = RatingManager.is_rating_open("2026-10-27", current_dt=dt)
        self.assertTrue(res["open"])
        self.assertEqual(res["reason"], "open")

    def test_today_afternoon_is_open(self):
        # Dienstag, 27.10.2026, 14:45 Uhr
        dt = datetime(2026, 10, 27, 14, 45, 0)
        res = RatingManager.is_rating_open("2026-10-27", current_dt=dt)
        self.assertTrue(res["open"])
        self.assertEqual(res["reason"], "open")

    def test_yesterday_dish_on_tuesday_before_1130_is_open(self):
        # Dienstag, 27.10.2026, 09:30 Uhr -> Gestriges Gericht von Montag (26.10.2026)
        dt = datetime(2026, 10, 27, 9, 30, 0)
        res = RatingManager.is_rating_open("2026-10-26", current_dt=dt)
        self.assertTrue(res["open"])
        self.assertEqual(res["reason"], "open")

    def test_yesterday_dish_on_tuesday_after_1130_remains_open(self):
        # Dienstag, 27.10.2026, 14:00 Uhr -> Gestriges Gericht bleibt nun ganztägig offen
        dt = datetime(2026, 10, 27, 14, 0, 0)
        res = RatingManager.is_rating_open("2026-10-26", current_dt=dt)
        self.assertTrue(res["open"])
        self.assertEqual(res["reason"], "open")

    def test_day_before_yesterday_on_wednesday_before_1130_is_open(self):
        # Mittwoch, 28.10.2026, 09:30 Uhr -> Gericht von Montag (26.10.2026) bis 11:30 Uhr bewertbar
        dt = datetime(2026, 10, 28, 9, 30, 0)
        res = RatingManager.is_rating_open("2026-10-26", current_dt=dt)
        self.assertTrue(res["open"])
        self.assertEqual(res["reason"], "open")

    def test_day_before_yesterday_on_wednesday_after_1130_is_expired(self):
        # Mittwoch, 28.10.2026, 11:30 Uhr -> Gericht von Montag (26.10.2026) ab 11:30 Uhr abgelaufen
        dt = datetime(2026, 10, 28, 11, 30, 0)
        res = RatingManager.is_rating_open("2026-10-26", current_dt=dt)
        self.assertFalse(res["open"])
        self.assertEqual(res["reason"], "expired")

    def test_monday_cannot_rate_friday(self):
        # Montag, 26.10.2026, 10:00 Uhr -> Freitag der Vorwoche (23.10.2026) ist abgelaufen
        dt = datetime(2026, 10, 26, 10, 0, 0)
        res = RatingManager.is_rating_open("2026-10-23", current_dt=dt)
        self.assertFalse(res["open"])
        self.assertEqual(res["reason"], "expired")

    def test_monday_cannot_rate_sunday(self):
        # Montag, 26.10.2026, 10:00 Uhr -> Gestern war Sonntag (Tag 1 = Montag-Regel)
        dt = datetime(2026, 10, 26, 10, 0, 0)
        res = RatingManager.is_rating_open("2026-10-25", current_dt=dt)
        self.assertFalse(res["open"])
        self.assertEqual(res["reason"], "expired")

    def test_older_than_yesterday_is_expired(self):
        # Donnerstag, 29.10.2026, 10:00 Uhr -> Montag (26.10.2026) ist abgelaufen
        dt = datetime(2026, 10, 29, 10, 0, 0)
        res = RatingManager.is_rating_open("2026-10-26", current_dt=dt)
        self.assertFalse(res["open"])
        self.assertEqual(res["reason"], "expired")

    def test_future_date_is_future(self):
        # Dienstag, 27.10.2026 -> Mittwoch (28.10.2026) ist noch nicht dran
        dt = datetime(2026, 10, 27, 12, 0, 0)
        res = RatingManager.is_rating_open("2026-10-28", current_dt=dt)
        self.assertFalse(res["open"])
        self.assertEqual(res["reason"], "future")


class TestRatingManagerCategoriesAndLimits(unittest.TestCase):
    """Prüft Kategorie-Zuordnung und Limitierung auf 1 Hauptgericht / 1 Suppe pro Tag."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.ratings_file = os.path.join(self.tmp_dir, "test_ratings.json")
        self.rm = RatingManager(self.ratings_file)
        self.dt_open = datetime(2026, 10, 27, 12, 0, 0) # Dienstag Mittag

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_normalize_category_type(self):
        self.assertEqual(RatingManager.normalize_category_type("Leibspeise 1"), "hauptgericht")
        self.assertEqual(RatingManager.normalize_category_type("Leibspeise 2"), "hauptgericht")
        self.assertEqual(RatingManager.normalize_category_type("Leibspeise 3"), "hauptgericht")
        self.assertEqual(RatingManager.normalize_category_type("Pizza"), "hauptgericht")
        self.assertEqual(RatingManager.normalize_category_type("Aktion"), "hauptgericht")
        self.assertEqual(RatingManager.normalize_category_type("Suppe"), "suppe")
        self.assertEqual(RatingManager.normalize_category_type("Tagessuppe"), "suppe")
        self.assertIsNone(RatingManager.normalize_category_type("Salatbar"))
        self.assertIsNone(RatingManager.normalize_category_type("Salatbuffet"))
        self.assertIsNone(RatingManager.normalize_category_type("Dessert"))

    def test_add_rating_success(self):
        dev_hash = RatingManager.hash_device_token("dev_123", "Mozilla/5.0")
        res = self.rm.add_rating(
            dish_date="2026-10-27",
            kategorie="Leibspeise 1",
            dish_title="Saftiger Schweinerücken Thymianjus Kartoffelklöße",
            stars=5,
            device_hash=dev_hash,
            current_dt=self.dt_open,
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["stars"], 5)
        self.assertEqual(res["dish_canonical"], "Schweinerücken")
        self.assertEqual(res["summary"]["count"], 1)
        self.assertEqual(res["summary"]["avg"], 5.0)

    def test_cannot_rate_salatbar(self):
        dev_hash = RatingManager.hash_device_token("dev_123", "Mozilla/5.0")
        res = self.rm.add_rating(
            dish_date="2026-10-27",
            kategorie="Salatbar",
            dish_title="Großes Salatbuffet",
            stars=4,
            device_hash=dev_hash,
            current_dt=self.dt_open,
        )
        self.assertFalse(res["success"])
        self.assertIn("Kategorie kann nicht bewertet werden", res["error"])

    def test_invalid_stars_rejected(self):
        dev_hash = RatingManager.hash_device_token("dev_123", "Mozilla/5.0")
        res0 = self.rm.add_rating("2026-10-27", "Leibspeise 1", "Schnitzel", 0, dev_hash, self.dt_open)
        res6 = self.rm.add_rating("2026-10-27", "Leibspeise 1", "Schnitzel", 6, dev_hash, self.dt_open)
        self.assertFalse(res0["success"])
        self.assertFalse(res6["success"])

    def test_single_main_dish_per_day_limit(self):
        dev_hash = RatingManager.hash_device_token("dev_123", "Mozilla/5.0")
        # 1. Hauptgericht bewerten -> OK
        r1 = self.rm.add_rating(
            "2026-10-27", "Leibspeise 1", "Schnitzel vom Schwein", 5, dev_hash, self.dt_open
        )
        self.assertTrue(r1["success"])

        # 2. Versuch, ein zweites Hauptgericht am selben Tag zu bewerten -> Abgelehnt
        r2 = self.rm.add_rating(
            "2026-10-27", "Leibspeise 2", "Champignon-Pfanne", 4, dev_hash, self.dt_open
        )
        self.assertFalse(r2["success"])
        self.assertIn("Hauptgericht bewertet", r2["error"])

        # 3. Suppe am selben Tag bewerten -> Erlaubt!
        r3 = self.rm.add_rating(
            "2026-10-27", "Suppe", "Kürbiscremesuppe", 4, dev_hash, self.dt_open
        )
        self.assertTrue(r3["success"])

        # 4. Zweite Suppe am selben Tag -> Abgelehnt
        r4 = self.rm.add_rating(
            "2026-10-27", "Suppe", "Erbsensuppe", 3, dev_hash, self.dt_open
        )
        self.assertFalse(r4["success"])
        self.assertIn("Suppe bewertet", r4["error"])

    def test_different_devices_can_both_vote(self):
        dev1 = RatingManager.hash_device_token("user_laptop", "Chrome")
        dev2 = RatingManager.hash_device_token("user_phone", "Safari")

        r1 = self.rm.add_rating("2026-10-27", "Leibspeise 1", "Schnitzel", 5, dev1, self.dt_open)
        r2 = self.rm.add_rating("2026-10-27", "Leibspeise 1", "Schnitzel", 3, dev2, self.dt_open)

        self.assertTrue(r1["success"])
        self.assertTrue(r2["success"])
        summary = self.rm.get_dish_summary("2026-10-27", "Schnitzel")
        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["avg"], 4.0)

    def test_undo_rating_within_8s_success(self):
        dev = RatingManager.hash_device_token("user_device", "Firefox")
        dt_0 = datetime(2026, 10, 27, 12, 0, 0)
        # 1. Ursprüngliche Wertung: 3 Sterne für Schweinebraten
        r1 = self.rm.add_rating("2026-10-27", "Leibspeise 1", "Schweinebraten", 3, dev, dt_0)
        self.assertTrue(r1["success"])
        self.assertEqual(self.rm.get_dish_summary("2026-10-27", "Schweinebraten")["count"], 1)

        # 2. Rückgängig machen nach 5 Sekunden
        dt_undo = datetime(2026, 10, 27, 12, 0, 5)
        res_undo = self.rm.undo_rating("2026-10-27", "Leibspeise 1", "Schweinebraten", dev, dt_undo)
        self.assertTrue(res_undo["success"])
        self.assertTrue(res_undo.get("undone", False))

        # Wertung muss komplett weg sein!
        self.assertEqual(self.rm.get_dish_summary("2026-10-27", "Schweinebraten")["count"], 0)
        self.assertEqual(self.rm.get_dish_summary("2026-10-27", "Schweinebraten")["formatted"], "–")

    def test_undo_rating_allows_rating_different_dish(self):
        dev = RatingManager.hash_device_token("user_device", "Firefox")
        dt_0 = datetime(2026, 10, 27, 12, 0, 0)
        # 1. Aus Versehen Leibspeise 1 (Burger) bewertet
        r1 = self.rm.add_rating("2026-10-27", "Leibspeise 1", "Burger", 4, dev, dt_0)
        self.assertTrue(r1["success"])

        # 2. Direkt innerhalb von 4 Sekunden rückgängig gemacht
        dt_undo = datetime(2026, 10, 27, 12, 0, 4)
        res_undo = self.rm.undo_rating("2026-10-27", "Leibspeise 1", "Burger", dev, dt_undo)
        self.assertTrue(res_undo["success"])

        # 3. Nun das eigentlich gemeinte andere Hauptgericht (Schnitzel) bewerten -> Jetzt erlaubt!
        dt_new = datetime(2026, 10, 27, 12, 0, 6)
        r2 = self.rm.add_rating("2026-10-27", "Leibspeise 2", "Schnitzel", 5, dev, dt_new)
        self.assertTrue(r2["success"])
        self.assertEqual(self.rm.get_dish_summary("2026-10-27", "Schnitzel")["avg"], 5.0)
        self.assertEqual(self.rm.get_dish_summary("2026-10-27", "Burger")["count"], 0)

    def test_undo_rating_after_11s_rejected(self):
        dev = RatingManager.hash_device_token("user_device", "Firefox")
        dt_0 = datetime(2026, 10, 27, 12, 0, 0)
        r1 = self.rm.add_rating("2026-10-27", "Leibspeise 1", "Pasta Pesto", 4, dev, dt_0)
        self.assertTrue(r1["success"])

        # Versuch nach 15 Sekunden (über 8s + 3s Puffer) rückgängig zu machen -> Abgelehnt!
        dt_late = datetime(2026, 10, 27, 12, 0, 15)
        res_undo = self.rm.undo_rating("2026-10-27", "Leibspeise 1", "Pasta Pesto", dev, dt_late)
        self.assertFalse(res_undo["success"])
        self.assertIn("abgelaufen", res_undo["error"])
        # Wertung bleibt bei 4 Sternen
        self.assertEqual(self.rm.get_dish_summary("2026-10-27", "Pasta Pesto")["avg"], 4.0)
        self.assertEqual(self.rm.get_dish_summary("2026-10-27", "Pasta Pesto")["count"], 1)

    def test_undo_rating_nonexistent_fails(self):
        dev = RatingManager.hash_device_token("nobody", "Firefox")
        res = self.rm.undo_rating("2026-10-27", "Leibspeise 1", "Nicht Da", dev)
        self.assertFalse(res["success"])


class TestRatingManagerAggregations(unittest.TestCase):
    """Prüft die Bewertungs-Bündelung strikt nach Datum + Gericht sowie Top-Rated Ranglisten."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.ratings_file = os.path.join(self.tmp_dir, "test_ratings.json")
        self.rm = RatingManager(self.ratings_file)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_date_and_dish_scoping(self):
        # Vorwoche (12.11.): Schnitzel mit Rahmsauce -> 5 Sterne
        dt_kw46 = datetime(2026, 11, 12, 12, 0, 0)
        dish_old = "Paniertes Schnitzel Schwein oder Hähnchen Rahmsauce Pommes frites"
        self.rm.add_rating("2026-11-12", "Leibspeise 1", dish_old, 5, "dev_a", dt_kw46)

        # Diese Woche (19.11.): Schnitzel mit Gorgonzolasauce -> 1 Stern
        dt_kw47 = datetime(2026, 11, 19, 12, 0, 0)
        dish_new = "Paniertes Schnitzel Schwein oder Hähnchen Gorgonzolasauce Pommes frites"
        self.rm.add_rating("2026-11-19", "Leibspeise 1", dish_new, 1, "dev_b", dt_kw47)

        # Gleiches Datum, zweites Gerät für neues Schnitzel -> 3 Sterne -> Schnitt 2,0 nur am 19.11.
        self.rm.add_rating("2026-11-19", "Leibspeise 1", dish_new, 3, "dev_c", dt_kw47)

        sum_old = self.rm.get_dish_summary("2026-11-12", dish_old)
        sum_new = self.rm.get_dish_summary("2026-11-19", dish_new)
        self.assertEqual(sum_old["count"], 1)
        self.assertEqual(sum_old["avg"], 5.0)
        self.assertEqual(sum_new["count"], 2)
        self.assertEqual(sum_new["avg"], 2.0)

        # Selbst bei exakt identischem Titel bleiben verschiedene Daten getrennt
        self.rm.add_rating("2026-11-26", "Leibspeise 1", dish_new, 4, "dev_d", datetime(2026, 11, 26, 12, 0, 0))
        self.assertEqual(self.rm.get_dish_summary("2026-11-19", dish_new)["count"], 2)
        self.assertEqual(self.rm.get_dish_summary("2026-11-26", dish_new)["count"], 1)
        self.assertEqual(self.rm.get_dish_summary("2026-11-26", dish_new)["avg"], 4.0)

    def test_get_top_rated_dishes(self):
        dt = datetime(2026, 10, 27, 12, 0, 0)
        self.rm.add_rating("2026-10-27", "Leibspeise 1", "Burger Deluxe", 5, "dev_1", dt)
        self.rm.add_rating("2026-10-27", "Leibspeise 2", "Falafel Bowl", 2, "dev_2", dt)

        top = self.rm.get_top_rated_dishes(min_votes=1, limit=5)
        self.assertEqual(len(top), 2)
        self.assertEqual(top[0]["dish"], "Burger Deluxe")
        self.assertEqual(top[0]["datum"], "2026-10-27")
        self.assertEqual(top[0]["avg"], 5.0)
        self.assertEqual(top[1]["dish"], "Falafel Bowl")
        self.assertEqual(top[1]["avg"], 2.0)


if __name__ == "__main__":
    unittest.main()
