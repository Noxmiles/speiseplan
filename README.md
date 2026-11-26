# Speiseplan Scraper & CLI (HessenTreff im HMdI)

Ein leicht verständliches Python-3-Projekt, das automatisch die wöchentliche Speisekarte des Betriebsrestaurants **„HessenTreff im HMdI“** von [kaiberg-kitchen.de](https://kaiberg-kitchen.de) abruft, ausliest, als saubere CSV-Dateien speichert und über Terminal oder GitHub Actions bereitstellt.

---

## Wie funktioniert das System? (Überblick)

```text
kaiberg-kitchen.de
   │
   ▼  1. Suchen & Herunterladen (speiseplan_core/scraper.py)
      Findet die Kantine "HessenTreff" -> bevorzugt PDF, sonst Vorschaubild
   │
   ▼  2. Tabelle & Text auslesen (speiseplan_core/parser.py)
      PDF direkt via Poppler (`pdftohtml` + `pdftoppm`)
      └─ Fallback bei Scan-PDF / Screenshot: Tesseract OCR (`deu`)
   │
   ▼  3. Bereinigen (speiseplan_core/text_cleaning.py)
      Trennt Gericht, Kalorien & Allergene; erkennt Vegetarisch/Vegan-Siegel
   │
   ▼  4. Speichern & Nutzen (speiseplan_core/storage.py)
      data/kwXX_YYYY.csv + data/archive.csv
      ├─ Terminal-CLI: `speiseplan.py` (`heute`, `woche`, `search`, `stats`, `watch`)
      └─ Auto-Sync:    `sync_daily.py` + GitHub Actions (`.github/workflows/`)
```

---

## Projektstruktur & Wegweiser durch den Code

Wenn du den Code verstehen oder in einer anderen Sprache (z. B. **Java**) nachbauen möchtest, ist dies der schnellste Einstieg:

| Datei / Ordner | Aufgabe | Wichtigste Funktionen / Klassen |
| :--- | :--- | :--- |
| [speiseplan.py](speiseplan.py) | Ausführbarer Einstiegspunkt fürs Terminal + Wegweiser-Kommentar | `main()`, re-exportiert `speiseplan_core` |
| [speiseplan_core/config.py](speiseplan_core/config.py) | Pfade, URL, CSV-Spalten & Suche nach `poppler` / `tesseract` | `CSV_COLUMNS`, `find_poppler_tool()`, `find_tesseract_binary()` |
| [speiseplan_core/models.py](speiseplan_core/models.py) | Datenstruktur einer Speise / eines Tages / einer Woche | `Dish`, `DayMenu`, `WeekMenu` |
| [speiseplan_core/scraper.py](speiseplan_core/scraper.py) | Findet PDF oder Bild genau für die gewünschte Kantine | `get_menu_source_url()`, `fetch_latest_menu_source()` |
| [speiseplan_core/parser.py](speiseplan_core/parser.py) | PDF-Tabellenparser + Bild-OCR-Fallback + Siegel-Erkennung | `parse_menu_file()`, `parse_menu_pdf()`, `parse_menu_image()`, `detect_grid()`, `detect_diet_badge()` |
| [speiseplan_core/text_cleaning.py](speiseplan_core/text_cleaning.py) | Entfernt Allergen-Ziffern/Kalorien, fixt Umbrüche & OCR-Umlaute | `clean_cell_text()`, `parse_category_cell()`, `get_canonical_dish()` |
| [speiseplan_core/storage.py](speiseplan_core/storage.py) | Schreibt/liest Wochen-CSVs und das deduplizierte Archiv | `save_week_csv()`, `update_archive_csv()`, `search_archive()` |
| [speiseplan_core/watchlist.py](speiseplan_core/watchlist.py) | Lieblingsgerichte merken & Treffer melden | `WatchlistManager` |
| [speiseplan_core/analytics.py](speiseplan_core/analytics.py) | Fleischarten, Klassiker vs. Eintagsfliegen, Soßen/Beilagen | `CanteenAnalytics`, `generate_demo_archive()` |
| [speiseplan_core/ratings.py](speiseplan_core/ratings.py) | Bewertungsregeln (pro Datum + Gericht, Zeitfenster, Undo) | `RatingManager` |
| [speiseplan_core/cli.py](speiseplan_core/cli.py) | Verarbeitung aller Terminal-Befehle | `ensure_week_menu()`, `cmd_show()`, `cmd_stats()` |
| [sync_daily.py](sync_daily.py) | Täglicher Sync + Upload per HTTPS-Webhook (oder SFTP) | `run_sync()`, `upload_via_webhook()` |
| [.github/workflows/speiseplan-sync.yml](.github/workflows/speiseplan-sync.yml) | Zeitgesteuerter GitHub-Actions-Lauf | installiert Poppler + Tesseract, startet `sync_daily.py --force` |
| [tests/](tests/) | Automatisierte Unit- & Integrationstests | `python3 tests/run_all_tests.py` |

---

## Besonderheiten der Speisepläne (wichtig für Nachbauten, z. B. in Java)

Kaiberg Kitchen veröffentlicht wöchentlich ein einseitiges Querformat-PDF (mit Vorschaubild auf der Webseite). Folgende Eigenheiten löst dieser Code gezielt:

1. **Mehrere Kantinen auf einer Seite (`scraper.py`):**
   Auf `kaiberg-kitchen.de` stehen *Seven Gardens*, *HessenTreff im HMdI* und *Dow Silicones* auf derselben Seite. Der Scraper sucht die Überschrift der Zielkantine und stoppt streng vor der nächsten Kantinen-Überschrift. Falls nötig, folgt er dem Link *„Zum Standort“* (`/hessentreff-im-hmdi/`).
   *(In Java z. B. mit **Jsoup** umsetzbar.)*

2. **Verdeckte zweite Textebene in Korrektur-PDFs (`_extract_visible_pdf_nodes` in `parser.py`):**
   Manche korrigierten PDFs enthalten zwei übereinanderliegende Textebenen (eine neue korrigierte Ebene obenauf und eine alte, überdeckte Vorlage darunter). Würde man nur reinen Text extrahieren, bekäme man alles doppelt.
   **Lösung hier:** Seite 1 wird kurz gerendert (`pdftoppm`), das sichtbare Tabellenraster erkannt (`detect_grid`) und jeder XML-Textblock auf Seitenränder sowie dunkle Pixel im gerenderten Bild geprüft.
   *(In Java z. B. mit **Apache PDFBox**: Text-Koordinaten via `PDFTextStripperByArea` / Bounding Boxes mit gerenderter Seite abgleichen und ggf. **Tess4J** als OCR-Fallback nutzen.)*

3. **Vegetarisch-/Vegan-Siegel in Spalte 0 (`detect_diet_badge`):**
   Ein grüner Kreis (**Vegetarisch**) oder oranger Kreis (**Vegan**) steht manchmal nicht in jeder Tageszelle einzeln, sondern links in **Spalte 0** (z. B. direkt neben *Leibspeise 2*). Deshalb wird erst Spalte 0 zeilenweise geprüft und die Eigenschaft an alle Gerichte dieser Zeile vererbt, sofern die einzelne Zelle kein eigenes Siegel hat.

4. **Platzhalter ausblenden:**
   Einträge, die nach dem Bereinigen nur `Tagesgericht` (z. B. in *Leibspeise 3*) oder leer sind, werden beim Parsen und Speichern übersprungen.

5. **Bewertungsregeln (`ratings.py`):**
   - Bewertet wird **immer die Kombination aus Datum + vollständigem Gerichtsnamen** (`YYYY-MM-DD|Gericht`), damit ein Schnitzel von dieser Woche nicht mit dem von letzter Woche vermischt wird.
   - Zeitfenster: am Tag selbst ab **11:30 Uhr**, am Folgetag ganztägig und am übernächsten Tag noch bis **11:29:59 Uhr** (Wochenende ausgenommen).
   - Maximal 1 Hauptgericht + 1 Suppe pro Tag/Gerät; innerhalb von **8 Sekunden** rückgängig machbar.

---

## Datenformat (CSV)

Alle Wochenpläne (`data/kwXX_YYYY.csv`) und das Archiv (`data/archive.csv`) nutzen UTF-8 mit Semikolon (`;`) als Trennzeichen:

```csv
kw;jahr;datum;wochentag;kategorie;gericht;preis_mitarbeiter;preis_gaeste;eigenschaften;kalorien;allergene
47;2026;2026-11-16;Montag;Suppe;Kokos-Möhrensuppe;2,80 €;4,60 €;;70 kcal**;
47;2026;2026-11-16;Montag;Leibspeise 1;Puten-Schlemmer-Schnitzel Sauce Béarnaise Kroketten;4,60 €;7,90 €;;230 kcal*;
47;2026;2026-11-16;Montag;Leibspeise 2;Vollkornpenne Vegetarische Kürbisbolognese Kirschtomaten;4,60 €;7,90 €;Vegetarisch;130 kcal*;
```

---

## Installation & Voraussetzungen

Benötigt wird **Python 3** sowie:
1. **Python-Pakete:**
   ```bash
   pip install -r requirements.txt
   ```
   *(Installiert `beautifulsoup4`, `requests`, `pillow` und `numpy`.)*

2. **Poppler-Tools (für direktes PDF-Auslesen ohne OCR):**
   - **Ubuntu / Debian:** `sudo apt install poppler-utils`
   - **Fedora / RHEL:** `sudo dnf install poppler-utils`
   - **Arch Linux:** `sudo pacman -S poppler`
   - **macOS (Homebrew):** `brew install poppler`

3. **Tesseract OCR (optional, als automatischer Bild-/Scan-Fallback):**
   - **Ubuntu / Debian:** `sudo apt install tesseract-ocr tesseract-ocr-deu`
   - **Fedora / RHEL:** `sudo dnf install tesseract tesseract-langpack-deu`
   - **Arch Linux:** `sudo pacman -S tesseract tesseract-data-deu`
   - **macOS:** `brew install tesseract tesseract-lang`
   - **Windows 11:** `winget install UB-Mannheim.TesseractOCR`

> **Tipp:** Mit `./speiseplan.py --install-help` prüfst du jederzeit den lokalen Status. Abfragen bereits gespeicherter CSVs (`heute`, `search`, `stats`) funktionieren auch ganz ohne Poppler/Tesseract.

---

## Nutzung im Terminal

```bash
# Heutiges, morgiges oder komplettes Wochenmenü anzeigen
./speiseplan.py heute
./speiseplan.py morgen
./speiseplan.py donnerstag
./speiseplan.py woche
./speiseplan.py update              # Plan live von Website neu laden

# Im Archiv suchen
./speiseplan.py search "Schnitzel"

# Statistiken & Fleischarten-Auswertung (mit --demo sofort ohne eigenes Archiv testbar)
./speiseplan.py stats --demo
./speiseplan.py stats dish "Pizza" --demo
./speiseplan.py stats combos "Schnitzel" --demo
./speiseplan.py stats weekday freitag --demo
./speiseplan.py stats lifecycle --demo
./speiseplan.py stats --demo --json

# Watchlist & stiller Cronjob-Check
./speiseplan.py watch add "Burger"
./speiseplan.py watch list
./speiseplan.py alert               # Bleibt stumm, außer es gibt einen Treffer
```

Beispiel für einen Cronjob (jeden Montag um 08:30 Uhr Desktop-Benachrichtigung bei Treffer):
```crontab
30 8 * * 1 /pfad/zu/speiseplan/speiseplan.py alert | while read line; do notify-send "Kantine" "$line"; done
```

---

## GitHub Actions (Automatisches Update)

Der Workflow [.github/workflows/speiseplan-sync.yml](.github/workflows/speiseplan-sync.yml) läuft automatisch nach Zeitplan (und manuell per *Run workflow*).  
Damit der Upload per Webhook funktioniert, muss im GitHub-Repository unter **Settings → Secrets and variables → Actions** das Secret **`SYNC_TOKEN`** hinterlegt sein – im Code selbst stehen keine Zugangsdaten.

---

## Tests ausführen

```bash
python3 tests/run_all_tests.py
```

*(Führt die Offline-Unit- und CLI-Integrationstests aus. Tests für lokale Beispielbilder/-PDFs werden automatisch übersprungen, falls die lokalen Cache-Dateien auf einem frischen System nicht vorliegen.)*
