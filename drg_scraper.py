import os
import time
import shutil
import random
import traceback

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC


# -------------------------
# CONFIG
# -------------------------

BASE_URL = "https://www.drg.ro/index.php"
DOWNLOAD_DIR = os.path.abspath("downloads")

MAX_RETRIES = 3
DOWNLOAD_TIMEOUT = 60
SLOW_MODE = True


# -------------------------
# DRIVER
# -------------------------

options = webdriver.ChromeOptions()
options.add_experimental_option("prefs", {
    "download.default_directory": DOWNLOAD_DIR,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
})

options.add_argument("--start-maximized")
options.add_argument("--disable-blink-features=AutomationControlled")

driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 20)


# -------------------------
# UTIL
# -------------------------

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def human_sleep(a=1.0, b=2.5):
    if not SLOW_MODE:
        return
    t = random.uniform(a, b)
    log(f"sleep {t:.2f}s")
    time.sleep(t)


def safe_click(el):
    for i in range(3):
        try:
            driver.execute_script("arguments[0].scrollIntoView(true);", el)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", el)
            return True
        except Exception as e:
            log(f"click retry {i+1}: {e}")
            time.sleep(1)
    return False


# -------------------------
# NAVIGATION
# -------------------------

def go_to_indicatori():
    driver.get(BASE_URL)

    wait.until(EC.visibility_of_element_located((By.TAG_NAME, "body")))

    btn = wait.until(
        EC.visibility_of_element_located(
            (By.XPATH, "//a[contains(@href,'p=indicatori')]")
        )
    )

    safe_click(btn)

    wait.until(EC.visibility_of_element_located((By.TAG_NAME, "body")))
    human_sleep()


# -------------------------
# DOWNLOAD
# -------------------------

def wait_download(before):
    start = time.time()

    while True:
        files = set(os.listdir(DOWNLOAD_DIR))
        new = files - before
        done = [f for f in new if not f.endswith(".crdownload")]

        if done:
            return done[0]

        if time.time() - start > DOWNLOAD_TIMEOUT:
            return None

        time.sleep(1)


def rename_file(f, y, m, a, j):
    j = j or "ALL"
    j = j.replace(" ", "_")

    new = f"{y}_{m}_{a}_{j}.xls"

    shutil.move(
        os.path.join(DOWNLOAD_DIR, f),
        os.path.join(DOWNLOAD_DIR, new)
    )


def safe_download(y, m, a, j):
    for attempt in range(MAX_RETRIES):
        try:
            before = set(os.listdir(DOWNLOAD_DIR))

            human_sleep(1, 2)

            # ✅ scope to correct form
            form = wait.until(EC.presence_of_element_located((By.ID, "spital")))

            btn = form.find_element(By.XPATH, ".//input[@type='submit' and @id='Af2']")
            safe_click(btn)

            # ✅ switch to new tab
            time.sleep(1)
            if len(driver.window_handles) > 1:
                driver.switch_to.window(driver.window_handles[-1])

            file = wait_download(before)

            # ✅ close tab if opened
            if len(driver.window_handles) > 1:
                driver.close()
                driver.switch_to.window(driver.window_handles[0])

            if file:
                rename_file(file, y, m, a, j)
                return True

        except Exception as e:
            log(f"download error: {e}")
            traceback.print_exc()

        time.sleep(2)

    return False


# -------------------------
# FORM
# -------------------------

def safe_select(select_name, value, form_id="spital"):
    for i in range(3):
        try:
            form = wait.until(EC.presence_of_element_located((By.ID, form_id)))

            el = form.find_element(By.NAME, select_name)
            Select(el).select_by_visible_text(value)

            human_sleep(0.5, 1.2)
            return True
        except Exception as e:
            log(f"select retry {i+1}: {e}")
            time.sleep(1)
    return False


def get_select_values(select_name, form_id="spital"):
    try:
        form = wait.until(EC.presence_of_element_located((By.ID, form_id)))
        el = form.find_element(By.NAME, select_name)

        return [
            o.text.strip()
            for o in Select(el).options
            if o.text.strip() and "selecteaza" not in o.text.lower()
        ]
    except:
        return []


def process_form(year, month):
    safe_select("extensie_fisier", "EXCEL")

    agregari = ["CMD", "DRG"]
    judete = get_select_values("judet") or [""]

    for a in agregari:
        safe_select("agregare", a)

        for j in judete:
            if j:
                safe_select("judet", j)

            success = safe_download(year, month, a, j)

            if not success:
                log(f"FAILED: {year}-{month}-{a}-{j}")


# -------------------------
# MAIN
# -------------------------

def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    go_to_indicatori()

    years = driver.find_elements(By.XPATH, "//a[contains(@href,'indicatori&s=')]")
    log(f"Found {len(years)} years")

    for i in range(len(years)):
        try:
            years = driver.find_elements(By.XPATH, "//a[contains(@href,'indicatori&s=')]")
            year_el = years[i]

            year = year_el.text.strip()
            if not year.isdigit():
                continue

            log(f"\nYear: {year}")

            safe_click(year_el)

            wait.until(EC.visibility_of_element_located((By.TAG_NAME, "body")))
            human_sleep()

            months = driver.find_elements(By.XPATH, "//a[contains(@href,'indicatori&s=20')]")

            for j in range(len(months)):
                try:
                    months = driver.find_elements(By.XPATH, "//a[contains(@href,'indicatori&s=20')]")
                    month_el = months[j]

                    month = month_el.text.strip()
                    if not month:
                        continue

                    log(f" Month: {month}")

                    safe_click(month_el)

                    wait.until(EC.presence_of_element_located((By.ID, "spital")))
                    human_sleep()

                    process_form(year, month)

                    driver.back()
                    wait.until(EC.visibility_of_element_located((By.TAG_NAME, "body")))

                except Exception as e:
                    log(f"Month failed: {e}")
                    traceback.print_exc()

            go_to_indicatori()

        except Exception as e:
            log(f"Year failed: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    try:
        main()
    finally:
        driver.quit()
