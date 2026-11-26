import unittest
import os
import sys
import tempfile
import shutil
import csv

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from speiseplan import Dish, DayMenu, WeekMenu
import speiseplan as storage


class TestStorageCSV(unittest.TestCase):
    """Tests für das Speichern und Laden von Wochenplänen in CSV."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_save_and_load_week_csv(self):
        d1 = Dish(kw=43, jahr=2026, datum="2026-10-19", wochentag="Montag", kategorie="Suppe",
                  gericht="Erbsensuppe mit Speck", preis_mitarbeiter="2,80 €", preis_gaeste="4,60 €",
                  eigenschaften="", kalorien="50 kcal*", allergene="K,P,7,10")
        d2 = Dish(kw=43, jahr=2026, datum="2026-10-19", wochentag="Montag", kategorie="Leibspeise 1",
                  gericht="Herzhafter Leberkäse", preis_mitarbeiter="4,60 €", preis_gaeste="7,90 €")

        week = WeekMenu(
            kw=43,
            jahr=2026,
            start_date="2026-10-19",
            end_date="2026-10-23",
            days={"Montag": DayMenu(wochentag="Montag", datum="2026-10-19", dishes=[d1, d2])}
        )

        saved_path = storage.save_week_csv(week, data_dir=self.tmp_dir)
        self.assertTrue(os.path.exists(saved_path))
        self.assertTrue(saved_path.endswith("kw43_2026.csv"))

        # Prüfe CSV-Header
        with open(saved_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=";")
            header = next(reader)
            self.assertEqual(header, storage.CSV_COLUMNS)

        # Lade zurück
        loaded = storage.load_week_csv(saved_path)
        self.assertEqual(loaded.kw, 43)
        self.assertEqual(loaded.jahr, 2026)
        self.assertIn("Montag", loaded.days)
        self.assertEqual(len(loaded.days["Montag"].dishes), 2)
        self.assertEqual(loaded.days["Montag"].dishes[0].gericht, "Erbsensuppe mit Speck")
        self.assertEqual(loaded.days["Montag"].dishes[0].allergene, "K,P,7,10")

    def test_load_nonexistent_file(self):
        with self.assertRaises(FileNotFoundError):
            storage.load_week_csv(os.path.join(self.tmp_dir, "nonexistent.csv"))


class TestArchiveDeduplication(unittest.TestCase):
    """Tests für die Langzeitarchivierung und Vermeidung von Duplikaten."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_archive_accumulate_and_deduplicate(self):
        # Woche 42
        d_kw42 = Dish(kw=42, jahr=2026, datum="2026-10-15", wochentag="Donnerstag",
                      kategorie="Leibspeise 1", gericht="Crispy Chicken Burger mit Pommes")
        week42 = WeekMenu(kw=42, jahr=2026, start_date="2026-10-12", end_date="2026-10-16",
                          days={"Donnerstag": DayMenu(wochentag="Donnerstag", datum="2026-10-15", dishes=[d_kw42])})

        count1 = storage.update_archive_csv(week42, data_dir=self.tmp_dir)
        self.assertEqual(count1, 1)

        # Woche 43
        d_kw43 = Dish(kw=43, jahr=2026, datum="2026-10-22", wochentag="Donnerstag",
                      kategorie="Leibspeise 1", gericht="Paniertes Schnitzel")
        week43 = WeekMenu(kw=43, jahr=2026, start_date="2026-10-19", end_date="2026-10-23",
                          days={"Donnerstag": DayMenu(wochentag="Donnerstag", datum="2026-10-22", dishes=[d_kw43])})

        count2 = storage.update_archive_csv(week43, data_dir=self.tmp_dir)
        self.assertEqual(count2, 2)

        # Erneutes Einspielen von Woche 43 darf keine doppelten Zeilen erzeugen
        count3 = storage.update_archive_csv(week43, data_dir=self.tmp_dir)
        self.assertEqual(count3, 2)

        # Einspielen einer aktualisierten Version von Woche 43 (z.B. Detailänderung)
        d_kw43_updated = Dish(kw=43, jahr=2026, datum="2026-10-22", wochentag="Donnerstag",
                              kategorie="Leibspeise 1", gericht="Paniertes Schnitzel mit Pommes frites")
        week43_up = WeekMenu(kw=43, jahr=2026, start_date="2026-10-19", end_date="2026-10-23",
                             days={"Donnerstag": DayMenu(wochentag="Donnerstag", datum="2026-10-22", dishes=[d_kw43_updated])})
        count4 = storage.update_archive_csv(week43_up, data_dir=self.tmp_dir)
        self.assertEqual(count4, 2)

        # Prüfe ob aktualisierter Text im Archiv steht
        results = storage.search_archive("Schnitzel", data_dir=self.tmp_dir)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].gericht, "Paniertes Schnitzel mit Pommes frites")

    def test_multi_week_rescan_and_accumulation(self):
        """Simuliert echten Wochenübergang: KW 43 (25 Gerichte) + KW 44 (25 Gerichte) mit Mehrfach-Scans."""
        categories = ["Suppe", "Leibspeise 1", "Leibspeise 2", "Leibspeise 3", "Salatbar"]
        days = [("Montag", "19"), ("Dienstag", "20"), ("Mittwoch", "21"), ("Donnerstag", "22"), ("Freitag", "23")]

        # KW 43 bauen (25 Gerichte)
        kw43_dishes = []
        for wday, day_num in days:
            for cat in categories:
                kw43_dishes.append(Dish(
                    kw=43, jahr=2026, datum=f"2026-10-{day_num}", wochentag=wday,
                    kategorie=cat, gericht=f"{cat} KW43 {wday}"
                ))

        class MockKW43:
            def all_dishes(self):
                return kw43_dishes

        # 1. Erster Scan KW 43 -> 25 Gerichte
        count = storage.update_archive_csv(MockKW43(), data_dir=self.tmp_dir)
        self.assertEqual(count, 25)

        # 2. Zweiter und dritter Scan KW 43 (z.B. Sonntag 3x täglich) -> bleibt exakt 25
        count = storage.update_archive_csv(MockKW43(), data_dir=self.tmp_dir)
        self.assertEqual(count, 25)
        count = storage.update_archive_csv(MockKW43(), data_dir=self.tmp_dir)
        self.assertEqual(count, 25)

        # KW 44 bauen (25 neue Gerichte für nächste Woche)
        days_kw44 = [("Montag", "26"), ("Dienstag", "27"), ("Mittwoch", "28"), ("Donnerstag", "29"), ("Freitag", "30")]
        kw44_dishes = []
        for wday, day_num in days_kw44:
            for cat in categories:
                kw44_dishes.append(Dish(
                    kw=44, jahr=2026, datum=f"2026-10-{day_num}", wochentag=wday,
                    kategorie=cat, gericht=f"{cat} KW44 {wday}"
                ))

        class MockKW44:
            def all_dishes(self):
                return kw44_dishes

        # 3. Neuer Plan KW 44 trifft ein -> muss genau 50 Gerichte ergeben (25 von KW43 + 25 von KW44)
        count = storage.update_archive_csv(MockKW44(), data_dir=self.tmp_dir)
        self.assertEqual(count, 50)

        # 4. Erneuter Scan KW 44 (z.B. am Montag) -> bleibt exakt 50
        count = storage.update_archive_csv(MockKW44(), data_dir=self.tmp_dir)
        self.assertEqual(count, 50)

        # 5. Prüfe, ob alle Gerichte beider Wochen auffindbar sind
        all_archived = storage.search_archive("", data_dir=self.tmp_dir)
        # Leer-Suche gibt nichts zurück, also nach KW suchen
        s_kw43 = storage.search_archive("KW43", data_dir=self.tmp_dir)
        s_kw44 = storage.search_archive("KW44", data_dir=self.tmp_dir)
        self.assertEqual(len(s_kw43), 25)
        self.assertEqual(len(s_kw44), 25)


class TestArchiveSearch(unittest.TestCase):
    """Tests für die Suche nach historischen Gerichten im Archiv."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        # Erstelle ein Archiv mit verschiedenen Daten
        dishes = [
            Dish(kw=30, jahr=2026, datum="2026-07-23", wochentag="Donnerstag", kategorie="Leibspeise 1", gericht="Cheeseburger"),
            Dish(kw=38, jahr=2026, datum="2026-09-17", wochentag="Donnerstag", kategorie="Leibspeise 1", gericht="Bacon Burger"),
            Dish(kw=42, jahr=2026, datum="2026-10-15", wochentag="Donnerstag", kategorie="Leibspeise 1", gericht="Crispy Chicken Burger"),
            Dish(kw=43, jahr=2026, datum="2026-10-22", wochentag="Donnerstag", kategorie="Leibspeise 1", gericht="Paniertes Schnitzel"),
            Dish(kw=43, jahr=2026, datum="2026-10-22", wochentag="Donnerstag", kategorie="Leibspeise 3", gericht="Pizza Speciale"),
        ]
        class MockWeek:
            def all_dishes(self):
                return dishes

        storage.update_archive_csv(MockWeek(), data_dir=self.tmp_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_search_burger_returns_newest_first(self):
        results = storage.search_archive("burger", data_dir=self.tmp_dir)
        self.assertEqual(len(results), 3)
        # Neuestes Datum zuerst
        self.assertEqual(results[0].datum, "2026-10-15")
        self.assertEqual(results[0].gericht, "Crispy Chicken Burger")
        self.assertEqual(results[1].datum, "2026-09-17")
        self.assertEqual(results[2].datum, "2026-07-23")

    def test_search_case_insensitive(self):
        self.assertEqual(len(storage.search_archive("BURGER", data_dir=self.tmp_dir)), 3)
        self.assertEqual(len(storage.search_archive("burger", data_dir=self.tmp_dir)), 3)
        self.assertEqual(len(storage.search_archive("BuRgEr", data_dir=self.tmp_dir)), 3)

    def test_search_no_match(self):
        results = storage.search_archive("Döner", data_dir=self.tmp_dir)
        self.assertEqual(results, [])

    def test_search_empty_archive(self):
        empty_dir = tempfile.mkdtemp()
        try:
            results = storage.search_archive("Burger", data_dir=empty_dir)
            self.assertEqual(results, [])
        finally:
            shutil.rmtree(empty_dir)


class TestFindLatestLocalWeek(unittest.TestCase):
    """Tests für die Ermittlung des neuesten lokalen Wochenplans (inkl. Jahreswechsel)."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def _create_mock_week_file(self, kw: int, year: int):
        dish = Dish(kw=kw, jahr=year, datum=f"{year}-01-01", wochentag="Montag",
                    kategorie="Leibspeise 1", gericht=f"Testgericht KW {kw}/{year}")
        week = WeekMenu(kw=kw, jahr=year, start_date=f"{year}-01-01", end_date=f"{year}-01-05",
                        days={"Montag": DayMenu(wochentag="Montag", datum=f"{year}-01-01", dishes=[dish])})
        return storage.save_week_csv(week, data_dir=self.tmp_dir)

    def test_empty_dir_returns_none(self):
        self.assertIsNone(storage.find_latest_local_week(data_dir=self.tmp_dir))

    def test_same_year_ordering(self):
        self._create_mock_week_file(42, 2026)
        self._create_mock_week_file(43, 2026)
        latest = storage.find_latest_local_week(data_dir=self.tmp_dir)
        self.assertIsNotNone(latest)
        self.assertEqual(latest.kw, 43)
        self.assertEqual(latest.jahr, 2026)

    def test_year_end_transition_picks_new_year(self):
        # Alphabetische Sortierung würde kw52_2026 VOR kw01_2027 einsortieren ('kw5' > 'kw0').
        # Numerische Sortierung nach (Jahr, KW) muss zwingend kw01_2027 bevorzugen!
        self._create_mock_week_file(43, 2026)
        self._create_mock_week_file(52, 2026)
        self._create_mock_week_file(1, 2027)

        latest = storage.find_latest_local_week(data_dir=self.tmp_dir)
        self.assertIsNotNone(latest)
        self.assertEqual(latest.kw, 1)
        self.assertEqual(latest.jahr, 2027)


if __name__ == "__main__":
    unittest.main()
