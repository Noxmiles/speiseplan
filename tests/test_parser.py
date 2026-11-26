import os
import sys
import unittest
import tempfile
import shutil

# Pfad erweitern
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TESTS_DIR)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from speiseplan import Dish, DayMenu, WeekMenu, WatchlistManager
import speiseplan as storage
import speiseplan as ocr


class TestSpeiseplan(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_dish_model(self):
        d = Dish(
            kw=43,
            jahr=2026,
            datum="2026-10-22",
            wochentag="Donnerstag",
            kategorie="Leibspeise 1",
            gericht="Paniertes Schnitzel vom Schwein",
            preis_mitarbeiter="4,60 €",
            preis_gaeste="7,90 €",
            eigenschaften="",
            kalorien="250 kcal*",
            allergene="1,4,7",
        )
        d_dict = d.to_dict()
        self.assertEqual(d_dict["kw"], 43)
        self.assertEqual(d_dict["wochentag"], "Donnerstag")

        d_reconstructed = Dish.from_dict(d_dict)
        self.assertEqual(d_reconstructed.gericht, "Paniertes Schnitzel vom Schwein")

    def test_storage_save_and_load(self):
        d = Dish(
            kw=43,
            jahr=2026,
            datum="2026-10-19",
            wochentag="Montag",
            kategorie="Suppe",
            gericht="Erbsensuppe mit Speck",
            preis_mitarbeiter="2,80 €",
            preis_gaeste="4,60 €",
        )
        week = WeekMenu(
            kw=43,
            jahr=2026,
            start_date="2026-10-19",
            end_date="2026-10-23",
            days={"Montag": DayMenu(wochentag="Montag", datum="2026-10-19", dishes=[d])},
        )
        csv_file = storage.save_week_csv(week, data_dir=self.tmp_dir)
        self.assertTrue(os.path.exists(csv_file))

        loaded = storage.load_week_csv(csv_file)
        self.assertEqual(loaded.kw, 43)
        self.assertEqual(len(loaded.days["Montag"].dishes), 1)
        self.assertEqual(loaded.days["Montag"].dishes[0].gericht, "Erbsensuppe mit Speck")

    def test_archive_deduplication_and_search(self):
        d1 = Dish(
            kw=42,
            jahr=2026,
            datum="2026-10-15",
            wochentag="Donnerstag",
            kategorie="Leibspeise 1",
            gericht="Crispy Chicken Burger mit Pommes",
        )
        d2 = Dish(
            kw=43,
            jahr=2026,
            datum="2026-10-22",
            wochentag="Donnerstag",
            kategorie="Leibspeise 1",
            gericht="Paniertes Schnitzel mit Pommes",
        )
        week1 = WeekMenu(kw=42, jahr=2026, start_date="2026-10-12", end_date="2026-10-16",
                         days={"Donnerstag": DayMenu(wochentag="Donnerstag", datum="2026-10-15", dishes=[d1])})
        week2 = WeekMenu(kw=43, jahr=2026, start_date="2026-10-19", end_date="2026-10-23",
                         days={"Donnerstag": DayMenu(wochentag="Donnerstag", datum="2026-10-22", dishes=[d2])})

        count1 = storage.update_archive_csv(week1, data_dir=self.tmp_dir)
        self.assertEqual(count1, 1)

        # Update mit zweiter Woche
        count2 = storage.update_archive_csv(week2, data_dir=self.tmp_dir)
        self.assertEqual(count2, 2)

        # Nochmal week2 einspeisen -> darf keine Duplikate erzeugen
        count3 = storage.update_archive_csv(week2, data_dir=self.tmp_dir)
        self.assertEqual(count3, 2)

        # Suche nach Burger
        res_burger = storage.search_archive("burger", data_dir=self.tmp_dir)
        self.assertEqual(len(res_burger), 1)
        self.assertEqual(res_burger[0].datum, "2026-10-15")
        self.assertIn("Crispy Chicken Burger", res_burger[0].gericht)

        # Suche nach Pommes
        res_pommes = storage.search_archive("pommes", data_dir=self.tmp_dir)
        self.assertEqual(len(res_pommes), 2)
        # Sortierung: neueste zuerst
        self.assertEqual(res_pommes[0].datum, "2026-10-22")
        self.assertEqual(res_pommes[1].datum, "2026-10-15")

    def test_watchlist_manager(self):
        wl_file = os.path.join(self.tmp_dir, "watchlist.json")
        wm = WatchlistManager(filepath=wl_file)

        # Hinzufügen
        self.assertTrue(wm.add("Burger"))
        self.assertFalse(wm.add("Burger"))  # Duplikat
        self.assertTrue(wm.add("Schnitzel"))

        self.assertIn("Burger", wm.list_keywords())
        self.assertIn("Schnitzel", wm.list_keywords())

        # Test auf WeekMenu Treffer
        d = Dish(
            kw=43,
            jahr=2026,
            datum="2026-10-22",
            wochentag="Donnerstag",
            kategorie="Leibspeise 1",
            gericht="Paniertes Schnitzel vom Schwein",
        )
        week = WeekMenu(kw=43, jahr=2026, start_date="2026-10-19", end_date="2026-10-23",
                        days={"Donnerstag": DayMenu(wochentag="Donnerstag", datum="2026-10-22", dishes=[d])})

        hits = wm.check_menu(week)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][0], "Schnitzel")

        alerts = wm.format_alerts(hits, detailed=False)
        self.assertEqual(alerts, ["hey, Donnerstag gibt es Schnitzel!"])

        # Entfernen
        self.assertTrue(wm.remove("Schnitzel"))
        self.assertFalse(wm.remove("Schnitzel"))
        self.assertNotIn("Schnitzel", wm.list_keywords())

    def test_cell_cleaning(self):
        sample_raw = "Spaghetti in\n7 Krduterpesto\ngeschmolzene Tomaten\n4\n200kcal*"
        dish, cal, alg = ocr.clean_cell_text(sample_raw)
        self.assertEqual(cal, "200kcal*")
        self.assertEqual(alg, "4")
        self.assertIn("Kräuterpesto", dish)
        self.assertIn("geschmolzene Tomaten", dish)

    def test_sample_image_parsing(self):
        sample_img = os.path.join(PROJECT_DIR, "sample_menu.png")
        if not os.path.exists(sample_img):
            self.skipTest("sample_menu.png nicht vorhanden")

        menu = ocr.parse_menu_image(sample_img)
        self.assertEqual(menu.kw, 44)
        self.assertEqual(menu.jahr, 2026)
        self.assertEqual(len(menu.days), 5)
        self.assertIn("Montag", menu.days)
        self.assertIn("Freitag", menu.days)

        # Donnerstag prüfen (Schnitzel)
        do_dishes = [d.gericht for d in menu.days["Donnerstag"].dishes]
        self.assertTrue(any("Schnitzel" in g for g in do_dishes))

    def test_modern_images_parsing(self):
        """Prüft, ob der moderne Parser sowohl KW 44 als auch KW 45 dynamisch und fehlerfrei erkennt."""
        img_kw44 = os.path.join(PROJECT_DIR, "data", "images", "Bildschirmfoto-2026-10-25-um-15.24.18-1.png")
        img_kw45 = os.path.join(PROJECT_DIR, "data", "images", "Bildschirmfoto-2026-11-02-um-03.29.15.png")

        if os.path.exists(img_kw44):
            from PIL import Image
            im1 = Image.open(img_kw44)
            h_lines1, v_lines1 = ocr.detect_grid(im1)
            self.assertEqual(len(h_lines1), 7)
            self.assertEqual(len(v_lines1), 7)

            m1 = ocr.parse_menu_image(img_kw44)
            self.assertEqual(m1.kw, 44)
            # 20 echte Gerichte (ohne die 5 generischen 'Tagesgericht'-Platzhalter)
            self.assertEqual(len(m1.all_dishes()), 20)
            # Prüfen auf Suppe als 1. Kategorie
            self.assertEqual(m1.days["Montag"].dishes[0].kategorie, "Suppe")
            self.assertIn("Frankfurter", m1.days["Montag"].dishes[0].gericht)

        if os.path.exists(img_kw45):
            from PIL import Image
            im2 = Image.open(img_kw45)
            h_lines2, v_lines2 = ocr.detect_grid(im2)
            self.assertEqual(len(h_lines2), 7)
            self.assertEqual(len(v_lines2), 7)

            m2 = ocr.parse_menu_image(img_kw45)
            self.assertEqual(m2.kw, 45)
            # 20 echte Gerichte (Leibspeise 3 mit nur 'Tagesgericht' wird ausgeblendet)
            self.assertEqual(len(m2.all_dishes()), 20)
            # Montag Gerichte
            self.assertIn("Italienische Nudelsuppe", m2.days["Montag"].dishes[0].gericht)
            self.assertIn("Schweinesteak", m2.days["Montag"].dishes[1].gericht)
            self.assertIn("Spinatknödel", m2.days["Montag"].dishes[2].gericht)
            # Donnerstag Schnitzel
            self.assertTrue(any("Schnitzel" in d.gericht for d in m2.days["Donnerstag"].dishes))

    def test_pdf_menu_parsing_kw47(self):
        """Prüft den direkten PDF-Parser inkl. Ebenenfilterung (Korrektur-PDF) und Spalte-0-Veggie-Erkennung."""
        pdf_kw47 = os.path.join(PROJECT_DIR, "data", "images", "HessenTreff_KW47_2026_Korrektur_v3.pdf")
        if not os.path.exists(pdf_kw47):
            self.skipTest("KW47 PDF nicht im lokalen Cache")
        if not ocr.find_poppler_tool("pdftoppm") or not ocr.find_poppler_tool("pdftohtml"):
            self.skipTest("Poppler (pdftoppm/pdftohtml) nicht installiert")

        m = ocr.parse_menu_file(pdf_kw47)
        self.assertEqual(m.kw, 47)
        self.assertEqual(m.jahr, 2026)
        self.assertEqual(m.start_date, "2026-11-16")
        self.assertEqual(m.end_date, "2026-11-20")
        self.assertEqual(len(m.all_dishes()), 20)

        mo = m.days["Montag"].dishes
        self.assertEqual(mo[0].gericht, "Kokos-Möhrensuppe")
        self.assertEqual(mo[1].gericht, "Puten-Schlemmer-Schnitzel Sauce Béarnaise Kroketten")
        self.assertEqual(mo[2].eigenschaften, "Vegetarisch")

        fr = m.days["Freitag"].dishes
        self.assertEqual(fr[1].gericht, "Fischfilet Müllerin Art Petersilienkartoffeln")
        self.assertEqual(fr[2].gericht, "Spätzle-Pilzpfanne Frankfurter grüne Kräuter")
        self.assertEqual(fr[2].eigenschaften, "Vegetarisch")


if __name__ == "__main__":
    unittest.main()
