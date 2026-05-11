#!/usr/bin/env python3
import os
import json
import argparse
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from selenium.webdriver.common.by import By
from scraper_utils import (
    get_driver, go_to_indicatori, get_links, parse_href, log,
    get_form_by_locatie, safe_select_in_form, get_options_in_form,
    wait_download, download_from_form, sanitize_token, clean_download_dir
)
import shutil

def process_single_month(task):
    """Process one month in a separate process."""
    year, month_code, month_data, manifest_path, base_download_dir, headless = task
    month_label = month_data.get("month_label", month_code)
    url = month_data["url"]

    download_dir = os.path.join(base_download_dir, year, month_code)
    os.makedirs(download_dir, exist_ok=True)

    log(f"Processing {year}-{month_code} ({month_label}) in {download_dir}")

    driver, wait, _ = get_driver(download_dir, headless=headless)
    success = False

    try:
        driver.get(url)
        time.sleep(1.5)
        wait.until(lambda d: d.find_element(By.TAG_NAME, "body"))

        # Reuse the full form processing logic from the original scraper (which includes the latest Spital fix)
        import drg_scraper2
        drg_scraper2.driver = driver
        drg_scraper2.wait = wait
        drg_scraper2.DOWNLOAD_DIR = download_dir
        drg_scraper2.process_all_forms(year, month_code)

        success = True
        log(f"SUCCESS: {year}-{month_code}")

    except Exception as e:
        log(f"FAILED {year}-{month_code}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()

    # Update manifest (resumability)
    try:
        with open(manifest_path, 'r+', encoding='utf-8') as f:
            manifest = json.load(f)
            key = month_code
            if year in manifest.get("years", {}) and key in manifest["years"][year]:
                manifest["years"][year][key]["status"] = success
                manifest["years"][year][key]["processed_at"] = datetime.now().isoformat()
                if success:
                    manifest["years"][year][key]["forms_processed"] = ["all"]
            f.seek(0)
            json.dump(manifest, f, indent=2, ensure_ascii=False)
            f.truncate()
    except Exception as e:
        log(f"Could not update manifest for {year}-{month_code}: {e}")

    return year, month_code, success


def process_manifest(manifest_path="manifest.json", workers=1, base_download_dir="downloads", headless=True):
    if not os.path.exists(manifest_path):
        log(f"Manifest {manifest_path} not found. Run generate_manifest.py first.")
        return

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    tasks = []
    for year, months in manifest.get("years", {}).items():
        for month_code, data in months.items():
            if not data.get("status", False):
                tasks.append((year, month_code, data, manifest_path, base_download_dir, headless))

    if not tasks:
        log("All months already processed according to manifest.")
        return

    log(f"Found {len(tasks)} unprocessed months. Processing with {workers} workers...")

    with ProcessPoolExecutor(max_workers=workers) as executor:
        future_to_task = {executor.submit(process_single_month, task): task for task in tasks}
        for future in as_completed(future_to_task):
            year, month_code, success = future.result()
            status = "SUCCESS" if success else "FAILED"
            log(f"{status}: {year}-{month_code}")

    log("Processing complete. Run again to resume any remaining months.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process DRG manifest in parallel")
    parser.add_argument("--manifest", default="manifest.json", help="Path to manifest JSON")
    parser.add_argument("--workers", type=int, default=1, help="Number of parallel workers (default 1)")
    parser.add_argument("--download-dir", default="downloads", help="Base download directory")
    parser.add_argument("--headless", action="store_true", default=True, help="Run in headless mode (default: True). Use --no-headless to see the browser.")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Disable headless mode to see the browser")
    args = parser.parse_args()

    process_manifest(
        manifest_path=args.manifest,
        workers=args.workers,
        base_download_dir=args.download_dir,
        headless=args.headless
    )
