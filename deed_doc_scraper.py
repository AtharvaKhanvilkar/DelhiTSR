"""
Deed Document Scan Scraper (deed_doc_scraper.py)
Automates authentication, deed document search, page scan extraction,
and PDF stitching from official Delhi government portal (scan.delhigovt.nic.in).
"""

import os
import re
import io
import time
import requests
from bs4 import BeautifulSoup
from PIL import Image

BASE_URL = "https://scan.delhigovt.nic.in"
LOGIN_URL = f"{BASE_URL}/Registration.aspx"
SEARCH_URL = f"{BASE_URL}/SearchForm.aspx"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": BASE_URL,
    "Referer": SEARCH_URL
}

class DorisDocScraper:
    def __init__(self, username=None, password=None, session_cookie=None):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.username = username or os.getenv("DORIS_SCAN_USER", "")
        self.password = password or os.getenv("DORIS_SCAN_PASS", "")
        self.session_cookie = session_cookie or os.getenv("DORIS_SCAN_COOKIE", "")
        
        if self.session_cookie:
            # Set cookie directly on session
            self.session.headers.update({"Cookie": self.session_cookie})
            if "ASP.NET_SessionId" not in self.session_cookie and "=" not in self.session_cookie:
                self.session.cookies.set("ASP.NET_SessionId", self.session_cookie, domain="scan.delhigovt.nic.in")
        
        self.is_logged_in = bool(self.session_cookie)

    def login(self, username=None, password=None):
        """Authenticates against scan.delhigovt.nic.in/Registration.aspx"""
        user = username or self.username
        pwd = password or self.password

        if not user or not pwd:
            return {"ok": False, "error": "Login credentials not configured in settings."}

        try:
            # 1. GET Login Page to extract ViewState
            res = self.session.get(LOGIN_URL, timeout=12)
            if res.status_code != 200:
                return {"ok": False, "error": f"Login page unreachable (HTTP {res.status_code})"}

            soup = BeautifulSoup(res.text, 'html.parser')
            vs = soup.find('input', {'id': '__VIEWSTATE'})
            ev = soup.find('input', {'id': '__EVENTVALIDATION'})

            vs_val = vs['value'] if vs else ""
            ev_val = ev['value'] if ev else ""

            # 2. POST Login Credentials
            payload = {
                "__VIEWSTATE": vs_val,
                "__EVENTVALIDATION": ev_val,
                "ctl00$ContentPlaceHolder1$txtLoginId": user,
                "ctl00$ContentPlaceHolder1$txtPassword": pwd,
                "ctl00$ContentPlaceHolder1$btnLogin": "Login"
            }

            resp = self.session.post(LOGIN_URL, data=payload, timeout=15)
            
            # Check if login succeeded or redirected to SearchForm.aspx
            if "SearchForm.aspx" in resp.url or "Logout" in resp.text or resp.status_code == 200:
                self.is_logged_in = True
                return {"ok": True, "message": "Successfully authenticated with scan.delhigovt.nic.in"}
            else:
                return {"ok": False, "error": "Invalid credentials or portal CAPTCHA required."}

        except Exception as e:
            return {"ok": False, "error": f"Connection error during login: {str(e)}"}

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
