import unittest
import sys
import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from speiseplan import Dish, DayMenu, WeekMenu


class TestDishModel(unittest.TestCase):
    """Tests für das Dish-Datenmodell."""

    def test_dish_creation_full(self):
        dish = Dish(
            kw=43,
            jahr=2026,
            datum="2026-10-22",
            wochentag="Donnerstag",
            kategorie="Leibspeise 1",
            gericht="Paniertes Schnitzel mit Pommes frites",
            preis_mitarbeiter="4,60 €",
            preis_gaeste="7,90 €",
            eigenschaften="Fleisch",
            kalorien="250 kcal*",
            allergene="1,4,7",
        )
        self.assertEqual(dish.kw, 43)
        self.assertEqual(dish.jahr, 2026)
        self.assertEqual(dish.datum, "2026-10-22")
        self.assertEqual(dish.wochentag, "Donnerstag")
        self.assertEqual(dish.kategorie, "Leibspeise 1")
        self.assertEqual(dish.preis_mitarbeiter, "4,60 €")
        self.assertEqual(dish.preis_gaeste, "7,90 €")

    def test_dish_serialization_roundtrip(self):
        original = Dish(
            kw=43,
            jahr=2026,
            datum="2026-10-21",
            wochentag="Mittwoch",
            kategorie="Leibspeise 2",
            gericht="Moroccan Bowl",
            preis_mitarbeiter="4,60 €",
            preis_gaeste="7,90 €",
            eigenschaften="Vegan",
            kalorien="200 kcal*",
            allergene="4,11,13",
        )
        data_dict = original.to_dict()
        self.assertIsInstance(data_dict, dict)
        self.assertEqual(data_dict["gericht"], "Moroccan Bowl")
        self.assertEqual(data_dict["eigenschaften"], "Vegan")

        reconstructed = Dish.from_dict(data_dict)
        self.assertEqual(reconstructed, original)

    def test_dish_from_dict_defaults(self):
        minimal_dict = {
            "kw": "43",
            "jahr": "2026",
            "datum": "2026-10-20",
            "wochentag": "Dienstag",
            "kategorie": "Suppe",
        }
        dish = Dish.from_dict(minimal_dict)
        self.assertEqual(dish.kw, 43)
        self.assertEqual(dish.jahr, 2026)
        self.assertEqual(dish.gericht, "")
        self.assertEqual(dish.preis_mitarbeiter, "")
        self.assertEqual(dish.allergene, "")


class TestDayMenuModel(unittest.TestCase):
    """Tests für das DayMenu-Datenmodell."""

    def test_day_menu_structure(self):
        dish1 = Dish(kw=43, jahr=2026, datum="2026-10-19", wochentag="Montag", kategorie="Suppe", gericht="Erbsensuppe")
        dish2 = Dish(kw=43, jahr=2026, datum="2026-10-19", wochentag="Montag", kategorie="Leibspeise 1", gericht="Leberkäse")
        dm = DayMenu(wochentag="Montag", datum="2026-10-19", dishes=[dish1, dish2])

        self.assertEqual(dm.wochentag, "Montag")
        self.assertEqual(dm.datum, "2026-10-19")
        self.assertEqual(len(dm.dishes), 2)
        self.assertEqual(dm.dishes[0].gericht, "Erbsensuppe")


class TestWeekMenuModel(unittest.TestCase):
    """Tests für das WeekMenu-Datenmodell."""

    def setUp(self):
        self.dish_mo = Dish(kw=43, jahr=2026, datum="2026-10-19", wochentag="Montag", kategorie="Suppe", gericht="Erbsensuppe")
        self.dish_di = Dish(kw=43, jahr=2026, datum="2026-10-20", wochentag="Dienstag", kategorie="Suppe", gericht="Kürbissuppe")
        self.week = WeekMenu(
            kw=43,
            jahr=2026,
            start_date="2026-10-19",
            end_date="2026-10-23",
            days={
                "Montag": DayMenu(wochentag="Montag", datum="2026-10-19", dishes=[self.dish_mo]),
                "Dienstag": DayMenu(wochentag="Dienstag", datum="2026-10-20", dishes=[self.dish_di]),
            },
        )

    def test_all_dishes(self):
        all_d = self.week.all_dishes()
        self.assertEqual(len(all_d), 2)
        self.assertIn(self.dish_mo, all_d)
        self.assertIn(self.dish_di, all_d)

    def test_get_day_case_insensitive(self):
        dm1 = self.week.get_day("Montag")
        dm2 = self.week.get_day("montag")
        dm3 = self.week.get_day("MONTAG")
        self.assertIsNotNone(dm1)
        self.assertEqual(dm1, dm2)
        self.assertEqual(dm1, dm3)

    def test_get_day_not_found(self):
        dm = self.week.get_day("Sonntag")
        self.assertIsNone(dm)


if __name__ == "__main__":
    unittest.main()
