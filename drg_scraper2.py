import os
import time
import shutil
import re
import traceback
import uuid

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC


# ---------------- CONFIG ----------------

BASE_URL = "https://www.drg.ro/index.php"
DOWNLOAD_DIR = os.path.abspath("downloads")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

VALID = {
    "Ian","Feb","Mar","Apr","Mai","Iun",
    "Iul","Aug","Sep","Oct","Noi","Dec",
    "T1","T2","T3","T4"
}

AGREGARI = ["CMD", "DRG"]

CONTAINER_XPATH = "/html/body/table/tbody/tr/td[1]/table/tbody/tr/td[2]/table/tbody/tr[2]/td/table/tbody/tr/td/table/tbody/tr/td"


# ---------------- DRIVER ----------------

options = webdriver.ChromeOptions()
options.add_experimental_option("prefs", {
    "download.default_directory": DOWNLOAD_DIR,
    "download.prompt_for_download": False,
    "profile.default_content_setting_values.automatic_downloads": 1,  # Allow multiple downloads
    "profile.default_content_settings.popups": 0,
    "safebrowsing.enabled": True,
})

# Run in headless mode by default
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 20)


# ---------------- UTIL ----------------

def log(x):
    print(x)


def clean_download_dir():
    """Remove all existing files/folders from download directory."""
    for entry in os.listdir(DOWNLOAD_DIR):
        path = os.path.join(DOWNLOAD_DIR, entry)
        if os.path.isfile(path) or os.path.islink(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)


def safe_click(el):
    """Click with retry to handle stale element errors."""
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


def continue_if_insecure_form_warning():
    """Bypass Chrome's 'Form is not secure' interstitial when DRG submits http forms."""
    try:
        if "Form is not secure" not in (driver.title or ""):
            return False
        btn = wait.until(EC.element_to_be_clickable((By.ID, "proceed-button")))
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(1.2)
        log("   Continued through Chrome insecure form warning")
        return True
    except Exception as e:
        log(f"   Could not bypass insecure form warning: {e}")
        return False


# ---------------- NAV ----------------

def go_to_indicatori():
    driver.get(BASE_URL)

    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    btn = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//a[contains(@href,'p=indicatori')]"))
    )
    safe_click(btn)


# ---------------- DOWNLOAD ----------------

def wait_download(before):
    """Short timeout (5 seconds) as requested. Will return faster on slow forms."""
    for _ in range(5):  # 5 seconds max
        files = set(os.listdir(DOWNLOAD_DIR))
        new = files - before
        done = [f for f in new if not f.endswith(".crdownload")]

        if done:
            return done[0]

        time.sleep(1)
    return None


def sanitize_token(value):
    return (value or "ALL").replace(" ", "_")


def click_submit(form, submit_ids):
    for submit_id in submit_ids:
        try:
            btn = form.find_element(By.ID, submit_id)
            safe_click(btn)
            return True
        except Exception:
            continue
    return False


def download_from_form(form, year, month, form_id, agregare, selector, submit_ids):
    before = set(os.listdir(DOWNLOAD_DIR))

    if not click_submit(form, submit_ids):
        log(f"  No submit button found for {form_id} ({submit_ids})")
        return

    file = wait_download(before)

    if file:
        selector_token = sanitize_token(selector)
        agregare_token = sanitize_token(agregare)
        random_suffix = uuid.uuid4().hex[:8]

        name = f"{year}_{month}_{form_id}_{agregare_token}_{selector_token}_{random_suffix}.xls"

        shutil.move(
            os.path.join(DOWNLOAD_DIR, file),
            os.path.join(DOWNLOAD_DIR, name)
        )

        log("OK " + name)
    else:
        log(f"  Download timeout for {form_id}")


# ---------------- FORM HELPERS ----------------

def get_forms():
    container = wait.until(
        EC.presence_of_element_located((By.XPATH, CONTAINER_XPATH))
    )

    forms = container.find_elements(By.TAG_NAME, "form")

    # keep only valid forms
    forms = [f for f in forms if f.get_attribute("id")]

    return forms


def get_form_by_locatie(locatie):
    """Use absolute XPath anchored to the exact container from drg_page_source.html.
    This is more stable than relying on form id attributes."""
    xpath = f"{CONTAINER_XPATH}//form[.//input[@name='locatie' and @value='{locatie}']]"
    return wait.until(
        EC.presence_of_element_located((By.XPATH, xpath))
    )


def safe_select_in_form(form, name, value):
    """Select by visible text in form field. Handles 'judet', 'cas', etc."""
    try:
        el = form.find_element(By.NAME, name)
        Select(el).select_by_visible_text(value)
        time.sleep(0.5)  # small delay after select
        continue_if_insecure_form_warning()
        return True
    except Exception as e:
        log(f"  Could not select {name}='{value}': {e}")
        return False


def get_options_in_form(form, name):
    """Get visible options from a select field (judet, cas, specialitate, etc)."""
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


def process_form_01_national(year, month):
    form = get_form_by_locatie("01_National")
    safe_select_in_form(form, "extensie_fisier", "EXCEL")
    for agregare in AGREGARI:
        safe_select_in_form(form, "agregare", agregare)
        download_from_form(form, year, month, "01_national", agregare, "ALL", ("Af",))


def process_form_02_pacient(year, month):
    form = get_form_by_locatie("02_Judet_pacient")
    safe_select_in_form(form, "extensie_fisier", "EXCEL")
    judete = get_options_in_form(form, "judet")
    for agregare in AGREGARI:
        safe_select_in_form(form, "agregare", agregare)
        for judet in judete:
            safe_select_in_form(form, "judet", judet)
            download_from_form(form, year, month, "02_pacient", agregare, judet, ("Af",))


def process_form_03_spital(year, month):
    form = get_form_by_locatie("03_Judet_Spital")
    safe_select_in_form(form, "extensie_fisier", "EXCEL")
    judete = get_options_in_form(form, "judet")
    for agregare in AGREGARI:
        safe_select_in_form(form, "agregare", agregare)
        for judet in judete:
            safe_select_in_form(form, "judet", judet)
            download_from_form(form, year, month, "03_spital", agregare, judet, ("Af2",))


def process_form_04_cas(year, month):
    form = get_form_by_locatie("04_CAS")
    safe_select_in_form(form, "extensie_fisier", "EXCEL")
    case_opts = get_options_in_form(form, "cas")
    for agregare in AGREGARI:
        safe_select_in_form(form, "agregare", agregare)
        for cas_name in case_opts:
            safe_select_in_form(form, "cas", cas_name)
            download_from_form(form, year, month, "04_cas", agregare, cas_name, ("Af2",))


def process_form_05_specialitate(year, month):
    """Specialitate form uses Af4 button and has many options.
    We increased wait_download timeout above to help with slow responses."""
    form = get_form_by_locatie("05_Specialitate")
    safe_select_in_form(form, "extensie_fisier", "EXCEL")
    specialitati = get_options_in_form(form, "specialitate")
    log(f"   Found {len(specialitati)} specialitati")
    for agregare in AGREGARI:
        safe_select_in_form(form, "agregare", agregare)
        for specialitate in specialitati:
            if safe_select_in_form(form, "specialitate", specialitate):
                download_from_form(form, year, month, "05_specialitate", agregare, specialitate, ("Af4",))
                time.sleep(1.5)  # extra breathing room after Af4 submit


def process_form_06_spital_dynamic(year, month):
    """Clean main-window only version as per latest request.
    Order: Select Judet → Select Spital → Set Type (using exact select XPath) → Click download.
    After each judet, click the 'Alege alt judet' link to reset the form."""
    log("   Processing dynamic Spital form (main window, click 'Alege alt judet' after each judet)")

    judete = []
    try:
        form = get_form_by_locatie("06_Spital")
        judete = get_options_in_form(form, "judet")
        log(f"   Found {len(judete)} judete")
    except Exception as e:
        log(f"   Could not read judete: {e}")
        return

    for agregare in AGREGARI:
        for judet in judete:
            try:
                form = get_form_by_locatie("06_Spital")
                safe_select_in_form(form, "judet", judet)
                time.sleep(2.5)

                form = get_form_by_locatie("06_Spital")
                unitati = get_options_in_form(form, "unitate") or []
                log(f"     Judet '{judet}': {len(unitati)} hospitals")

                for unitate in unitati:
                    try:
                        form = get_form_by_locatie("06_Spital")
                        safe_select_in_form(form, "unitate", unitate)

                        # Set type using exact XPath to the select[3]
                        xpath_select = "/html/body/table/tbody/tr/td[1]/table/tbody/tr/td[2]/table/tbody/tr[2]/td/table/tbody/tr/td/table/tbody/tr/td/form[6]/div/select[3]"
                        select_el = wait.until(EC.presence_of_element_located((By.XPATH, xpath_select)))
                        Select(select_el).select_by_visible_text("EXCEL")
                        time.sleep(0.8)

                        # Click the download button
                        xpath_btn = "/html/body/table/tbody/tr/td[1]/table/tbody/tr/td[2]/table/tbody/tr[2]/td/table/tbody/tr/td/table/tbody/tr/td/form[6]/div/input[4]"
                        btn = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_btn)))
                        driver.execute_script("arguments[0].click();", btn)
                        log(f"       Downloaded for {judet} - {unitate}")
                        time.sleep(3.5)
                    except Exception as e:
                        log(f"       Hospital '{unitate}' failed: {e}")
                        continue

                # After finishing all hospitals for this judet, click "Alege alt judet" link
                try:
                    xpath_link = "/html/body/table/tbody/tr/td[1]/table/tbody/tr/td[2]/table/tbody/tr[2]/td/table/tbody/tr/td/table/tbody/tr/td/form[6]/div/a"
                    link = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_link)))
                    driver.execute_script("arguments[0].click();", link)
                    time.sleep(3.0)
                    log(f"     Clicked 'Alege alt judet' after completing {judet}")
                except Exception as le:
                    log(f"     Could not click reset link after {judet}: {le}")
                    time.sleep(2.0)

            except Exception as e:
                log(f"     Judet '{judet}' failed: {e}")
                continue


def process_form_07_icm_national(year, month):
    form = get_form_by_locatie("07_ICM_spitale")
    safe_select_in_form(form, "extensie_fisier", "EXCEL")
    download_from_form(form, year, month, "07_icm_spitale", "NON", "ALL", ("Af",))


def process_form_08_icm_specialitati(year, month):
    form = get_form_by_locatie("08_ICM_specialitati")
    safe_select_in_form(form, "extensie_fisier", "EXCEL")
    download_from_form(form, year, month, "08_icm_specialitati", "NON", "ALL", ("Af",))


def process_form_09_internari_urgente(year, month):
    """Start from the last form as requested: Rapoarte privind internarile in urgenta"""
    log("   Starting from last form (internari_urgente)")
    form = get_form_by_locatie("09_internari_urgente")
    safe_select_in_form(form, "extensie_fisier", "EXCEL")
    download_from_form(form, year, month, "09_internari_urgente", "NON", "ALL", ("Af",))


def process_all_forms(year, month):
    """Process all 9 forms in DESCENDING order (starting from the last form:
    Rapoarte privind internarile in urgenta). Uses absolute XPaths from drg_page_source.html."""
    log("   Processing 9 custom forms in DESCENDING order (starting from last form)")

    tasks = [
        ("09_internari_urgente", process_form_09_internari_urgente),
        ("08_ICM_specialitati", process_form_08_icm_specialitati),
        ("07_ICM_spitale", process_form_07_icm_national),
        ("06_Spital", process_form_06_spital_dynamic),
        ("05_Specialitate", process_form_05_specialitate),
        ("04_CAS", process_form_04_cas),
        ("03_Judet_Spital", process_form_03_spital),
        ("02_Judet_pacient", process_form_02_pacient),
        ("01_National", process_form_01_national),
    ]

    for name, fn in tasks:
        try:
            log(f"   → Form {name}")
            fn(year, month)
        except Exception as e:
            log(f"   Form {name} failed: {e}")
            traceback.print_exc()
            time.sleep(1)


# ---------------- PARSE ----------------

def get_links():
    return driver.find_elements(By.XPATH, "//a[contains(@href,'indicatori&s=')]")


def parse_href(el):
    href = el.get_attribute("href")
    m = re.search(r"s=(\d{4})_(\d{2})", href)
    if not m:
        return None, None
    return m.group(1), m.group(2)


# ---------------- MAIN ----------------

def main():
    clean_download_dir()
    go_to_indicatori()

    links = get_links()
    years = [el.text.strip() for el in links if re.fullmatch(r"\d{4}", el.text.strip())]
    log(f"Years: {years}")

    for year in years:
        try:
            log(f"\nYEAR {year}")
            year_links = [el for el in get_links() if el.text.strip() == year]
            if not year_links:
                log(f"  Year link not found anymore: {year}")
                continue
            if not safe_click(year_links[0]):
                continue
            time.sleep(2)  # wait for page reload

            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

            links = get_links()
            months = []
            for el in links:
                y, m = parse_href(el)
                label = el.text.strip()
                if label and (not label.isdigit()) and (label in VALID) and y == year:
                    months.append((m, label))

            log(f"Months: {[label for _, label in months]}")

            for m_code, m_label in months:
                try:
                    log(f"  Month {m_label}")
                    month_links = []
                    for el in get_links():
                        y, m = parse_href(el)
                        label = el.text.strip()
                        if y == year and m == m_code and label == m_label:
                            month_links.append(el)
                    if not month_links:
                        log(f"  Month link missing: {m_label}")
                        continue
                    if not safe_click(month_links[0]):
                        continue
                    time.sleep(2)  # wait for month page to load

                    # Keep month-page readiness check permissive (old behavior was body-based).
                    # Some months/years may not render report forms immediately.
                    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

                    process_all_forms(year, m_code)

                    driver.back()
                    time.sleep(2)
                    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

                except Exception as e:
                    log(f"Month error: {e}")
                    traceback.print_exc()

            go_to_indicatori()

        except Exception as e:
            log(f"Year error: {e}")
            traceback.print_exc()

    driver.quit()


if __name__ == "__main__":
    main()
