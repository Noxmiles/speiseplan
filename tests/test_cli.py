import unittest
import subprocess
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_SCRIPT = os.path.join(PROJECT_DIR, "speiseplan.py")


class TestCLIIntegration(unittest.TestCase):
    """Integrationstests für die CLI speiseplan.py über echte Subprozesse."""

    def run_cli(self, args: list) -> subprocess.CompletedProcess:
        cmd = [sys.executable, CLI_SCRIPT] + args
        return subprocess.run(
            cmd,
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=25,
        )

    def test_cli_help(self):
        res = self.run_cli(["--help"])
        self.assertEqual(res.returncode, 0)
        self.assertIn("Speiseplan CLI - HessenTreff", res.stdout)
        self.assertIn("heute", res.stdout)
        self.assertIn("search", res.stdout)
        self.assertIn("alert", res.stdout)

    def test_cli_hilfe_keyword(self):
        for kw in ["hilfe", "help"]:
            res = self.run_cli([kw])
            self.assertEqual(res.returncode, 0)
            self.assertIn("Speiseplan CLI - HessenTreff", res.stdout)
            self.assertIn("BEFEHLE & ECHTE BEISPIELE", res.stdout)

    def test_cli_install_help(self):
        for arg in ["--install-help", "install-help"]:
            res = self.run_cli([arg])
            self.assertEqual(res.returncode, 0)
            self.assertIn("TESSERACT-OCR", res.stdout)
            self.assertIn("Ubuntu / Debian", res.stdout)
            self.assertIn("Rocky / AlmaLinux", res.stdout)
            self.assertIn("Arch Linux", res.stdout)
            self.assertIn("Windows 11 (Terminal / winget)", res.stdout)
            self.assertIn("Windows 11 (Manuell ohne winget)", res.stdout)
            self.assertIn("https://github.com/UB-Mannheim/tesseract/wiki", res.stdout)

    def test_cli_heute(self):
        res = self.run_cli(["heute"])
        self.assertEqual(res.returncode, 0)
        self.assertIn("Suppe:", res.stdout)
        self.assertIn("Leibspeise 1:", res.stdout)
        self.assertIn("Salatbar", res.stdout)

    def test_cli_morgen(self):
        res = self.run_cli(["morgen"])
        self.assertEqual(res.returncode, 0)
        if "geschlossen" in res.stdout:
            self.assertIn("Kantine hat geschlossen", res.stdout)
        else:
            self.assertIn("Suppe:", res.stdout)
            self.assertIn("Leibspeise 1:", res.stdout)

    def test_cli_wochentag_freitag(self):
        res = self.run_cli(["freitag"])
        self.assertEqual(res.returncode, 0)
        self.assertIn("Freitag", res.stdout)
        self.assertIn("Suppe:", res.stdout)
        self.assertIn("Leibspeise 1:", res.stdout)

    def test_cli_woche(self):
        res = self.run_cli(["woche"])
        self.assertEqual(res.returncode, 0)
        self.assertIn("SPEISEPLAN KW", res.stdout)
        for wday in ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]:
            self.assertIn(wday, res.stdout)

    def test_cli_search_found(self):
        res = self.run_cli(["search", "Schnitzel"])
        self.assertEqual(res.returncode, 0)
        self.assertIn("Suchergebnisse im Archiv für 'Schnitzel'", res.stdout)
        self.assertIn("Zuletzt im Angebot:", res.stdout)
        self.assertIn("Schnitzel", res.stdout)

    def test_cli_search_not_found(self):
        res = self.run_cli(["search", "EinVölligUnbekanntesGericht123"])
        self.assertEqual(res.returncode, 0)
        self.assertIn("Keine Einträge für", res.stdout)

    def test_cli_watch_workflow(self):
        # 0. Vorher aufräumen, falls durch vorherige Testabbrüche vorhanden
        self.run_cli(["watch", "remove", "Currywurst"])

        # 1. Hinzufügen
        res_add = self.run_cli(["watch", "add", "Currywurst"])
        self.assertEqual(res_add.returncode, 0)
        self.assertIn("zur Watchlist hinzugefügt", res_add.stdout)

        # 2. Prüfen in list
        res_list = self.run_cli(["watch", "list"])
        self.assertEqual(res_list.returncode, 0)
        self.assertIn("Currywurst", res_list.stdout)

        # 3. Entfernen
        res_rm = self.run_cli(["watch", "remove", "Currywurst"])
        self.assertEqual(res_rm.returncode, 0)
        self.assertIn("aus Watchlist entfernt", res_rm.stdout)

    def test_cli_alert_silent_no_match(self):
        # Temporär nur einen Begriff in der Watchlist, der NICHT auf der Karte steht
        self.run_cli(["watch", "remove", "Schnitzel"])
        self.run_cli(["watch", "remove", "Pizza"])
        self.run_cli(["watch", "add", "Kaviar"])

        res_alert = self.run_cli(["alert"])
        self.assertEqual(res_alert.returncode, 0)
        # Muss absolut stumm sein!
        self.assertEqual(res_alert.stdout.strip(), "")

        # Aufräumen
        self.run_cli(["watch", "remove", "Kaviar"])

    def test_cli_alert_silent_with_match(self):
        # Schnitzel steht auf der Karte am Donnerstag
        self.run_cli(["watch", "add", "Schnitzel"])

        res_alert = self.run_cli(["alert"])
        self.assertEqual(res_alert.returncode, 0)
        self.assertIn("hey, Donnerstag gibt es Schnitzel!", res_alert.stdout)

        # Aufräumen
        self.run_cli(["watch", "remove", "Schnitzel"])


if __name__ == "__main__":
    unittest.main()
