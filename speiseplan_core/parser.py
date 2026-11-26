"""
speiseplan_core/parser.py — PDF- & Bild-Tabellenparser (mit automatischem OCR-Fallback).

Wie funktioniert das Auslesen der Wochenkarte?
1. **PDF-Direktextraktion (`parse_menu_pdf`) — Standardweg:**
   - Rendert Seite 1 der PDF-Datei kurz als PNG (`pdftoppm -r 150`), damit:
     a) `detect_grid()` die exakten Spalten- und Zeilengrenzen der Tabelle findet,
     b) `detect_diet_badge()` grüne (Vegetarisch) und orange (Vegan) Siegel anhand
        ihrer Pixel-Farbe erkennen kann (auch zeilenweite Siegel in Spalte 0!),
     c) unsichtbare/überdeckte Alt-Textebenen in Korrektur-PDFs erkannt werden.
   - Liest gleichzeitig alle Textblöcke inkl. Koordinaten per `pdftohtml -xml` aus
     und ordnet sie exakt den ermittelten Tabellenzellen zu.
   - Falls die PDF kaum maschinenlesbaren Text enthält (z. B. reines Scan-PDF),
     schaltet der Parser automatisch auf `parse_menu_image()` (Tesseract OCR) um.

2. **Bild-OCR (`parse_menu_image`) — Fallback für Screenshots & Scan-PDFs:**
   - Erkennt ebenfalls über `detect_grid()` das Tabellenraster (auch bei manuell
     zugeschnittenen Screenshots), schneidet jede Zelle aus und liest sie über
     Tesseract (`run_tesseract`) mit deutschem Sprachmodell aus.

Einstiegspunkt: `parse_menu_file(file_path)` entscheidet automatisch anhand `.pdf`.
"""

from datetime import datetime, timedelta
import io
import os
import re
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image

from .config import (
    find_poppler_tool,
    find_tesseract_binary,
    get_tesseract_ocr_args,
    print_missing_tesseract_help,
)
from .models import DayMenu, Dish, WeekMenu
from .text_cleaning import clean_cell_text, parse_category_cell, parse_header_info_from_text


def run_tesseract(crop: Image.Image, psm: int = 6) -> str:
    """Führt Tesseract OCR über stdin/stdout auf einem Bildausschnitt aus (mit `deu`-Sprachmodell)."""
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
    """
    Ermittelt dynamisch die 7 horizontalen und 7 vertikalen Trennlinien der Speiseplan-Tabelle.
    Passt sich automatisch an variierende Bildauflösungen, Ränder und manuelle Zuschnitte an.
    """
    rgb = image.convert("RGB")
    arr = np.array(rgb)
    h, w, _ = arr.shape

    # 1. Spalten ermitteln:
    # Im vertikalen Tabellenkörper (25% bis 85% der Höhe) haben Trennlinien eine sehr geringe Farbvarianz.
    body = arr[int(h * 0.25):int(h * 0.85), :]
    v_stds = np.std(body, axis=0).mean(axis=1)
    v_means = np.mean(body, axis=0)

    cand_v = []
    for x in range(int(w * 0.02), int(w * 0.98)):
        if v_stds[x] < 3.0 and (v_means[x] < 240).any():
            cand_v.append(x)

    v_groups = []
    for x in cand_v:
        if not v_groups or x > v_groups[-1][-1] + 5:
            v_groups.append([x])
        else:
            v_groups[-1].append(x)

    v_lines_raw = [int(np.mean(g)) for g in v_groups]
    left_edge = min([x for x in v_lines_raw if x < w * 0.10], default=int(w * 0.04))
    col0_right = min([x for x in v_lines_raw if int(w * 0.12) <= x <= int(w * 0.22)], default=int(w * 0.16))
    right_edge = max([x for x in v_lines_raw if x > w * 0.90], default=int(w * 0.96))

    # Die 5 Wochentage teilen sich den Raum zwischen Spalte 0 und rechtem Rand gleichmäßig
    day_col_width = (right_edge - col0_right) / 5.0
    v_lines = [left_edge, col0_right] + [int(col0_right + i * day_col_width) for i in range(1, 6)]

    # 2. Dunkler Header-Balken (KW & Wochentage) auffinden
    table_slice = arr[:, int(col0_right + 20):int(right_edge - 20)]
    row_means = np.mean(table_slice, axis=(1, 2))

    header_top = None
    header_bottom = None
    cur_start = None
    for y in range(int(h * 0.15), int(h * 0.35)):
        if row_means[y] < 245:
            if cur_start is None:
                cur_start = y
        else:
            if cur_start is not None:
                if y - cur_start >= 30:
                    header_top = cur_start
                    header_bottom = y
                    break
                cur_start = None

    if header_top is None:
        header_top = int(h * 0.20)
    if header_bottom is None:
        header_bottom = int(header_top + h * 0.055)

    # 3. Horizontale Trennlinien zwischen den 5 Gerichtszeilen ermitteln
    h_stds = np.std(table_slice, axis=1).mean(axis=1)
    cand_h = []
    for y in range(header_bottom + 15, int(h * 0.95)):
        if h_stds[y] < 8.0 and row_means[y] < 248:
            cand_h.append(y)

    h_groups = []
    for y in cand_h:
        if not h_groups or y > h_groups[-1][-1] + 8:
            h_groups.append([y])
        else:
            h_groups[-1].append(y)

    raw_dividers = [int(np.mean(g)) for g in h_groups]

    # Mindestabstand von 40px zwischen Zeilentrennern einhalten
    dividers = []
    for d in raw_dividers:
        if not dividers or d - dividers[-1] >= 40:
            dividers.append(d)

    if len(dividers) == 5:
        selected_divs = dividers
    elif len(dividers) > 5:
        selected_divs = dividers[:5]
    else:
        # Fallback: geometrische Interpolation anhand des Tabellenendes
        table_bottom = dividers[-1] if dividers else int(h * 0.86)
        body_h = table_bottom - header_bottom
        ratios = [0.17, 0.44, 0.71, 0.86, 1.0]
        selected_divs = [int(header_bottom + body_h * r) for r in ratios]

    h_lines = [header_top, header_bottom] + selected_divs
    return h_lines, v_lines


def parse_header_info(image: Image.Image, h_top: int) -> Tuple[int, int, str, str]:
    """Liest KW und Datumsspanne per OCR aus dem Tabellenkopf."""
    w, _ = image.size
    header_text = run_tesseract(image.crop((0, 0, w, h_top)), psm=6)
    return parse_header_info_from_text(header_text)


def detect_diet_badge(cell_crop: Image.Image, full_cell: bool = False) -> str:
    """
    Erkennt runde Vegan- (orange) oder Vegetarisch-Siegel (grün) anhand ihrer RGB-Farben.
    Mit `full_cell=True` wird die komplette Zelle gescannt (wichtig für Spalte 0, z. B. Leibspeise 2).
    """
    w, h = cell_crop.size
    if w < 40 or h < 40:
        return ""

    if full_cell:
        region = cell_crop
    else:
        if w < 60 or h < 60:
            return ""
        region = cell_crop.crop((max(0, w - 85), max(0, h - 85), w, h))
    arr = np.array(region.convert("RGB"))

    # Grüner Kreis (Vegetarisch)
    green_mask = (
        (arr[:, :, 0] >= 50) & (arr[:, :, 0] <= 125)
        & (arr[:, :, 1] >= 105) & (arr[:, :, 1] <= 175)
        & (arr[:, :, 2] <= 45)
    )
    if green_mask.sum() > 300:
        return "Vegetarisch"

    # Oranger Kreis (Vegan)
    orange_mask = (
        (arr[:, :, 0] > 200)
        & (arr[:, :, 1] > 70) & (arr[:, :, 1] < 150)
        & (arr[:, :, 2] < 50)
    )
    if orange_mask.sum() > 300:
        return "Vegan"

    return ""


def parse_menu_image(image_path: str) -> WeekMenu:
    """Liest eine Wochenkarte komplett über Bildsegmentierung + Tesseract OCR ein."""
    img = Image.open(image_path)
    h_lines, v_lines = detect_grid(img)
    kw, jahr, start_d, end_d = parse_header_info(img, h_lines[0])

    start_dt = datetime.strptime(start_d, "%Y-%m-%d")
    weekdays_5 = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]
    day_dates = {wday: (start_dt + timedelta(days=i)).strftime("%Y-%m-%d") for i, wday in enumerate(weekdays_5)}

    categories = [
        parse_category_cell(
            run_tesseract(img.crop((v_lines[0] + 3, h_lines[r] + 3, v_lines[1] - 3, h_lines[r + 1] - 3)), psm=6),
            row_idx=r,
        )
        for r in range(1, len(h_lines) - 1)
    ]

    days = {wday: DayMenu(wochentag=wday, datum=day_dates[wday], dishes=[]) for wday in weekdays_5}

    for r_idx, (cat_name, p_ma, p_gaeste) in enumerate(categories, start=1):
        col0_cell = img.crop((v_lines[0] + 3, h_lines[r_idx] + 3, v_lines[1] - 3, h_lines[r_idx + 1] - 3))
        row_diet = detect_diet_badge(col0_cell, full_cell=True) if "salat" not in cat_name.lower() else ""
        for c_idx, wday in enumerate(weekdays_5, start=1):
            cell = img.crop((v_lines[c_idx] + 3, h_lines[r_idx] + 3, v_lines[c_idx + 1] - 3, h_lines[r_idx + 1] - 3))
            raw = run_tesseract(cell, psm=6)
            dish_text, cal, _alg = clean_cell_text(raw)

            # Generischen Platzhalter 'Tagesgericht' komplett überspringen (kein Mehrwert)
            norm_dish = re.sub(r"^[\d\s,.*+-]+|[\d\s,.*+-]+$", "", dish_text).strip().lower()
            if not norm_dish or norm_dish == "tagesgericht":
                continue

            diet = detect_diet_badge(cell)
            if not diet:
                low = raw.lower()
                diet = "Vegan" if "vegan" in low else ("Vegetarisch" if "vegetarisch" in low else row_diet)

            # Allergene werden bewusst weggelassen (Hinweis verweist auf Original-Speisekarte)
            days[wday].dishes.append(Dish(
                kw=kw, jahr=jahr, datum=day_dates[wday], wochentag=wday,
                kategorie=cat_name, gericht=dish_text, preis_mitarbeiter=p_ma,
                preis_gaeste=p_gaeste, eigenschaften=diet, kalorien=cal, allergene="",
            ))

    return WeekMenu(kw=kw, jahr=jahr, start_date=start_d, end_date=end_d, days=days)


def _extract_visible_pdf_nodes(
    pdf_path: str, img: Image.Image, h_lines: List[int], v_lines: List[int]
) -> List[Tuple[str, float, float, float, float]]:
    """
    Extrahiert sichtbare Textelemente aus Seite 1 des PDFs via `pdftohtml -xml`.
    Filtert verdeckte Alt-Ebenen heraus (manche Korrektur-PDFs legen ein weißes Bild
    über eine ältere Textebene, die `pdftotext` sonst doppelt/abgeschnitten mitliest).
    """
    pdftohtml_bin = find_poppler_tool("pdftohtml")
    if not pdftohtml_bin:
        return []

    res = subprocess.run([pdftohtml_bin, "-xml", "-i", "-stdout", pdf_path], capture_output=True)
    if res.returncode != 0 or not res.stdout:
        return []

    try:
        root = ET.fromstring(res.stdout)
    except ET.ParseError:
        return []

    page = root.find(".//page")
    if page is None:
        return []

    pw = float(page.attrib.get("width", "0") or 0)
    ph = float(page.attrib.get("height", "0") or 0)
    if pw <= 0 or ph <= 0:
        return []

    iw, ih = img.size
    sx, sy = iw / pw, ih / ph
    gray_arr = np.array(img.convert("L"))
    fonts = {
        f.attrib["id"]: f.attrib.get("family", "").split("+")[-1].split("-")[0]
        for f in page.findall("fontspec")
        if "id" in f.attrib
    }

    nodes: List[Tuple[str, float, float, float, float, str, bool, float]] = []
    for t in page.findall("text"):
        txt = "".join(t.itertext()).strip()
        if not txt:
            continue
        x0 = float(t.attrib.get("left", 0)) * sx
        y0 = float(t.attrib.get("top", 0)) * sy
        x1 = x0 + float(t.attrib.get("width", 0)) * sx
        y1 = y0 + float(t.attrib.get("height", 0)) * sy
        oob = x0 < -2 or y0 < -2 or x1 > iw + 2 or y1 > ih + 2
        cx0, cy0 = max(0, int(x0)), max(0, int(y0))
        cx1, cy1 = min(iw, int(x1)), min(ih, int(y1))
        dark_ratio = float((gray_arr[cy0:cy1, cx0:cx1] < 200).mean()) if (cx1 > cx0 and cy1 > cy0) else 0.0
        base_font = fonts.get(t.attrib.get("font", ""), "unknown")
        nodes.append((txt, x0, y0, x1, y1, base_font, oob, dark_ratio))

    if not nodes:
        return []

    # Falls mehrere Schriftart-Ebenen existieren, die tatsächlich sichtbare Ebene bevorzugen
    by_font: Dict[str, List[Tuple[str, float, float, float, float, str, bool, float]]] = {}
    for nd in nodes:
        by_font.setdefault(nd[5], []).append(nd)

    if len(by_font) > 1:
        def font_visibility_score(items):
            in_bounds = sum(1 for it in items if not it[6])
            oob_cnt = sum(1 for it in items if it[6])
            zero_ink = sum(1 for it in items if it[7] < 0.01)
            in_table = sum(
                1 for it in items
                if not it[6]
                and v_lines[0] <= (it[1] + it[3]) / 2 <= v_lines[-1]
                and h_lines[0] <= (it[2] + it[4]) / 2 <= h_lines[-1]
            )
            mean_dark = sum(it[7] for it in items) / max(len(items), 1)
            return (in_table + in_bounds - oob_cnt * 5 - zero_ink * 3) + mean_dark * 20

        best_font = max(by_font.keys(), key=lambda f: font_visibility_score(by_font[f]))
        best_items = by_font[best_font]
        if len(best_items) >= 35 and sum(1 for it in best_items if it[7] < 0.01) == 0:
            nodes = best_items

    return [
        (txt, x0, y0, x1, y1)
        for (txt, x0, y0, x1, y1, _bf, oob, dark_ratio) in nodes
        if not oob and dark_ratio >= 0.005
    ]


def _join_cell_nodes(cell_nodes: List[Tuple[str, float, float, float, float]]) -> str:
    """Fügt Textfragmente einer Tabellenzelle geordnet nach Zeilen und X-Position zusammen."""
    if not cell_nodes:
        return ""
    sorted_nodes = sorted(cell_nodes, key=lambda n: (n[2], n[1]))
    lines: List[List[Tuple[float, str]]] = []
    cur_y: Optional[float] = None
    cur_h: float = 12.0
    for txt, x0, y0, _x1, y1 in sorted_nodes:
        h = max(y1 - y0, 8.0)
        if cur_y is None or abs(y0 - cur_y) > max(cur_h, h) * 0.45:
            lines.append([(x0, txt)])
            cur_y = y0
            cur_h = h
        else:
            lines[-1].append((x0, txt))
    return "\n".join(" ".join(t for _x, t in sorted(ln, key=lambda p: p[0])) for ln in lines)


def parse_menu_pdf(pdf_path: str) -> WeekMenu:
    """Liest den Speiseplan direkt aus einer PDF-Wochenkarte (mit automatischem OCR-Fallback für Scan-PDFs)."""
    pdftoppm_bin = find_poppler_tool("pdftoppm")
    if not pdftoppm_bin:
        raise FileNotFoundError("pdftoppm (poppler-utils) wurde nicht gefunden.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_prefix = os.path.join(tmp_dir, "page")
        res = subprocess.run(
            [pdftoppm_bin, "-png", "-r", "150", "-f", "1", "-l", "1", pdf_path, out_prefix],
            capture_output=True,
        )
        png_files = sorted(
            os.path.join(tmp_dir, f) for f in os.listdir(tmp_dir) if f.startswith("page") and f.endswith(".png")
        )
        if res.returncode != 0 or not png_files:
            raise RuntimeError(f"PDF-Rendering fehlgeschlagen: {res.stderr.decode(errors='ignore').strip()}")

        rendered_png = png_files[0]
        img = Image.open(rendered_png)
        h_lines, v_lines = detect_grid(img)
        nodes = _extract_visible_pdf_nodes(pdf_path, img, h_lines, v_lines)

        # Fallback auf OCR, falls das PDF keine ausreichende Textebene enthält (z. B. reines Scan-PDF)
        table_nodes = [
            nd for nd in nodes
            if v_lines[0] <= (nd[1] + nd[3]) / 2 <= v_lines[-1]
            and h_lines[1] <= (nd[2] + nd[4]) / 2 <= h_lines[-1]
        ]
        if len(table_nodes) < 10:
            return parse_menu_image(rendered_png)

        header_nodes = [nd for nd in nodes if (nd[2] + nd[4]) / 2 <= h_lines[0] + 15]
        header_text = _join_cell_nodes(header_nodes)
        kw, jahr, start_d, end_d = parse_header_info_from_text(header_text)

        start_dt = datetime.strptime(start_d, "%Y-%m-%d")
        weekdays_5 = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]
        day_dates = {wday: (start_dt + timedelta(days=i)).strftime("%Y-%m-%d") for i, wday in enumerate(weekdays_5)}

        def nodes_in_box(x0: int, y0: int, x1: int, y1: int) -> List[Tuple[str, float, float, float, float]]:
            return [
                nd for nd in nodes
                if x0 <= (nd[1] + nd[3]) / 2 <= x1 and y0 <= (nd[2] + nd[4]) / 2 <= y1
            ]

        days = {wday: DayMenu(wochentag=wday, datum=day_dates[wday], dishes=[]) for wday in weekdays_5}

        for r_idx in range(1, len(h_lines) - 1):
            col0_text = _join_cell_nodes(nodes_in_box(v_lines[0], h_lines[r_idx], v_lines[1], h_lines[r_idx + 1]))
            cat_name, p_ma, p_gaeste = parse_category_cell(col0_text, row_idx=r_idx)
            col0_cell = img.crop((v_lines[0] + 3, h_lines[r_idx] + 3, v_lines[1] - 3, h_lines[r_idx + 1] - 3))
            row_diet = detect_diet_badge(col0_cell, full_cell=True) if "salat" not in cat_name.lower() else ""

            for c_idx, wday in enumerate(weekdays_5, start=1):
                raw = _join_cell_nodes(nodes_in_box(v_lines[c_idx], h_lines[r_idx], v_lines[c_idx + 1], h_lines[r_idx + 1]))
                dish_text, cal, _alg = clean_cell_text(raw)

                norm_dish = re.sub(r"^[\d\s,.*+-]+|[\d\s,.*+-]+$", "", dish_text).strip().lower()
                if not norm_dish or norm_dish == "tagesgericht":
                    continue

                cell = img.crop((v_lines[c_idx] + 3, h_lines[r_idx] + 3, v_lines[c_idx + 1] - 3, h_lines[r_idx + 1] - 3))
                diet = detect_diet_badge(cell)
                if not diet:
                    low = raw.lower()
                    diet = "Vegan" if "vegan" in low else ("Vegetarisch" if "vegetarisch" in low else row_diet)

                days[wday].dishes.append(Dish(
                    kw=kw, jahr=jahr, datum=day_dates[wday], wochentag=wday,
                    kategorie=cat_name, gericht=dish_text, preis_mitarbeiter=p_ma,
                    preis_gaeste=p_gaeste, eigenschaften=diet, kalorien=cal, allergene="",
                ))

        return WeekMenu(kw=kw, jahr=jahr, start_date=start_d, end_date=end_d, days=days)


def parse_menu_file(file_path: str) -> WeekMenu:
    """Parst wahlweise eine PDF-Wochenkarte direkt oder ein Wochenkarten-Bild per OCR."""
    if file_path.lower().endswith(".pdf"):
        return parse_menu_pdf(file_path)
    return parse_menu_image(file_path)
