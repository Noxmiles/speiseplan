import unittest
from unittest.mock import patch, MagicMock
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import speiseplan as scraper

SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
    <div class="card">
        <h3>HessenTreff im HMdI</h3>
        <figure class="wp-block-image">
            <img src="https://kaiberg-kitchen.de/wp-content/uploads/2026/10/Bildschirmfoto-small.png"
                 srcset="https://kaiberg-kitchen.de/wp-content/uploads/2026/10/Bildschirmfoto-1024.png 1024w, https://kaiberg-kitchen.de/wp-content/uploads/2026/10/Bildschirmfoto-2048.png 2048w" />
            <figcaption>Wochenkarte</figcaption>
        </figure>
    </div>
    <div class="card">
        <h3>Dow Silicone</h3>
        <figure class="wp-block-image">
            <img src="https://kaiberg-kitchen.de/wp-content/uploads/2026/10/dow.png" />
            <figcaption>Wochenkarte</figcaption>
        </figure>
    </div>
</body>
</html>
"""


NEW_FORMAT_HTML = """
<!DOCTYPE html>
<html>
<body>
    <article class="card">
        <h3>Seven Gardens</h3>
        <a href="https://kaiberg-kitchen.de/wp-content/uploads/2026/11/SevenGardens_KW47_2026_Final_v3.pdf">Wochenkarte (PDF)</a>
        <img src="https://kaiberg-kitchen.de/wp-content/uploads/2026/11/SevenGardens_KW47_2026_Final_v3-pdf.jpg" alt="Wochenkarte Seven Gardens, 16.–20. November 2026. PDF öffnen" />
    </article>
    <article class="card">
        <h3>HessenTreff im HMdI</h3>
        <a href="https://kaiberg-kitchen.de/wp-content/uploads/2026/11/HessenTreff_KW47_2026_Korrektur_v3.pdf">Wochenkarte (PDF)</a>
        <a href="/hessentreff-im-hmdi/">Zum Standort</a>
        <a href="https://kaiberg-kitchen.de/wp-content/uploads/2026/11/HessenTreff_KW47_2026_Korrektur_v3.pdf">
            <img src="https://kaiberg-kitchen.de/wp-content/uploads/2026/11/HessenTreff_KW47_2026_Korrektur_v3-pdf.jpg"
                 alt="Wochenkarte HessenTreff im HMdI, 16.–20. November 2026. PDF öffnen" />
        </a>
    </article>
    <article class="card">
        <h3>Dow Silicones</h3>
        <a href="https://kaiberg-kitchen.de/wp-content/uploads/2026/11/Dow_KW47_2026_Final_v3.pdf">Wochenkarte (PDF)</a>
    </article>
</body>
</html>
"""


class TestScraperHTMLExtraction(unittest.TestCase):
    """Tests für die HTML-Scraping-Logik von scraper.py."""

    @patch("requests.get")
    def test_get_menu_source_url_prefers_pdf_and_image_fallback(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.content = NEW_FORMAT_HTML.encode("utf-8")
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        pdf_url = scraper.get_menu_source_url(page_url="https://kaiberg-kitchen.de/", canteen="HessenTreff", prefer_pdf=True)
        self.assertEqual(pdf_url, "https://kaiberg-kitchen.de/wp-content/uploads/2026/11/HessenTreff_KW47_2026_Korrektur_v3.pdf")

        img_url = scraper.get_menu_image_url(page_url="https://kaiberg-kitchen.de/", canteen="HessenTreff")
        self.assertEqual(img_url, "https://kaiberg-kitchen.de/wp-content/uploads/2026/11/HessenTreff_KW47_2026_Korrektur_v3-pdf.jpg")

    @patch("requests.get")
    def test_get_menu_source_follows_standort_subpage_fallback(self, mock_get):
        home_html = """
        <article><h3>HessenTreff im HMdI</h3><a href="/hessentreff-im-hmdi/">Zum Standort</a></article>
        """
        sub_html = """
        <main><h1>HessenTreff im HMdI</h1><a href="https://kaiberg-kitchen.de/wp-content/uploads/2026/11/HessenTreff_KW47.pdf">Wochenkarte als PDF öffnen</a></main>
        """
        r1, r2 = MagicMock(), MagicMock()
        r1.content = home_html.encode("utf-8")
        r2.content = sub_html.encode("utf-8")
        mock_get.side_effect = [r1, r2]

        url = scraper.get_menu_source_url(page_url="https://kaiberg-kitchen.de/", canteen="HessenTreff")
        self.assertEqual(url, "https://kaiberg-kitchen.de/wp-content/uploads/2026/11/HessenTreff_KW47.pdf")
        self.assertEqual(mock_get.call_count, 2)

    @patch("requests.get")
    def test_get_menu_image_url_highest_resolution(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.content = SAMPLE_HTML.encode("utf-8")
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        url = scraper.get_menu_image_url(page_url="https://fake-url.de/", canteen="HessenTreff")
        # Sollte den 2048w Link aus dem srcset wählen
        self.assertEqual(url, "https://kaiberg-kitchen.de/wp-content/uploads/2026/10/Bildschirmfoto-2048.png")

    @patch("requests.get")
    def test_get_menu_image_url_other_canteen(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.content = SAMPLE_HTML.encode("utf-8")
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        url = scraper.get_menu_image_url(page_url="https://fake-url.de/", canteen="Dow Silicone")
        self.assertEqual(url, "https://kaiberg-kitchen.de/wp-content/uploads/2026/10/dow.png")

    @patch("requests.get")
    def test_canteen_not_found_raises_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.content = SAMPLE_HTML.encode("utf-8")
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        with self.assertRaises(ValueError) as ctx:
            scraper.get_menu_image_url(canteen="NichtExistent")
        self.assertIn("nicht gefunden", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
