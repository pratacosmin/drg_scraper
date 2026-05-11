import os
import time
import re
import traceback
import uuid
import shutil
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

BASE_URL = "https://www.drg.ro/index.php"
VALID_PERIODS = {
    "Ian","Feb","Mar","Apr","Mai","Iun",
    "Iul","Aug","Sep","Oct","Noi","Dec",
    "T1","T2","T3","T4",
    "An", "an"  # full year
}
AGREGARI = ["CMD", "DRG"]
CONTAINER_XPATH = "/html/body/table/tbody/tr/td[1]/table/tbody/tr/td[2]/table/tbody/tr[2]/td/table/tbody/tr/td/table/tbody/tr/td"

def get_driver(download_dir=None, headless=True):
    if download_dir is None:
        download_dir = os.path.abspath("downloads")
    os.makedirs(download_dir, exist_ok=True)

    options = webdriver.ChromeOptions()
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "profile.default_content_setting_values.automatic_downloads": 1,
        "profile.default_content_settings.popups": 0,
        "safebrowsing.enabled": True,
        "profile.default_content_setting_values.notifications": 2,
    }
    options.add_experimental_option("prefs", prefs)
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 30)

    # Force the download directory using Chrome DevTools Protocol (most reliable method)
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": download_dir
    })

    return driver, wait, download_dir

def log(x):
    print(x)

def safe_click(driver, el):
    try:
        driver.execute_script("arguments[0].click();", el)
        return True
    except Exception:
        try:
            el.click()
            return True
        except Exception as e:
            log(f"  Click failed: {e}")
            return False

def go_to_indicatori(driver, wait):
    driver.get(BASE_URL)
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    btn = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//a[contains(@href,'p=indicatori')]"))
    )
    safe_click(driver, btn)
    time.sleep(2)

def get_links(driver):
    return driver.find_elements(By.XPATH, "//a[contains(@href,'indicatori&s=')]")

def parse_href(el):
    """Parse year and period code from href. Supports months (01-12), trimesters (t1-t4), and full year (an)."""
    href = el.get_attribute("href")
    m = re.search(r"s=(\d{4})_([a-zA-Z0-9]+)", href)
    if not m:
        return None, None
    year = m.group(1)
    code = m.group(2).lower()
    return year, code

def get_form_by_locatie(driver, wait, locatie):
    xpath = f"{CONTAINER_XPATH}//form[.//input[@name='locatie' and @value='{locatie}']]"
    return wait.until(
        EC.presence_of_element_located((By.XPATH, xpath))
    )

def safe_select_in_form(form, name, value):
    try:
        el = form.find_element(By.NAME, name)
        Select(el).select_by_visible_text(value)
        time.sleep(0.5)
        return True
    except Exception as e:
        log(f"  Could not select {name}='{value}': {e}")
        return False

def get_options_in_form(form, name):
    try:
        el = form.find_element(By.NAME, name)
        select = Select(el)
        options = []
        for o in select.options:
            text = o.text.strip()
            if text and not text.lower().startswith("selecteaza"):
                options.append(text)
        return options
    except Exception as e:
        log(f"  Could not get options for {name}: {e}")
        return []

def wait_download(download_dir, before, timeout=8):
    """Reduced timeout (was 30, now 8s max) for faster processing as requested."""
    import os
    for _ in range(timeout):
        files = set(os.listdir(download_dir))
        new = files - before
        done = [f for f in new if not f.endswith(".crdownload")]
        if done:
            return done[0]
        time.sleep(1)
    return None

def sanitize_token(value):
    return (value or "ALL").replace(" ", "_").replace("/", "_")

def clean_download_dir(download_dir):
    """Remove all existing files/folders from download directory (per year/month)."""
    for entry in os.listdir(download_dir):
        path = os.path.join(download_dir, entry)
        if os.path.isfile(path) or os.path.islink(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)


def download_from_form(driver, wait, download_dir, form, year, month, form_id, agregare, selector, submit_ids=("Af4", "Af2", "Af")):
    before = set(os.listdir(download_dir))
    clicked = False
    for sid in submit_ids:
        try:
            btns = form.find_elements(By.ID, sid)
            if btns:
                safe_click(driver, btns[0])
                clicked = True
                break
        except:
            continue

    if not clicked:
        log(f"  No submit button found for {form_id}")
        return False

    file = wait_download(download_dir, before)
    if file:
        selector_token = sanitize_token(selector)
        agregare_token = sanitize_token(agregare)
        random_suffix = uuid.uuid4().hex[:8]
        name = f"{year}_{month}_{form_id}_{agregare_token}_{selector_token}_{random_suffix}.xls"
        shutil.move(
            os.path.join(download_dir, file),
            os.path.join(download_dir, name)
        )
        log("OK " + name)
        return True
    else:
        log(f"  Download timeout for {form_id}")
        return False
