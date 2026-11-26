import unittest
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from speiseplan import (
    Dish, CanteenAnalytics, split_components, render_ascii_bar,
    generate_demo_archive, fix_dangling_components, get_canonical_dish
)


class TestCanteenAnalytics(unittest.TestCase):
    """Tests für das Analytics-Modul."""

    @classmethod
    def setUpClass(cls):
        # 20 Wochen Demodaten für statistische Tests
        cls.dishes = generate_demo_archive(20)
        cls.ca = CanteenAnalytics(cls.dishes)

    def test_overview_metrics(self):
        ov = self.ca.get_overview()
        self.assertEqual(ov["total_dishes"], 500)
        self.assertEqual(ov["total_weeks"], 20)
        self.assertIn("Vegan", ov["diet_distribution"])
        self.assertIn("Vegetarisch", ov["diet_distribution"])
        self.assertIn("meat_distribution", ov)
        self.assertIn("Geflügel (Huhn / Pute)", ov["meat_distribution"])
        self.assertIn("Schwein", ov["meat_distribution"])
        self.assertGreater(ov["avg_price_employee"], 3.0)
        self.assertGreater(ov["staples_count"], 10)

    def test_analyze_dish_pizza_mostly_thursday(self):
        res = self.ca.analyze_dish("Pizza")
        self.assertTrue(res["found"])
        self.assertEqual(res["count"], 20)
        # Pizza sollte im Datensatz nur donnerstags sein
        self.assertIn("Donnerstag", res["weekday_distribution"])
        self.assertEqual(res["weekday_distribution"]["Donnerstag"], 20)
        self.assertNotIn("Montag", res["weekday_distribution"])

    def test_analyze_combos_schnitzel_sauces_and_sides(self):
        res = self.ca.analyze_combos("Schnitzel")
        self.assertTrue(res["found"])
        # Top-Soßen prüfen
        sauce_names = [s[0].lower() for s in res["top_sauces"]]
        self.assertTrue(any("paprikarahmsoße" in s for s in sauce_names))
        self.assertTrue(any("jägersoße" in s for s in sauce_names))

        # Top-Beilagen prüfen
        side_names = [s[0].lower() for s in res["top_sides"]]
        self.assertTrue(any("pommes" in s for s in side_names))

    def test_analyze_weekday_friday_fish(self):
        res = self.ca.analyze_weekday("Freitag")
        self.assertEqual(res["weekday"], "Freitag")
        self.assertEqual(res["count"], 100)
        self.assertGreater(res["fish_dishes_count"], 10)

    def test_lifecycle_staples_and_one_hits(self):
        res = self.ca.get_lifecycle()
        self.assertGreater(len(res["staples"]), 5)
        self.assertGreater(res["one_hit_total"], 0)
        one_hits_str = " ".join(res["one_hit_wonders"])
        self.assertTrue("Hirschgulasch" in one_hits_str or "Trüffel" in one_hits_str)

    def test_split_components(self):
        text = "Paniertes Schnitzel | Paprikarahmsoße | Pommes frites mit Ketchup"
        comps = split_components(text)
        self.assertIn("Paniertes Schnitzel", comps)
        self.assertIn("Paprikarahmsoße", comps)
        self.assertIn("Pommes frites", comps)
        self.assertIn("Ketchup", comps)

    def test_render_ascii_bar(self):
        bar_full = render_ascii_bar(10, 10, bar_length=10)
        self.assertEqual(bar_full, "▇" * 10)
        bar_half = render_ascii_bar(5, 10, bar_length=10)
        self.assertEqual(bar_half, "▇" * 5 + "░" * 5)
        bar_zero = render_ascii_bar(0, 10, bar_length=10)
        self.assertEqual(bar_zero, "░" * 10)

    def test_fix_dangling_components(self):
        # Zeilenumbruch mit "vom"
        raw1 = "Paniertes Schnitzel vom | Schwein oder Hähnchen | Paprikarahmsoße | Pommes frites"
        self.assertEqual(
            fix_dangling_components(raw1),
            "Paniertes Schnitzel vom Schwein oder Hähnchen | Paprikarahmsoße | Pommes frites"
        )
        # Zeilenumbruch mit "in"
        raw2 = "Saftiges Kotelett in | feiner Knusperpanade | Schmorzwiebel"
        self.assertEqual(
            fix_dangling_components(raw2),
            "Saftiges Kotelett in feiner Knusperpanade | Schmorzwiebel"
        )
        # Zeilenumbruch mit Bindestrich
        raw3 = "Toskanische- | Bohnensuppe"
        self.assertEqual(fix_dangling_components(raw3), "Toskanische Bohnensuppe")

        # Randfall: Präposition am Anfang des Folgeblocks
        raw4 = "Paniertes Schnitzel | vom Schwein | Pommes frites"
        self.assertEqual(fix_dangling_components(raw4), "Paniertes Schnitzel vom Schwein | Pommes frites")

        # Randfall: Präposition mit Satzzeichen
        raw5 = "Paniertes Schnitzel vom, | Schwein"
        self.assertEqual(fix_dangling_components(raw5), "Paniertes Schnitzel vom, Schwein")

        # Randfall: Leere / Whitespace-Eingaben
        self.assertEqual(fix_dangling_components(""), "")
        self.assertEqual(fix_dangling_components("   "), "")
        self.assertEqual(fix_dangling_components("|||"), "")

    def test_get_canonical_dish_all_three_canteens(self):
        # HessenTreff Gerichte
        self.assertEqual(get_canonical_dish("Paniertes Schnitzel vom | Schwein oder Hähnchen | Paprikarahmsoße"), "Schnitzel vom Schwein oder Hähnchen")
        self.assertEqual(get_canonical_dish("Saftiges Kotelett in | feiner Knusperpanade | Schmorzwiebel"), "Kotelett in feiner Knusperpanade")
        self.assertEqual(get_canonical_dish("Herzhafter Leberkäse | Spiegelei | Rahmspinat"), "Leberkäse")
        self.assertEqual(get_canonical_dish("Spaghetti in | 7 Kräuterpesto | geschmolzene Tomaten"), "Spaghetti in 7 Kräuterpesto")
        self.assertEqual(get_canonical_dish("Ofenfrische Pizza Speciale | Schinken | Mozzarella"), "Pizza Speciale")
        self.assertEqual(get_canonical_dish("“Moroccan Bowl“ | Harissa-Süßkartoffeln"), "Moroccan Bowl")

        # Kaiberg Kitchen meets DOW Gerichte
        self.assertEqual(get_canonical_dish("Schweinegulasch \"Hausfrauen Art\" | Paprika | Zwiebeln"), "Schweinegulasch Hausfrauen Art")
        self.assertEqual(get_canonical_dish("Hähnchen-Cordon-Bleu | Schmorzwiebel | Bratkartoffeln"), "Hähnchen-Cordon-Bleu")
        self.assertEqual(get_canonical_dish("Knusprig ausgebackenes Seelachsfilet | Salzkartoffeln"), "Seelachsfilet")
        self.assertEqual(get_canonical_dish("Schwedische Köttbullar (Schwein oder Geflügel) | Sahne-Rahmsauce"), "Schwedische Köttbullar (Schwein oder Geflügel)")

        # Kaiberg Kitchen meets SevenGardens Gerichte
        self.assertEqual(get_canonical_dish("Pulled Pork Burger | Coleslaw | Tomate"), "Pulled Pork Burger")
        self.assertEqual(get_canonical_dish("Medaillons von der Schweinelende | Steinpilzrahmsauce"), "Medaillons von der Schweinelende")
        self.assertEqual(get_canonical_dish("Knusprig paniertes Hähnchen „Sweet & Sour“ | Wokgemüse"), "Hähnchen Sweet & Sour")
        self.assertEqual(get_canonical_dish("\"Herbst-Bowl\" | Ofenkürbis | Hirse"), "Herbst-Bowl")
        self.assertEqual(get_canonical_dish("Ofenfrische Pizza Salami | Kirschtomaten | Käse"), "Pizza Salami")
        self.assertEqual(get_canonical_dish("Steinpilz-Cappelletti | feine Gorgonzolacreme"), "Steinpilz-Cappelletti")

        # Komplett neues, unbekanntes Gericht (wird ohne Vokabelliste sauber verarbeitet)
        self.assertEqual(get_canonical_dish("Shakshuka mit Fladenbrot | Hirtenkäse"), "Shakshuka mit Fladenbrot")
        self.assertEqual(get_canonical_dish("Kasslerbraten an Sauerkraut | Kartoffelpüree"), "Kasslerbraten an Sauerkraut")

        # Gerichte ohne Pipe-Trennstriche (wie im bereinigten Archiv)
        self.assertEqual(
            get_canonical_dish("Paniertes Schnitzel vom Schwein oder Hähnchen Paprikarahmsoße Pommes frites"),
            "Schnitzel vom Schwein oder Hähnchen"
        )
        self.assertEqual(
            get_canonical_dish("Paniertes Schnitzel vom Schwein oder Hähnchen Sauce Hollandaise Pommes frites"),
            "Schnitzel vom Schwein oder Hähnchen"
        )
        self.assertEqual(
            get_canonical_dish("Herzhafter Leberkäse Spiegelei Rahmspinat cremiger Kartoffelpüree"),
            "Leberkäse"
        )
        self.assertEqual(
            get_canonical_dish("Knusprig ausgebackenes Seelachsfilet Salzkartoffeln Remoulade"),
            "Seelachsfilet"
        )

        # Randfall: Reines Schmuckadjektiv (darf niemals leer zurückgeben)
        self.assertEqual(get_canonical_dish("Knusprig"), "Knusprig")
        self.assertEqual(get_canonical_dish(""), "")


if __name__ == "__main__":
    unittest.main()
