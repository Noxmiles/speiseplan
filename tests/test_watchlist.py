import unittest
import os
import sys
import tempfile
import shutil

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from speiseplan import Dish, DayMenu, WeekMenu, WatchlistManager


class TestWatchlistCRUD(unittest.TestCase):
    """Tests für das Hinzufügen, Auflisten und Entfernen von Suchbegriffen."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.wl_file = os.path.join(self.tmp_dir, "test_watchlist.json")
        self.wm = WatchlistManager(filepath=self.wl_file)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_initial_empty(self):
        self.assertEqual(self.wm.list_keywords(), [])

    def test_add_and_list_keywords(self):
        self.assertTrue(self.wm.add("Burger"))
        self.assertTrue(self.wm.add("Schnitzel"))
        items = self.wm.list_keywords()
        self.assertEqual(len(items), 2)
        self.assertIn("Burger", items)
        self.assertIn("Schnitzel", items)

    def test_add_duplicate_case_insensitive(self):
        self.assertTrue(self.wm.add("Burger"))
        self.assertFalse(self.wm.add("Burger"))
        self.assertFalse(self.wm.add("burger"))
        self.assertFalse(self.wm.add("BURGER"))
        self.assertEqual(len(self.wm.list_keywords()), 1)

    def test_add_empty_or_whitespace(self):
        self.assertFalse(self.wm.add(""))
        self.assertFalse(self.wm.add("   "))
        self.assertEqual(self.wm.list_keywords(), [])

    def test_remove_keyword(self):
        self.wm.add("Burger")
        self.wm.add("Pizza")
        self.assertTrue(self.wm.remove("Burger"))
        self.assertNotIn("Burger", self.wm.list_keywords())
        self.assertIn("Pizza", self.wm.list_keywords())

    def test_remove_nonexistent(self):
        self.assertFalse(self.wm.remove("Döner"))


class TestWatchlistMatching(unittest.TestCase):
    """Tests für den Abgleich von Watchlist mit einem Speiseplan."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.wl_file = os.path.join(self.tmp_dir, "test_watchlist.json")
        self.wm = WatchlistManager(filepath=self.wl_file)

        # Beispiel-Woche mit verschiedenen Gerichten
        d_mo = Dish(kw=43, jahr=2026, datum="2026-10-19", wochentag="Montag", kategorie="Leibspeise 1", gericht="Herzhafter Leberkäse mit Spiegelei")
        d_di = Dish(kw=43, jahr=2026, datum="2026-10-20", wochentag="Dienstag", kategorie="Leibspeise 1", gericht="Dönerteller vom Hähnchen")
        d_do1 = Dish(kw=43, jahr=2026, datum="2026-10-22", wochentag="Donnerstag", kategorie="Leibspeise 1", gericht="Paniertes Schnitzel vom Schwein")
        d_do2 = Dish(kw=43, jahr=2026, datum="2026-10-22", wochentag="Donnerstag", kategorie="Leibspeise 3", gericht="Ofenfrische Pizza Speciale")

        self.week = WeekMenu(
            kw=43,
            jahr=2026,
            start_date="2026-10-19",
            end_date="2026-10-23",
            days={
                "Montag": DayMenu(wochentag="Montag", datum="2026-10-19", dishes=[d_mo]),
                "Dienstag": DayMenu(wochentag="Dienstag", datum="2026-10-20", dishes=[d_di]),
                "Donnerstag": DayMenu(wochentag="Donnerstag", datum="2026-10-22", dishes=[d_do1, d_do2]),
            }
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_check_menu_single_hit(self):
        self.wm.add("Schnitzel")
        hits = self.wm.check_menu(self.week)
        self.assertEqual(len(hits), 1)
        keyword, dish = hits[0]
        self.assertEqual(keyword, "Schnitzel")
        self.assertEqual(dish.wochentag, "Donnerstag")

    def test_check_menu_multiple_hits(self):
        self.wm.add("Schnitzel")
        self.wm.add("Pizza")
        self.wm.add("Döner")
        hits = self.wm.check_menu(self.week)
        self.assertEqual(len(hits), 3)

        hit_keywords = [h[0] for h in hits]
        self.assertIn("Schnitzel", hit_keywords)
        self.assertIn("Pizza", hit_keywords)
        self.assertIn("Döner", hit_keywords)

    def test_check_menu_no_hit(self):
        self.wm.add("Burger")
        self.wm.add("Sushi")
        hits = self.wm.check_menu(self.week)
        self.assertEqual(hits, [])

    def test_format_alerts_simple(self):
        self.wm.add("Burger")
        d = Dish(kw=43, jahr=2026, datum="2026-10-22", wochentag="Donnerstag", kategorie="Leibspeise 1", gericht="Smash Burger")
        hits = [("Burger", d)]

        alerts = self.wm.format_alerts(hits, detailed=False)
        self.assertEqual(alerts, ["hey, Donnerstag gibt es Burger!"])

    def test_format_alerts_detailed(self):
        d = Dish(kw=43, jahr=2026, datum="2026-10-22", wochentag="Donnerstag", kategorie="Leibspeise 1",
                 gericht="Smash Burger mit Pommes", eigenschaften="Vegetarisch")
        hits = [("Burger", d)]

        alerts = self.wm.format_alerts(hits, detailed=True)
        self.assertEqual(len(alerts), 1)
        self.assertIn("hey, Donnerstag gibt es Burger!", alerts[0])
        self.assertIn("[Vegetarisch]", alerts[0])


if __name__ == "__main__":
    unittest.main()
