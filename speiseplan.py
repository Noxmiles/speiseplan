#!/usr/bin/env python3
"""
Speiseplan CLI - HessenTreff (Kaiberg Kitchen)
Lädt den wöchentlichen Speiseplan per OCR von der Webseite herunter, speichert ihn
in CSV-Dateien (pro KW und Langzeitarchiv), ermöglicht flexible Abfragen, Archivsuche,
statistische Auswertungen (inkl. Fleischarten) und Lieblingsgericht-Benachrichtigungen.

Kompatibel mit Linux, macOS und Windows 11.
"""

# ┌─────────────────────────────────────────────────────────────────────────────┐
# │ INHALTSVERZEICHNIS / ARCHITEKTUR                                            │
# │                                                                             │
# │  1. KONFIGURATION, PFADE & PLATTFORM-KOMPATIBILITÄT (Linux / Win 11)        │
# │  2. DATENMODELLE (Dish, DayMenu, WeekMenu)                                  │
# │  3. WEB-SCRAPER & BILD-DOWNLOAD (kaiberg-kitchen.de)                        │
# │  4. OCR-PARSING & BILDGITTER-SEGMENTIERUNG (Tesseract, Siegel, Text)        │
# │  5. CSV-SPEICHER & LANGZEITARCHIV (Deduplizierung, Suche)                   │
# │  6. WATCHLIST FÜR LIEBLINGSGERICHTE (JSON, Alarm-Banner, Silent-Alert)      │
# │  7. KANTINEN-ANALYTIK (Fleischarten, Wochentage, Soßen, Lebenszyklus)       │
# │  8. DEMO-DATENSATZ-GENERATOR (20 Wochen Historie für Tests & Vorschau)      │
# │  9. CLI-HANDLER & FORMATIERTE AUSGABE (Tageskarten, Suche, Banner, Stats)  │
# │ 10. CLI-EINSTIEGSPUNKT, ARGUMENT-PARSER & HILFE                             │
# └─────────────────────────────────────────────────────────────────────────────┘

import sys
import os
import platform
import re
import csv
import io
import json
import shutil
import subprocess
import argparse
import functools
import urllib.request
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Any, Optional
from collections import Counter
from dataclasses import dataclass, field, asdict
from PIL import Image
import numpy as np

# Optionale Imports für Web-Scraping mit weichem Fallback
try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None

# ==============================================================================
# 1. KONFIGURATION, PFADE & PLATTFORM-KOMPATIBILITÄT (LINUX / WIN 11)
# ==============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
IMAGES_DIR = os.path.join(DATA_DIR, "images")
ARCHIVE_CSV = os.path.join(DATA_DIR, "archive.csv")
WATCHLIST_FILE = os.path.join(DATA_DIR, "watchlist.json")

DEFAULT_URL = "https://kaiberg-kitchen.de/"
DEFAULT_CANTEEN = "HessenTreff"
WEEKDAYS_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
CSV_COLUMNS = [
    "kw", "jahr", "datum", "wochentag", "kategorie", "gericht",
    "preis_mitarbeiter", "preis_gaeste", "eigenschaften", "kalorien", "allergene"
]

# Windows 11 ANSI-Farben aktivieren
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
    """Erstellt die notwendigen Unterordner automatisch relativ zum Skript."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)


def find_tesseract_binary() -> Optional[str]:
    """Findet die Tesseract-Ausführungsdatei unter Linux, macOS oder Windows 11."""
    # 1. Im Systempfad (PATH) suchen
    found = shutil.which("tesseract")
    if found:
        return found

    # 2. Typische Windows-Installationspfade prüfen
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


def print_missing_tesseract_help():
    """Gibt verständliche Installationsanleitungen für alle Betriebssysteme aus."""
    print(f"\n{RED}{BOLD}❌ Tesseract OCR wurde auf diesem System nicht gefunden!{RESET}")
    print("Das Skript benötigt Tesseract, um den Speiseplan aus dem Bild auszulesen.\n")
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


# ==============================================================================
# OCR-KORREKTURMATRIX & SPRACHKONFIGURATION
# ==============================================================================

OCR_REPLACEMENTS = [
    # Umlaute & Käse
    (r"\bK[a-z]{0,2}se\b", "Käse"),
    (r"kdse", "käse"),
    (r"Kdse", "Käse"),
    (r"\bKase\b", "Käse"),
    (r"\bK[da]sesp[ad]tzle\b", "Käsespätzle"),
    # Hähnchen
    (r"H[da]hnchen", "Hähnchen"),
    # Döner & Burger
    (r"D[eé]nerteller", "Dönerteller"),
    # Kürbis (Kürbissuppe, Hokkaido-Kürbis, Ofenkürbis, Kürbiskerne)
    (r"K[iua]rbis", "Kürbis"),
    # Kräuter
    (r"Kr[da]uter", "Kräuter"),
    # Frühlingsröllchen
    (r"Fr[iuü]h?lingsr[a-z]{2,5}chen", "Frühlingsröllchen"),
    # Süßkartoffeln
    (r"S[uü][Rrs]+kartoffel", "Süßkartoffel"),
    # Soße / Sauce
    (r"Paprikarahmso[Rc]e", "Paprikarahmsoße"),
    (r"([a-z]+)so[Rc]e\b", r"\1soße"),
    (r"\bSo[Rc]e\b", "Soße"),
    # Geröstet
    (r"ger[ode]stet([a-z]*)", r"geröstet\1"),
    # Püree & Spätzle
    (r"Kartoffel[piu]+ree", "Kartoffelpüree"),
    (r"([bB]utter|[kK]äse)sp[ad]tzle", r"\1spätzle"),
    (r"\bSp[ad]tzle\b", "Spätzle"),
    # Klöße & Köttbullar
    (r"K[oe]ttbullar", "Köttbullar"),
    (r"Kartoffelklo[Rsc]+e", "Kartoffelklöße"),
    (r"Markkl[od][Rsc]+chen", "Markklößchen"),
    # Nüsse & Trüffel & Gemüse
    (r"Waln[ui]sse", "Walnüsse"),
    (r"Tr[ui]ffel[oeo]?l?", "Trüffelöl"),
    (r"Tr[ui]ffel", "Trüffel"),
    (r"([a-zA-Z]*)gem[ui]se\b", r"\1gemüse"),
    (r"([a-zA-Z]*)Gem[ui]se\b", r"\1Gemüse"),
    (r"W[ui]rstchen", "Würstchen"),
    (r"Bohnensu\s*ppe", "Bohnensuppe"),
]


def normalize_ocr_text(text: str) -> str:
    """Bereinigt typische OCR-Fehlinterpretationen von Umlauten und Sonderzeichen."""
    for pattern, repl in OCR_REPLACEMENTS:
        text = re.sub(pattern, repl, text)
    return text


DECORATIVE_WORDS = [
    "paniert", "saftig", "knusprig", "ausgebacken", "zart", "fein",
    "ofenfrisch", "hausgemacht", "frisch", "herzhaft", "gebraten", "goldbraun",
    "cremig", "würzig", "vegetarisch"
]
DEC_PATTERN = re.compile(
    r"^\s*(" + "|".join(DECORATIVE_WORDS) + r")(?:es|er|em|en|e|s)?\b\s*",
    flags=re.I
)
DANGLING_PREPS = {"vom", "von", "in", "an", "auf", "mit", "nach", "aus", "im", "bei"}


def fix_dangling_components(dish_text: str) -> str:
    """Verbindet Zeilenfragmente, die mit einer Präposition (vom, in, an) oder Bindestrich abbrechen."""
    parts = [p.strip() for p in dish_text.split("|") if p.strip()]
    if not parts:
        return ""
    merged = []
    i = 0
    while i < len(parts):
        curr = parts[i]
        while i + 1 < len(parts):
            next_part = parts[i + 1]
            # Fall 1: curr endet mit Bindestrich (z.B. 'Toskanische-')
            if curr.endswith("-"):
                curr = curr.rstrip("-").strip() + " " + next_part
                i += 1
                continue
            # Fall 2: curr endet mit einer Präposition (auch bei Satzzeichen wie 'vom,')
            last_token = curr.rstrip().split()[-1].lower() if curr.split() else ""
            clean_last = re.sub(r"^[^\w]+|[^\w]+$", "", last_token)
            if clean_last in DANGLING_PREPS:
                curr = f"{curr} {next_part}"
                i += 1
                continue
            # Fall 3: next_part beginnt mit einer Präposition (z.B. 'Paniertes Schnitzel' | 'vom Schwein')
            first_token = next_part.lstrip().split()[0].lower() if next_part.split() else ""
            clean_first = re.sub(r"^[^\w]+|[^\w]+$", "", first_token)
            if clean_first in DANGLING_PREPS and first_token == clean_first:
                curr = f"{curr} {next_part}"
                i += 1
                continue
            break
        merged.append(curr)
        i += 1
    return " | ".join(merged)


def get_canonical_dish(dish_text: str) -> str:
    """Extrahiert die Hauptkomponente eines Gerichts (ohne Füll-Adjektive und abbrechende Satzteile)."""
    cleaned = fix_dangling_components(dish_text)
    if not cleaned:
        return ""
    head = cleaned.split("|")[0].strip()
    head = re.sub(r"^[\"\'„“»«\s]+|[\"\'„“»«\s]+$", "", head)
    orig_head = head
    prev = None
    while prev != head:
        prev = head
        head = DEC_PATTERN.sub("", head).strip()
    head = re.sub(r"[\"\'„“»«]", "", head).strip()
    return head if head else orig_head


@functools.lru_cache(maxsize=1)
def get_tesseract_ocr_args() -> List[str]:
    """Ermittelt die optimalen Argumente für Tesseract (Sprachflag deu und tessdata-Pfad)."""
    tess_bin = find_tesseract_binary()
    if not tess_bin:
        return []

    # 1. Prüfen auf lokales tessdata Verzeichnis im Projekt (z.B. tessdata_best/deu.traineddata)
    project_dir = os.path.dirname(os.path.abspath(__file__))
    local_tessdata = os.path.join(project_dir, "tessdata")
    if os.path.isfile(os.path.join(local_tessdata, "deu.traineddata")):
        return ["--tessdata-dir", local_tessdata, "-l", "deu"]

    # 2. Prüfen, ob das System-Tesseract 'deu' installiert hat
    try:
        res = subprocess.run([tess_bin, "--list-langs"], capture_output=True, text=True, timeout=5)
        langs = [l.strip() for l in res.stdout.splitlines() if l.strip() and not l.startswith("List of")]
        if "deu" in langs:
            return ["-l", "deu"]
    except Exception:
        pass

    return []


# ==============================================================================
# 2. DATENMODELLE
# ==============================================================================

@dataclass
class Dish:
    kw: int
    jahr: int
    datum: str                  # Format: YYYY-MM-DD
    wochentag: str              # Montag .. Freitag
    kategorie: str              # Suppe, Leibspeise 1-3, Salatbar
    gericht: str                # Name / Beschreibung
    preis_mitarbeiter: str = "" # z.B. "4,60 €"
    preis_gaeste: str = ""      # z.B. "7,90 €"
    eigenschaften: str = ""     # "Vegan", "Vegetarisch" oder leer
    kalorien: str = ""          # z.B. "250 kcal*"
    allergene: str = ""         # z.B. "1,4,7,10"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Dish":
        return cls(
            kw=int(data["kw"]),
            jahr=int(data["jahr"]),
            datum=str(data["datum"]),
            wochentag=str(data["wochentag"]),
            kategorie=str(data["kategorie"]),
            gericht=fix_dangling_components(normalize_ocr_text(str(data.get("gericht", "")))),
            preis_mitarbeiter=str(data.get("preis_mitarbeiter", "")),
            preis_gaeste=str(data.get("preis_gaeste", "")),
            eigenschaften=str(data.get("eigenschaften", "")),
            kalorien=str(data.get("kalorien", "")),
            allergene=str(data.get("allergene", "")),
        )


@dataclass
class DayMenu:
    wochentag: str
    datum: str
    dishes: List[Dish] = field(default_factory=list)


@dataclass
class WeekMenu:
    kw: int
    jahr: int
    start_date: str
    end_date: str
    days: Dict[str, DayMenu] = field(default_factory=dict)

    def all_dishes(self) -> List[Dish]:
        res = []
        for d in self.days.values():
            res.extend(d.dishes)
        return res

    def get_day(self, weekday_name: str) -> Optional[DayMenu]:
        name = weekday_name.strip().lower()
        for k, v in self.days.items():
            if k.lower() == name:
                return v
        return None


# ==============================================================================
# 3. WEB-SCRAPER (KAIBERG KITCHEN)
# ==============================================================================

def get_menu_image_url(page_url: str = DEFAULT_URL, canteen: str = DEFAULT_CANTEEN) -> str:
    """Findet auf kaiberg-kitchen.de die Wochenkarte für HessenTreff."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}

    if requests and BeautifulSoup:
        resp = requests.get(page_url, headers=headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")

        # Suche nach Überschrift mit Kantinenname
        target_heading = None
        for heading in soup.find_all(["h1", "h2", "h3", "h4", "strong", "p"]):
            if canteen.lower() in heading.get_text().lower():
                target_heading = heading
                break

        if not target_heading:
            raise ValueError(f"Kantine '{canteen}' konnte auf {page_url} nicht gefunden werden.")

        # In Eltern-Containern nach der Wochenkarte suchen
        node = target_heading
        menu_img = None
        for _ in range(6):
            if not node.parent:
                break
            node = node.parent
            for fig in node.find_all("figure"):
                if "wochenkarte" in fig.get_text().lower():
                    img = fig.find("img")
                    if img:
                        menu_img = img
                        break
            if menu_img:
                break

        if not menu_img:
            for img in node.find_all("img"):
                src = img.get("src", "")
                if "Bildschirmfoto" in src or "wochenkarte" in src.lower():
                    menu_img = img
                    break

        if not menu_img:
            raise ValueError(f"Wochenkarte für '{canteen}' nicht gefunden.")

        # Höchste Auflösung aus srcset wählen
        srcset = menu_img.get("srcset")
        if srcset:
            parts = [p.strip().split() for p in srcset.split(",") if p.strip()]
            return max(parts, key=lambda x: int(re.sub(r"\D", "", x[1])) if len(x) > 1 and re.sub(r"\D", "", x[1]) else 0)[0]
        return menu_img.get("src")
    else:
        # Fallback ohne requests/bs4 via urllib und Regex
        req = urllib.request.Request(page_url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        match = re.search(r'src=["\'](https://[^"\']+Bildschirmfoto[^"\']+)["\']', html)
        if match:
            return match.group(1)
        raise RuntimeError("Wochenkarten-URL konnte nicht ermittelt werden.")


def download_menu_image(image_url: str, output_path: str) -> str:
    """Lädt das Bild herunter und speichert es lokal."""
    ensure_data_dirs()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
    req = urllib.request.Request(image_url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp, open(output_path, "wb") as f:
        f.write(resp.read())
    return output_path


def fetch_latest_menu_image(output_dir: str = IMAGES_DIR, canteen: str = DEFAULT_CANTEEN) -> str:
    """Holt die aktuelle Wochenkarte und speichert sie im Cache-Ordner."""
    url = get_menu_image_url(canteen=canteen)
    filename = os.path.basename(url.split("?")[0])
    target_path = os.path.join(output_dir, filename)
    return download_menu_image(url, target_path)


# ==============================================================================
# 4. OCR & TABELLEN-PARSER (TESSERACT + PILLOW)
# ==============================================================================

def run_tesseract(crop: Image.Image, psm: int = 6) -> str:
    """Führt Tesseract über stdin/stdout auf einem Bildausschnitt aus (mit deutschem Sprachmodell & tessdata_best)."""
    tess_bin = find_tesseract_binary()
    if not tess_bin:
        print_missing_tesseract_help()
        raise FileNotFoundError("tesseract nicht gefunden")

    buf = io.BytesIO()
    crop.save(buf, format="PNG")
    ocr_args = get_tesseract_ocr_args()
    cmd = [tess_bin, "stdin", "stdout"] + ocr_args + ["--psm", str(psm)]
    res = subprocess.run(cmd, input=buf.getvalue(), capture_output=True)
    return res.stdout.decode("utf-8", errors="ignore").strip()


def detect_grid(image: Image.Image) -> Tuple[List[int], List[int]]:
    """Ermittelt die 7 horizontalen und vertikalen Trennlinien des Tabellenrasters."""
    gray = image.convert("L")
    arr = np.array(gray)
    h, w = arr.shape

    # Horizontale Linien (dunkle Pixel < 120)
    cand_h = np.where((arr < 120).sum(axis=1) > int(w * 0.5))[0]
    h_groups = []
    for idx in cand_h:
        if not h_groups or idx > h_groups[-1][-1] + 6:
            h_groups.append([idx])
        else:
            h_groups[-1].append(idx)
    h_lines = [int(np.mean(g)) for g in h_groups if len(g) >= 1]
    h_lines = [y for y in h_lines if int(h * 0.15) < y < int(h * 0.95)]

    # Fallback bei Abweichung
    if len(h_lines) != 7:
        h_lines = [int(h * r) for r in [0.1966, 0.2371, 0.3298, 0.4895, 0.6722, 0.7873, 0.8696]]

    # Vertikale Linien
    sub = arr[h_lines[0]:h_lines[-1], :]
    cand_v = np.where((sub < 120).sum(axis=0) > int((h_lines[-1] - h_lines[0]) * 0.8))[0]
    v_groups = []
    for idx in cand_v:
        if not v_groups or idx > v_groups[-1][-1] + 6:
            v_groups.append([idx])
        else:
            v_groups[-1].append(idx)
    v_lines = [int(np.mean(g)) for g in v_groups if len(g) >= 1]
    v_lines = [x for x in v_lines if int(w * 0.02) < x < int(w * 0.99)]

    if len(v_lines) != 7:
        v_lines = [int(w * r) for r in [0.0405, 0.1411, 0.3125, 0.4805, 0.6377, 0.8047, 0.9663]]

    return h_lines, v_lines


def parse_header_info(image: Image.Image, h_top: int) -> Tuple[int, int, str, str]:
    """Liest KW und Datumsspanne aus dem Tabellenkopf."""
    w, _ = image.size
    header_text = run_tesseract(image.crop((0, 0, w, h_top)), psm=6)

    kw_match = re.search(r"KW\s*(\d+)", header_text, re.I)
    kw = int(kw_match.group(1)) if kw_match else datetime.now().isocalendar()[1]

    date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})\s*-\s*(\d{1,2})\.(\d{1,2})\.(\d{4})", header_text)
    if date_match:
        d1, m1, y1, d2, m2, y2 = date_match.groups()
        jahr = int(y1)
        start_date = f"{jahr:04d}-{int(m1):02d}-{int(d1):02d}"
        end_date = f"{int(y2):04d}-{int(m2):02d}-{int(d2):02d}"
    else:
        now = datetime.now()
        jahr = now.year
        start_date = now.strftime("%Y-%m-%d")
        end_date = (now + timedelta(days=4)).strftime("%Y-%m-%d")

    return kw, jahr, start_date, end_date


def detect_diet_badge(cell_crop: Image.Image) -> str:
    """Erkennt das runde braune Vegan- oder Vegetarisch-Siegel."""
    w, h = cell_crop.size
    if w < 60 or h < 60:
        return ""
    corner = cell_crop.crop((max(0, w - 85), max(0, h - 85), w, h))
    arr = np.array(corner.convert("RGB"))
    brown_mask = (arr[:, :, 0] > 115) & (arr[:, :, 0] < 210) & \
                 (arr[:, :, 1] > 95)  & (arr[:, :, 1] < 190) & \
                 (arr[:, :, 2] > 75)  & (arr[:, :, 2] < 170)
    if brown_mask.sum() < 250:
        return ""

    up = corner.resize((corner.width * 3, corner.height * 3), Image.Resampling.LANCZOS).convert("L")
    ocr_corner = run_tesseract(up.point(lambda p: 0 if p < 115 else 255), psm=6).lower()
    if re.search(r"v[a-z\.\s]{1,4}an|vecan|vegan|vican|egan", ocr_corner):
        return "Vegan"
    return "Vegetarisch"


def clean_cell_text(raw_text: str) -> Tuple[str, str, str]:
    """Trennt Gerichtsname, Kalorien und Allergen-Codes."""
    norm = normalize_ocr_text(raw_text)
    lines = [l.strip() for l in norm.split("\n") if l.strip()]
    dish_lines, calories, allergens = [], "", ""

    for line in lines:
        if re.search(r"\b\d+\s*k(?:c|e|ec)?al(?:\*+)?", line, re.I):
            calories = line
        elif re.match(r"^[0-9,\s\.\*\+\-\|KAPGVFSCO_]+$", line) and len(line) <= 15:
            allergens = line
        elif line.lower() in ["vegan", "vegetarisch"] or (len(line) <= 2 and line in ["‘", "’", "'", ".", ","]):
            continue
        else:
            dish_lines.append(line)

    dish = " | ".join(dish_lines) if dish_lines else (lines[0] if lines else "")
    dish = re.sub(r"\s*\|\s*$", "", re.sub(r"^\s*\|\s*", "", dish))
    dish = fix_dangling_components(dish)
    return dish, calories, allergens


def parse_category_cell(raw_text: str) -> Tuple[str, str, str]:
    """Parst Kategorie und Preise (z.B. Leibspeise 1 / 4,60 € / 7,90 €)."""
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    cat_name = lines[0] if lines else "Unbekannt"

    if "leibspeise" in cat_name.lower():
        return cat_name, "4,60 €", "7,90 €"
    elif "suppe" in cat_name.lower():
        return cat_name, "2,80 €", "4,60 €"
    elif "salatbar" in cat_name.lower():
        return cat_name, "4,60 €", "3,00 € / 5,80 €"
    return cat_name, "", ""


def parse_menu_image(image_path: str) -> WeekMenu:
    """Hauptfunktion: Zerlegt das Bild in Zellen und baut das WeekMenu auf."""
    img = Image.open(image_path)
    h_lines, v_lines = detect_grid(img)
    kw, jahr, start_d, end_d = parse_header_info(img, h_lines[0])

    start_dt = datetime.strptime(start_d, "%Y-%m-%d")
    weekdays_5 = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]
    day_dates = {wday: (start_dt + timedelta(days=i)).strftime("%Y-%m-%d") for i, wday in enumerate(weekdays_5)}

    categories = [parse_category_cell(run_tesseract(img.crop((v_lines[0] + 3, h_lines[r] + 3, v_lines[1] - 3, h_lines[r + 1] - 3)), psm=6))
                  for r in range(1, len(h_lines) - 1)]

    days = {wday: DayMenu(wochentag=wday, datum=day_dates[wday], dishes=[]) for wday in weekdays_5}

    for r_idx, (cat_name, p_ma, p_gaeste) in enumerate(categories, start=1):
        for c_idx, wday in enumerate(weekdays_5, start=1):
            cell = img.crop((v_lines[c_idx] + 3, h_lines[r_idx] + 3, v_lines[c_idx + 1] - 3, h_lines[r_idx + 1] - 3))
            raw = run_tesseract(cell, psm=6)
            dish_text, cal, alg = clean_cell_text(raw)
            diet = detect_diet_badge(cell)
            if not diet:
                low = raw.lower()
                diet = "Vegan" if "vegan" in low else ("Vegetarisch" if "vegetarisch" in low else "")

            days[wday].dishes.append(Dish(
                kw=kw, jahr=jahr, datum=day_dates[wday], wochentag=wday,
                kategorie=cat_name, gericht=dish_text, preis_mitarbeiter=p_ma,
                preis_gaeste=p_gaeste, eigenschaften=diet, kalorien=cal, allergene=alg
            ))

    return WeekMenu(kw=kw, jahr=jahr, start_date=start_d, end_date=end_d, days=days)


# ==============================================================================
# 5. CSV-SPEICHERUNG & LANGZEITARCHIV
# ==============================================================================

def get_week_csv_path(kw: int, jahr: int, data_dir: str = DATA_DIR) -> str:
    return os.path.join(data_dir, f"kw{kw:02d}_{jahr}.csv")


def save_week_csv(menu: WeekMenu, data_dir: str = DATA_DIR) -> str:
    os.makedirs(data_dir, exist_ok=True)
    target = get_week_csv_path(menu.kw, menu.jahr, data_dir)
    with open(target, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, delimiter=";")
        writer.writeheader()
        for dish in menu.all_dishes():
            writer.writerow(dish.to_dict())
    return target


def load_week_csv(csv_path: str) -> WeekMenu:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Datei {csv_path} existiert nicht.")
    dishes = []
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            dishes.append(Dish.from_dict(row))
    if not dishes:
        raise ValueError(f"Keine Einträge in {csv_path}")

    days = {}
    for d in dishes:
        if d.wochentag not in days:
            days[d.wochentag] = DayMenu(wochentag=d.wochentag, datum=d.datum, dishes=[])
        days[d.wochentag].dishes.append(d)

    sorted_dates = sorted([d.datum for d in dishes])
    return WeekMenu(kw=dishes[0].kw, jahr=dishes[0].jahr,
                    start_date=sorted_dates[0], end_date=sorted_dates[-1], days=days)


def update_archive_csv(menu: WeekMenu, data_dir: str = DATA_DIR) -> int:
    """Fügt Gerichte der Woche in archive.csv ein (aktualisiert bei gleichem Datum/Kategorie)."""
    os.makedirs(data_dir, exist_ok=True)
    archive_path = os.path.join(data_dir, "archive.csv")
    existing = {}

    if os.path.exists(archive_path):
        with open(archive_path, "r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter=";"):
                try:
                    d = Dish.from_dict(row)
                    norm_cat = re.sub(r"\s+", "", d.kategorie.lower())
                    existing[(d.datum, norm_cat)] = d
                except Exception:
                    pass

    for dish in menu.all_dishes():
        norm_cat = re.sub(r"\s+", "", dish.kategorie.lower())
        existing[(dish.datum, norm_cat)] = dish

    sorted_dishes = sorted(existing.values(), key=lambda x: (x.datum, re.sub(r"\s+", "", x.kategorie.lower())), reverse=True)
    with open(archive_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, delimiter=";")
        writer.writeheader()
        for dish in sorted_dishes:
            writer.writerow(dish.to_dict())
    return len(sorted_dishes)


def search_archive(query: str, data_dir: str = DATA_DIR) -> List[Dish]:
    """Sucht nach Gerichten im Langzeitarchiv (neueste zuerst)."""
    archive_path = os.path.join(data_dir, "archive.csv")
    if not os.path.exists(archive_path):
        return []
    q = query.strip().lower()
    matches = []
    with open(archive_path, "r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter=";"):
            d = Dish.from_dict(row)
            if q in d.gericht.lower() or q in d.kategorie.lower():
                matches.append(d)
    matches.sort(key=lambda x: x.datum, reverse=True)
    return matches


def load_archive_dishes(data_dir: str = DATA_DIR) -> List[Dish]:
    archive_path = os.path.join(data_dir, "archive.csv")
    if not os.path.exists(archive_path):
        return []
    res = []
    with open(archive_path, "r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter=";"):
            try:
                res.append(Dish.from_dict(row))
            except Exception:
                pass
    return res


def find_latest_local_week(data_dir: str = DATA_DIR) -> Optional[WeekMenu]:
    if not os.path.exists(data_dir):
        return None
    files = sorted([f for f in os.listdir(data_dir) if f.startswith("kw") and f.endswith(".csv")], reverse=True)
    return load_week_csv(os.path.join(data_dir, files[0])) if files else None


# ==============================================================================
# 6. WATCHLIST & BENACHRICHTIGUNGEN
# ==============================================================================

class WatchlistManager:
    """Verwaltet Lieblingsgerichte in watchlist.json und prüft Speisepläne."""

    def __init__(self, filepath: str = WATCHLIST_FILE):
        self.filepath = filepath
        os.makedirs(os.path.dirname(os.path.abspath(self.filepath)), exist_ok=True)
        if not os.path.exists(self.filepath):
            self.save([])

    def load(self) -> List[str]:
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                d = json.load(f)
                return [str(x).strip() for x in d if str(x).strip()] if isinstance(d, list) else []
        except Exception:
            return []

    def save(self, items: List[str]):
        cleaned = sorted(list({x.strip() for x in items if x.strip()}), key=lambda s: s.lower())
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)

    def add(self, keyword: str) -> bool:
        kw = keyword.strip()
        if not kw or any(kw.lower() == item.lower() for item in self.load()):
            return False
        items = self.load()
        items.append(kw)
        self.save(items)
        return True

    def remove(self, keyword: str) -> bool:
        kw = keyword.strip().lower()
        items = self.load()
        filtered = [x for x in items if x.lower() != kw]
        if len(filtered) == len(items):
            return False
        self.save(filtered)
        return True

    def list_keywords(self) -> List[str]:
        return self.load()

    def check_menu(self, menu: WeekMenu) -> List[Tuple[str, Dish]]:
        keywords = self.load()
        if not keywords:
            return []
        hits = []
        for dish in menu.all_dishes():
            text = dish.gericht.lower()
            for kw in keywords:
                if kw.lower() in text:
                    hits.append((kw, dish))
        return hits

    @staticmethod
    def format_alerts(hits: List[Tuple[str, Dish]], detailed: bool = False) -> List[str]:
        msgs = []
        for kw, dish in hits:
            if detailed:
                diet = f" [{dish.eigenschaften}]" if dish.eigenschaften else ""
                msgs.append(f"hey, {dish.wochentag} gibt es {kw}! ({dish.kategorie}: {dish.gericht}{diet})")
            else:
                msgs.append(f"hey, {dish.wochentag} gibt es {kw}!")
        return msgs


# ==============================================================================
# 7. ANALYTICS & FLEISCHARTEN-AUSWERTUNG
# ==============================================================================

SAUCE_KEYWORDS = ["soße", "sauce", "dipp", "dip", "pesto", "salsa", "creme", "dressing", "schmand", "jus"]
SIDE_KEYWORDS = ["pommes", "kartoffel", "wedges", "reis", "drillinge", "nudeln", "spaghetti",
                 "couscous", "salat", "kroketten", "spätzle", "knödel", "püree", "pasta", "gnocchi", "gemüse"]


def render_ascii_bar(count: int, max_val: int, bar_length: int = 16) -> str:
    if max_val <= 0:
        return ""
    filled = int(round((count / max_val) * bar_length))
    return "▇" * filled + "░" * (bar_length - filled)


def split_components(dish_text: str) -> List[str]:
    parts = [p.strip() for p in dish_text.split("|") if p.strip()]
    res = []
    for p in parts:
        for sp in re.split(r"\b(?:mit|an|auf|dazu)\b", p, flags=re.I):
            clean = re.sub(r"^[\s,\.-]+|[\s,\.-]+$", "", sp.strip())
            if len(clean) > 1:
                res.append(clean)
    return res


class CanteenAnalytics:
    """Berechnet Statistiken, Wochentagsmuster, Soßen & Fleischarten."""

    def __init__(self, dishes: List[Dish]):
        self.dishes = dishes

    def get_overview(self) -> Dict[str, Any]:
        if not self.dishes:
            return {"total_dishes": 0}

        dates = sorted({d.datum for d in self.dishes if d.datum})
        kws = sorted({(d.kw, d.jahr) for d in self.dishes})
        diet_counter = Counter(d.eigenschaften if d.eigenschaften else "Fleisch / Klassisch" for d in self.dishes)

        filtered = [get_canonical_dish(d.gericht) for d in self.dishes if d.gericht.lower() not in ["salatbar", "tagesgericht", ""]]
        top_dishes = Counter(filtered).most_common(5)
        counts = Counter(filtered)

        # Durchschnittspreis NUR für echte Hauptgerichte (Leibspeisen)
        prices_ma = [float(re.search(r"(\d+[,.]\d{2})", d.preis_mitarbeiter).group(1).replace(",", "."))
                     for d in self.dishes if "leibspeise" in d.kategorie.lower() and re.search(r"(\d+[,.]\d{2})", d.preis_mitarbeiter)]
        avg_price = (sum(prices_ma) / len(prices_ma)) if prices_ma else 0.0

        return {
            "total_dishes": len(self.dishes),
            "total_weeks": len(kws),
            "date_start": dates[0] if dates else "",
            "date_end": dates[-1] if dates else "",
            "diet_distribution": dict(diet_counter),
            "top_dishes": top_dishes,
            "one_hit_wonders_count": sum(1 for c in counts.values() if c == 1),
            "staples_count": sum(1 for c in counts.values() if c >= 3),
            "avg_price_employee": avg_price,
            "meat_distribution": self.get_meat_distribution(),
        }

    def get_meat_distribution(self) -> Dict[str, int]:
        """Klassifiziert Hauptgerichte nach Fleischarten und Ernährungsformen."""
        counter = Counter()
        for d in self.dishes:
            if "leibspeise" in d.kategorie.lower():
                text = d.gericht.lower()
                diet = d.eigenschaften.lower()
                if "vegan" in diet or "vegan" in text:
                    counter["Vegan"] += 1
                elif "vegetarisch" in diet or "vegetarisch" in text:
                    counter["Vegetarisch"] += 1
                elif any(k in text for k in ["fisch", "lachs", "scholle", "seelachs", "kabeljau", "knusperfisch"]):
                    counter["Fisch / Meeresfrüchte"] += 1
                elif any(k in text for k in ["hähnchen", "hahnchen", "huhn", "pute", "chicken", "geflügel"]):
                    counter["Geflügel (Huhn / Pute)"] += 1
                elif any(k in text for k in ["schwein", "schnitzel", "leberkäse", "leberkase", "kotelett", "schinken", "speck"]):
                    counter["Schwein"] += 1
                elif any(k in text for k in ["rind", "rinder", "beef", "hackfleisch", "roulade", "gulasch"]):
                    counter["Rind / Kalb"] += 1
                else:
                    counter["Nicht explizit genannt / Tagesgericht"] += 1
        return dict(counter)

    def analyze_dish(self, query: str) -> Dict[str, Any]:
        q = query.strip().lower()
        matches = [d for d in self.dishes if q in d.gericht.lower()]
        if not matches:
            return {"query": query, "found": False, "count": 0}

        wday_cnt = Counter(d.wochentag for d in matches)
        sorted_m = sorted(matches, key=lambda x: x.datum, reverse=True)
        return {
            "query": query, "found": True, "count": len(matches),
            "latest_date": sorted_m[0].datum, "latest_dish": sorted_m[0].gericht,
            "latest_weekday": sorted_m[0].wochentag,
            "weekday_distribution": {w: wday_cnt[w] for w in ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"] if wday_cnt[w] > 0}
        }

    def analyze_combos(self, query: str) -> Dict[str, Any]:
        q = query.strip().lower()
        matches = [d for d in self.dishes if q in d.gericht.lower()]
        if not matches:
            return {"query": query, "found": False, "count": 0}

        sauces, sides = [], []
        for dish in matches:
            for c in split_components(dish.gericht):
                low = c.lower()
                if q in low and len(low.replace(q, "").strip()) < 4:
                    continue
                if any(k in low for k in SAUCE_KEYWORDS):
                    sauces.append(c)
                elif any(k in low for k in SIDE_KEYWORDS):
                    sides.append(c)

        return {
            "query": query, "found": True, "count": len(matches),
            "top_sauces": Counter(sauces).most_common(8),
            "top_sides": Counter(sides).most_common(8)
        }

    def analyze_weekday(self, weekday: str) -> Dict[str, Any]:
        wday_norm = weekday.strip().capitalize()
        day_dishes = [d for d in self.dishes if d.wochentag.lower() == weekday.strip().lower()]
        if not day_dishes:
            return {"weekday": wday_norm, "count": 0}

        filtered = [d.gericht for d in day_dishes if d.gericht.lower() not in ["salatbar", "tagesgericht", ""]]
        fish = sum(1 for d in day_dishes if any(k in d.gericht.lower() for k in ["fisch", "lachs", "scholle", "knusperfisch"]))
        soups = [d.gericht for d in day_dishes if "suppe" in d.kategorie.lower()]

        return {
            "weekday": wday_norm, "count": len(day_dishes),
            "top_dishes": Counter(filtered).most_common(6),
            "top_soups": Counter(soups).most_common(5),
            "fish_dishes_count": fish
        }

    def get_lifecycle(self) -> Dict[str, Any]:
        filtered = [get_canonical_dish(d.gericht) for d in self.dishes if d.gericht.lower() not in ["salatbar", "tagesgericht", ""]]
        counts = Counter(filtered)
        return {
            "staples": [(dish, cnt) for dish, cnt in counts.most_common() if cnt >= 3][:10],
            "one_hit_wonders": [dish for dish, cnt in counts.items() if cnt == 1][:12],
            "one_hit_total": sum(1 for cnt in counts.values() if cnt == 1)
        }


# ==============================================================================
# 8. DEMODATEN-GENERATOR (20 WOCHEN FÜR STATISTIKEN)
# ==============================================================================

def generate_demo_archive(num_weeks: int = 20) -> List[Dish]:
    dishes = []
    base_monday = datetime(2026, 5, 25)
    soups = ["Erbsensuppe mit Speck", "Kürbissuppe mit Kokosmilch", "Toskanische Bohnensuppe",
             "Kartoffelcremesuppe mit Croutons", "Tomaten-Parmesan-Suppe"]
    schnitzels = ["Paniertes Schnitzel | Paprikarahmsoße | Pommes frites",
                  "Paniertes Schnitzel vom Hähnchen | Jägersoße | Pommes frites",
                  "Paniertes Schweineschnitzel | Champignonrahmsoße | Bratkartoffeln"]
    pizzas = ["Pizza Speciale | Schinken | Champignons", "Pizza Margherita | Basilikum", "Pizza Diavolo | Salami"]
    fish = ["Knusperfisch | Remouladensauce | Petersilienkartoffeln", "Gebratenes Lachsfilet | Wildreis"]
    veggies = [("Moroccan Bowl | Harissa-Süßkartoffeln | Couscous", "Vegan"),
               ("Champignon-Pfanne | Knoblauch-Dipp | Drillinge", "Vegetarisch"),
               ("Spaghetti in 7 Kräuterpesto | Kirschtomaten", "Vegan")]
    one_hits = ["Hirschgulasch aus heimischer Jagd | Butterspätzle", "Trüffel-Tagliatelle | frischer Sommertrüffel"]

    for w_idx in range(num_weeks):
        monday = base_monday + timedelta(weeks=w_idx)
        kw, year = monday.isocalendar()[1], monday.year
        for d_idx, wday in enumerate(["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]):
            dt = (monday + timedelta(days=d_idx)).strftime("%Y-%m-%d")
            # Suppe
            dishes.append(Dish(kw=kw, jahr=year, datum=dt, wochentag=wday, kategorie="Suppe",
                               gericht=soups[(w_idx * 5 + d_idx) % len(soups)], preis_mitarbeiter="2,80 €", preis_gaeste="4,60 €"))
            # Leibspeise 1
            if wday == "Donnerstag":
                ls1 = schnitzels[w_idx % len(schnitzels)]
            elif wday == "Freitag":
                ls1 = fish[w_idx % len(fish)]
            elif w_idx == 4 and d_idx == 1:
                ls1 = one_hits[0]
            elif w_idx == 8 and d_idx == 2:
                ls1 = one_hits[1]
            else:
                ls1 = "Saftiges Kotelett | Schmorzwiebel | Bratkartoffeln" if d_idx % 2 == 0 else "Dönerteller vom Hähnchen | Pommes"
            dishes.append(Dish(kw=kw, jahr=year, datum=dt, wochentag=wday, kategorie="Leibspeise 1",
                               gericht=ls1, preis_mitarbeiter="4,60 €", preis_gaeste="7,90 €"))
            # Leibspeise 2
            v_dish, v_diet = veggies[(w_idx * 5 + d_idx) % len(veggies)]
            dishes.append(Dish(kw=kw, jahr=year, datum=dt, wochentag=wday, kategorie="Leibspeise 2",
                               gericht=v_dish, preis_mitarbeiter="4,60 €", preis_gaeste="7,90 €", eigenschaften=v_diet))
            # Leibspeise 3
            ls3 = pizzas[w_idx % len(pizzas)] if wday == "Donnerstag" else "Tagesgericht"
            dishes.append(Dish(kw=kw, jahr=year, datum=dt, wochentag=wday, kategorie="Leibspeise 3",
                               gericht=ls3, preis_mitarbeiter="4,60 €", preis_gaeste="7,90 €"))
            # Salatbar
            dishes.append(Dish(kw=kw, jahr=year, datum=dt, wochentag=wday, kategorie="Salatbar",
                               gericht="Salatbar", preis_mitarbeiter="4,60 €", preis_gaeste="3,00 € / 5,80 €"))
    return dishes


# ==============================================================================
# 9. CLI-HANDLER & FORMATIERTE AUSGABE
# ==============================================================================

def print_footer_hint():
    """Gibt einen dezenten Hinweis auf die Hilfeseite (-h) am Ende interaktiver Ausgaben aus."""
    script = os.path.basename(sys.argv[0])
    print(f"{DIM}💡 Tipp: Für alle weiteren Optionen und Beispiele: ./{script} -h{RESET}\n")


def ensure_week_menu(force_update: bool = False, offline: bool = False) -> WeekMenu:
    """
    Stellt sicher, dass der Wochenplan der aktuellen Kalenderwoche geladen ist:
    1. Prüft den lokalen Cache (data/kwXX_YYYY.csv).
    2. Falls nicht vorhanden (oder force_update=True), wird das Bild geladen und OCR ausgeführt.
    3. Speichert die neue Wochen-CSV und führt das Langzeitarchiv (data/archive.csv) nach.
    """
    ensure_data_dirs()
    now = datetime.now()
    cur_kw, cur_year = now.isocalendar()[1], now.isocalendar()[0]
    expected_csv = get_week_csv_path(cur_kw, cur_year)

    # 1. Schneller Cache-Treffer: CSV existiert bereits lokal
    if not force_update and os.path.exists(expected_csv):
        return load_week_csv(expected_csv)

    # 2. Offline-Modus: Neuesten lokalen Wochenplan aus dem Ordner laden
    if offline:
        latest = find_latest_local_week()
        if latest:
            return latest
        raise RuntimeError("Kein lokaler Speiseplan vorhanden und --offline aktiv.")

    # 3. Vor dem Web-Download prüfen, ob Tesseract für die Bilderkennung bereitsteht
    tess = find_tesseract_binary()
    if not tess:
        print_missing_tesseract_help()
        sys.exit(1)

    # 4. Bild von Website abrufen, OCR durchführen und CSVs aktualisieren
    print(f"{CYAN}ℹ Lade aktuellen Speiseplan von {DEFAULT_URL} herunter...{RESET}", file=sys.stderr)
    img_path = fetch_latest_menu_image()
    print(f"{CYAN}ℹ Führe OCR-Tabellenanalyse durch...{RESET}", file=sys.stderr)
    menu = parse_menu_image(img_path)
    csv_file = save_week_csv(menu)
    total = update_archive_csv(menu)
    print(f"{GREEN}✓ KW {menu.kw} gespeichert ({csv_file}, {total} Gerichte im Archiv).{RESET}\n", file=sys.stderr)
    return menu


def print_banner_alerts(menu: WeekMenu, wm: WatchlistManager):
    """Prüft die Watchlist und gibt bei Treffern ein auffälliges Alarm-Banner aus."""
    hits = wm.check_menu(menu)
    if hits:
        print(f"\n{BG_YELLOW}{BOLD}{WHITE} 🔔 LIEBLINGSGERICHT-ALARM! {RESET}")
        for alert in wm.format_alerts(hits, detailed=True):
            print(f"  {YELLOW}👉 {BOLD}{alert}{RESET}")
        print()


def print_day_menu(dm: DayMenu, is_today: bool = False):
    """Gibt das Tagesangebot mit Preisen (MA/Gäste), Kalorien und Siegeln strukturiert aus."""
    today = f" {GREEN}(Heute){RESET}" if is_today else ""
    print(f"{BOLD}{CYAN}══════════════════════════════════════════════════════════════════{RESET}")
    print(f" {BOLD}{dm.wochentag}{RESET}, {dm.datum}{today}")
    print(f"{BOLD}{CYAN}══════════════════════════════════════════════════════════════════{RESET}")
    for dish in dm.dishes:
        # Ernährungs-Badge (Vegan / Vegetarisch)
        badge = f" {GREEN}[VEGAN]{RESET}" if dish.eigenschaften == "Vegan" else (f" {YELLOW}[VEGETARISCH]{RESET}" if dish.eigenschaften == "Vegetarisch" else "")
        # Mitarbeiter- und Gästepreis
        price = f" {DIM}(MA: {dish.preis_mitarbeiter} | Gäste: {dish.preis_gaeste}){RESET}" if dish.preis_mitarbeiter else ""
        # Kalorienwert
        cal = f" {DIM}[{dish.kalorien}]{RESET}" if dish.kalorien else ""
        print(f"  {BOLD}• {dish.kategorie}:{RESET} {dish.gericht}{badge}{price}{cal}")
    print()


def cmd_show(args, wm: WatchlistManager):
    """CLI-Handler für Tages- und Wochenanzeigen (heute, morgen, woche oder Wochentag)."""
    menu = ensure_week_menu(force_update=args.update, offline=args.offline)
    now = datetime.now()
    cur_wday = WEEKDAYS_DE[now.weekday()]

    # Watchlist-Alarm als Banner einblenden (außer wenn unterdrückt)
    if not args.no_alert:
        print_banner_alerts(menu, wm)

    target = args.target.strip().lower() if args.target else "heute"

    # Fall A: Heutiger Tag
    if target in ["heute", "today"]:
        if cur_wday in ["Samstag", "Sonntag"]:
            print(f"{YELLOW}Heute ist {cur_wday} – am Wochenende hat die Kantine geschlossen.{RESET}")
            for w in ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]:
                dm = menu.get_day(w)
                if dm:
                    print_day_menu(dm, is_today=False)
        else:
            dm = menu.get_day(cur_wday)
            if dm:
                print_day_menu(dm, is_today=True)

    # Fall B: Nächster Tag
    elif target in ["morgen", "tomorrow"]:
        tm = now + timedelta(days=1)
        tm_wday = WEEKDAYS_DE[tm.weekday()]
        if tm_wday in ["Samstag", "Sonntag"]:
            print(f"{YELLOW}Morgen ist {tm_wday} – die Kantine hat geschlossen.{RESET}")
        else:
            dm = menu.get_day(tm_wday)
            if dm:
                print_day_menu(dm, is_today=False)

    # Fall C: Komplette Wochenübersicht
    elif target in ["woche", "week", "alle"]:
        print(f"\n{BOLD}SPEISEPLAN KW {menu.kw} ({menu.start_date} bis {menu.end_date}) - HessenTreff (Kaiberg Kitchen){RESET}\n")
        for w in ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]:
            dm = menu.get_day(w)
            if dm:
                print_day_menu(dm, is_today=(w == cur_wday))

    # Fall D: Spezifischer Wochentag (z.B. donnerstag, freitag)
    else:
        matched = next((w for w in ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"] if w.lower().startswith(target)), None)
        if matched:
            dm = menu.get_day(matched)
            if dm:
                print_day_menu(dm, is_today=(matched == cur_wday))
        else:
            print(f"{RED}Unbekannter Wochentag: '{args.target}'. Erlaubt: heute, morgen, woche, montag..freitag.{RESET}")


def cmd_search(args):
    """CLI-Handler für die Archivsuche: findet Termine und Details zu früheren Gerichten."""
    q = args.query.strip()
    if not q:
        print(f"{RED}Suchbegriff angeben: ./{os.path.basename(sys.argv[0])} search <Begriff>{RESET}")
        return
    results = search_archive(q)
    if not results:
        print(f"{YELLOW}Keine Einträge für '{q}' im Archiv gefunden.{RESET}")
        return

    # Neuesten Treffer prominent hervorheben
    print(f"\n{BOLD}{CYAN}Suchergebnisse im Archiv für '{q}':{RESET} ({len(results)} Treffer)\n")
    latest = results[0]
    print(f"{GREEN}⭐ Zuletzt im Angebot:{RESET}")
    print(f"  {BOLD}Datum:{RESET}       {latest.wochentag}, {latest.datum} (KW {latest.kw}/{latest.jahr})")
    print(f"  {BOLD}Kategorie:{RESET}   {latest.kategorie}")
    print(f"  {BOLD}Gericht:{RESET}     {latest.gericht}")
    if latest.preis_mitarbeiter:
        print(f"  {BOLD}Preise:{RESET}      Mitarbeiter {latest.preis_mitarbeiter} / Gäste {latest.preis_gaeste}")
    print()

    # Ältere Termine chronologisch absteigend auflisten
    if len(results) > 1:
        print(f"{BOLD}Frühere Termine:{RESET}")
        for r in results[1:8]:
            print(f"  • {r.datum} ({r.wochentag[:2]}, KW {r.kw}): {r.gericht}")
    print()


def cmd_watch(args, wm: WatchlistManager):
    """CLI-Handler für die Verwaltung der Lieblingsgerichte (Watchlist)."""
    action = args.watch_action
    # Watchlist auflisten
    if action == "list":
        items = wm.list_keywords()
        print(f"\n{BOLD}{CYAN}Watchlist für Lieblingsgerichte:{RESET}")
        if not items:
            print(f"  {DIM}(leer – hinzufügen mit: ./{os.path.basename(sys.argv[0])} watch add \"Burger\"){RESET}\n")
        else:
            for it in items:
                print(f"  • {GREEN}{it}{RESET}")
            print()
    # Begriff hinzufügen
    elif action == "add":
        if wm.add(args.keyword):
            print(f"{GREEN}✓ '{args.keyword}' zur Watchlist hinzugefügt.{RESET}")
        else:
            print(f"{YELLOW}ℹ Bereits vorhanden oder ungültig.{RESET}")
    # Begriff entfernen
    elif action in ["remove", "del", "rm"]:
        if wm.remove(args.keyword):
            print(f"{GREEN}✓ '{args.keyword}' aus Watchlist entfernt.{RESET}")
        else:
            print(f"{YELLOW}ℹ Nicht gefunden.{RESET}")


def cmd_alert_silent(args, wm: WatchlistManager):
    """
    CLI-Handler für Cronjobs & Shell-Skripte:
    Völlig stumm (0 Zeichen Ausgabe), solange kein Lieblingsgericht auf der aktuellen
    Wochenkarte steht. Bei Treffern wird pro Gericht eine Alarmzeile ausgegeben.
    """
    try:
        menu = ensure_week_menu(force_update=args.update, offline=args.offline)
    except Exception:
        sys.exit(0)
    hits = wm.check_menu(menu)
    if hits:
        for alert in wm.format_alerts(hits, detailed=False):
            print(alert)
    sys.exit(0)


def cmd_stats(args):
    """
    CLI-Handler für statistische Auswertungen des Archivs:
    - overview/dashboard: Kennzahlen, Fleischarten-Balkendiagramm, Top-Gerichte, Ø Preis
    - dish: An welchem Wochentag gab es ein bestimmtes Gericht meistens?
    - combos: Welche Soßen und Beilagen werden am häufigsten dazu serviert?
    - weekday: Charakteristik eines Wochentags (z. B. Fisch-Quote am Freitag)
    - lifecycle: Dauerbrenner (>= 3x serviert) versus Eintagsfliegen (nur 1x)
    """
    dishes = generate_demo_archive(20) if getattr(args, "demo", False) else load_archive_dishes()
    src_label = f"{YELLOW}(DEMO: 20 Wochen / {len(dishes)} Gerichte){RESET}" if getattr(args, "demo", False) else f"{CYAN}(Echtes Archiv: {len(dishes)} Gerichte){RESET}"

    if not dishes:
        print(f"{YELLOW}Archiv leer. Erst './speiseplan.py update' ausführen oder '--demo' nutzen.{RESET}")
        return

    ca = CanteenAnalytics(dishes)
    mode = getattr(args, "mode", "overview") or "overview"
    as_json = getattr(args, "json", False)

    # Modus 1: Gesamt-Dashboard mit Fleischartenanalyse
    if mode in ["overview", "dashboard"]:
        ov = ca.get_overview()
        if as_json:
            print(json.dumps(ov, ensure_ascii=False, indent=2))
            return
        print(f"\n{BOLD}{CYAN}══════════════════════════════════════════════════════════════════{RESET}")
        print(f" {BOLD}KANTINEN-ANALYSE & DASHBOARD{RESET} {src_label}")
        print(f"{BOLD}{CYAN}══════════════════════════════════════════════════════════════════{RESET}")
        print(f"  • Erfasste Speisen:       {BOLD}{ov['total_dishes']}{RESET} Gerichte ({ov['total_weeks']} Wochen)")
        print(f"  • Zeitraum:               {ov['date_start']} bis {ov['date_end']}")
        print(f"  • Ø Preis Hauptgerichte:  {BOLD}{ov['avg_price_employee']:.2f} €{RESET}\n")

        # Fleischarten & Proteinquellen (mit Balkendiagramm)
        print(f"{BOLD}🥩 Fleischarten & Proteinquellen (Hauptgerichte):{RESET}")
        m_dist = ov["meat_distribution"]
        m_max = max(m_dist.values()) if m_dist else 1
        m_total = sum(m_dist.values()) if m_dist else 1
        for meat, cnt in sorted(m_dist.items(), key=lambda x: x[1], reverse=True):
            pct = (cnt / m_total) * 100
            bar = render_ascii_bar(cnt, m_max, 14)
            print(f"  {meat:26s} {CYAN}{bar}{RESET} {BOLD}{cnt:2d}x{RESET} ({pct:4.1f}%)")
        print()

        # Beliebteste Dauerbrenner
        print(f"{BOLD}⭐ Häufigste Gerichte:{RESET}")
        for dish, cnt in ov["top_dishes"]:
            print(f"  • {BOLD}{cnt}x{RESET}: {dish}")
        print()
        print(f"{BOLD}🔄 Lebenszyklus:{RESET} {ov['staples_count']} Klassiker (≥ 3x), {ov['one_hit_wonders_count']} Eintagsfliegen (nur 1x).")
        print(f"  {DIM}(Details mit: ./{os.path.basename(sys.argv[0])} stats lifecycle){RESET}\n")

    # Modus 2: Wochentagsmuster eines Gerichts (z. B. "Wann gab es meistens Pizza?")
    elif mode in ["dish", "gericht"]:
        q = " ".join(getattr(args, "param", []))
        if not q:
            print(f"{RED}Gericht angeben: ./{os.path.basename(sys.argv[0])} stats dish <Name>{RESET}")
            return
        res = ca.analyze_dish(q)
        if as_json:
            print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
            return
        if not res["found"]:
            print(f"{YELLOW}Keine Treffer für '{q}'.{RESET}")
            return
        print(f"\n{BOLD}{CYAN}Wochentags-Muster für '{q}'{RESET} {src_label}")
        print(f"  • Gesamthäufigkeit: {BOLD}{res['count']}x{RESET} (Zuletzt: {res['latest_weekday']}, {res['latest_date']})")
        m_cnt = max(res["weekday_distribution"].values()) if res["weekday_distribution"] else 1
        for w in ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]:
            cnt = res["weekday_distribution"].get(w, 0)
            if cnt > 0:
                print(f"  {w:12s} {CYAN}{render_ascii_bar(cnt, m_cnt, 14)}{RESET} {BOLD}{cnt:2d}x{RESET}")
        print()

    # Modus 3: Häufigste Kombinationen (Soßen & Beilagen zum Schnitzel)
    elif mode in ["combos", "sauce", "beilagen"]:
        q = " ".join(getattr(args, "param", []))
        if not q:
            print(f"{RED}Gericht angeben: ./{os.path.basename(sys.argv[0])} stats combos <Name>{RESET}")
            return
        res = ca.analyze_combos(q)
        if as_json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return
        if not res["found"]:
            print(f"{YELLOW}Keine Treffer für '{q}'.{RESET}")
            return
        print(f"\n{BOLD}{CYAN}Soßen & Beilagen zu '{q}'{RESET} {src_label}")
        if res["top_sauces"]:
            print(f"{BOLD}🥣 Häufigste Soßen:{RESET}")
            m_s = res["top_sauces"][0][1]
            for s, c in res["top_sauces"]:
                print(f"  • {s:30s} {CYAN}{render_ascii_bar(c, m_s, 12)}{RESET} {BOLD}{c:2d}x{RESET}")
            print()
        if res["top_sides"]:
            print(f"{BOLD}🥔 Häufigste Beilagen:{RESET}")
            m_b = res["top_sides"][0][1]
            for b, c in res["top_sides"]:
                print(f"  • {b:30s} {CYAN}{render_ascii_bar(c, m_b, 12)}{RESET} {BOLD}{c:2d}x{RESET}")
            print()

    # Modus 4: Spezifische Analyse eines Wochentags (z. B. Freitag)
    elif mode in ["weekday", "tag"]:
        p = " ".join(getattr(args, "param", [])) or "Freitag"
        res = ca.analyze_weekday(p)
        if as_json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return
        print(f"\n{BOLD}{CYAN}Charakteristik am {res['weekday']}{RESET} {src_label}")
        if res["fish_dishes_count"] > 0:
            print(f"  • 🐟 Fischgerichte: {BOLD}{res['fish_dishes_count']}x{RESET}")
        print(f"{BOLD}Top-Gerichte:{RESET}")
        for d, c in res["top_dishes"][:5]:
            print(f"  • {BOLD}{c:2d}x{RESET}: {d}")
        print()

    # Modus 5: Lebenszyklus (Dauerbrenner vs. Eintagsfliegen)
    elif mode in ["lifecycle", "klassiker"]:
        res = ca.get_lifecycle()
        if as_json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return
        print(f"\n{BOLD}{CYAN}Klassiker vs. Eintagsfliegen{RESET} {src_label}\n")
        print(f"{BOLD}🏆 Dauerbrenner (≥ 3x serviert):{RESET}")
        for d, c in res["staples"]:
            print(f"  • {BOLD}{c:2d}x{RESET}: {d}")
        print(f"\n{BOLD}🌟 Eintagsfliegen ({res['one_hit_total']} Gerichte nur genau 1x):{RESET}")
        for d in res["one_hit_wonders"][:8]:
            print(f"  • {d}")
        print()


# ==============================================================================
# 10. HAUPTEINSTIEG & HILFESEITE
# ==============================================================================

DOC_DESCRIPTION = f"""{BOLD}Speiseplan CLI - HessenTreff (Kaiberg Kitchen){RESET}
Lädt den wöchentlichen Speiseplan per OCR von der Webseite herunter, speichert ihn
in CSV-Dateien (pro KW und Langzeitarchiv), ermöglicht flexible Abfragen, Archivsuche,
statistische Auswertungen (inkl. Fleischarten) und Lieblingsgericht-Benachrichtigungen.

Kompatibel mit Linux, macOS und Windows 11."""

HELP_EPILOG = f"""
{BOLD}{CYAN}══════════════════════════════════════════════════════════════════════════════{RESET}
 {BOLD}BEFEHLE & ECHTE BEISPIELE ZUM AUSPROBIEREN{RESET}
{BOLD}{CYAN}══════════════════════════════════════════════════════════════════════════════{RESET}

{BOLD}📅 1. TAGES- & WOCHENABFRAGEN:{RESET}
  {GREEN}./speiseplan.py{RESET}                          Zeigt das heutige Menü (inkl. Alarm-Banner)
  {GREEN}./speiseplan.py heute{RESET}                    Heutiges Angebot im HessenTreff
  {GREEN}./speiseplan.py morgen{RESET}                   Angebot für morgen
  {GREEN}./speiseplan.py donnerstag{RESET}               Menü für Donnerstag (Montag - Freitag)
  {GREEN}./speiseplan.py woche{RESET}                    Komplette Wochenübersicht (Mo-Fr)
  {GREEN}./speiseplan.py update{RESET}                   Aktuellen Plan live von Website neu laden

{BOLD}🔎 2. HISTORISCHE ARCHIVSUCHE:{RESET}
  {GREEN}./speiseplan.py search "Burger"{RESET}           Wann gab es zuletzt Burger und wie oft?
  {GREEN}./speiseplan.py search "Schnitzel"{RESET}        Findet alle Termine für Schnitzel
  {GREEN}./speiseplan.py search "Pizza"{RESET}            Historische Termine für Pizza

{BOLD}📊 3. STATISTIKEN & AUSWERTUNGEN (mit ASCII-Diagrammen):{RESET}
  {GREEN}./speiseplan.py stats{RESET}                          Dashboard (Fleischarten, Top-Gerichte, Ø Preis)
  {GREEN}./speiseplan.py stats --demo{RESET}                   20-Wochen-Historie mit 500 Gerichten testen
  {GREEN}./speiseplan.py stats dish "Pizza" --demo{RESET}         An welchem Tag gab es meistens Pizza?
  {GREEN}./speiseplan.py stats combos "Schnitzel" --demo{RESET}     Häufigste Soßen & beliebteste Beilagen
  {GREEN}./speiseplan.py stats weekday freitag --demo{RESET}      Tagescharakteristik (z.B. Fisch am Freitag)
  {GREEN}./speiseplan.py stats lifecycle --demo{RESET}          Klassiker (≥ 3x) vs. Eintagsfliegen (1x)
  {GREEN}./speiseplan.py stats --demo --json{RESET}            Ergebnisse als strukturiertes JSON

{BOLD}🔔 4. WATCHLIST FÜR LIEBLINGSGERICHTE:{RESET}
  {GREEN}./speiseplan.py watch add "Burger"{RESET}            'Burger' zur Überwachung hinzufügen
  {GREEN}./speiseplan.py watch list{RESET}                    Gespeicherte Lieblingsgerichte anzeigen
  {GREEN}./speiseplan.py watch remove "Burger"{RESET}         'Burger' aus der Watchlist entfernen

{BOLD}🤖 5. SILENT-CHECK (für Cronjobs & Shell-Skripte):{RESET}
  {GREEN}./speiseplan.py alert{RESET}                         Bleibt völlig stumm (0 Zeichen), außer ein
                                                beobachtetes Gericht steht diese Woche auf
                                                der Karte (z. B. 'hey, Donnerstag gibt es Burger!').

{BOLD}ℹ️  6. SYSTEMDIAGNOSE & HILFE:{RESET}
  {GREEN}./speiseplan.py hilfe{RESET}                         Zeigt diese Hilfeseite (auch mit -h oder --help)
  {GREEN}./speiseplan.py --install-help{RESET}                Tesseract-Status & Installationsanleitung für alle OS
  {GREEN}./speiseplan.py install-help{RESET}                  (Alternative ohne Bindestriche)
"""


def main():
    """Haupteinstiegspunkt: parst Befehlszeilenargumente und delegiert an CLI-Handler."""
    wm = WatchlistManager()
    first_arg = (sys.argv[1].lower() if len(sys.argv) > 1 else "").strip()

    # 1. Diagnose- & Installationshilfe (--install-help oder install-help)
    if first_arg in ["install-help", "install-info", "doctor", "--install-help", "-i"]:
        cmd_install_help()
        return

    # 2. Direkte Hilfebefehle ohne Minus (hilfe oder help)
    if first_arg in ["hilfe", "help"]:
        parser = argparse.ArgumentParser(
            description=DOC_DESCRIPTION,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=HELP_EPILOG
        )
        parser.add_argument("target", nargs="?", default="heute", help="heute, morgen, woche, montag, dienstag, hilfe...")
        parser.add_argument("--update", "-u", action="store_true", help="Erzwingt Aktualisierung von der Webseite")
        parser.add_argument("--offline", action="store_true", help="Keine Netzwerkverbindung aufbauen")
        parser.add_argument("--no-alert", action="store_true", help="Kein Alarm-Banner anzeigen")
        parser.add_argument("--install-help", "-i", action="store_true", help="Zeigt Tesseract-Status und Installationshilfe")
        parser.print_help()
        return

    # 3. Archivsuche (search <Begriff>)
    if first_arg == "search":
        parser = argparse.ArgumentParser(description="Archiv nach Gerichten durchsuchen")
        parser.add_argument("subcmd")
        parser.add_argument("query", nargs="*", help="Suchbegriff im Archiv")
        args = parser.parse_args()
        args.query = " ".join(args.query)
        cmd_search(args)
        print_footer_hint()
        return

    # 4. Statistiken und Auswertungen (stats [mode] [param] [--demo] [--json])
    elif first_arg in ["stats", "analyse"]:
        parser = argparse.ArgumentParser(description="Statistiken und Auswertungen")
        parser.add_argument("subcmd")
        parser.add_argument("mode", nargs="?", default="overview",
                            choices=["overview", "dashboard", "dish", "combos", "weekday", "lifecycle"])
        parser.add_argument("param", nargs="*", help="Gericht oder Wochentag")
        parser.add_argument("--demo", action="store_true", help="20-Wochen-Demodatensatz nutzen")
        parser.add_argument("--json", action="store_true", help="JSON-Ausgabe")
        args = parser.parse_args()
        cmd_stats(args)
        if not getattr(args, "json", False):
            print_footer_hint()
        return

    # 5. Watchlist verwalten (watch list | add | remove <Begriff>)
    elif first_arg == "watch":
        parser = argparse.ArgumentParser(description="Watchlist verwalten")
        parser.add_argument("subcmd")
        parser.add_argument("watch_action", nargs="?", choices=["list", "add", "remove", "del", "rm"], default="list")
        parser.add_argument("keyword", nargs="*", help="Suchbegriff")
        args = parser.parse_args()
        args.keyword = " ".join(args.keyword)
        cmd_watch(args, wm)
        print_footer_hint()
        return

    # 6. Silent-Check für Cronjobs (alert [--update] [--offline])
    elif first_arg == "alert":
        parser = argparse.ArgumentParser(description="Silent-Check für Cronjobs")
        parser.add_argument("subcmd")
        parser.add_argument("--update", "-u", action="store_true")
        parser.add_argument("--offline", action="store_true")
        args = parser.parse_args()
        cmd_alert_silent(args, wm)
        return

    # 7. Speiseplan neu von Website laden (update)
    elif first_arg == "update":
        parser = argparse.ArgumentParser(description="Speiseplan neu laden")
        parser.add_argument("subcmd")
        args = parser.parse_args()
        menu = ensure_week_menu(force_update=True, offline=False)
        print(f"{GREEN}✓ KW {menu.kw} erfolgreich aktualisiert!{RESET}")
        print_footer_hint()
        return

    # 8. Standard-Tages- und Wochenabfragen (heute, morgen, woche, montag...freitag)
    parser = argparse.ArgumentParser(
        description=DOC_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=HELP_EPILOG
    )
    parser.add_argument("target", nargs="?", default="heute", help="heute, morgen, woche, montag, dienstag...")
    parser.add_argument("--update", "-u", action="store_true", help="Erzwingt Aktualisierung von der Webseite")
    parser.add_argument("--offline", action="store_true", help="Keine Netzwerkverbindung aufbauen")
    parser.add_argument("--no-alert", action="store_true", help="Kein Alarm-Banner anzeigen")
    parser.add_argument("--install-help", "-i", action="store_true", help="Zeigt Tesseract-Status und Installationshilfe")

    args = parser.parse_args()
    if args.install_help:
        cmd_install_help()
        return
    if args.target.lower() in ["hilfe", "help"]:
        parser.print_help()
        return
    cmd_show(args, wm)
    print_footer_hint()


if __name__ == "__main__":
    main()
