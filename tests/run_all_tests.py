#!/usr/bin/env python3
"""
Zentraler Test-Runner für alle Test-Suiten des Speiseplan-Projekts.
Führt alle Unit-, Modul- und CLI-Integrationstests aus und gibt einen detaillierten Bericht aus.
"""

import unittest
import sys
import os
import time

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TESTS_DIR)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
RESET = "\033[0m"


def main():
    print(f"\n{BOLD}{CYAN}══════════════════════════════════════════════════════════════════{RESET}")
    print(f" {BOLD}Speiseplan Test-Suite Runner (Python unittest){RESET}")
    print(f"{BOLD}{CYAN}══════════════════════════════════════════════════════════════════{RESET}\n")

    if TESTS_DIR not in sys.path:
        sys.path.insert(0, TESTS_DIR)

    test_modules = [
        f[:-3] for f in sorted(os.listdir(TESTS_DIR))
        if f.startswith("test_") and f.endswith(".py") and f != "test_live_suite.py"
    ]
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(test_modules)

    start_time = time.time()
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    elapsed = time.time() - start_time

    print(f"\n{BOLD}══════════════════════════════════════════════════════════════════{RESET}")
    print(f" {BOLD}Zusammenfassung der Tests:{RESET}")
    print(f"  • Ausgeführte Tests:   {BOLD}{result.testsRun}{RESET}")
    print(f"  • Dauer:               {BOLD}{elapsed:.2f} Sekunden{RESET}")
    print(f"  • Erfolgreich:         {GREEN}{result.testsRun - len(result.failures) - len(result.errors)}{RESET}")
    print(f"  • Fehlgeschlagen:      {RED}{len(result.failures)}{RESET}")
    print(f"  • Fehler:              {RED}{len(result.errors)}{RESET}")
    print(f"  • Übersprungen:        {YELLOW}{len(result.skipped)}{RESET}")
    print(f"{BOLD}══════════════════════════════════════════════════════════════════{RESET}\n")

    if result.wasSuccessful():
        print(f"{GREEN}{BOLD}✓ Alle Tests erfolgreich bestanden!{RESET}\n")
        sys.exit(0)
    else:
        print(f"{RED}{BOLD}✗ Einige Tests sind fehlgeschlagen.{RESET}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
