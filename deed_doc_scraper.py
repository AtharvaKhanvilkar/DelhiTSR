"""
Deed Document Scan Scraper (deed_doc_scraper.py)
Automates authentication, deed document search, page scan extraction,
and PDF stitching from official Delhi government portal (scan.delhigovt.nic.in).

Architecture: Uses a SINGLE persistent Playwright browser context that stays
alive across the full flow: load CAPTCHA → submit login → autocomplete locality
→ select SRO → search deed documents.

Portal Form Structure (SearchForm.aspx):
  - txtSearch: text input with AjaxControlToolkit AutoComplete (calls GetLoc WebMethod)
  - ddl_Sro: SRO dropdown (populated by postback after locality selection in txtSearch)
  - txt_Regno: Registration number input
  - dd_regyear: Registration year dropdown (pre-populated)
  - ddl_book: Book number dropdown (pre-populated)
  - btnSearch: Search button
"""

import os
import re
import io
import time
import base64
import requests
from bs4 import BeautifulSoup
from PIL import Image
from playwright.sync_api import sync_playwright

BASE_URL = "https://scan.delhigovt.nic.in"
LOGIN_URL = f"{BASE_URL}/Login.aspx"
SEARCH_URL = f"{BASE_URL}/SearchForm.aspx"

# ASP.NET element IDs on SearchForm.aspx
ID_TXT_SEARCH = "#ctl00_ContentPlaceHolder1_GenerateTicket1_txtSearch"
ID_DDL_SRO = "#ctl00_ContentPlaceHolder1_GenerateTicket1_ddl_Sro"
ID_TXT_REGNO = "#ctl00_ContentPlaceHolder1_GenerateTicket1_txt_Regno"
ID_DDL_REGYEAR = "#ctl00_ContentPlaceHolder1_GenerateTicket1_dd_regyear"
ID_DDL_BOOK = "#ctl00_ContentPlaceHolder1_GenerateTicket1_ddl_book"
ID_BTN_SEARCH = "#ctl00_ContentPlaceHolder1_GenerateTicket1_btnSearch"
ID_AUTOCOMPLETE_LIST = "#ctl00_ContentPlaceHolder1_GenerateTicket1_AutoCompleteExtender2_completionListElem"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": BASE_URL,
    "Referer": SEARCH_URL
}

# ──────────────────────────────────────────────────────────────────────────────
# Module-level persistent Playwright state.
# All Playwright operations run on a SINGLE dedicated thread via _pw_executor
# to avoid thread-affinity issues with sync_playwright.
# ──────────────────────────────────────────────────────────────────────────────
from concurrent.futures import ThreadPoolExecutor

_pw_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="playwright")
_pw_instance = None
_pw_browser = None
_pw_context = None
_pw_page = None


def _ensure_browser():
    """Ensure a persistent Playwright browser + context + page exists.
    MUST only be called from the _pw_executor thread."""
    global _pw_instance, _pw_browser, _pw_context, _pw_page

    if _pw_instance is None:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        _pw_instance = pw
        _pw_browser = browser
        _pw_context = context
        _pw_page = page

    return _pw_page, _pw_context


def _teardown():
    """Tear down Playwright state. MUST only be called from the _pw_executor thread."""
    global _pw_instance, _pw_browser, _pw_context, _pw_page
    try:
        if _pw_browser:
            _pw_browser.close()
    except Exception:
        pass
    try:
        if _pw_instance:
            _pw_instance.stop()
    except Exception:
        pass
    _pw_instance = None
    _pw_browser = None
    _pw_context = None
    _pw_page = None


def _run_in_pw_thread(fn):
    """Submit a function to the dedicated Playwright thread and wait for result.
    This ensures ALL Playwright calls happen on the same single thread."""
    future = _pw_executor.submit(fn)
    return future.result(timeout=60)


def reset_browser():
    """Public: tear down and force a fresh browser on next call."""
    _run_in_pw_thread(_teardown)



class DorisDocScraper:
    def __init__(self, username=None, password=None, session_cookie=None):
        self.username = username or os.getenv("DORIS_SCAN_USER", "9892245178")
        self.password = password or os.getenv("DORIS_SCAN_PASS", "Atharva@2026")
        self.session_cookie = session_cookie or os.getenv("DORIS_SCAN_COOKIE", "")

    # ── Step 1: Load Login page & capture CAPTCHA ─────────────────────────
    def start_login_session(self):
        """Loads Login.aspx in a PERSISTENT Playwright browser and captures live CAPTCHA image.
        The browser stays open so submit_login_with_captcha() can use the SAME session."""
        try:
            def _do():
                _teardown()
                page, context = _ensure_browser()

                page.goto(LOGIN_URL, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_selector("#IMG4, img[src*='JpegImage']", timeout=10000)

                captcha_el = page.query_selector("#IMG4") or page.query_selector("img[src*='JpegImage']")
                if not captcha_el:
                    return {"ok": False, "error": "CAPTCHA element not found on Login.aspx"}

                png_bytes = captcha_el.screenshot()
                b64_str = f"data:image/png;base64,{base64.b64encode(png_bytes).decode('utf-8')}"

                return {"ok": True, "captcha_b64": b64_str}
            return _run_in_pw_thread(_do)
        except Exception as e:
            return {"ok": False, "error": f"Failed to load Login page via Playwright: {str(e)}"}

    # ── Step 2: Submit CAPTCHA + credentials on the SAME session ──────────
    def submit_login_with_captcha(self, username, password, captcha_code):
        """Fills login form on the SAME page/session that generated the CAPTCHA and submits."""
        user = username or self.username
        pwd = password or self.password
        try:
            def _do():
                page, context = _ensure_browser()

                current_url = page.url
                if "Login.aspx" not in current_url:
                    page.goto(LOGIN_URL, timeout=30000, wait_until="domcontentloaded")

                page.fill("#ctl00_ContentPlaceHolder1_txtuserid", user)
                page.fill("#ctl00_ContentPlaceHolder1_txtpwd", pwd)
                page.fill("#ctl00_ContentPlaceHolder1_txtcaptcha", str(captcha_code).strip())

                page.click("#ctl00_ContentPlaceHolder1_btnlogin")
                page.wait_for_timeout(3000)

                curr_url = page.url
                page_content = page.content()
                cookies = context.cookies()
                cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])

                login_success = (
                    "SearchForm.aspx" in curr_url or
                    "Logout" in page_content or
                    "Welcome" in page_content or
                    "SearchForm" in page_content
                )

                if login_success:
                    return {"ok": True, "cookie_str": cookie_str, "message": "Authenticated with scan.delhigovt.nic.in!"}
                else:
                    if "Invalid Captcha" in page_content or "captcha" in page_content.lower():
                        return {"ok": False, "error": "Invalid CAPTCHA code. Please try again."}
                    elif "Invalid User" in page_content or "invalid" in page_content.lower():
                        return {"ok": False, "error": "Invalid credentials. Please check username and password."}
                    else:
                        return {"ok": False, "error": f"Login failed. Page stayed at: {curr_url}"}
            result = _run_in_pw_thread(_do)
            if result.get("ok") and result.get("cookie_str"):
                self.session_cookie = result["cookie_str"]
            return result
        except Exception as e:
            return {"ok": False, "error": f"Login submission error: {str(e)}"}

    # ── Step 3: Get locality autocomplete suggestions ─────────────────────
    def get_locality_suggestions(self, query):
        """Types a locality query into the txtSearch AutoComplete field and
        returns the live autocomplete suggestions from the portal.
        
        The portal uses AjaxControlToolkit AutoCompleteBehavior with:
        - minimumPrefixLength: 2
        - serviceMethod: GetLoc
        - servicePath: /SearchForm.aspx
        """
        if not query or len(query) < 2:
            return {"ok": True, "suggestions": []}

        try:
            def _do():
                page, context = _ensure_browser()

                # Navigate to SearchForm if not already there
                if "SearchForm.aspx" not in page.url:
                    page.goto(SEARCH_URL, timeout=30000, wait_until="domcontentloaded")

                if "login.aspx" in page.url.lower():
                    return {"ok": False, "diagnostic_code": "PORTAL_SESSION_EXPIRED",
                            "error": "Session expired. Please log in again."}

                # Clear the search field and type the query
                search_input = page.locator(ID_TXT_SEARCH)
                search_input.fill("")  # clear first
                search_input.click()

                # Type character by character to trigger autocomplete
                for char in query:
                    search_input.press(char)
                    page.wait_for_timeout(50)

                # Wait for autocomplete suggestions to appear
                page.wait_for_timeout(1500)

                # Extract suggestions from the completion list
                completion_list = page.locator(ID_AUTOCOMPLETE_LIST)
                suggestions = []

                if completion_list.is_visible():
                    items = completion_list.locator("li")
                    count = items.count()
                    for i in range(count):
                        text = items.nth(i).inner_text().strip()
                        if text:
                            suggestions.append(text)

                return {"ok": True, "suggestions": suggestions}
            return _run_in_pw_thread(_do)
        except Exception as e:
            return {"ok": False, "error": f"Failed to get locality suggestions: {str(e)}"}

    # ── Step 4: Select locality and get SRO list ──────────────────────────
    def select_locality_and_get_sros(self, locality_name):
        """Selects a locality from the autocomplete list (by clicking it),
        waits for the ASP.NET postback, and extracts the populated SRO dropdown.
        
        Must call get_locality_suggestions() first to populate the autocomplete list.
        """
        try:
            def _do():
                page, context = _ensure_browser()

                if "login.aspx" in page.url.lower():
                    return {"ok": False, "diagnostic_code": "PORTAL_SESSION_EXPIRED",
                            "error": "Session expired. Please log in again."}

                # The autocomplete list should already be visible from get_locality_suggestions()
                completion_list = page.locator(ID_AUTOCOMPLETE_LIST)

                if completion_list.is_visible():
                    items = completion_list.locator("li")
                    count = items.count()

                    # Find and click the matching item
                    clicked = False
                    for i in range(count):
                        text = items.nth(i).inner_text().strip()
                        if text.lower() == locality_name.lower():
                            items.nth(i).click()
                            clicked = True
                            break

                    if not clicked and count > 0:
                        items.nth(0).click()
                        clicked = True

                    if not clicked:
                        return {"ok": False, "error": f"No autocomplete suggestion found for '{locality_name}'"}
                else:
                    # Try typing the locality and triggering autocomplete
                    search_input = page.locator(ID_TXT_SEARCH)
                    search_input.fill("")
                    search_input.click()
                    for char in locality_name:
                        search_input.press(char)
                        page.wait_for_timeout(50)
                    page.wait_for_timeout(1500)

                    completion_list = page.locator(ID_AUTOCOMPLETE_LIST)
                    if completion_list.is_visible():
                        items = completion_list.locator("li")
                        if items.count() > 0:
                            items.nth(0).click()
                        else:
                            return {"ok": False, "error": "No autocomplete suggestions appeared."}
                    else:
                        return {"ok": False, "error": "Autocomplete list not visible."}

                # Wait for the postback to populate the SRO dropdown
                page.wait_for_timeout(3000)

                # Extract SRO options
                sro_options = page.eval_on_selector_all(
                    f"{ID_DDL_SRO} option",
                    "opts => opts.map(o => ({id: o.value.trim(), name: o.innerText.trim()}))"
                )
                sro_list = [o for o in sro_options if o["id"] and o["id"] != "0" and "select" not in o["name"].lower()]

                return {"ok": True, "sro_list": sro_list}
            return _run_in_pw_thread(_do)
        except Exception as e:
            return {"ok": False, "error": f"Failed to select locality: {str(e)}"}

    # ── Step 5: Get registration years ────────────────────────────────────
    def get_reg_years(self):
        """Extracts the registration year dropdown options from SearchForm.aspx."""
        try:
            def _do():
                page, context = _ensure_browser()

                if "SearchForm.aspx" not in page.url:
                    page.goto(SEARCH_URL, timeout=30000, wait_until="domcontentloaded")

                if "login.aspx" in page.url.lower():
                    return {"ok": False, "error": "Session expired."}

                options = page.eval_on_selector_all(
                    f"{ID_DDL_REGYEAR} option",
                    "opts => opts.map(o => ({id: o.value.trim(), name: o.innerText.trim()}))"
                )
                years = [o for o in options if o["id"] and o["id"] != "0" and "select" not in o["name"].lower()]

                return {"ok": True, "reg_years": years}
            return _run_in_pw_thread(_do)
        except Exception as e:
            return {"ok": False, "error": f"Failed to get reg years: {str(e)}"}

    # ── Legacy compat: get_sro_list (now requires locality first) ─────────
    def get_sro_list(self):
        """Legacy method. SRO list requires a locality selection first.
        Returns empty list with guidance message."""
        return {
            "ok": True,
            "sro_list": [],
            "message": "SRO list requires typing a locality name first. Use get_locality_suggestions() then select_locality_and_get_sros()."
        }

    # ── Legacy compat: get_locality_list ──────────────────────────────────
    def get_locality_list(self, sro_val="0"):
        """Legacy method. The portal uses text autocomplete, not a dropdown.
        Redirect to get_locality_suggestions()."""
        return {
            "ok": True,
            "locality_list": [],
            "message": "Portal uses autocomplete, not a dropdown. Use get_locality_suggestions(query) instead."
        }

    # ── Deed Document Search & Extract ────────────────────────────────────
    def fetch_deed_document(self, locality, reg_no, reg_year, sro_name="", book_no="1"):
        """
        Submits search request on SearchForm.aspx and extracts scan images.
        Converts extracted scans into a stitched PDF.
        """
        try:
            # Ensure session is active
            res_form = self.session.get(SEARCH_URL, timeout=12)
            if res_form.status_code != 200:
                login_res = self.login()
                if not login_res["ok"]:
                    return login_res
                res_form = self.session.get(SEARCH_URL, timeout=12)

            soup = BeautifulSoup(res_form.text, 'html.parser')
            vs = soup.find('input', {'id': '__VIEWSTATE'})
            ev = soup.find('input', {'id': '__EVENTVALIDATION'})

            vs_val = vs['value'] if vs else ""
            ev_val = ev['value'] if ev else ""

            sro_val = "0"
            sro_select = soup.find('select', {'id': re.compile(r'ddlSRO|ddl_Sro', re.I)})
            if sro_select and sro_name:
                for opt in sro_select.find_all('option'):
                    if sro_name.lower() in opt.text.lower() or opt.text.lower() in sro_name.lower():
                        sro_val = opt.get('value', '0')
                        break

            payload = {
                "__VIEWSTATE": vs_val,
                "__EVENTVALIDATION": ev_val,
                "ctl00$ContentPlaceHolder1$GenerateTicket1$txtSearch": locality or "",
                "ctl00$ContentPlaceHolder1$GenerateTicket1$ddl_Sro": sro_val,
                "ctl00$ContentPlaceHolder1$GenerateTicket1$txt_Regno": str(reg_no),
                "ctl00$ContentPlaceHolder1$GenerateTicket1$dd_regyear": str(reg_year),
                "ctl00$ContentPlaceHolder1$GenerateTicket1$ddl_book": str(book_no),
                "ctl00$ContentPlaceHolder1$GenerateTicket1$btnSearch": "Search"
            }

            res_search = self.session.post(SEARCH_URL, data=payload, timeout=18)
            if res_search.status_code != 200:
                return {
                    "ok": False,
                    "diagnostic_code": "BACKEND_HTTP_ERROR",
                    "error": f"Portal returned HTTP {res_search.status_code}."
                }

            if "Logout" in res_search.url or "errorPage" in res_search.url or "Some Error occured" in res_search.text:
                return {
                    "ok": False,
                    "diagnostic_code": "PORTAL_SESSION_EXPIRED",
                    "error": "Government portal session expired or blocked automated login. Active session cookie required."
                }

            search_soup = BeautifulSoup(res_search.text, 'html.parser')
            img_tags = search_soup.find_all('img', {'src': re.compile(r'\.(jpg|jpeg|png|tiff|gif|aspx)', re.I)})
            
            image_urls = []
            for img in img_tags:
                src = img.get('src', '')
                if 'captcha' in src.lower() or 'logo' in src.lower() or 'banner' in src.lower():
                    continue
                if not src.startswith('http'):
                    src = f"{BASE_URL}/{src.lstrip('/')}"
                image_urls.append(src)

            if not image_urls:
                links = search_soup.find_all('a', {'href': re.compile(r'(View|Show|Doc|Page)', re.I)})
                for a in links:
                    href = a.get('href', '')
                    if not href.startswith('http'):
                        href = f"{BASE_URL}/{href.lstrip('/')}"
                    image_urls.append(href)

            if not image_urls:
                if "Check Deed Doc" not in res_search.text and "No Record" in res_search.text:
                    return {
                        "ok": False,
                        "diagnostic_code": "NO_RECORDS_ON_GOVT_SITE",
                        "error": f"Government database has 0 scanned deed records for Reg No. {reg_no} ({reg_year})."
                    }
                else:
                    return {
                        "ok": False,
                        "diagnostic_code": "NO_SCANNED_PAGES_FOUND",
                        "error": f"Government portal returned 0 scanned pages for Reg No. {reg_no} in {reg_year}."
                    }

            return {
                "ok": True,
                "diagnostic_code": "SUCCESS",
                "image_urls": image_urls,
                "total_pages": len(image_urls),
                "raw_html": res_search.text[:2000]
            }

        except Exception as e:
            return {
                "ok": False,
                "diagnostic_code": "BACKEND_EXCEPTION",
                "error": f"Deed document query exception: {str(e)}"
            }

    def generate_stitched_pdf(self, image_urls, output_pdf_path):
        """Downloads images from image_urls, converts them to RGB, and stitches into a PDF."""
        images = []
        try:
            for url in image_urls:
                try:
                    resp = self.session.get(url, timeout=10)
                    if resp.status_code == 200 and len(resp.content) > 100:
                        img = Image.open(io.BytesIO(resp.content))
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                        images.append(img)
                except Exception as img_err:
                    print(f"Skipping unreadable image {url}: {img_err}")
                    continue

            if not images:
                return {"ok": False, "error": "No valid document page scan images could be downloaded."}

            os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)
            images[0].save(output_pdf_path, save_all=True, append_images=images[1:], resolution=100.0, quality=90)

            return {
                "ok": True,
                "pdf_path": output_pdf_path,
                "page_count": len(images),
                "file_size_bytes": os.path.getsize(output_pdf_path)
            }

        except Exception as e:
            return {"ok": False, "error": f"PDF stitching failed: {str(e)}"}
