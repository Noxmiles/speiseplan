"""
speiseplan_core/config.py — Zentrale Konfiguration, Dateipfade & Hilfsprogramme.

Dieses Modul bündelt an einer Stelle:
1. Alle Standardpfade (relativ zum Projekt-Hauptverzeichnis, z. B. `data/`, `data/images/`).
2. Die Ziel-Website (`https://kaiberg-kitchen.de/`) und Kantinen-Vorgabe (`HessenTreff`).
3. Das einheitliche CSV-Spaltenschema (`CSV_COLUMNS`).
4. Hilfsfunktionen zum Auffinden von externen Werkzeugen (`poppler-utils` für PDFs
   und `tesseract` als OCR-Bild-Fallback) unter Linux, macOS und Windows.
"""

import functools
import os
import platform
import shutil
import subprocess
import sys
from typing import List, Optional

# ==============================================================================
# PROJEKTPFADE & GRUNDEINSTELLUNGEN
# ==============================================================================

# Eine Ebene über speiseplan_core/ liegt das Hauptverzeichnis des Projekts
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
IMAGES_DIR = os.path.join(DATA_DIR, "images")
ARCHIVE_CSV = os.path.join(DATA_DIR, "archive.csv")
WATCHLIST_FILE = os.path.join(DATA_DIR, "watchlist.json")
RATINGS_FILE = os.path.join(DATA_DIR, "ratings.json")

DEFAULT_URL = "https://kaiberg-kitchen.de/"
DEFAULT_CANTEEN = "HessenTreff"
WEEKDAYS_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

# Spaltenreihenfolge aller erzeugten Wochen- und Archiv-CSV-Dateien (Semikolon-getrennt, UTF-8)
CSV_COLUMNS = [
    "kw",
    "jahr",
    "datum",
    "wochentag",
    "kategorie",
    "gericht",
    "preis_mitarbeiter",
    "preis_gaeste",
    "eigenschaften",
    "kalorien",
    "allergene",
]

# Windows 11 ANSI-Farben im Terminal aktivieren
if sys.platform == "win32":
    os.system("")

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
WHITE = "\033[37m"
BG_YELLOW = "\033[43m"


def ensure_data_dirs():
    """Erstellt die notwendigen Datenordner (`data/` und `data/images/`) bei Bedarf automatisch."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)


# ==============================================================================
# EXTERNE WERKZEUGE (POPPLER FÜR PDF & TESSERACT ALS OCR-FALLBACK)
# ==============================================================================

def find_tesseract_binary() -> Optional[str]:
    """Findet die Tesseract-Ausführungsdatei unter Linux, macOS oder Windows 11."""
    found = shutil.which("tesseract")
    if found:
        return found

    if sys.platform == "win32":
        candidates = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path

    return None


def find_poppler_tool(tool_name: str) -> Optional[str]:
    """Findet ein Poppler-Hilfsprogramm (z. B. `pdftohtml`, `pdftoppm`) im Systempfad."""
    found = shutil.which(tool_name)
    if found:
        return found

    if sys.platform == "win32":
        exe = f"{tool_name}.exe" if not tool_name.endswith(".exe") else tool_name
        for base in [
            r"C:\Program Files\poppler\Library\bin",
            r"C:\Program Files\poppler\bin",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\poppler\Library\bin"),
        ]:
            candidate = os.path.join(base, exe)
            if os.path.isfile(candidate):
                return candidate
    return None


@functools.lru_cache(maxsize=1)
def get_tesseract_ocr_args() -> List[str]:
    """Ermittelt die optimalen Argumente für Tesseract (`-l deu` und optional lokales `tessdata/`)."""
    tess_bin = find_tesseract_binary()
    if not tess_bin:
        return []

    # 1. Prüfen auf lokales tessdata-Verzeichnis im Projektroot (z. B. tessdata_best/deu.traineddata)
    local_tessdata = os.path.join(SCRIPT_DIR, "tessdata")
    if os.path.isfile(os.path.join(local_tessdata, "deu.traineddata")):
        return ["--tessdata-dir", local_tessdata, "-l", "deu"]

    # 2. Prüfen, ob das System-Tesseract das deutsche Sprachpaket 'deu' installiert hat
    try:
        res = subprocess.run([tess_bin, "--list-langs"], capture_output=True, text=True, timeout=5)
        langs = [l.strip() for l in res.stdout.splitlines() if l.strip() and not l.startswith("List of")]
        if "deu" in langs:
            return ["-l", "deu"]
    except Exception:
        pass

    return []


def print_missing_tesseract_help():
    """Gibt verständliche Installationsanleitungen für Tesseract OCR aus."""
    print(f"\n{RED}{BOLD}❌ Tesseract OCR wurde auf diesem System nicht gefunden!{RESET}")
    print("Das Skript benötigt Tesseract, um den Speiseplan aus einem Bild auszulesen.\n")
    print(f"{BOLD}So installierst du Tesseract auf deinem Betriebssystem:{RESET}")
    print(f"  • {BOLD}Ubuntu / Debian:{RESET}                  sudo apt install tesseract-ocr tesseract-ocr-deu")
    print(f"  • {BOLD}Fedora / RHEL / Rocky / AlmaLinux:{RESET} sudo dnf install tesseract tesseract-langpack-deu")
    print(f"  • {BOLD}Arch Linux / CachyOS:{RESET}             sudo pacman -S tesseract tesseract-data-deu")
    print(f"  • {BOLD}macOS (Homebrew):{RESET}                 brew install tesseract tesseract-lang")
    print(f"  • {BOLD}Windows 11 (Terminal / winget):{RESET}   winget install UB-Mannheim.TesseractOCR")
    print(f"  • {BOLD}Windows 11 (Manuell ohne winget):{RESET} Lade den offiziellen Installer (.exe) herunter:")
    print("                                           👉 https://github.com/UB-Mannheim/tesseract/wiki")
    print("                                           (Einfach herunterladen, per Doppelklick starten und 'Weiter' klicken).\n")
    print(f"{DIM}Hinweis: Abfragen bereits gespeicherter Pläne (heute, search, stats) funktionieren auch ohne Tesseract.{RESET}\n")


def cmd_install_help():
    """Zeigt eine Systemdiagnose und die vollständige Tesseract-Installationshilfe an."""
    tess_path = find_tesseract_binary()
    print(f"\n{BOLD}{CYAN}══════════════════════════════════════════════════════════════════════════════{RESET}")
    print(f" {BOLD}TESSERACT-OCR SYSTEMDIAGNOSE & INSTALLATIONSHILFE{RESET}")
    print(f"{BOLD}{CYAN}══════════════════════════════════════════════════════════════════════════════{RESET}\n")
    print(f"{BOLD}Aktueller Systemstatus auf diesem Rechner:{RESET}")
    print(f"  • Betriebssystem:     {BOLD}{sys.platform}{RESET} ({platform.system()} {platform.release()})")
    if tess_path:
        print(f"  • Tesseract-Status:   {GREEN}{BOLD}✅ Gefunden{RESET} ({tess_path})")
    else:
        print(f"  • Tesseract-Status:   {RED}{BOLD}❌ Nicht gefunden{RESET}")
    print(f"\n{DIM}Nachfolgend die vollständige Installationsanleitung für alle Betriebssysteme,{RESET}")
    print(f"{DIM}wie sie auch bei fehlendem OCR auf jedem System komplett ausgegeben wird:{RESET}")
    print_missing_tesseract_help()
