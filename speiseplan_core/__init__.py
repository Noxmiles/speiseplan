"""
speiseplan_core — Modulares Kernpaket des HessenTreff-Speiseplan-Projekts.

Überblick über die Teilmodule (empfohlene Lesereihenfolge für Einsteiger):
1. `config.py`        – Pfade, URL, CSV-Spalten und Tool-Suche (Poppler / Tesseract).
2. `models.py`        – Datenstrukturen `Dish`, `DayMenu`, `WeekMenu`.
3. `scraper.py`       – Findet PDF-Wochenkarte bzw. Vorschaubild auf `kaiberg-kitchen.de`.
4. `parser.py`        – Liest PDF-Dateien direkt aus (`pdftohtml`/`pdftoppm`) mit OCR-Fallback.
5. `text_cleaning.py` – Bereinigt Gerichtsnamen, Kalorien, Allergen-Ziffern und OCR-Umlaute.
6. `storage.py`       – Speichert und durchsucht `kwXX_YYYY.csv` und `archive.csv`.
7. `watchlist.py`     – Verwaltet Lieblingsgerichte in `watchlist.json`.
8. `analytics.py`     – Fleischarten-, Wochentags-, Soßen- und Klassiker-Statistiken.
9. `ratings.py`       – Bewertungsregeln (pro Datum + Gericht, Zeitfenster, 8-Sekunden-Undo).
10. `cli.py`          – Terminal-Befehle (`heute`, `woche`, `search`, `stats`, `watch`, `alert`).
"""

from .analytics import (
    CanteenAnalytics,
    SAUCE_KEYWORDS,
    SIDE_KEYWORDS,
    generate_demo_archive,
    render_ascii_bar,
    split_components,
)
from .cli import (
    DOC_DESCRIPTION,
    HELP_EPILOG,
    cmd_alert_silent,
    cmd_search,
    cmd_show,
    cmd_stats,
    cmd_watch,
    ensure_week_menu,
    main,
    print_banner_alerts,
    print_day_menu,
    print_footer_hint,
)
from .config import (
    ARCHIVE_CSV,
    BG_YELLOW,
    BOLD,
    CSV_COLUMNS,
    CYAN,
    DATA_DIR,
    DEFAULT_CANTEEN,
    DEFAULT_URL,
    DIM,
    GREEN,
    IMAGES_DIR,
    RATINGS_FILE,
    RED,
    RESET,
    SCRIPT_DIR,
    WATCHLIST_FILE,
    WEEKDAYS_DE,
    WHITE,
    YELLOW,
    cmd_install_help,
    ensure_data_dirs,
    find_poppler_tool,
    find_tesseract_binary,
    get_tesseract_ocr_args,
    print_missing_tesseract_help,
)
from .models import DayMenu, Dish, WeekMenu
from .parser import (
    _extract_visible_pdf_nodes,
    _join_cell_nodes,
    detect_diet_badge,
    detect_grid,
    parse_header_info,
    parse_menu_file,
    parse_menu_image,
    parse_menu_pdf,
    run_tesseract,
)
from .ratings import RatingManager
from .scraper import (
    _extract_menu_candidates_from_soup,
    _is_menu_image,
    _pick_img_url,
    download_menu_file,
    download_menu_image,
    fetch_latest_menu_image,
    fetch_latest_menu_source,
    get_menu_image_url,
    get_menu_source_url,
)
from .storage import (
    find_latest_local_week,
    get_week_csv_path,
    load_archive_dishes,
    load_week_csv,
    save_week_csv,
    search_archive,
    update_archive_csv,
)
from .text_cleaning import (
    DANGLING_PREPS,
    DEC_PATTERN,
    DECORATIVE_WORDS,
    OCR_REPLACEMENTS,
    SIDE_SAUCE_PATTERN,
    clean_cell_text,
    clean_dish_title,
    fix_dangling_components,
    get_canonical_dish,
    is_allergen_line,
    normalize_ocr_text,
    parse_category_cell,
    parse_header_info_from_text,
)
from .watchlist import WatchlistManager
