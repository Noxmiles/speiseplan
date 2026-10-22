# Speiseplan Scraper & CLI (HessenTreff im HMdI)

Ein Python 3 Skript, das automatisch die Wochenkarte des Betriebsrestaurants **„HessenTreff im HMdI“** von [kaiberg-kitchen.de](https://kaiberg-kitchen.de) herunterlädt, per OCR analysiert, in CSV-Dateien speichert (pro Kalenderwoche und kumuliertes Langzeitarchiv), flexible Abfragen ermöglicht und dich über deine Lieblingsgerichte benachrichtigt.

---

## Funktionen

- 🔍 **Automatisches Web-Scraping:** Findet die aktuelle Wochenkarte auf `kaiberg-kitchen.de` und lädt das PNG in bester Auflösung herunter.
- 📐 **Präzise OCR & Grid-Erkennung:** Segmentiert die Speisekarte in Zeilen und Spalten via Bildanalyse und liest Gerichte, Preise (Mitarbeiter/Gäste), Kalorien sowie Siegel (`[VEGAN]`, `[VEGETARISCH]`) zellscharf aus.
- 📁 **Strukturierte CSV-Speicherung & Auto-Ordner:** Erstellt benötigte Ordner (`data/`, `data/images/`) automatisch relativ zum Skript.
  - `data/kwXX_YYYY.csv`: Kompletter Speiseplan der jeweiligen Kalenderwoche.
  - `data/archive.csv`: Fortlaufendes Langzeitarchiv aller Speisen zur historischen Recherche (automatisch dedupliziert).
- 📅 **Interaktive CLI-Abfragen:**
  - `speiseplan` oder `speiseplan heute`: Zeigt das heutige Menü.
  - `speiseplan morgen`: Menü für den nächsten Tag.
  - `speiseplan <wochentag>`: z. B. `speiseplan freitag`, `speiseplan dienstag`.
  - `speiseplan woche`: Komplette Wochenübersicht.
- 🥩 **Fleischarten- & Ernährungsanalyse:** Automatische Klassifizierung nach Schwein, Geflügel (Huhn / Pute), Rind / Kalb, Fisch / Meeresfrüchte sowie Vegetarisch und Vegan.
- 🔎 **Archivsuche:** Beantwortet z. B. *„Wann gab es zum letzten Mal Burger?“* mit exaktem Datum, Wochentag, Kategorie und Gerichtname.
- 🔔 **Watchlist & Benachrichtigungen:**
  - Verwaltung von Suchbegriffen (`speiseplan watch add/list/remove`).
  - Auffälliges Banner bei normalen Aufrufen.
  - **Silent-Modus (`speiseplan alert`):** Prüft den aktuellen Plan und gibt **nur dann** etwas aus, wenn ein Treffer vorliegt (z. B. `hey, Donnerstag gibt es Burger!`). Perfekt für Cron-Jobs, Shell-Skripte oder Login-Hooks.
- 🪟 **Single-File & 100% Windows 11 kompatibel:** Alle Module sind kompakt in `speiseplan.py` gebündelt – bereit zur Weitergabe als einzelne Datei.

---

## Installation & Voraussetzungen

Das Skript benötigt **Python 3** und für das Einlesen neuer Menü-Bilder **Tesseract OCR**. (Abfragen bereits gespeicherter Pläne funktionieren auch ohne Tesseract!)

### 1. Python-Pakete installieren:
```bash
pip install -r requirements.txt
```
*(Benötigt lediglich `requests`, `beautifulsoup4`, `Pillow` und `pytesseract`).*

### 2. Tesseract OCR installieren (falls noch nicht vorhanden):
Das Skript erkennt automatisch, falls Tesseract fehlt, und gibt maßgeschneiderte Anweisungen aus:

- **Ubuntu / Debian:**
  ```bash
  sudo apt install tesseract-ocr tesseract-ocr-deu
  ```
- **Fedora / RHEL / Rocky / AlmaLinux:**
  ```bash
  sudo dnf install tesseract tesseract-langpack-deu
  ```
- **Arch Linux / CachyOS:**
  ```bash
  sudo pacman -S tesseract tesseract-data-deu
  ```
- **Windows 11 (per Terminal / Paketmanager winget):**
  ```powershell
  winget install UB-Mannheim.TesseractOCR
  ```
- **Windows 11 (manuell ohne winget):**
  Lade den offiziellen Windows-Installer (`.exe`) von [UB-Mannheim Tesseract Wiki](https://github.com/UB-Mannheim/tesseract/wiki) herunter, führe ihn per Doppelklick aus und klicke auf *Weiter*. Das Skript findet Tesseract im Standardpfad `C:\Program Files\Tesseract-OCR\tesseract.exe` automatisch!

> **Tipp:** Du kannst den aktuellen Tesseract-Status und alle Installationshinweise jederzeit mit `./speiseplan.py --install-help` (oder `./speiseplan.py install-help`) testen!

---

## Befehlsübersicht & Beispiele

### 1. Tages- und Wochenabfragen

```bash
# Heutiges Angebot abrufen
./speiseplan.py heute

# Angebot für morgen
./speiseplan.py morgen

# Bestimmter Wochentag
./speiseplan.py donnerstag
./speiseplan.py freitag

# Gesamte Woche anzeigen
./speiseplan.py woche

# Manuelle Neuaktualisierung von der Website erzwingen
./speiseplan.py update
```

### 2. Archiv durchsuchen & Historie

```bash
# Wann gab es zuletzt Schnitzel oder Pizza?
./speiseplan.py search "Schnitzel"
./speiseplan.py search "Pizza"
```

---

### 3. Statistische Auswertungen & Analysen (`stats`)

Sobald das Archiv über mehrere Wochen wächst, liefert das Analyse-Modul detaillierte Auswertungen. Mit dem Schalter `--demo` kannst du alle Analysen sofort mit einem 20-wöchigen Beispieldatensatz testen:

```bash
# 📊 1. Gesamt-Dashboard & Kennzahlen (Top-Gerichte, Vegan-Anteil, Ø Preis)
./speiseplan.py stats
./speiseplan.py stats --demo

# 📅 2. Wochentagsmuster (z. B. "An welchem Tag gab es meistens Pizza?")
./speiseplan.py stats dish "Pizza" --demo

# 🥣 3. Soßen- & Beilagen-Analyse (z. B. "Was ist die häufigste Soße zum Schnitzel?")
./speiseplan.py stats combos "Schnitzel" --demo

# 🐟 4. Wochentags-Charakteristik (z. B. Fisch am Freitag, Suppen am Montag)
./speiseplan.py stats weekday freitag --demo
./speiseplan.py stats weekday montag --demo

# 🔄 5. Lebenszyklus: Klassiker vs. Eintagsfliegen (One-Hit-Wonders)
./speiseplan.py stats lifecycle --demo

# 📦 Optional: JSON-Export für eigene Skripte
./speiseplan.py stats --demo --json
```

---

### 4. Watchlist & Benachrichtigungen

```bash
# Lieblingsgericht hinzufügen
./speiseplan.py watch add "Burger"
./speiseplan.py watch add "Schnitzel"

# Watchlist ansehen
./speiseplan.py watch list

# Gericht entfernen
./speiseplan.py watch remove "Burger"
```

Bei normalen Abfragen erscheint automatisch ein Benachrichtigungs-Banner:
```text
 🔔 LIEBLINGSGERICHT-ALARM! 
  👉 hey, Donnerstag gibt es Schnitzel! (Leibspeise 1: Paniertes Schnitzel vom Schwein oder Hähnchen...)
```

### 4. Silent-Check für Skripte & Cronjobs

Der Befehl `speiseplan alert` bleibt stumm, solange kein beobachtetes Gericht auf der Karte steht. Gibt es einen Treffer, wird die Zeile direkt ausgegeben:

```bash
./speiseplan.py alert
# Ausgabe bei Treffer:
# hey, Donnerstag gibt es Schnitzel!
```

#### Cron-Beispiel (z. B. jeden Montag um 08:30 Uhr prüfen und Benachrichtigung senden):
```crontab
30 8 * * 1 /home/alex/.gemini/antigravity/scratch/speiseplan/speiseplan.py alert | while read line; do notify-send "Kantine" "$line"; done
```

---

## Datenstruktur

- `data/kwXX_YYYY.csv`:
  ```csv
  kw;jahr;datum;wochentag;kategorie;gericht;preis_mitarbeiter;preis_gaeste;eigenschaften;kalorien;allergene
  43;2026;2026-10-22;Donnerstag;Leibspeise 1;Paniertes Schnitzel vom Schwein oder Hähnchen | Paprikarahmsoße | Pommes frites;4,60€;7,90 €;;250kcal*;1,4,7,10,11
  43;2026;2026-10-22;Donnerstag;Leibspeise 3;Ofenfrische Pizza Speciale | Schinken | Mozzarella | Champignons | Rucola;4,60€;7,90 €;;250kcal*;K,A,P,4,7
  ```
- `data/archive.csv`: Kumuliertes Archiv aller Kalenderwochen ohne Duplikate.
- `data/watchlist.json`: Textbasierte JSON-Datei der überwachten Suchbegriffe.

---

## Tests ausführen
 
```bash
python3 tests/run_all_tests.py
```
*(Führt alle 59 Unit- und CLI-Integrationstests aus).*
