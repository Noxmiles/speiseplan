import unittest
import os
import sys
from PIL import Image

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import speiseplan as ocr


class TestOCRTextCleaning(unittest.TestCase):
    """Tests für Text-Normalisierung, Bereinigung von Allergenen und Kalorien."""

    def test_normalize_ocr_umlauts(self):
        raw = "Herzhafter Leberkdse mit cremigem Kartoffelpiiree und Kurbissuppe"
        norm = ocr.normalize_ocr_text(raw)
        self.assertIn("Leberkäse", norm)
        self.assertIn("Kartoffelpüree", norm)
        self.assertIn("Kürbissuppe", norm)

    def test_normalize_kaiberg_kitchen_vocabulary(self):
        cases = [
            ("Kirbissuppe", "Kürbissuppe"),
            ("Hokkaido-Kirbis", "Hokkaido-Kürbis"),
            ("Hdhnchen-Cordon-Bleu", "Hähnchen-Cordon-Bleu"),
            ("Krduterpesto", "Kräuterpesto"),
            ("gerostete Kurbiskerne", "geröstete Kürbiskerne"),
            ("gerdsteter Blumenkohl", "gerösteter Blumenkohl"),
            ("Butterspdtzle", "Butterspätzle"),
            ("KartoffelkloRe", "Kartoffelklöße"),
            ("MarkkldRchen", "Markklößchen"),
            ("PaprikarahmsoRe", "Paprikarahmsoße"),
            ("Truffelol", "Trüffelöl"),
            ("Frihlingsrellichen", "Frühlingsröllchen"),
            ("Kdsespatzle", "Käsespätzle"),
        ]
        for raw, expected in cases:
            self.assertEqual(ocr.normalize_ocr_text(raw), expected)

    def test_clean_cell_with_calories_and_allergens(self):
        raw = "Paniertes Schnitzel vom\nSchwein oder Hähnchen\nPaprikarahmsoße\nPommes frites\n1,4,7,10,11\n250kcal*"
        dish, cal, alg = ocr.clean_cell_text(raw)
        self.assertEqual(cal, "250kcal*")
        self.assertEqual(alg, "1,4,7,10,11")
        self.assertIn("Paniertes Schnitzel vom", dish)
        self.assertIn("Paprikarahmsoße", dish)
        self.assertIn("Pommes frites", dish)
        self.assertNotIn("250kcal*", dish)
        self.assertNotIn("1,4,7,10,11", dish)

    def test_clean_cell_with_ocr_typos_in_calories(self):
        raw = "Tomaten-Parmesan-Suppe\n7\n35 kecal**"
        dish, cal, alg = ocr.clean_cell_text(raw)
        self.assertEqual(cal, "35 kecal**")
        self.assertEqual(alg, "7")
        self.assertEqual(dish, "Tomaten-Parmesan-Suppe")

    def test_clean_cell_krauterpesto_not_stripped_as_calorie(self):
        raw = "Spaghetti in\n7 Kräuterpesto\ngeschmolzene Tomaten\n4\n200kcal*"
        dish, cal, alg = ocr.clean_cell_text(raw)
        self.assertEqual(cal, "200kcal*")
        self.assertEqual(alg, "4")
        self.assertIn("7 Kräuterpesto", dish)
        self.assertIn("geschmolzene Tomaten", dish)

    def test_clean_dish_title_trailing_allergens_and_footnotes(self):
        # 1. Tortellini mit Fußnote 147
        d1 = ocr.clean_dish_title("Tortellini cremige Sahnesauce Champignons Erbsen Grana Padano 147")
        self.assertEqual(d1, "Tortellini cremige Sahnesauce Champignons Erbsen Grana Padano")

        # 2. Toskanische Bohnensuppe mit Allergen 'a )'
        d2 = ocr.clean_dish_title("Toskanische Bohnensuppe a )")
        self.assertEqual(d2, "Toskanische Bohnensuppe")

        # 3. Moroccan Bowl mit ', 4,.11,13 ®©'
        d3 = ocr.clean_dish_title("“Moroccan Bowl“ Harissa-Süßkartoffeln orientalischer Couscous Kichererbsen Datteln Granatapfel Cremige Mango-Soja-Sauce, 4,.11,13 ®©")
        self.assertEqual(d3, "“Moroccan Bowl“ Harissa-Süßkartoffeln orientalischer Couscous Kichererbsen Datteln Granatapfel Cremige Mango-Soja-Sauce")

    def test_parse_category_cell_prices(self):
        # Leibspeise
        text_ls = "Leibspeise 1\nMitarbeiter 4,60€\nGäste 7,90€"
        name, p_ma, p_gaeste = ocr.parse_category_cell(text_ls)
        self.assertEqual(name, "Leibspeise 1")
        self.assertIn("4,60", p_ma)
        self.assertIn("7,90", p_gaeste)

        # Suppe
        text_suppe = "Suppe\n2,80€ / 4,60€"
        name_s, p_ma_s, p_gaeste_s = ocr.parse_category_cell(text_suppe)
        self.assertEqual(name_s, "Suppe")
        self.assertEqual(p_ma_s, "2,80 €")
        self.assertEqual(p_gaeste_s, "4,60 €")


class TestOCRGridAndImageParsing(unittest.TestCase):
    """Tests für Grid-Erkennung und Parsing des Test-Speiseplans."""

    @classmethod
    def setUpClass(cls):
        cls.sample_path = os.path.join(PROJECT_DIR, "sample_menu.png")
        if not os.path.exists(cls.sample_path):
            raise unittest.SkipTest("sample_menu.png nicht verfügbar")
        cls.image = Image.open(cls.sample_path)

    def test_detect_grid_returns_seven_lines(self):
        h_lines, v_lines = ocr.detect_grid(self.image)
        self.assertEqual(len(h_lines), 7)
        self.assertEqual(len(v_lines), 7)
        # Monoton steigend
        self.assertTrue(all(h_lines[i] < h_lines[i + 1] for i in range(len(h_lines) - 1)))
        self.assertTrue(all(v_lines[i] < v_lines[i + 1] for i in range(len(v_lines) - 1)))

    def test_parse_header_info(self):
        h_lines, _ = ocr.detect_grid(self.image)
        kw, jahr, start_d, end_d = ocr.parse_header_info(self.image, h_lines[0])
        self.assertEqual(kw, 44)
        self.assertEqual(jahr, 2026)
        self.assertEqual(start_d, "2026-10-26")
        self.assertEqual(end_d, "2026-10-30")

    def test_parse_menu_image_end_to_end(self):
        menu = ocr.parse_menu_image(self.sample_path)
        self.assertEqual(menu.kw, 44)
        self.assertEqual(menu.jahr, 2026)
        self.assertEqual(len(menu.days), 5)

        # Alle 5 Wochentage überspringen den inhaltsleeren Platzhalter 'Tagesgericht' -> 4 echte Gerichte pro Tag
        for wday in ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]:
            self.assertIn(wday, menu.days)
            self.assertEqual(len(menu.days[wday].dishes), 4)

        # Prüfe Vegetarisch-Siegel bei Suppe am Montag (Frankfurter Kräutersüppchen)
        dish_suppe = menu.days["Montag"].dishes[0]
        self.assertIn("Frankfurter", dish_suppe.gericht)
        self.assertEqual(dish_suppe.eigenschaften, "Vegetarisch")

        # Prüfe Vegan-Siegel bei Leibspeise 2 am Dienstag (Vegane Paella)
        dish_paella = menu.days["Dienstag"].dishes[2]
        self.assertIn("Paella", dish_paella.gericht)
        self.assertEqual(dish_paella.eigenschaften, "Vegan")

        # Prüfe Schnitzel am Donnerstag
        dish_schnitzel = menu.days["Donnerstag"].dishes[1]
        self.assertIn("Schnitzel", dish_schnitzel.gericht)


if __name__ == "__main__":
    unittest.main()
