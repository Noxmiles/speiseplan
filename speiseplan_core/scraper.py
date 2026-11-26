"""
speiseplan_core/scraper.py — Web-Scraper für kaiberg-kitchen.de.

Aufgabe dieses Moduls:
Die Website von Kaiberg Kitchen listet mehrere Kantinen (Seven Gardens, HessenTreff, Dow).
Dieses Modul findet gezielt den Abschnitt für die gewünschte Kantine (`DEFAULT_CANTEEN`)
und lädt die aktuelle Wochenkarte herunter.

Suchstrategie (von robust nach Fallback):
1. Überschrift der Kantine finden (z. B. "HessenTreff im HMdI").
2. Im HTML-Fluss vorwärts bis zur nächsten Kantinen-Überschrift suchen nach:
   - einem `.pdf`-Link (`Wochenkarte (PDF)`), bevorzugt mit Kantinenname/Wochenkarte im Text;
   - einem Wochenkarten-Bild (`-pdf.jpg`, `alt`/`figcaption` mit "Wochenkarte", `Bildschirmfoto`).
3. Falls im direkten Fluss nichts steht, maximal 6 Eltern-Container prüfen (stoppt vor fremden Kantinen).
4. Falls auf der Startseite nur ein Link "Zum Standort" (`/hessentreff-im-hmdi/`) liegt,
   dieser Unterseite einmalig folgen und dort nach PDF/Bild suchen.
"""

import os
import re
import urllib.parse
import urllib.request
from typing import List, Optional, Tuple

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None

from .config import DEFAULT_CANTEEN, DEFAULT_URL, IMAGES_DIR, ensure_data_dirs


def _pick_img_url(img_tag, base_url: str) -> str:
    """Wählt die höchste Bildauflösung aus `srcset` oder nutzt alternativ `src`."""
    srcset = img_tag.get("srcset")
    if srcset:
        parts = [p.strip().split() for p in srcset.split(",") if p.strip()]
        best = max(
            parts,
            key=lambda x: int(re.sub(r"\D", "", x[1])) if len(x) > 1 and re.sub(r"\D", "", x[1]) else 0,
        )[0]
        return urllib.parse.urljoin(base_url, best)
    return urllib.parse.urljoin(base_url, img_tag.get("src", ""))


def _is_menu_image(img_tag) -> bool:
    """Prüft, ob ein `<img>`-Tag auf eine Wochenkarte bzw. einen Speiseplan verweist."""
    src = (img_tag.get("src") or "").lower()
    alt = (img_tag.get("alt") or "").lower()
    combined = f"{src} {alt}"
    if any(k in combined for k in ["bildschirmfoto", "wochenkarte", "speiseplan", "-pdf."]):
        return True
    fig = img_tag.find_parent("figure")
    if fig and "wochenkarte" in fig.get_text().lower():
        return True
    return False


def _extract_menu_candidates_from_soup(
    soup: "BeautifulSoup", page_url: str, canteen: str
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extrahiert `(pdf_url, img_url, standort_url)` für die gesuchte Kantine aus dem HTML-DOM."""
    canteen_low = canteen.lower()
    target_heading = None
    for heading in soup.find_all(["h1", "h2", "h3", "h4", "strong", "p"]):
        if canteen_low in heading.get_text().lower():
            target_heading = heading
            break

    if not target_heading:
        raise ValueError(f"Kantine '{canteen}' konnte auf {page_url} nicht gefunden werden.")

    # Verhindert, dass in die Karte einer Nachbarkantine weitergewandert wird
    all_canteens = ["sevengardens", "seven gardens", "hessentreff", "dow"]
    other_canteens = [c for c in all_canteens if c not in canteen_low and canteen_low not in c]
    canteen_token = canteen_low.split()[0]

    pdf_candidates: List[Tuple[int, str]] = []
    img_candidates: List[str] = []
    standort_url: Optional[str] = None

    curr = target_heading
    while curr:
        curr = curr.next_element
        if not curr:
            break
        tag_name = getattr(curr, "name", None)
        if tag_name in ["h1", "h2", "h3", "h4", "strong", "p"]:
            t = curr.get_text().lower()
            if any(oc in t for oc in other_canteens):
                break
        if tag_name == "a":
            href = (curr.get("href") or "").strip()
            link_text = curr.get_text(" ", strip=True).lower()
            if href and ".pdf" in href.lower():
                full_pdf = urllib.parse.urljoin(page_url, href)
                score = 0
                if "wochenkarte" in link_text or "speiseplan" in link_text:
                    score += 2
                if canteen_token in full_pdf.lower():
                    score += 2
                pdf_candidates.append((score, full_pdf))
            elif href and not standort_url and ("standort" in link_text or canteen_token in href.lower()):
                if not href.startswith("#") and ".pdf" not in href.lower():
                    standort_url = urllib.parse.urljoin(page_url, href)
        if tag_name == "img" and _is_menu_image(curr):
            img_candidates.append(_pick_img_url(curr, page_url))

    # Fallback auf übergeordnete Container der Kantine (stoppt vor Container anderer Kantinen)
    if not pdf_candidates or not img_candidates:
        node = target_heading
        for _ in range(6):
            if not node.parent:
                break
            node = node.parent
            node_text = node.get_text().lower()
            if any(oc in node_text for oc in other_canteens):
                break
            if not pdf_candidates:
                for a_tag in node.find_all("a", href=True):
                    if ".pdf" in a_tag["href"].lower():
                        pdf_candidates.append((1, urllib.parse.urljoin(page_url, a_tag["href"])))
            if not img_candidates:
                for fig in node.find_all("figure"):
                    if "wochenkarte" in fig.get_text().lower():
                        img = fig.find("img")
                        if img:
                            img_candidates.append(_pick_img_url(img, page_url))
                            break
                if not img_candidates:
                    for img in node.find_all("img"):
                        if _is_menu_image(img):
                            img_candidates.append(_pick_img_url(img, page_url))
                            break

    pdf_url = max(pdf_candidates, key=lambda x: x[0])[1] if pdf_candidates else None
    img_url = img_candidates[0] if img_candidates else None
    return pdf_url, img_url, standort_url


def get_menu_source_url(
    page_url: str = DEFAULT_URL,
    canteen: str = DEFAULT_CANTEEN,
    prefer_pdf: bool = True,
    _follow_standort: bool = True,
) -> str:
    """Findet auf `kaiberg-kitchen.de` die aktuelle Wochenkarte (PDF bevorzugt, mit Bild-Fallback)."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}

    if requests and BeautifulSoup:
        resp = requests.get(page_url, headers=headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")

        pdf_url, img_url, standort_url = _extract_menu_candidates_from_soup(soup, page_url, canteen)

        # Falls auf Übersichtsseite nichts gefunden, ggf. Standort-Unterseite prüfen
        if not pdf_url and not img_url and _follow_standort and standort_url and standort_url != page_url:
            return get_menu_source_url(
                page_url=standort_url,
                canteen=canteen,
                prefer_pdf=prefer_pdf,
                _follow_standort=False,
            )

        chosen = (pdf_url or img_url) if prefer_pdf else (img_url or pdf_url)
        if not chosen:
            raise ValueError(f"Wochenkarte für '{canteen}' nicht gefunden.")
        return chosen
    else:
        # Einfacher Regex-Fallback, falls requests/BeautifulSoup nicht installiert sind
        req = urllib.request.Request(page_url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        canteen_tok = re.escape(canteen.split()[0])
        if prefer_pdf:
            pdf_match = re.search(rf'href=["\'](https?://[^"\']*{canteen_tok}[^"\']*\.pdf)["\']', html, re.I)
            if not pdf_match:
                pdf_match = re.search(r'href=["\'](https?://[^"\']+\.pdf)["\']', html, re.I)
            if pdf_match:
                return pdf_match.group(1)
        match = re.search(r'src=["\'](https?://[^"\']*(?:Bildschirmfoto|wochenkarte|-pdf\.)[^"\']+)["\']', html, re.I)
        if match:
            return match.group(1)
        raise RuntimeError("Wochenkarten-URL konnte nicht ermittelt werden.")


def get_menu_image_url(page_url: str = DEFAULT_URL, canteen: str = DEFAULT_CANTEEN) -> str:
    """Findet gezielt die Bild-URL der Wochenkarte (abwärtskompatibler Wrapper)."""
    return get_menu_source_url(page_url=page_url, canteen=canteen, prefer_pdf=False)


def download_menu_file(file_url: str, output_path: str) -> str:
    """Lädt die Wochenkarte (PDF oder Bild) herunter und speichert sie lokal."""
    ensure_data_dirs()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
    req = urllib.request.Request(file_url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp, open(output_path, "wb") as f:
        f.write(resp.read())
    return output_path


def download_menu_image(image_url: str, output_path: str) -> str:
    """Lädt das Bild herunter und speichert es lokal (abwärtskompatibler Alias)."""
    return download_menu_file(image_url, output_path)


def fetch_latest_menu_source(
    output_dir: str = IMAGES_DIR,
    canteen: str = DEFAULT_CANTEEN,
    prefer_pdf: bool = True,
) -> str:
    """Holt die aktuelle Wochenkarte (PDF bevorzugt, sonst Bild) und speichert sie im Cache-Ordner."""
    url = get_menu_source_url(canteen=canteen, prefer_pdf=prefer_pdf)
    filename = os.path.basename(url.split("?")[0])
    target_path = os.path.join(output_dir, filename)
    return download_menu_file(url, target_path)


def fetch_latest_menu_image(output_dir: str = IMAGES_DIR, canteen: str = DEFAULT_CANTEEN) -> str:
    """Holt die aktuelle Wochenkarte als Bild und speichert sie im Cache-Ordner."""
    return fetch_latest_menu_source(output_dir=output_dir, canteen=canteen, prefer_pdf=False)
