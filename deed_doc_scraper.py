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


def _run_in_pw_thread(fn, timeout=60):
    """Submit a function to the dedicated Playwright thread and wait for result.
    This ensures ALL Playwright calls happen on the same single thread."""
    future = _pw_executor.submit(fn)
    return future.result(timeout=timeout)


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

    # ── Deed Document Search & Extract (persistent Playwright session) ─────
    def fetch_deed_document(self, locality, reg_no, reg_year, sro_name="", book_no="1"):
        """
        Uses the SAME persistent, already-authenticated Playwright session (with the
        locality → SRO cascade completed) to submit the deed search on
        SearchForm.aspx and extract the scan image URLs from the result page.

        Note: sro_name carries the SRO <option> value sent by the frontend hidden
        field, so it is matched against the option value first, then its label.
        """
        try:
            def _do():
                page, context = _ensure_browser()

                # Session must be active on SearchForm.aspx
                if "SearchForm.aspx" not in page.url:
                    page.goto(SEARCH_URL, timeout=30000, wait_until="domcontentloaded")

                if "login.aspx" in page.url.lower():
                    return {"ok": False, "diagnostic_code": "PORTAL_SESSION_EXPIRED",
                            "error": "Government portal session expired. Please sign in again."}

                def _select(selector, wanted):
                    """Select an <option> by value, then visible label, then fuzzy label."""
                    if not wanted:
                        return False
                    for kwargs in ({"value": str(wanted)}, {"label": str(wanted)}):
                        try:
                            page.select_option(selector, **kwargs)
                            return True
                        except Exception:
                            pass
                    try:
                        opts = page.eval_on_selector_all(
                            f"{selector} option",
                            "els => els.map(o => ({value: o.value, label: o.innerText.trim()}))"
                        )
                        w = str(wanted).lower()
                        for o in opts:
                            lbl = o["label"].lower()
                            if lbl and (w in lbl or lbl in w):
                                page.select_option(selector, value=o["value"])
                                return True
                    except Exception:
                        pass
                    return False

                # 1. Select the SRO office (value carried in sro_name)
                if sro_name:
                    _select(ID_DDL_SRO, sro_name)
                    page.wait_for_timeout(500)

                # 2. Fill the registration number
                page.fill(ID_TXT_REGNO, str(reg_no))

                # 3. Select the registration year and book
                _select(ID_DDL_REGYEAR, reg_year)
                _select(ID_DDL_BOOK, book_no)

                # 4. Submit the search and wait for the result table to render
                page.click(ID_BTN_SEARCH)
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    page.wait_for_timeout(3000)

                html = page.content()
                curr_url = page.url

                if "login.aspx" in curr_url.lower():
                    return {"ok": False, "diagnostic_code": "PORTAL_SESSION_EXPIRED",
                            "error": "Government portal session expired during search. Please sign in again."}

                if "Some Error occured" in html or "errorPage" in curr_url:
                    return {"ok": False, "diagnostic_code": "PORTAL_SESSION_EXPIRED",
                            "error": "Government portal returned an error. Session may have expired — please sign in again."}

                # 5. The result table carries a "Check Deed Doc" button that opens the
                #    scanned deed in a popup. If it is absent, there is no record.
                deed_btn = page.locator(
                    "input[value*='Check Deed' i], a:has-text('Check Deed'), "
                    "button:has-text('Check Deed'), :text('Check Deed Doc')"
                ).first
                try:
                    deed_btn.wait_for(state="visible", timeout=8000)
                except Exception:
                    if "No Record" in html or "not found" in html.lower():
                        return {"ok": False, "diagnostic_code": "NO_RECORDS_ON_GOVT_SITE",
                                "error": f"Government database has 0 scanned deed records for Reg No. {reg_no} ({reg_year})."}
                    return {"ok": False, "diagnostic_code": "NO_SCANNED_PAGES_FOUND",
                            "error": f"Could not find the 'Check Deed Doc' button for Reg No. {reg_no} ({reg_year})."}

                # 6. Open the deed popup. The portal renders the deed as a real, complete
                #    PDF (Chrome shows its PDF viewer with Save-as/Print). The best capture
                #    is that PDF itself — far better than screenshotting page images.
                #    We watch the network for the PDF response URL, and also handle the
                #    cases where it opens in a new tab or inside an <embed>/<iframe>.
                pdf_url_candidates = []

                def _on_response(resp):
                    try:
                        u = resp.url
                        ul = u.split("?")[0].lower()
                        is_pdf = ul.endswith(".pdf")
                        if not is_pdf:
                            try:
                                ct = (resp.headers or {}).get("content-type", "").lower()
                                is_pdf = "application/pdf" in ct
                            except Exception:
                                is_pdf = False
                        if is_pdf and u not in pdf_url_candidates:
                            pdf_url_candidates.append(u)
                    except Exception:
                        pass

                opened_pages = []
                context.on("response", _on_response)
                context.on("page", lambda p: opened_pages.append(p))

                deed_btn.click()

                # Wait for the PDF request to appear (or the popup/embed to render)
                for _ in range(24):
                    if pdf_url_candidates:
                        break
                    page.wait_for_timeout(500)

                # Also collect a PDF URL from any newly-opened tab or from an embed/iframe
                for np in opened_pages:
                    try:
                        np.wait_for_load_state("domcontentloaded", timeout=4000)
                    except Exception:
                        pass
                    u = np.url or ""
                    if ".pdf" in u.lower() and u not in pdf_url_candidates:
                        pdf_url_candidates.append(u)

                try:
                    embed_src = page.evaluate("""() => {
                        const els = Array.from(document.querySelectorAll('iframe,embed,object'));
                        for (const e of els) {
                            const s = e.src || e.data || '';
                            if (s && /pdf/i.test(s)) return s;
                        }
                        return null;
                    }""")
                except Exception:
                    embed_src = None
                if embed_src:
                    full = embed_src if embed_src.startswith("http") else f"{BASE_URL}/{embed_src.lstrip('/')}"
                    if full not in pdf_url_candidates:
                        pdf_url_candidates.append(full)

                # Download the deed PDF using the authenticated session
                pdf_body = None
                for u in pdf_url_candidates:
                    full = u if u.startswith("http") else f"{BASE_URL}/{u.lstrip('/')}"
                    try:
                        resp = context.request.get(full, timeout=30000)
                        if resp.ok:
                            body = resp.body()
                            if body and body[:4] == b"%PDF":
                                pdf_body = body
                                break
                    except Exception:
                        continue

                # Fallback: pull the bytes straight from an opened PDF tab (uses its session)
                if not pdf_body:
                    for np in opened_pages:
                        if ".pdf" not in (np.url or "").lower():
                            continue
                        try:
                            b64 = np.evaluate("""async () => {
                                const r = await fetch(location.href);
                                const buf = await r.arrayBuffer();
                                const bytes = new Uint8Array(buf);
                                let bin = '';
                                const chunk = 0x8000;
                                for (let i = 0; i < bytes.length; i += chunk) {
                                    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
                                }
                                return btoa(bin);
                            }""")
                            if b64:
                                raw = base64.b64decode(b64)
                                if raw[:4] == b"%PDF":
                                    pdf_body = raw
                                    break
                        except Exception:
                            continue

                # Tidy up: stop listening and close any popup tabs
                try:
                    context.remove_listener("response", _on_response)
                except Exception:
                    pass
                for np in opened_pages:
                    try:
                        if np != page:
                            np.close()
                    except Exception:
                        pass

                if pdf_body:
                    try:
                        pages = len(re.findall(rb'/Type\s*/Page[^s]', pdf_body)) or None
                    except Exception:
                        pages = None
                    return {"ok": True, "diagnostic_code": "SUCCESS",
                            "pdf_bytes_b64": base64.b64encode(pdf_body).decode("utf-8"),
                            "total_pages": pages}

                # ── Fallback: no downloadable PDF found → capture rendered scan images ──
                page.wait_for_timeout(1500)

                # JS that (a) scrolls every scrollable container one screen at a time to
                # trigger lazy-loaded pages, and (b) tags every genuine deed scan image.
                # Placeholders, logos and CAPTCHAs are filtered out by src + size.
                tag_js = r"""() => {
                    const bad = /wait|process|loading|spinner|logo|emblem|ashok|banner|header|captcha|jpegimage|\.gif/i;
                    // Step forward through any scrollable panes to load more pages
                    document.querySelectorAll('*').forEach(e => {
                        const s = getComputedStyle(e);
                        if ((s.overflowY === 'auto' || s.overflowY === 'scroll') &&
                            e.scrollHeight > e.clientHeight + 20) {
                            e.scrollTop = Math.min(e.scrollTop + e.clientHeight, e.scrollHeight);
                        }
                    });
                    let n = 0;
                    document.querySelectorAll('img').forEach(img => {
                        img.removeAttribute('data-deedcap');
                        const src = img.src || '';
                        const bigEnough = img.naturalWidth > 150 && img.naturalHeight > 150;
                        const rect = img.getBoundingClientRect();
                        const shown = rect.width > 120 && rect.height > 120;
                        if (bigEnough && shown && !bad.test(src)) {
                            img.setAttribute('data-deedcap', '1');
                            n++;
                        }
                    });
                    return n;
                }"""

                deadline = time.time() + 35
                last_count = -1
                stable = 0
                while time.time() < deadline:
                    count = page.evaluate(tag_js)
                    if count > 0 and count == last_count:
                        stable += 1
                        if stable >= 2:
                            break
                    else:
                        stable = 0
                    last_count = count
                    page.wait_for_timeout(900)

                # 7. Capture each tagged deed page. Prefer native-resolution bytes
                #    (data: URI or the same-session image URL); fall back to a rendered
                #    screenshot of the element if the bytes are unavailable.
                handles = page.query_selector_all('img[data-deedcap="1"]')
                page_images_b64 = []
                for el in handles:
                    src = el.get_attribute('src') or ''
                    raw = None
                    try:
                        if src.startswith('data:image'):
                            raw = base64.b64decode(src.split(',', 1)[1])
                        elif src.startswith('http'):
                            resp = context.request.get(src, timeout=15000)
                            if resp.ok:
                                raw = resp.body()
                    except Exception:
                        raw = None
                    if not raw or len(raw) < 100:
                        try:
                            raw = el.screenshot()
                        except Exception:
                            raw = None
                    if raw and len(raw) >= 100:
                        page_images_b64.append(base64.b64encode(raw).decode('utf-8'))

                if not page_images_b64:
                    # Save a debug snapshot so the failure can be diagnosed
                    try:
                        with open(os.path.join(os.getcwd(), "deed_modal_debug.html"), "w", encoding="utf-8") as f:
                            f.write(page.content())
                        page.screenshot(path=os.path.join(os.getcwd(), "deed_modal_debug.png"), full_page=True)
                    except Exception:
                        pass
                    return {"ok": False, "diagnostic_code": "NO_SCANNED_PAGES_FOUND",
                            "error": (f"Opened the deed viewer but could not capture scan pages for "
                                      f"Reg No. {reg_no} ({reg_year}). A debug snapshot was saved.")}

                return {"ok": True, "diagnostic_code": "SUCCESS",
                        "page_images_b64": page_images_b64, "total_pages": len(page_images_b64)}

            return _run_in_pw_thread(_do, timeout=120)
        except Exception as e:
            return {"ok": False, "diagnostic_code": "BACKEND_EXCEPTION",
                    "error": f"Deed document query exception: {str(e)}"}

    def generate_stitched_pdf(self, page_images_b64, output_pdf_path):
        """Stitches the captured deed page images (base64 PNG/JPEG strings) into one PDF."""
        try:
            images = []
            for b64 in page_images_b64:
                try:
                    raw = base64.b64decode(b64)
                    img = Image.open(io.BytesIO(raw))
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    images.append(img)
                except Exception as e:
                    print(f"Skipping undecodable page image: {e}")
                    continue

            if not images:
                return {"ok": False, "error": "No valid deed scan pages were captured."}

            os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)
            images[0].save(output_pdf_path, save_all=True, append_images=images[1:], resolution=150.0)

            return {
                "ok": True,
                "pdf_path": output_pdf_path,
                "page_count": len(images),
                "file_size_bytes": os.path.getsize(output_pdf_path)
            }

        except Exception as e:
            return {"ok": False, "error": f"PDF stitching failed: {str(e)}"}
