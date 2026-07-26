"""
Deed Document Scan Scraper (deed_doc_scraper.py)
Automates authentication, deed document search, page scan extraction,
and PDF stitching from official Delhi government portal (scan.delhigovt.nic.in).
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": BASE_URL,
    "Referer": SEARCH_URL
}

class DorisDocScraper:
    _playwright_instance = None
    _browser_instance = None
    _context_instance = None
    _page_instance = None

    def __init__(self, username=None, password=None, session_cookie=None):
        self.username = username or os.getenv("DORIS_SCAN_USER", "")
        self.password = password or os.getenv("DORIS_SCAN_PASS", "")
        self.session_cookie = session_cookie

    @classmethod
    def get_playwright_page(cls):
        """Returns active Playwright page instance, initializing if needed."""
        if cls._page_instance and not cls._page_instance.is_closed():
            return cls._page_instance

        if not cls._playwright_instance:
            cls._playwright_instance = sync_playwright().start()

        if not cls._browser_instance:
            cls._browser_instance = cls._playwright_instance.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )

        if not cls._context_instance:
            cls._context_instance = cls._browser_instance.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

        cls._page_instance = cls._context_instance.new_page()
        return cls._page_instance

    def start_login_session(self):
        """Loads Login.aspx in Playwright and captures the live CAPTCHA element screenshot."""
        try:
            page = self.get_playwright_page()
            page.goto(LOGIN_URL, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_selector("#IMG4, img[src*='JpegImage']", timeout=10000)

            captcha_el = page.query_selector("#IMG4") or page.query_selector("img[src*='JpegImage']")
            if not captcha_el:
                return {"ok": False, "error": "CAPTCHA image element not found on Login.aspx"}

            png_bytes = captcha_el.screenshot()
            b64_str = f"data:image/png;base64,{base64.b64encode(png_bytes).decode('utf-8')}"
            return {"ok": True, "captcha_b64": b64_str}
        except Exception as e:
            return {"ok": False, "error": f"Failed to load Login page via Playwright: {str(e)}"}

    def submit_login_with_captcha(self, username, password, captcha_code):
        """Fills login form in Playwright, submits CAPTCHA, and verifies authentication."""
        user = username or self.username
        pwd = password or self.password
        try:
            page = self.get_playwright_page()
            if "Login.aspx" not in page.url:
                page.goto(LOGIN_URL, timeout=30000, wait_until="domcontentloaded")

            # Fill inputs
            page.fill("#ctl00_ContentPlaceHolder1_txtuserid", user)
            page.fill("#ctl00_ContentPlaceHolder1_txtpwd", pwd)
            page.fill("#ctl00_ContentPlaceHolder1_txtcaptcha", str(captcha_code).strip())

            # Click Sign In
            page.click("#ctl00_ContentPlaceHolder1_btnlogin")
            page.wait_for_timeout(3000)

            curr_url = page.url
            page_content = page.content()

            if "SearchForm.aspx" in curr_url or "Logout" in page_content:
                cookies = page.context.cookies()
                cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                return {"ok": True, "cookie_str": cookie_str, "message": "Authenticated with scan.delhigovt.nic.in!"}
            else:
                return {"ok": False, "error": "Login failed. Please check Visual Code or credentials."}
        except Exception as e:
            return {"ok": False, "error": f"Login submission error: {str(e)}"}

    def get_sro_list(self):
        """Extracts live SRO list from Playwright page DOM."""
        try:
            page = self.get_playwright_page()
            if "SearchForm.aspx" not in page.url:
                page.goto(SEARCH_URL, timeout=30000, wait_until="domcontentloaded")

            if "Login.aspx" in page.url or "Logout.aspx" in page.url:
                return {"ok": False, "diagnostic_code": "PORTAL_SESSION_EXPIRED", "error": "Session expired."}

            sro_select = page.query_selector("select[id*='ddlSRO']") or page.query_selector("select")
            if not sro_select:
                return {"ok": False, "error": "SRO dropdown element not found on page"}

            options = page.eval_on_selector_all("select option", "opts => opts.map(o => ({id: o.value.trim(), name: o.innerText.trim()}))")
            sro_list = [o for o in options if o["id"] and o["id"] != "0" and "select" not in o["name"].lower()]
            return {"ok": True, "sro_list": sro_list}
        except Exception as e:
            return {"ok": False, "error": f"Failed to fetch SRO list: {str(e)}"}

    def get_locality_list(self, sro_val="0"):
        """Selects SRO in Playwright live page and extracts live localities from DOM."""
        try:
            page = self.get_playwright_page()
            if "SearchForm.aspx" not in page.url:
                page.goto(SEARCH_URL, timeout=30000, wait_until="domcontentloaded")

            if "Login.aspx" in page.url or "Logout.aspx" in page.url:
                return {"ok": False, "diagnostic_code": "PORTAL_SESSION_EXPIRED", "error": "Session expired."}

            # Select SRO if provided
            if sro_val and sro_val != "0":
                page.select_option("select[id*='ddlSRO']", sro_val)
                page.wait_for_timeout(1000)

            # Extract locality options or autocompletes from DOM
            options = page.eval_on_selector_all("select option", "opts => opts.map(o => ({id: o.value.trim(), name: o.innerText.trim()}))")
            loc_list = [o for o in options if o["id"] and o["id"] != "0" and "select" not in o["name"].lower()]
            return {"ok": True, "locality_list": loc_list}
        except Exception as e:
            return {"ok": False, "error": f"Failed to fetch locality list: {str(e)}"}

    def fetch_deed_document(self, locality, reg_no, reg_year, sro_name="", book_no="1"):
        """
        Submits search request on SearchForm.aspx and extracts scan images.
        Converts extracted scans into a stitched PDF.
        """
        try:
            # Ensure session is active
            res_form = self.session.get(SEARCH_URL, timeout=12)
            if res_form.status_code != 200:
                # Attempt re-login
                login_res = self.login()
                if not login_res["ok"]:
                    return login_res
                res_form = self.session.get(SEARCH_URL, timeout=12)

            soup = BeautifulSoup(res_form.text, 'html.parser')
            vs = soup.find('input', {'id': '__VIEWSTATE'})
            ev = soup.find('input', {'id': '__EVENTVALIDATION'})

            vs_val = vs['value'] if vs else ""
            ev_val = ev['value'] if ev else ""

            # Extract SRO dropdown option matching sro_name
            sro_val = "0"
            sro_select = soup.find('select', {'id': re.compile(r'ddlSRO', re.I)})
            if sro_select and sro_name:
                for opt in sro_select.find_all('option'):
                    if sro_name.lower() in opt.text.lower() or opt.text.lower() in sro_name.lower():
                        sro_val = opt.get('value', '0')
                        break

            # Build ASP.NET Search Payload
            payload = {
                "__VIEWSTATE": vs_val,
                "__EVENTVALIDATION": ev_val,
                "ctl00$ContentPlaceHolder1$txtLocality": locality or "",
                "ctl00$ContentPlaceHolder1$ddlSRO": sro_val,
                "ctl00$ContentPlaceHolder1$txtRegNo": str(reg_no),
                "ctl00$ContentPlaceHolder1$ddlRegYear": str(reg_year),
                "ctl00$ContentPlaceHolder1$ddlBookNo": str(book_no),
                "ctl00$ContentPlaceHolder1$btnSearch": "Search"
            }

            res_search = self.session.post(SEARCH_URL, data=payload, timeout=18)
            if res_search.status_code != 200:
                return {
                    "ok": False,
                    "diagnostic_code": "BACKEND_HTTP_ERROR",
                    "error": f"Portal returned HTTP {res_search.status_code}."
                }

            # Check if portal redirected to Logout/Error page
            if "Logout" in res_search.url or "errorPage" in res_search.url or "Some Error occured" in res_search.text:
                return {
                    "ok": False,
                    "diagnostic_code": "PORTAL_SESSION_EXPIRED",
                    "error": "Government portal session expired or blocked automated login. Active session cookie required."
                }

            search_soup = BeautifulSoup(res_search.text, 'html.parser')
            
            # Find page scan image tags or iframe sources
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
                # Also check links / anchors
                links = search_soup.find_all('a', {'href': re.compile(r'(View|Show|Doc|Page)', re.I)})
                for a in links:
                    href = a.get('href', '')
                    if not href.startswith('http'):
                        href = f"{BASE_URL}/{href.lstrip('/')}"
                    image_urls.append(href)

            if not image_urls:
                # Check if "No Records Found" or "Check Deed Doc" button was missing
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
