# DRG Data Scraper

This project scrapes downloadable DRG indicator files from [drg.ro](https://www.drg.ro/index.php) using Selenium and Chrome.

The workflow has two steps:

1. Build a **manifest** (what periods exist and where to open them)
2. Process that manifest in parallel (download files for each period)

## Scripts Overview

### `generate_manifest.py`

Scans the DRG indicators page and creates a `manifest.json` file with:

- years discovered on the website
- period codes for each year (months, trimesters, full year, and some special periods)
- direct URL for each period
- processing status flags (`status`, `processed_at`, `forms_processed`)

This script does **not** download the data files. It prepares the plan for the downloader.

### `process_manifest.py`

Reads `manifest.json`, finds periods where `status` is `false`, and processes them.

For each period, it:

- opens the period URL
- runs the full form processing logic from `drg_scraper2.py`
- saves downloaded files under a structured folder
- updates `manifest.json` so progress is resumable

By default, downloads are saved to:

`downloads/<year>/<period_code>/`

## Prerequisites

- Python 3
- Google Chrome installed
- Matching ChromeDriver available to Selenium
- Python dependencies (at least `selenium`)

If you use a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## How To Use

### 1) Generate the manifest

Generate for a specific year range (example: only 2024):

```bash
python generate_manifest.py --start-year 2024 --end-year 2024
```

Or generate the latest N years (default is 5):

```bash
python generate_manifest.py --years 5
```

Useful options:

- `--output <file>`: output path (default `manifest.json`)
- `--headless` / `--no-headless`: run with or without visible browser

### 2) Process/download from the manifest

Run with 4 parallel workers in headless mode:

```bash
python process_manifest.py --workers 4 --headless
```

Useful options:

- `--manifest <file>`: manifest path (default `manifest.json`)
- `--workers <n>`: number of parallel processes
- `--download-dir <dir>`: base output folder (default `downloads`)
- `--headless` / `--no-headless`: run with or without visible browser

## Resume Behavior

`process_manifest.py` updates `manifest.json` after each period.  
If a run fails or is interrupted, re-run the same command and it continues with unprocessed periods.

## Typical End-to-End Example

```bash
# Step 1: build manifest for 2024 only
python generate_manifest.py --start-year 2024 --end-year 2024

# Step 2: process and download using 4 workers
python process_manifest.py --workers 4 --headless
```

## Notes

- The scraper depends on website structure; if the DRG page changes, selectors may need updates.
- Running with `--no-headless` is useful for debugging.
