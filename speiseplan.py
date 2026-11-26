#!/usr/bin/env python3
"""
================================================================================
Speiseplan CLI — HessenTreff im HMdI (Kaiberg Kitchen)
================================================================================

WEGWEISER DURCH DEN CODE (auch für Einsteiger & Nachbauten, z. B. in Java):
Die eigentliche Logik liegt sauber aufgeteilt im Ordner `speiseplan_core/`:

  1. Web-Scraper       -> speiseplan_core/scraper.py
     Sucht auf https://kaiberg-kitchen.de/ den Bereich "HessenTreff" und lädt
     bevorzugt die Wochenkarte als PDF (oder als Vorschaubild / über /hessentreff-im-hmdi/).
     Einstieg: `get_menu_source_url()`, `fetch_latest_menu_source()`

  2. PDF- & OCR-Parser -> speiseplan_core/parser.py
     Liest PDFs direkt aus (`pdftohtml -xml` + `pdftoppm` für das Tabellenraster und
     Vegetarisch/Vegan-Siegel in Spalte 0). Filtert verdeckte Altschichten in
     Korrektur-PDFs heraus. Bei reinen Scan-PDFs/Screenshots greift automatisch
     der Tesseract-OCR-Fallback (`parse_menu_image()`).
     Einstieg: `parse_menu_file()`

  3. Textbereinigung   -> speiseplan_core/text_cleaning.py
     Trennt Gerichtsnamen, Kalorien und Allergene (`clean_cell_text()`), korrigiert
     typische OCR-Fehler und kürzt Nebenzutaten für Statistiken (`get_canonical_dish()`).

  4. Datenmodelle      -> speiseplan_core/models.py
     `Dish`, `DayMenu`, `WeekMenu` (entspricht 1:1 den Spalten der CSV-Dateien).

  5. CSV-Speicher      -> speiseplan_core/storage.py
     Speichert `data/kwXX_YYYY.csv` und das deduplizierte Archiv `data/archive.csv`.

  6. Extras & Regeln   -> speiseplan_core/watchlist.py, analytics.py, ratings.py
     Lieblingsgerichte-Alarm, Fleischarten-Statistiken und Bewertungsregeln
     (Bewertung strikt pro Datum + Gericht, Zeitfenster 11:30 bis übermorgen 11:29).

  7. Terminal-Befehle  -> speiseplan_core/cli.py
     Verarbeitet `./speiseplan.py heute`, `woche`, `search`, `stats`, `watch`, `alert`.

Ausführliche Erklärungen, Ablaufdiagramm & Besonderheiten für Nachbauer: siehe README.md.
Diese Datei dient als ausführbarer Einstiegspunkt und exportiert alle Symbole
abwärtskompatibel für `sync_daily.py` und die Tests in `tests/`.
"""

from speiseplan_core import (  # noqa: F401
    ARCHIVE_CSV,
    BG_YELLOW,
    BOLD,
    CSV_COLUMNS,
    CYAN,
    DANGLING_PREPS,
    DATA_DIR,
    DEC_PATTERN,
    DECORATIVE_WORDS,
    DEFAULT_CANTEEN,
    DEFAULT_URL,
    DIM,
    DOC_DESCRIPTION,
    GREEN,
    HELP_EPILOG,
    IMAGES_DIR,
    OCR_REPLACEMENTS,
    RATINGS_FILE,
    RED,
    RESET,
    SAUCE_KEYWORDS,
    SCRIPT_DIR,
    SIDE_KEYWORDS,
    SIDE_SAUCE_PATTERN,
    WATCHLIST_FILE,
    WEEKDAYS_DE,
    WHITE,
    YELLOW,
    CanteenAnalytics,
    DayMenu,
    Dish,
    RatingManager,
    WatchlistManager,
    WeekMenu,
    _extract_menu_candidates_from_soup,
    _extract_visible_pdf_nodes,
    _is_menu_image,
    _join_cell_nodes,
    _pick_img_url,
    clean_cell_text,
    clean_dish_title,
    cmd_alert_silent,
    cmd_install_help,
    cmd_search,
    cmd_show,
    cmd_stats,
    cmd_watch,
    detect_diet_badge,
    detect_grid,
    download_menu_file,
    download_menu_image,
    ensure_data_dirs,
    ensure_week_menu,
    fetch_latest_menu_image,
    fetch_latest_menu_source,
    find_latest_local_week,
    find_poppler_tool,
    find_tesseract_binary,
    fix_dangling_components,
    generate_demo_archive,
    get_canonical_dish,
    get_menu_image_url,
    get_menu_source_url,
    get_tesseract_ocr_args,
    get_week_csv_path,
    load_archive_dishes,
    load_week_csv,
    main,
    normalize_ocr_text,
    parse_category_cell,
    parse_header_info,
    parse_header_info_from_text,
    parse_menu_file,
    parse_menu_image,
    parse_menu_pdf,
    print_banner_alerts,
    print_day_menu,
    print_footer_hint,
    print_missing_tesseract_help,
    render_ascii_bar,
    run_tesseract,
    save_week_csv,
    search_archive,
    split_components,
    update_archive_csv,
)

if __name__ == "__main__":
    main()
