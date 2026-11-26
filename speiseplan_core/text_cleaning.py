"""
speiseplan_core/text_cleaning.py — Textbereinigung, OCR-Korrektur & Normalisierung.

Warum braucht man dieses Modul?
Roher Text aus Speiseplan-PDFs oder Screenshots enthält neben dem eigentlichen
Gerichtsnamen oft zusätzliche Informationen oder typische Formatierungsprobleme:
- Allergen-Nummern am Zellenende (z. B. "1,4,7" oder "10,11")
- Kalorienangaben (z. B. "ca. 230 kcal*")
- Umgebrochene Bindestrich-Wörter ("Puten-Schlemmer-\\nSchnitzel")
- Typische OCR-Verwechslungen bei Umlauten ("Kurbissuppe" -> "Kürbissuppe")

Dieses Modul trennt sauber:
- `clean_cell_text()`: Trennt Gerichtstitel, Kalorien und Allergene.
- `parse_category_cell()`: Erkennt die Zeile ("Suppe", "Leibspeise 1"..) und Standardpreise.
- `parse_header_info_from_text()`: Liest KW und Wochenspanne (Mo-Fr) aus der Kopfzeile.
- `get_canonical_dish()`: Extrahiert den kurzen Kernnamen für Statistiken (z. B. ohne Soße/Beilage).
"""

from datetime import datetime, timedelta
import re
from typing import Tuple

# ==============================================================================
# 1. OCR-UMLAUT- & VOKABULAR-KORREKTUR
# ==============================================================================

OCR_REPLACEMENTS = [
    # Umlaute & Käse
    (r"\bK(?:[äaöde]{1,2}|)se\b", "Käse"),
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
    (r"Erdn[ui]sse", "Erdnüsse"),
    (r"Tr[uiü]ffel(?:[öo]l|\böl)", "Trüffelöl"),
    (r"Tr[ui]ffel", "Trüffel"),
    (r"([a-zA-Z]*)gem[ui]se\b", r"\1gemüse"),
    (r"([a-zA-Z]*)Gem[ui]se\b", r"\1Gemüse"),
    (r"W[ui]rstchen", "Würstchen"),
    (r"Bohnensu\s*ppe", "Bohnensuppe"),
    # Typische Kaiberg-Gerichte
    (r"Spinatkn[oö]del", "Spinatknödel"),
    (r"\bKn[oö]del\b", "Knödel"),
    (r"S[uü]dtiroler", "Südtiroler"),
    (r"Fl[aä]dlesuppe", "Flädlesuppe"),
    (r"Kr[aä]uters[uü]ppchen", "Kräutersüppchen"),
    (r"Cevapcici", "Cevapcici"),
    (r"Steinpilzrahm", "Steinpilzrahm"),
    (r"Pangasius(?:filet)?", "Pangasiusfilet"),
    (r"all['’]?Arrabbiata", "all’Arrabbiata"),
]


def normalize_ocr_text(text: str) -> str:
    """Bereinigt typische OCR-Fehlinterpretationen von Umlauten und Sonderzeichen."""
    for pattern, repl in OCR_REPLACEMENTS:
        text = re.sub(pattern, repl, text)
    return text


# ==============================================================================
# 2. KANONISCHE KURZNAMEN (FÜR STATISTIK-GRUPPIERUNG)
# ==============================================================================

DECORATIVE_WORDS = [
    "paniert", "saftig", "knusprig", "ausgebacken", "zart", "fein",
    "ofenfrisch", "hausgemacht", "frisch", "herzhaft", "gebraten", "goldbraun",
    "cremig", "würzig", "vegetarisch",
]
DEC_PATTERN = re.compile(
    r"^\s*(" + "|".join(DECORATIVE_WORDS) + r")(?:es|er|em|en|e|s)?\b\s*",
    flags=re.I,
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
            if curr.endswith("-"):
                curr = curr.rstrip("-").strip() + " " + next_part
                i += 1
                continue
            last_token = curr.rstrip().split()[-1].lower() if curr.split() else ""
            clean_last = re.sub(r"^[^\w]+|[^\w]+$", "", last_token)
            if clean_last in DANGLING_PREPS:
                curr = f"{curr} {next_part}"
                i += 1
                continue
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


SIDE_SAUCE_PATTERN = re.compile(
    r"\b(?:"
    r"pommes(?:\s+frites)?\b"
    r"|steakhouse-pommes\b"
    r"|kartoffelstäbchen\b"
    r"|(?:knusprige|cremige|petersilien|salz|brat)?kartoffel(?:n|püree|wedges|klöße|gratin)?\b"
    r"|(?:butter)?spätzle\b"
    r"|drillinge\b"
    r"|(?:basmati|wild|spanischer\s+gewürz)?reis\b"
    r"|(?:orientalischer\s+)?couscous\b"
    r"|kräuterquark\b"
    r"|brokkoli\b"
    r"|rotkohl\b"
    r"|buttergemüse\b"
    r"|wokgemüse\b"
    r"|mediterranes\s+gemüse\b"
    r"|geschmolzene\s+tomaten\b"
    r"|kirschtomaten\b"
    r"|schmorzwiebel\w*"
    r"|spiegelei\b"
    r"|rahmspinat\b"
    r"|frühlingsröllchen\b"
    r"|frische\s+kräuter\b"
    r"|(?:knackiger\s+bunter\s+)?salat\b"
    r"|(?:harissa-)?süßkartoffel\w*"
    r"|schinken\s+mozzarella\b"
    r"|champignons\s+erbsen\b"
    r"|rote\s+zwiebeln\b"
    r"|hokkaido-kürbis\b"
    r"|aromatische\s+gewürze\b"
    r"|sauce\s+\w+"
    r"|frankfurter\s+grüne\s+soße\b"
    r"|(?:(?:cremige|feine|leichte|würzige|aromatische|toskanische)\s+)?(?:[\w\-]+)?(?:soße|sauce|jus|pesto|dipp?|remoulade|mayo)\b"
    r")",
    flags=re.I,
)


def get_canonical_dish(dish_text: str) -> str:
    """Extrahiert die Hauptkomponente eines Gerichts (ohne Füll-Adjektive, Beilagen und Saucen)."""
    cleaned = fix_dangling_components(dish_text)
    if not cleaned:
        return ""
    if "|" in cleaned:
        head = cleaned.split("|")[0].strip()
    else:
        head = cleaned
        for m in SIDE_SAUCE_PATTERN.finditer(cleaned):
            start = m.start()
            if start <= 3:
                continue
            prefix = cleaned[:start].rstrip()
            # Falls vor dem Treffer eine Präposition wie in/auf/an/mit steht, gehört die Zutat zum Gerichtstitel
            if re.search(
                r"\b(?:in|an|auf|mit|von|vom|aus)\s+(?:feine[rm]?|cremige[rm]?|würzige[rm]?|leichte[rm]?|aromatische[rm]?|toskanische[rm]?)?$",
                prefix,
                flags=re.I,
            ):
                continue
            head = prefix
            break

    head = re.sub(r"^[\"\'„“»«\s]+|[\"\'„“»«\s]+$", "", head)
    orig_head = head
    prev = None
    while prev != head:
        prev = head
        head = DEC_PATTERN.sub("", head).strip()
    head = re.sub(r"[\"\'„“»«]", "", head).strip()

    # Nachlaufende Präpositionen und unvollständige Adjektive bereinigen (z. B. 'in feiner')
    dangling_pattern = re.compile(
        r"\s+\b(?:"
        r"in|an|auf|mit|vom|von|aus|nach|bei|im|oder|und"
        r"|(?:fein|cremig|würzig|leicht|toskanisch|aromatisch|hausgemacht|frisch|bunt)(?:e[srmn]?|er)?"
        r")\b\s*$",
        flags=re.I,
    )
    prev = None
    while prev != head:
        prev = head
        head = dangling_pattern.sub("", head).strip()

    return head if head else orig_head


# ==============================================================================
# 3. ZELLEN- & KOPFZEILEN-BEREINIGUNG (FÜR PDF UND BILD-OCR)
# ==============================================================================

def parse_header_info_from_text(header_text: str) -> Tuple[int, int, str, str]:
    """Extrahiert Kalenderwoche, ISO-Jahr und Datumsspanne (Mo–Fr) aus der Kopfzeile."""
    kw_match = re.search(r"KW\s*(\d+)", header_text, re.I)
    kw = int(kw_match.group(1)) if kw_match else datetime.now().isocalendar()[1]

    date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})\s*-\s*(\d{1,2})\.(\d{1,2})\.(\d{4})", header_text)
    if date_match:
        d1, m1, y1, d2, m2, y2 = date_match.groups()
        try:
            start_dt = datetime(int(y1), int(m1), int(d1))
            # Das ISO-Jahr entspricht immer dem Kalenderjahr des Donnerstags (Montag + 3 Tage)
            thursday_dt = start_dt + timedelta(days=3)
            jahr = thursday_dt.isocalendar()[0]
            start_date = start_dt.strftime("%Y-%m-%d")
            end_date = datetime(int(y2), int(m2), int(d2)).strftime("%Y-%m-%d")
            if not kw_match:
                kw = thursday_dt.isocalendar()[1]
        except ValueError:
            jahr = int(y1)
            start_date = f"{jahr:04d}-{int(m1):02d}-{int(d1):02d}"
            end_date = f"{int(y2):04d}-{int(m2):02d}-{int(d2):02d}"
    else:
        now = datetime.now()
        jahr = now.isocalendar()[0]
        start_date = now.strftime("%Y-%m-%d")
        end_date = (now + timedelta(days=4)).strftime("%Y-%m-%d")

    return kw, jahr, start_date, end_date


def is_allergen_line(line: str) -> bool:
    """Prüft, ob eine Zeile ausschließlich aus Allergen-Kennzeichnungen (z. B. '1,4,7' oder 'K,A') besteht."""
    if re.search(r"k(?:c|e|ec)?al", line, re.I):
        return False
    clean_line = re.sub(r"^[\s\.\*\+\-\|©®»«“”\"\'„‘]+|[\s\.\*\+\-\|©®»«“”\"\'„‘]+$", "", line).strip()
    if not clean_line or len(clean_line) > 35:
        return False

    tokens = [t.strip(" .,-/*") for t in re.split(r"[,/|\s\.]+", clean_line) if t.strip(" .,-/*")]
    if not tokens:
        return False

    for t in tokens:
        if t.isdigit() and len(t) <= 6:
            continue
        if len(t) >= 3 and not t.isupper():
            return False
        if not re.match(r"^(?:[0-9]{1,4}|[A-Z]{1,2})$", t):
            return False

    return True


def clean_dish_title(text: str) -> str:
    """Entfernt nachlaufende Allergen-Codes, Fußnoten (z. B. 147, 4,.11,13) und OCR-Reste am Titelende."""
    s = text.strip()
    s = re.sub(r"(\w+)-\s+(\w+)", r"\1 \2", s)
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"[\s,\.\-]+[©®»«“”\"\'„‘\*\#\+]+$", "", s).strip()
        s = re.sub(r"\s*\([a-z0-9\s,\.\/\*\+\-]+\)\s*$", "", s, flags=re.I).strip()
        s = re.sub(r"\s+[a-z0-9]{1,3}\s*\)\s*$", "", s, flags=re.I).strip()
        s = re.sub(
            r"[\s,]+(?:[0-9]{1,3}|[a-z]{1,2})(?:[\s,\.]+(?:[0-9]{1,3}|[a-z]{1,2}))+[\s©®»«“”\"\'„‘\.\,]*$",
            "",
            s,
            flags=re.I,
        ).strip()
        s = re.sub(r"(?:,\s*[0-9]{1,4}|\s+[0-9]{1,4})\s*$", "", s).strip()
        s = re.sub(r"(?:,\s*[a-zA-Z]|\s+[a-zA-Z])\s*$", "", s).strip()
        s = re.sub(r"[\s,\.\-\|\/]+$", "", s).strip()
    return s


def clean_cell_text(raw_text: str) -> Tuple[str, str, str]:
    """Trennt den rohen Zellentext in `(Gerichtsname, Kalorien, Allergene)`."""
    norm = normalize_ocr_text(raw_text)
    lines = [l.strip() for l in norm.split("\n") if l.strip()]
    dish_lines, calories = [], ""
    allergen_parts = []

    for line in lines:
        cal_match = re.search(r"(\d+\s*k(?:c|e|ec)?al(?:\*+)?)", line, re.I)
        if cal_match:
            calories = cal_match.group(1).strip()
            prefix = line[:cal_match.start()].strip()
            if prefix and not is_allergen_line(prefix):
                cleaned_pre = re.sub(r"[\s\|]+(?:u\s*)?[©®»«“”\"]+\s*$", "", prefix).strip()
                cleaned_pre = re.sub(r"[\s\|]+\bca\.?\s*$", "", cleaned_pre, flags=re.I).strip()
                cleaned_pre = re.sub(r"^[\s\/\|\*]+\s*", "", cleaned_pre).strip()
                if cleaned_pre.lower() not in ["ca", "ca.", "ca.*"] and cleaned_pre:
                    dish_lines.append(cleaned_pre)
        elif is_allergen_line(line):
            clean_alg = re.sub(r"^[\s\.\*\+\-\|©®»«“”\"\'„‘]+|[\s\.\*\+\-\|©®»«“”\"\'„‘]+$", "", line).strip()
            if clean_alg:
                allergen_parts.append(clean_alg)
        elif line.lower() in ["vegan", "vegetarisch"] or re.match(r"^[\s\.\,\'\"\‘\’\“\”\©\®\»\«\-\|\/uX]+$", line):
            continue
        else:
            cleaned_line = re.sub(r"[\s\|]+(?:u\s*)?[©®»«“”\"]+\s*$", "", line).strip()
            cleaned_line = re.sub(r"[\s\|]+\bca\.?\s*$", "", cleaned_line, flags=re.I).strip()
            cleaned_line = re.sub(r"^[\s\/\|\*]+\s*", "", cleaned_line).strip()
            if cleaned_line.lower() in ["ca", "ca.", "ca.*"]:
                continue
            if cleaned_line:
                dish_lines.append(cleaned_line)

    # Zeilen zu natürlichem Fließtext verbinden (Bindestriche vor Großbuchstaben z. B. "Puten-Schlemmer-Schnitzel" erhalten)
    cleaned_lines = []
    for dl in dish_lines:
        dl = dl.replace("|", " ").strip()
        if dl:
            cleaned_lines.append(dl)

    if cleaned_lines:
        res = []
        for cl in cleaned_lines:
            if res and res[-1].endswith("-"):
                if cl and cl[0].isupper():
                    res[-1] = res[-1] + cl
                else:
                    res[-1] = res[-1].rstrip("-").strip() + " " + cl
            else:
                res.append(cl)
        dish = " ".join(res)
    else:
        dish = lines[0] if lines else ""

    dish = dish.replace("|", " ")
    dish = clean_dish_title(dish)
    dish = re.sub(r"\s+", " ", dish).strip()
    calories = re.sub(r"[\s©®]+$", "", calories).strip()
    allergens = ", ".join(allergen_parts) if allergen_parts else ""
    return dish, calories, allergens


def parse_category_cell(raw_text: str, row_idx: int = 1) -> Tuple[str, str, str]:
    """Erkennt Kategorie (Spalte 0) und Standardpreise für Mitarbeiter und Gäste."""
    standard_categories = [
        ("Suppe", "2,80 €", "4,60 €"),
        ("Leibspeise 1", "4,60 €", "7,90 €"),
        ("Leibspeise 2", "4,60 €", "7,90 €"),
        ("Leibspeise 3", "4,60 €", "7,90 €"),
        ("Salatbar", "4,60 €", "3,00 € / 5,80 €"),
    ]
    default_cat, default_ma, default_gaeste = standard_categories[min(max(row_idx - 1, 0), 4)]

    clean = raw_text.lower()
    if "suppe" in clean:
        return "Suppe", "2,80 €", "4,60 €"
    elif "leibspeise 1" in clean:
        return "Leibspeise 1", "4,60 €", "7,90 €"
    elif "leibspeise 2" in clean:
        return "Leibspeise 2", "4,60 €", "7,90 €"
    elif "leibspeise 3" in clean:
        return "Leibspeise 3", "4,60 €", "7,90 €"
    elif "salat" in clean:
        return "Salatbar", "4,60 €", "3,00 € / 5,80 €"

    return default_cat, default_ma, default_gaeste
