# scrape_aep.py
import time, json, re
from datetime import datetime
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd

# ---------------------------------------------
# Config
# ---------------------------------------------
URL = "https://africa-energy-portal.org/database"
ENDPOINT_PATTERN = re.compile(r"get-database-data", re.I)
OUT_DIR = Path("scraped_json")
OUT_DIR.mkdir(exist_ok=True)
WAIT_SHORT = 3
WAIT_LONG = 25

XPATHS = {
    "year_dropdown": '//*[@id="block-newdatabaseblock"]/div[1]/div/div/div[1]/div/div[2]/div[1]/div/div[1]/div/a',
    "year_all_option": '//*[@id="block-newdatabaseblock"]/div[1]/div/div/div[1]/div/div[2]/div[1]/div/div[1]/div/div/div[1]/div/label/span',
    "country_dropdown": '//*[@id="block-newdatabaseblock"]/div[1]/div/div/div[1]/div/div[2]/div[1]/div/div[3]/div/a',
    "country_all_option": '//*[@id="block-newdatabaseblock"]/div[1]/div/div/div[1]/div/div[2]/div[1]/div/div[3]/div/div/div[1]/div/label/span',
    "sector_button_by_text": '//*[normalize-space()="{text}"]',
    "electricity_container": '//*[@id="electricity"]',
    "energy_container": '//*[@id="energy"]',
    "electricity_tab_by_text": '//*[@id="electricity"]//*[normalize-space()="{text}"]',
    "energy_tab_by_text": '//*[@id="energy"]//*[normalize-space()="{text}"]',
    "electricity_all_checkbox": '//*[@id="electricity"]/div/div[1]/div/div/label/span',
    "energy_all_checkbox": '//*[@id="energy"]/div/div[1]/div/div/label/span',
    "electricity_apply": '//*[@id="block-newdatabaseblock"]/div[1]/div/div/div[2]/div/div[1]/div/div[3]/div/a[1]',
    "energy_apply": '//*[@id="block-newdatabaseblock"]/div[1]/div/div/div[2]/div/div[1]/div/div[3]/div/a[1]',
}

SECTORS = {
    "Electricity": {
        "container_key": "electricity_container",
        "tab_xpath_tpl": "electricity_tab_by_text",
        "all_checkbox": "electricity_all_checkbox",
        "apply_xpath": "electricity_apply",
        "submenus": ["Access", "Supply", "Technical"],
    },
    "Energy": {
        "container_key": "energy_container",
        "tab_xpath_tpl": "energy_tab_by_text",
        "all_checkbox": "energy_all_checkbox",
        "apply_xpath": "energy_apply",
        "submenus": ["Access", "Efficiency"],
    },
}

def setup_brave_driver():
    brave_path = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
    chrome_options = Options()
    chrome_options.binary_location = brave_path
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    caps = DesiredCapabilities.CHROME.copy()
    caps["goog:loggingPrefs"] = {"performance": "ALL"}
    chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    driver_path = ChromeDriverManager(driver_version="141.0.7390.70").install()
    driver = webdriver.Chrome(service=Service(driver_path), options=chrome_options)
    driver.execute_cdp_cmd("Network.enable", {})
    driver.execute_cdp_cmd("Network.setCacheDisabled", {"cacheDisabled": True})
    driver.set_page_load_timeout(90)
    return driver

def wait_click(driver, xpath, timeout=WAIT_LONG):
    el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xpath)))
    try:
        el.click()
    except Exception:
        driver.execute_script("arguments[0].click();", el)
    return el

def visible(driver, xpath, timeout=WAIT_LONG):
    return WebDriverWait(driver, timeout).until(EC.visibility_of_element_located((By.XPATH, xpath)))

def safe_click_by_text(driver, template_key, text, timeout=WAIT_LONG):
    return wait_click(driver, XPATHS[template_key].format(text=text), timeout=timeout)

def select_all_in_select2(driver, dropdown_xpath, all_option_xpath):
    wait_click(driver, dropdown_xpath)
    visible(driver, all_option_xpath)
    time.sleep(0.2)
    wait_click(driver, all_option_xpath)
    time.sleep(0.3)

def drain_perf_logs(driver):
    try:
        driver.get_log("performance")
    except Exception:
        pass

def collect_matching_response_events(driver):
    matches = []
    for raw in driver.get_log("performance"):
        msg = json.loads(raw.get("message", "{}")).get("message", {})
        if msg.get("method") == "Network.responseReceived":
            resp = msg.get("params", {}).get("response", {})
            url = resp.get("url", "")
            if re.search(ENDPOINT_PATTERN, url):
                matches.append(msg.get("params", {}))
    return matches

def get_body_by_request_id(driver, request_id):
    try:
        body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
        return body.get("body", None)
    except Exception:
        return None

def click_apply_and_capture(driver, apply_xpath, sector_name, submenu_name, wait_after=2.8):
    drain_perf_logs(driver)
    wait_click(driver, apply_xpath)
    time.sleep(wait_after)
    events = collect_matching_response_events(driver)
    if not events:
        time.sleep(1.5)
        events = collect_matching_response_events(driver)
    if not events:
        print(f"[warn] No matching JSON for {sector_name} → {submenu_name}")
        return None
    req_id = events[-1].get("requestId")
    body = get_body_by_request_id(driver, req_id)
    if not body:
        print(f"[warn] No body for requestId={req_id}")
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        start, end = body.find("{"), body.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(body[start:end+1])
            except Exception:
                return None
        return None

def save_json_blob(json_data, sector, submenu):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fp = OUT_DIR / f"{sector}_{submenu}_{ts}.json"
    fp.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[saved] {fp}")
    return fp

def scrape_portal():
    driver = setup_brave_driver()
    try:
        print("Opening page…")
        driver.get(URL)
        time.sleep(2)
        print("Selecting Year=All")
        select_all_in_select2(driver, XPATHS["year_dropdown"], XPATHS["year_all_option"])
        print("Selecting Country=All")
        select_all_in_select2(driver, XPATHS["country_dropdown"], XPATHS["country_all_option"])
        for sector_name, cfg in SECTORS.items():
            print(f"Sector → {sector_name}")
            safe_click_by_text(driver, "sector_button_by_text", sector_name)
            visible(driver, XPATHS[cfg["container_key"]])
            for submenu in cfg["submenus"]:
                print(f"  Submenu → {submenu}")
                safe_click_by_text(driver, cfg["tab_xpath_tpl"], submenu)
                wait_click(driver, XPATHS[cfg["all_checkbox"]])
                data = click_apply_and_capture(driver, XPATHS[cfg["apply_xpath"]], sector_name, submenu)
                if data is not None:
                    save_json_blob(data, sector_name, submenu)
                else:
                    print(f"[warn] No JSON captured for {sector_name} → {submenu}")
                wait_click(driver, XPATHS[cfg["all_checkbox"]])
        print("Done scraping.")
    finally:
        driver.quit()

if __name__ == "__main__":
    scrape_portal()
