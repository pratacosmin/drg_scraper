#!/usr/bin/env python3
import os
import json
import argparse
import time
from datetime import datetime
from scraper_utils import (
    get_driver, go_to_indicatori, get_links, parse_href,
    log, VALID_PERIODS as VALID, safe_click
)
from selenium.webdriver.common.by import By

def generate_manifest(years_limit=5, start_year=None, end_year=None, output="manifest.json", headless=True):
    driver, wait, _ = get_driver(headless=headless)
    try:
        go_to_indicatori(driver, wait)
        links = get_links(driver)
        years = [el.text.strip() for el in links if el.text.strip().isdigit() and len(el.text.strip()) == 4]
        years = sorted([int(y) for y in years], reverse=True)

        if start_year and end_year:
            years = [y for y in years if end_year <= y <= start_year]
        else:
            years = years[:years_limit]

        manifest = {"years": {}, "last_run": datetime.now().isoformat(), "config": {"years_limit": years_limit}}

        log(f"Generating manifest for years: {years}")

        for year in years:
            manifest["years"][str(year)] = {}
            log(f"\nScanning year {year}")

            year_links = [el for el in get_links(driver) if el.text.strip() == str(year)]
            if not year_links:
                log(f"  Year link not found for {year}")
                continue

            safe_click(driver, year_links[0])
            time.sleep(3)
            wait.until(lambda d: d.find_element(By.TAG_NAME, "body"))

            period_links = []
            for el in get_links(driver):
                y, code = parse_href(el)
                label = el.text.strip()
                if y == str(year) and label and code:
                    # Include months (01-12), trimesters (t1-t4), full year (an), and other special periods like IanNov
                    if (code.isdigit() or code.startswith('t') or code in ('an', '995', 'iannov')):
                        period_links.append((code, label, el.get_attribute("href")))
                        log(f"  Added period {label} ({code}) for year {year}")

            # Remove duplicate log (moved inside the loop above)
            for period_code, period_label, url in period_links:
                manifest["years"][str(year)][period_code] = {
                    "period_label": period_label,
                    "url": url,
                    "status": False,
                    "forms_processed": [],
                    "processed_at": None
                }

            # Go back to main indicators page for next year
            driver.back()
            time.sleep(2)
            wait.until(lambda d: d.find_element(By.TAG_NAME, "body"))

        with open(output, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        log(f"\nManifest successfully generated: {output}")
        log(f"Total years: {len(manifest['years'])}, Total months: {sum(len(m) for m in manifest['years'].values())}")

    finally:
        driver.quit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate manifest JSON for DRG scraper")
    parser.add_argument("--years", type=int, default=5, help="Number of most recent years to include (default: 5)")
    parser.add_argument("--start-year", type=int, help="Start year (inclusive)")
    parser.add_argument("--end-year", type=int, help="End year (inclusive)")
    parser.add_argument("--output", default="manifest.json", help="Output JSON file")
    parser.add_argument("--headless", action="store_true", default=True, help="Run in headless mode (default: True). Use --no-headless to see the browser.")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Disable headless mode to see the browser")
    args = parser.parse_args()

    generate_manifest(
        years_limit=args.years,
        start_year=args.start_year,
        end_year=args.end_year,
        output=args.output,
        headless=args.headless
    )
